from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.douyin_session.bootstrap import bootstrap_manual_session
from app.douyin_session.models import (
    has_valid_douyin_cookie,
    sanitise_storage_state_path,
    validate_storage_state_path,
)
from app.errors import AppError


class FakePage:
    async def goto(self, url: str, *, wait_until: str) -> None:
        assert url == "https://www.douyin.com/"
        assert wait_until == "domcontentloaded"


class FakeContext:
    def __init__(self, state_payload: dict[str, object]) -> None:
        self.state_payload = state_payload

    async def new_page(self) -> FakePage:
        return FakePage()

    async def storage_state(self, *, path: str) -> None:
        await asyncio.to_thread(
            Path(path).write_text,
            json.dumps(self.state_payload),
            encoding="utf-8",
        )

    async def close(self) -> None:
        return None


class FakeBrowser:
    def __init__(self, state_payload: dict[str, object]) -> None:
        self.state_payload = state_payload

    async def new_context(self) -> FakeContext:
        return FakeContext(self.state_payload)

    async def close(self) -> None:
        return None


class FakeChromium:
    def __init__(self, state_payload: dict[str, object]) -> None:
        self.state_payload = state_payload

    async def launch(self, *, headless: bool) -> FakeBrowser:
        assert headless is False
        return FakeBrowser(self.state_payload)


class FakePlaywright:
    def __init__(self, state_payload: dict[str, object]) -> None:
        self.chromium = FakeChromium(state_payload)


class FakeManager:
    def __init__(self, state_payload: dict[str, object] | None = None) -> None:
        self.state_payload = state_payload or {
            "cookies": [{"domain": ".douyin.com", "name": "session", "value": "present"}],
            "origins": [],
        }

    async def __aenter__(self) -> FakePlaywright:
        return FakePlaywright(self.state_payload)

    async def __aexit__(self, *_args) -> None:
        return None


def session_settings(tmp_path: Path, **changes: object) -> Settings:
    external_storage = tmp_path / "external-storage"
    external_storage.mkdir()
    values: dict[str, object] = {
        "app_env": "test",
        "douyin_session_enabled": True,
        "douyin_storage_state_path": external_storage / "operator-state.json",
    }
    values.update(changes)
    return Settings(**values)


@pytest.mark.asyncio
async def test_bootstrap_is_closed_when_optional_feature_is_disabled(tmp_path: Path) -> None:
    settings = session_settings(tmp_path, douyin_session_enabled=False)

    with pytest.raises(AppError) as caught:
        await bootstrap_manual_session(
            settings,
            playwright_factory=FakeManager,
            wait_for_operator=lambda: None,
        )

    assert caught.value.code == "DOUYIN_SESSION_DISABLED"


@pytest.mark.asyncio
async def test_manual_bootstrap_saves_external_state_without_logging_contents(tmp_path: Path, caplog) -> None:
    settings = session_settings(tmp_path)

    result = await bootstrap_manual_session(
        settings,
        playwright_factory=FakeManager,
        wait_for_operator=lambda: None,
    )

    assert result.state_path_label == "<external-storage>/operator-state.json"
    assert settings.douyin_storage_state_path is not None
    assert settings.douyin_storage_state_path.exists()
    assert "cookies" not in caplog.text
    assert str(settings.douyin_storage_state_path.parent) not in caplog.text


def test_storage_state_rejects_repository_relative_or_invalid_files(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="绝对路径"):
        validate_storage_state_path("state.json", require_exists=False)
    with pytest.raises(ValueError, match="仓库目录"):
        validate_storage_state_path(
            Path(__file__).resolve().parents[2] / "operator-state.json",
            require_exists=False,
        )
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="有效"):
        validate_storage_state_path(invalid, require_exists=True)


def test_storage_state_label_never_reveals_parent_directories(tmp_path: Path) -> None:
    assert sanitise_storage_state_path(tmp_path / "secret" / "state.json") == "<external-storage>/state.json"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"cookies": [], "origins": []},
        {"cookies": [{"domain": ".example.com", "name": "session", "value": "present"}]},
        {"cookies": [{"domain": ".douyin.com", "name": "", "value": "present"}]},
    ],
)
async def test_bootstrap_rejects_incomplete_login_without_creating_state(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    settings = session_settings(tmp_path)

    with pytest.raises(AppError) as caught:
        await bootstrap_manual_session(
            settings,
            playwright_factory=lambda: FakeManager(payload),
            wait_for_operator=lambda: None,
        )

    assert caught.value.code == "DOUYIN_SESSION_LOGIN_INCOMPLETE"
    assert settings.douyin_storage_state_path is not None
    assert not settings.douyin_storage_state_path.exists()


@pytest.mark.asyncio
async def test_incomplete_login_does_not_overwrite_existing_state(tmp_path: Path) -> None:
    settings = session_settings(tmp_path)
    assert settings.douyin_storage_state_path is not None
    settings.douyin_storage_state_path.write_text("existing-valid-state", encoding="utf-8")

    with pytest.raises(AppError) as caught:
        await bootstrap_manual_session(
            settings,
            playwright_factory=lambda: FakeManager({"cookies": [], "origins": []}),
            wait_for_operator=lambda: None,
        )

    assert caught.value.code == "DOUYIN_SESSION_LOGIN_INCOMPLETE"
    assert settings.douyin_storage_state_path.read_text(encoding="utf-8") == "existing-valid-state"
    assert not list(settings.douyin_storage_state_path.parent.glob(".operator-state.json.*.tmp"))


def test_douyin_cookie_check_does_not_return_cookie_details(tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    state.write_text(
        json.dumps({"cookies": [{"domain": ".douyin.com", "name": "secret", "value": "hidden"}]}),
        encoding="utf-8",
    )
    assert has_valid_douyin_cookie(state) is True


def production_settings(**changes: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "production",
        "public_base_url": "https://api.example.cn",
        "app_token_secret": "2xY7z9K4mN8qR1vT5wC0dF3hJ6lP9sB2",
        "wechat_app_id": "wx1234567890abcdef",
        "wechat_app_secret": "a" * 32,
        "mock_wechat_auth": False,
        "dev_bypass_download_entitlement": False,
    }
    values.update(changes)
    return Settings(**values)


def test_production_session_path_is_checked_only_when_explicitly_enabled(tmp_path: Path) -> None:
    disabled = production_settings(douyin_session_enabled=False)
    assert disabled.douyin_session_enabled is False
    with pytest.raises(ValueError, match="必须设置"):
        production_settings(douyin_session_enabled=True)
    with pytest.raises(ValueError, match="仓库目录"):
        production_settings(
            douyin_session_enabled=True,
            douyin_storage_state_path=Path(__file__).resolve().parents[2] / "state.json",
        )
    invalid = tmp_path / "bad-state.json"
    invalid.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="权限不安全|格式无效"):
        production_settings(douyin_session_enabled=True, douyin_storage_state_path=invalid)
