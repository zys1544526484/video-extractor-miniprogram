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
from ..schemas import ParsePublicResult, ParserImageModel, ParserResultModel, ParserSourceModel
from .media_processor import MediaProcessor
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
        media_processor: MediaProcessor | None = None,
    ) -> None:
        self.settings = settings
        self.http = http
        self.registry = registry
        self.media_sessions = media_sessions
        self.media_processor = media_processor or MediaProcessor(settings)
        self.semaphore = asyncio.Semaphore(settings.global_parse_concurrency)
        self.active_users: dict[int, int] = defaultdict(int)
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
            if self.active_users[user_id] >= self.settings.max_active_parse_jobs_per_user:
                raise AppError(
                    "PARSE_CONCURRENCY_LIMIT",
                    f"每位用户最多同时提取 {self.settings.max_active_parse_jobs_per_user} 个视频",
                    status_code=429,
                    retryable=True,
                )
            attempts.append(now)
            self.active_users[user_id] += 1

    async def _leave(self, user_id: int) -> None:
        async with self.lock:
            remaining = self.active_users.get(user_id, 0) - 1
            if remaining > 0:
                self.active_users[user_id] = remaining
            else:
                self.active_users.pop(user_id, None)

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
        try:
            transferred = 0
            total = result.size_bytes
            completed = False
            last_error: Exception | None = None
            for attempt in range(3):
                opened = None
                try:
                    opened = await self.http.open_stream(
                        result.upstream_media_url,
                        headers=result.required_headers,
                        range_header=f"bytes={transferred}-" if transferred else None,
                    )
                    declared = opened.response.headers.get("content-length")
                    if transferred and opened.response.status_code != 206:
                        transferred = 0
                        partial.unlink(missing_ok=True)
                    if total is None and declared and declared.isdigit():
                        total = transferred + int(declared)
                    if total and total > self.settings.max_source_video_bytes:
                        raise AppError("MEDIA_TOO_LARGE", "源视频超过服务器可处理上限")
                    mode = "ab" if transferred else "wb"
                    with partial.open(mode) as output:
                        async for chunk in opened.response.aiter_bytes():
                            transferred += len(chunk)
                            if transferred > self.settings.max_source_video_bytes:
                                raise AppError("MEDIA_TOO_LARGE", "源视频超过服务器可处理上限")
                            output.write(chunk)
                            if progress and total:
                                percent = 20 + min(34, int(transferred * 34 / max(total, 1)))
                                await progress(percent, "分块下载公开媒体")
                    completed = True
                    break
                except AppError:
                    raise
                except Exception as error:
                    last_error = error
                    if attempt == 2:
                        raise AppError(
                            "DOWNLOAD_FAILED",
                            "源视频分块下载失败，请稍后重试",
                            retryable=True,
                        ) from error
                finally:
                    if opened is not None:
                        await opened.close()
            if not completed:
                raise AppError("DOWNLOAD_FAILED", "源视频下载失败", retryable=True) from last_error
            partial.replace(final)
            result.temporary_file = str(final)
            result.upstream_media_url = None
            result.required_headers = {}
            result.size_bytes = transferred
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, directory, True)
            raise

    async def _materialize_image(
        self,
        image: ParserImageModel,
    ) -> None:
        """Download a parser image into the managed temp root before issuing a token."""
        if not image.url:
            return
        directory = Path(
            await asyncio.to_thread(tempfile.mkdtemp, prefix="image_", dir=self.settings.temp_dir)
        )
        partial = directory / "image.part"
        final = directory / "image.bin"
        try:
            opened = await self.http.open_stream(image.url, headers=image.required_headers)
            try:
                content_type = opened.response.headers.get("content-type", image.mime_type)
                content_type = content_type.split(";", 1)[0].strip().lower()
                if content_type == "image/jpg":
                    content_type = "image/jpeg"
                if not content_type.startswith("image/"):
                    raise AppError("MEDIA_FORMAT_UNSUPPORTED", "解析图片格式无效")
                declared = opened.response.headers.get("content-length")
                max_image_bytes = min(self.settings.max_source_video_bytes, 20 * 1024 * 1024)
                if declared and declared.isdigit() and int(declared) > max_image_bytes:
                    raise AppError("MEDIA_TOO_LARGE", "解析图片超过服务器处理上限")
                transferred = 0
                with partial.open("wb") as output:
                    async for chunk in opened.response.aiter_bytes():
                        transferred += len(chunk)
                        if transferred > max_image_bytes:
                            raise AppError("MEDIA_TOO_LARGE", "解析图片超过服务器处理上限")
                        output.write(chunk)
                partial.replace(final)
                image.temporary_file = str(final)
                image.url = None
                image.required_headers = {}
                image.mime_type = content_type
                image.size_bytes = transferred
            finally:
                await opened.close()
        except BaseException:
            await asyncio.to_thread(shutil.rmtree, directory, True)
            raise

    def _source_candidates(self, result: ParserResultModel) -> list[ParserSourceModel]:
        # An image-only work has no video sources.  Do not synthesize a video
        # source from its primary image or from the cover field.
        if result.media_type == "image":
            return []
        if result.sources:
            return list(result.sources[:4])
        return [
            ParserSourceModel(
                source_id="source-1",
                quality_label=result.quality_label,
                upstream_media_url=result.upstream_media_url,
                temporary_file=result.temporary_file,
                mime_type=result.mime_type,
                size_bytes=result.size_bytes,
                required_headers=result.required_headers,
                notices=result.notices,
            )
        ]

    def _validate_local_file(self, value: str | None) -> Path:
        if not value:
            raise AppError("PARSE_FAILED", "临时媒体不存在")
        file = Path(value).resolve()
        try:
            file.relative_to(self.settings.temp_dir.resolve())
        except ValueError as error:
            raise AppError("PARSE_FAILED", "临时媒体路径无效") from error
        if not file.is_file():
            raise AppError("PARSE_FAILED", "临时媒体不存在")
        if file.stat().st_size > self.settings.max_source_video_bytes:
            raise AppError("MEDIA_TOO_LARGE", "源视频超过服务器可处理上限")
        return file

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
                await progress(20, "准备媒体文件")
            sources: list[dict[str, object]] = []
            for index, source in enumerate(self._source_candidates(result), start=1):
                if bool(source.upstream_media_url) == bool(source.temporary_file):
                    if not source.upstream_media_url and not source.temporary_file:
                        continue
                    raise AppError("PARSE_FAILED", "解析结果缺少唯一媒体来源")
                await self._materialize_remote(source, progress)
                if source.upstream_media_url:
                    await self.http.validate_url(source.upstream_media_url)
                if source.temporary_file:
                    file = self._validate_local_file(source.temporary_file)
                    processed = await self.media_processor.process(
                        file,
                        quality,
                        source.quality_label or result.quality_label,
                        progress,
                    )
                    source.temporary_file = str(processed.file)
                    source.size_bytes = processed.probe.size_bytes
                    source.mime_type = "video/mp4"
                    if result.duration_seconds is None:
                        result.duration_seconds = processed.probe.duration_seconds
                    source.quality_label = processed.quality_label
                    if processed.notice:
                        source.notices.append(processed.notice)
                session = await self.media_sessions.create(
                    user_id=user_id,
                    platform=result.platform,
                    title=result.title,
                    upstream_url=source.upstream_media_url,
                    temporary_file=source.temporary_file,
                    required_headers=source.required_headers,
                    mime_type=source.mime_type,
                    size_bytes=source.size_bytes,
                )
                sources.append(
                    {
                        "source_id": source.source_id or f"source-{index}",
                        "session_id": session.session_id,
                        "quality_label": source.quality_label,
                        "size_bytes": source.size_bytes,
                        "mime_type": source.mime_type,
                        "expires_at": session.access_token_expires_at,
                        "media_expires_at": session.expires_at,
                    }
                )
                if len(sources) >= 4:
                    break
            images: list[dict[str, object]] = []
            image_candidates = list(result.images)
            for image in image_candidates[:8]:
                try:
                    if bool(image.url) == bool(image.temporary_file):
                        if not image.url and not image.temporary_file:
                            continue
                        raise AppError("PARSE_FAILED", "解析图片缺少唯一来源")
                    await self._materialize_image(image)
                    file = self._validate_local_file(image.temporary_file)
                    image_session = await self.media_sessions.create(
                        user_id=user_id,
                        platform=result.platform,
                        title=image.alt or result.title,
                        upstream_url=None,
                        temporary_file=str(file),
                        required_headers={},
                        mime_type=image.mime_type,
                        size_bytes=image.size_bytes,
                    )
                    images.append(
                        {
                            "image_id": image.image_id,
                            "session_id": image_session.session_id,
                            "mime_type": image.mime_type,
                            "size_bytes": image.size_bytes,
                            "alt": image.alt,
                            "expires_at": image_session.access_token_expires_at,
                            "media_expires_at": image_session.expires_at,
                        }
                    )
                except AppError:
                    # A cover/image is optional; a failed image must not discard a valid video.
                    continue

            if not sources and result.media_type != "image":
                raise AppError("PARSE_FAILED", "解析结果没有可用视频源")

            # Pure image works use the first materialized image as the primary
            # capability.  The images list remains the source of truth for the
            # image tab; no cover is fabricated when the parser did not provide
            # a real image candidate.
            if not sources and result.media_type == "image":
                if not images:
                    raise AppError("PLATFORM_UNSUPPORTED", "未找到可安全保存的公开图片")
                if progress:
                    await progress(95, "生成安全图片链接")
                base = self.settings.public_base_url.rstrip("/")
                primary_image = images[0]
                primary_session = await self.media_sessions.issue_token(
                    str(primary_image["session_id"]), user_id=user_id
                )
                primary_path = f"{base}/api/v1/media/{primary_session.token}"
                return ParsePublicResult(
                    session_id=primary_session.session_id,
                    platform=result.platform,
                    title=result.title,
                    cover_url=result.cover_url,
                    media_type="image",
                    duration_seconds=None,
                    size_bytes=primary_image.get("size_bytes"),
                    quality_label=None,
                    requested_quality=quality,
                    preview_url=f"{primary_path}/preview",
                    download_url=f"{primary_path}/download",
                    expires_at=primary_session.access_token_expires_at,
                    media_expires_at=primary_session.expires_at,
                    watermark_status=result.watermark_status,
                    notice="；".join(result.notices),
                    sources=[],
                    images=images,
                    share_text=result.share_text or f"{result.title}\n{result.canonical_url}",
                    selected_source_id=None,
                )

            primary = sources[0]
            if progress:
                await progress(95, "生成安全下载链接")
            base = self.settings.public_base_url.rstrip("/")
            primary_session = await self.media_sessions.issue_token(
                str(primary["session_id"]), user_id=user_id
            )
            primary_path = f"{base}/api/v1/media/{primary_session.token}"
            return ParsePublicResult(
                session_id=primary_session.session_id,
                platform=result.platform,
                title=result.title,
                cover_url=result.cover_url,
                duration_seconds=result.duration_seconds,
                size_bytes=primary.get("size_bytes") or result.size_bytes,
                quality_label=primary.get("quality_label") or result.quality_label,
                requested_quality=quality,
                preview_url=f"{primary_path}/preview",
                download_url=f"{primary_path}/download",
                expires_at=primary_session.access_token_expires_at,
                media_expires_at=primary_session.expires_at,
                watermark_status=result.watermark_status,
                notice="；".join(result.notices),
                sources=sources,
                images=images,
                share_text=result.share_text or f"{result.title}\n{result.canonical_url}",
                selected_source_id=str(primary["source_id"]),
            )
        finally:
            await self._leave(user_id)
