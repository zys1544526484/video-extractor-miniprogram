from __future__ import annotations

from ..errors import AppError
from ..schemas import ParserResultModel
from .base import BaseParser, ParseContext
from .generic import GenericParser
from .yt_dlp_adapter import YtDlpAdapter


class YtDlpPlatformParser(BaseParser):
    def __init__(self, platform: str, adapter: YtDlpAdapter, *, download_media: bool = False) -> None:
        self.platform = platform
        self.adapter = adapter
        self.download_media = download_media

    def can_handle(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        await context.http.validate_url(url)
        return await self.adapter.extract(url, self.platform, download_media=self.download_media)


class KuaishouParser(BaseParser):
    platform = "kuaishou"

    def __init__(self, generic: GenericParser) -> None:
        self.generic = generic

    def can_handle(self, url: str) -> bool:
        return url.startswith(("http://", "https://"))

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        try:
            result = await self.generic.parse(url, context)
        except AppError as error:
            raise AppError(
                "PLATFORM_CHANGED",
                "快手公开页面当前受限，暂时无法稳定解析",
                retryable=True,
            ) from error
        result.platform = "快手"
        return result

