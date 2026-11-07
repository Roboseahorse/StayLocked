"""
Platform-specific helpers (Windows / macOS / Linux).
"""

from staylocked.platform.windows import (
    HAS_WIN32,
    minimize_process_windows,
    is_dangerous_process,
)

__all__ = [
    "HAS_WIN32",
    "minimize_process_windows",
    "is_dangerous_process",
]
