from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import Settings
from app.database import Database
from app.schemas import ParserResultModel
from app.services.media_sessions import MediaSessionStore
from app.services.parse_service import ParseService


class ChunkResponse:
    def __init__(self, chunks: list[bytes], *, status_code: int, fail: bool = False) -> None:
        self.chunks = chunks
        self.status_code = status_code
        self.fail = fail
        self.headers = {"content-length": str(sum(len(chunk) for chunk in chunks))}

    async def aiter_bytes(self):
        for chunk in self.chunks:
            yield chunk
        if self.fail:
            raise ConnectionError("simulated interrupted transfer")


class OpenedChunkStream:
    def __init__(self, response: ChunkResponse) -> None:
        self.response = response
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class ResumableHttp:
    def __init__(self) -> None:
        self.ranges: list[str | None] = []

    async def open_stream(self, url, *, headers=None, range_header=None):
        self.ranges.append(range_header)
        if len(self.ranges) == 1:
            return OpenedChunkStream(ChunkResponse([b"abc"], status_code=200, fail=True))
        return OpenedChunkStream(ChunkResponse([b"def"], status_code=206))


@pytest.mark.asyncio
async def test_remote_download_resumes_from_last_complete_chunk(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        temp_dir=tmp_path / "media",
        max_video_bytes=1024,
        max_source_video_bytes=4096,
        min_free_disk_bytes=0,
    )
    settings.temp_dir.mkdir(parents=True)
    database = Database(f"sqlite:///{tmp_path / 'resume.db'}")
    database.create_schema()
    http = ResumableHttp()
    service = ParseService(
        settings,
        http,
        object(),
        MediaSessionStore(database, 60, settings.temp_dir),
    )
    result = ParserResultModel(
        platform="generic",
        canonical_url="https://example.com/watch",
        title="resumable",
        upstream_media_url="https://example.com/video.mp4",
        size_bytes=6,
    )

    await service._materialize_remote(result, None)

    assert http.ranges == [None, "bytes=3-"]
    assert await asyncio.to_thread(Path(result.temporary_file).read_bytes) == b"abcdef"
    assert result.upstream_media_url is None
    database.close()
