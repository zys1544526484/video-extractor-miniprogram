"""One-shot, redacted local acceptance runner for the P3 headed session PoC."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from ..config import Settings, load_settings
from .models import has_valid_douyin_cookie, repository_root, validate_storage_state_path
from .smoke import SmokeOutput, run_smoke

EXPECTED_BRANCH = "codex/p3-douyin-session-poc"
MINIMUM_HEAD = "f15943d599cdab085566662b6c9116751b504a21"
ALLOWED_DIRTY_PATHS = frozenset(
    {
        "backend/wechat_video_extractor_backend.egg-info/PKG-INFO",
        "backend/wechat_video_extractor_backend.egg-info/SOURCES.txt",
        "backend/wechat_video_extractor_backend.egg-info/requires.txt",
    }
)
SAFE_PHASES = frozenset(
    {
        "browser_launch",
        "page_navigation",
        "target_identity",
        "player_mount",
        "player_activation",
        "media_capture",
        "player_seek",
        "player_reload",
        "media_verify",
    }
)
SAFE_CANDIDATE_SOURCES = frozenset(
    {"detail_json", "hydration_json", "main_player_network", "main_player_mse"}
)
INTEGER_FIELDS = frozenset(
    {
        "bytes_read",
        "elapsed_ms",
        "phase_elapsed_ms",
        "video_count",
        "visible_video_count",
        "media_response_count",
        "target_bound_candidate_count",
        "unbound_candidate_count",
        "candidate_group_count",
        "before_target_verified",
        "wrong_frame",
        "referer_exact_target_path",
        "referer_douyin_origin_only",
        "referer_other_douyin_path",
        "referer_external_origin",
        "referer_missing",
        "wrong_mime",
        "ssrf_rejected",
        "ambiguous_resource",
        "hidden_player_possible",
        "equivalent_group_count",
    }
)
BOOLEAN_FIELDS = frozenset(
    {"has_current_src", "has_src", "has_source_child", "has_blob_source"}
)
ERROR_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
WORK_ID_PATTERN = re.compile(r"^\d{6,32}$")


class GitResult(NamedTuple):
    returncode: int
    stdout: str


GitRunner = Callable[[Path, Sequence[str]], GitResult]
SmokeRunner = Callable[[Settings, str], Awaitable[SmokeOutput]]


class VerificationError(Exception):
    """Stable local preflight failure without raw subprocess or path details."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _run_git(cwd: Path, arguments: Sequence[str]) -> GitResult:
    git = shutil.which("git")
    if git is None:
        return GitResult(127, "")
    try:
        completed = subprocess.run(  # noqa: S603 - executable and arguments are controlled here.
            [git, *arguments],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return GitResult(1, "")
    # Porcelain status uses a meaningful leading space for an unstaged change.
    # Callers that expect a scalar value trim it in ``_git_value`` instead.
    return GitResult(completed.returncode, completed.stdout)


def _git_value(
    root: Path,
    arguments: Sequence[str],
    *,
    error_code: str,
    runner: GitRunner,
) -> str:
    result = runner(root, arguments)
    if result.returncode != 0 or not result.stdout.strip():
        raise VerificationError(error_code)
    return result.stdout.strip()


def _status_paths(status_text: str) -> set[str]:
    paths: set[str] = set()
    for raw_line in status_text.splitlines():
        if len(raw_line) < 4:
            continue
        path = raw_line[3:].strip().replace("\\", "/")
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[-1]
        paths.add(path.strip('"'))
    return paths


def verify_preflight(
    *,
    root: Path,
    environ: Mapping[str, str],
    git_runner: GitRunner = _run_git,
) -> tuple[str, str]:
    """Verify repository identity and required state without disclosing secret values."""
    fetch = git_runner(root, ("fetch", "--quiet", "origin", EXPECTED_BRANCH))
    if fetch.returncode != 0:
        raise VerificationError("VERIFY_GIT_FETCH_FAILED")
    branch = _git_value(
        root,
        ("branch", "--show-current"),
        error_code="VERIFY_BRANCH_FAILED",
        runner=git_runner,
    )
    if branch != EXPECTED_BRANCH:
        raise VerificationError("VERIFY_WRONG_BRANCH")
    head = _git_value(
        root,
        ("rev-parse", "HEAD"),
        error_code="VERIFY_HEAD_FAILED",
        runner=git_runner,
    )
    remote_head = _git_value(
        root,
        ("rev-parse", f"refs/remotes/origin/{EXPECTED_BRANCH}"),
        error_code="VERIFY_REMOTE_HEAD_FAILED",
        runner=git_runner,
    )
    if not re.fullmatch(r"[0-9a-f]{40}", head) or head != remote_head:
        raise VerificationError("VERIFY_HEAD_NOT_PUSHED")
    ancestor = git_runner(root, ("merge-base", "--is-ancestor", MINIMUM_HEAD, head))
    if ancestor.returncode != 0:
        raise VerificationError("VERIFY_BASELINE_MISMATCH")
    status = git_runner(root, ("status", "--porcelain=v1", "--untracked-files=all"))
    if status.returncode != 0:
        raise VerificationError("VERIFY_GIT_STATUS_FAILED")
    unexpected = _status_paths(status.stdout) - ALLOWED_DIRTY_PATHS
    if unexpected:
        raise VerificationError("VERIFY_WORKTREE_HAS_UNEXPECTED_CHANGES")

    if environ.get("DOUYIN_SESSION_ENABLED", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise VerificationError("VERIFY_SESSION_NOT_ENABLED")
    if not environ.get("DOUYIN_SMOKE_URL", "").strip():
        raise VerificationError("VERIFY_SMOKE_URL_REQUIRED")
    try:
        state_path = validate_storage_state_path(
            environ.get("DOUYIN_STORAGE_STATE_PATH"),
            require_exists=True,
        )
    except ValueError as error:
        raise VerificationError("VERIFY_STORAGE_STATE_INVALID") from error
    if not has_valid_douyin_cookie(state_path):
        raise VerificationError("VERIFY_SESSION_LOGIN_INCOMPLETE")
    return branch, head


def _safe_origin(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.hostname.lower()}"


def _safe_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _smoke_mapping(output: SmokeOutput | Mapping[str, Any]) -> dict[str, Any]:
    if is_dataclass(output) and not isinstance(output, type):
        return asdict(output)
    return dict(output)


def sanitise_smoke_output(output: SmokeOutput | Mapping[str, Any]) -> dict[str, object]:
    """Rebuild the final payload from an allow-list; never pass arbitrary strings through."""
    source = _smoke_mapping(output)
    outcome = source.get("outcome") if source.get("outcome") in {"success", "failure"} else "failure"
    error_code = source.get("error_code")
    if not isinstance(error_code, str) or ERROR_CODE_PATTERN.fullmatch(error_code) is None:
        error_code = "VERIFY_OUTPUT_INVALID"
        outcome = "failure"
    work_id = str(source.get("work_id") or "")
    if WORK_ID_PATTERN.fullmatch(work_id) is None:
        work_id = None
    final_page_path = source.get("final_page_path")
    if work_id is None or final_page_path != f"/video/{work_id}":
        final_page_path = None
    last_phase = source.get("last_phase")
    if last_phase not in SAFE_PHASES:
        last_phase = None
    candidate_source = source.get("candidate_source")
    if candidate_source not in SAFE_CANDIDATE_SOURCES:
        candidate_source = None

    phases_source = source.get("phases_ms")
    phases_ms: dict[str, int] = {}
    if isinstance(phases_source, Mapping):
        for phase in SAFE_PHASES:
            value = _safe_integer(phases_source.get(phase))
            if value is not None:
                phases_ms[phase] = value

    media_mime_types = []
    values = source.get("media_mime_types")
    if isinstance(values, (list, tuple)):
        media_mime_types = sorted(
            {
                value.lower()
                for value in values
                if isinstance(value, str)
                and (
                    value.lower().startswith("video/")
                    or value.lower()
                    in {"application/vnd.apple.mpegurl", "application/x-mpegurl"}
                )
            }
        )
    media_domains = []
    values = source.get("media_domains")
    if isinstance(values, (list, tuple)):
        media_domains = sorted({origin for value in values if (origin := _safe_origin(value))})

    result: dict[str, object] = {
        "outcome": outcome,
        "error_code": error_code,
        "work_id": work_id,
        "media_domain": _safe_origin(source.get("media_domain")),
        "last_phase": last_phase,
        "phases_ms": phases_ms,
        "final_page_path": final_page_path,
        "media_mime_types": media_mime_types,
        "media_domains": media_domains,
        "candidate_source": candidate_source,
    }
    for field in INTEGER_FIELDS:
        result[field] = _safe_integer(source.get(field))
    for field in BOOLEAN_FIELDS:
        value = source.get(field)
        result[field] = value if isinstance(value, bool) else None
    return result


def _failure_payload(code: str, *, branch: str | None = None, head: str | None = None) -> dict[str, object]:
    return {
        "verification": "failure",
        "branch": branch,
        "head": head,
        "outcome": "failure",
        "error_code": code if ERROR_CODE_PATTERN.fullmatch(code) else "VERIFY_INTERNAL_ERROR",
        "work_id": None,
        "media_domain": None,
        "bytes_read": None,
        "elapsed_ms": 0,
        "last_phase": None,
        "phase_elapsed_ms": None,
        "phases_ms": {},
        "final_page_path": None,
        "media_mime_types": [],
        "media_domains": [],
    }


async def run_verification(
    *,
    root: Path | None = None,
    environ: Mapping[str, str] | None = None,
    git_runner: GitRunner = _run_git,
    settings_loader: Callable[[], Settings] = load_settings,
    smoke_runner: SmokeRunner = run_smoke,
) -> tuple[dict[str, object], int]:
    active_root = (root or repository_root()).resolve()
    active_environ = environ or os.environ
    try:
        branch, head = verify_preflight(
            root=active_root,
            environ=active_environ,
            git_runner=git_runner,
        )
    except VerificationError as error:
        return _failure_payload(error.code), 2

    previous_headless = os.environ.get("DOUYIN_SESSION_HEADLESS")
    os.environ["DOUYIN_SESSION_HEADLESS"] = "false"
    try:
        settings = settings_loader()
        if settings.douyin_session_headless:
            return _failure_payload("VERIFY_HEADED_MODE_REQUIRED", branch=branch, head=head), 2
        output = await smoke_runner(settings, active_environ["DOUYIN_SMOKE_URL"])
    except Exception:  # The final CLI must not expose raw settings/browser exceptions.
        return _failure_payload("VERIFY_RUNTIME_FAILED", branch=branch, head=head), 2
    finally:
        if previous_headless is None:
            os.environ.pop("DOUYIN_SESSION_HEADLESS", None)
        else:
            os.environ["DOUYIN_SESSION_HEADLESS"] = previous_headless

    safe_output = sanitise_smoke_output(output)
    payload = {
        "verification": "pass" if safe_output["outcome"] == "success" else "smoke_failed",
        "branch": branch,
        "head": head,
        **safe_output,
    }
    return payload, 0 if safe_output["outcome"] == "success" else 1


async def async_main() -> int:
    payload, exit_code = await run_verification()
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return exit_code


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
