"""
Block mode runners: timed, until-restart, pomodoro, allowance.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Optional

from staylocked.enforcer import Enforcer


class BlockRunner:
    """Runs a focus session in a background thread."""

    def __init__(
        self,
        enforcer: Enforcer,
        stop_event: threading.Event,
        check_interval: float = 1.5,
        on_status: Optional[Callable[[str], None]] = None,
        on_notify: Optional[Callable[[str], None]] = None,
        on_finished: Optional[Callable[[], None]] = None,
    ):
        self.enforcer = enforcer
        self.stop_event = stop_event
        self.check_interval = check_interval
        self.on_status = on_status or (lambda s: None)
        self.on_notify = on_notify or (lambda m: None)
        self.on_finished = on_finished or (lambda: None)

        self.block_end_time: Optional[datetime] = None
        self.pomodoro_state = "work"
        self.thread: Optional[threading.Thread] = None

    def start_timed(self, minutes: int, resume_end: Optional[datetime] = None) -> None:
        if resume_end:
            self.block_end_time = resume_end
        else:
            self.block_end_time = datetime.now() + timedelta(minutes=minutes)
        self.thread = threading.Thread(target=self._run_timed, daemon=True)
        self.thread.start()

    def start_until_restart(self) -> None:
        self.block_end_time = None
        self.thread = threading.Thread(target=self._run_until_restart, daemon=True)
        self.thread.start()

    def start_pomodoro(
        self,
        work_min: int = 25,
        break_min: int = 5,
        cycles: int = 4,
        resume_state: str = "work",
        resume_end: Optional[datetime] = None,
    ) -> None:
        self.pomodoro_state = resume_state
        self.thread = threading.Thread(
            target=self._run_pomodoro,
            args=(work_min, break_min, cycles, resume_end),
            daemon=True,
        )
        self.thread.start()

    def start_allowance(self, allow_min: int = 10, block_min: int = 50) -> None:
        self.thread = threading.Thread(
            target=self._run_allowance,
            args=(allow_min, block_min),
            daemon=True,
        )
        self.thread.start()

    # ------------------------------------------------------------------
    # Internal runners
    # ------------------------------------------------------------------

    def _run_timed(self) -> None:
        while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
            self.enforcer.enforce_once()
            time.sleep(self.check_interval)
        if not self.stop_event.is_set():
            self.on_notify("Block finished! Great work.")
        self.on_finished()

    def _run_until_restart(self) -> None:
        while not self.stop_event.is_set():
            self.enforcer.enforce_once()
            time.sleep(self.check_interval)
        self.on_finished()

    def _run_pomodoro(
        self,
        work: int,
        brk: int,
        cycles: int,
        resume_end: Optional[datetime] = None,
    ) -> None:
        start_cycle = 0
        # Simple resume: if we have a remaining end time, treat current phase as ongoing
        if resume_end and resume_end > datetime.now():
            self.block_end_time = resume_end
            while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
                if self.pomodoro_state == "work":
                    self.enforcer.enforce_once()
                time.sleep(self.check_interval if self.pomodoro_state == "work" else 1)

        for c in range(start_cycle, cycles):
            if self.stop_event.is_set():
                break

            # Work phase
            self.pomodoro_state = "work"
            self.block_end_time = datetime.now() + timedelta(minutes=work)
            self.on_status(f"POMODORO WORK ({c + 1}/{cycles})")
            while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
                self.enforcer.enforce_once()
                time.sleep(self.check_interval)

            if self.stop_event.is_set():
                break

            # Break phase
            self.pomodoro_state = "break"
            self.block_end_time = datetime.now() + timedelta(minutes=brk)
            self.on_status(f"POMODORO BREAK ({c + 1}/{cycles}) — apps free")
            self.on_notify("Break time! Stretch.")
            while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
                time.sleep(1)

        if not self.stop_event.is_set():
            self.on_notify("Pomodoro session complete!")
        self.on_finished()

    def _run_allowance(self, allow_mins: int, block_mins: int) -> None:
        # Free time first
        self.block_end_time = datetime.now() + timedelta(minutes=allow_mins)
        self.on_status("ALLOWANCE — free use of all apps")
        while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
            time.sleep(1)

        if self.stop_event.is_set():
            self.on_finished()
            return

        self.on_notify("Allowance over. HardLock block starting now.")
        self.block_end_time = datetime.now() + timedelta(minutes=block_mins)
        self.on_status("BLOCK ACTIVE after allowance")

        while not self.stop_event.is_set() and datetime.now() < self.block_end_time:
            self.enforcer.enforce_once()
            time.sleep(self.check_interval)

        self.on_finished()
