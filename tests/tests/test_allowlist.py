"""Basic tests for allowlist / profile helpers."""

import json
from pathlib import Path

import pytest

from staylocked.config import PROFILES_DIR, APP_DIR
from staylocked.allowlist import (
    list_profiles,
    load_profile,
    save_profile,
    delete_profile,
)


def test_save_and_load_profile(tmp_path, monkeypatch):
    # Redirect profiles dir for the test
    monkeypatch.setattr("hardlock.allowlist.PROFILES_DIR", tmp_path)
    monkeypatch.setattr("hardlock.config.PROFILES_DIR", tmp_path)

    apps = {"code.exe", "chrome.exe", "notepad.exe"}
    save_profile("work", apps)

    assert "work" in list_profiles()
    loaded = load_profile("work")
    assert loaded == apps

    delete_profile("work")
    assert "work" not in list_profiles()


def test_empty_profile(tmp_path, monkeypatch):
    monkeypatch.setattr("hardlock.allowlist.PROFILES_DIR", tmp_path)
    assert load_profile("nonexistent") == set()
