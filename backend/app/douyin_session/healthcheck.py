"""Private health check for the optional isolated headed session container."""

from __future__ import annotations

from ..config import load_settings
from .models import validate_storage_state_path


def main() -> None:
    settings = load_settings()
    if not settings.douyin_session_enabled or settings.douyin_session_headless:
        raise SystemExit(1)
    validate_storage_state_path(
        settings.douyin_storage_state_path,
        require_exists=True,
        require_private_permissions=False,
    )
    print("ok")


if __name__ == "__main__":
    main()
