from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WechatAuthRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ParserResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    canonical_url: str
    title: str
    cover_url: str = ""
    media_type: Literal["video"] = "video"
    upstream_media_url: str | None = None
    temporary_file: str | None = None
    mime_type: str = "video/mp4"
    duration_seconds: float | None = None
    size_bytes: int | None = None
    quality_label: str | None = None
    watermark_status: Literal[
        "source_original", "platform_watermarked", "author_embedded", "unknown"
    ] = "unknown"
    required_headers: dict[str, str] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)


class ParsePublicResult(BaseModel):
    session_id: str
    platform: str
    title: str
    cover_url: str
    media_type: Literal["video"] = "video"
    duration_seconds: float | None
    size_bytes: int | None
    quality_label: str | None
    preview_url: str
    download_url: str
    expires_at: datetime
    watermark_status: str
    notice: str

