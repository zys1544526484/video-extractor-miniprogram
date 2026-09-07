from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.douyin_session.models import CapturedMedia, SessionWorkerResult
from app.douyin_session.worker import DouyinSessionWorker
from app.errors import AppError
from app.services.safe_http import SafeHttpClient

WORK_ID = "7123456789012345678"
TARGET_URL = f"https://www.douyin.com/video/{WORK_ID}"
MEDIA_URL = "https://cdn.example.com/video.mp4?signature=must-not-log"


async def public_resolver(host: str) -> list[str]:
    if host in {"www.douyin.com", "cdn.example.com"}:
        return ["93.184.216.34"]
    return ["127.0.0.1"]


def session_settings(tmp_path: Path, **changes: object) -> Settings:
    state_path = tmp_path / "operator-state.json"
    state_path.write_text(json.dumps({"cookies": [], "origins": []}), encoding="utf-8")
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


def video_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers.get("cookie") is None
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
    assert result.media_origin == "https://cdn.example.com/video.mp4"
    assert "signature" not in caplog.text
    assert "cookies" not in repr(result)
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
