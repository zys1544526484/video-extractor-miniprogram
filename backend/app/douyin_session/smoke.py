from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import asdict, dataclass

from ..config import Settings, load_settings
from ..errors import AppError
from ..services.safe_http import SafeHttpClient
from .models import target_id_from_url
from .worker import DouyinSessionWorker


@dataclass(frozen=True)
class SmokeOutput:
    outcome: str
    error_code: str
    work_id: str | None
    media_domain: str | None
    bytes_read: int | None
    elapsed_ms: int


def build_safe_http(settings: Settings) -> SafeHttpClient:
    return SafeHttpClient(
        timeout_seconds=settings.http_timeout_seconds,
        max_redirects=settings.max_redirects,
        max_video_bytes=settings.max_video_bytes,
    )


async def resolve_smoke_target(url: str, http: SafeHttpClient) -> tuple[str, str]:
    """Follow a public short link through SafeHttpClient and require a work URL."""
    await http.validate_url(url)
    final_url, _document, _headers = await http.get_text(url, max_bytes=256 * 1024)
    work_id = target_id_from_url(final_url)
    if work_id is None:
        raise AppError(
            "DOUYIN_RESOLVE_FAILED",
            "抖音短链接未能解析到具体作品，请稍后重试",
            retryable=True,
        )
    return f"https://www.douyin.com/video/{work_id}", work_id


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
