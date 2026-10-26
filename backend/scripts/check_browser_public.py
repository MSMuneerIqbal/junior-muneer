r"""Opt-in smoke check: actual Chromium visits example.com through the production network guard, no model calls.

Run from backend: .venv\Scripts\python scripts/check_browser_public.py
Uses throwaway storage. Never loads the owner's chats, cookies, profile or connected accounts.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def check():
    from junior.browser.runtime import BrowserAction, BrowserManager
    from junior.settings_store import set_setting
    set_setting("browser_enabled", True)
    set_setting("browser_sites", ["https://example.com"])
    browser = BrowserManager()
    try:
        await browser.execute(BrowserAction(kind="navigate", url="https://example.com"))
        snapshot = await browser.snapshot()
        assert snapshot["title"] == "Example Domain" and len(snapshot["text"]) > 30
        print("PASS: real Chromium HTTPS navigation and bounded snapshot via scoped public-IP proxy; zero model calls.")
    finally:
        await browser.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="junior-browser-public-") as folder:
        os.environ["DATA_DIR"] = folder
        os.environ["SCHEDULER_ENABLED"] = "false"
        from junior.config import get_settings
        get_settings.cache_clear()
        from junior.db import init_db
        from junior.db.engine import close_all_connections
        init_db()
        try:
            asyncio.run(check())
        finally:
            close_all_connections()
