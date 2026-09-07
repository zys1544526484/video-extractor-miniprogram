from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.douyin_session.bootstrap import bootstrap_manual_session
from app.douyin_session.models import sanitise_storage_state_path, validate_storage_state_path
from app.errors import AppError


class FakePage:
    async def goto(self, url: str, *, wait_until: str) -> None:
        assert url == "https://www.douyin.com/"
        assert wait_until == "domcontentloaded"


class FakeContext:
    async def new_page(self) -> FakePage:
        return FakePage()

    async def storage_state(self, *, path: str) -> None:
        await asyncio.to_thread(
            Path(path).write_text,
            json.dumps({"cookies": [], "origins": []}),
            encoding="utf-8",
        )

    async def close(self) -> None:
        return None


class FakeBrowser:
    async def new_context(self) -> FakeContext:
        return FakeContext()

    async def close(self) -> None:
        return None


class FakeChromium:
    async def launch(self, *, headless: bool) -> FakeBrowser:
        assert headless is False
        return FakeBrowser()


class FakePlaywright:
    chromium = FakeChromium()


class FakeManager:
    async def __aenter__(self) -> FakePlaywright:
        return FakePlaywright()

    async def __aexit__(self, *_args) -> None:
        return None


def session_settings(tmp_path: Path, **changes: object) -> Settings:
    values: dict[str, object] = {
        "app_env": "test",
        "douyin_session_enabled": True,
        "douyin_storage_state_path": tmp_path.parent / "operator-state.json",
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
