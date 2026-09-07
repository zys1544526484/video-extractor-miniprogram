from __future__ import annotations

import asyncio
import html
import json
import re
import time
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from ..errors import AppError
from ..schemas import ParserResultModel, ParserSourceModel
from .base import BaseParser, ParseContext
from .yt_dlp_adapter import YtDlpAdapter

if TYPE_CHECKING:
    from collections.abc import Iterable


DOUYIN_WORK_ID_PATTERN = re.compile(r"/(?:video|note)/(\d{8,})(?:[/?#]|$)", re.IGNORECASE)
DOUYIN_EMBEDDED_ID_PATTERN = re.compile(
    r'["\'](?:aweme_id|awemeId|item_id|itemId)["\']\s*[:=]\s*["\']?(\d{8,})',
    re.IGNORECASE,
)
JSON_STRING_PATTERN = r'(?P<value>(?:\\.|[^"\\])*)'
TITLE_PATTERNS = (
    re.compile(rf'["\']desc["\']\s*:\s*["\']{JSON_STRING_PATTERN}["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](?P<value>[^"\']+)', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\'](?P<value>[^"\']+)["\'][^>]+property=["\']og:title', re.IGNORECASE),
)
PUBLIC_MEDIA_KEYS = ("play_addr", "playaddr", "play_url", "playurl", "download_addr", "downloadaddr")
PUBLIC_COVER_KEYS = ("origin_cover", "dynamic_cover", "static_cover", "cover", "poster")
PUBLIC_RESTRICTION_MARKERS = (
    "仅好友可见",
    "私密作品",
    "该作品为私密",
    "需要登录后查看",
    "登录后查看",
    "friends only",
    "this video is private",
    "login required",
)
URL_PATTERN = re.compile(r"https?:(?:\\/|\\u002[fF]|/)[^\"'\\<>\s]+", re.IGNORECASE)


def _decode_json_string(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return html.unescape(value).replace("\\/", "/").replace("\\u002F", "/")


def _normalise_public_url(value: str) -> str:
    return html.unescape(value).replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")


class DouyinParser(BaseParser):
    """Small, Cookie-free parser for publicly embedded Douyin work metadata.

    This intentionally does not use any undocumented signed endpoint.  It can
    only consume redirects and HTML already served to an anonymous visitor.
    """

    platform = "douyin"

    def __init__(self, fallback: YtDlpAdapter) -> None:
        self.fallback = fallback

    def can_handle(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return host == "douyin.com" or host.endswith(".douyin.com")

    @staticmethod
    def _work_id_from_url(url: str) -> str | None:
        match = DOUYIN_WORK_ID_PATTERN.search(url)
        return match.group(1) if match else None

    @staticmethod
    def _work_id_from_html(document: str) -> str | None:
        match = DOUYIN_EMBEDDED_ID_PATTERN.search(document)
        return match.group(1) if match else None

    @staticmethod
    def _has_explicit_public_restriction(document: str) -> bool:
        lowered = document.lower()
        return any(marker in lowered for marker in PUBLIC_RESTRICTION_MARKERS)

    @staticmethod
    def _first_title(document: str) -> str:
        for pattern in TITLE_PATTERNS:
            match = pattern.search(document)
            if match:
                value = _decode_json_string(match.group("value")).strip()
                if value:
                    return value[:200]
        return "抖音公开视频"

    @staticmethod
    def _public_urls(document: str, keys: Iterable[str]) -> list[str]:
        matches: list[str] = []
        lowered = document.lower()
        for found in URL_PATTERN.finditer(document):
            # Only use an address occurring in a clearly labelled public media
            # field.  Do not treat arbitrary tracking/image/script URLs as a
            # downloadable asset.
            window = lowered[max(0, found.start() - 320):found.end() + 96]
            if not any(key in window for key in keys):
                continue
            candidate = _normalise_public_url(found.group(0)).rstrip("\\,;)")
            if candidate not in matches:
                matches.append(candidate)
        return matches

    def _result_from_document(
        self,
        *,
        document: str,
        work_id: str,
        context: ParseContext,
    ) -> ParserResultModel:
        if self._has_explicit_public_restriction(document):
            raise AppError("CONTENT_RESTRICTED", "该内容不可公开访问")

        media_urls = self._public_urls(document, PUBLIC_MEDIA_KEYS)
        if not media_urls:
            raise self._resolve_failed()
        media_url = media_urls[0]
        # Validate parser-produced addresses now, before ParseService starts a
        # media probe or session.  This keeps a malicious public page from
        # smuggling a private target through the parser.
        # The call is awaited by parse() because SafeHttpClient is async.
        title = self._first_title(document)
        cover_urls = self._public_urls(document, PUBLIC_COVER_KEYS)
        canonical_url = f"https://www.douyin.com/video/{work_id}"
        source = ParserSourceModel(
            source_id="source-1",
            quality_label="公开原始资源",
            upstream_media_url=media_url,
            mime_type="video/mp4",
        )
        return ParserResultModel(
            platform="抖音",
            canonical_url=canonical_url,
            title=title,
            cover_url=cover_urls[0] if cover_urls else "",
            mime_type="video/mp4",
            watermark_status="unknown",
            notices=["仅处理无需登录即可公开访问的媒体", "不保证移除作者画面内标识"],
            sources=[source],
            share_text=f"{title}\n{canonical_url}",
        )

    @staticmethod
    def _resolve_failed() -> AppError:
        return AppError(
            "DOUYIN_RESOLVE_FAILED",
            "抖音短链接未能解析到具体作品，请稍后重试",
            retryable=True,
        )

    async def _parse_public_document(self, url: str, context: ParseContext) -> ParserResultModel:
        final_url, document, _headers = await context.http.get_text(url)
        work_id = self._work_id_from_url(final_url) or self._work_id_from_html(document)
        if not work_id:
            raise self._resolve_failed()
        canonical_url = f"https://www.douyin.com/video/{work_id}"
        if self._work_id_from_url(final_url) != work_id:
            _canonical_final, document, _headers = await context.http.get_text(canonical_url)
        result = self._result_from_document(document=document, work_id=work_id, context=context)
        for source in result.sources:
            if source.upstream_media_url:
                await context.http.validate_url(source.upstream_media_url)
        if result.cover_url:
            await context.http.validate_url(result.cover_url)
        return result

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        await context.http.validate_url(url)
        started = time.monotonic()
        total_budget = min(
            context.settings.parse_timeout_seconds,
            context.settings.douyin_metadata_timeout_seconds,
        )
        try:
            async with asyncio.timeout(total_budget):
                return await self._parse_public_document(url, context)
        except TimeoutError as error:
            raise AppError("PARSE_TIMEOUT", "抖音公开页面解析超时，请稍后重试", retryable=True) from error
        except AppError as error:
            if error.code in {"CONTENT_RESTRICTED", "URL_INVALID"}:
                raise
            public_error = error

        elapsed = time.monotonic() - started
        remaining = total_budget - elapsed
        fallback_timeout = min(
            context.settings.douyin_yt_dlp_fallback_timeout_seconds,
            max(0, int(remaining)),
        )
        if fallback_timeout < 1:
            if public_error.code == "UPSTREAM_TIMEOUT":
                raise AppError("PARSE_TIMEOUT", "抖音公开页面解析超时，请稍后重试", retryable=True)
            raise self._resolve_failed() from public_error
        try:
            return await self.fallback.extract(
                url,
                "douyin",
                requested_quality=context.requested_quality,
                timeout_seconds=fallback_timeout,
            )
        except AppError as fallback_error:
            if fallback_error.code == "CONTENT_RESTRICTED":
                raise
            if fallback_error.code == "PARSE_TIMEOUT":
                raise AppError(
                    "PARSE_TIMEOUT",
                    "抖音公开页面解析超时，请稍后重试",
                    retryable=True,
                ) from fallback_error
            raise self._resolve_failed() from fallback_error
