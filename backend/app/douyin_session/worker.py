from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlsplit

from ..config import Settings
from ..errors import AppError
from ..services.safe_http import SafeHttpClient
from .bootstrap import _load_async_playwright
from .errors import (
    risk_controlled,
    session_bound_media,
    session_disabled,
    session_expired,
    session_media_not_found,
    session_timeout,
    session_unavailable,
    target_mismatch,
)
from .models import CapturedMedia, SessionWorkerResult, target_id_from_url, validate_storage_state_path

logger = logging.getLogger(__name__)

RISK_URL_MARKERS = ("/captcha", "/verify", "/security", "/risk")
RISK_COMPONENT_SELECTOR = (
    '[data-e2e*="captcha"], [data-e2e*="verify"], [data-e2e*="risk"], '
    'iframe[src*="captcha"], iframe[src*="verify"], [role="dialog"][data-captcha]'
)
PRIMARY_VIDEO_READY_SCRIPT = """
() => Array.from(document.querySelectorAll('video')).some((video) => {
  const rect = video.getBoundingClientRect();
  const hidden = getComputedStyle(video).visibility === 'hidden'
    || getComputedStyle(video).display === 'none';
  const ad = video.closest('[data-e2e*="ad"], [class*="advert"], [class*="ad-"]');
  return !hidden && !ad && rect.width > 120 && rect.height > 120 && Boolean(video.currentSrc || video.src);
})
"""
PRIMARY_VIDEO_URL_SCRIPT = """
() => Array.from(document.querySelectorAll('video'))
  .filter((video) => {
    const rect = video.getBoundingClientRect();
    const style = getComputedStyle(video);
    const ad = video.closest('[data-e2e*="ad"], [class*="advert"], [class*="ad-"]');
    return !ad && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
  })
  .sort((left, right) => (right.clientWidth * right.clientHeight) - (left.clientWidth * left.clientHeight))
  .map((video) => video.currentSrc || video.src || '')
  .find(Boolean) || ''
"""
PUBLIC_MEDIA_HEADERS = {
    "Origin": "https://www.douyin.com",
    "User-Agent": "VideoExtractor/0.1 (+public-media-parser)",
    "Accept": "video/*,application/octet-stream;q=0.9,*/*;q=0.8",
}


class SessionBrowserAdapter(Protocol):
    async def capture(
        self,
        *,
        target_url: str,
        target_id: str,
        storage_state_path: str,
        timeout_seconds: int,
    ) -> CapturedMedia: ...


def _sanitise_media_origin(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_resource(left: str, right: str) -> bool:
    left_parts = urlsplit(left)
    right_parts = urlsplit(right)
    return (
        left_parts.scheme == right_parts.scheme
        and left_parts.netloc == right_parts.netloc
        and left_parts.path == right_parts.path
    )


class PlaywrightSessionAdapter:
    """Minimal browser adapter; it intentionally contains no stealth behavior."""

    def __init__(self, playwright_factory: Callable[[], Any] | None = None) -> None:
        self.playwright_factory = playwright_factory

    @staticmethod
    async def _has_visible_risk_component(page: Any) -> bool:
        if any(marker in page.url.lower() for marker in RISK_URL_MARKERS):
            return True
        try:
            return await page.locator(RISK_COMPONENT_SELECTOR).first.is_visible(timeout=250)
        except Exception:
            return False

    @staticmethod
    async def _wait_for_primary_video_url(page: Any, timeout_seconds: int) -> str | None:
        try:
            await page.wait_for_function(PRIMARY_VIDEO_READY_SCRIPT, timeout=timeout_seconds * 1000)
            candidate = await page.evaluate(PRIMARY_VIDEO_URL_SCRIPT)
        except Exception as error:
            if error.__class__.__name__ == "TimeoutError":
                return None
            raise
        if isinstance(candidate, str) and candidate.startswith(("https://", "http://")):
            return candidate
        return None

    async def capture(
        self,
        *,
        target_url: str,
        target_id: str,
        storage_state_path: str,
        timeout_seconds: int,
    ) -> CapturedMedia:
        # The lazy loader returns Playwright's async_playwright factory, not
        # the async context manager itself.
        context_manager_factory = self.playwright_factory or _load_async_playwright()
        try:
            async with context_manager_factory() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(storage_state=storage_state_path)
                    try:
                        page = await context.new_page()
                        network_media_urls: list[str] = []

                        def observe_response(response: Any) -> None:
                            request = response.request
                            content_type = response.headers.get("content-type", "").lower()
                            # Network responses are only candidates. They must later match
                            # the active main player or structured media for this exact page.
                            if (
                                request.resource_type == "media"
                                and content_type.startswith("video/")
                                and response.url not in network_media_urls
                            ):
                                network_media_urls.append(response.url)

                        page.on("response", observe_response)
                        await page.goto(
                            target_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_seconds * 1000,
                        )
                        if await self._has_visible_risk_component(page):
                            return CapturedMedia(target_id=None, media_url=None, state="risk")
                        if "/login" in page.url.lower():
                            return CapturedMedia(target_id=None, media_url=None, state="expired")
                        if target_id_from_url(page.url) != target_id:
                            return CapturedMedia(target_id=None, media_url=None, state="mismatch")
                        primary_media_url = await self._wait_for_primary_video_url(page, timeout_seconds)
                        # The final route is exact; only then can public structured
                        # metadata from this page be associated with the target work.
                        from ..parsers.douyin import DouyinParser

                        document = await page.content()
                        _title, media_urls, _covers = DouyinParser._structured_metadata(document)
                        media_url = primary_media_url or (media_urls[0] if media_urls else None)
                        if media_url is not None and not any(
                            _same_resource(media_url, candidate) for candidate in network_media_urls
                        ):
                            # Direct player/structured address is still allowed; network
                            # entries never replace it merely because they are video MIME.
                            network_media_urls.clear()
                        return CapturedMedia(target_id=target_id, media_url=media_url)
                    finally:
                        await context.close()
                finally:
                    await browser.close()
        except AppError:
            raise
        except Exception as error:
            raise session_unavailable() from error


class DouyinSessionWorker:
    """Explicit opt-in PoC for operator session inspection, not an API parser."""

    def __init__(
        self,
        *,
        settings: Settings,
        http: SafeHttpClient,
        browser: SessionBrowserAdapter | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.browser = browser or PlaywrightSessionAdapter()
        self._semaphore = asyncio.Semaphore(settings.douyin_session_max_concurrency)

    async def inspect(self, target_url: str) -> SessionWorkerResult:
        if not self.settings.douyin_session_enabled:
            raise session_disabled()
        target_id = target_id_from_url(target_url)
        if target_id is None:
            raise AppError("URL_INVALID", "抖音专用会话只接受已确认的作品链接")
        state_path = validate_storage_state_path(
            self.settings.douyin_storage_state_path,
            require_exists=True,
        )
        started = time.monotonic()
        async with self._semaphore:
            try:
                async with asyncio.timeout(self.settings.douyin_session_timeout_seconds):
                    capture = await self.browser.capture(
                        target_url=target_url,
                        target_id=target_id,
                        storage_state_path=str(state_path),
                        timeout_seconds=self.settings.douyin_session_timeout_seconds,
                    )
            except TimeoutError as error:
                raise session_timeout() from error
            if capture.state == "expired":
                raise session_expired()
            if capture.state == "risk":
                raise risk_controlled()
            if capture.state != "ok" or capture.target_id != target_id:
                raise target_mismatch()
            if not capture.media_url:
                raise session_media_not_found()
            try:
                # No session headers are supplied: a candidate must be independently
                # public before it can be used by the existing media pipeline.
                public_headers = {**PUBLIC_MEDIA_HEADERS, "Referer": target_url}
                probe = await self.http.probe_media(capture.media_url, headers=public_headers)
                stream = await self.http.open_stream(
                    capture.media_url,
                    headers=public_headers,
                    range_header="bytes=0-1023",
                    media_kind="video",
                )
                try:
                    bytes_read = 0
                    async for chunk in stream.response.aiter_bytes():
                        bytes_read += len(chunk)
                        if bytes_read >= 1024:
                            break
                finally:
                    await stream.close()
            except AppError as error:
                if error.code == "CONTENT_NOT_PUBLIC":
                    raise session_bound_media() from error
                raise
            if bytes_read < 1024:
                raise AppError("DOWNLOAD_FAILED", "公开媒体无法读取足够的视频数据", retryable=True)
            result = SessionWorkerResult(
                target_id=target_id,
                media_origin=_sanitise_media_origin(capture.media_url),
                size_bytes=probe.get("size"),
                bytes_read=bytes_read,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
            logger.info(
                "douyin_session_worker outcome=success target_id=%s media_origin=%s elapsed_ms=%d",
                result.target_id,
                result.media_origin,
                result.elapsed_ms,
            )
            return result
