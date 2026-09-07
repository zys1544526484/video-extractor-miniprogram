from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.douyin_session.models import SessionWorkerResult
from app.douyin_session.smoke import SmokeOutput, resolve_smoke_target, run_smoke
from app.errors import AppError
from app.services.safe_http import SafeHttpClient

WORK_ID = "7123456789012345678"
SHORT_URL = "https://v.douyin.com/example-short/"
CANONICAL_URL = f"https://www.douyin.com/video/{WORK_ID}"


async def public_resolver(host: str) -> list[str]:
    if host in {"v.douyin.com", "www.douyin.com"}:
        return ["93.184.216.34"]
    return ["127.0.0.1"]


def safe_http(handler) -> SafeHttpClient:
    return SafeHttpClient(
        timeout_seconds=2,
        max_redirects=2,
        max_video_bytes=10 * 1024 * 1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )


class FakeWorker:
    def __init__(self, result: SessionWorkerResult | AppError) -> None:
        self.result = result
        self.urls: list[str] = []

    async def inspect(self, target_url: str) -> SessionWorkerResult:
        self.urls.append(target_url)
        if isinstance(self.result, AppError):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_smoke_resolves_short_link_without_hardcoding_real_link() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(302, headers={"location": CANONICAL_URL})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    resolved, work_id = await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert resolved == CANONICAL_URL
    assert work_id == WORK_ID


@pytest.mark.asyncio
async def test_smoke_output_only_contains_safe_fields() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    worker = FakeWorker(
        SessionWorkerResult(
            target_id=WORK_ID,
            media_origin="https://cdn.example.com",
            size_bytes=2048,
            bytes_read=1024,
            elapsed_ms=1,
        )
    )
    output = await run_smoke(
        Settings(app_env="test", douyin_session_enabled=True),
        CANONICAL_URL,
        http=safe_http(handler),
        worker=worker,  # type: ignore[arg-type]
    )

    payload = json.dumps(output.__dict__)
    assert output.outcome == "success"
    assert worker.urls == [CANONICAL_URL]
    assert "signature" not in payload
    assert "cookie" not in payload.lower()
    assert "?" not in payload


@pytest.mark.asyncio
async def test_smoke_invalid_final_url_uses_stable_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>home</html>")

    output = await run_smoke(
        Settings(app_env="test"),
        SHORT_URL,
        http=safe_http(handler),
        worker=FakeWorker(AppError("UNUSED", "unused")),  # type: ignore[arg-type]
    )

    assert output.outcome == "failure"
    assert output.error_code == "DOUYIN_RESOLVE_FAILED"
    assert output.work_id is None


def test_smoke_output_schema_has_no_url_or_path_fields() -> None:
    assert set(SmokeOutput.__annotations__) == {
        "outcome",
        "error_code",
        "work_id",
        "media_domain",
        "bytes_read",
        "elapsed_ms",
    }
