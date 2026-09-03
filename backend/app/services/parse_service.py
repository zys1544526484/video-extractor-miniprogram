from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..config import Settings
from ..errors import AppError
from ..parsers.base import ParseContext
from ..parsers.registry import ParserRegistry
from ..schemas import ParsePublicResult
from .media_sessions import MediaSessionStore
from .safe_http import SafeHttpClient
from .url_service import detect_platform, extract_first_http_url


class ParseService:
    def __init__(
        self,
        settings: Settings,
        http: SafeHttpClient,
        registry: ParserRegistry,
        media_sessions: MediaSessionStore,
    ) -> None:
        self.settings = settings
        self.http = http
        self.registry = registry
        self.media_sessions = media_sessions
        self.semaphore = asyncio.Semaphore(settings.global_parse_concurrency)
        self.active_users: set[int] = set()
        self.recent: dict[int, deque[datetime]] = defaultdict(deque)
        self.lock = asyncio.Lock()

    async def _enter(self, user_id: int) -> None:
        now = datetime.now(UTC)
        async with self.lock:
            attempts = self.recent[user_id]
            cutoff = now - timedelta(minutes=10)
            while attempts and attempts[0] < cutoff:
                attempts.popleft()
            if len(attempts) >= self.settings.user_parse_limit_per_10_minutes:
                raise AppError("RATE_LIMITED", "请求过于频繁，请稍后重试", status_code=429, retryable=True)
            if user_id in self.active_users:
                raise AppError("RATE_LIMITED", "已有提取任务正在进行", status_code=409, retryable=True)
            attempts.append(now)
            self.active_users.add(user_id)

    async def _leave(self, user_id: int) -> None:
        async with self.lock:
            self.active_users.discard(user_id)

    async def _materialize_remote(
        self,
        result,
        progress: Callable[[int, str], Awaitable[None]] | None,
    ) -> None:
        if not result.upstream_media_url:
            return
        directory = Path(
            await asyncio.to_thread(tempfile.mkdtemp, prefix="media_", dir=self.settings.temp_dir)
        )
        partial = directory / "video.mp4.part"
        final = directory / "video.mp4"
        opened = None
        try:
            opened = await self.http.open_stream(
                result.upstream_media_url,
                headers=result.required_headers,
            )
            declared = opened.response.headers.get("content-length")
            total = int(declared) if declared and declared.isdigit() else result.size_bytes
            transferred = 0
            with partial.open("wb") as output:
                async for chunk in opened.response.aiter_bytes():
                    transferred += len(chunk)
                    if transferred > self.settings.max_video_bytes:
                        raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")
                    output.write(chunk)
                    if progress and total:
                        percent = 45 + min(40, int(transferred * 40 / max(total, 1)))
                        await progress(percent, "下载公开媒体")
            partial.replace(final)
            result.temporary_file = str(final)
            result.upstream_media_url = None
            result.required_headers = {}
            result.size_bytes = transferred
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, directory, True)
            raise
        finally:
            if opened is not None:
                await opened.close()

    async def parse(
        self,
        text: str,
        user_id: int,
        quality: str = "original",
        progress: Callable[[int, str], Awaitable[None]] | None = None,
    ) -> ParsePublicResult:
        await self._enter(user_id)
        try:
            url = extract_first_http_url(text)
            platform = detect_platform(url)
            parser = self.registry.get(platform)
            context = ParseContext(
                settings=self.settings,
                http=self.http,
                requested_quality=quality,
            )
            if progress:
                await progress(10, "解析公开页面")
            async with self.semaphore:
                try:
                    async with asyncio.timeout(self.settings.parse_timeout_seconds):
                        result = await parser.parse(url, context)
                except TimeoutError as error:
                    raise AppError("PARSE_TIMEOUT", "提取超时，请稍后重试", retryable=True) from error

            if progress:
                await progress(45, "准备媒体文件")
            await self._materialize_remote(result, progress)

            if bool(result.upstream_media_url) == bool(result.temporary_file):
                raise AppError("PARSE_FAILED", "解析结果缺少唯一媒体来源")
            if result.upstream_media_url:
                await self.http.validate_url(result.upstream_media_url)
            if result.temporary_file:
                file = await asyncio.to_thread(Path(result.temporary_file).resolve)
                try:
                    file.relative_to(self.settings.temp_dir.resolve())
                except ValueError as error:
                    raise AppError("PARSE_FAILED", "临时媒体路径无效") from error
                if not file.is_file():
                    raise AppError("PARSE_FAILED", "临时媒体不存在")
                if file.stat().st_size > self.settings.max_video_bytes:
                    raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")

            session = await self.media_sessions.create(
                user_id=user_id,
                platform=result.platform,
                title=result.title,
                upstream_url=result.upstream_media_url,
                temporary_file=result.temporary_file,
                required_headers=result.required_headers,
                mime_type=result.mime_type,
                size_bytes=result.size_bytes,
            )
            if progress:
                await progress(95, "生成安全下载链接")
            base = self.settings.public_base_url.rstrip("/")
            path = f"{base}/api/v1/media/{session.token}"
            return ParsePublicResult(
                session_id=session.session_id,
                platform=result.platform,
                title=result.title,
                cover_url=result.cover_url,
                duration_seconds=result.duration_seconds,
                size_bytes=result.size_bytes,
                quality_label=result.quality_label,
                requested_quality=quality,
                preview_url=f"{path}/preview",
                download_url=f"{path}/download",
                expires_at=session.expires_at,
                watermark_status=result.watermark_status,
                notice="；".join(result.notices),
            )
        finally:
            await self._leave(user_id)
