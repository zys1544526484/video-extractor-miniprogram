from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..config import Settings
from ..schemas import ParserResultModel
from ..services.safe_http import SafeHttpClient


@dataclass
class ParseContext:
    settings: Settings
    http: SafeHttpClient
    requested_quality: str = "original"


class BaseParser(ABC):
    platform: str

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        raise NotImplementedError
