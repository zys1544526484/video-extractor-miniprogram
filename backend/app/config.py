from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_PATTERN = re.compile(
    r"example\.(?:com|net|org)|replace|placeholder|change[-_]?me|your[-_]?",
    re.IGNORECASE,
)
WECHAT_APP_ID_PATTERN = re.compile(r"^wx[0-9A-Fa-f]{16}$")
WECHAT_APP_SECRET_PATTERN = re.compile(r"^[0-9A-Za-z]{32}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    version: str = "0.1.0"
    database_url: str = "sqlite:///./data/app.db"
    public_base_url: str = "http://127.0.0.1:8000"
    app_token_secret: SecretStr = SecretStr("development-only-token-secret-change-me")
    auth_token_ttl_seconds: int = 604800

    wechat_app_id: str = ""
    wechat_app_secret: SecretStr = SecretStr("")
    mock_wechat_auth: bool = True
    dev_bypass_download_entitlement: bool = False
    download_access_mode: Literal["free", "rewarded_ad"] = "free"

    max_video_bytes: int = 180 * 1024 * 1024
    parse_timeout_seconds: int = 30
    media_session_ttl_seconds: int = 900
    temp_file_ttl_seconds: int = 1800
    max_redirects: int = 5
    http_timeout_seconds: int = 20
    global_parse_concurrency: int = 4
    user_parse_limit_per_10_minutes: int = 10
    ad_attempt_min_seconds: int = 5
    ad_attempt_ttl_seconds: int = 600
    temp_dir: Path = Path("./tmp/media")
    log_level: str = "INFO"

    @model_validator(mode="after")
    def production_safety(self) -> Settings:
        if self.max_video_bytes <= 0 or self.max_video_bytes > 200 * 1024 * 1024:
            raise ValueError("MAX_VIDEO_BYTES 必须在 1..200MiB 范围内")
        if self.max_redirects < 0 or self.max_redirects > 10:
            raise ValueError("MAX_REDIRECTS 必须在 0..10 范围内")
        if self.ad_attempt_min_seconds < 0 or self.ad_attempt_min_seconds > 120:
            raise ValueError("AD_ATTEMPT_MIN_SECONDS 必须在 0..120 范围内")
        if self.ad_attempt_ttl_seconds < self.ad_attempt_min_seconds + 30:
            raise ValueError("AD_ATTEMPT_TTL_SECONDS 必须至少比最短观看时间长 30 秒")
        if self.app_env == "production":
            if self.mock_wechat_auth:
                raise ValueError("生产环境禁止 MOCK_WECHAT_AUTH")
            if self.dev_bypass_download_entitlement:
                raise ValueError("生产环境禁止 DEV_BYPASS_DOWNLOAD_ENTITLEMENT")
            try:
                parsed = urlsplit(self.public_base_url)
                host = parsed.hostname or ""
            except (ValueError, TypeError):
                parsed = None
                host = ""
            try:
                ipaddress.ip_address(host)
            except ValueError:
                is_ip = False
            else:
                is_ip = True
            if (
                parsed is None
                or parsed.scheme != "https"
                or not host
                or parsed.username
                or parsed.password
                or parsed.port is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or host.lower() == "localhost"
                or is_ip
                or PLACEHOLDER_PATTERN.search(host)
            ):
                raise ValueError("生产 PUBLIC_BASE_URL 必须是无端口、非占位的 HTTPS 域名源站")
            wechat_secret = self.wechat_app_secret.get_secret_value()
            if not WECHAT_APP_ID_PATTERN.fullmatch(self.wechat_app_id):
                raise ValueError("生产 WECHAT_APP_ID 格式无效或仍为占位值")
            if (
                not WECHAT_APP_SECRET_PATTERN.fullmatch(wechat_secret)
                or PLACEHOLDER_PATTERN.search(wechat_secret)
            ):
                raise ValueError("生产 WECHAT_APP_SECRET 格式无效或仍为占位值")
            secret = self.app_token_secret.get_secret_value()
            if len(secret) < 32 or len(set(secret)) < 12 or PLACEHOLDER_PATTERN.search(secret):
                raise ValueError("生产 APP_TOKEN_SECRET 必须是至少 32 位的非占位高熵随机值")
            if self.ad_attempt_min_seconds < 3:
                raise ValueError("生产 AD_ATTEMPT_MIN_SECONDS 不得低于 3 秒")
        return self


def load_settings() -> Settings:
    return Settings()
