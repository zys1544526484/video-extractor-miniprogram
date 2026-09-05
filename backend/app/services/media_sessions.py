from __future__ import annotations

import asyncio
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from time import time

from sqlalchemy import delete, select

from ..database import Database
from ..errors import AppError
from ..models import MediaAccessToken, MediaSessionRecord


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


ALLOWED_MEDIA_TYPES = {
    "video/mp4",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def normalize_media_type(value: str | None) -> str:
    media_type = (value or "video/mp4").split(";", 1)[0].strip().lower()
    if media_type == "video/*":
        media_type = "video/mp4"
    if media_type in {"image/jpg", "image/pjpeg"}:
        media_type = "image/jpeg"
    if media_type not in ALLOWED_MEDIA_TYPES:
        raise AppError("MEDIA_FORMAT_UNSUPPORTED", "媒体格式暂不支持")
    return media_type


@dataclass
class MediaSession:
    token: str
    session_id: str
    user_id: int
    platform: str
    title: str
    upstream_url: None
    temporary_file: Path
    required_headers: dict[str, str]
    mime_type: str
    size_bytes: int | None
    access_token_expires_at: datetime
    expires_at: datetime


class MediaSessionStore:
    def __init__(
        self,
        database: Database,
        ttl_seconds: int,
        temp_root: Path,
        temp_file_ttl_seconds: int = 10800,
        access_token_ttl_seconds: int = 900,
    ) -> None:
        self.database = database
        self.ttl_seconds = ttl_seconds
        self.temp_file_ttl_seconds = temp_file_ttl_seconds
        self.access_token_ttl_seconds = access_token_ttl_seconds
        self.temp_root = temp_root.resolve()
        self._lock = asyncio.Lock()

    @staticmethod
    def _token_hash(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    def _relative_file(self, value: str | Path) -> str:
        file = Path(value).resolve()
        try:
            relative = file.relative_to(self.temp_root)
        except ValueError as error:
            raise AppError("PARSE_FAILED", "临时媒体路径无效") from error
        if not file.is_file():
            raise AppError("PARSE_FAILED", "临时媒体不存在")
        return relative.as_posix()

    def _token_expires_at(self, session_expires_at: datetime, now: datetime) -> datetime:
        return min(session_expires_at, now + timedelta(seconds=self.access_token_ttl_seconds))

    def _session(
        self,
        record: MediaSessionRecord,
        token: str,
        access_token_expires_at: datetime,
    ) -> MediaSession:
        temporary_file = (self.temp_root / record.file_path).resolve()
        try:
            temporary_file.relative_to(self.temp_root)
        except ValueError as error:
            raise AppError("MEDIA_SESSION_EXPIRED", "结果已失效，请重新提取", status_code=410) from error
        if not temporary_file.is_file():
            raise AppError("MEDIA_SESSION_EXPIRED", "结果文件已清理，请重新提取", status_code=410)
        return MediaSession(
            token=token,
            session_id=record.session_id,
            user_id=record.user_id,
            platform=record.platform,
            title=record.title,
            upstream_url=None,
            temporary_file=temporary_file,
            required_headers={},
            mime_type=normalize_media_type(record.mime_type),
            size_bytes=record.size_bytes,
            access_token_expires_at=access_token_expires_at.replace(tzinfo=UTC),
            expires_at=record.expires_at.replace(tzinfo=UTC),
        )

    async def create(
        self,
        *,
        user_id: int,
        platform: str,
        title: str,
        upstream_url: str | None,
        temporary_file: str | None,
        required_headers: dict[str, str],
        mime_type: str,
        size_bytes: int | None,
    ) -> MediaSession:
        if upstream_url or not temporary_file:
            raise AppError("PARSE_FAILED", "媒体必须先安全落盘")
        normalized_mime = normalize_media_type(mime_type)
        relative_file = await asyncio.to_thread(self._relative_file, temporary_file)
        now = utc_now_naive()
        expires_at = now + timedelta(seconds=self.ttl_seconds)
        token_expires_at = self._token_expires_at(expires_at, now)
        session_id = f"ps_{secrets.token_hex(12)}"
        token = secrets.token_urlsafe(32)
        async with self._lock:
            with self.database.session_factory() as session:
                record = MediaSessionRecord(
                    session_id=session_id,
                    user_id=user_id,
                    platform=platform,
                    title=title,
                    file_path=relative_file,
                    mime_type=normalized_mime,
                    size_bytes=size_bytes,
                    created_at=now,
                    expires_at=expires_at,
                )
                session.add(record)
                session.flush()
                session.add(
                    MediaAccessToken(
                        token_hash=self._token_hash(token),
                        session_id=session_id,
                        expires_at=token_expires_at,
                    )
                )
                session.commit()
                return self._session(record, token, token_expires_at)

    async def available_until(self, session_id: str, *, user_id: int) -> datetime | None:
        now = utc_now_naive()
        async with self._lock:
            with self.database.session_factory() as session:
                record = session.get(MediaSessionRecord, session_id)
                if record is None or record.user_id != user_id or record.expires_at <= now:
                    return None
                try:
                    self._session(record, "", record.expires_at)
                except AppError:
                    return None
                return record.expires_at.replace(tzinfo=UTC)

    async def issue_token(self, session_id: str, *, user_id: int) -> MediaSession:
        token = secrets.token_urlsafe(32)
        now = utc_now_naive()
        async with self._lock:
            with self.database.session_factory() as session:
                record = session.get(MediaSessionRecord, session_id)
                if record is None or record.user_id != user_id or record.expires_at <= now:
                    raise AppError("MEDIA_SESSION_EXPIRED", "结果已过期，请重新提取", status_code=410)
                token_expires_at = self._token_expires_at(record.expires_at, now)
                session.add(
                    MediaAccessToken(
                        token_hash=self._token_hash(token),
                        session_id=session_id,
                        expires_at=token_expires_at,
                    )
                )
                session.commit()
                return self._session(record, token, token_expires_at)

    async def get(self, token: str) -> MediaSession:
        token_hash = self._token_hash(token)
        now = utc_now_naive()
        async with self._lock:
            with self.database.session_factory() as session:
                access = session.get(MediaAccessToken, token_hash)
                if access is None or access.expires_at <= now:
                    if access is not None:
                        session.delete(access)
                        session.commit()
                    raise AppError("MEDIA_SESSION_EXPIRED", "结果已过期，请重新提取", status_code=410)
                record = session.get(MediaSessionRecord, access.session_id)
                if record is None or record.expires_at <= now:
                    raise AppError("MEDIA_SESSION_EXPIRED", "结果已过期，请重新提取", status_code=410)
                return self._session(record, token, access.expires_at)

    def _remove_relative_file(self, relative_file: str) -> None:
        file = (self.temp_root / relative_file).resolve()
        try:
            file.relative_to(self.temp_root)
        except ValueError:
            return
        if not file.exists():
            return
        parent = file.parent
        if parent == self.temp_root:
            file.unlink(missing_ok=True)
        else:
            shutil.rmtree(parent, ignore_errors=True)

    @staticmethod
    def _is_media_file(path: Path) -> bool:
        """Return whether a root-level file is safe for orphan cleanup.

        ``TEMP_DIR`` can be colocated with SQLite in development.  Cleanup must
        never treat database files (or other operator-managed files) as media.
        Media sessions are constrained to the formats accepted by
        ``normalize_media_type``.
        """

        return path.suffix.lower() in {".mp4", ".jpg", ".jpeg", ".png", ".webp"}

    async def cleanup(self) -> int:
        now = utc_now_naive()
        expired_files: list[str] = []
        active_directories: set[Path] = set()
        async with self._lock:
            with self.database.session_factory() as session:
                session.execute(delete(MediaAccessToken).where(MediaAccessToken.expires_at <= now))
                expired = list(
                    session.scalars(select(MediaSessionRecord).where(MediaSessionRecord.expires_at <= now))
                )
                expired_files = [item.file_path for item in expired]
                for item in expired:
                    session.delete(item)
                active = list(session.scalars(select(MediaSessionRecord)))
                active_directories = {(self.temp_root / item.file_path).resolve().parent for item in active}
                session.commit()
        for relative_file in expired_files:
            await asyncio.to_thread(self._remove_relative_file, relative_file)

        orphaned = 0
        cutoff = time() - self.temp_file_ttl_seconds
        if self.temp_root.exists():
            for child in self.temp_root.iterdir():
                if child in active_directories:
                    continue
                try:
                    modified = child.stat().st_mtime
                except OSError:
                    continue
                if modified <= cutoff:
                    if child.is_dir():
                        shutil.rmtree(child, ignore_errors=True)
                    elif self._is_media_file(child):
                        child.unlink(missing_ok=True)
                    else:
                        continue
                    orphaned += 1
        return len(expired_files) + orphaned
