from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import AppError
from ..schemas import ParserResultModel

os.environ.setdefault("YTDLP_NO_PLUGINS", "1")

PLATFORM_LABELS = {
    "bilibili": "Bilibili",
    "weibo": "微博",
    "xiaohongshu": "小红书",
    "douyin": "抖音",
}


class YtDlpAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

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
    def _select_progressive_format(info: dict[str, Any]) -> dict[str, Any] | None:
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
        if candidates:
            return max(candidates, key=lambda item: (item.get("height") or 0, item.get("tbr") or 0))
        if info.get("url") and info.get("ext") == "mp4":
            return info
        return None

    def _extract_sync(self, url: str, platform: str, download_media: bool) -> ParserResultModel:
        try:
            import yt_dlp
            from yt_dlp.utils import DownloadError
        except ImportError as error:
            raise AppError("PLATFORM_CHANGED", "平台解析依赖未安装", retryable=True) from error

        temp_dir: Path | None = None
        options: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "cachedir": False,
            "socket_timeout": self.settings.http_timeout_seconds,
            "retries": 1,
            "fragment_retries": 1,
            "ignoreconfig": True,
            "max_filesize": self.settings.max_video_bytes,
            "restrictfilenames": True,
            "nopart": True,
            "overwrites": True,
        }

        if download_media:
            temp_dir = self.settings.temp_dir.resolve() / uuid.uuid4().hex
            temp_dir.mkdir(parents=True, exist_ok=False)
            options.update(
                {
                    "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
                    "merge_output_format": "mp4",
                    "paths": {"home": str(temp_dir)},
                    "outtmpl": {"default": "media.%(ext)s"},
                }
            )
        else:
            options["skip_download"] = True

        try:
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=download_media)
        except DownloadError as error:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)
            message = str(error).lower()
            if any(word in message for word in ("private", "login", "cookie", "member", "unavailable")):
                raise AppError("CONTENT_RESTRICTED", "该内容不可公开访问") from error
            raise AppError("PLATFORM_CHANGED", "当前平台解析异常，请稍后再试", retryable=True) from error
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
            if size > self.settings.max_video_bytes:
                if temp_dir is not None:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")
            temporary_file = str(file)
            quality = "已合并"
        else:
            selected = self._select_progressive_format(info)
            if selected is None:
                raise AppError("MEDIA_FORMAT_UNSUPPORTED", "没有可直接保存的公开视频格式")
            upstream_url = str(selected["url"])
            size = selected.get("filesize") or selected.get("filesize_approx")
            if size and int(size) > self.settings.max_video_bytes:
                raise AppError("MEDIA_TOO_LARGE", "视频超过 180MiB 限制")
            height = selected.get("height")
            quality = f"{height}P" if height else str(selected.get("format_note") or "公开资源")
            headers = {**headers, **self._safe_headers(selected)}

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
            notices=["仅处理无需登录即可公开访问的媒体"],
        )

    async def extract(self, url: str, platform: str, *, download_media: bool = False) -> ParserResultModel:
        return await asyncio.to_thread(self._extract_sync, url, platform, download_media)
