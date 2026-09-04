from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.database import Database
from app.errors import AppError
from app.models import MediaAccessToken, User
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
    database = Database(f"sqlite:///{tmp_path / 'sessions.db'}")
    database.create_schema()
    with database.session_factory() as session:
        session.add(User(openid="media-test-user"))
        session.commit()
    stored = tmp_path / "stored" / "video.mp4"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"video")
    store = MediaSessionStore(database, ttl_seconds=-1, temp_root=tmp_path, temp_file_ttl_seconds=1)
    media = await store.create(
        user_id=1,
        platform="generic",
        title="video",
        upstream_url=None,
        temporary_file=str(stored),
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
    assert await store.cleanup() == 2
    assert not stored.parent.exists()
    assert not orphan.parent.exists()
    database.close()


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
    _database = Database(f"sqlite:///{tmp_path / 'escape-media.db'}")
    _database.create_schema()
    service = ParseService(
        settings,
        NoNetworkHttp(),
        SingleRegistry(),
        MediaSessionStore(_database, 60, settings.temp_dir),
    )
    with pytest.raises(AppError) as captured:
        await service.parse("https://example.com/watch", user_id=1)
    assert captured.value.code == "PARSE_FAILED"
    _database.close()


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


def test_default_job_limits_and_result_retention_are_bounded() -> None:
    settings = Settings(app_env="test", _env_file=None)
    assert settings.max_active_parse_jobs_per_user == 2
    assert settings.parse_worker_concurrency == 2
    assert settings.media_processing_concurrency == 1
    assert settings.media_session_ttl_seconds == 24 * 60 * 60
    assert settings.media_access_token_ttl_seconds == 900
    assert settings.temp_file_ttl_seconds >= settings.media_session_ttl_seconds


def test_result_file_ttl_cannot_be_shorter_than_media_session() -> None:
    with pytest.raises(ValidationError, match="TEMP_FILE_TTL_SECONDS"):
        Settings(
            app_env="test",
            media_session_ttl_seconds=3600,
            temp_file_ttl_seconds=3599,
        )


def test_media_access_token_ttl_cannot_exceed_media_retention() -> None:
    with pytest.raises(ValidationError, match="MEDIA_ACCESS_TOKEN_TTL_SECONDS"):
        Settings(
            app_env="test",
            media_session_ttl_seconds=900,
            media_access_token_ttl_seconds=901,
        )


@pytest.mark.asyncio
async def test_media_access_token_is_short_lived_and_reissuable(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'token-ttl.db'}")
    database.create_schema()
    with database.session_factory() as session:
        session.add(User(openid="token-ttl-user"))
        session.commit()
    media_file = tmp_path / "media" / "video.mp4"
    media_file.parent.mkdir(parents=True)
    media_file.write_bytes(b"video")
    store = MediaSessionStore(
        database,
        ttl_seconds=24 * 60 * 60,
        temp_root=tmp_path / "media",
        temp_file_ttl_seconds=90000,
        access_token_ttl_seconds=900,
    )

    first = await store.create(
        user_id=1,
        platform="generic",
        title="video",
        upstream_url=None,
        temporary_file=str(media_file),
        required_headers={},
        mime_type="video/mp4",
        size_bytes=5,
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    with database.session_factory() as session:
        access = session.get(MediaAccessToken, store._token_hash(first.token))
        assert access is not None
        assert 0 < (access.expires_at - now).total_seconds() <= 900

    second = await store.issue_token(first.session_id, user_id=1)
    assert second.token != first.token
    assert (await store.get(second.token)).session_id == first.session_id
    database.close()
