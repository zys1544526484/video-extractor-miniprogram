from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.douyin_session.models import CapturedMedia, SessionWorkerResult
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
    worker.settings.douyin_session_timeout_seconds = 0.001  # type: ignore[assignment]

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
    def __init__(self, url: str, content_type: str = "video/mp4") -> None:
        self.url = url
        self.headers = {"content-type": content_type}
        self.request = AdapterRequest()


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
        delayed_src: str = "",
        document: str = "<html></html>",
        risk_visible: bool = False,
        responses: list[AdapterResponse] | None = None,
    ) -> None:
        self.url = final_url
        self.current_src = current_src
        self.delayed_src = delayed_src
        self.document = document
        self.risk_visible = risk_visible
        self.responses = responses or []
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
        if self.delayed_src:
            self.current_src = self.delayed_src
        if not self.current_src:
            timeout_error = type("TimeoutError", (Exception,), {})
            raise timeout_error()

    async def evaluate(self, _script: str) -> str:
        return self.current_src

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
        assert headless is True
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
