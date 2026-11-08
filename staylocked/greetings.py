"""
Time-of-day greetings. Phrases come from a JSON file the user can edit
(~/.staylocked/greetings.json); {name} is replaced with the display name.
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from staylocked.config import APP_DIR

PHRASES_FILE = APP_DIR / "greetings.json"

DEFAULT_PHRASES: Dict[str, List[str]] = {
    "morning": [
        "Good morning, {name}",
        "Rise and focus, {name}",
        "A fresh start, {name}",
        "Morning, {name}. Let's make it count",
        "New day, clear mind, {name}",
    ],
    "afternoon": [
        "Good afternoon, {name}",
        "Afternoon push, {name}",
        "Keep the momentum, {name}",
        "Halfway there, {name}",
        "Still going strong, {name}",
    ],
    "evening": [
        "Good evening, {name}",
        "Evening focus, {name}",
        "One more good session, {name}",
        "Finish strong, {name}",
        "Quiet evening, loud progress, {name}",
    ],
    "night": [
        "Burning the midnight oil, {name}?",
        "Late night focus, {name}",
        "Quiet hours, {name}. Let's use them",
        "Night owl mode, {name}",
        "Still up, {name}?",
    ],
    "any": [
        "Ready to lock in, {name}?",
        "Let's get something done, {name}",
        "Distractions off, {name}",
        "One session at a time, {name}",
        "Deep work time, {name}",
        "Welcome back, {name}",
        "Time to focus, {name}",
    ],
}

_last_phrase: Optional[str] = None


def period(now: Optional[datetime] = None) -> str:
    hour = (now or datetime.now()).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def ensure_file() -> None:
    """Create the editable phrases file with defaults if it doesn't exist."""
    if PHRASES_FILE.exists():
        return
    try:
        with open(PHRASES_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PHRASES, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def reset_to_defaults() -> None:
    try:
        with open(PHRASES_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PHRASES, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def load_phrases() -> Dict[str, List[str]]:
    """Read the phrases file; fall back to defaults if it is missing or broken."""
    try:
        with open(PHRASES_FILE, encoding="utf-8") as f:
            data = json.load(f)
        cleaned: Dict[str, List[str]] = {}
        for key, value in data.items():
            if isinstance(value, list):
                phrases = [p.strip() for p in value if isinstance(p, str) and p.strip()]
                if phrases:
                    cleaned[key] = phrases
        if cleaned:
            return cleaned
    except Exception:
        pass
    return DEFAULT_PHRASES


def pick(now: Optional[datetime] = None) -> str:
    """Choose a random phrase for the current time of day (not the same twice in a row)."""
    global _last_phrase
    phrases = load_phrases()
    pool = list(phrases.get(period(now), [])) + list(phrases.get("any", []))
    if not pool:
        pool = DEFAULT_PHRASES[period(now)] + DEFAULT_PHRASES["any"]
    if len(pool) > 1 and _last_phrase in pool:
        pool.remove(_last_phrase)
    choice = random.choice(pool)
    _last_phrase = choice
    return choice


def split_name(phrase: str, name: str) -> Tuple[str, str, str]:
    """Split a phrase around {name} so the name can be coloured separately."""
    if "{name}" not in phrase:
        return phrase, "", ""
    before, _, after = phrase.partition("{name}")
    return before, name, after.replace("{name}", name)
