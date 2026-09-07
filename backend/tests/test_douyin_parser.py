from __future__ import annotations

import asyncio
import json
import logging

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


def structured_document(media_field: str, *, description: str = "公开作品标题") -> str:
    """Build a public hydration script; media_field is intentionally raw JSON."""
    return f'''<!doctype html><html><head><meta property="og:title" content="公开作品标题"></head>
    <body><script id="RENDER_DATA" type="application/json">{{"aweme_id":"{WORK_ID}",
    "desc":{json.dumps(description, ensure_ascii=False)},"video":{{{media_field}}}}}</script></body></html>'''


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
@pytest.mark.parametrize(
    ("media_field", "expected_url"),
    [
        (
            r'"play_addr":{"url_list":["https:\/\/cdn.example.com\/escaped.mp4"]}',
            "https://cdn.example.com/escaped.mp4",
        ),
        (
            r'"play_addr_h264":{"url_list":["https:\u002F\u002Fcdn.example.com\u002Funicode.mp4"]}',
            "https://cdn.example.com/unicode.mp4",
        ),
        (
            '"download_addr":{"url_list":["https://cdn.example.com/entity.mp4?x=1&amp;y=2"]}',
            "https://cdn.example.com/entity.mp4?x=1&y=2",
        ),
        (
            '"bit_rate":[{"play_addr":{"url_list":["https://cdn.example.com/bit-rate.mp4"]}}]',
            "https://cdn.example.com/bit-rate.mp4",
        ),
    ],
)
async def test_structured_public_media_fields_decode_real_url_encodings(
    settings,
    media_field: str,
    expected_url: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=structured_document(media_field),
        )

    result = await DouyinParser(Fallback()).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert result.sources[0].upstream_media_url == expected_url


@pytest.mark.asyncio
async def test_description_text_cannot_smuggle_a_media_url(settings) -> None:
    forged = structured_document(
        '"cover":{"url_list":["https://cdn.example.com/cover.jpg"]}',
        description="play_addr https://attacker.example.com/not-media.mp4",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=forged)

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_note_url_is_not_rewritten_to_video_or_parsed_as_video(settings) -> None:
    note_url = f"https://www.douyin.com/note/{WORK_ID}"

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("a direct /note/ URL must not fetch video metadata")

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(note_url, context(settings, safe_http(handler)))

    assert caught.value.code == "PLATFORM_UNSUPPORTED"
    assert caught.value.message == "抖音图文作品暂不支持视频提取"
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_parse_log_records_sanitised_final_url_and_elapsed_time(settings, caplog) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=public_document())

    caplog.set_level(logging.INFO, logger="app.parsers.douyin")
    await DouyinParser(Fallback()).parse(
        f"{CANONICAL_URL}?sensitive_query=never-log-this",
        context(settings, safe_http(handler)),
    )

    message = next(
        record.getMessage()
        for record in caplog.records
        if "douyin_public_parse" in record.getMessage()
    )
    assert "outcome=success" in message
    assert "elapsed_ms=" in message
    assert CANONICAL_URL in message
    assert "sensitive_query" not in message


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
async def test_description_login_words_do_not_mark_valid_public_media_private(settings) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text=public_document(private=True).replace("该作品为私密内容", "登录后查看：作品描述"),
        )

    fallback = Fallback()
    result = await DouyinParser(fallback).parse(CANONICAL_URL, context(settings, safe_http(handler)))

    assert result.sources[0].upstream_media_url == "https://cdn.example.com/public.mp4"
    assert fallback.calls == []


@pytest.mark.asyncio
async def test_homepage_recommendation_aweme_id_is_not_the_requested_work(settings) -> None:
    homepage = f'''<html><head><title>首页</title></head><body>
    <script type="application/json">{{"aweme_id":"{WORK_ID}","video":{{"play_addr":{{"url_list":["https://cdn.example.com/recommended.mp4"]}}}}}}</script>
    </body></html>'''

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=homepage)

    fallback = Fallback()
    with pytest.raises(AppError) as caught:
        await DouyinParser(fallback).parse(
            "https://v.douyin.com/redirected-home/",
            context(settings, safe_http(handler)),
        )

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_strict_canonical_og_url_can_identify_the_target_video(settings) -> None:
    homepage = f'''<html><head><meta property="og:url" content="{CANONICAL_URL}?share=1"></head>
    <body><script type="application/json">{{"video":{{"play_addr":{{"url_list":["https://cdn.example.com/canonical.mp4"]}}}}}}</script></body></html>'''

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "v.douyin.com":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=homepage)
        assert str(request.url).split("?", 1)[0] == CANONICAL_URL
        return httpx.Response(200, headers={"content-type": "text/html"}, text=public_document())

    result = await DouyinParser(Fallback()).parse(
        "https://v.douyin.com/canonical-target/",
        context(settings, safe_http(handler)),
    )

    assert result.canonical_url == CANONICAL_URL
    assert result.sources[0].upstream_media_url == "https://cdn.example.com/public.mp4"


@pytest.mark.asyncio
async def test_non_douyin_or_non_video_canonical_url_is_not_trusted(settings) -> None:
    document = '''<html><head>
    <link rel="canonical" href="https://attacker.example.com/video/7123456789012345678">
    </head><body><script type="application/json">{"video":{"play_addr":{"url_list":["https://cdn.example.com/not-target.mp4"]}}}</script></body></html>'''

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=document)

    with pytest.raises(AppError) as caught:
        await DouyinParser(Fallback()).parse(
            "https://v.douyin.com/bad-canonical/",
            context(settings, safe_http(handler)),
        )

    assert caught.value.code == "DOUYIN_RESOLVE_FAILED"


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
