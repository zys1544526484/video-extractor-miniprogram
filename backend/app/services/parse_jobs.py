from __future__ import annotations

import asyncio
import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, select

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
        self.worker_task: asyncio.Task[None] | None = None
        self.current_job_id: str | None = None
        self.current_parse_task: asyncio.Task[None] | None = None

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
        self.worker_task = asyncio.create_task(self._worker(), name="parse-job-worker")

    async def stop(self) -> None:
        if self.current_parse_task and not self.current_parse_task.done():
            self.current_parse_task.cancel()
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass

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
        source_url = extract_first_http_url(text)
        platform = detect_platform(source_url)
        digest = self._idempotency_hash(user_id, idempotency_key)
        now = utc_now_naive()
        with self.database.session_factory() as session:
            existing = session.scalar(select(ParseJob).where(ParseJob.idempotency_hash == digest))
            if existing is not None:
                return await self._public(existing, user_id=user_id)
            active = session.scalar(
                select(ParseJob).where(
                    ParseJob.user_id == user_id,
                    ParseJob.status.in_(ACTIVE_STATUSES),
                )
            )
            if active is not None:
                raise AppError(
                    "PARSE_ALREADY_RUNNING",
                    "已有提取任务正在进行，请等待当前任务完成",
                    status_code=409,
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
                if self.current_job_id == job_id and self.current_parse_task:
                    self.current_parse_task.cancel()
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

    async def _public(self, job: ParseJob, *, user_id: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "stage": job.stage,
            "created_at": iso_utc(job.created_at),
            "updated_at": iso_utc(job.updated_at),
        }
        if job.status == "ready" and job.result_json:
            result = json.loads(job.result_json)
            media = await self.media_sessions.issue_token(result["session_id"], user_id=user_id)
            base = self.settings.public_base_url.rstrip("/")
            path = f"{base}/api/v1/media/{media.token}"
            result.update(
                preview_url=f"{path}/preview",
                download_url=f"{path}/download",
                expires_at=media.expires_at.isoformat().replace("+00:00", "Z"),
            )
            payload["result"] = result
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
            result = await self.parse_service.parse(
                source_url,
                user_id,
                quality,
                progress=lambda value, stage: self._progress(job_id, value, stage),
            )
            result_data = result.model_dump(mode="json")
            result_data.pop("preview_url", None)
            result_data.pop("download_url", None)
            result_data.pop("expires_at", None)
            with self.database.session_factory() as session:
                job = session.get(ParseJob, job_id)
                if job is None or job.status == "cancelled":
                    return
                job.status = "ready"
                job.progress = 100
                job.stage = "处理完成"
                job.result_json = json.dumps(result_data, ensure_ascii=False)
                job.updated_at = utc_now_naive()
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

    async def _worker(self) -> None:
        while True:
            job_id = await self.queue.get()
            self.current_job_id = job_id
            self.current_parse_task = asyncio.create_task(self._run_job(job_id))
            try:
                await self.current_parse_task
            finally:
                self.current_job_id = None
                self.current_parse_task = None
                self.queue.task_done()
