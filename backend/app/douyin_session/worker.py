from __future__ import annotations

import asyncio
import hashlib
import logging
import re
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
MEDIA_SOURCE_TRACE_INIT_SCRIPT = r"""
(() => {
  if (window.__videoExtractorReadPrimaryMseUrls) return;
  const MAX_URLS = 4;
  const MAX_URL_LENGTH = 4096;
  let active = true;
  const blobToMediaSource = new Map();
  const blobToDirectUrls = new Map();
  const mediaSourceUrls = new WeakMap();
  const sourceBufferMediaSource = new WeakMap();
  const payloadUrls = new WeakMap();
  const streamUrls = new WeakMap();
  const readerUrls = new WeakMap();

  const boundedUrl = (value) => typeof value === 'string'
    && value.length <= MAX_URL_LENGTH
    && (value.startsWith('https://') || value.startsWith('http://'));
  const payloadKey = (value) => {
    if (value instanceof ArrayBuffer) return value;
    if (ArrayBuffer.isView(value)) return value.buffer;
    if (typeof Blob !== 'undefined' && value instanceof Blob) return value;
    return null;
  };
  const rememberPayload = (payload, url) => {
    const key = payloadKey(payload);
    if (active && key && boundedUrl(url)) payloadUrls.set(key, url);
  };
  const rememberMediaUrl = (mediaSource, url) => {
    if (!active || !mediaSource || !boundedUrl(url)) return;
    const values = mediaSourceUrls.get(mediaSource) || [];
    if (!values.includes(url) && values.length < MAX_URLS) values.push(url);
    mediaSourceUrls.set(mediaSource, values);
  };

  try {
    const originalCreateObjectURL = URL.createObjectURL.bind(URL);
    URL.createObjectURL = (object) => {
      const blobUrl = originalCreateObjectURL(object);
      if (!active) return blobUrl;
      const isMediaSource = (typeof MediaSource !== 'undefined' && object instanceof MediaSource)
        || (typeof ManagedMediaSource !== 'undefined' && object instanceof ManagedMediaSource);
      if (isMediaSource) blobToMediaSource.set(blobUrl, object);
      const directUrl = payloadUrls.get(object);
      if (boundedUrl(directUrl)) blobToDirectUrls.set(blobUrl, [directUrl]);
      return blobUrl;
    };
  } catch (_) {}

  const instrumentMediaSource = (constructor) => {
    if (!constructor || !constructor.prototype) return;
    const originalAddSourceBuffer = constructor.prototype.addSourceBuffer;
    if (typeof originalAddSourceBuffer !== 'function') return;
    constructor.prototype.addSourceBuffer = function(...args) {
      const sourceBuffer = originalAddSourceBuffer.apply(this, args);
      sourceBufferMediaSource.set(sourceBuffer, this);
      return sourceBuffer;
    };
  };
  try { instrumentMediaSource(typeof MediaSource === 'undefined' ? null : MediaSource); } catch (_) {}
  try {
    instrumentMediaSource(typeof ManagedMediaSource === 'undefined' ? null : ManagedMediaSource);
  } catch (_) {}

  try {
    const originalAppendBuffer = SourceBuffer.prototype.appendBuffer;
    SourceBuffer.prototype.appendBuffer = function(payload) {
      const mediaSource = sourceBufferMediaSource.get(this);
      const url = payloadUrls.get(payloadKey(payload));
      rememberMediaUrl(mediaSource, url);
      return originalAppendBuffer.call(this, payload);
    };
  } catch (_) {}

  try {
    const originalArrayBuffer = Response.prototype.arrayBuffer;
    Response.prototype.arrayBuffer = async function() {
      const payload = await originalArrayBuffer.call(this);
      rememberPayload(payload, this.url);
      return payload;
    };
    const originalBlob = Response.prototype.blob;
    Response.prototype.blob = async function() {
      const payload = await originalBlob.call(this);
      rememberPayload(payload, this.url);
      return payload;
    };
  } catch (_) {}

  try {
    const bodyDescriptor = Object.getOwnPropertyDescriptor(Response.prototype, 'body');
    if (bodyDescriptor && typeof bodyDescriptor.get === 'function') {
      Object.defineProperty(Response.prototype, 'body', {
        ...bodyDescriptor,
        get: function() {
          const stream = bodyDescriptor.get.call(this);
          if (active && stream && boundedUrl(this.url)) streamUrls.set(stream, this.url);
          return stream;
        },
      });
    }
    const originalGetReader = ReadableStream.prototype.getReader;
    ReadableStream.prototype.getReader = function(...args) {
      const reader = originalGetReader.apply(this, args);
      const url = streamUrls.get(this);
      if (boundedUrl(url)) readerUrls.set(reader, url);
      return reader;
    };
    const instrumentReader = (constructor) => {
      if (!constructor || !constructor.prototype || typeof constructor.prototype.read !== 'function') {
        return;
      }
      const originalRead = constructor.prototype.read;
      constructor.prototype.read = async function(...args) {
        const result = await originalRead.apply(this, args);
        if (result && result.value) rememberPayload(result.value, readerUrls.get(this));
        return result;
      };
    };
    instrumentReader(
      typeof ReadableStreamDefaultReader === 'undefined' ? null : ReadableStreamDefaultReader
    );
    instrumentReader(
      typeof ReadableStreamBYOBReader === 'undefined' ? null : ReadableStreamBYOBReader
    );
  } catch (_) {}

  try {
    const originalOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function(...args) {
      const requestedUrl = args[1];
      const result = originalOpen.apply(this, args);
      this.addEventListener('readystatechange', () => {
        if (this.readyState === 4) {
          rememberPayload(this.response, this.responseURL || requestedUrl);
        }
      });
      return result;
    };
  } catch (_) {}

  Object.defineProperty(window, '__videoExtractorReadPrimaryMseUrls', {
    configurable: false,
    enumerable: false,
    writable: false,
    value: (blobUrl) => {
      if (!active || typeof blobUrl !== 'string' || !blobUrl.startsWith('blob:')) return [];
      const direct = blobToDirectUrls.get(blobUrl);
      if (Array.isArray(direct)) return direct.slice(0, MAX_URLS);
      const mediaSource = blobToMediaSource.get(blobUrl);
      const values = mediaSource ? mediaSourceUrls.get(mediaSource) : null;
      return Array.isArray(values) ? values.slice(0, MAX_URLS) : [];
    },
  });
  Object.defineProperty(window, '__videoExtractorClearMseTrace', {
    configurable: false,
    enumerable: false,
    writable: false,
    value: () => {
      active = false;
      blobToMediaSource.clear();
      blobToDirectUrls.clear();
    },
  });
})();
"""
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
PAUSE_HIDDEN_VIDEOS_SCRIPT = """
() => {
  let paused = 0;
  for (const video of Array.from(document.querySelectorAll('video'))) {
    const rect = video.getBoundingClientRect();
    const style = getComputedStyle(video);
    const excluded = video.closest('[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
      + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]');
    const visible = !excluded && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
    if (!visible) { video.pause(); video.preload = 'none'; paused += 1; }
  }
  return paused;
}
"""
PRIMARY_VIDEO_SEEK_SCRIPT = """
() => {
  const video = Array.from(document.querySelectorAll('video')).find((candidate) => {
    const rect = candidate.getBoundingClientRect();
    const style = getComputedStyle(candidate);
    const excluded = candidate.closest('[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
      + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]');
    return !excluded && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
  });
  if (!video) return { triggered: false, buffered: false };
  const duration = Number.isFinite(video.duration) ? video.duration : 0;
  let target = null;
  for (let index = 0; index < video.buffered.length; index += 1) {
    const end = video.buffered.end(index);
    if (duration > 1 && end < duration - 0.25) { target = Math.min(duration - 0.1, end + 0.5); break; }
  }
  if (target === null) return { triggered: false, buffered: true };
  try { video.currentTime = target; } catch (_) { return { triggered: false, buffered: true }; }
  const result = video.play();
  if (result && typeof result.catch === 'function') result.catch(() => {});
  return { triggered: true, buffered: false };
}
"""
PRIMARY_VIDEO_MSE_URLS_SCRIPT = """
() => {
  const video = Array.from(document.querySelectorAll('video')).find((candidate) => {
    const rect = candidate.getBoundingClientRect();
    const style = getComputedStyle(candidate);
    const excluded = candidate.closest('[data-e2e*="ad"], [class*="advert"], [class*="ad-"], '
      + '[data-e2e*="recommend"], [class*="recommend"], [class*="related"]');
    return !excluded && style.visibility !== 'hidden' && style.display !== 'none'
      && rect.width > 120 && rect.height > 120;
  });
  if (!video || typeof window.__videoExtractorReadPrimaryMseUrls !== 'function') return [];
  const blobUrl = video.currentSrc || video.src || '';
  return window.__videoExtractorReadPrimaryMseUrls(blobUrl);
}
"""
CLEAR_MEDIA_SOURCE_TRACE_SCRIPT = """
() => {
  if (typeof window.__videoExtractorClearMseTrace === 'function') {
    window.__videoExtractorClearMseTrace();
  }
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
CONTROLLED_CAPTURE_SECONDS = 1
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
    capture_phase: str
    controlled_window: bool
    resource_type: str
    range_total: int | None
    content_length: int | None
    etag_fingerprint: str | None
    path_fingerprint: str


@dataclass
class CandidateRejectionCounts:
    before_target_verified: int = 0
    wrong_frame: int = 0
    referer_exact_target_path: int = 0
    referer_douyin_origin_only: int = 0
    referer_other_douyin_path: int = 0
    referer_external_origin: int = 0
    referer_missing: int = 0
    wrong_mime: int = 0
    ssrf_rejected: int = 0
    ambiguous_resource: int = 0
    hidden_player_possible: int = 0


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
    def _header_int(headers: dict[str, Any], name: str) -> int | None:
        try:
            value = int(str(headers.get(name, "")))
        except (TypeError, ValueError):
            return None
        return value if value >= 0 else None

    @classmethod
    def _response_evidence(cls, response: Any) -> tuple[int | None, int | None, str | None, str]:
        """Return bounded in-memory equivalence evidence, never diagnostic values."""
        headers = getattr(response, "headers", {}) or {}
        content_range = str(headers.get("content-range", ""))
        match = re.search(r"/([0-9]+)$", content_range)
        range_total = int(match.group(1)) if match else None
        etag = str(headers.get("etag", ""))
        etag_fingerprint = hashlib.sha256(etag.encode()).hexdigest() if etag else None
        path = urlsplit(str(getattr(response, "url", ""))).path
        path_fingerprint = hashlib.sha256(path.encode()).hexdigest()
        return range_total, cls._header_int(headers, "content-length"), etag_fingerprint, path_fingerprint

    @staticmethod
    def _candidate_groups(candidates: list[CachedMediaCandidate]) -> list[list[CachedMediaCandidate]]:
        """Group only target-window candidates with a stable resource fingerprint."""
        groups: dict[str, list[CachedMediaCandidate]] = {}
        for candidate in candidates:
            if not candidate.controlled_window:
                continue
            # A normalized path identifies a resource across CDN mirrors; page
            # window + main frame have already been required before reaching here.
            key = candidate.path_fingerprint
            groups.setdefault(key, []).append(candidate)
        return list(groups.values())

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
    def _referer_kind(referer: str | None, target_url: str) -> str:
        """Classify without retaining a Referer value in diagnostics or logs."""
        if referer is None:
            return "missing"
        try:
            referer_parts = urlsplit(referer)
            target_parts = urlsplit(target_url)
        except ValueError:
            return "external_origin"
        same_origin = (
            referer_parts.scheme == target_parts.scheme
            and referer_parts.hostname == target_parts.hostname
            and referer_parts.port == target_parts.port
        )
        if same_origin and referer_parts.path == target_parts.path:
            return "exact_target_path"
        if same_origin and referer_parts.path in {"", "/"}:
            return "douyin_origin_only"
        host = (referer_parts.hostname or "").lower().rstrip(".")
        if host == "douyin.com" or host.endswith(".douyin.com"):
            return "other_douyin_path"
        return "external_origin"

    @staticmethod
    def _count_referer_kind(counts: CandidateRejectionCounts, kind: str) -> None:
        setattr(counts, f"referer_{kind}", getattr(counts, f"referer_{kind}") + 1)

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

    async def _target_bound_mse_urls(
        self,
        page: Any,
        observed_candidates: list[CachedMediaCandidate],
        target_url: str,
        validator: Callable[[str], Awaitable[tuple[str, list[str]]]] | None,
    ) -> tuple[str, ...]:
        """Resolve only URLs actually appended to the unique visible blob player."""
        values = await page.evaluate(PRIMARY_VIDEO_MSE_URLS_SCRIPT)
        if not isinstance(values, list):
            return ()
        now = time.monotonic()
        observed = {
            candidate.url: candidate
            for candidate in observed_candidates
            if now - candidate.captured_at <= MAX_EARLY_MEDIA_AGE_SECONDS
        }
        bound: list[str] = []
        for value in values[:MAX_EARLY_MEDIA_CANDIDATES]:
            if not isinstance(value, str) or value in bound:
                continue
            candidate = observed.get(value)
            if candidate is None or not candidate.main_frame:
                continue
            if self._referer_kind(candidate.referer, target_url) not in {
                "exact_target_path",
                "douyin_origin_only",
            }:
                continue
            checked = await self._validate_direct_url(value, validator)
            if checked is not None:
                bound.append(checked)
        return tuple(bound)

    @staticmethod
    async def _wait_for_controlled_capture(page: Any, timeout_seconds: int) -> None:
        """Keep a brief real-browser window while fake adapters merely yield."""
        wait_for_timeout = getattr(page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            await wait_for_timeout(min(CONTROLLED_CAPTURE_SECONDS, timeout_seconds) * 1000)
        else:
            await asyncio.sleep(0)

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
        rejection_counts: CandidateRejectionCounts | None = None,
        equivalent_group_count: int = 0,
    ) -> PlayerDiagnostics:
        snapshot = snapshot or {}
        playback_media = playback_media or []
        rejection_counts = rejection_counts or CandidateRejectionCounts()
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
            before_target_verified=rejection_counts.before_target_verified,
            wrong_frame=rejection_counts.wrong_frame,
            referer_exact_target_path=rejection_counts.referer_exact_target_path,
            referer_douyin_origin_only=rejection_counts.referer_douyin_origin_only,
            referer_other_douyin_path=rejection_counts.referer_other_douyin_path,
            referer_external_origin=rejection_counts.referer_external_origin,
            referer_missing=rejection_counts.referer_missing,
            wrong_mime=rejection_counts.wrong_mime,
            ssrf_rejected=rejection_counts.ssrf_rejected,
            ambiguous_resource=rejection_counts.ambiguous_resource,
            hidden_player_possible=rejection_counts.hidden_player_possible,
            equivalent_group_count=equivalent_group_count,
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
        observed_candidates: list[CachedMediaCandidate] = []
        early_candidates: list[CachedMediaCandidate] = []
        controlled_candidates: list[CachedMediaCandidate] = []
        detail_tasks: list[asyncio.Task[TargetBoundMediaGroup | None]] = []
        target_groups: list[TargetBoundMediaGroup] = []
        rejection_counts = CandidateRejectionCounts()
        target_verified = False
        controlled_capture = False
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
                    await page.add_init_script(MEDIA_SOURCE_TRACE_INIT_SCRIPT)
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
                            is_target_detail = self._is_target_detail_request(request, target_id)
                            if is_target_detail:
                                if len(detail_tasks) < MAX_DETAIL_RESPONSE_TASKS:
                                    detail_tasks.append(
                                        asyncio.create_task(self._response_target_group(response, target_id))
                                    )
                                return
                            content_type = response.headers.get("content-type", "").lower()
                            url = response.url
                            resource_type = str(getattr(request, "resource_type", ""))
                            if not _is_media_response(content_type, resource_type):
                                rejection_counts.wrong_mime += 1
                                return
                            if not isinstance(url, str) or len(url) > MAX_EARLY_MEDIA_URL_LENGTH:
                                rejection_counts.ssrf_rejected += 1
                                return
                            main_frame = self._request_is_main_frame(request, page)
                            referer = self._request_referer(request)
                            referer_kind = self._referer_kind(referer, target_url)
                            self._count_referer_kind(rejection_counts, referer_kind)
                            if not main_frame:
                                rejection_counts.wrong_frame += 1
                                return
                            if referer_kind not in {"exact_target_path", "douyin_origin_only"}:
                                return
                            if (
                                controlled_capture
                                and len(controlled_candidates) >= MAX_EARLY_MEDIA_CANDIDATES
                            ):
                                rejection_counts.ambiguous_resource += 1
                                return
                            range_total, content_length, etag_fingerprint, path_fingerprint = (
                                self._response_evidence(response)
                            )
                            candidate = CachedMediaCandidate(
                                url=url,
                                content_type=content_type.split(";", 1)[0].lower(),
                                captured_at=time.monotonic(),
                                main_frame=main_frame,
                                referer=referer,
                                capture_phase=phase,
                                controlled_window=controlled_capture,
                                resource_type=resource_type,
                                range_total=range_total,
                                content_length=content_length,
                                etag_fingerprint=etag_fingerprint,
                                path_fingerprint=path_fingerprint,
                            )
                            observed_candidates.append(candidate)
                            if len(observed_candidates) > MAX_EARLY_MEDIA_CANDIDATES:
                                del observed_candidates[0]
                            playback_media[:] = [
                                (item.url, item.content_type) for item in observed_candidates
                            ]
                            if not target_verified:
                                rejection_counts.before_target_verified += 1
                                return
                            if controlled_capture:
                                controlled_candidates.append(candidate)
                            else:
                                early_candidates.append(candidate)
                            self._active_candidate_count = len(controlled_candidates)

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
                        target_verified = True
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
                        if int(before_start.get("visible_video_count", 0)) != 1:
                            complete_phase()
                            return CapturedMedia(
                                target_id=target_id,
                                media_url=None,
                                state="player_missing",
                                diagnostics=self._record_diagnostics(
                                    target_id=target_id,
                                    phase=phase,
                                    phase_ms=phase_ms,
                                    snapshot=before_start,
                                    rejection_counts=rejection_counts,
                                ),
                            )
                        groups: list[list[CachedMediaCandidate]] = []
                        selected_urls: tuple[str, ...] = ()
                        # The target page and exactly one visible main player now exist.
                        # Discard all prior anonymous traffic and create a narrow capture
                        # window that is attributable only to this player activation.
                        paused_hidden = await page.evaluate(PAUSE_HIDDEN_VIDEOS_SCRIPT)
                        if isinstance(paused_hidden, int) and paused_hidden > 0:
                            rejection_counts.hidden_player_possible += paused_hidden
                        mse_urls = await self._target_bound_mse_urls(
                            page,
                            observed_candidates,
                            target_url,
                            public_url_validator,
                        )
                        if mse_urls:
                            (
                                _direct_urls,
                                has_current_src,
                                has_src,
                                has_source_child,
                                has_blob_url,
                            ) = self._snapshot_urls(before_start)
                            move_to("media_capture")
                            complete_phase()
                            diagnostics = self._record_diagnostics(
                                target_id=target_id,
                                phase=phase,
                                phase_ms=phase_ms,
                                snapshot=before_start,
                                playback_media=playback_media,
                                has_current_src=has_current_src,
                                has_src=has_src,
                                has_source_child=has_source_child,
                                has_blob_url=has_blob_url,
                                target_bound_candidate_count=len(mse_urls),
                                unbound_candidate_count=len(early_candidates),
                                candidate_group_count=1,
                                candidate_source="main_player_mse",
                                rejection_counts=rejection_counts,
                                equivalent_group_count=1,
                            )
                            return CapturedMedia(
                                target_id=target_id,
                                media_url=mse_urls[0],
                                media_urls=mse_urls,
                                candidate_source="main_player_mse",
                                diagnostics=diagnostics,
                            )
                        early_candidates.clear()
                        controlled_candidates.clear()
                        controlled_capture = True
                        move_to("player_activation")
                        await asyncio.wait_for(
                            page.evaluate(PRIMARY_VIDEO_START_SCRIPT), timeout=player_timeout_seconds
                        )
                        move_to("media_capture")
                        await self._wait_for_controlled_capture(page, media_capture_timeout_seconds)
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
                            groups = self._candidate_groups(controlled_candidates)
                            if len(groups) == 1:
                                grouped_urls = await self._validated_group_urls(
                                    tuple(candidate.url for candidate in groups[0]), public_url_validator
                                )
                                if grouped_urls:
                                    media_url = grouped_urls[0]
                                    selected_urls = grouped_urls
                                    candidate_source = "main_player_network"
                            elif len(groups) > 1:
                                rejection_counts.ambiguous_resource += len(groups)
                        if media_url is None and has_blob_url:
                            # A single bounded seek can create a fresh Range request for
                            # an already-buffered MediaSource player. It never clicks any
                            # other UI and is not retried.
                            move_to("player_seek")
                            controlled_candidates.clear()
                            seek_result = await asyncio.wait_for(
                                page.evaluate(PRIMARY_VIDEO_SEEK_SCRIPT), timeout=player_timeout_seconds
                            )
                            if isinstance(seek_result, dict) and seek_result.get("buffered"):
                                move_to("player_reload")
                                await page.reload(
                                    wait_until="domcontentloaded",
                                    timeout=navigation_timeout_seconds * 1000,
                                )
                            await self._wait_for_controlled_capture(page, media_capture_timeout_seconds)
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
                            groups = self._candidate_groups(controlled_candidates)
                            if len(groups) == 1:
                                grouped_urls = await self._validated_group_urls(
                                    tuple(candidate.url for candidate in groups[0]), public_url_validator
                                )
                                if grouped_urls:
                                    media_url = grouped_urls[0]
                                    selected_urls = grouped_urls
                                    candidate_source = "main_player_network"
                            elif len(groups) > 1:
                                rejection_counts.ambiguous_resource += len(groups)
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
                            rejection_counts=rejection_counts,
                            equivalent_group_count=len(groups),
                        )
                        return CapturedMedia(
                            target_id=target_id,
                            media_url=media_url,
                            state="ok" if media_url else "media_missing",
                            diagnostics=diagnostics,
                            media_urls=selected_urls or ((media_url,) if media_url else ()),
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
            if page is not None:
                try:
                    await page.evaluate(CLEAR_MEDIA_SOURCE_TRACE_SCRIPT)
                except Exception:
                    # Page teardown can race with browser shutdown. The page is
                    # closed immediately below; never include browser text here.
                    logger.debug(
                        "douyin_session_trace outcome=already_closed phase=%s",
                        phase,
                    )
            observed_candidates.clear()
            early_candidates.clear()
            controlled_candidates.clear()
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
            content_fingerprints: set[str] = set()
            compare_group_content = (
                capture.candidate_source == "main_player_network" and len(media_urls) > 1
            )
            for candidate_url in media_urls:
                try:
                    logger.info("douyin_session_phase target_id=%s phase=media_verify", target_id)
                    async with asyncio.timeout(self.settings.douyin_session_media_verify_timeout_seconds):
                        public_headers = {**PUBLIC_MEDIA_HEADERS, "Referer": target_url}
                        candidate_probe = await self.http.probe_media(candidate_url, headers=public_headers)
                        stream = await self.http.open_stream(
                            candidate_url,
                            headers=public_headers,
                            range_header="bytes=0-4095",
                            media_kind="video",
                        )
                        try:
                            candidate_bytes = 0
                            content_sample = bytearray()
                            async for chunk in stream.response.aiter_bytes():
                                candidate_bytes += len(chunk)
                                if len(content_sample) < 4096:
                                    content_sample.extend(chunk[: 4096 - len(content_sample)])
                                if candidate_bytes >= 1024:
                                    break
                        finally:
                            await stream.close()
                    if candidate_bytes >= 1024:
                        content_fingerprints.add(hashlib.sha256(content_sample).hexdigest())
                        if verified_url is None:
                            verified_url, probe, bytes_read = candidate_url, candidate_probe, candidate_bytes
                        if not compare_group_content:
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
            if compare_group_content and len(content_fingerprints) > 1:
                self.last_internal_reason = "network_media_content_mismatch"
                raise session_media_not_found()
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
