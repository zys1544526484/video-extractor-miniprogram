from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sanitise_storage_state_path(path: Path) -> str:
    """Return a log-safe label that does not disclose external directories."""
    return f"<external-storage>/{path.name}"


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def validate_storage_state_path(
    value: Path | str | None,
    *,
    require_exists: bool,
    require_private_permissions: bool = False,
) -> Path:
    """Validate a Playwright storage state without exposing its contents."""
    if value is None or not str(value).strip():
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 必须设置为仓库外的绝对路径")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 必须是绝对路径")
    resolved = path.resolve(strict=False)
    if _is_within(resolved, repository_root()):
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 不得位于仓库目录")
    if not require_exists:
        if not resolved.parent.is_dir():
            raise ValueError("DOUYIN_STORAGE_STATE_PATH 的父目录不存在")
        return resolved
    if not resolved.is_file():
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 不存在或不是文件")
    if resolved.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 文件过大")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 不是有效的 storage state 文件") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("cookies", []), list):
        raise ValueError("DOUYIN_STORAGE_STATE_PATH 格式无效")
    if require_private_permissions:
        mode = stat.S_IMODE(resolved.stat().st_mode)
        if mode & 0o077:
            raise ValueError("DOUYIN_STORAGE_STATE_PATH 权限不安全")
    return resolved


def has_valid_douyin_cookie(value: Path | str) -> bool:
    """Check login completeness without returning any Cookie data."""
    try:
        payload = json.loads(Path(value).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    if not isinstance(cookies, list):
        return False
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        domain = str(cookie.get("domain", "")).lower().lstrip(".")
        name = cookie.get("name")
        value = cookie.get("value")
        if (
            (domain == "douyin.com" or domain.endswith(".douyin.com"))
            and isinstance(name, str)
            and bool(name.strip())
            and isinstance(value, str)
            and bool(value.strip())
        ):
            return True
    return False


def target_id_from_url(url: str) -> str | None:
    """Accept exactly a public www.douyin.com /video/{numeric-id} URL."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.douyin.com"
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2 or parts[0] != "video" or not parts[1].isdigit():
        return None
    return parts[1]


def normalise_douyin_redirect_target(url: str) -> tuple[str, str] | None:
    """Safely convert a validated public redirect target into a canonical URL.

    This deliberately accepts query parameters only while resolving an external
    short link.  The session worker continues to require the exact, query-free
    canonical URL returned here.
    """
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username
        or parsed.password
        or port is not None
    ):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    work_id: str | None = None
    if hostname in {"douyin.com", "www.douyin.com"}:
        if len(parts) == 2 and parts[0] == "video" and parts[1].isdigit():
            work_id = parts[1]
    elif hostname == "www.iesdouyin.com":
        if len(parts) == 3 and parts[:2] == ["share", "video"] and parts[2].isdigit():
            work_id = parts[2]
    if work_id is None:
        return None
    return f"https://www.douyin.com/video/{work_id}", work_id


@dataclass(frozen=True)
class PlayerDiagnostics:
    """Log-safe player facts. This model deliberately contains no URLs."""

    page_route: str
    target_id: str
    video_count: int
    visible_video_count: int
    has_current_src: bool
    has_src: bool
    has_source_child: bool
    has_blob_url: bool
    media_response_count: int
    media_content_types: tuple[str, ...]
    media_domains: tuple[str, ...]
    last_phase: str
    phase_ms: tuple[tuple[str, int], ...]
    target_bound_candidate_count: int = 0
    unbound_candidate_count: int = 0
    candidate_group_count: int = 0
    candidate_source: str | None = None
    before_target_verified: int = 0
    wrong_frame: int = 0
    missing_referer: int = 0
    referer_mismatch: int = 0
    wrong_mime: int = 0
    ssrf_rejected: int = 0
    ambiguous_resource: int = 0
    hidden_player_possible: int = 0
    equivalent_group_count: int = 0


@dataclass(frozen=True)
class CapturedMedia:
    """Internal browser capture; never serialise or log its URL."""

    target_id: str | None
    media_url: str | None
    state: str = "ok"
    diagnostics: PlayerDiagnostics | None = None
    # Mirror URLs from one exact target-bound structured source remain only in
    # memory for this capture; the worker independently probes them without
    # browser session credentials.
    media_urls: tuple[str, ...] = ()
    candidate_source: str | None = None


@dataclass(frozen=True)
class SessionWorkerResult:
    """Safe POC outcome: deliberately contains neither URL nor cookies."""

    target_id: str
    media_origin: str
    size_bytes: int | None
    bytes_read: int
    elapsed_ms: int
