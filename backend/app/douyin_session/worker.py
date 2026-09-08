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
    session_config_invalid,
    session_disabled,
    session_expired,
    session_media_not_found,
    session_player_not_found,
    session_timeout,
    session_unavailable,
    target_mismatch,
)
from .models import (
    CapturedMedia,
    PlayerDiagnostics,
    SessionWorkerResult,
    target_id_from_url,
    validate_storage_state_path,
)

logger = logging.getLogger(__name__)

RISK_URL_MARKERS = ("/captcha", "/verify", "/security", "/risk")
RISK_COMPONENT_SELECTOR = (
    '[data-e2e*="captcha"], [data-e2e*="verify"], [data-e2e*="risk"], '
    'iframe[src*="captcha"], iframe[src*="verify"], [role="dialog"][data-captcha]'
)
HLS_CONTENT_TYPES = {"application/vnd.apple.mpegurl", "application/x-mpegurl"}
PRIMARY_VIDEO_MOUNTED_SCRIPT = """
() => Array.from(document.querySelectorAll('video')).some((video) => {
  const rect = video.getBoundingClientRect();
  const hidden = getComputedStyle(video).visibility === 'hidden'
    || getComputedStyle(video).display === 'none';
  const excluded = video.closest(
    '[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
    + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]'
  );
  return !hidden && !excluded && rect.width > 120 && rect.height > 120;
})
"""
PRIMARY_VIDEO_SNAPSHOT_SCRIPT = """
() => Array.from(document.querySelectorAll('video'))
  .map((video) => {
    const rect = video.getBoundingClientRect();
    const style = getComputedStyle(video);
    const excluded = video.closest(
      '[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
      + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]'
    );
    const visible = !excluded && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
    const sources = Array.from(video.querySelectorAll('source[src]')).map((source) => source.src || '');
    return {
      visible,
      current_src: video.currentSrc || '',
      src: video.src || '',
      source_urls: sources,
    };
  })
  .reduce((result, video) => {
    result.video_count += 1;
    if (video.visible) result.visible_video_count += 1;
    if (video.visible && result.primary === null) result.primary = video;
    return result;
  }, { video_count: 0, visible_video_count: 0, primary: null })
"""
PRIMARY_VIDEO_START_SCRIPT = """
() => {
  const video = Array.from(document.querySelectorAll('video')).find((candidate) => {
    const rect = candidate.getBoundingClientRect();
    const style = getComputedStyle(candidate);
    const excluded = candidate.closest(
      '[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
      + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]'
    );
    return !excluded && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
  });
  if (!video) return false;
  video.scrollIntoView({ block: 'center', inline: 'nearest' });
  video.muted = true;
  const result = video.play();
  if (result && typeof result.catch === 'function') result.catch(() => {});
  return true;
}
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
        headless: bool,
        launch_timeout_seconds: int,
        navigation_timeout_seconds: int,
        player_timeout_seconds: int,
        media_capture_timeout_seconds: int,
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


def _safe_media_domain(url: str) -> str | None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return parsed.hostname.lower()


def _is_media_response(content_type: str, resource_type: str) -> bool:
    mime = content_type.split(";", 1)[0].strip().lower()
    return resource_type in {"media", "xhr", "fetch"} and (
        mime.startswith("video/") or mime in HLS_CONTENT_TYPES
    )


def _first_public_url(values: list[str]) -> str | None:
    for value in values:
        if isinstance(value, str) and value.startswith(("https://", "http://")):
            return value
    return None


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
    async def _wait_for_primary_player(page: Any, timeout_seconds: int) -> bool:
        try:
            await page.wait_for_function(PRIMARY_VIDEO_MOUNTED_SCRIPT, timeout=timeout_seconds * 1000)
        except Exception as error:
            if error.__class__.__name__ == "TimeoutError":
                return False
            raise
        return True

    @staticmethod
    async def _player_snapshot(page: Any) -> dict[str, Any]:
        snapshot = await page.evaluate(PRIMARY_VIDEO_SNAPSHOT_SCRIPT)
        if not isinstance(snapshot, dict):
            return {"video_count": 0, "visible_video_count": 0, "primary": None}
        return snapshot

    @staticmethod
    def _snapshot_urls(snapshot: dict[str, Any]) -> tuple[list[str], bool, bool, bool, bool]:
        primary = snapshot.get("primary")
        if not isinstance(primary, dict):
            return [], False, False, False, False
        current_src = primary.get("current_src")
        src = primary.get("src")
        source_urls = primary.get("source_urls")
        urls = [value for value in [current_src, src] if isinstance(value, str) and value]
        if isinstance(source_urls, list):
            urls.extend(value for value in source_urls if isinstance(value, str) and value)
        return (
            urls,
            bool(current_src),
            bool(src),
            bool(source_urls),
            any(value.startswith("blob:") for value in urls),
        )

    async def capture(
        self,
        *,
        target_url: str,
        target_id: str,
        storage_state_path: str,
        timeout_seconds: int,
        headless: bool = True,
        launch_timeout_seconds: int | None = None,
        navigation_timeout_seconds: int | None = None,
        player_timeout_seconds: int | None = None,
        media_capture_timeout_seconds: int | None = None,
    ) -> CapturedMedia:
        # The lazy loader returns Playwright's async_playwright factory, not
        # the async context manager itself.
        context_manager_factory = self.playwright_factory or _load_async_playwright()
        launch_timeout_seconds = launch_timeout_seconds or timeout_seconds
        navigation_timeout_seconds = navigation_timeout_seconds or timeout_seconds
        player_timeout_seconds = player_timeout_seconds or timeout_seconds
        media_capture_timeout_seconds = media_capture_timeout_seconds or timeout_seconds
        phase_started = time.monotonic()
        phase_ms: dict[str, int] = {}
        phase = "browser_launch"

        def move_to(next_phase: str) -> None:
            nonlocal phase, phase_started
            phase_ms[phase] = int((time.monotonic() - phase_started) * 1000)
            phase = next_phase
            phase_started = time.monotonic()

        def log_phase_failure() -> None:
            phase_ms[phase] = int((time.monotonic() - phase_started) * 1000)
            logger.warning(
                "douyin_session_phase target_id=%s last_phase=%s phase_ms=%s",
                target_id,
                phase,
                ",".join(f"{name}:{elapsed}" for name, elapsed in phase_ms.items()),
            )

        try:
            async with context_manager_factory() as playwright:
                browser = await asyncio.wait_for(
                    playwright.chromium.launch(headless=headless), timeout=launch_timeout_seconds
                )
                try:
                    context = await browser.new_context(storage_state=storage_state_path)
                    try:
                        page = await context.new_page()
                        playback_media: list[tuple[str, str]] = []
                        capture_playback_responses = False

                        def observe_response(response: Any) -> None:
                            request = response.request
                            content_type = response.headers.get("content-type", "").lower()
                            # Only collect media responses after the verified primary player
                            # has been started.  Preloads, ads and recommendation responses
                            # are intentionally excluded.
                            if (
                                capture_playback_responses
                                and _is_media_response(content_type, request.resource_type)
                                and response.url not in [candidate[0] for candidate in playback_media]
                            ):
                                playback_media.append((response.url, content_type.split(";", 1)[0].lower()))

                        page.on("response", observe_response)
                        move_to("page_navigation")
                        await page.goto(
                            target_url,
                            wait_until="domcontentloaded",
                            timeout=navigation_timeout_seconds * 1000,
                        )
                        move_to("target_identity")
                        if await self._has_visible_risk_component(page):
                            return CapturedMedia(target_id=None, media_url=None, state="risk")
                        if "/login" in page.url.lower():
                            return CapturedMedia(target_id=None, media_url=None, state="expired")
                        if target_id_from_url(page.url) != target_id:
                            return CapturedMedia(target_id=None, media_url=None, state="mismatch")
                        move_to("player_mount")
                        if not await self._wait_for_primary_player(page, player_timeout_seconds):
                            return CapturedMedia(target_id=target_id, media_url=None, state="player_missing")
                        before_start = await self._player_snapshot(page)
                        move_to("player_activation")
                        capture_playback_responses = True
                        await asyncio.wait_for(
                            page.evaluate(PRIMARY_VIDEO_START_SCRIPT), timeout=player_timeout_seconds
                        )
                        move_to("media_capture")
                        try:
                            await page.wait_for_function(
                                """() => Array.from(document.querySelectorAll('video')).some(
                                    (video) => Boolean(video.currentSrc || video.src
                                        || video.querySelector('source[src]'))
                                )""",
                                timeout=media_capture_timeout_seconds * 1000,
                            )
                        except Exception as error:
                            if error.__class__.__name__ != "TimeoutError":
                                raise
                        snapshot = await self._player_snapshot(page)
                        (
                            direct_urls,
                            has_current_src,
                            has_src,
                            has_source_child,
                            has_blob_url,
                        ) = self._snapshot_urls(snapshot)
                        # The final route is exact; only then can public structured
                        # metadata from this page be associated with the target work.
                        # The final route is exact; only then can public structured
                        # metadata from this page be associated with the target work.
                        from ..parsers.douyin import DouyinParser

                        document = await page.content()
                        _title, media_urls, _covers = DouyinParser._structured_metadata(document)
                        direct_media_url = _first_public_url(direct_urls)
                        structured_media_url = _first_public_url(media_urls)
                        network_urls = [candidate[0] for candidate in playback_media]
                        media_url = direct_media_url or structured_media_url
                        if media_url is None and has_blob_url and len(network_urls) == 1:
                            # A blob player has no directly probeable URL.  A single response
                            # produced only after starting the verified primary player is a
                            # bounded candidate; multiple responses stay unresolved to avoid
                            # choosing ads or recommendations.
                            media_url = network_urls[0]
                        domains = tuple(
                            sorted(
                                {
                                    domain
                                    for url, _mime in playback_media
                                    if (domain := _safe_media_domain(url))
                                }
                            )
                        )
                        phase_ms[phase] = int((time.monotonic() - phase_started) * 1000)
                        diagnostics = PlayerDiagnostics(
                            page_route=f"https://www.douyin.com/video/{target_id}",
                            target_id=target_id,
                            video_count=int(
                                snapshot.get("video_count", before_start.get("video_count", 0))
                            ),
                            visible_video_count=int(
                                snapshot.get(
                                    "visible_video_count",
                                    before_start.get("visible_video_count", 0),
                                )
                            ),
                            has_current_src=has_current_src,
                            has_src=has_src,
                            has_source_child=has_source_child,
                            has_blob_url=has_blob_url,
                            media_response_count=len(playback_media),
                            media_content_types=tuple(sorted({mime for _url, mime in playback_media})),
                            media_domains=domains,
                            last_phase=phase,
                            phase_ms=tuple(phase_ms.items()),
                        )
                        return CapturedMedia(
                            target_id=target_id,
                            media_url=media_url,
                            state="ok" if media_url else "media_missing",
                            diagnostics=diagnostics,
                        )
                    finally:
                        await context.close()
                finally:
                    await browser.close()
        except TimeoutError as error:
            log_phase_failure()
            raise session_timeout() from error
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
        try:
            state_path = validate_storage_state_path(
                self.settings.douyin_storage_state_path,
                require_exists=True,
            )
        except ValueError as error:
            logger.warning("douyin_session_worker outcome=config_invalid")
            raise session_config_invalid() from error
        started = time.monotonic()
        async with self._semaphore:
            try:
                capture = await asyncio.wait_for(
                    self.browser.capture(
                        target_url=target_url,
                        target_id=target_id,
                        storage_state_path=str(state_path),
                        timeout_seconds=self.settings.douyin_session_timeout_seconds,
                        headless=self.settings.douyin_session_headless,
                        launch_timeout_seconds=self.settings.douyin_session_launch_timeout_seconds,
                        navigation_timeout_seconds=self.settings.douyin_session_navigation_timeout_seconds,
                        player_timeout_seconds=self.settings.douyin_session_player_timeout_seconds,
                        media_capture_timeout_seconds=self.settings.douyin_session_media_capture_timeout_seconds,
                    ),
                    timeout=(
                        self.settings.douyin_session_launch_timeout_seconds
                        + self.settings.douyin_session_navigation_timeout_seconds
                        + self.settings.douyin_session_player_timeout_seconds * 2
                        + self.settings.douyin_session_media_capture_timeout_seconds
                    ),
                )
            except TimeoutError as error:
                raise session_timeout() from error
            if capture.diagnostics is not None:
                diagnostics = capture.diagnostics
                logger.info(
                    "douyin_session_player target_id=%s page=%s videos=%d visible=%d "
                    "current_src=%s src=%s source_child=%s blob=%s media_responses=%d "
                    "content_types=%s media_domains=%s last_phase=%s phase_ms=%s",
                    diagnostics.target_id,
                    diagnostics.page_route,
                    diagnostics.video_count,
                    diagnostics.visible_video_count,
                    diagnostics.has_current_src,
                    diagnostics.has_src,
                    diagnostics.has_source_child,
                    diagnostics.has_blob_url,
                    diagnostics.media_response_count,
                    ",".join(diagnostics.media_content_types) or "none",
                    ",".join(diagnostics.media_domains) or "none",
                    diagnostics.last_phase,
                    ",".join(f"{name}:{elapsed}" for name, elapsed in diagnostics.phase_ms),
                )
            if capture.state == "expired":
                raise session_expired()
            if capture.state == "risk":
                raise risk_controlled()
            if capture.state == "player_missing":
                raise session_player_not_found()
            if capture.state == "media_missing":
                raise session_media_not_found()
            if capture.state != "ok" or capture.target_id != target_id:
                raise target_mismatch()
            if not capture.media_url:
                raise session_media_not_found()
            try:
                logger.info("douyin_session_phase target_id=%s phase=media_verify", target_id)
                async with asyncio.timeout(self.settings.douyin_session_media_verify_timeout_seconds):
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
            except TimeoutError as error:
                raise AppError(
                    "DOUYIN_SESSION_MEDIA_VERIFY_TIMEOUT", "媒体公开复验超时", retryable=True
                ) from error
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
