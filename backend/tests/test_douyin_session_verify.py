from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.douyin_session.verify import (
    ALLOWED_DIRTY_PATHS,
    EXPECTED_BRANCH,
    MINIMUM_HEAD,
    GitResult,
    run_verification,
    sanitise_smoke_output,
    verify_preflight,
)

REMOTE_HEAD = "a" * 40


def valid_environment(tmp_path: Path) -> dict[str, str]:
    state_path = tmp_path / "operator-state.json"
    state_path.write_text(
        json.dumps(
            {
                "cookies": [
                    {"domain": ".douyin.com", "name": "operator", "value": "present"}
                ]
            }
        ),
        encoding="utf-8",
    )
    return {
        "DOUYIN_SESSION_ENABLED": "true",
        "DOUYIN_STORAGE_STATE_PATH": str(state_path),
        "DOUYIN_SMOKE_URL": "https://v.douyin.com/example/",
    }


def git_runner(*, dirty: str = ""):
    def run(_root: Path, arguments: tuple[str, ...] | list[str]) -> GitResult:
        key = tuple(arguments)
        if key == ("fetch", "--quiet", "origin", EXPECTED_BRANCH):
            return GitResult(0, "")
        if key == ("branch", "--show-current"):
            return GitResult(0, EXPECTED_BRANCH)
        if key in {
            ("rev-parse", "HEAD"),
            ("rev-parse", f"refs/remotes/origin/{EXPECTED_BRANCH}"),
        }:
            return GitResult(0, REMOTE_HEAD)
        if key == ("merge-base", "--is-ancestor", MINIMUM_HEAD, REMOTE_HEAD):
            return GitResult(0, "")
        if key == ("status", "--porcelain=v1", "--untracked-files=all"):
            return GitResult(0, dirty)
        return GitResult(1, "")

    return run


def test_preflight_accepts_remote_head_and_only_known_generated_changes(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    dirty = "\n".join(f" M {path}" for path in sorted(ALLOWED_DIRTY_PATHS))

    branch, head = verify_preflight(
        root=root,
        environ=valid_environment(tmp_path),
        git_runner=git_runner(dirty=dirty),
    )

    assert branch == EXPECTED_BRANCH
    assert head == REMOTE_HEAD


def test_preflight_rejects_unexpected_worktree_change(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(Exception, match="VERIFY_WORKTREE_HAS_UNEXPECTED_CHANGES"):
        verify_preflight(
            root=root,
            environ=valid_environment(tmp_path),
            git_runner=git_runner(dirty=" M backend/app/main.py"),
        )


@pytest.mark.asyncio
async def test_verification_forces_headed_and_runs_exactly_one_smoke(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    environment = valid_environment(tmp_path)
    calls: list[tuple[bool, str]] = []

    def load_fake_settings():
        return SimpleNamespace(douyin_session_headless=os.environ["DOUYIN_SESSION_HEADLESS"] != "false")

    async def run_fake_smoke(settings, url: str):
        calls.append((settings.douyin_session_headless, url))
        return {
            "outcome": "success",
            "error_code": "NONE",
            "work_id": "7678969660380843304",
            "media_domain": "https://media.example.com/signed/path?token=secret",
            "bytes_read": 1024,
            "elapsed_ms": 1234,
            "last_phase": "media_verify",
            "phase_elapsed_ms": 25,
            "phases_ms": {"media_verify": 25},
            "final_page_path": "/video/7678969660380843304",
            "media_mime_types": ["video/mp4"],
            "media_domains": ["https://media.example.com/signed/path?token=secret"],
        }

    payload, exit_code = await run_verification(
        root=root,
        environ=environment,
        git_runner=git_runner(),
        settings_loader=load_fake_settings,
        smoke_runner=run_fake_smoke,
    )

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0] == (False, environment["DOUYIN_SMOKE_URL"])
    assert payload["media_domain"] == "https://media.example.com"
    assert payload["media_domains"] == ["https://media.example.com"]
    assert "secret" not in json.dumps(payload)


def test_smoke_output_is_rebuilt_from_safe_allow_list() -> None:
    payload = sanitise_smoke_output(
        {
            "outcome": "failure",
            "error_code": "DOUYIN_SESSION_MEDIA_NOT_FOUND",
            "work_id": "7678969660380843304",
            "media_domain": "https://cdn.example.com/private/signature?token=secret",
            "elapsed_ms": 10,
            "last_phase": "media_capture",
            "phases_ms": {"media_capture": 10, "secret_phase": 99},
            "final_page_path": "/video/7678969660380843304?token=secret",
            "media_mime_types": ["video/mp4", "text/html?secret"],
            "media_domains": ["https://cdn.example.com/private/signature?token=secret"],
            "candidate_source": "main_player_network",
            "unexpected": "cookie=secret",
        }
    )

    encoded = json.dumps(payload)
    assert payload["media_domain"] == "https://cdn.example.com"
    assert payload["final_page_path"] is None
    assert payload["phases_ms"] == {"media_capture": 10}
    assert payload["media_mime_types"] == ["video/mp4"]
    assert "unexpected" not in payload
    assert "secret" not in encoded


def test_powershell_wrapper_invokes_only_verifier_and_emits_last_json_line() -> None:
    script = (
        Path(__file__).resolve().parents[2] / "scripts" / "verify_douyin_session.ps1"
    ).read_text(encoding="utf-8")

    assert script.count("-m app.douyin_session.verify") == 1
    assert "app.douyin_session.smoke" not in script
    assert "bootstrap" not in script.lower()
    assert "2>$null" in script
    assert "Select-Object -Last 1" in script
    assert "$env:DOUYIN_STORAGE_STATE_PATH" not in script
