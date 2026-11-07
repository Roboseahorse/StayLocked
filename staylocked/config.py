"""
Configuration, paths, and defaults for HardLock.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from staylocked import __version__

APP_NAME = "StayLocked"
APP_VERSION = __version__

# Change this to your own GitHub repo once you create it
# Format: https://api.github.com/repos/USERNAME/REPO/releases/latest
UPDATE_CHECK_URL = "https://api.github.com/repos/Roboseahorse/StayLocked/releases/latest"

APP_DIR = Path.home() / ".staylocked"
APP_DIR.mkdir(exist_ok=True)

ALLOWLIST_FILE = APP_DIR / "allowlist.json"
CONFIG_FILE = APP_DIR / "config.json"
SESSION_FILE = APP_DIR / "active_session.json"
LAST_SESSION_FILE = APP_DIR / "last_session.json"
PROFILES_DIR = APP_DIR / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)

# Permanent install location (Windows)
if sys.platform == "win32":
    INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "HardLock"
else:
    INSTALL_DIR = Path.home() / ".local" / "share" / "HardLock"

INSTALL_EXE = INSTALL_DIR / "StayLocked.exe"

DEFAULT_CONFIG: dict[str, Any] = {
    "force_close": True,
    "notifications": True,
    "check_interval": 1.5,
    "emergency_password": "",
    "theme": "dark",
    "pomodoro_work": 25,
    "pomodoro_break": 5,
    "check_for_updates": True,
    "update_url": UPDATE_CHECK_URL,
    # New options ready for future features
    "start_minimized": False,
    "always_on_top_when_blocking": False,
    "protect_task_manager": False,  # aggressive option
}


def load_config() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config: dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def load_allowlist() -> set[str]:
    if ALLOWLIST_FILE.exists():
        try:
            with open(ALLOWLIST_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_allowlist(allowlist: set[str]) -> None:
    with open(ALLOWLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(allowlist)), f, indent=2)


def load_last_session() -> dict[str, Any]:
    if LAST_SESSION_FILE.exists():
        try:
            with open(LAST_SESSION_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_last_session(data: dict[str, Any]) -> None:
    with open(LAST_SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
