from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, func, select

from ..config import Settings
from ..database import Database
from ..errors import AppError
from ..models import ParseJob
from .media_sessions import MediaSessionStore
from .parse_service import ParseService
from .url_service import detect_platform, extract_first_http_url

ACTIVE_STATUSES = {"queued", "processing"}
TERMINAL_STATUSES = {"ready", "failed", "cancelled", "expired"}
logger = logging.getLogger("video_extractor.parse_jobs")


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def iso_utc(value: datetime) -> str:
    return value.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


class ParseJobService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        parse_service: ParseService,
        media_sessions: MediaSessionStore,
    ) -> None:
        self.settings = settings
        self.database = database
        self.parse_service = parse_service
        self.media_sessions = media_sessions
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker_tasks: list[asyncio.Task[None]] = []
        self.running_tasks: dict[str, asyncio.Task[None]] = {}
        self.submit_lock = asyncio.Lock()

    async def start(self) -> None:
        now = utc_now_naive()
        with self.database.session_factory() as session:
            recoverable = list(
                session.scalars(select(ParseJob).where(ParseJob.status.in_(ACTIVE_STATUSES)))
            )
            for job in recoverable:
                if job.expires_at <= now:
                    job.status = "expired"
                    job.stage = "任务已过期"
                else:
                    job.status = "queued"
                    job.progress = 0
                    job.stage = "服务重启后重新排队"
                job.updated_at = now
            session.commit()
        for job in recoverable:
            if job.status == "queued":
                await self.queue.put(job.job_id)
        self.worker_tasks = [
            asyncio.create_task(self._worker(index), name=f"parse-job-worker-{index + 1}")
            for index in range(self.settings.parse_worker_concurrency)
        ]

    async def stop(self) -> None:
        for task in list(self.running_tasks.values()):
            if not task.done():
                task.cancel()
        for task in self.worker_tasks:
            task.cancel()
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        self.worker_tasks = []
        self.running_tasks.clear()

    @staticmethod
    def _idempotency_hash(user_id: int, idempotency_key: str) -> str:
        return sha256(f"{user_id}:{idempotency_key}".encode()).hexdigest()

    async def create(
        self,
        *,
        user_id: int,
        text: str,
        quality: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        disk = await asyncio.to_thread(shutil.disk_usage, self.settings.temp_dir)
        if disk.free < self.settings.min_free_disk_bytes:
            raise AppError(
                "SERVICE_BUSY",
                "服务器临时空间不足，请稍后重试",
                status_code=503,
                retryable=True,
            )
        source_url = extract_first_http_url(text)
        platform = detect_platform(source_url)
        digest = self._idempotency_hash(user_id, idempotency_key)
        now = utc_now_naive()
        async with self.submit_lock:
            with self.database.session_factory() as session:
                existing = session.scalar(select(ParseJob).where(ParseJob.idempotency_hash == digest))
                if existing is not None:
                    return await self._public(existing, user_id=user_id)
                user_active = session.scalar(
                    select(func.count()).select_from(ParseJob).where(
                        ParseJob.user_id == user_id,
                        ParseJob.status.in_(ACTIVE_STATUSES),
                    )
                )
                if (user_active or 0) >= self.settings.max_active_parse_jobs_per_user:
                    raise AppError(
                        "PARSE_CONCURRENCY_LIMIT",
                        (
                            f"最多可同时提取 {self.settings.max_active_parse_jobs_per_user} 个视频，"
                            "请先等待一个完成"
                        ),
                        status_code=429,
                        retryable=True,
                    )
                global_active = session.scalar(
                    select(func.count()).select_from(ParseJob).where(
                        ParseJob.status.in_(ACTIVE_STATUSES)
                    )
                )
                if (global_active or 0) >= self.settings.max_queued_parse_jobs:
                    raise AppError(
                        "PARSE_QUEUE_FULL",
                        "当前提取队列已满，请稍后重试",
                        status_code=503,
                        retryable=True,
                    )
                job = ParseJob(
                    job_id=f"pj_{secrets.token_hex(16)}",
                    user_id=user_id,
                    idempotency_hash=digest,
                    source_url=source_url,
                    platform=platform,
                    requested_quality=quality,
                    status="queued",
                    progress=0,
                    stage="等待处理",
                    created_at=now,
                    updated_at=now,
                    expires_at=now + timedelta(seconds=self.settings.parse_job_ttl_seconds),
                )
                session.add(job)
                session.commit()
                session.refresh(job)
                payload = await self._public(job, user_id=user_id)
        await self.queue.put(job.job_id)
        return payload

    async def get(self, job_id: str, *, user_id: int) -> dict[str, Any]:
        with self.database.session_factory() as session:
            job = session.get(ParseJob, job_id)
            if job is None or job.user_id != user_id:
                raise AppError("JOB_NOT_FOUND", "提取任务不存在", status_code=404)
            if job.expires_at <= utc_now_naive() and job.status not in {"expired", "cancelled"}:
                job.status = "expired"
                job.stage = "任务已过期"
                job.updated_at = utc_now_naive()
                session.commit()
            return await self._public(job, user_id=user_id)

    async def list(self, *, user_id: int, limit: int = 20) -> list[dict[str, Any]]:
        now = utc_now_naive()
        with self.database.session_factory() as session:
            jobs = list(
                session.scalars(
                    select(ParseJob)
                    .where(ParseJob.user_id == user_id, ParseJob.expires_at > now)
                    .order_by(ParseJob.created_at.desc())
                    .limit(max(1, min(limit, 50)))
                )
            )
            return [await self._history_public(job, user_id=user_id) for job in jobs]

    async def cancel(self, job_id: str, *, user_id: int) -> dict[str, Any]:
        with self.database.session_factory() as session:
            job = session.get(ParseJob, job_id)
            if job is None or job.user_id != user_id:
                raise AppError("JOB_NOT_FOUND", "提取任务不存在", status_code=404)
            if job.status in {"queued", "processing"}:
                job.status = "cancelled"
                job.stage = "已取消"
                job.updated_at = utc_now_naive()
                session.commit()
                running = self.running_tasks.get(job_id)
                if running is not None:
                    running.cancel()
            return await self._public(job, user_id=user_id)

    async def cleanup(self) -> int:
        now = utc_now_naive()
        with self.database.session_factory() as session:
            result = session.execute(
                delete(ParseJob).where(
                    ParseJob.status.in_(TERMINAL_STATUSES),
                    ParseJob.expires_at <= now,
                )
            )
            session.commit()
            return result.rowcount or 0

    @staticmethod
    def _stored_result(result: dict[str, Any]) -> dict[str, Any]:
        """Strip all capability URLs before persisting a job result."""
        result.pop("preview_url", None)
        result.pop("download_url", None)
        result.pop("expires_at", None)
        result.pop("media_expires_at", None)
        for source in result.get("sources") or []:
            if isinstance(source, dict):
                source.pop("preview_url", None)
                source.pop("download_url", None)
                source.pop("expires_at", None)
                source.pop("media_expires_at", None)
        for image in result.get("images") or []:
            if isinstance(image, dict):
                image.pop("preview_url", None)
                image.pop("download_url", None)
                image.pop("expires_at", None)
                image.pop("media_expires_at", None)
        return result

    @staticmethod
    def _stored_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
        sources = [item for item in (result.get("sources") or []) if isinstance(item, dict)]
        if sources:
            return sources
        # Results written before source lists were introduced remain readable.
        if result.get("session_id"):
            return [
                {
                    "source_id": "source-1",
                    "session_id": result["session_id"],
                    "quality_label": result.get("quality_label"),
                    "size_bytes": result.get("size_bytes"),
                    "mime_type": "video/mp4",
                }
            ]
        return []

    @staticmethod
    def _safe_public_source(source: dict[str, Any], media: Any, base: str) -> dict[str, Any]:
        path = f"{base}/api/v1/media/{media.token}"
        return {
            "source_id": source.get("source_id") or "source-1",
            "quality_label": source.get("quality_label"),
            "size_bytes": source.get("size_bytes") or media.size_bytes,
            "mime_type": source.get("mime_type") or media.mime_type,
            "preview_url": f"{path}/preview",
            "download_url": f"{path}/download",
            "expires_at": media.access_token_expires_at.isoformat().replace("+00:00", "Z"),
            "media_expires_at": media.expires_at.isoformat().replace("+00:00", "Z"),
        }

    async def _public(self, job: ParseJob, *, user_id: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "platform": job.platform,
            "source_url": job.source_url,
            "requested_quality": job.requested_quality,
            "media_available": False,
            "created_at": iso_utc(job.created_at),
            "updated_at": iso_utc(job.updated_at),
        }
        if job.status == "ready" and job.result_json:
            result = json.loads(job.result_json)
            sources: list[dict[str, Any]] = []
            for source in self._stored_sources(result):
                try:
                    media = await self.media_sessions.issue_token(
                        str(source.get("session_id")), user_id=user_id
                    )
                except AppError as error:
                    if error.code != "MEDIA_SESSION_EXPIRED":
                        raise
                    continue
                sources.append(
                    self._safe_public_source(
                        source,
                        media,
                        self.settings.public_base_url.rstrip("/"),
                    )
                )
            if not sources:
                payload.update(
                    status="expired",
                    stage="文件已过期，请重新提取",
                    media_available=False,
                )
                return payload
            selected_id = result.get("selected_source_id")
            selected = next(
                (item for item in sources if item["source_id"] == selected_id),
                sources[0],
            )
            result["sources"] = sources
            result["selected_source_id"] = selected["source_id"]
            result["session_id"] = next(
                source.get("session_id")
                for source in self._stored_sources(json.loads(job.result_json))
                if source.get("source_id") == selected["source_id"]
            )
            result.update(
                size_bytes=selected["size_bytes"],
                quality_label=selected["quality_label"],
                preview_url=selected["preview_url"],
                download_url=selected["download_url"],
                expires_at=selected["expires_at"],
                media_expires_at=selected["media_expires_at"],
            )
            public_images: list[dict[str, Any]] = []
            for image in result.get("images") or []:
                if not isinstance(image, dict) or not image.get("session_id"):
                    continue
                try:
                    image_media = await self.media_sessions.issue_token(
                        str(image["session_id"]), user_id=user_id
                    )
                except AppError as error:
                    if error.code == "MEDIA_SESSION_EXPIRED":
                        continue
                    raise
                image_path = f"{self.settings.public_base_url.rstrip('/')}/api/v1/media/{image_media.token}"
                public_images.append(
                    {
                        "image_id": image.get("image_id") or f"image-{len(public_images) + 1}",
                        "mime_type": image.get("mime_type") or image_media.mime_type,
                        "size_bytes": image.get("size_bytes") or image_media.size_bytes,
                        "alt": image.get("alt") or result.get("title") or "",
                        "preview_url": f"{image_path}/preview",
                        "download_url": f"{image_path}/download",
                        "expires_at": image_media.access_token_expires_at.isoformat().replace("+00:00", "Z"),
                        "media_expires_at": image_media.expires_at.isoformat().replace("+00:00", "Z"),
                    }
                )
            result["images"] = public_images
            payload["media_available"] = True
            payload["result"] = result
        elif job.status == "failed":
            payload["error"] = {
                "code": job.error_code or "PARSE_FAILED",
                "message": job.error_message or "提取失败",
                "retryable": job.error_retryable,
            }
        return payload

    async def _history_public(self, job: ParseJob, *, user_id: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "platform": job.platform,
            "source_url": job.source_url,
            "requested_quality": job.requested_quality,
            "media_available": False,
            "created_at": iso_utc(job.created_at),
            "updated_at": iso_utc(job.updated_at),
        }
        if job.status == "ready" and job.result_json:
            result = json.loads(job.result_json)
            available_until_values = [
                value
                for value in await asyncio.gather(
                    *[
                        self.media_sessions.available_until(
                            str(source.get("session_id")), user_id=user_id
                        )
                        for source in self._stored_sources(result)
                    ]
                )
                if value is not None
            ]
            available_until = max(available_until_values) if available_until_values else None
            payload.update(
                status="ready" if available_until else "expired",
                stage="处理完成" if available_until else "文件已过期，请重新提取",
                media_available=bool(available_until),
                media_expires_at=(
                    available_until.isoformat().replace("+00:00", "Z")
                    if available_until
                    else None
                ),
                summary={
                    "title": result.get("title") or "未命名视频",
                    "cover_url": result.get("cover_url") or "",
                    "duration_seconds": result.get("duration_seconds"),
                    "size_bytes": result.get("size_bytes"),
                    "quality_label": result.get("quality_label"),
                },
            )
        elif job.status == "failed":
            payload["error"] = {
                "code": job.error_code or "PARSE_FAILED",
                "message": job.error_message or "提取失败",
                "retryable": job.error_retryable,
            }
        return payload

    async def _progress(self, job_id: str, progress: int, stage: str) -> None:
        with self.database.session_factory() as session:
            job = session.get(ParseJob, job_id)
            if job is None or job.status != "processing":
                return
            job.progress = max(job.progress, min(99, progress))
            job.stage = stage[:64]
            job.updated_at = utc_now_naive()
            session.commit()

    async def _heartbeat(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(1.5)
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is None or job.status != "processing":
                    return
                job.progress = min(90, max(1, job.progress + 1))
                if job.progress < 20:
                    job.stage = "解析公开页面"
                elif job.progress < 57:
                    job.stage = "分块下载并准备视频"
                else:
                    job.stage = "压缩并合成完整视频"
                job.updated_at = utc_now_naive()
                session.commit()

    async def _run_job(self, job_id: str) -> None:
        with self.database.session_factory() as session:
            job = session.get(ParseJob, job_id)
            if job is None or job.status != "queued":
                return
            job.status = "processing"
            job.progress = 1
            job.stage = "开始处理"
            job.updated_at = utc_now_naive()
            session.commit()
            user_id = job.user_id
            source_url = job.source_url
            quality = job.requested_quality
        try:
            heartbeat = asyncio.create_task(self._heartbeat(job_id))
            try:
                result = await self.parse_service.parse(
                    source_url,
                    user_id,
                    quality,
                    progress=lambda value, stage: self._progress(job_id, value, stage),
                )
            finally:
                heartbeat.cancel()
                try:
                    await heartbeat
                except asyncio.CancelledError:
                    pass
            result_data = self._stored_result(result.model_dump(mode="json"))
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is None or job.status == "cancelled":
                    return
                job.status = "ready"
                job.progress = 100
                job.stage = "处理完成"
                job.result_json = json.dumps(result_data, ensure_ascii=False)
                job.updated_at = utc_now_naive()
                job.expires_at = job.updated_at + timedelta(
                    seconds=self.settings.parse_job_ttl_seconds
                )
                session.commit()
        except asyncio.CancelledError:
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is not None and job.status != "cancelled":
                    job.status = "cancelled"
                    job.stage = "已取消"
                    job.updated_at = utc_now_naive()
                    session.commit()
        except AppError as error:
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is not None and job.status != "cancelled":
                    job.status = "failed"
                    job.progress = min(job.progress, 99)
                    job.stage = "处理失败"
                    job.error_code = error.code
                    job.error_message = error.message
                    job.error_retryable = error.retryable
                    job.updated_at = utc_now_naive()
                    session.commit()
        except Exception:
            logger.exception("parse_job_failed job_id=%s", job_id)
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is not None and job.status != "cancelled":
                    job.status = "failed"
                    job.stage = "处理失败"
                    job.error_code = "INTERNAL_ERROR"
                    job.error_message = "服务暂时不可用"
                    job.error_retryable = True
                    job.updated_at = utc_now_naive()
                    session.commit()

    async def _worker(self, worker_index: int) -> None:
        while True:
            job_id = await self.queue.get()
            task = asyncio.create_task(
                self._run_job(job_id), name=f"parse-job-{worker_index + 1}-{job_id}"
            )
            self.running_tasks[job_id] = task
            try:
                await task
            finally:
                self.running_tasks.pop(job_id, None)
                self.queue.task_done()
