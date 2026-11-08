"""
StayLocked main application (CustomTkinter UI shell).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set

import customtkinter as ctk
import psutil
from tkinter import filedialog, messagebox
import tkinter as tk

from staylocked import __version__, greetings, theme
from staylocked.config import (
    APP_NAME,
    APP_VERSION,
    load_config,
    save_config,
    load_allowlist,
    save_allowlist,
    load_last_session,
    save_last_session,
)
from staylocked.session import (
    save_active_session,
    clear_active_session,
    load_active_session,
)
from staylocked.enforcer import Enforcer
from staylocked.modes import BlockRunner
from staylocked.emergency import show_emergency_stop_dialog
from staylocked.updater import check_for_updates, perform_update, ensure_installed
from staylocked.allowlist import list_profiles, load_profile, save_profile
from staylocked.theme import (
    ACCENT, ACCENT_DIM, ACCENT_HOVER, BG, BORDER, FAINT, GREEN, MUTED,
    SURFACE, SURFACE_2, SURFACE_3, TEXT, font,
)
from staylocked.widgets import Dots, TabBar, TimerRing, button, card, entry

# Optional notifications
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

MODE_LABELS = {
    "Timed": "timed",
    "Pomodoro": "pomodoro",
    "Allowance": "allowance",
    "Until restart": "restart",
}
MODE_CODES = {code: label for label, code in MODE_LABELS.items()}


def resource_path(name: str) -> str:
    """Find a bundled file when running from source or from the built exe."""
    base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
    return str(Path(base) / name)


def fmt_time(seconds: float) -> str:
    secs = max(0, int(seconds + 0.999))
    if secs >= 6000:  # 100+ minutes: H:MM:SS
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        return f"{h}:{m:02d}:{s:02d}"
    return f"{secs // 60:02d}:{secs % 60:02d}"


class StayLockedApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.title(APP_NAME)
        try:
            scale = float(self._get_window_scaling())
        except Exception:
            scale = 1.0
        avail = int(self.winfo_screenheight() / scale) - 90
        height = max(640, min(780, avail))
        self.compact = height < 740
        self.geometry(f"920x{height}")
        self.minsize(840, min(700, height))
        self.configure(fg_color=BG)

        self.config = load_config()
        self.allowlist: Set[str] = load_allowlist()
        self.is_blocking = False
        self.stop_event = threading.Event()
        self.block_mode = "timed"
        self.current_whitelist: Set[str] = set()
        self.last_duration = 25
        self.runner: Optional[BlockRunner] = None
        self.enforcer: Optional[Enforcer] = None

        # Timer ring / phase tracking
        self._cur_end: Optional[datetime] = None
        self._phase_total = 1.0
        self._phase_kind = "block"  # "block" (red) or "free" (green)
        self._phase_caption = "BLOCK ACTIVE"

        # Ensure we are running from the permanent install location
        ensure_installed()

        self.create_widgets()
        self.load_last_session_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Check for updates shortly after launch (non-blocking)
        if self.config.get("check_for_updates", True):
            self.after(1500, self._check_updates)

        # Offer to resume an interrupted session
        self.after(800, self.check_resume_session)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def load_last_session_ui(self):
        data = load_last_session()
        if "allowlist" in data:
            self.allowlist = set(data["allowlist"])
            self.refresh_allowlist_box()
        if "last_duration" in data and hasattr(self, "duration_entry"):
            self.duration_entry.delete(0, "end")
            self.duration_entry.insert(0, str(data["last_duration"]))
        mode = data.get("mode")
        if mode in MODE_CODES:
            self.mode_var.set(mode)
            self.mode_seg.set(MODE_CODES[mode])
        self.on_mode_change()

    def save_last_session_ui(self):
        data = {
            "allowlist": sorted(list(self.allowlist)),
            "last_duration": self.last_duration,
            "mode": self.block_mode,
        }
        save_last_session(data)

    def _persist_active(self):
        if not self.is_blocking or not self.runner:
            return
        save_active_session(
            is_blocking=True,
            mode=self.block_mode,
            allowlist=self.current_whitelist,
            force_close=self.config["force_close"],
            end_time=self.runner.block_end_time,
            pomodoro_state=self.runner.pomodoro_state,
        )

    def periodic_save(self):
        if self.is_blocking:
            self._persist_active()
            self.after(10000, self.periodic_save)

    # ------------------------------------------------------------------
    # UI construction: shell
    # ------------------------------------------------------------------

    def create_widgets(self):
        self.status_var = ctk.StringVar(value="Ready. Pick your apps and start a focus session.")

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(16, 4))
        ctk.CTkLabel(header, text="", image=theme.logo_image(38)).pack(side="left")
        titles = ctk.CTkFrame(header, fg_color="transparent")
        titles.pack(side="left", padx=12)
        ctk.CTkLabel(titles, text=APP_NAME, font=font(18, "bold"), text_color=TEXT,
                     anchor="w").pack(anchor="w")
        ctk.CTkLabel(titles, text="Whitelist focus blocker", font=font(11),
                     text_color=MUTED, anchor="w").pack(anchor="w")
        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkLabel(right, text=datetime.now().strftime("%a, %b %d"), font=font(13),
                     text_color=TEXT).pack(anchor="e")
        ctk.CTkLabel(right, text=f"v{APP_VERSION}", font=font(11),
                     text_color=MUTED).pack(anchor="e")

        # Tab bar + divider
        self.tabbar = TabBar(
            self,
            [("timer", "Timer", "timer"), ("allowlist", "Allowlist", "list"),
             ("settings", "Settings", "gear")],
            self.show_tab,
        )
        self.tabbar.pack(fill="x", padx=24, pady=(6, 0))
        ctk.CTkFrame(self, height=1, fg_color=BORDER, corner_radius=0).pack(fill="x")

        # Status bar (packed before the pages so it always keeps its space)
        self.status_label = ctk.CTkLabel(
            self, textvariable=self.status_var, anchor="w", font=font(12),
            text_color=MUTED, fg_color="transparent",
        )
        self.status_label.pack(side="bottom", fill="x", padx=30, pady=(0, 10))

        # Pages
        self.page_host = ctk.CTkFrame(self, fg_color="transparent")
        self.page_host.pack(fill="both", expand=True)
        self.pages: Dict[str, ctk.CTkFrame] = {
            key: ctk.CTkFrame(self.page_host, fg_color="transparent")
            for key in ("timer", "allowlist", "settings")
        }
        self.build_timer_page()
        self.build_allowlist_page()
        self.build_settings_page()
        self.show_tab("timer")
        self.refresh_greeting()
        self.update_summary()

    def show_tab(self, key: str):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill="both", expand=True)
        self.tabbar.set_active(key)

    # ------------------------------------------------------------------
    # Timer page
    # ------------------------------------------------------------------

    def build_timer_page(self):
        page = self.pages["timer"]
        c = card(page)
        c.pack(fill="both", expand=True, padx=48, pady=(14, 6))
        inner = ctk.CTkFrame(c, fg_color="transparent")
        inner.pack(expand=True, pady=10)

        # Mode pills
        self.mode_var = ctk.StringVar(value="timed")
        self.mode_seg = ctk.CTkSegmentedButton(
            inner, values=list(MODE_LABELS), command=self._on_mode_pick,
            width=500, height=38, font=font(13, "bold"), corner_radius=12, border_width=4,
            fg_color="#1D1D1D", selected_color=SURFACE_3, selected_hover_color="#383838",
            unselected_color="#1D1D1D", unselected_hover_color="#262626", text_color=TEXT,
        )
        self.mode_seg.set("Timed")
        self.mode_seg.pack()

        # Greeting (click it for a new phrase)
        greet = ctk.CTkFrame(inner, fg_color="transparent")
        greet.pack(pady=(12 if self.compact else 16, 0))
        self.greet_pre = ctk.CTkLabel(greet, text="", font=font(18, "bold"), text_color=TEXT)
        self.greet_name = ctk.CTkLabel(greet, text="", font=font(18, "bold"), text_color=ACCENT)
        self.greet_post = ctk.CTkLabel(greet, text="", font=font(18, "bold"), text_color=TEXT)
        for lbl in (self.greet_pre, self.greet_name, self.greet_post):
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda _e: self.refresh_greeting())

        # Ring
        ring_size = 196 if self.compact else 236
        self.ring = TimerRing(inner, size=ring_size, thickness=12 if self.compact else 13)
        self.ring.pack(pady=(8, 4))

        # Controls: [-5]  START  [+5]
        ctrl = ctk.CTkFrame(inner, fg_color="transparent")
        ctrl.pack(pady=(6, 8))
        circle = dict(width=46, height=46, corner_radius=23, fg_color=SURFACE_2,
                      hover_color=SURFACE_3, text_color=TEXT, border_width=1,
                      border_color=BORDER, font=font(13, "bold"),
                      text_color_disabled=FAINT)
        self.minus_btn = ctk.CTkButton(ctrl, text="−5", command=lambda: self._step(-1), **circle)
        self.minus_btn.pack(side="left", padx=14)
        self.start_btn = button(
            ctrl, "START", self.start_block, kind="primary", width=200, height=52,
            corner_radius=26, font=font(16, "bold"),
            image=theme.icon("play", 16, "#FFFFFF"), compound="left",
            text_color_disabled="#D58A8C",
        )
        self.start_btn.pack(side="left", padx=4)
        self.plus_btn = ctk.CTkButton(ctrl, text="+5", command=lambda: self._step(1), **circle)
        self.plus_btn.pack(side="left", padx=14)

        # Mode options
        self.opts_host = ctk.CTkFrame(inner, fg_color="transparent")
        self.opts_host.pack(pady=(4, 0))
        self._opt_entries: List[ctk.CTkEntry] = []
        self._build_option_frames()

        # Emergency stop (only visible during a block)
        self.stop_btn = button(
            inner, "Emergency stop…", self.request_emergency_stop, kind="danger", width=180,
        )

        # Allowlist summary link below the card
        self.allow_strip = ctk.CTkButton(
            page, text="", fg_color="transparent", hover_color=SURFACE_2, text_color=MUTED,
            font=font(13), height=34, corner_radius=17,
            command=lambda: self.show_tab("allowlist"),
        )
        self.allow_strip.pack(pady=(0, 6))

    def _labeled_entry(self, parent, label: str, value, suffix: str = "", width: int = 56):
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.pack(side="left", padx=10)
        ctk.CTkLabel(group, text=label, font=font(12), text_color=MUTED).pack(side="left", padx=(0, 6))
        e = entry(group, width=width)
        e.insert(0, str(value))
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda _e: self.update_summary())
        self._opt_entries.append(e)
        if suffix:
            ctk.CTkLabel(group, text=suffix, font=font(12), text_color=MUTED).pack(side="left", padx=(6, 0))
        return e

    def _build_option_frames(self):
        host = self.opts_host

        # Timed: presets + custom
        self.timed_frame = ctk.CTkFrame(host, fg_color="transparent")
        chips = ctk.CTkFrame(self.timed_frame, fg_color="transparent")
        chips.pack()
        self.chip_buttons: Dict[int, ctk.CTkButton] = {}
        for m in (15, 25, 45, 60, 90, 120):
            b = ctk.CTkButton(
                chips, text=str(m), width=50, height=30, corner_radius=15, font=font(12, "bold"),
                fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT, border_width=1,
                border_color=BORDER, text_color_disabled=FAINT,
                command=lambda x=m: self.set_duration(x),
            )
            b.pack(side="left", padx=3)
            self.chip_buttons[m] = b
        custom = ctk.CTkFrame(self.timed_frame, fg_color="transparent")
        custom.pack(pady=(10, 0))
        self.duration_entry = self._labeled_entry(custom, "Custom", "25", "min", width=64)

        # Pomodoro
        self.pomo_frame = ctk.CTkFrame(host, fg_color="transparent")
        row = ctk.CTkFrame(self.pomo_frame, fg_color="transparent")
        row.pack()
        self.pomo_work = self._labeled_entry(row, "Work", self.config["pomodoro_work"], "min")
        self.pomo_break = self._labeled_entry(row, "Break", self.config["pomodoro_break"], "min")
        self.pomo_cycles = self._labeled_entry(row, "Cycles", "4", "", width=48)
        sess = ctk.CTkFrame(self.pomo_frame, fg_color="transparent")
        sess.pack(pady=(12, 0))
        ctk.CTkLabel(sess, text="SESSION", font=font(11, "bold"), text_color=MUTED).pack(side="left", padx=(0, 10))
        self.pomo_dots = Dots(sess)
        self.pomo_dots.pack(side="left")
        self.pomo_count = ctk.CTkLabel(sess, text="0 / 4", font=font(11, "bold"), text_color=MUTED)
        self.pomo_count.pack(side="left", padx=(10, 0))

        # Allowance
        self.allow_frame = ctk.CTkFrame(host, fg_color="transparent")
        arow = ctk.CTkFrame(self.allow_frame, fg_color="transparent")
        arow.pack()
        self.allowance_entry = self._labeled_entry(arow, "Free time", "10", "min")
        self.allow_block_entry = self._labeled_entry(arow, "then block for", "50", "min")

        # Until restart
        self.restart_frame = ctk.CTkFrame(host, fg_color="transparent")
        ctk.CTkLabel(
            self.restart_frame,
            text="The block stays active until you restart your computer.",
            font=font(12), text_color=MUTED,
        ).pack()

        self.on_mode_change()

    # -- mode handling ---------------------------------------------------

    def _on_mode_pick(self, label: str):
        self.mode_var.set(MODE_LABELS[label])
        self.on_mode_change()

    def on_mode_change(self):
        mode = self.mode_var.get()
        for f in (self.timed_frame, self.pomo_frame, self.allow_frame, self.restart_frame):
            f.pack_forget()
        {"timed": self.timed_frame, "pomodoro": self.pomo_frame,
         "allowance": self.allow_frame, "restart": self.restart_frame}[mode].pack()
        self.update_summary()

    def set_duration(self, mins: int):
        self.duration_entry.delete(0, "end")
        self.duration_entry.insert(0, str(mins))
        self.update_summary()

    @staticmethod
    def _int(widget, default: int = 0) -> int:
        try:
            return max(0, int(widget.get()))
        except (ValueError, AttributeError):
            return default

    def _step(self, direction: int):
        """Minus / plus button: nudge the main value (idle) or extend the block (active)."""
        if self.is_blocking:
            if direction > 0:
                self.extend_block(10)
            return
        mode = self.mode_var.get()
        target = {"timed": self.duration_entry, "pomodoro": self.pomo_work,
                  "allowance": self.allowance_entry}.get(mode)
        if target is None:
            return
        value = max(1, min(999, self._int(target, 25) + 5 * direction))
        target.delete(0, "end")
        target.insert(0, str(value))
        self.update_summary()

    def _refresh_steppers(self):
        if self.is_blocking:
            self.minus_btn.configure(text="−5", state="disabled")
            can_extend = self.block_mode == "timed"
            self.plus_btn.configure(text="+10", state="normal" if can_extend else "disabled")
        else:
            usable = self.mode_var.get() != "restart"
            self.minus_btn.configure(text="−5", state="normal" if usable else "disabled")
            self.plus_btn.configure(text="+5", state="normal" if usable else "disabled")

    def update_summary(self):
        """Refresh everything that reflects the current settings while idle."""
        if not hasattr(self, "ring") or not hasattr(self, "allow_strip"):
            return

        n = len(self.allowlist)
        if n:
            self.allow_strip.configure(
                text=f"{n} app{'s' if n != 1 else ''} allowed   ·   Edit allowlist",
                text_color=MUTED)
        else:
            self.allow_strip.configure(
                text="No apps on your allowlist yet   ·   Add apps", text_color=ACCENT)

        if self.is_blocking:
            return

        mode = self.mode_var.get()
        total_cycles = max(1, self._int(self.pomo_cycles, 4))
        if mode == "timed":
            minutes = self._int(self.duration_entry, 25)
            text, caption = fmt_time(minutes * 60), "FOCUS BLOCK"
        elif mode == "pomodoro":
            text, caption = fmt_time(self._int(self.pomo_work, 25) * 60), "POMODORO  ·  WORK"
        elif mode == "allowance":
            text, caption = fmt_time(self._int(self.allowance_entry, 10) * 60), "ALLOWANCE FIRST"
        else:
            text, caption = "∞", "UNTIL RESTART"
        self.ring.set_time(text)
        self.ring.set_caption(caption)
        self.ring.set_ring(1.0, ACCENT)
        self.pomo_dots.set(0, total_cycles)
        self.pomo_count.configure(text=f"0 / {total_cycles}")

        current = self._int(self.duration_entry, -1)
        for m, b in self.chip_buttons.items():
            if m == current:
                b.configure(fg_color=ACCENT_DIM, border_color=ACCENT, text_color="#FF9B9D")
            else:
                b.configure(fg_color=SURFACE_2, border_color=BORDER, text_color=TEXT)
        self._refresh_steppers()

    # -- greeting ---------------------------------------------------------

    def refresh_greeting(self):
        name = (self.config.get("user_name") or "Friend").strip() or "Friend"
        pre, nm, post = greetings.split_name(greetings.pick(), name)
        self.greet_pre.configure(text=pre)
        self.greet_name.configure(text=nm)
        self.greet_post.configure(text=post)

    # ------------------------------------------------------------------
    # Allowlist page
    # ------------------------------------------------------------------

    def build_allowlist_page(self):
        page = self.pages["allowlist"]
        c = card(page)
        c.pack(fill="both", expand=True, padx=48, pady=(14, 10))

        head = ctk.CTkFrame(c, fg_color="transparent")
        head.pack(fill="x", padx=24, pady=(20, 8))
        titles = ctk.CTkFrame(head, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text="Allowlist", font=font(20, "bold"), text_color=TEXT).pack(anchor="w")
        self.allow_count_label = ctk.CTkLabel(
            titles, text="Only listed apps are allowed during a block", font=font(12), text_color=MUTED)
        self.allow_count_label.pack(anchor="w")

        prof = ctk.CTkFrame(head, fg_color="transparent")
        prof.pack(side="right")
        self.profile_var = ctk.StringVar(value="Profiles")
        self.profile_menu = ctk.CTkOptionMenu(
            prof, variable=self.profile_var, values=["(current)"] + list_profiles(),
            width=150, height=34, corner_radius=17, font=font(13),
            fg_color=SURFACE_2, button_color=SURFACE_3, button_hover_color="#3A3A3A",
            text_color=TEXT, dropdown_fg_color=SURFACE_2, dropdown_text_color=TEXT,
            dropdown_hover_color=SURFACE_3, command=self._on_profile_selected,
        )
        self.profile_menu.pack(side="left", padx=(0, 8))
        button(prof, "Save as…", self._save_profile_dialog, kind="secondary", width=86, height=34).pack(side="left")

        list_wrap = ctk.CTkFrame(c, fg_color=SURFACE_2, corner_radius=14)
        list_wrap.pack(fill="both", expand=True, padx=24, pady=8)
        self.allow_listbox = tk.Listbox(
            list_wrap, selectmode="extended", bg=SURFACE_2, fg=TEXT, selectbackground=ACCENT,
            selectforeground="#FFFFFF", highlightthickness=0, bd=0, relief="flat",
            activestyle="none", font=("Segoe UI", 12),
        )
        self.allow_listbox.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=12)
        scrollbar = ctk.CTkScrollbar(list_wrap, command=self.allow_listbox.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 4), pady=10)
        self.allow_listbox.config(yscrollcommand=scrollbar.set)
        self.allow_empty = ctk.CTkLabel(
            list_wrap, text="No apps yet.\nUse “Add running apps” to pick from what's open.",
            font=font(13), text_color=MUTED, fg_color=SURFACE_2, justify="center")

        row1 = ctk.CTkFrame(c, fg_color="transparent")
        row1.pack(fill="x", padx=24, pady=(8, 4))
        button(row1, "Add running apps", self.add_running_apps, kind="primary", width=150).pack(side="left", padx=(0, 8))
        button(row1, "Add EXE / name", self.add_manual, kind="secondary", width=130).pack(side="left", padx=(0, 8))
        button(row1, "Remove selected", self.remove_selected, kind="danger", width=140).pack(side="left", padx=(0, 8))
        button(row1, "Clear all", self.clear_allowlist, kind="ghost", width=90).pack(side="left")

        row2 = ctk.CTkFrame(c, fg_color="transparent")
        row2.pack(fill="x", padx=24, pady=(0, 20))
        button(row2, "Export", self.export_allowlist, kind="ghost", width=90, height=32).pack(side="left", padx=(0, 8))
        button(row2, "Import", self.import_allowlist, kind="ghost", width=90, height=32).pack(side="left")

        self.refresh_allowlist_box()

    def refresh_allowlist_box(self):
        self.allow_listbox.delete(0, "end")
        for app in sorted(self.allowlist):
            self.allow_listbox.insert("end", app)
        n = len(self.allowlist)
        self.allow_count_label.configure(
            text=f"{n} app{'s' if n != 1 else ''} allowed during a block" if n
            else "Only listed apps are allowed during a block")
        if n:
            self.allow_empty.place_forget()
        else:
            self.allow_empty.place(relx=0.5, rely=0.45, anchor="center")
        self.update_summary()

    def add_running_apps(self):
        from staylocked.running_apps import show_running_apps_dialog

        def on_add(names):
            self.allowlist.update(names)
            save_allowlist(self.allowlist)
            self.refresh_allowlist_box()

        show_running_apps_dialog(self, on_add, already=self.allowlist)

    def add_manual(self):
        dialog = ctk.CTkInputDialog(
            text="Enter process name (e.g. code.exe or chrome)\nor full path to .exe:",
            title="Add Application",
        )
        value = dialog.get_input()
        if value:
            name = (
                Path(value).name.lower()
                if value.lower().endswith((".exe", ".app"))
                else value.lower()
            )
            self.allowlist.add(name)
            save_allowlist(self.allowlist)
            self.refresh_allowlist_box()

    def remove_selected(self):
        selected = [self.allow_listbox.get(i) for i in self.allow_listbox.curselection()]
        for s in selected:
            self.allowlist.discard(s)
        save_allowlist(self.allowlist)
        self.refresh_allowlist_box()

    def clear_allowlist(self):
        if messagebox.askyesno("Confirm", "Clear entire allowlist?"):
            self.allowlist.clear()
            save_allowlist(self.allowlist)
            self.refresh_allowlist_box()

    def export_allowlist(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON", "*.json"), ("All", "*.*")]
        )
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sorted(list(self.allowlist)), f, indent=2)
            self.notify("Allowlist exported")

    def import_allowlist(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                    self.allowlist.update(data)
                save_allowlist(self.allowlist)
                self.refresh_allowlist_box()
                self.notify("Allowlist imported")
            except Exception as e:
                messagebox.showerror("Error", f"Could not import: {e}")

    def _on_profile_selected(self, name: str):
        if name and name != "(current)":
            apps = load_profile(name)
            if apps:
                self.allowlist = apps
                save_allowlist(self.allowlist)
                self.refresh_allowlist_box()
                self.notify(f"Loaded profile “{name}”")

    def _save_profile_dialog(self):
        dialog = ctk.CTkInputDialog(text="Profile name:", title="Save Allowlist as Profile")
        name = dialog.get_input()
        if name:
            name = name.strip()
            if name:
                save_profile(name, self.allowlist)
                self.profile_menu.configure(values=["(current)"] + list_profiles())
                self.profile_var.set(name)
                self.notify(f"Profile “{name}” saved")

    # ------------------------------------------------------------------
    # Settings page
    # ------------------------------------------------------------------

    def _section(self, parent, title: str, subtitle: str = ""):
        c = card(parent, corner_radius=16)
        c.pack(fill="x", padx=2, pady=6)
        ctk.CTkLabel(c, text=title, font=font(15, "bold"), text_color=TEXT).pack(
            anchor="w", padx=20, pady=(16, 0))
        if subtitle:
            ctk.CTkLabel(c, text=subtitle, font=font(12), text_color=MUTED, wraplength=640,
                         justify="left").pack(anchor="w", padx=20, pady=(2, 0))
        body = ctk.CTkFrame(c, fg_color="transparent")
        body.pack(fill="x", padx=20, pady=(8, 16))
        return body

    def _checkbox(self, parent, text: str, variable):
        return ctk.CTkCheckBox(
            parent, text=text, variable=variable, command=self.update_config,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, border_color=FAINT,
            text_color=TEXT, font=font(13), checkbox_width=20, checkbox_height=20,
        )

    def build_settings_page(self):
        page = self.pages["settings"]
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=36, pady=(8, 8))

        # Personalise
        body = self._section(
            scroll, "Personalise",
            "Your name appears in the greeting on the Timer screen. Click the greeting there for a new phrase.")
        name_row = ctk.CTkFrame(body, fg_color="transparent")
        name_row.pack(anchor="w", pady=(6, 0))
        ctk.CTkLabel(name_row, text="Display name", font=font(13), text_color=TEXT).pack(side="left", padx=(0, 10))
        self.name_entry = entry(name_row, width=200, justify="left")
        self.name_entry.insert(0, self.config.get("user_name", "Friend"))
        self.name_entry.pack(side="left", padx=(0, 8))
        self.name_entry.bind("<Return>", lambda _e: self.save_name())
        self.name_entry.bind("<FocusOut>", lambda _e: self.save_name())
        button(name_row, "Save", self.save_name, kind="secondary", width=70, height=34).pack(side="left")
        phr = ctk.CTkFrame(body, fg_color="transparent")
        phr.pack(anchor="w", pady=(12, 0))
        button(phr, "New greeting", self.refresh_greeting, kind="secondary", width=120, height=34).pack(side="left", padx=(0, 8))
        button(phr, "Edit phrases file", self.open_phrases_file, kind="secondary", width=140, height=34).pack(side="left", padx=(0, 8))
        button(phr, "Reset phrases", self.reset_phrases, kind="ghost", width=120, height=34).pack(side="left")
        ctk.CTkLabel(
            body, text="Phrases are listed by time of day in a simple text file. Use {name} where your name should go.",
            font=font(11), text_color=MUTED).pack(anchor="w", pady=(8, 0))

        # Blocking
        body = self._section(scroll, "Blocking behaviour")
        self.force_var = ctk.BooleanVar(value=self.config["force_close"])
        self._checkbox(body, "Force-close non-whitelisted apps (recommended)", self.force_var).pack(anchor="w", pady=4)
        self.notify_var = ctk.BooleanVar(value=self.config["notifications"])
        self._checkbox(body, "Show desktop notifications", self.notify_var).pack(anchor="w", pady=4)
        self.update_var = ctk.BooleanVar(value=self.config.get("check_for_updates", True))
        self._checkbox(body, "Check for updates on launch", self.update_var).pack(anchor="w", pady=4)
        self.protect_tm_var = ctk.BooleanVar(value=self.config.get("protect_task_manager", False))
        self._checkbox(body, "Also block Task Manager / Process Explorer (aggressive)", self.protect_tm_var).pack(anchor="w", pady=4)
        irow = ctk.CTkFrame(body, fg_color="transparent")
        irow.pack(anchor="w", pady=(10, 0))
        ctk.CTkLabel(irow, text="Check interval", font=font(13), text_color=TEXT).pack(side="left", padx=(0, 10))
        self.interval_entry = entry(irow, width=70)
        self.interval_entry.insert(0, str(self.config["check_interval"]))
        self.interval_entry.pack(side="left")
        self.interval_entry.bind("<FocusOut>", lambda _e: self.update_config())
        ctk.CTkLabel(irow, text="seconds", font=font(12), text_color=MUTED).pack(side="left", padx=(8, 0))

        # Emergency
        body = self._section(
            scroll, "Emergency stop password",
            "Optional but recommended. If set, you must enter this password plus a confirmation "
            "phrase to stop a block early. During a block the rest of the app is locked.")
        pw_row = ctk.CTkFrame(body, fg_color="transparent")
        pw_row.pack(anchor="w", pady=(6, 0))
        self.pw_entry = entry(pw_row, width=220, show="•", justify="left")
        self.pw_entry.insert(0, self.config.get("emergency_password", ""))
        self.pw_entry.pack(side="left", padx=(0, 8))
        button(pw_row, "Save password", self.save_password, kind="secondary", width=130, height=34).pack(side="left")

        ctk.CTkLabel(scroll, text=f"StayLocked v{APP_VERSION}", font=font(11), text_color=FAINT).pack(pady=(10, 14))

    def save_name(self):
        name = self.name_entry.get().strip() or "Friend"
        self.config["user_name"] = name
        save_config(self.config)
        self.refresh_greeting()

    def open_phrases_file(self):
        greetings.ensure_file()
        path = str(greetings.PHRASES_FILE)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Could not open file", f"{path}\n\n{e}")

    def reset_phrases(self):
        if messagebox.askyesno("Reset phrases", "Replace your greeting phrases with the defaults?"):
            greetings.reset_to_defaults()
            self.refresh_greeting()

    def update_config(self):
        self.config["force_close"] = self.force_var.get()
        self.config["notifications"] = self.notify_var.get()
        self.config["check_for_updates"] = self.update_var.get()
        self.config["protect_task_manager"] = self.protect_tm_var.get()
        try:
            self.config["check_interval"] = float(self.interval_entry.get())
        except ValueError:
            pass
        save_config(self.config)

    def save_password(self):
        self.config["emergency_password"] = self.pw_entry.get()
        save_config(self.config)
        messagebox.showinfo("Saved", "Emergency password updated.")

    # ------------------------------------------------------------------
    # Blocking
    # ------------------------------------------------------------------

    def _apply_status(self, msg: str):
        """Show a runner status message and update the ring's phase colour/caption."""
        self.status_var.set(msg)
        m = re.match(r"POMODORO (WORK|BREAK) \((\d+)/(\d+)\)", msg)
        if m:
            phase, cycle, total = m.group(1), int(m.group(2)), int(m.group(3))
            if phase == "WORK":
                self._phase_kind = "block"
                self._phase_caption = f"POMODORO  ·  WORK {cycle}/{total}"
                self.pomo_dots.set(cycle - 1, total, active=True)
                self.pomo_count.configure(text=f"{cycle - 1} / {total}")
            else:
                self._phase_kind = "free"
                self._phase_caption = f"BREAK {cycle}/{total}  ·  APPS FREE"
                self.pomo_dots.set(cycle, total, active=False)
                self.pomo_count.configure(text=f"{cycle} / {total}")
        elif msg.startswith("ALLOWANCE"):
            self._phase_kind = "free"
            self._phase_caption = "ALLOWANCE  ·  APPS FREE"
        elif msg.startswith("BLOCK ACTIVE"):
            self._phase_kind = "block"
            self._phase_caption = "BLOCK ACTIVE"

    def _set_active_ui(self, active: bool):
        self.mode_seg.configure(state="disabled" if active else "normal")
        self.tabbar.set_enabled(not active)
        state = "disabled" if active else "normal"
        for e in self._opt_entries:
            e.configure(state=state)
        for b in self.chip_buttons.values():
            b.configure(state=state)
        if active:
            self.start_btn.configure(
                text="LOCKED IN", state="disabled", fg_color=ACCENT_DIM,
                image=theme.icon("lock", 16, "#D58A8C"))
            self.stop_btn.pack(pady=(14, 0))
        else:
            self.start_btn.configure(
                text="START", state="normal", fg_color=ACCENT,
                image=theme.icon("play", 16, "#FFFFFF"))
            self.stop_btn.pack_forget()
        self._refresh_steppers()

    def start_block(self, resume: bool = False, resume_data: Optional[dict] = None):
        if not resume and not self.allowlist:
            messagebox.showwarning(
                "Empty Allowlist",
                "Please add at least one application to the allowlist first.",
            )
            self.show_tab("allowlist")
            return

        self.update_config()

        if not resume:
            self.current_whitelist = {a.lower() for a in self.allowlist}
            self.block_mode = self.mode_var.get()
        else:
            self.current_whitelist = set(resume_data.get("allowlist", []))
            self.block_mode = resume_data.get("mode", "timed")
            self.config["force_close"] = resume_data.get("force_close", True)
            if self.block_mode in MODE_CODES:
                self.mode_var.set(self.block_mode)
                self.mode_seg.set(MODE_CODES[self.block_mode])
                self.on_mode_change()

        self.stop_event.clear()
        self.is_blocking = True
        self._cur_end = None
        self._phase_kind = "block"
        self._phase_caption = "BLOCK ACTIVE"
        self._set_active_ui(True)
        self.show_tab("timer")

        self.enforcer = Enforcer(
            whitelist=self.current_whitelist,
            force_close=self.config["force_close"],
            protect_task_manager=self.config.get("protect_task_manager", False),
        )

        def status_cb(msg: str):
            self.after(0, lambda: self._apply_status(msg))

        def notify_cb(msg: str):
            self.after(0, lambda: self.notify(msg))

        def finished_cb():
            self.after(0, self.end_block)

        self.runner = BlockRunner(
            enforcer=self.enforcer,
            stop_event=self.stop_event,
            check_interval=self.config["check_interval"],
            on_status=status_cb,
            on_notify=notify_cb,
            on_finished=finished_cb,
        )

        try:
            if self.block_mode == "timed":
                if resume and resume_data and resume_data.get("end_time"):
                    end = datetime.fromisoformat(resume_data["end_time"])
                    self.runner.start_timed(0, resume_end=end)
                else:
                    mins = int(self.duration_entry.get())
                    self.last_duration = mins
                    self.runner.start_timed(mins)
            elif self.block_mode == "restart":
                self.runner.start_until_restart()
            elif self.block_mode == "pomodoro":
                work = int(self.pomo_work.get())
                brk = int(self.pomo_break.get())
                cycles = int(self.pomo_cycles.get())
                resume_state = "work"
                resume_end = None
                if resume and resume_data:
                    resume_state = resume_data.get("pomodoro_state", "work")
                    if resume_data.get("end_time"):
                        resume_end = datetime.fromisoformat(resume_data["end_time"])
                self.pomo_dots.set(0, cycles, active=True)
                self.runner.start_pomodoro(work, brk, cycles, resume_state, resume_end)
            elif self.block_mode == "allowance":
                allow_mins = int(self.allowance_entry.get())
                block_mins = int(self.allow_block_entry.get())
                self._apply_status("ALLOWANCE — free use of all apps")
                self.runner.start_allowance(allow_mins, block_mins)

            self.save_last_session_ui()
            self._persist_active()
            if not resume:
                self.notify("StayLocked session started. Stay strong.")
            if self.block_mode != "allowance":
                self._apply_status("BLOCK ACTIVE — only allowlisted apps permitted")
            self.after(200, self.update_timer_display)
            self.after(10000, self.periodic_save)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.end_block()

    def extend_block(self, minutes: int = 10):
        if not self.is_blocking or not self.runner or not self.runner.block_end_time:
            return
        self.runner.block_end_time += timedelta(minutes=minutes)
        self.last_duration += minutes
        # keep the ring continuous instead of treating this as a new phase
        if self._cur_end is not None:
            self._cur_end += timedelta(minutes=minutes)
            self._phase_total += minutes * 60
        self._persist_active()
        self.notify(f"Extended by {minutes} minutes")

    def update_timer_display(self):
        if not self.is_blocking or not self.runner:
            return
        end = self.runner.block_end_time
        if end:
            remaining = max(0.0, (end - datetime.now()).total_seconds())
            if self._cur_end is None or abs((end - self._cur_end).total_seconds()) > 1.5:
                self._cur_end = end
                self._phase_total = max(remaining, 1.0)
            self.ring.set_time(fmt_time(remaining))
            self.ring.set_ring(
                remaining / self._phase_total,
                GREEN if self._phase_kind == "free" else ACCENT,
            )
        else:
            self.ring.set_time("∞")
            self.ring.set_ring(1.0, ACCENT)
        self.ring.set_caption(self._phase_caption)
        self.after(500, self.update_timer_display)

    def end_block(self):
        self.is_blocking = False
        self.stop_event.set()
        clear_active_session()
        self._cur_end = None
        self._set_active_ui(False)
        self.status_var.set("Ready. Pick your apps and start a focus session.")
        self.notify("StayLocked session ended.")
        self.runner = None
        self.enforcer = None
        self.refresh_greeting()
        self.update_summary()

    def request_emergency_stop(self):
        if not self.is_blocking:
            return

        def confirmed():
            self.stop_event.set()
            self.end_block()
            self.notify("Block stopped by emergency override.")

        show_emergency_stop_dialog(
            self,
            emergency_password=self.config.get("emergency_password", ""),
            on_confirmed=confirmed,
        )

    # ------------------------------------------------------------------
    # Session resume & updates
    # ------------------------------------------------------------------

    def check_resume_session(self):
        data = load_active_session()
        if not data:
            return
        remaining = ""
        end = data.get("end_time")
        if end:
            secs = (datetime.fromisoformat(end) - datetime.now()).total_seconds()
            remaining = f"\nRemaining: ~{int(secs // 60)} minutes"
        if messagebox.askyesno(
            "Resume StayLocked Session?",
            f"An interrupted focus session was found.{remaining}\n\n"
            "Would you like to resume it now?",
        ):
            self.start_block(resume=True, resume_data=data)

    def _check_updates(self):
        def on_available(latest: str, url: str):
            self.after(0, lambda: self._offer_update(latest, url))

        check_for_updates(
            current_version=APP_VERSION,
            update_url=self.config.get("update_url"),
            on_update_available=on_available,
        )

    def _offer_update(self, latest: str, download_url: str):
        if messagebox.askyesno(
            "Update Available",
            f"A new version ({latest}) is available.\n\n"
            f"You are running {APP_VERSION}.\n\n"
            "Download and install automatically now?\n"
            "StayLocked will restart and resume any active session.",
        ):
            self._persist_active()
            perform_update(
                download_url,
                latest,
                on_status=lambda s: self.status_var.set(s),
                on_error=lambda e: messagebox.showerror("Update failed", e),
            )

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def notify(self, message: str):
        if self.config.get("notifications") and HAS_PLYER:
            try:
                notification.notify(
                    title=APP_NAME,
                    message=message,
                    app_name=APP_NAME,
                    timeout=4,
                )
            except Exception:
                pass

    def on_close(self):
        if self.is_blocking:
            messagebox.showwarning(
                "Block Active",
                "A focus block is running.\n"
                "Use the Emergency Stop button on the Timer tab\n"
                "(requires password + phrase confirmation).",
            )
            return
        self.destroy()


def main():
    app = StayLockedApp()
    app.mainloop()
