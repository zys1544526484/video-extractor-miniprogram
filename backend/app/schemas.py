from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WechatAuthRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class ParseRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    quality: Literal["original", "720p", "540p"] = "original"


class AdCompleteRequest(BaseModel):
    attempt_token: str = Field(min_length=32, max_length=128)


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ParserSourceModel(BaseModel):
    """A parser-provided media candidate; upstream URLs never leave the backend."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1, max_length=64)
    quality_label: str | None = None
    upstream_media_url: str | None = None
    temporary_file: str | None = None
    mime_type: str = "video/mp4"
    size_bytes: int | None = None
    required_headers: dict[str, str] = Field(default_factory=dict)
    notices: list[str] = Field(default_factory=list)


class ParserImageModel(BaseModel):
    """A parser-provided image candidate; it is materialized before exposure."""

    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(min_length=1, max_length=64)
    url: str | None = None
    temporary_file: str | None = None
    mime_type: str = "image/jpeg"
    size_bytes: int | None = None
    alt: str = ""
    required_headers: dict[str, str] = Field(default_factory=dict)


class ParserResultModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: str
    canonical_url: str
    title: str
    cover_url: str = ""
    media_type: Literal["video", "image"] = "video"
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
    sources: list[ParserSourceModel] = Field(default_factory=list)
    images: list[ParserImageModel] = Field(default_factory=list)
    share_text: str = ""


class ParsePublicResult(BaseModel):
    session_id: str
    platform: str
    title: str
    cover_url: str
    media_type: Literal["video", "image"] = "video"
    duration_seconds: float | None
    size_bytes: int | None
    quality_label: str | None
    requested_quality: Literal["original", "720p", "540p"]
    preview_url: str
    download_url: str
    expires_at: datetime
    media_expires_at: datetime
    watermark_status: str
    notice: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    share_text: str = ""
    selected_source_id: str | None = None
