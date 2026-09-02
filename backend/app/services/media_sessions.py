from __future__ import annotations

import asyncio
import secrets
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time

from ..errors import AppError


@dataclass
class MediaSession:
    token: str
    session_id: str
    user_id: int
    platform: str
    title: str
    upstream_url: str | None
    temporary_file: Path | None
    required_headers: dict[str, str]
    mime_type: str
    size_bytes: int | None
    expires_at: datetime


class MediaSessionStore:
    def __init__(self, ttl_seconds: int, temp_root: Path, temp_file_ttl_seconds: int = 1800) -> None:
        self.ttl_seconds = ttl_seconds
        self.temp_file_ttl_seconds = temp_file_ttl_seconds
        self.temp_root = temp_root.resolve()
        self._sessions: dict[str, MediaSession] = {}
        self._lock = asyncio.Lock()

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
        token = secrets.token_urlsafe(32)
        session_id = f"ps_{secrets.token_hex(12)}"
        resolved_file = await asyncio.to_thread(Path(temporary_file).resolve) if temporary_file else None
        session = MediaSession(
            token=token,
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            title=title,
            upstream_url=upstream_url,
            temporary_file=resolved_file,
            required_headers=dict(required_headers),
            mime_type=mime_type,
            size_bytes=size_bytes,
            expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
        )
        async with self._lock:
            self._sessions[token] = session
        return session

    async def get(self, token: str) -> MediaSession:
        async with self._lock:
            session = self._sessions.get(token)
            if session is None or session.expires_at <= datetime.now(UTC):
                if session is not None:
                    self._sessions.pop(token, None)
                raise AppError("MEDIA_SESSION_EXPIRED", "结果已过期，请重新提取", status_code=410)
            return session

    def _remove_temp_file(self, session: MediaSession) -> None:
        file = session.temporary_file
        if file is None:
            return
        try:
            file.relative_to(self.temp_root)
        except ValueError:
            return
        if file.exists():
            parent = file.parent
            if parent == self.temp_root:
                file.unlink(missing_ok=True)
            else:
                shutil.rmtree(parent, ignore_errors=True)

    async def cleanup(self) -> int:
        now = datetime.now(UTC)
        expired: list[MediaSession] = []
        async with self._lock:
            for token, session in list(self._sessions.items()):
                if session.expires_at <= now:
                    expired.append(self._sessions.pop(token))
            active_directories = {
                session.temporary_file.parent
                for session in self._sessions.values()
                if session.temporary_file is not None
            }
        for session in expired:
            self._remove_temp_file(session)
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
                    else:
                        child.unlink(missing_ok=True)
                    orphaned += 1
        return len(expired) + orphaned
