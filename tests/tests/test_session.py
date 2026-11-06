"""Basic tests for session persistence."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from staylocked.session import (
    save_active_session,
    load_active_session,
    clear_active_session,
)
from staylocked import config as cfg


def test_save_and_load_session(tmp_path, monkeypatch):
    session_file = tmp_path / "active_session.json"
    monkeypatch.setattr(cfg, "SESSION_FILE", session_file)
    monkeypatch.setattr("hardlock.session.SESSION_FILE", session_file)

    end = datetime.now() + timedelta(minutes=30)
    save_active_session(
        is_blocking=True,
        mode="timed",
        allowlist={"code.exe", "chrome.exe"},
        force_close=True,
        end_time=end,
        pomodoro_state="work",
    )

    data = load_active_session()
    assert data is not None
    assert data["mode"] == "timed"
    assert set(data["allowlist"]) == {"code.exe", "chrome.exe"}
    assert data["force_close"] is True

    clear_active_session()
    assert load_active_session() is None


def test_expired_session_is_cleared(tmp_path, monkeypatch):
    session_file = tmp_path / "active_session.json"
    monkeypatch.setattr(cfg, "SESSION_FILE", session_file)
    monkeypatch.setattr("hardlock.session.SESSION_FILE", session_file)

    end = datetime.now() - timedelta(minutes=5)  # already expired
    save_active_session(
        is_blocking=True,
        mode="timed",
        allowlist={"code.exe"},
        force_close=True,
        end_time=end,
    )

    assert load_active_session() is None
