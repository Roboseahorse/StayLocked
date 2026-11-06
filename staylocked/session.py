"""
Active session persistence and resume logic.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from staylocked.config import SESSION_FILE, APP_VERSION


def save_active_session(
    is_blocking: bool,
    mode: str,
    allowlist: set[str],
    force_close: bool,
    end_time: Optional[datetime],
    pomodoro_state: str = "work",
) -> None:
    """Save rich state so we can resume after an update/restart."""
    if not is_blocking:
        clear_active_session()
        return

    data = {
        "version": APP_VERSION,
        "mode": mode,
        "allowlist": sorted(list(allowlist)),
        "force_close": force_close,
        "end_time": end_time.isoformat() if end_time else None,
        "pomodoro_state": pomodoro_state,
        "started_at": datetime.now().isoformat(),
    }
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def clear_active_session() -> None:
    if SESSION_FILE.exists():
        try:
            SESSION_FILE.unlink()
        except Exception:
            pass


def load_active_session() -> Optional[dict[str, Any]]:
    if not SESSION_FILE.exists():
        return None
    try:
        with open(SESSION_FILE, encoding="utf-8") as f:
            data = json.load(f)
        end = data.get("end_time")
        if end:
            end_dt = datetime.fromisoformat(end)
            if datetime.now() >= end_dt:
                # Session already expired
                clear_active_session()
                return None
        return data
    except Exception:
        clear_active_session()
        return None
