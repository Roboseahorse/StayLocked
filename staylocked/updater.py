"""
GitHub Releases auto-update support.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from staylocked.config import (
    APP_NAME,
    APP_VERSION,
    INSTALL_DIR,
    INSTALL_EXE,
    UPDATE_CHECK_URL,
)


def version_gt(a: str, b: str) -> bool:
    def parts(v: str):
        nums = []
        for x in v.replace("-", ".").split("."):
            if x.isdigit():
                nums.append(int(x))
        return nums

    return parts(a) > parts(b)


def check_for_updates(
    current_version: str = APP_VERSION,
    update_url: str = UPDATE_CHECK_URL,
    on_update_available: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Non-blocking update check against GitHub Releases."""

    def worker():
        try:
            req = urllib.request.Request(
                update_url,
                headers={"User-Agent": f"{APP_NAME}/{current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            tag = data.get("tag_name", "")
            latest = tag.lstrip("v").split("-")[0]
            if not latest:
                return

            if version_gt(latest, current_version):
                assets = data.get("assets", [])
                download_url = None
                for a in assets:
                    name = a.get("name", "").lower()
                    if name == "hardlock.exe" or (name.endswith(".exe") and "hardlock" in name):
                        download_url = a.get("browser_download_url")
                        break
                if not download_url:
                    for a in assets:
                        if a.get("name", "").lower().endswith(".exe"):
                            download_url = a.get("browser_download_url")
                            break
                if download_url and on_update_available:
                    on_update_available(latest, download_url)
        except Exception:
            pass  # silent fail when offline or no releases yet

    threading.Thread(target=worker, daemon=True).start()


def perform_update(
    download_url: str,
    latest: str,
    on_status: Optional[Callable[[str], None]] = None,
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """Download the new EXE and replace + restart (Windows frozen only)."""

    def worker():
        try:
            if on_status:
                on_status("Downloading update…")

            with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as tmp:
                tmp_path = Path(tmp.name)

            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as out:
                shutil.copyfileobj(resp, out)

            if not getattr(sys, "frozen", False):
                # Running from source – just notify
                if on_status:
                    on_status(f"Update {latest} downloaded to {tmp_path}")
                return

            # Windows frozen: schedule replace + relaunch
            if sys.platform == "win32":
                INSTALL_DIR.mkdir(parents=True, exist_ok=True)
                bat = INSTALL_DIR / "update_helper.bat"
                bat.write_text(
                    f"""@echo off
timeout /t 2 /nobreak >nul
copy /Y "{tmp_path}" "{INSTALL_EXE}"
start "" "{INSTALL_EXE}"
del "%~f0"
""",
                    encoding="utf-8",
                )
                subprocess.Popen(
                    ["cmd", "/c", str(bat)],
                    creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
                )
                sys.exit(0)
        except Exception as e:
            if on_error:
                on_error(str(e))

    threading.Thread(target=worker, daemon=True).start()


def ensure_installed() -> None:
    """Copy the EXE to a permanent location on first run (Windows frozen)."""
    if not getattr(sys, "frozen", False):
        return
    if sys.platform != "win32":
        return

    current = Path(sys.executable).resolve()
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    try:
        if current == INSTALL_EXE.resolve():
            return
    except Exception:
        pass

    try:
        shutil.copy2(current, INSTALL_EXE)

        # Best-effort Start Menu shortcut
        try:
            start_menu = (
                Path(os.environ.get("APPDATA", ""))
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
            )
            start_menu.mkdir(parents=True, exist_ok=True)
            shortcut = start_menu / "HardLock.lnk"
            ps_cmd = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{shortcut}'); "
                f"$s.TargetPath = '{INSTALL_EXE}'; "
                f"$s.WorkingDirectory = '{INSTALL_DIR}'; "
                "$s.Description = 'HardLock Focus Tool'; "
                "$s.Save()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass

        subprocess.Popen([str(INSTALL_EXE)], cwd=str(INSTALL_DIR))
        sys.exit(0)
    except Exception:
        pass
