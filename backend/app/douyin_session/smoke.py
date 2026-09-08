from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from ..config import Settings, load_settings
from ..errors import AppError
from ..services.safe_http import SafeHttpClient
from .models import PlayerDiagnostics, normalise_douyin_redirect_target
from .worker import DouyinSessionWorker


@dataclass(frozen=True)
class SmokeOutput:
    outcome: str
    error_code: str
    work_id: str | None
    media_domain: str | None
    bytes_read: int | None
    elapsed_ms: int
    last_phase: str | None
    phase_elapsed_ms: int | None
    phases_ms: dict[str, int]
    final_page_path: str | None
    video_count: int | None
    visible_video_count: int | None
    has_current_src: bool | None
    has_src: bool | None
    has_source_child: bool | None
    has_blob_source: bool | None
    media_response_count: int | None
    media_mime_types: tuple[str, ...]
    media_domains: tuple[str, ...]
    target_bound_candidate_count: int | None
    unbound_candidate_count: int | None
    candidate_group_count: int | None
    candidate_source: str | None


logger = logging.getLogger(__name__)
SHORT_LINK_HOST = "v.douyin.com"


def _safe_origin(value: str) -> str | None:
    """Return only scheme + hostname, never a media route or credentials."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme in {"http", "https"} and parsed.hostname:
        return f"{parsed.scheme}://{parsed.hostname.lower()}"
    return None


def _safe_page_path(value: str, target_id: str | None) -> str | None:
    if target_id is None:
        return None
    expected = f"/video/{target_id}"
    return expected if value == expected else None


def _diagnostic_fields(diagnostics: PlayerDiagnostics | None, work_id: str | None) -> dict[str, object]:
    if diagnostics is None:
        return {
            "last_phase": None,
            "phase_elapsed_ms": None,
            "phases_ms": {},
            "final_page_path": None,
            "video_count": None,
            "visible_video_count": None,
            "has_current_src": None,
            "has_src": None,
            "has_source_child": None,
            "has_blob_source": None,
            "media_response_count": None,
            "media_mime_types": (),
            "media_domains": (),
            "target_bound_candidate_count": None,
            "unbound_candidate_count": None,
            "candidate_group_count": None,
            "candidate_source": None,
        }
    phases = {name: int(elapsed) for name, elapsed in diagnostics.phase_ms}
    return {
        "last_phase": diagnostics.last_phase,
        "phase_elapsed_ms": phases.get(diagnostics.last_phase),
        "phases_ms": phases,
        "final_page_path": _safe_page_path(diagnostics.page_route, work_id),
        "video_count": diagnostics.video_count,
        "visible_video_count": diagnostics.visible_video_count,
        "has_current_src": diagnostics.has_current_src,
        "has_src": diagnostics.has_src,
        "has_source_child": diagnostics.has_source_child,
        "has_blob_source": diagnostics.has_blob_url,
        "media_response_count": diagnostics.media_response_count,
        "media_mime_types": tuple(sorted(set(diagnostics.media_content_types))),
        "media_domains": tuple(
            sorted({origin for value in diagnostics.media_domains if (origin := _safe_origin(value))})
        ),
        "target_bound_candidate_count": diagnostics.target_bound_candidate_count,
        "unbound_candidate_count": diagnostics.unbound_candidate_count,
        "candidate_group_count": diagnostics.candidate_group_count,
        "candidate_source": diagnostics.candidate_source,
    }


def _resolve_failed() -> AppError:
    return AppError(
        "DOUYIN_RESOLVE_FAILED",
        "抖音短链接未能解析到具体作品，请稍后重试",
        retryable=True,
    )


def validate_douyin_redirect_hop(url: str) -> None:
    """Limit short-link resolution to known public Douyin route shapes."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise _resolve_failed() from error
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or port is not None
    ):
        raise _resolve_failed()
    if hostname == SHORT_LINK_HOST and parsed.path.strip("/"):
        return
    if normalise_douyin_redirect_target(url) is not None:
        return
    raise _resolve_failed()


def sanitise_redirect_hop(url: str) -> str:
    """Keep route evidence while never logging query strings or opaque tokens."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    scheme = parsed.scheme or "https"
    if hostname == SHORT_LINK_HOST:
        return f"{scheme}://{hostname}/<short-link>"
    normalised = normalise_douyin_redirect_target(url)
    if normalised is not None:
        return normalised[0]
    return f"{scheme}://{hostname}/<rejected>"


def build_safe_http(settings: Settings) -> SafeHttpClient:
    return SafeHttpClient(
        timeout_seconds=settings.http_timeout_seconds,
        max_redirects=settings.max_redirects,
        max_video_bytes=settings.max_video_bytes,
    )


async def resolve_smoke_target(url: str, http: SafeHttpClient) -> tuple[str, str]:
    """Follow a public short link through SafeHttpClient and require a work URL."""
    final_url, redirect_chain = await http.resolve_redirect_chain(
        url,
        max_bytes=256 * 1024,
        redirect_validator=validate_douyin_redirect_hop,
    )
    logger.info(
        "douyin_session_smoke_redirect_chain=%s",
        " -> ".join(sanitise_redirect_hop(hop) for hop in redirect_chain),
    )
    normalised = normalise_douyin_redirect_target(final_url)
    if normalised is None:
        raise _resolve_failed()
    return normalised


async def run_smoke(
    settings: Settings,
    url: str,
    *,
    http: SafeHttpClient | None = None,
    worker: DouyinSessionWorker | None = None,
) -> SmokeOutput:
    started = time.monotonic()
    client = http or build_safe_http(settings)
    work_id: str | None = None
    active_worker = worker or DouyinSessionWorker(settings=settings, http=client)
    try:
        target_url, work_id = await resolve_smoke_target(url, client)
        result = await active_worker.inspect(target_url)
        return SmokeOutput(
            outcome="success",
            error_code="NONE",
            work_id=work_id,
            media_domain=result.media_origin,
            bytes_read=result.bytes_read,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            **_diagnostic_fields(getattr(active_worker, "last_diagnostics", None), work_id),
        )
    except AppError as error:
        return SmokeOutput(
            outcome="failure",
            error_code=error.code,
            work_id=work_id,
            media_domain=None,
            bytes_read=None,
            elapsed_ms=int((time.monotonic() - started) * 1000),
            **_diagnostic_fields(getattr(active_worker, "last_diagnostics", None), work_id),
        )


async def async_main() -> int:
    url = os.environ.get("DOUYIN_SMOKE_URL", "").strip()
    if not url:
        print(
            json.dumps(
                asdict(
                    SmokeOutput(
                        "failure", "SMOKE_URL_REQUIRED", None, None, None, 0,
                        **_diagnostic_fields(None, None),
                    )
                )
            )
        )
        return 2
    output = await run_smoke(load_settings(), url)
    print(json.dumps(asdict(output), ensure_ascii=False))
    return 0 if output.outcome == "success" else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
