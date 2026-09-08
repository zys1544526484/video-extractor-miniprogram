from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import parse_qs, urlsplit

from ..config import Settings
from ..errors import AppError
from ..parsers.douyin import DouyinParser
from ..services.safe_http import SafeHttpClient
from .bootstrap import _load_async_playwright
from .errors import (
    risk_controlled,
    session_bound_media,
    session_config_invalid,
    session_disabled,
    session_expired,
    session_login_required,
    session_media_not_found,
    session_page_failed,
    session_player_not_found,
    session_timeout,
    session_unavailable,
    target_mismatch,
)
from .models import (
    CapturedMedia,
    PlayerDiagnostics,
    SessionWorkerResult,
    has_valid_douyin_cookie,
    target_id_from_url,
    validate_storage_state_path,
)

logger = logging.getLogger(__name__)

RISK_URL_MARKERS = ("/captcha", "/verify", "/security", "/risk")
RISK_COMPONENT_SELECTOR = (
    '[data-e2e*="captcha"], [data-e2e*="verify"], [data-e2e*="risk"], '
    'iframe[src*="captcha"], iframe[src*="verify"], [role="dialog"][data-captcha]'
)
LOGIN_COMPONENT_SELECTOR = (
    '[data-e2e*="login"], [data-e2e*="login-button"], '
    '[class*="login"][role="dialog"], [role="dialog"] [data-e2e*="qrcode"]'
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
MAX_EARLY_MEDIA_CANDIDATES = 4
MAX_EARLY_MEDIA_URL_LENGTH = 4096
MAX_EARLY_MEDIA_AGE_SECONDS = 15
MAX_DETAIL_RESPONSE_TASKS = 2
DETAIL_PATH_MARKERS = (
    "/aweme/v1/web/aweme/detail/",
    "/aweme/v1/aweme/detail/",
    "/aweme/detail/",
)


@dataclass(frozen=True)
class CachedMediaCandidate:
    """Ephemeral browser response evidence; never log or persist the URL."""

    url: str
    content_type: str
    captured_at: float
    main_frame: bool
    referer: str | None


@dataclass(frozen=True)
class TargetBoundMediaGroup:
    """Bound media mirrors from one exact target work JSON payload."""

    source: str
    urls: tuple[str, ...]


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
        public_url_validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None = None,
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
    return f"{parsed.scheme}://{parsed.hostname.lower()}"


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
        self.last_diagnostics: PlayerDiagnostics | None = None
        self._active_candidate_count = 0

    @staticmethod
    async def _has_visible_risk_component(page: Any) -> bool:
        if any(marker in page.url.lower() for marker in RISK_URL_MARKERS):
            return True
        try:
            return await page.locator(RISK_COMPONENT_SELECTOR).first.is_visible(timeout=250)
        except Exception:
            return False

    @staticmethod
    async def _has_visible_login_component(page: Any) -> bool:
        if "/login" in page.url.lower():
            return True
        try:
            return await page.locator(LOGIN_COMPONENT_SELECTOR).first.is_visible(timeout=250)
        except Exception:
            return False

    @staticmethod
    async def _wait_for_primary_player(page: Any, timeout_seconds: int) -> bool:
        try:
            await page.wait_for_function(
                PRIMARY_VIDEO_MOUNTED_SCRIPT,
                timeout=timeout_seconds * 1000,
                polling=100,
            )
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

    @staticmethod
    def _request_is_main_frame(request: Any, page: Any) -> bool:
        frame = getattr(request, "frame", None)
        main_frame = getattr(page, "main_frame", None)
        return frame is None or main_frame is None or frame is main_frame

    @staticmethod
    def _request_referer(request: Any) -> str | None:
        headers = getattr(request, "headers", {}) or {}
        value = headers.get("referer") or headers.get("Referer")
        return value if isinstance(value, str) and len(value) <= MAX_EARLY_MEDIA_URL_LENGTH else None

    @staticmethod
    def _is_target_detail_request(request: Any, target_id: str) -> bool:
        """Accept only an explicit official detail request for this work id."""
        try:
            parsed = urlsplit(str(getattr(request, "url", "")))
        except ValueError:
            return False
        host = (parsed.hostname or "").lower().rstrip(".")
        allowed_host = (
            host == "douyin.com"
            or host.endswith(".douyin.com")
            or host == "iesdouyin.com"
            or host.endswith(".iesdouyin.com")
        )
        if not allowed_host:
            return False
        if not any(marker in parsed.path for marker in DETAIL_PATH_MARKERS):
            return False
        return parse_qs(parsed.query).get("aweme_id") == [target_id]

    @staticmethod
    async def _response_target_group(response: Any, target_id: str) -> TargetBoundMediaGroup | None:
        """Parse a detail JSON response without retaining its URL or body."""
        request = getattr(response, "request", None)
        if request is None or not PlaywrightSessionAdapter._is_target_detail_request(request, target_id):
            return None
        content_type = str(getattr(response, "headers", {}).get("content-type", "")).lower()
        if "json" not in content_type:
            return None
        try:
            payload = await response.json()
        except Exception:
            return None
        urls = DouyinParser.target_bound_media_urls_from_payload(payload, target_id)
        if not urls:
            return None
        return TargetBoundMediaGroup("detail_json", tuple(urls[:MAX_EARLY_MEDIA_CANDIDATES]))

    @staticmethod
    def _referer_matches_target(referer: str | None, target_url: str) -> bool:
        if referer is None:
            return False
        referer_parts = urlsplit(referer)
        target_parts = urlsplit(target_url)
        return (
            referer_parts.scheme == target_parts.scheme
            and referer_parts.hostname == target_parts.hostname
            and referer_parts.path == target_parts.path
        )

    async def _select_early_candidate(
        self,
        candidates: list[CachedMediaCandidate],
        *,
        target_url: str,
        validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None,
    ) -> str | None:
        """Select exactly one public, target-page candidate after identity is verified."""
        now = time.monotonic()
        accepted: list[str] = []
        for candidate in candidates:
            if (
                not candidate.main_frame
                or now - candidate.captured_at > MAX_EARLY_MEDIA_AGE_SECONDS
                or not self._referer_matches_target(candidate.referer, target_url)
            ):
                continue
            if validator is not None:
                try:
                    await validator(candidate.url)
                except AppError:
                    continue
            accepted.append(candidate.url)
        unique = list(dict.fromkeys(accepted))
        return unique[0] if len(unique) == 1 else None

    async def _validated_group_urls(
        self,
        urls: tuple[str, ...] | list[str],
        validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None,
    ) -> tuple[str, ...]:
        """Keep only safe media mirrors; raw addresses stay task-local."""
        valid: list[str] = []
        for url in urls[:MAX_EARLY_MEDIA_CANDIDATES]:
            checked = await self._validate_direct_url(url, validator)
            if checked is not None and checked not in valid:
                valid.append(checked)
        return tuple(valid)

    async def _validate_direct_url(
        self,
        url: str | None,
        validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None,
    ) -> str | None:
        if url is None or len(url) > MAX_EARLY_MEDIA_URL_LENGTH:
            return None
        if validator is not None:
            try:
                await validator(url)
            except AppError:
                return None
        return url

    @staticmethod
    async def _close_safely(resource: Any, *, resource_name: str, phase: str) -> None:
        if resource is None:
            return
        try:
            await resource.close()
        except Exception as error:
            # Playwright may have closed a context while its page or browser
            # was being torn down.  That is a normal terminal state, not a
            # second failure that should obscure the useful capture result.
            if error.__class__.__name__ == "TargetClosedError" or "closed" in str(error).lower():
                logger.debug(
                    "douyin_session_cleanup outcome=already_closed resource=%s phase=%s",
                    resource_name,
                    phase,
                )
                return
            # Closing must never replace the useful page/player error.  Do not
            # include exception text because browser errors can echo URLs.
            logger.warning(
                "douyin_session_cleanup outcome=failed resource=%s internal_reason=close_failed phase=%s",
                resource_name,
                phase,
            )

    @staticmethod
    def _browser_disconnected(browser: Any | None) -> bool:
        if browser is None:
            return True
        try:
            is_connected = getattr(browser, "is_connected", None)
            return callable(is_connected) and not bool(is_connected())
        except Exception:
            return False

    def _record_diagnostics(
        self,
        *,
        target_id: str,
        phase: str,
        phase_ms: dict[str, int],
        snapshot: dict[str, Any] | None = None,
        playback_media: list[tuple[str, str]] | None = None,
        has_current_src: bool = False,
        has_src: bool = False,
        has_source_child: bool = False,
        has_blob_url: bool = False,
        target_bound_candidate_count: int = 0,
        unbound_candidate_count: int = 0,
        candidate_group_count: int = 0,
        candidate_source: str | None = None,
    ) -> PlayerDiagnostics:
        snapshot = snapshot or {}
        playback_media = playback_media or []
        phase_copy = dict(phase_ms)
        diagnostics = PlayerDiagnostics(
            page_route=f"/video/{target_id}",
            target_id=target_id,
            video_count=int(snapshot.get("video_count", 0)),
            visible_video_count=int(snapshot.get("visible_video_count", 0)),
            has_current_src=has_current_src,
            has_src=has_src,
            has_source_child=has_source_child,
            has_blob_url=has_blob_url,
            media_response_count=len(playback_media),
            media_content_types=tuple(sorted({mime for _url, mime in playback_media})),
            media_domains=tuple(
                sorted(
                    {
                        domain
                        for url, _mime in playback_media
                        if (domain := _safe_media_domain(url))
                    }
                )
            ),
            last_phase=phase,
            phase_ms=tuple(phase_copy.items()),
            target_bound_candidate_count=target_bound_candidate_count,
            unbound_candidate_count=unbound_candidate_count,
            candidate_group_count=candidate_group_count,
            candidate_source=candidate_source,
        )
        self.last_diagnostics = diagnostics
        return diagnostics

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
        public_url_validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None = None,
    ) -> CapturedMedia:
        # The lazy loader returns Playwright's async_playwright factory, not
        # the async context manager itself.
        context_manager_factory = self.playwright_factory or _load_async_playwright()
        launch_timeout_seconds = launch_timeout_seconds or timeout_seconds
        navigation_timeout_seconds = navigation_timeout_seconds or timeout_seconds
        player_timeout_seconds = player_timeout_seconds or timeout_seconds
        media_capture_timeout_seconds = media_capture_timeout_seconds or timeout_seconds
        self.last_diagnostics = None
        self._active_candidate_count = 0
        phase_started = time.monotonic()
        phase_ms: dict[str, int] = {}
        phase = "browser_launch"

        def move_to(next_phase: str) -> None:
            nonlocal phase, phase_started
            phase_ms[phase] = int((time.monotonic() - phase_started) * 1000)
            phase = next_phase
            phase_started = time.monotonic()

        def complete_phase() -> None:
            phase_ms[phase] = int((time.monotonic() - phase_started) * 1000)

        def log_phase_failure() -> None:
            complete_phase()
            logger.warning(
                "douyin_session_phase target_id=%s last_phase=%s phase_ms=%s",
                target_id,
                phase,
                ",".join(f"{name}:{elapsed}" for name, elapsed in phase_ms.items()),
            )

        try:
            manager = context_manager_factory()
        except AppError:
            raise
        except Exception as error:
            raise session_unavailable() from error

        browser: Any | None = None
        context: Any | None = None
        page: Any | None = None
        snapshot: dict[str, Any] = {}
        playback_media: list[tuple[str, str]] = []
        early_candidates: list[CachedMediaCandidate] = []
        detail_tasks: list[asyncio.Task[TargetBoundMediaGroup | None]] = []
        target_groups: list[TargetBoundMediaGroup] = []
        try:
            async with manager as playwright:
                try:
                    browser = await asyncio.wait_for(
                        playwright.chromium.launch(headless=headless), timeout=launch_timeout_seconds
                    )
                except TimeoutError as error:
                    log_phase_failure()
                    self._record_diagnostics(target_id=target_id, phase=phase, phase_ms=phase_ms)
                    raise session_timeout() from error
                except Exception as error:
                    log_phase_failure()
                    self._record_diagnostics(target_id=target_id, phase=phase, phase_ms=phase_ms)
                    raise session_unavailable() from error
                try:
                    context = await browser.new_context(storage_state=storage_state_path)
                    page = await context.new_page()
                except Exception as error:
                    log_phase_failure()
                    self._record_diagnostics(target_id=target_id, phase=phase, phase_ms=phase_ms)
                    raise session_page_failed() from error
                try:
                        def observe_response(response: Any) -> None:
                            request = response.request
                            # A detail response is stronger evidence than a CDN URL:
                            # both its request and its parsed JSON must name the exact
                            # target aweme.  Do this before navigation without logging
                            # either response URL or body.
                            if (
                                self._is_target_detail_request(request, target_id)
                                and len(detail_tasks) < MAX_DETAIL_RESPONSE_TASKS
                            ):
                                detail_tasks.append(
                                    asyncio.create_task(self._response_target_group(response, target_id))
                                )
                            content_type = response.headers.get("content-type", "").lower()
                            url = response.url
                            if (
                                not _is_media_response(content_type, request.resource_type)
                                or not isinstance(url, str)
                                or len(url) > MAX_EARLY_MEDIA_URL_LENGTH
                                or len(early_candidates) >= MAX_EARLY_MEDIA_CANDIDATES
                                or any(candidate.url == url for candidate in early_candidates)
                            ):
                                return
                            # This listener is intentionally installed before goto. The raw URL
                            # remains only in task memory until target identity is confirmed.
                            early_candidates.append(
                                CachedMediaCandidate(
                                    url=url,
                                    content_type=content_type.split(";", 1)[0].lower(),
                                    captured_at=time.monotonic(),
                                    main_frame=self._request_is_main_frame(request, page),
                                    referer=self._request_referer(request),
                                )
                            )
                            self._active_candidate_count = len(early_candidates)
                            playback_media[:] = [
                                (candidate.url, candidate.content_type)
                                for candidate in early_candidates
                            ]

                        page.on("response", observe_response)
                        move_to("page_navigation")
                        try:
                            await page.goto(
                                target_url,
                                wait_until="domcontentloaded",
                                timeout=navigation_timeout_seconds * 1000,
                            )
                        except TimeoutError as error:
                            log_phase_failure()
                            self._record_diagnostics(target_id=target_id, phase=phase, phase_ms=phase_ms)
                            raise session_timeout() from error
                        except Exception as error:
                            log_phase_failure()
                            self._record_diagnostics(target_id=target_id, phase=phase, phase_ms=phase_ms)
                            raise session_page_failed() from error
                        move_to("target_identity")
                        if await self._has_visible_risk_component(page):
                            complete_phase()
                            return CapturedMedia(
                                target_id=None,
                                media_url=None,
                                state="risk",
                                diagnostics=self._record_diagnostics(
                                    target_id=target_id, phase=phase, phase_ms=phase_ms
                                ),
                            )
                        if await self._has_visible_login_component(page):
                            complete_phase()
                            return CapturedMedia(
                                target_id=None,
                                media_url=None,
                                state="expired",
                                diagnostics=self._record_diagnostics(
                                    target_id=target_id, phase=phase, phase_ms=phase_ms
                                ),
                            )
                        if target_id_from_url(page.url) != target_id:
                            complete_phase()
                            return CapturedMedia(
                                target_id=None,
                                media_url=None,
                                state="mismatch",
                                diagnostics=self._record_diagnostics(
                                    target_id=target_id, phase=phase, phase_ms=phase_ms
                                ),
                            )
                        # Consume only completed official detail JSON responses after
                        # target identity is exact. A bad/mismatched JSON simply yields
                        # no group; it cannot influence naked CDN fallback selection.
                        if detail_tasks:
                            done, pending = await asyncio.wait(
                                detail_tasks,
                                timeout=min(1, media_capture_timeout_seconds),
                            )
                            for task in done:
                                try:
                                    group = task.result()
                                except Exception:
                                    group = None
                                if group is not None:
                                    target_groups.append(group)
                            for task in pending:
                                task.cancel()
                        document = await page.content()
                        hydration_urls = DouyinParser.target_bound_media_urls_from_document(
                            document, target_id
                        )
                        if hydration_urls:
                            target_groups.append(
                                TargetBoundMediaGroup(
                                    "hydration_json",
                                    tuple(hydration_urls[:MAX_EARLY_MEDIA_CANDIDATES]),
                                )
                            )
                        # Bound details/hydration are deterministic: their URL list is
                        # one exact work object, ordered by H.264, play, bitrate,
                        # download. Do not wait for a blob player or reload when present.
                        for group in target_groups:
                            bound_urls = await self._validated_group_urls(group.urls, public_url_validator)
                            if bound_urls:
                                move_to("structured_media")
                                complete_phase()
                                diagnostics = self._record_diagnostics(
                                    target_id=target_id,
                                    phase=phase,
                                    phase_ms=phase_ms,
                                    playback_media=playback_media,
                                    target_bound_candidate_count=len(bound_urls),
                                    unbound_candidate_count=len(early_candidates),
                                    candidate_group_count=len(target_groups),
                                    candidate_source=group.source,
                                )
                                return CapturedMedia(
                                    target_id=target_id,
                                    media_url=bound_urls[0],
                                    media_urls=bound_urls,
                                    candidate_source=group.source,
                                    diagnostics=diagnostics,
                                )
                        move_to("player_mount")
                        if not await self._wait_for_primary_player(page, player_timeout_seconds):
                            snapshot = await self._player_snapshot(page)
                            complete_phase()
                            return CapturedMedia(
                                target_id=target_id,
                                media_url=None,
                                state="player_missing",
                                diagnostics=self._record_diagnostics(
                                    target_id=target_id,
                                    phase=phase,
                                    phase_ms=phase_ms,
                                    snapshot=snapshot,
                                ),
                            )
                        before_start = await self._player_snapshot(page)
                        move_to("player_activation")
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
                        direct_media_url = await self._validate_direct_url(
                            _first_public_url(direct_urls), public_url_validator
                        )
                        media_url = direct_media_url
                        candidate_source = "main_player_network" if media_url else None
                        if media_url is None and has_blob_url:
                            media_url = await self._select_early_candidate(
                                early_candidates,
                                target_url=target_url,
                                validator=public_url_validator,
                            )
                            if media_url is not None:
                                candidate_source = "main_player_network"
                        if media_url is None and has_blob_url:
                            # Some MediaSource players fetch their manifest before the
                            # visible video is activated. One controlled reload gives the
                            # already-installed listener a single fresh chance; never loop.
                            move_to("player_reload")
                            await page.reload(
                                wait_until="domcontentloaded",
                                timeout=navigation_timeout_seconds * 1000,
                            )
                            if target_id_from_url(page.url) != target_id:
                                return CapturedMedia(
                                    target_id=None,
                                    media_url=None,
                                    state="mismatch",
                                    diagnostics=self._record_diagnostics(
                                        target_id=target_id,
                                        phase=phase,
                                        phase_ms=phase_ms,
                                        playback_media=playback_media,
                                    ),
                                )
                            if await self._wait_for_primary_player(page, player_timeout_seconds):
                                await asyncio.wait_for(
                                    page.evaluate(PRIMARY_VIDEO_START_SCRIPT),
                                    timeout=player_timeout_seconds,
                                )
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
                                    replay_urls,
                                    has_current_src,
                                    has_src,
                                    has_source_child,
                                    has_blob_url,
                                ) = self._snapshot_urls(snapshot)
                                media_url = await self._validate_direct_url(
                                    _first_public_url(replay_urls), public_url_validator
                                )
                                if media_url is not None:
                                    candidate_source = "main_player_network"
                                if media_url is None:
                                    media_url = await self._select_early_candidate(
                                        early_candidates,
                                        target_url=target_url,
                                        validator=public_url_validator,
                                    )
                                    if media_url is not None:
                                        candidate_source = "main_player_network"
                        complete_phase()
                        diagnostics = self._record_diagnostics(
                            target_id=target_id,
                            phase=phase,
                            phase_ms=phase_ms,
                            snapshot={
                                "video_count": snapshot.get(
                                    "video_count", before_start.get("video_count", 0)
                                ),
                                "visible_video_count": snapshot.get(
                                    "visible_video_count",
                                    before_start.get("visible_video_count", 0),
                                ),
                            },
                            playback_media=playback_media,
                            has_current_src=has_current_src,
                            has_src=has_src,
                            has_source_child=has_source_child,
                            has_blob_url=has_blob_url,
                            target_bound_candidate_count=0,
                            unbound_candidate_count=len(early_candidates),
                            candidate_group_count=len(target_groups),
                            candidate_source=candidate_source,
                        )
                        return CapturedMedia(
                            target_id=target_id,
                            media_url=media_url,
                            state="ok" if media_url else "media_missing",
                            diagnostics=diagnostics,
                            media_urls=(media_url,) if media_url else (),
                            candidate_source=candidate_source,
                        )
                except TimeoutError as error:
                    log_phase_failure()
                    self._record_diagnostics(
                        target_id=target_id, phase=phase, phase_ms=phase_ms, snapshot=snapshot,
                        playback_media=playback_media,
                    )
                    raise session_timeout() from error
                except AppError:
                    raise
                except Exception as error:
                    log_phase_failure()
                    self._record_diagnostics(
                        target_id=target_id, phase=phase, phase_ms=phase_ms, snapshot=snapshot,
                        playback_media=playback_media,
                    )
                    raise session_page_failed() from error
        except TimeoutError as error:
            log_phase_failure()
            self._record_diagnostics(
                target_id=target_id,
                phase=phase,
                phase_ms=phase_ms,
                snapshot=snapshot,
                playback_media=playback_media,
            )
            raise session_timeout() from error
        except AppError:
            raise
        except Exception as error:
            log_phase_failure()
            self._record_diagnostics(
                target_id=target_id,
                phase=phase,
                phase_ms=phase_ms,
                snapshot=snapshot,
                playback_media=playback_media,
            )
            if self._browser_disconnected(browser):
                raise session_unavailable() from error
            # The browser has launched and remains connected. An unexpected
            # page/context error is not an unavailable Playwright environment.
            raise session_page_failed() from error
        finally:
            # Candidate URLs are task-local evidence only. Clear them before
            # releasing browser resources so they cannot survive into another job.
            early_candidates.clear()
            playback_media.clear()
            for task in detail_tasks:
                if not task.done():
                    task.cancel()
            if detail_tasks:
                await asyncio.gather(*detail_tasks, return_exceptions=True)
            detail_tasks.clear()
            target_groups.clear()
            self._active_candidate_count = 0
            await self._close_safely(page, resource_name="page", phase=phase)
            await self._close_safely(context, resource_name="context", phase=phase)
            await self._close_safely(browser, resource_name="browser", phase=phase)


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
        self.last_diagnostics: PlayerDiagnostics | None = None
        # Stable internal category for operators and tests.  It intentionally
        # never contains a browser exception message or a URL.
        self.last_internal_reason: str | None = None

    def _copy_browser_diagnostics(self) -> None:
        diagnostics = getattr(self.browser, "last_diagnostics", None)
        if isinstance(diagnostics, PlayerDiagnostics):
            self.last_diagnostics = diagnostics

    async def inspect(self, target_url: str) -> SessionWorkerResult:
        self.last_diagnostics = None
        self.last_internal_reason = None
        if not self.settings.douyin_session_enabled:
            self.last_internal_reason = "feature_disabled"
            raise session_disabled()
        target_id = target_id_from_url(target_url)
        if target_id is None:
            self.last_internal_reason = "invalid_target"
            raise AppError("URL_INVALID", "抖音专用会话只接受已确认的作品链接")
        try:
            state_path = validate_storage_state_path(
                self.settings.douyin_storage_state_path,
                require_exists=True,
            )
        except ValueError as error:
            self.last_internal_reason = "storage_state_invalid"
            logger.warning("douyin_session_worker outcome=config_invalid")
            raise session_config_invalid() from error
        if not has_valid_douyin_cookie(state_path):
            self.last_internal_reason = "storage_state_not_logged_in"
            logger.warning("douyin_session_worker outcome=login_required")
            raise session_login_required()
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
                        public_url_validator=self.http.validate_url,
                    ),
                    timeout=(
                        self.settings.douyin_session_launch_timeout_seconds
                        + self.settings.douyin_session_navigation_timeout_seconds
                        + self.settings.douyin_session_player_timeout_seconds * 2
                        + self.settings.douyin_session_media_capture_timeout_seconds
                    ),
                )
            except TimeoutError as error:
                self._copy_browser_diagnostics()
                self.last_internal_reason = "worker_timeout"
                raise session_timeout() from error
            except AppError:
                self._copy_browser_diagnostics()
                raise
            if capture.diagnostics is not None:
                diagnostics = capture.diagnostics
                self.last_diagnostics = diagnostics
                logger.info(
                    "douyin_session_player target_id=%s page=%s videos=%d visible=%d "
                    "current_src=%s src=%s source_child=%s blob=%s media_responses=%d "
                    "content_types=%s media_domains=%s bound=%d unbound=%d groups=%d source=%s "
                    "last_phase=%s phase_ms=%s",
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
                    diagnostics.target_bound_candidate_count,
                    diagnostics.unbound_candidate_count,
                    diagnostics.candidate_group_count,
                    diagnostics.candidate_source or "none",
                    diagnostics.last_phase,
                    ",".join(f"{name}:{elapsed}" for name, elapsed in diagnostics.phase_ms),
                )
            if capture.state == "expired":
                self.last_internal_reason = "session_expired"
                raise session_expired()
            if capture.state == "risk":
                self.last_internal_reason = "risk_component_visible"
                raise risk_controlled()
            if capture.state == "player_missing":
                self.last_internal_reason = "player_not_mounted"
                raise session_player_not_found()
            if capture.state == "media_missing":
                self.last_internal_reason = "player_media_missing"
                raise session_media_not_found()
            if capture.state != "ok" or capture.target_id != target_id:
                self.last_internal_reason = "target_mismatch"
                raise target_mismatch()
            media_urls = capture.media_urls or ((capture.media_url,) if capture.media_url else ())
            if not media_urls:
                self.last_internal_reason = "player_media_missing"
                raise session_media_not_found()
            probe: dict[str, Any] | None = None
            bytes_read = 0
            verified_url: str | None = None
            last_error: AppError | None = None
            for candidate_url in media_urls:
                try:
                    logger.info("douyin_session_phase target_id=%s phase=media_verify", target_id)
                    async with asyncio.timeout(self.settings.douyin_session_media_verify_timeout_seconds):
                        public_headers = {**PUBLIC_MEDIA_HEADERS, "Referer": target_url}
                        candidate_probe = await self.http.probe_media(candidate_url, headers=public_headers)
                        stream = await self.http.open_stream(
                            candidate_url,
                            headers=public_headers,
                            range_header="bytes=0-1023",
                            media_kind="video",
                        )
                        try:
                            candidate_bytes = 0
                            async for chunk in stream.response.aiter_bytes():
                                candidate_bytes += len(chunk)
                                if candidate_bytes >= 1024:
                                    break
                        finally:
                            await stream.close()
                    if candidate_bytes >= 1024:
                        verified_url, probe, bytes_read = candidate_url, candidate_probe, candidate_bytes
                        break
                    last_error = AppError("DOWNLOAD_FAILED", "公开媒体无法读取足够的视频数据", retryable=True)
                except TimeoutError as error:
                    last_error = AppError(
                        "DOUYIN_SESSION_MEDIA_VERIFY_TIMEOUT", "媒体公开复验超时", retryable=True
                    )
                    last_error.__cause__ = error
                except AppError as error:
                    last_error = error
            if verified_url is None:
                if last_error is not None and last_error.code == "CONTENT_NOT_PUBLIC":
                    self.last_internal_reason = "session_bound_media"
                    raise session_bound_media() from last_error
                if last_error is not None:
                    self.last_internal_reason = "media_verify_failed"
                    raise last_error
                self.last_internal_reason = "public_media_too_short"
                raise AppError("DOWNLOAD_FAILED", "公开媒体无法读取足够的视频数据", retryable=True)
            result = SessionWorkerResult(
                target_id=target_id,
                media_origin=_sanitise_media_origin(verified_url),
                size_bytes=probe.get("size") if probe is not None else None,
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
