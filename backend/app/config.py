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
    max_source_video_bytes: int = 2 * 1024 * 1024 * 1024
    min_free_disk_bytes: int = 10 * 1024 * 1024 * 1024
    parse_timeout_seconds: int = 1800
    douyin_metadata_timeout_seconds: int = 8
    douyin_yt_dlp_fallback_timeout_seconds: int = 4
    media_processing_timeout_seconds: int = 1800
    media_session_ttl_seconds: int = 86400
    media_access_token_ttl_seconds: int = 900
    temp_file_ttl_seconds: int = 90000
    parse_job_ttl_seconds: int = 86400
    max_redirects: int = 5
    http_timeout_seconds: int = 20
    global_parse_concurrency: int = 2
    parse_worker_concurrency: int = 2
    media_processing_concurrency: int = 1
    max_active_parse_jobs_per_user: int = 2
    max_queued_parse_jobs: int = 20
    user_parse_limit_per_10_minutes: int = 10
    ad_attempt_min_seconds: int = 5
    ad_attempt_ttl_seconds: int = 600
    temp_dir: Path = Path("./tmp/media")
    log_level: str = "INFO"

    @model_validator(mode="after")
    def production_safety(self) -> Settings:
        if self.max_video_bytes <= 0 or self.max_video_bytes > 200 * 1024 * 1024:
            raise ValueError("MAX_VIDEO_BYTES 必须在 1..200MiB 范围内")
        if (
            self.max_source_video_bytes < self.max_video_bytes
            or self.max_source_video_bytes > 4 * 1024 * 1024 * 1024
        ):
            raise ValueError("MAX_SOURCE_VIDEO_BYTES 必须不小于成品上限且不超过 4GiB")
        if self.min_free_disk_bytes < 0:
            raise ValueError("MIN_FREE_DISK_BYTES 不得为负数")
        if self.media_processing_timeout_seconds < 30:
            raise ValueError("MEDIA_PROCESSING_TIMEOUT_SECONDS 不得低于 30 秒")
        if not 1 <= self.douyin_metadata_timeout_seconds <= 30:
            raise ValueError("DOUYIN_METADATA_TIMEOUT_SECONDS 必须在 1..30 秒范围内")
        if not 1 <= self.douyin_yt_dlp_fallback_timeout_seconds <= 15:
            raise ValueError("DOUYIN_YT_DLP_FALLBACK_TIMEOUT_SECONDS 必须在 1..15 秒范围内")
        if not 1 <= self.global_parse_concurrency <= 8:
            raise ValueError("GLOBAL_PARSE_CONCURRENCY 必须在 1..8 范围内")
        if not 1 <= self.parse_worker_concurrency <= 8:
            raise ValueError("PARSE_WORKER_CONCURRENCY 必须在 1..8 范围内")
        if not 1 <= self.media_processing_concurrency <= 4:
            raise ValueError("MEDIA_PROCESSING_CONCURRENCY 必须在 1..4 范围内")
        if not 1 <= self.max_active_parse_jobs_per_user <= 5:
            raise ValueError("MAX_ACTIVE_PARSE_JOBS_PER_USER 必须在 1..5 范围内")
        if not self.max_active_parse_jobs_per_user <= self.max_queued_parse_jobs <= 100:
            raise ValueError("MAX_QUEUED_PARSE_JOBS 必须不小于单用户上限且不超过 100")
        if self.media_session_ttl_seconds <= 0:
            raise ValueError("MEDIA_SESSION_TTL_SECONDS 必须大于 0")
        if self.media_access_token_ttl_seconds <= 0:
            raise ValueError("MEDIA_ACCESS_TOKEN_TTL_SECONDS 必须大于 0")
        if self.media_access_token_ttl_seconds > self.media_session_ttl_seconds:
            raise ValueError("MEDIA_ACCESS_TOKEN_TTL_SECONDS 不得长于媒体结果有效期")
        if self.temp_file_ttl_seconds < self.media_session_ttl_seconds:
            raise ValueError("TEMP_FILE_TTL_SECONDS 不得短于媒体结果有效期")
        if self.parse_job_ttl_seconds < self.media_session_ttl_seconds:
            raise ValueError("PARSE_JOB_TTL_SECONDS 不得短于媒体结果有效期")
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
