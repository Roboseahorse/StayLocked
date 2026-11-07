"""
Process monitoring and enforcement (force-close or minimize).

StayLocked – whitelist-based focus blocker.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Set

import psutil

from staylocked.platform import HAS_WIN32, minimize_process_windows, is_dangerous_process


# ---------------------------------------------------------------------------
# Always-allowed process names (case-insensitive)
# ---------------------------------------------------------------------------
SYSTEM_WHITELIST: Set[str] = {
    # StayLocked / Python runtime
    "staylocked",
    "staylocked.exe",
    "hardlock",
    "hardlock.exe",
    "python",
    "python3",
    "pythonw",
    "python.exe",
    "pythonw.exe",

    # Critical Windows core (never kill)
    "system",
    "idle",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "lsaiso.exe",
    "svchost.exe",
    "dwm.exe",
    "explorer.exe",
    "userinit.exe",
    "logonui.exe",
    "fontdrvhost.exe",

    # Shell / UI hosts
    "sihost.exe",
    "taskhostw.exe",
    "runtimebroker.exe",
    "applicationframehost.exe",
    "shellhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "searchapp.exe",
    "searchindexer.exe",
    "lockapp.exe",
    "textinputhost.exe",
    "ctfmon.exe",
    "dllhost.exe",
    "conhost.exe",
    "backgroundtaskhost.exe",
    "systemsettings.exe",
    "systemsettingsbroker.exe",

    # Audio / input
    "audiodg.exe",
    "tabtip.exe",
    "osk.exe",

    # Security / Defender
    "msmpeng.exe",
    "securityhealthservice.exe",
    "securityhealthsystray.exe",
    "smartscreen.exe",
    "nissrv.exe",

    # Common Win11 extras
    "widgets.exe",
    "widgetservice.exe",
}

# Directories that are considered system-owned (any exe under these is allowed)
_SYSTEM_DIRS = (
    Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve(),
)


def _is_under_system_dir(exe_path: str | None) -> bool:
    """Return True if the executable lives under a Windows system directory."""
    if not exe_path:
        return False
    try:
        p = Path(exe_path).resolve()
        for root in _SYSTEM_DIRS:
            try:
                p.relative_to(root)
                return True
            except ValueError:
                continue
    except Exception:
        pass
    return False


class Enforcer:
    """Scans running processes and force-closes / minimizes non-whitelisted ones."""

    def __init__(
        self,
        whitelist: Set[str],
        force_close: bool = True,
        protect_task_manager: bool = False,
        protect_system_dirs: bool = True,
    ):
        self.whitelist = {w.lower() for w in whitelist} | SYSTEM_WHITELIST
        self.force_close = force_close
        self.protect_task_manager = protect_task_manager
        self.protect_system_dirs = protect_system_dirs

    def update_whitelist(self, whitelist: Set[str]) -> None:
        self.whitelist = {w.lower() for w in whitelist} | SYSTEM_WHITELIST

    def enforce_once(self) -> None:
        """One pass over all processes – close or minimize anything not allowed."""
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if not name:
                    continue

                # 1. Explicit name whitelist
                if name in self.whitelist:
                    continue

                # 2. Our own process family
                if "staylocked" in name or "hardlock" in name:
                    continue

                # 3. Optional: treat Task Manager / Process Hacker as blocked
                if self.protect_task_manager and is_dangerous_process(name):
                    try:
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    continue

                # 4. Optional: never touch anything living under C:\Windows
                if self.protect_system_dirs and _is_under_system_dir(proc.info.get("exe")):
                    continue

                # 5. Enforce
                if self.force_close:
                    proc.terminate()
                else:
                    if HAS_WIN32:
                        minimize_process_windows(proc.info["pid"])

            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            except Exception:
                # Never let a single bad process crash the enforcer loop
                pass