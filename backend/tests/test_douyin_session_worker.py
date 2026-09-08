from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.douyin_session import worker as worker_module
from app.douyin_session.models import CapturedMedia, PlayerDiagnostics, SessionWorkerResult
from app.douyin_session.worker import DouyinSessionWorker, PlaywrightSessionAdapter
from app.errors import AppError
from app.services.safe_http import SafeHttpClient

WORK_ID = "7123456789012345678"
TARGET_URL = f"https://www.douyin.com/video/{WORK_ID}"
MEDIA_URL = "https://cdn.example.com/signed-path/video.mp4?signature=must-not-log"


async def public_resolver(host: str) -> list[str]:
    if host in {"www.douyin.com", "cdn.example.com"}:
        return ["93.184.216.34"]
    return ["127.0.0.1"]


def session_settings(tmp_path: Path, **changes: object) -> Settings:
    state_path = tmp_path / "operator-state.json"
    state_path.write_text(
        json.dumps({"cookies": [{"value": "secret-session-cookie"}], "origins": []}),
        encoding="utf-8",
    )
    values: dict[str, object] = {
        "app_env": "test",
        "douyin_session_enabled": True,
        "douyin_storage_state_path": state_path,
        "douyin_session_timeout_seconds": 5,
    }
    values.update(changes)
    return Settings(**values)


def safe_http(handler) -> SafeHttpClient:
    return SafeHttpClient(
        timeout_seconds=2,
        max_redirects=2,
        max_video_bytes=10 * 1024 * 1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )


class FakeBrowser:
    def __init__(self, capture: CapturedMedia, *, wait: asyncio.Event | None = None) -> None:
        self.capture_result = capture
        self.wait = wait
        self.calls: list[dict[str, object]] = []

    async def capture(self, **kwargs) -> CapturedMedia:
        self.calls.append(kwargs)
        if self.wait is not None:
            await self.wait.wait()
        return self.capture_result


class SlowBrowser(FakeBrowser):
    async def capture(self, **kwargs) -> CapturedMedia:
        await asyncio.sleep(0.02)
        return await super().capture(**kwargs)


def video_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("cookie") is None
    assert request.headers.get("authorization") is None
    assert all("token" not in key.lower() for key in request.headers)
    assert request.headers["referer"] == TARGET_URL
    assert request.headers["origin"] == "https://www.douyin.com"
    assert request.headers.get("user-agent")
    assert request.headers.get("accept")
    if request.method == "HEAD":
        return httpx.Response(200, headers={"content-type": "video/mp4", "content-length": "2048"})
    assert request.headers.get("range") == "bytes=0-1023"
    return httpx.Response(206, headers={"content-type": "video/mp4"}, content=b"v" * 1024)


@pytest.mark.asyncio
async def test_session_worker_keeps_cookie_out_of_public_probe_and_result(tmp_path: Path, caplog) -> None:
    browser = FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL))
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=browser,
    )

    result = await worker.inspect(TARGET_URL)

    assert isinstance(result, SessionWorkerResult)
    assert result.target_id == WORK_ID
    assert result.bytes_read == 1024
    assert result.media_origin == "https://cdn.example.com"
    assert "signature" not in caplog.text
    assert "signed-path" not in caplog.text
    assert "cookies" not in repr(result)
    assert "secret-session-cookie" not in caplog.text
    assert browser.calls[0]["target_id"] == WORK_ID


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_code"),
    [("expired", "DOUYIN_SESSION_EXPIRED"), ("risk", "DOUYIN_RISK_CONTROLLED")],
)
async def test_session_worker_stops_for_expired_or_risk_state(
    tmp_path: Path,
    state: str,
    expected_code: str,
) -> None:
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(target_id=None, media_url=None, state=state)),
    )

    with pytest.raises(AppError) as caught:
        await worker.inspect(TARGET_URL)

    assert caught.value.code == expected_code


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "expected_code"),
    [
        ("player_missing", "DOUYIN_SESSION_PLAYER_NOT_FOUND"),
        ("media_missing", "DOUYIN_SESSION_MEDIA_NOT_FOUND"),
    ],
)
async def test_session_worker_keeps_distinct_player_capture_failures(
    tmp_path: Path,
    state: str,
    expected_code: str,
) -> None:
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=None, state=state)),
    )

    with pytest.raises(AppError) as caught:
        await worker.inspect(TARGET_URL)

    assert caught.value.code == expected_code


@pytest.mark.asyncio
async def test_session_worker_rejects_wrong_work_and_private_media(tmp_path: Path) -> None:
    wrong = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(target_id="7999999999999999999", media_url=MEDIA_URL)),
    )
    with pytest.raises(AppError, match="目标") as caught:
        await wrong.inspect(TARGET_URL)
    assert caught.value.code == "DOUYIN_SESSION_TARGET_MISMATCH"

    def private_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    private = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(private_handler),
        browser=FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL)),
    )
    with pytest.raises(AppError) as private_error:
        await private.inspect(TARGET_URL)
    assert private_error.value.code == "SESSION_BOUND_MEDIA"


@pytest.mark.asyncio
async def test_session_worker_rejects_invalid_target_and_ssrf_media(tmp_path: Path) -> None:
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url="http://127.0.0.1/private.mp4")),
    )
    with pytest.raises(AppError) as invalid_target:
        await worker.inspect(f"{TARGET_URL}?share=1")
    assert invalid_target.value.code == "URL_INVALID"
    with pytest.raises(AppError) as ssrf:
        await worker.inspect(TARGET_URL)
    assert ssrf.value.code == "URL_INVALID"


@pytest.mark.asyncio
async def test_session_worker_maps_missing_state_configuration_to_safe_error(tmp_path: Path, caplog) -> None:
    worker = DouyinSessionWorker(
        settings=Settings(app_env="test", douyin_session_enabled=True),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL)),
    )

    with pytest.raises(AppError) as caught:
        await worker.inspect(TARGET_URL)

    assert caught.value.code == "DOUYIN_SESSION_CONFIG_INVALID"
    assert "DOUYIN_STORAGE_STATE_PATH" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "expected_code"),
    [
        ({"content-type": "text/html", "content-length": "2048"}, "MEDIA_FORMAT_UNSUPPORTED"),
        ({"content-type": "video/mp4", "content-length": str(20 * 1024 * 1024)}, "MEDIA_TOO_LARGE"),
    ],
)
async def test_session_worker_keeps_safe_media_type_and_size_limits(
    tmp_path: Path,
    headers: dict[str, str],
    expected_code: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers=headers)
        raise AssertionError("invalid media must not be streamed")

    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(handler),
        browser=FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL)),
    )
    with pytest.raises(AppError) as caught:
        await worker.inspect(TARGET_URL)
    assert caught.value.code == expected_code


@pytest.mark.asyncio
async def test_session_worker_enforces_browser_timeout(tmp_path: Path) -> None:
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path, douyin_session_timeout_seconds=1),
        http=safe_http(video_handler),
        browser=SlowBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL)),
    )
    worker.settings.douyin_session_launch_timeout_seconds = 0.001  # type: ignore[assignment]
    worker.settings.douyin_session_navigation_timeout_seconds = 0.001  # type: ignore[assignment]
    worker.settings.douyin_session_player_timeout_seconds = 0.001  # type: ignore[assignment]
    worker.settings.douyin_session_media_capture_timeout_seconds = 0.001  # type: ignore[assignment]

    with pytest.raises(AppError) as caught:
        await worker.inspect(TARGET_URL)

    assert caught.value.code == "DOUYIN_SESSION_TIMEOUT"


@pytest.mark.asyncio
async def test_session_worker_serialises_concurrent_browser_access(tmp_path: Path) -> None:
    release = asyncio.Event()
    browser = FakeBrowser(CapturedMedia(target_id=WORK_ID, media_url=MEDIA_URL), wait=release)
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=browser,
    )
    first = asyncio.create_task(worker.inspect(TARGET_URL))
    await asyncio.sleep(0)
    second = asyncio.create_task(worker.inspect(TARGET_URL))
    await asyncio.sleep(0)
    assert len(browser.calls) == 1
    release.set()
    await first
    await second
    assert len(browser.calls) == 2


class AdapterRequest:
    resource_type = "media"


class AdapterResponse:
    def __init__(
        self,
        url: str,
        content_type: str = "video/mp4",
        resource_type: str = "media",
    ) -> None:
        self.url = url
        self.headers = {"content-type": content_type}
        self.request = AdapterRequest()
        self.request.resource_type = resource_type


class AdapterRiskLocator:
    def __init__(self, visible: bool) -> None:
        self.visible = visible
        self.first = self

    async def is_visible(self, **kwargs: int) -> bool:
        assert kwargs["timeout"] == 250
        return self.visible


class AdapterPage:
    def __init__(
        self,
        *,
        final_url: str = TARGET_URL,
        current_src: str = "",
        src: str = "",
        source_urls: list[str] | None = None,
        delayed_src: str = "",
        document: str = "<html></html>",
        risk_visible: bool = False,
        responses: list[AdapterResponse] | None = None,
        play_responses: list[AdapterResponse] | None = None,
        visible: bool = True,
    ) -> None:
        self.url = final_url
        self.current_src = current_src
        self.src = src
        self.source_urls = source_urls or []
        self.delayed_src = delayed_src
        self.document = document
        self.risk_visible = risk_visible
        self.responses = responses or []
        self.play_responses = play_responses or []
        self.visible = visible
        self.callbacks: list = []
        self.waited = False

    def on(self, event: str, callback) -> None:
        assert event == "response"
        self.callbacks.append(callback)

    async def goto(self, _url: str, **kwargs: object) -> None:
        assert kwargs["wait_until"] == "domcontentloaded"
        assert isinstance(kwargs["timeout"], int) and kwargs["timeout"] > 0
        for response in self.responses:
            for callback in self.callbacks:
                callback(response)

    def locator(self, _selector: str) -> AdapterRiskLocator:
        return AdapterRiskLocator(self.risk_visible)

    async def wait_for_function(self, _script: str, **kwargs: int) -> None:
        assert kwargs["timeout"] > 0
        self.waited = True
        if "rect.width > 120" in _script and not self.visible:
            timeout_error = type("TimeoutError", (Exception,), {})
            raise timeout_error()
        if self.delayed_src:
            self.current_src = self.delayed_src
        if "currentSrc || video.src" in _script and not (
            self.current_src or self.src or self.source_urls
        ):
            timeout_error = type("TimeoutError", (Exception,), {})
            raise timeout_error()

    async def evaluate(self, script: str):
        if "scrollIntoView" in script:
            for response in self.play_responses:
                for callback in self.callbacks:
                    callback(response)
            return True
        if "source_urls" in script:
            primary = None
            if self.visible:
                primary = {
                    "visible": True,
                    "current_src": self.current_src,
                    "src": self.src,
                    "source_urls": self.source_urls,
                }
            return {
                "video_count": 1 if self.visible else 0,
                "visible_video_count": 1 if self.visible else 0,
                "primary": primary,
            }
        return ""

    async def content(self) -> str:
        return self.document


class AdapterContext:
    def __init__(self, page: AdapterPage) -> None:
        self.page = page

    async def new_page(self) -> AdapterPage:
        return self.page

    async def close(self) -> None:
        return None


class AdapterBrowser:
    def __init__(self, page: AdapterPage) -> None:
        self.page = page

    async def new_context(self, *, storage_state: str) -> AdapterContext:
        assert storage_state.endswith("operator-state.json")
        return AdapterContext(self.page)

    async def close(self) -> None:
        return None


class AdapterChromium:
    def __init__(self, page: AdapterPage) -> None:
        self.page = page

    async def launch(self, *, headless: bool) -> AdapterBrowser:
        self.page.headless = headless
        return AdapterBrowser(self.page)


class AdapterPlaywright:
    def __init__(self, page: AdapterPage) -> None:
        self.chromium = AdapterChromium(page)


class AdapterManager:
    def __init__(self, page: AdapterPage) -> None:
        self.page = page

    async def __aenter__(self) -> AdapterPlaywright:
        return AdapterPlaywright(self.page)

    async def __aexit__(self, *_args) -> None:
        return None


def adapter_for(page: AdapterPage) -> PlaywrightSessionAdapter:
    return PlaywrightSessionAdapter(playwright_factory=lambda: AdapterManager(page))


@pytest.mark.asyncio
async def test_playwright_adapter_calls_lazy_loader_then_its_context_manager_factory(monkeypatch) -> None:
    calls: list[str] = []
    page = AdapterPage(current_src=MEDIA_URL)

    def context_manager_factory() -> AdapterManager:
        calls.append("context-manager-factory")
        return AdapterManager(page)

    def lazy_loader():
        calls.append("lazy-loader")
        return context_manager_factory

    monkeypatch.setattr(worker_module, "_load_async_playwright", lazy_loader)
    captured = await PlaywrightSessionAdapter().capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.media_url == MEDIA_URL
    assert calls == ["lazy-loader", "context-manager-factory"]


@pytest.mark.asyncio
async def test_playwright_adapter_captures_cdn_source_without_work_id() -> None:
    cdn_url = "https://cdn.example.com/encoded/video.mp4?signature=hidden"
    page = AdapterPage(current_src=cdn_url, responses=[AdapterResponse(cdn_url)])

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert page.waited is True
    assert captured.target_id == WORK_ID
    assert captured.media_url == cdn_url


@pytest.mark.asyncio
async def test_playwright_adapter_waits_for_delayed_primary_current_src() -> None:
    delayed_url = "https://cdn.example.com/delayed.mp4"
    page = AdapterPage(delayed_src=delayed_url)

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert page.waited is True
    assert captured.media_url == delayed_url


@pytest.mark.asyncio
async def test_playwright_adapter_reads_primary_video_src_and_source_child() -> None:
    src_url = "https://cdn.example.com/from-src.mp4"
    source_url = "https://cdn.example.com/from-source.m3u8"
    from_src = await adapter_for(AdapterPage(src=src_url)).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )
    from_source = await adapter_for(AdapterPage(source_urls=[source_url])).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert from_src.media_url == src_url
    assert from_source.media_url == source_url


@pytest.mark.asyncio
async def test_playwright_adapter_uses_single_post_playback_response_for_blob_player() -> None:
    network_url = "https://cdn.example.com/blob-backed.mp4?signature=hidden"
    page = AdapterPage(
        current_src="blob:https://www.douyin.com/opaque",
        play_responses=[
            AdapterResponse(network_url, "application/vnd.apple.mpegurl", resource_type="fetch")
        ],
    )

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.media_url == network_url
    assert captured.diagnostics is not None
    assert captured.diagnostics.has_blob_url is True
    assert captured.diagnostics.media_domains == ("cdn.example.com",)
    assert captured.diagnostics.media_content_types == ("application/vnd.apple.mpegurl",)


@pytest.mark.asyncio
async def test_playwright_adapter_rejects_multiple_blob_network_candidates_as_ambiguous() -> None:
    page = AdapterPage(
        current_src="blob:https://www.douyin.com/opaque",
        play_responses=[
            AdapterResponse("https://ads.example.com/ad.mp4"),
            AdapterResponse("https://cdn.example.com/recommendation.mp4"),
        ],
    )

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.state == "media_missing"
    assert captured.media_url is None


@pytest.mark.asyncio
async def test_playwright_adapter_does_not_select_ad_or_recommendation_network_media() -> None:
    primary_url = "https://cdn.example.com/target.mp4"
    page = AdapterPage(
        current_src=primary_url,
        responses=[
            AdapterResponse("https://ads.example.com/ad.mp4"),
            AdapterResponse("https://cdn.example.com/recommended.mp4"),
        ],
    )

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.media_url == primary_url


@pytest.mark.asyncio
async def test_playwright_adapter_can_run_visible_for_manual_smoke() -> None:
    page = AdapterPage(current_src=MEDIA_URL)
    await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
        headless=False,
    )

    assert page.headless is False


@pytest.mark.asyncio
async def test_session_worker_logs_only_safe_player_diagnostics(tmp_path: Path, caplog) -> None:
    diagnostics = PlayerDiagnostics(
        page_route=TARGET_URL,
        target_id=WORK_ID,
        video_count=2,
        visible_video_count=1,
        has_current_src=True,
        has_src=False,
        has_source_child=False,
        has_blob_url=False,
        media_response_count=1,
        media_content_types=("video/mp4",),
        media_domains=("cdn.example.com",),
        last_phase="media_capture",
        phase_ms=(("browser_launch", 1), ("media_capture", 2)),
    )
    worker = DouyinSessionWorker(
        settings=session_settings(tmp_path),
        http=safe_http(video_handler),
        browser=FakeBrowser(CapturedMedia(WORK_ID, MEDIA_URL, diagnostics=diagnostics)),
    )

    await worker.inspect(TARGET_URL)

    assert "cdn.example.com" in caplog.text
    assert "signed-path" not in caplog.text
    assert "signature" not in caplog.text
    assert "secret-session-cookie" not in caplog.text


@pytest.mark.asyncio
async def test_playwright_adapter_rejects_mismatched_page_before_media_capture() -> None:
    page = AdapterPage(final_url="https://www.douyin.com/video/7999999999999999999", current_src=MEDIA_URL)

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.state == "mismatch"
    assert page.waited is False


@pytest.mark.asyncio
async def test_playwright_adapter_marks_missing_primary_player_separately() -> None:
    page = AdapterPage(visible=False)

    captured = await adapter_for(page).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )

    assert captured.state == "player_missing"
    assert captured.target_id == WORK_ID


@pytest.mark.asyncio
async def test_playwright_adapter_ignores_hidden_captcha_text_but_stops_for_visible_risk() -> None:
    hidden = AdapterPage(
        current_src=MEDIA_URL,
        document="<script>const captcha = 'hidden test text'</script>",
    )
    captured = await adapter_for(hidden).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )
    assert captured.state == "ok"

    visible = AdapterPage(current_src=MEDIA_URL, risk_visible=True)
    risk = await adapter_for(visible).capture(
        target_url=TARGET_URL,
        target_id=WORK_ID,
        storage_state_path="C:/outside/operator-state.json",
        timeout_seconds=3,
    )
    assert risk.state == "risk"
