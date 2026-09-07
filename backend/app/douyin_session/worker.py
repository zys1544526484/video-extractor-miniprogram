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
    session_unavailable,
    target_mismatch,
)
from .models import CapturedMedia, SessionWorkerResult, target_id_from_url, validate_storage_state_path

logger = logging.getLogger(__name__)

RISK_MARKERS = ("验证码", "滑块", "安全验证", "风险控制", "captcha")


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
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


class PlaywrightSessionAdapter:
    """Minimal browser adapter; it intentionally contains no stealth behavior."""

    def __init__(self, playwright_factory: Callable[[], Any] | None = None) -> None:
        self.playwright_factory = playwright_factory

    async def capture(
        self,
        *,
        target_url: str,
        target_id: str,
        storage_state_path: str,
        timeout_seconds: int,
    ) -> CapturedMedia:
        factory = self.playwright_factory or _load_async_playwright
        try:
            async with factory() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(storage_state=storage_state_path)
                    try:
                        page = await context.new_page()
                        network_media_url: str | None = None

                        def observe_response(response: Any) -> None:
                            nonlocal network_media_url
                            request = response.request
                            # A network media URL is trusted only after the page itself
                            # is confirmed as the requested work and its URL carries that ID.
                            if (
                                request.resource_type == "media"
                                and target_id in response.url
                                and network_media_url is None
                            ):
                                network_media_url = response.url

                        page.on("response", observe_response)
                        await page.goto(
                            target_url,
                            wait_until="domcontentloaded",
                            timeout=timeout_seconds * 1000,
                        )
                        document = await page.content()
                        lower_document = document.lower()
                        if any(marker in lower_document for marker in RISK_MARKERS):
                            return CapturedMedia(target_id=None, media_url=None, state="risk")
                        if "/login" in page.url.lower():
                            return CapturedMedia(target_id=None, media_url=None, state="expired")
                        if target_id_from_url(page.url) != target_id:
                            return CapturedMedia(target_id=None, media_url=None, state="mismatch")
                        # The final route is exact; only then can public structured
                        # metadata from this page be associated with the target work.
                        from ..parsers.douyin import DouyinParser

                        _title, media_urls, _covers = DouyinParser._structured_metadata(document)
                        media_url = media_urls[0] if media_urls else network_media_url
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
            capture = await self.browser.capture(
                target_url=target_url,
                target_id=target_id,
                storage_state_path=str(state_path),
                timeout_seconds=self.settings.douyin_session_timeout_seconds,
            )
            if capture.state == "expired":
                raise session_expired()
            if capture.state == "risk":
                raise risk_controlled()
            if capture.state != "ok" or capture.target_id != target_id or not capture.media_url:
                raise target_mismatch()
            try:
                # No session headers are supplied: a candidate must be independently
                # public before it can be used by the existing media pipeline.
                probe = await self.http.probe_media(capture.media_url)
                stream = await self.http.open_stream(
                    capture.media_url,
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
