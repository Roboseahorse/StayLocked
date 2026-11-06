"""
Windows-specific process and window helpers.
"""

from __future__ import annotations

import sys
from typing import Optional

HAS_WIN32 = False

if sys.platform == "win32":
    try:
        import win32gui
        import win32con
        import win32process

        HAS_WIN32 = True
    except ImportError:
        pass


# Processes that are commonly used to kill HardLock
DANGEROUS_PROCESSES = {
    "taskmgr.exe",
    "procexp.exe",
    "procexp64.exe",
    "processhacker.exe",
    "procmon.exe",
    "procmon64.exe",
}


def is_dangerous_process(name: str) -> bool:
    return name.lower() in DANGEROUS_PROCESSES


def minimize_process_windows(pid: int) -> None:
    """Minimize all visible windows belonging to the given process."""
    if not HAS_WIN32:
        return

    def callback(hwnd, _):
        try:
            _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
            if found_pid == pid and win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(callback, None)
    except Exception:
        pass


def set_window_always_on_top(hwnd: Optional[int], enable: bool = True) -> None:
    """Best-effort always-on-top for the main window."""
    if not HAS_WIN32 or hwnd is None:
        return
    try:
        flag = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(
            hwnd,
            flag,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE,
        )
    except Exception:
        pass
