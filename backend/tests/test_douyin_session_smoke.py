from __future__ import annotations

import json

import httpx
import pytest

from app.config import Settings
from app.douyin_session.models import SessionWorkerResult
from app.douyin_session.smoke import (
    SmokeOutput,
    resolve_smoke_target,
    run_smoke,
    sanitise_redirect_hop,
)
from app.errors import AppError
from app.services.safe_http import SafeHttpClient

WORK_ID = "7123456789012345678"
SHORT_URL = "https://v.douyin.com/example-short/"
CANONICAL_URL = f"https://www.douyin.com/video/{WORK_ID}"


async def public_resolver(host: str) -> list[str]:
    if host in {
        "v.douyin.com",
        "www.douyin.com",
        "douyin.com",
        "www.iesdouyin.com",
        "attacker.example.com",
    }:
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
async def test_smoke_normalises_short_link_redirect_with_query_without_logging_it(caplog) -> None:
    query_target = f"{CANONICAL_URL}?share_token=do-not-log#fragment"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            assert request.headers.get("cookie") is None
            assert request.headers.get("authorization") is None
            return httpx.Response(302, headers={"location": query_target})
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    resolved, work_id = await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert resolved == CANONICAL_URL
    assert work_id == WORK_ID
    assert "share_token" not in caplog.text
    assert "do-not-log" not in caplog.text
    assert "fragment" not in caplog.text


@pytest.mark.asyncio
async def test_smoke_normalises_iesdouyin_share_video_route() -> None:
    share_url = f"https://www.iesdouyin.com/share/video/{WORK_ID}?from=share"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html></html>")

    resolved, work_id = await resolve_smoke_target(share_url, safe_http(handler))

    assert resolved == CANONICAL_URL
    assert work_id == WORK_ID


@pytest.mark.asyncio
async def test_smoke_rejects_homepage_without_work_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(302, headers={"location": "https://www.douyin.com/?recommend=1"})
        raise AssertionError("homepage must be rejected before a request")

    with pytest.raises(AppError) as caught:
        await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"


@pytest.mark.asyncio
async def test_smoke_rejects_external_redirect_before_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(302, headers={"location": "https://attacker.example.com/video/123"})
        raise AssertionError("external redirect must be rejected before a request")

    with pytest.raises(AppError) as caught:
        await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"


@pytest.mark.asyncio
async def test_smoke_revalidates_private_redirect_before_platform_whitelist() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
        raise AssertionError("private redirect must be rejected before a request")

    with pytest.raises(AppError) as caught:
        await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert caught.value.code == "URL_INVALID"


@pytest.mark.asyncio
async def test_smoke_rejects_redirect_loop_at_safe_http_limit() -> None:
    requests = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(302, headers={"location": SHORT_URL})

    with pytest.raises(AppError) as caught:
        await resolve_smoke_target(SHORT_URL, safe_http(handler))

    assert caught.value.code == "UPSTREAM_TIMEOUT"
    assert requests == 3


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://v.douyin.com/opaque-token?signature=never-log", "https://v.douyin.com/<short-link>"),
        (f"{CANONICAL_URL}?signature=never-log", CANONICAL_URL),
    ],
)
def test_redirect_log_sanitiser_excludes_queries_and_opaque_short_tokens(url: str, expected: str) -> None:
    logged = sanitise_redirect_hop(url)
    assert logged == expected
    assert "signature" not in logged
    assert "never-log" not in logged


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
