from __future__ import annotations

from ..config import Settings
from ..errors import AppError
from .base import BaseParser
from .douyin import DouyinParser
from .generic import GenericParser
from .platforms import KuaishouParser, YtDlpPlatformParser
from .yt_dlp_adapter import YtDlpAdapter


class ParserRegistry:
    def __init__(self, settings: Settings) -> None:
        generic = GenericParser()
        adapter = YtDlpAdapter(settings)
        self.parsers: dict[str, BaseParser] = {
            "generic": generic,
            "bilibili": YtDlpPlatformParser("bilibili", adapter, download_media=True),
            "weibo": YtDlpPlatformParser("weibo", adapter),
            "xiaohongshu": YtDlpPlatformParser("xiaohongshu", adapter),
            "douyin": DouyinParser(adapter),
            "kuaishou": KuaishouParser(generic),
        }

    def get(self, platform: str) -> BaseParser:
        parser = self.parsers.get(platform)
        if parser is None:
            raise AppError("PLATFORM_UNSUPPORTED", "暂不支持该链接")
        return parser
