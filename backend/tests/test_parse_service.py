from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.database import Database
from app.models import User
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


class FastPathHttp:
    def __init__(self) -> None:
        self.probe_calls: list[str] = []
        self.stream_calls = 0

    async def probe_media(self, url, *, headers=None):
        self.probe_calls.append(url)
        return {
            "url": "https://cdn.example/video.mp4",
            "content_type": "video/mp4",
            "size": 123,
        }

    async def validate_url(self, url):
        return url, []

    async def open_stream(self, *args, **kwargs):
        self.stream_calls += 1
        raise AssertionError("fast path must not open a download stream during parsing")


class FastPathParser:
    async def parse(self, url, context):
        return ParserResultModel(
            platform="generic",
            canonical_url=url,
            title="fast path",
            upstream_media_url="https://origin.example/video.mp4",
            mime_type="video/mp4",
            size_bytes=123,
            quality_label="720P",
        )


class FastPathRegistry:
    def get(self, platform):
        return FastPathParser()


class FallbackParser:
    async def parse(self, url, context):
        return ParserResultModel(
            platform="generic",
            canonical_url=url,
            title="fallback",
            upstream_media_url="http://origin.example/video.webm",
            mime_type="video/webm",
            size_bytes=6,
            quality_label="公开资源",
        )


class FallbackRegistry:
    def get(self, platform):
        return FallbackParser()


class PassthroughProcessor:
    async def process(self, file, requested_quality, quality_label, progress=None):
        if progress:
            await progress(70, "回退处理")
        size_bytes = await asyncio.to_thread(lambda: Path(file).stat().st_size)
        return SimpleNamespace(
            file=Path(file),
            probe=SimpleNamespace(size_bytes=size_bytes, duration_seconds=1),
            quality_label=quality_label or "公开资源",
            notice=None,
        )


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


@pytest.mark.asyncio
async def test_parse_uses_metadata_only_fast_path_for_bounded_https_mp4(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        temp_dir=tmp_path / "media",
        max_video_bytes=1024,
        max_source_video_bytes=4096,
        min_free_disk_bytes=0,
    )
    settings.temp_dir.mkdir(parents=True)
    database = Database(f"sqlite:///{tmp_path / 'fast.db'}")
    database.create_schema()
    with database.session_factory() as session:
        session.add(User(openid="fast-path-user"))
        session.commit()
    http = FastPathHttp()
    service = ParseService(
        settings,
        http,
        FastPathRegistry(),
        MediaSessionStore(database, 60, settings.temp_dir),
    )

    result = await service.parse("https://example.com/watch", user_id=1)

    assert result.download_url.endswith("/download")
    assert http.probe_calls == ["https://origin.example/video.mp4"]
    assert http.stream_calls == 0
    refreshed = await service.media_sessions.issue_token(result.session_id, user_id=1)
    stored = await service.media_sessions.get(refreshed.token)
    assert stored.temporary_file is None
    assert stored.upstream_url == "https://cdn.example/video.mp4"
    database.close()


@pytest.mark.asyncio
async def test_parse_falls_back_to_materialization_for_non_https_or_non_mp4(tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        temp_dir=tmp_path / "media",
        max_video_bytes=1024,
        max_source_video_bytes=4096,
        min_free_disk_bytes=0,
    )
    settings.temp_dir.mkdir(parents=True)
    database = Database(f"sqlite:///{tmp_path / 'fallback.db'}")
    database.create_schema()
    with database.session_factory() as session:
        session.add(User(openid="fallback-user"))
        session.commit()
    http = ResumableHttp()
    service = ParseService(
        settings,
        http,
        FallbackRegistry(),
        MediaSessionStore(database, 60, settings.temp_dir),
        media_processor=PassthroughProcessor(),
    )

    result = await service.parse("https://example.com/watch", user_id=1)

    assert result.download_url.endswith("/download")
    assert http.ranges == [None, "bytes=3-"]
    refreshed = await service.media_sessions.issue_token(result.session_id, user_id=1)
    stored = await service.media_sessions.get(refreshed.token)
    assert stored.temporary_file is not None
    assert stored.upstream_url is None
    database.close()
