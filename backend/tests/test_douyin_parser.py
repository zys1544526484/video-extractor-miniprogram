from __future__ import annotations

import asyncio

import httpx
import pytest

from app.errors import AppError
from app.parsers.base import ParseContext
from app.parsers.douyin import DouyinParser
from app.parsers.platforms import KuaishouParser, YtDlpPlatformParser
from app.parsers.registry import ParserRegistry
from app.schemas import ParserResultModel
from app.services.safe_http import SafeHttpClient

WORK_ID = "7123456789012345678"
CANONICAL_URL = f"https://www.douyin.com/video/{WORK_ID}"


def public_document(*, media_url: str = "https://cdn.example.com/public.mp4", private: bool = False) -> str:
    restriction = "该作品为私密内容" if private else ""
    return f'''<!doctype html><html><head><meta property="og:title" content="公开作品标题"></head>
    <body>{restriction}<script>window.__DATA__ = {{"aweme_id":"{WORK_ID}","desc":"公开作品标题",
    "video":{{"play_addr":{{"url_list":["{media_url}"]}}}},
    "cover":{{"url_list":["https://cdn.example.com/cover.jpg"]}}}};</script></body></html>'''


async def public_resolver(host: str) -> list[str]:
    if host in {"v.douyin.com", "www.douyin.com", "cdn.example.com"}:
        return ["93.184.216.34"]
    return ["127.0.0.1"]


def safe_http(handler) -> SafeHttpClient:
    return SafeHttpClient(
        timeout_seconds=2,
        max_redirects=5,
        max_video_bytes=180 * 1024 * 1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )


class Fallback:
    def __init__(self, response: ParserResultModel | AppError | None = None) -> None:
        self.response = response or AppError("DOUYIN_RESOLVE_FAILED", "fallback failed", retryable=True)
        self.calls: list[dict] = []

    async def extract(self, *args, **kwargs) -> ParserResultModel:
        self.calls.append(kwargs)
        if isinstance(self.response, AppError):
            raise self.response
        return self.response


def context(settings, http: SafeHttpClient) -> ParseContext:
    return ParseContext(settings=settings, http=http)


@pytest.mark.asyncio
async def test_short_link_redirects_to_public_work_and_returns_safe_parser_source(settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(302, headers={"location": CANONICAL_URL})
        assert str(request.url).split("?", 1)[0] == CANONICAL_URL
        return httpx.Response(200, headers={"content-type": "text/html"}, text=public_document())

    fallback = Fallback()
    result = await DouyinParser(fallback).parse(
        "https://v.douyin.com/public-short/",
        context(settings, safe_http(handler)),
    )

    assert result.platform == "抖音"
    assert result.canonical_url == CANONICAL_URL
    assert result.title == "公开作品标题"
    assert result.sources[0].upstream_media_url == "https://cdn.example.com/public.mp4"
    assert result.sources[0].upstream_media_url not in result.share_text
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_direct_work_url_uses_public_html_without_yt_dlp(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=public_document())

    fallback = Fallback()
    result = await DouyinParser(fallback).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert result.canonical_url == CANONICAL_URL
    assert result.sources[0].source_id == "source-1"
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_short_link_that_lands_on_homepage_returns_retryable_resolve_failure(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>首页</html>")

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(
            "https://v.douyin.com/lost-work-id/",
            context(settings, safe_http(handler)),
        )

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"
    assert caught.value.message == "抖音短链接未能解析到具体作品，请稍后重试"
    assert caught.value.retryable is True
    assert len(fallback.calls) == 1
    assert 1 <= fallback.calls[0]["timeout_seconds"] <= settings.douyin_yt_dlp_fallback_timeout_seconds


@pytest.mark.asyncio
async def test_explicit_private_work_is_content_restricted_without_fallback(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=public_document(private=True),
        )

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert caught.value.code == "CONTENT_RESTRICTED"
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_redirect_to_private_address_is_rejected_by_safe_http(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    with pytest.raises(AppError) as caught:
        await DouyinParser(Fallback()).parse(
            "https://v.douyin.com/unsafe-redirect/",
            context(settings, safe_http(handler)),
        )

    assert caught.value.code == "URL_INVALID"


@pytest.mark.asyncio
async def test_public_media_url_is_checked_against_ssrf_before_result(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=public_document(media_url="http://127.0.0.1/private.mp4"),
        )

    with pytest.raises(AppError) as caught:
        await DouyinParser(Fallback()).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert caught.value.code == "URL_INVALID"


@pytest.mark.asyncio
async def test_public_html_timeout_is_bounded_and_never_reports_private_content(settings) -> None:
    settings.douyin_metadata_timeout_seconds = 1

    async def slow_handler(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(1.1)
        return httpx.Response(200, headers={"content-type": "text/html"}, text=public_document())

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(CANONICAL_URL, context(settings, safe_http(slow_handler)))

    assert caught.value.code == "PARSE_TIMEOUT"
    assert caught.value.retryable is True
    assert fallback.calls == []


def test_registry_uses_douyin_parser_without_changing_other_platform_types(settings) -> None:
    registry = ParserRegistry(settings)

    assert isinstance(registry.get("douyin"), DouyinParser)
    assert isinstance(registry.get("bilibili"), YtDlpPlatformParser)
    assert isinstance(registry.get("weibo"), YtDlpPlatformParser)
    assert isinstance(registry.get("xiaohongshu"), YtDlpPlatformParser)
    assert isinstance(registry.get("kuaishou"), KuaishouParser)
