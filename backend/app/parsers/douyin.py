from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from ..errors import AppError
from ..schemas import ParserResultModel, ParserSourceModel
from .base import BaseParser, ParseContext
from .yt_dlp_adapter import YtDlpAdapter

DOUYIN_WORK_PATH_PATTERN = re.compile(
    r"/(?P<kind>video|note)/(?P<work_id>\d{8,})(?:[/?#]|$)",
    re.IGNORECASE,
)
DOUYIN_EMBEDDED_ID_PATTERN = re.compile(
    r'["\'](?:aweme_id|awemeId|item_id|itemId)["\']\s*[:=]\s*["\']?(\d{8,})',
    re.IGNORECASE,
)
TITLE_PATTERNS = (
    re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](?P<value>[^"\']+)', re.IGNORECASE),
    re.compile(r'<meta[^>]+content=["\'](?P<value>[^"\']+)["\'][^>]+property=["\']og:title', re.IGNORECASE),
)
VIDEO_MEDIA_FIELDS = ("play_addr", "play_addr_h264", "download_addr")
COVER_FIELDS = ("origin_cover", "dynamic_cover", "static_cover", "cover", "poster")
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
HYDRATION_JSON_START_PATTERN = re.compile(r"(?:^|[=(:,;])\s*(?P<json>[{\[])")
JSON_PARSE_PATTERN = re.compile(r"JSON\.parse\(\s*(?P<json>\"(?:\\.|[^\"\\])*\")\s*\)")
logger = logging.getLogger(__name__)


def _normalise_public_url(value: str) -> str:
    """Decode representations that are valid inside public JSON or HTML."""
    decoded = html.unescape(value)
    try:
        # JSON decoding handles both escaped slashes and unicode slash escapes.
        decoded = json.loads(json.dumps(decoded))
    except (TypeError, ValueError):
        pass
    return decoded.replace("\\/", "/").replace("\\u002F", "/").replace("\\u002f", "/")


class _ScriptCollector(HTMLParser):
    """Collect script bodies without treating arbitrary page text as JSON."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.scripts: list[tuple[dict[str, str], list[str]]] = []
        self._current: tuple[dict[str, str], list[str]] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self._current = ({key.lower(): value or "" for key, value in attrs}, [])

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current[1].append(data)

    def handle_entityref(self, name: str) -> None:
        if self._current is not None:
            self._current[1].append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._current is not None:
            self._current[1].append(f"&#{name};")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._current is not None:
            self.scripts.append(self._current)
            self._current = None


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
    def _work_reference_from_url(url: str) -> tuple[str, str] | None:
        match = DOUYIN_WORK_PATH_PATTERN.search(url)
        if match is None:
            return None
        return match.group("kind").lower(), match.group("work_id")

    @staticmethod
    def _work_id_from_html(document: str) -> str | None:
        match = DOUYIN_EMBEDDED_ID_PATTERN.search(document)
        return match.group(1) if match else None

    @staticmethod
    def _unsupported_note() -> AppError:
        return AppError("PLATFORM_UNSUPPORTED", "抖音图文作品暂不支持视频提取")

    @staticmethod
    def _has_explicit_public_restriction(document: str) -> bool:
        lowered = document.lower()
        return any(marker in lowered for marker in PUBLIC_RESTRICTION_MARKERS)

    @staticmethod
    def _first_meta_title(document: str) -> str:
        for pattern in TITLE_PATTERNS:
            match = pattern.search(document)
            if match:
                value = html.unescape(match.group("value")).strip()
                if value:
                    return value[:200]
        return "抖音公开视频"

    @staticmethod
    def _script_json_values(document: str) -> list[dict[str, Any] | list[Any]]:
        collector = _ScriptCollector()
        collector.feed(document)
        collector.close()
        decoder = json.JSONDecoder()
        values: list[dict[str, Any] | list[Any]] = []
        for attributes, parts in collector.scripts:
            script = html.unescape("".join(parts)).strip()
            if not script:
                continue
            candidates: list[str] = [script]
            if attributes.get("type", "").lower() in {"application/json", "application/ld+json"}:
                candidates.append(script)
            for match in JSON_PARSE_PATTERN.finditer(script):
                try:
                    embedded = json.loads(match.group("json"))
                except json.JSONDecodeError:
                    continue
                if isinstance(embedded, str):
                    candidates.append(embedded)
            for match in HYDRATION_JSON_START_PATTERN.finditer(script):
                candidates.append(script[match.start("json"):])
            seen: set[str] = set()
            for candidate in candidates[:65]:
                if candidate in seen:
                    continue
                seen.add(candidate)
                try:
                    value, _ = decoder.raw_decode(candidate.lstrip())
                except json.JSONDecodeError:
                    continue
                if isinstance(value, (dict, list)):
                    values.append(value)
        return values

    @staticmethod
    def _walk_dicts(value: object) -> list[dict[str, Any]]:
        stack = [value]
        found: list[dict[str, Any]] = []
        while stack and len(found) < 10_000:
            current = stack.pop()
            if isinstance(current, dict):
                found.append(current)
                stack.extend(current.values())
            elif isinstance(current, list):
                stack.extend(current)
        return found

    @staticmethod
    def _urls_in_address(value: object) -> list[str]:
        if not isinstance(value, dict):
            return []
        candidates = value.get("url_list") or value.get("urlList") or value.get("url")
        values = candidates if isinstance(candidates, list) else [candidates]
        urls: list[str] = []
        for candidate in values:
            if not isinstance(candidate, str):
                continue
            decoded = _normalise_public_url(candidate).strip()
            if decoded.startswith(("http://", "https://")) and decoded not in urls:
                urls.append(decoded)
        return urls

    @classmethod
    def _structured_metadata(cls, document: str) -> tuple[str, list[str], list[str]]:
        """Read only explicit public media paths from parsed JSON values."""
        title = ""
        media_urls: list[str] = []
        cover_urls: list[str] = []
        for payload in cls._script_json_values(document):
            for node in cls._walk_dicts(payload):
                if not title and isinstance(node.get("desc"), str):
                    title = str(node["desc"]).strip()[:200]
                video = node.get("video")
                if not isinstance(video, dict):
                    continue
                for field in VIDEO_MEDIA_FIELDS:
                    for url in cls._urls_in_address(video.get(field)):
                        if url not in media_urls:
                            media_urls.append(url)
                bit_rates = video.get("bit_rate") or video.get("bitRate")
                if isinstance(bit_rates, list):
                    for bit_rate in bit_rates:
                        if not isinstance(bit_rate, dict):
                            continue
                        for url in cls._urls_in_address(bit_rate.get("play_addr")):
                            if url not in media_urls:
                                media_urls.append(url)
                for field in COVER_FIELDS:
                    for url in cls._urls_in_address(video.get(field)):
                        if url not in cover_urls:
                            cover_urls.append(url)
                for field in COVER_FIELDS:
                    for url in cls._urls_in_address(node.get(field)):
                        if url not in cover_urls:
                            cover_urls.append(url)
        return title, media_urls, cover_urls

    def _result_from_document(
        self,
        *,
        document: str,
        work_id: str,
    ) -> ParserResultModel:
        if self._has_explicit_public_restriction(document):
            raise AppError("CONTENT_RESTRICTED", "该内容不可公开访问")

        structured_title, media_urls, cover_urls = self._structured_metadata(document)
        if not media_urls:
            raise self._resolve_failed()
        media_url = media_urls[0]
        title = structured_title or self._first_meta_title(document)
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

    @staticmethod
    def _safe_log_url(url: str) -> str:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

    @staticmethod
    def _log_outcome(*, outcome: str, started: float, final_url: str, error_code: str = "") -> None:
        logger.info(
            "douyin_public_parse outcome=%s error_code=%s elapsed_ms=%d final_url=%s",
            outcome,
            error_code or "NONE",
            int((time.monotonic() - started) * 1000),
            DouyinParser._safe_log_url(final_url),
        )

    async def _parse_public_document(
        self,
        url: str,
        context: ParseContext,
        resolved: dict[str, str],
    ) -> ParserResultModel:
        final_url, document, _headers = await context.http.get_text(url)
        resolved["url"] = final_url
        reference = self._work_reference_from_url(final_url)
        if reference and reference[0] == "note":
            raise self._unsupported_note()
        work_id = (reference[1] if reference else None) or self._work_id_from_html(document)
        if not work_id:
            raise self._resolve_failed()
        canonical_url = f"https://www.douyin.com/video/{work_id}"
        if not reference or reference[1] != work_id:
            _canonical_final, document, _headers = await context.http.get_text(canonical_url)
        result = self._result_from_document(document=document, work_id=work_id)
        for source in result.sources:
            if source.upstream_media_url:
                await context.http.validate_url(source.upstream_media_url)
        if result.cover_url:
            await context.http.validate_url(result.cover_url)
        return result

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        await context.http.validate_url(url)
        input_reference = self._work_reference_from_url(url)
        if input_reference and input_reference[0] == "note":
            raise self._unsupported_note()
        started = time.monotonic()
        total_budget = min(
            context.settings.parse_timeout_seconds,
            context.settings.douyin_metadata_timeout_seconds,
        )
        resolved = {"url": url}
        try:
            async with asyncio.timeout(total_budget):
                result = await self._parse_public_document(url, context, resolved)
                self._log_outcome(outcome="success", started=started, final_url=resolved["url"])
                return result
        except TimeoutError as error:
            self._log_outcome(
                outcome="failed",
                started=started,
                final_url=resolved["url"],
                error_code="PARSE_TIMEOUT",
            )
            raise AppError("PARSE_TIMEOUT", "抖音公开页面解析超时，请稍后重试", retryable=True) from error
        except AppError as error:
            if error.code in {"CONTENT_RESTRICTED", "PLATFORM_UNSUPPORTED", "URL_INVALID"}:
                self._log_outcome(
                    outcome="failed",
                    started=started,
                    final_url=resolved["url"],
                    error_code=error.code,
                )
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
                self._log_outcome(
                    outcome="failed",
                    started=started,
                    final_url=resolved["url"],
                    error_code="PARSE_TIMEOUT",
                )
                raise AppError("PARSE_TIMEOUT", "抖音公开页面解析超时，请稍后重试", retryable=True)
            self._log_outcome(
                outcome="failed",
                started=started,
                final_url=resolved["url"],
                error_code="DOUYIN_RESOLVE_FAILED",
            )
            raise self._resolve_failed() from public_error
        try:
            result = await self.fallback.extract(
                url,
                "douyin",
                requested_quality=context.requested_quality,
                timeout_seconds=fallback_timeout,
            )
            self._log_outcome(outcome="fallback_success", started=started, final_url=resolved["url"])
            return result
        except AppError as fallback_error:
            if fallback_error.code == "CONTENT_RESTRICTED":
                self._log_outcome(
                    outcome="failed",
                    started=started,
                    final_url=resolved["url"],
                    error_code=fallback_error.code,
                )
                raise
            if fallback_error.code == "PARSE_TIMEOUT":
                self._log_outcome(
                    outcome="failed",
                    started=started,
                    final_url=resolved["url"],
                    error_code="PARSE_TIMEOUT",
                )
                raise AppError(
                    "PARSE_TIMEOUT",
                    "抖音公开页面解析超时，请稍后重试",
                    retryable=True,
                ) from fallback_error
            self._log_outcome(
                outcome="failed",
                started=started,
                final_url=resolved["url"],
                error_code="DOUYIN_RESOLVE_FAILED",
            )
            raise self._resolve_failed() from fallback_error
