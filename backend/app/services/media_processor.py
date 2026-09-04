from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import AppError

ProgressCallback = Callable[[int, str], Awaitable[None]]
QUALITY_HEIGHTS = {"original": None, "720p": 720, "540p": 540}
COMPATIBLE_VIDEO_CODECS = {"h264", "hevc"}


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    width: int
    height: int
    video_codec: str
    audio_codec: str | None
    format_names: frozenset[str]
    size_bytes: int

    @property
    def is_mp4(self) -> bool:
        return "mp4" in self.format_names or "mov" in self.format_names


@dataclass(frozen=True)
class MediaProcessResult:
    file: Path
    probe: MediaProbe
    quality_label: str
    compressed: bool
    notice: str | None = None


@dataclass(frozen=True)
class TranscodePlan:
    height: int
    video_kbps: int
    audio_kbps: int
    target_bytes: int


class MediaProcessor:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.processing_semaphore = asyncio.Semaphore(settings.media_processing_concurrency)

    @staticmethod
    def _tool(name: str) -> str:
        executable = shutil.which(name)
        if not executable:
            raise AppError("SERVICE_UNAVAILABLE", f"服务器缺少 {name}", retryable=True)
        return executable

    @staticmethod
    def _process_options() -> dict[str, int]:
        return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}

    async def probe(self, file: Path) -> MediaProbe:
        try:
            resolved = await asyncio.to_thread(file.resolve, strict=True)
        except OSError as error:
            raise AppError("PARSE_FAILED", "临时媒体不存在", retryable=True) from error
        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                [
                    self._tool("ffprobe"),
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    "-of",
                    "json",
                    str(resolved),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=30,
                **self._process_options(),
            )
        except subprocess.TimeoutExpired as error:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "视频格式检查超时") from error
        stdout = completed.stdout
        if completed.returncode != 0 or len(stdout) > 2 * 1024 * 1024:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "视频文件损坏或格式不受支持")
        try:
            payload: dict[str, Any] = json.loads(stdout.decode("utf-8"))
            streams = payload.get("streams") or []
            video = next(item for item in streams if item.get("codec_type") == "video")
            audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
            format_data = payload.get("format") or {}
            duration = float(format_data.get("duration") or video.get("duration") or 0)
            width = int(video.get("width") or 0)
            height = int(video.get("height") or 0)
            video_codec = str(video.get("codec_name") or "").lower()
            audio_codec = str(audio.get("codec_name") or "").lower() if audio else None
            format_names = frozenset(str(format_data.get("format_name") or "").lower().split(","))
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "视频缺少可用的视频流") from error
        if duration <= 0 or width <= 0 or height <= 0:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "无法读取视频时长或分辨率")
        return MediaProbe(
            duration_seconds=duration,
            width=width,
            height=height,
            video_codec=video_codec,
            audio_codec=audio_codec,
            format_names=format_names,
            size_bytes=resolved.stat().st_size,
        )

    def transcode_plan(
        self,
        probe: MediaProbe,
        requested_quality: str,
        *,
        budget_ratio: float = 0.90,
    ) -> TranscodePlan:
        target_bytes = min(
            int(self.settings.max_video_bytes * budget_ratio),
            170 * 1024 * 1024,
        )
        total_kbps = int(target_bytes * 8 / probe.duration_seconds / 1000)
        if total_kbps >= 200:
            audio_kbps = 48
        elif total_kbps >= 100:
            audio_kbps = 32
        else:
            audio_kbps = 24
        video_kbps = int((total_kbps - audio_kbps) * 0.94)
        if video_kbps < 24:
            raise AppError(
                "MEDIA_TOO_LARGE",
                "视频时长过长，无法压缩到微信可可靠保存的单文件范围",
            )

        if video_kbps >= 2500:
            bitrate_height = probe.height
        elif video_kbps >= 1200:
            bitrate_height = 720
        elif video_kbps >= 650:
            bitrate_height = 540
        elif video_kbps >= 300:
            bitrate_height = 360
        else:
            bitrate_height = 240
        requested_height = QUALITY_HEIGHTS.get(requested_quality)
        height = min(probe.height, bitrate_height, requested_height or probe.height)
        height = max(2, height - (height % 2))
        return TranscodePlan(height, video_kbps, audio_kbps, target_bytes)

    @staticmethod
    def _requires_transcode(probe: MediaProbe, requested_quality: str, max_bytes: int) -> bool:
        requested_height = QUALITY_HEIGHTS.get(requested_quality)
        return (
            probe.size_bytes > max_bytes
            or not probe.is_mp4
            or probe.video_codec not in COMPATIBLE_VIDEO_CODECS
            or (probe.audio_codec is not None and probe.audio_codec != "aac")
            or (requested_height is not None and probe.height > requested_height)
        )

    async def _transcode(
        self,
        source: Path,
        output: Path,
        probe: MediaProbe,
        plan: TranscodePlan,
        progress: ProgressCallback | None,
        *,
        progress_start: int = 60,
        progress_end: int = 93,
    ) -> None:
        await asyncio.to_thread(output.unlink, missing_ok=True)
        command = [
            self._tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            f"scale=-2:min(ih\\,{plan.height})",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-b:v",
            f"{plan.video_kbps}k",
            "-maxrate",
            f"{max(plan.video_kbps + 1, int(plan.video_kbps * 1.15))}k",
            "-bufsize",
            f"{max(64, plan.video_kbps * 2)}k",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            f"{plan.audio_kbps}k",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            "-progress",
            "pipe:1",
            "-nostats",
            str(output),
        ]
        process = await asyncio.to_thread(
            subprocess.Popen,
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **self._process_options(),
        )
        assert process.stdout is not None
        assert process.stderr is not None
        stderr_task = asyncio.create_task(asyncio.to_thread(process.stderr.read))
        try:
            async with asyncio.timeout(self.settings.media_processing_timeout_seconds):
                while True:
                    line = await asyncio.to_thread(process.stdout.readline)
                    if not line:
                        break
                    key, _, raw_value = line.decode("utf-8", errors="replace").partition("=")
                    if key in {"out_time_us", "out_time_ms"} and raw_value.strip().isdigit() and progress:
                        elapsed = int(raw_value.strip()) / 1_000_000
                        ratio = min(1.0, elapsed / probe.duration_seconds)
                        value = progress_start + int((progress_end - progress_start) * ratio)
                        await progress(value, "压缩并合成完整视频")
                await asyncio.to_thread(process.wait)
        except TimeoutError as error:
            process.kill()
            await asyncio.to_thread(process.wait)
            raise AppError("PARSE_TIMEOUT", "视频压缩超时，请改选较低画质", retryable=True) from error
        except asyncio.CancelledError:
            process.kill()
            await asyncio.to_thread(process.wait)
            raise
        finally:
            await stderr_task
        output_exists = await asyncio.to_thread(output.is_file)
        if process.returncode != 0 or not output_exists:
            await asyncio.to_thread(output.unlink, missing_ok=True)
            raise AppError("PARSE_FAILED", "视频合成失败", retryable=True)

    async def process(
        self,
        file: Path,
        requested_quality: str,
        quality_label: str | None,
        progress: ProgressCallback | None = None,
    ) -> MediaProcessResult:
        if progress and self.processing_semaphore.locked():
            await progress(56, "等待媒体处理资源")
        async with self.processing_semaphore:
            return await self._process(file, requested_quality, quality_label, progress)

    async def _process(
        self,
        file: Path,
        requested_quality: str,
        quality_label: str | None,
        progress: ProgressCallback | None = None,
    ) -> MediaProcessResult:
        if progress:
            await progress(57, "校验视频格式")
        original = await self.probe(file)
        if original.size_bytes > self.settings.max_source_video_bytes:
            raise AppError("MEDIA_TOO_LARGE", "源视频超过服务器可处理上限")
        if not self._requires_transcode(original, requested_quality, self.settings.max_video_bytes):
            codec = "H.265" if original.video_codec == "hevc" else "H.264"
            label = quality_label or f"{original.height}P {codec}"
            return MediaProcessResult(file, original, label, False)

        output = file.with_name("video.final.mp4")
        plan = self.transcode_plan(original, requested_quality)
        await self._transcode(file, output, original, plan, progress)
        final = await self.probe(output)
        if final.size_bytes > self.settings.max_video_bytes:
            retry_plan = self.transcode_plan(original, requested_quality, budget_ratio=0.72)
            await self._transcode(file, output, original, retry_plan, progress, progress_start=75)
            final = await self.probe(output)
        if final.size_bytes > self.settings.max_video_bytes:
            await asyncio.to_thread(output.unlink, missing_ok=True)
            raise AppError("MEDIA_TOO_LARGE", "压缩后仍超过微信可可靠保存的单文件范围")
        if file != output:
            await asyncio.to_thread(file.unlink, missing_ok=True)
        label = f"{final.height}P H.264（自动压缩，源 {original.height}P）"
        return MediaProcessResult(
            output,
            final,
            label,
            True,
            "源文件较大或编码不兼容，已自动压缩并合成为一个完整 MP4",
        )
