"""
Process monitoring and enforcement (force-close or minimize).
"""

from __future__ import annotations

import psutil
from typing import Set

from staylocked.platform import HAS_WIN32, minimize_process_windows, is_dangerous_process


# Always-allowed system processes (do not kill these)
SYSTEM_WHITELIST = {
    "python", "python3", "pythonw", "python.exe", "pythonw.exe",
    "hardlock", "hardlock.exe",
    "focus micromanager", "focusmicromanager",
    "explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe",
    "svchost.exe", "system", "idle",
    "finder", "dock", "windowserver",
    "sihost.exe", "taskhostw.exe", "runtimebroker.exe",
    "searchhost.exe", "startmenuexperiencehost.exe",
    "shellhost.exe", "applicationframehost.exe", "staylocked", "staylocked.exe", "ctfmon.exe", "textinputhost.exe", "searchapp.exe", "searchindexer.exe",
    "shellexperiencehost.exe", "lockapp.exe", "fontdrvhost.exe",
    "dllhost.exe", "conhost.exe", "backgroundtaskhost.exe",
    "widgets.exe", "widgetservice.exe", "securityhealthsystray.exe",
}


class Enforcer:
    """Responsible for scanning processes and applying the block policy."""

    def __init__(
        self,
        whitelist: Set[str],
        force_close: bool = True,
        protect_task_manager: bool = False,
    ):
        self.whitelist = {w.lower() for w in whitelist} | SYSTEM_WHITELIST
        self.force_close = force_close
        self.protect_task_manager = protect_task_manager

    def update_whitelist(self, whitelist: Set[str]) -> None:
        self.whitelist = {w.lower() for w in whitelist} | SYSTEM_WHITELIST

    def enforce_once(self) -> None:
        """Scan all processes and close/minimize non-whitelisted ones."""
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                name = (proc.info["name"] or "").lower()
                if not name:
                    continue

                # Always skip our own process family and system processes
                if name in self.whitelist:
                    continue
                if "staylocked" in name or "focus" in name and "micromanager" in name:
                    continue

                # Optional: treat Task Manager etc. as blocked
                if self.protect_task_manager and is_dangerous_process(name):
                    try:
                        proc.terminate()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    continue

                if name in self.whitelist:
                    continue

                if self.force_close:
                    print("blocked:", name)
                    proc.terminate()
                else:
                    if HAS_WIN32:
                        minimize_process_windows(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
