from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from app.config import Settings
from app.errors import AppError
from app.services.media_processor import MediaProbe, MediaProcessor

FFMPEG_AVAILABLE = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def create_sample_video(file: Path, *, duration: int = 3) -> None:
    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size=1280x720:rate=30:duration={duration}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=1000:sample_rate=44100:duration={duration}",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "0",
        "-c:a",
        "aac",
        "-shortest",
        str(file),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode("utf-8", errors="replace")


def processor_settings(tmp_path: Path, *, max_video_bytes: int) -> Settings:
    return Settings(
        app_env="test",
        temp_dir=tmp_path,
        max_video_bytes=max_video_bytes,
        max_source_video_bytes=max(20 * 1024 * 1024, max_video_bytes * 3),
        min_free_disk_bytes=0,
        media_processing_timeout_seconds=60,
    )


def test_long_video_plan_prioritizes_a_complete_single_file(tmp_path: Path) -> None:
    processor = MediaProcessor(processor_settings(tmp_path, max_video_bytes=180 * 1024 * 1024))
    probe = MediaProbe(
        duration_seconds=43 * 60 + 34,
        width=1920,
        height=1080,
        video_codec="h264",
        audio_codec="aac",
        format_names=frozenset({"mp4"}),
        size_bytes=400 * 1024 * 1024,
    )

    plan = processor.transcode_plan(probe, "540p")

    assert plan.target_bytes <= 170 * 1024 * 1024
    assert plan.height <= 540
    assert plan.video_kbps > 0


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe are required")
@pytest.mark.asyncio
async def test_oversized_video_is_compressed_to_one_valid_mp4(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    await create_sample_video(source)
    assert source.stat().st_size > 450 * 1024
    processor = MediaProcessor(processor_settings(tmp_path, max_video_bytes=450 * 1024))
    updates: list[tuple[int, str]] = []

    result = await processor.process(
        source,
        "540p",
        "720P H.264 · 原视频",
        lambda value, stage: updates.append((value, stage)) or asyncio.sleep(0),
    )

    assert result.compressed is True
    assert result.file.name == "video.final.mp4"
    assert result.file.stat().st_size <= 450 * 1024
    assert result.probe.video_codec == "h264"
    assert result.probe.audio_codec == "aac"
    assert result.probe.is_mp4
    assert "自动压缩" in result.quality_label
    assert any("合成完整视频" in stage for _, stage in updates)


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg/ffprobe are required")
@pytest.mark.asyncio
async def test_processor_does_not_require_asyncio_subprocess_support(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "compatible.mp4"
    await create_sample_video(source, duration=1)

    async def forbidden_asyncio_subprocess(*args, **kwargs):
        raise AssertionError("uvicorn's Windows event loop may not implement subprocess_exec")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_asyncio_subprocess)
    processor = MediaProcessor(processor_settings(tmp_path, max_video_bytes=10 * 1024 * 1024))

    result = await processor.process(source, "original", None)

    assert result.probe.is_mp4
    assert result.probe.video_codec == "h264"


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffprobe is required")
@pytest.mark.asyncio
async def test_invalid_media_is_rejected(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not-a-video")
    processor = MediaProcessor(processor_settings(tmp_path, max_video_bytes=1024 * 1024))

    with pytest.raises(AppError) as captured:
        await processor.probe(invalid)

    assert captured.value.code == "MEDIA_FORMAT_UNSUPPORTED"
