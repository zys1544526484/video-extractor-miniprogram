from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..config import Settings, load_settings
from .errors import session_disabled, session_unavailable
from .models import sanitise_storage_state_path, validate_storage_state_path

logger = logging.getLogger(__name__)


def _load_async_playwright() -> Any:
    """Import Playwright only when an operator explicitly starts bootstrap."""
    try:
        from playwright.async_api import async_playwright
    except ImportError as error:
        raise session_unavailable() from error
    return async_playwright


@dataclass(frozen=True)
class BootstrapResult:
    state_path_label: str


async def bootstrap_manual_session(
    settings: Settings,
    *,
    playwright_factory: Callable[[], Any] | None = None,
    wait_for_operator: Callable[[], None] | None = None,
) -> BootstrapResult:
    """Open a visible browser and wait for an operator to login manually.

    This accepts no account or password values.  Captcha, slider and device
    verification are deliberately left to the operator and are never automated.
    """
    if not settings.douyin_session_enabled:
        raise session_disabled()
    state_path = validate_storage_state_path(
        settings.douyin_storage_state_path,
        require_exists=False,
    )
    factory = playwright_factory or _load_async_playwright
    pause = wait_for_operator or (lambda: input("请在可视浏览器中手动登录后按 Enter 保存会话："))
    try:
        async with factory() as playwright:
            browser = await playwright.chromium.launch(headless=False)
            try:
                context = await browser.new_context()
                try:
                    page = await context.new_page()
                    await page.goto("https://www.douyin.com/", wait_until="domcontentloaded")
                    pause()
                    await context.storage_state(path=str(state_path))
                finally:
                    await context.close()
            finally:
                await browser.close()
    except Exception as error:
        if getattr(error, "code", None):
            raise
        raise session_unavailable() from error
    if os.name == "posix":
        state_path.chmod(0o600)
    validate_storage_state_path(
        state_path,
        require_exists=True,
        require_private_permissions=os.name == "posix",
    )
    label = sanitise_storage_state_path(state_path)
    logger.info("douyin_session_bootstrap outcome=success state_path=%s", label)
    return BootstrapResult(state_path_label=label)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start an operator-only Douyin session bootstrap.")
    parser.parse_args()
    asyncio.run(bootstrap_manual_session(load_settings()))


if __name__ == "__main__":
    main()
