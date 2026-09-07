from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..config import Settings
from ..errors import AppError
from ..schemas import ParserResultModel, ParserSourceModel

PLATFORM_LABELS = {
    "bilibili": "Bilibili",
    "weibo": "微博",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
}
WORKER_CWD = str(Path(__file__).resolve().parents[2])
MAX_WORKER_RESPONSE_BYTES = 1024 * 1024
MERGE_SIZE_HEADROOM_RATIO = 0.9
QUALITY_MAX_HEIGHT = {
    "original": None,
    "720p": 720,
    "540p": 540,
    "compatible": 1080,
}
QUALITY_LABELS = {
    "original": "原视频",
    "720p": "720P",
    "540p": "540P",
    "compatible": "兼容画质",
}


EXPLICIT_CONTENT_RESTRICTION_MARKERS = (
    "private video",
    "this video is private",
    "friends only",
    "only available to friends",
    "login required",
    "sign in to view",
    "must be logged in",
    "members only",
    "has been removed",
    "has been deleted",
    "video is deleted",
)


def reject_live_streams(info: dict[str, Any], *, incomplete: bool) -> str | None:
    if not incomplete and info.get("is_live"):
        return "live streams are not supported"
    return None


class YtDlpAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def classify_download_error(platform: str, message: str) -> AppError:
        """Map only explicit upstream access facts to a restricted-content error.

        Generic mentions of cookies or availability often indicate an extractor
        compatibility failure, not proof that the work is private.  In
        particular, a Douyin short URL that lost its work ID must remain
        retryable instead of being presented as a private work.
        """
        normalized = message.lower()
        if any(marker in normalized for marker in EXPLICIT_CONTENT_RESTRICTION_MARKERS):
            return AppError("CONTENT_RESTRICTED", "该内容不可公开访问")
        if platform == "douyin" and "unsupported url" in normalized:
            return AppError(
                "DOUYIN_RESOLVE_FAILED",
                "抖音短链接未能解析到具体作品，请稍后重试",
                retryable=True,
            )
        return AppError("PLATFORM_CHANGED", "当前平台解析异常，请稍后再试", retryable=True)

    @staticmethod
    def _first_entry(info: dict[str, Any]) -> dict[str, Any]:
        if info.get("_type") in {"playlist", "multi_video"}:
            entries = [entry for entry in info.get("entries") or [] if entry]
            if not entries:
                raise AppError("PARSE_FAILED", "解析器没有返回公开视频")
            return entries[0]
        return info

    @staticmethod
    def _safe_headers(info: dict[str, Any]) -> dict[str, str]:
        allowed = {"user-agent", "referer", "origin", "accept", "accept-language"}
        return {
            str(key): str(value)
            for key, value in (info.get("http_headers") or {}).items()
            if str(key).lower() in allowed and "\r" not in str(value) and "\n" not in str(value)
        }

    @staticmethod
    def _select_progressive_format(
        info: dict[str, Any],
        requested_quality: str = "original",
    ) -> dict[str, Any] | None:
        formats = info.get("formats") or []
        progressive = [
            item
            for item in formats
            if item.get("url")
            and item.get("vcodec") not in {None, "none"}
            and item.get("acodec") not in {None, "none"}
        ]
        mp4 = [item for item in progressive if item.get("ext") == "mp4"]
        candidates = mp4 or progressive
        max_height = QUALITY_MAX_HEIGHT.get(requested_quality)
        if max_height is not None and candidates:
            known_height = [item for item in candidates if int(item.get("height") or 0) > 0]
            bounded = [
                item for item in known_height if int(item.get("height") or 0) <= max_height
            ]
            if bounded:
                candidates = bounded
            elif known_height:
                return None
        if candidates:
            return max(candidates, key=lambda item: (item.get("height") or 0, item.get("tbr") or 0))
        if info.get("url") and info.get("ext") == "mp4":
            return info
        return None

    @classmethod
    def _select_progressive_sources(
        cls,
        info: dict[str, Any],
        requested_quality: str = "original",
        max_source_bytes: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to two distinct public progressive sources, best first."""
        formats = info.get("formats") or []
        candidates = [
            item
            for item in formats
            if item.get("url")
            and item.get("vcodec") not in {None, "none"}
            and item.get("acodec") not in {None, "none"}
            and str(item.get("protocol") or "").lower().startswith("http")
            and str(item.get("ext") or "").lower() == "mp4"
        ]
        if not candidates:
            selected = cls._select_progressive_format(info, requested_quality)
            return [selected] if selected else []
        max_height = QUALITY_MAX_HEIGHT.get(requested_quality)
        if max_height is not None:
            bounded = [item for item in candidates if int(item.get("height") or 0) <= max_height]
            if bounded:
                candidates = bounded
        candidates.sort(
            key=lambda item: (
                int(item.get("height") or 0),
                float(item.get("tbr") or item.get("vbr") or 0),
            ),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()
        seen_heights: set[int] = set()
        for item in candidates:
            item_url = str(item.get("url"))
            height = int(item.get("height") or 0)
            if item_url in seen_urls or height in seen_heights:
                continue
            size = cls._known_size(item)
            if max_source_bytes is not None and size and size > max_source_bytes:
                continue
            selected.append(item)
            seen_urls.add(item_url)
            seen_heights.add(height)
            if len(selected) == 2:
                break
        return selected

    @staticmethod
    def _known_size(item: dict[str, Any]) -> int | None:
        value = item.get("filesize") or item.get("filesize_approx")
        try:
            size = int(value)
        except (TypeError, ValueError):
            return None
        return size if size > 0 else None

    @staticmethod
    def _compatible_video_codec(item: dict[str, Any]) -> tuple[str, int] | None:
        codec = str(item.get("vcodec") or "").lower()
        if codec.startswith(("avc1", "h264")):
            return "H.264", 2
        if codec.startswith(("hev1", "hvc1", "hevc", "h265")):
            return "H.265", 1
        return None

    @classmethod
    def _select_bilibili_download_format(
        cls,
        info: dict[str, Any],
        max_video_bytes: int,
        requested_quality: str = "compatible",
    ) -> tuple[str, str, int]:
        """Select a size-bounded WeChat-compatible video + AAC DASH pair."""

        if requested_quality not in QUALITY_MAX_HEIGHT:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "不支持所选画质")

        formats = info.get("formats") or []

        def is_http(item: dict[str, Any]) -> bool:
            return str(item.get("protocol") or "").lower().startswith("http")

        videos = [
            item
            for item in formats
            if item.get("format_id")
            and is_http(item)
            and item.get("ext") == "mp4"
            and item.get("vcodec") not in {None, "none"}
            and item.get("acodec") in {None, "none"}
            and int(item.get("height") or 0) > 0
            and cls._compatible_video_codec(item) is not None
            and cls._known_size(item) is not None
        ]
        audios = [
            item
            for item in formats
            if item.get("format_id")
            and is_http(item)
            and item.get("ext") in {"m4a", "mp4"}
            and item.get("vcodec") in {None, "none"}
            and item.get("acodec") not in {None, "none"}
            and cls._known_size(item) is not None
        ]
        if not videos or not audios:
            raise AppError("MEDIA_FORMAT_UNSUPPORTED", "没有兼容微信播放的 MP4 格式")

        max_height = QUALITY_MAX_HEIGHT[requested_quality]
        eligible_videos = [
            item
            for item in videos
            if max_height is None or int(item.get("height") or 0) <= max_height
        ]
        if requested_quality == "compatible":
            eligible_videos = [
                item
                for item in eligible_videos
                if cls._compatible_video_codec(item) == ("H.264", 2)
            ]
        if not eligible_videos:
            raise AppError(
                "MEDIA_FORMAT_UNSUPPORTED",
                f"平台没有可用的 {QUALITY_LABELS[requested_quality]} 公开画质",
            )
        if requested_quality != "compatible":
            target_height = max(int(item.get("height") or 0) for item in eligible_videos)
            eligible_videos = [
                item for item in eligible_videos if int(item.get("height") or 0) == target_height
            ]

        size_budget = int(max_video_bytes * MERGE_SIZE_HEADROOM_RATIO)
        candidates: list[tuple[dict[str, Any], dict[str, Any], int]] = []
        for video in eligible_videos:
            video_size = cls._known_size(video)
            if video_size is None:
                continue
            for audio in audios:
                audio_size = cls._known_size(audio)
                if audio_size is None:
                    continue
                estimated_size = video_size + audio_size
                if estimated_size <= size_budget:
                    candidates.append((video, audio, estimated_size))

        if not candidates:
            raise AppError(
                "MEDIA_TOO_LARGE",
                f"所选{QUALITY_LABELS[requested_quality]}源文件超过服务器处理上限，请改选较低画质",
            )

        video, audio, estimated_size = max(
            candidates,
            key=lambda pair: (
                int(pair[0].get("height") or 0),
                (cls._compatible_video_codec(pair[0]) or ("", 0))[1],
                float(pair[0].get("tbr") or pair[0].get("vbr") or 0),
                float(pair[1].get("abr") or pair[1].get("tbr") or 0),
            ),
        )
        height = int(video.get("height") or 0)
        codec_label = (cls._compatible_video_codec(video) or ("MP4", 0))[0]
        quality = f"{height}P {codec_label}" if height else codec_label
        if requested_quality == "original":
            quality = f"{quality} · 原视频"
        elif requested_quality in {"720p", "540p"} and height != QUALITY_MAX_HEIGHT[requested_quality]:
            quality = f"{quality}（{QUALITY_LABELS[requested_quality]} 档）"
        return f"{video['format_id']}+{audio['format_id']}", quality, estimated_size

    def _extract_sync(
        self,
        url: str,
        platform: str,
        download_media: bool,
        requested_quality: str = "original",
    ) -> ParserResultModel:
        try:
            import yt_dlp
            from yt_dlp.utils import DownloadError
        except ImportError as error:
            raise AppError("PLATFORM_CHANGED", "平台解析依赖未安装", retryable=True) from error

        temp_dir: Path | None = None
        selected_quality: str | None = None
        options: dict[str, Any] = {
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": self.settings.http_timeout_seconds,
            "retries": 1,
            "fragment_retries": 1,
            "ignoreconfig": True,
            "max_filesize": self.settings.max_source_video_bytes,
            "restrictfilenames": True,
            "nopart": True,
            "overwrites": True,
            "proxy": "",
            "geo_bypass": False,
            "external_downloader": {"default": "native"},
            "hls_prefer_native": True,
            "match_filter": reject_live_streams,
            "break_on_reject": True,
        }

        try:
            if download_media:
                metadata_options = {**options, "skip_download": True}
                with yt_dlp.YoutubeDL(metadata_options) as downloader:
                    metadata = self._first_entry(downloader.extract_info(url, download=False) or {})
                selected_format, selected_quality, _ = self._select_bilibili_download_format(
                    metadata,
                    self.settings.max_source_video_bytes,
                    requested_quality,
                )
                temp_dir = self.settings.temp_dir.resolve() / uuid.uuid4().hex
                temp_dir.mkdir(parents=True, exist_ok=False)
                options.update(
                    {
                        "format": selected_format,
                        "merge_output_format": "mp4",
                        "paths": {"home": str(temp_dir)},
                        "outtmpl": {"default": "media.%(ext)s"},
                    }
                )
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(url, download=True)
            else:
                options["skip_download"] = True
                with yt_dlp.YoutubeDL(options) as downloader:
                    info = downloader.extract_info(url, download=False)
        except AppError:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise
        except DownloadError as error:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise self.classify_download_error(platform, str(error)) from error
        except Exception as error:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise AppError("PARSE_FAILED", "平台解析失败", retryable=True) from error

        info = self._first_entry(info or {})
        title = str(info.get("title") or "公开视频")[:200]
        duration = info.get("duration")
        cover = str(info.get("thumbnail") or "")
        headers = self._safe_headers(info)
        temporary_file = None
        upstream_url = None
        mime_type = "video/mp4"
        size = None
        quality = None
        source_models: list[ParserSourceModel] = []

        if download_media:
            files = [
                file
                for file in (temp_dir.iterdir() if temp_dir else [])
                if file.is_file() and file.suffix.lower() == ".mp4"
            ]
            if not files:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                raise AppError("PARSE_FAILED", "公开视频合并失败", retryable=True)
            file = max(files, key=lambda item: item.stat().st_size)
            size = file.stat().st_size
            if size > self.settings.max_source_video_bytes:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                raise AppError("MEDIA_TOO_LARGE", "源视频超过服务器可处理上限")
            temporary_file = str(file)
            quality = selected_quality or "已合并"
        else:
            selected_candidates = self._select_progressive_sources(
                info,
                requested_quality,
                self.settings.max_source_video_bytes,
            )
            selected = selected_candidates[0] if selected_candidates else None
            if selected is None:
                raise AppError("MEDIA_FORMAT_UNSUPPORTED", "没有可直接保存的公开视频格式")
            upstream_url = str(selected["url"])
            size = selected.get("filesize") or selected.get("filesize_approx")
            if size and int(size) > self.settings.max_source_video_bytes:
                raise AppError(
                    "MEDIA_TOO_LARGE",
                    "源视频超过服务器可处理上限",
                )
            height = selected.get("height")
            quality = f"{height}P" if height else str(selected.get("format_note") or "公开资源")
            headers = {**headers, **self._safe_headers(selected)}
            for index, candidate in enumerate(selected_candidates, start=1):
                candidate_height = candidate.get("height")
                source_models.append(
                    ParserSourceModel(
                        source_id=f"source-{index}",
                        quality_label=(
                            f"{candidate_height}P"
                            if candidate_height
                            else str(candidate.get("format_note") or "公开资源")
                        ),
                        upstream_media_url=str(candidate["url"]),
                        mime_type="video/mp4",
                        size_bytes=self._known_size(candidate),
                        required_headers={**headers, **self._safe_headers(candidate)},
                    )
                )

        notices = ["仅处理无需登录即可公开访问的媒体"]
        if quality and "H.265" in quality:
            notices.append("当前档位使用 H.265，请在目标 Android/iOS 真机验证预览与相册播放")

        return ParserResultModel(
            platform=PLATFORM_LABELS.get(platform, platform),
            canonical_url=str(info.get("webpage_url") or url),
            title=title,
            cover_url=cover,
            upstream_media_url=upstream_url,
            temporary_file=temporary_file,
            mime_type=mime_type,
            duration_seconds=float(duration) if duration is not None else None,
            size_bytes=int(size) if size else None,
            quality_label=quality,
            watermark_status="unknown",
            required_headers=headers,
            notices=notices,
            sources=source_models,
            share_text=f"{title}\n{str(info.get('webpage_url') or url)}",
        )

    async def extract(
        self,
        url: str,
        platform: str,
        *,
        download_media: bool = False,
        requested_quality: str = "original",
    ) -> ParserResultModel:
        try:
            literal_host = urlsplit(url).hostname
            literal_ip = ipaddress.ip_address(literal_host) if literal_host else None
        except ValueError:
            literal_ip = None
        if literal_ip is not None and not literal_ip.is_global:
            raise AppError("PLATFORM_CHANGED", "平台解析目标不是公网地址", retryable=True)
        payload = {
            "url": url,
            "platform": platform,
            "download_media": download_media,
            "requested_quality": requested_quality,
            "settings": {
                "temp_dir": str(self.settings.temp_dir.resolve()),
                "max_video_bytes": self.settings.max_video_bytes,
                "max_source_video_bytes": self.settings.max_source_video_bytes,
                "http_timeout_seconds": self.settings.http_timeout_seconds,
                "parse_timeout_seconds": self.settings.parse_timeout_seconds,
            },
        }
        environment = dict(os.environ)
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
            "PYTHONHOME",
            "PYTHONPATH",
        ):
            environment.pop(name, None)
        environment["YTDLP_NO_PLUGINS"] = "1"
        environment["PYTHONNOUSERSITE"] = "1"

        process_options: dict[str, Any] = {}
        if os.name == "nt":
            process_options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
        else:
            process_options["start_new_session"] = True

        process = await asyncio.to_thread(
            subprocess.Popen,
            [sys.executable, "-m", "app.parsers.yt_dlp_worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=WORKER_CWD,
            env=environment,
            **process_options,
        )
        try:
            async with asyncio.timeout(self.settings.parse_timeout_seconds):
                stdout, _ = await asyncio.to_thread(
                    process.communicate,
                    json.dumps(payload, ensure_ascii=False).encode("utf-8")
                )
        except TimeoutError as error:
            await self._terminate_process_tree(process)
            raise AppError("PARSE_TIMEOUT", "提取超时，请稍后重试", retryable=True) from error
        except asyncio.CancelledError:
            await self._terminate_process_tree(process)
            raise

        if process.returncode != 0:
            raise AppError("PLATFORM_CHANGED", "平台解析进程异常，请稍后再试", retryable=True)
        if len(stdout) > MAX_WORKER_RESPONSE_BYTES:
            raise AppError("PARSE_FAILED", "平台解析结果过大", retryable=True)
        try:
            message = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AppError("PARSE_FAILED", "平台解析结果无效", retryable=True) from error
        if not message.get("ok"):
            detail = message.get("error") or {}
            allowed_codes = {
                "CONTENT_RESTRICTED",
                "DOUYIN_RESOLVE_FAILED",
                "MEDIA_FORMAT_UNSUPPORTED",
                "MEDIA_TOO_LARGE",
                "PARSE_FAILED",
                "PLATFORM_CHANGED",
            }
            code = detail.get("code")
            if code not in allowed_codes:
                code = "PARSE_FAILED"
            raise AppError(
                code,
                str(detail.get("message") or "平台解析失败"),
                retryable=bool(detail.get("retryable")),
            )
        try:
            return ParserResultModel.model_validate(message["result"])
        except (KeyError, TypeError, ValueError) as error:
            raise AppError("PARSE_FAILED", "平台解析结果无效", retryable=True) from error

    @staticmethod
    async def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
        if process.returncode is not None:
            return
        try:
            if os.name == "nt":
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except (OSError, subprocess.SubprocessError):
            process.kill()
        try:
            async with asyncio.timeout(5):
                await asyncio.to_thread(process.wait)
        except TimeoutError:
            process.kill()
            await asyncio.to_thread(process.wait)
