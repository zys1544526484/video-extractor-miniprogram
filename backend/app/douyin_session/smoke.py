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
from .models import normalise_douyin_redirect_target
from .worker import DouyinSessionWorker


@dataclass(frozen=True)
class SmokeOutput:
    outcome: str
    error_code: str
    work_id: str | None
    media_domain: str | None
    bytes_read: int | None
    elapsed_ms: int


logger = logging.getLogger(__name__)
SHORT_LINK_HOST = "v.douyin.com"


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
    try:
        target_url, work_id = await resolve_smoke_target(url, client)
        result = await (worker or DouyinSessionWorker(settings=settings, http=client)).inspect(target_url)
        return SmokeOutput(
            outcome="success",
            error_code="NONE",
            work_id=work_id,
            media_domain=result.media_origin,
            bytes_read=result.bytes_read,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except AppError as error:
        return SmokeOutput(
            outcome="failure",
            error_code=error.code,
            work_id=None,
            media_domain=None,
            bytes_read=None,
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )


async def async_main() -> int:
    url = os.environ.get("DOUYIN_SMOKE_URL", "").strip()
    if not url:
        print(json.dumps(asdict(SmokeOutput("failure", "SMOKE_URL_REQUIRED", None, None, None, 0))))
        return 2
    output = await run_smoke(load_settings(), url)
    print(json.dumps(asdict(output), ensure_ascii=False))
    return 0 if output.outcome == "success" else 1


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
