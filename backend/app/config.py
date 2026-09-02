from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    max_video_bytes: int = 180 * 1024 * 1024
    parse_timeout_seconds: int = 30
    media_session_ttl_seconds: int = 900
    temp_file_ttl_seconds: int = 1800
    max_redirects: int = 5
    http_timeout_seconds: int = 20
    global_parse_concurrency: int = 4
    user_parse_limit_per_10_minutes: int = 10
    temp_dir: Path = Path("./tmp/media")
    log_level: str = "INFO"

    @model_validator(mode="after")
    def production_safety(self) -> Settings:
        if self.max_video_bytes <= 0 or self.max_video_bytes > 200 * 1024 * 1024:
            raise ValueError("MAX_VIDEO_BYTES 必须在 1..200MiB 范围内")
        if self.max_redirects < 0 or self.max_redirects > 10:
            raise ValueError("MAX_REDIRECTS 必须在 0..10 范围内")
        if self.app_env == "production":
            if self.mock_wechat_auth:
                raise ValueError("生产环境禁止 MOCK_WECHAT_AUTH")
            if not self.public_base_url.startswith("https://"):
                raise ValueError("生产 PUBLIC_BASE_URL 必须使用 HTTPS")
            if not self.wechat_app_id or not self.wechat_app_secret.get_secret_value():
                raise ValueError("生产环境必须配置微信 AppID/AppSecret")
            secret = self.app_token_secret.get_secret_value()
            if len(secret) < 32 or secret.startswith("development"):
                raise ValueError("生产 APP_TOKEN_SECRET 必须是至少 32 位随机值")
        return self


def load_settings() -> Settings:
    return Settings()
