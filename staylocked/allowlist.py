"""
Allowlist management helpers (including future profiles support).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Set

from staylocked.config import PROFILES_DIR, load_allowlist, save_allowlist


def get_current_allowlist() -> Set[str]:
    return load_allowlist()


def set_current_allowlist(apps: Set[str]) -> None:
    save_allowlist(apps)


def list_profiles() -> List[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def load_profile(name: str) -> Set[str]:
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        return set()
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_profile(name: str, apps: Set[str]) -> None:
    path = PROFILES_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(list(apps)), f, indent=2)


def delete_profile(name: str) -> None:
    path = PROFILES_DIR / f"{name}.json"
    if path.exists():
        path.unlink()
