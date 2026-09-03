from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.errors import AppError
from app.parsers.base import BaseParser, ParseContext
from app.schemas import ParserResultModel
from app.services.media_sessions import MediaSessionStore
from app.services.parse_service import ParseService
from app.services.safe_http import SafeHttpClient


async def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


@pytest.mark.asyncio
async def test_safe_http_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow", request=request)

    client = SafeHttpClient(
        timeout_seconds=1,
        max_redirects=1,
        max_video_bytes=1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError) as captured:
        await client.get_text("https://example.com/watch")
    assert captured.value.code == "UPSTREAM_TIMEOUT"


@pytest.mark.asyncio
async def test_safe_http_rejects_declared_oversized_media() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "video/mp4", "content-length": "2048"},
        )

    client = SafeHttpClient(
        timeout_seconds=1,
        max_redirects=1,
        max_video_bytes=1024,
        resolver=public_resolver,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(AppError) as captured:
        await client.probe_media("https://example.com/video.mp4")
    assert captured.value.code == "MEDIA_TOO_LARGE"


@pytest.mark.asyncio
async def test_expired_media_token_and_orphan_cleanup(tmp_path: Path) -> None:
    store = MediaSessionStore(ttl_seconds=-1, temp_root=tmp_path, temp_file_ttl_seconds=1)
    media = await store.create(
        user_id=1,
        platform="generic",
        title="video",
        upstream_url="https://example.com/video.mp4",
        temporary_file=None,
        required_headers={},
        mime_type="video/mp4",
        size_bytes=10,
    )
    with pytest.raises(AppError) as captured:
        await store.get(media.token)
    assert captured.value.code == "MEDIA_SESSION_EXPIRED"

    orphan = tmp_path / "orphan" / "video.mp4"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"old")
    os.utime(orphan.parent, (0, 0))
    assert await store.cleanup() == 1
    assert not orphan.parent.exists()


class EscapingParser(BaseParser):
    platform = "generic"

    def can_handle(self, url: str) -> bool:
        return True

    async def parse(self, url: str, context: ParseContext) -> ParserResultModel:
        return ParserResultModel(
            platform="generic",
            canonical_url=url,
            title="escape",
            temporary_file=context.settings.database_url,
        )


class SingleRegistry:
    def get(self, platform: str) -> BaseParser:
        return EscapingParser()


class NoNetworkHttp:
    async def validate_url(self, url: str) -> None:
        return None


@pytest.mark.asyncio
async def test_parser_cannot_escape_temp_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    settings = Settings(
        app_env="test",
        database_url=str(outside),
        temp_dir=tmp_path / "allowed",
    )
    service = ParseService(
        settings,
        NoNetworkHttp(),
        SingleRegistry(),
        MediaSessionStore(60, settings.temp_dir),
    )
    with pytest.raises(AppError) as captured:
        await service.parse("https://example.com/watch", user_id=1)
    assert captured.value.code == "PARSE_FAILED"


def test_production_rejects_mock_and_insecure_base_url() -> None:
    with pytest.raises(ValidationError):
        Settings(app_env="production")


def test_production_rejects_public_placeholders() -> None:
    common = {
        "app_env": "production",
        "mock_wechat_auth": False,
        "public_base_url": "https://media-api.valid-domain.cn",
        "wechat_app_id": "wx1234567890abcdef",
        "wechat_app_secret": "0123456789abcdef0123456789abcdef",
    }
    with pytest.raises(ValidationError):
        Settings(**common, app_token_secret="replace-this-with-at-least-32-random-characters")
    with pytest.raises(ValidationError):
        Settings(
            **{**common, "public_base_url": "https://api.example.com"},
            app_token_secret="vF3_7sQ9-jL2_xM8-aC4_kR6-zT1_wN5",
        )


def test_production_accepts_non_placeholder_values() -> None:
    settings = Settings(
        app_env="production",
        mock_wechat_auth=False,
        dev_bypass_download_entitlement=False,
        public_base_url="https://media-api.valid-domain.cn",
        wechat_app_id="wx1234567890abcdef",
        wechat_app_secret="0123456789abcdef0123456789abcdef",
        app_token_secret="vF3_7sQ9-jL2_xM8-aC4_kR6-zT1_wN5",
    )
    assert settings.app_env == "production"
    assert settings.download_access_mode == "free"


def test_production_rejects_development_entitlement_bypass() -> None:
    with pytest.raises(ValidationError, match="DEV_BYPASS_DOWNLOAD_ENTITLEMENT"):
        Settings(
            app_env="production",
            mock_wechat_auth=False,
            dev_bypass_download_entitlement=True,
            public_base_url="https://media-api.valid-domain.cn",
            wechat_app_id="wx1234567890abcdef",
            wechat_app_secret="0123456789abcdef0123456789abcdef",
            app_token_secret="vF3_7sQ9-jL2_xM8-aC4_kR6-zT1_wN5",
        )
