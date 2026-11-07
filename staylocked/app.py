"""
HardLock main application (CustomTkinter UI shell).
"""
from __future__ import annotations
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set

import customtkinter as ctk
import psutil
from tkinter import filedialog, messagebox
import tkinter as tk

def resource_path(name: str) -> str:
  """Find a bundled file when running from source or from the built exe."""
  base = getattr(sys, "_MEIPASS", None) or Path(__file__).resolve().parent.parent
  return str(Path(base) / name)

from staylocked import __version__
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

# Optional notifications
try:
    from plyer import notification
    HAS_PLYER = True
except ImportError:
    HAS_PLYER = False

# Swiss Design / HardLock colour system
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


class StayLockedApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.title(APP_NAME)
        self.geometry("820x680")
        self.minsize(720, 580)
        self.configure(fg_color="#1A1A1A")


        self.title(APP_NAME)
        self.geometry("820x680")
        self.minsize(720, 580)
        self.configure(fg_color="#1A1A1A")

        self.config = load_config()
        self.allowlist: Set[str] = load_allowlist()
        self.is_blocking = False
        self.stop_event = threading.Event()
        self.block_mode = "timed"
        self.current_whitelist: Set[str] = set()
        self.last_duration = 25
        self.runner: Optional[BlockRunner] = None
        self.enforcer: Optional[Enforcer] = None

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
    # UI construction
    # ------------------------------------------------------------------

    def create_widgets(self):
        # Top brand bar
        top = ctk.CTkFrame(self, fg_color="#1A1A1A", height=52, corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        brand = ctk.CTkLabel(
            top,
            text="  Staylocked",
            font=ctk.CTkFont(family="Helvetica", size=18, weight="bold"),
            text_color="#D82C2C",
        )
        brand.pack(side="left", padx=16, pady=12)

        version_lbl = ctk.CTkLabel(
            top,
            text=f"v{APP_VERSION}",
            font=ctk.CTkFont(size=11),
            text_color="#A9B2B1",
        )
        version_lbl.pack(side="left", pady=14)

        # Main tab view
        self.tabs = ctk.CTkTabview(
            self,
            width=780,
            height=560,
            fg_color="#1A1A1A",
            segmented_button_fg_color="#2A2A2A",
            segmented_button_selected_color="#D82C2C",
            segmented_button_selected_hover_color="#B82424",
            segmented_button_unselected_color="#2A2A2A",
            segmented_button_unselected_hover_color="#333333",
            text_color="#F2F2F2",
            corner_radius=8,
        )
        self.tabs.pack(padx=16, pady=(8, 6), fill="both", expand=True)

        self.tab_allow = self.tabs.add("Allowlist")
        self.tab_duration = self.tabs.add("Duration")
        self.tab_settings = self.tabs.add("Settings")
        self.tab_start = self.tabs.add("Start")

        self.build_allowlist_tab()
        self.build_duration_tab()
        self.build_settings_tab()
        self.build_start_tab()

        self.status_var = ctk.StringVar(value="Ready — select apps and start a focus session.")
        status = ctk.CTkLabel(
            self,
            textvariable=self.status_var,
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color="#A9B2B1",
            fg_color="#1A1A1A",
        )
        status.pack(fill="x", padx=20, pady=(0, 10))

    def build_allowlist_tab(self):
        frame = self.tab_allow
        ctk.CTkLabel(
            frame,
            text="Only listed apps will be allowed during a block",
            font=ctk.CTkFont(size=13),
        ).pack(pady=(10, 5))

        # Profiles row (ready for feature)
        profile_frame = ctk.CTkFrame(frame, fg_color="transparent")
        profile_frame.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(profile_frame, text="Profile:").pack(side="left", padx=(0, 6))
        self.profile_var = ctk.StringVar(value="")
        self.profile_menu = ctk.CTkOptionMenu(
            profile_frame,
            variable=self.profile_var,
            values=["(current)"] + list_profiles(),
            width=160,
            command=self._on_profile_selected,
        )
        self.profile_menu.pack(side="left", padx=4)
        ctk.CTkButton(
            profile_frame, text="Save As…", width=80, command=self._save_profile_dialog
        ).pack(side="left", padx=4)

        list_frame = ctk.CTkFrame(frame)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.allow_listbox = tk.Listbox(
            list_frame,
            selectmode="extended",
            bg="#252525",
            fg="#F2F2F2",
            selectbackground="#D82C2C",
            font=("Segoe UI", 11),
            height=12,
        )
        self.allow_listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ctk.CTkScrollbar(list_frame, command=self.allow_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.allow_listbox.config(yscrollcommand=scrollbar.set)

        btn_frame = ctk.CTkFrame(frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=10, pady=8)

        ctk.CTkButton(
            btn_frame, text="Add Running Apps", width=140, command=self.add_running_apps
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_frame, text="Add EXE / Name", width=130, command=self.add_manual
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_frame,
            text="Remove Selected",
            width=130,
            command=self.remove_selected,
            fg_color="#8B0000",
            hover_color="#A52A2A",
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_frame, text="Clear All", width=90, command=self.clear_allowlist, fg_color="#555"
        ).pack(side="left", padx=4)

        exp_frame = ctk.CTkFrame(frame, fg_color="transparent")
        exp_frame.pack(fill="x", padx=10, pady=4)
        ctk.CTkButton(
            exp_frame, text="Export Allowlist", width=130, command=self.export_allowlist
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            exp_frame, text="Import Allowlist", width=130, command=self.import_allowlist
        ).pack(side="left", padx=4)

        self.refresh_allowlist_box()

    def build_duration_tab(self):
        frame = self.tab_duration
        ctk.CTkLabel(
            frame, text="Block Mode", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(15, 5))

        self.mode_var = ctk.StringVar(value="timed")
        modes = ctk.CTkFrame(frame, fg_color="transparent")
        modes.pack(pady=5)
        ctk.CTkRadioButton(
            modes, text="Timed Block", variable=self.mode_var, value="timed", command=self.on_mode_change
        ).pack(side="left", padx=10)
        ctk.CTkRadioButton(
            modes, text="Until Restart", variable=self.mode_var, value="restart", command=self.on_mode_change
        ).pack(side="left", padx=10)
        ctk.CTkRadioButton(
            modes, text="Pomodoro", variable=self.mode_var, value="pomodoro", command=self.on_mode_change
        ).pack(side="left", padx=10)
        ctk.CTkRadioButton(
            modes, text="Allowance First", variable=self.mode_var, value="allowance", command=self.on_mode_change
        ).pack(side="left", padx=10)

        self.timed_frame = ctk.CTkFrame(frame)
        self.timed_frame.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(self.timed_frame, text="Duration (minutes):").pack(side="left", padx=10)
        self.duration_entry = ctk.CTkEntry(self.timed_frame, width=80)
        self.duration_entry.insert(0, "25")
        self.duration_entry.pack(side="left", padx=5)
        presets = ctk.CTkFrame(self.timed_frame, fg_color="transparent")
        presets.pack(side="left", padx=15)
        for m in [15, 25, 45, 60, 90, 120]:
            ctk.CTkButton(
                presets, text=str(m), width=40, command=lambda x=m: self.set_duration(x)
            ).pack(side="left", padx=2)

        self.pomo_frame = ctk.CTkFrame(frame)
        ctk.CTkLabel(self.pomo_frame, text="Work (min):").grid(row=0, column=0, padx=10, pady=5)
        self.pomo_work = ctk.CTkEntry(self.pomo_frame, width=60)
        self.pomo_work.insert(0, str(self.config["pomodoro_work"]))
        self.pomo_work.grid(row=0, column=1, padx=5)
        ctk.CTkLabel(self.pomo_frame, text="Break (min):").grid(row=0, column=2, padx=10, pady=5)
        self.pomo_break = ctk.CTkEntry(self.pomo_frame, width=60)
        self.pomo_break.insert(0, str(self.config["pomodoro_break"]))
        self.pomo_break.grid(row=0, column=3, padx=5)
        ctk.CTkLabel(self.pomo_frame, text="Cycles:").grid(row=0, column=4, padx=10)
        self.pomo_cycles = ctk.CTkEntry(self.pomo_frame, width=50)
        self.pomo_cycles.insert(0, "4")
        self.pomo_cycles.grid(row=0, column=5, padx=5)

        self.allow_frame = ctk.CTkFrame(frame)
        ctk.CTkLabel(self.allow_frame, text="Allowance minutes:").pack(side="left", padx=10)
        self.allowance_entry = ctk.CTkEntry(self.allow_frame, width=70)
        self.allowance_entry.insert(0, "10")
        self.allowance_entry.pack(side="left", padx=5)
        ctk.CTkLabel(self.allow_frame, text="then block for (min):").pack(side="left", padx=10)
        self.allow_block_entry = ctk.CTkEntry(self.allow_frame, width=70)
        self.allow_block_entry.insert(0, "50")
        self.allow_block_entry.pack(side="left", padx=5)

        self.on_mode_change()

        info = (
            "• Timed: block for exact minutes\n"
            "• Until Restart: stays active until you reboot\n"
            "• Pomodoro: alternating work / break periods\n"
            "• Allowance: free time first, then the real block starts"
        )
        ctk.CTkLabel(
            frame, text=info, justify="left", font=ctk.CTkFont(size=12), text_color="#aaaaaa"
        ).pack(pady=15, padx=20)

    def build_settings_tab(self):
        frame = self.tab_settings

        ctk.CTkLabel(
            frame, text="Blocking Behaviour", font=ctk.CTkFont(size=15, weight="bold")
        ).pack(pady=(15, 8))

        self.force_var = ctk.BooleanVar(value=self.config["force_close"])
        ctk.CTkCheckBox(
            frame,
            text="Force-close non-whitelisted apps (recommended)",
            variable=self.force_var,
            command=self.update_config,
        ).pack(anchor="w", padx=30, pady=4)

        self.notify_var = ctk.BooleanVar(value=self.config["notifications"])
        ctk.CTkCheckBox(
            frame,
            text="Show desktop notifications",
            variable=self.notify_var,
            command=self.update_config,
        ).pack(anchor="w", padx=30, pady=4)

        self.update_var = ctk.BooleanVar(value=self.config.get("check_for_updates", True))
        ctk.CTkCheckBox(
            frame,
            text="Check for updates on launch",
            variable=self.update_var,
            command=self.update_config,
        ).pack(anchor="w", padx=30, pady=4)

        self.protect_tm_var = ctk.BooleanVar(value=self.config.get("protect_task_manager", False))
        ctk.CTkCheckBox(
            frame,
            text="Also block Task Manager / Process Explorer (aggressive)",
            variable=self.protect_tm_var,
            command=self.update_config,
        ).pack(anchor="w", padx=30, pady=4)

        ctk.CTkLabel(frame, text="Check interval (seconds):").pack(anchor="w", padx=30, pady=(12, 2))
        self.interval_entry = ctk.CTkEntry(frame, width=80)
        self.interval_entry.insert(0, str(self.config["check_interval"]))
        self.interval_entry.pack(anchor="w", padx=30)
        self.interval_entry.bind("<FocusOut>", lambda e: self.update_config())

        ctk.CTkLabel(
            frame,
            text="Emergency Stop Password (optional but recommended)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(25, 5))
        ctk.CTkLabel(
            frame,
            text="If set, you must enter this password + a confirmation phrase to stop a block early.",
            text_color="#aaaaaa",
            wraplength=600,
        ).pack(padx=30)

        pw_frame = ctk.CTkFrame(frame, fg_color="transparent")
        pw_frame.pack(pady=8)
        self.pw_entry = ctk.CTkEntry(pw_frame, width=200, show="•")
        self.pw_entry.insert(0, self.config.get("emergency_password", ""))
        self.pw_entry.pack(side="left", padx=5)
        ctk.CTkButton(
            pw_frame, text="Save Password", width=110, command=self.save_password
        ).pack(side="left", padx=5)

        ctk.CTkLabel(
            frame,
            text=(
                "Note: During an active block the main window is locked.\n"
                "Emergency stop requires password + random phrase + final confirmation."
            ),
            text_color="#cc6666",
            justify="left",
        ).pack(pady=20, padx=30)

        ctk.CTkLabel(
            frame, text=f"Version {APP_VERSION}", text_color="#666666"
        ).pack(side="bottom", pady=10)

    def build_start_tab(self):
        frame = self.tab_start

        self.summary_label = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=14), justify="left", wraplength=650
        )
        self.summary_label.pack(pady=20, padx=20)

        self.timer_label = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=32, weight="bold")
        )
        self.timer_label.pack(pady=10)

        self.progress = ctk.CTkProgressBar(frame, width=400)
        self.progress.pack(pady=10)
        self.progress.set(0)

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(pady=20)

        self.start_btn = ctk.CTkButton(
            btn_row,
            text="▶  START FOCUS BLOCK",
            font=ctk.CTkFont(size=16, weight="bold"),
            width=220,
            height=45,
            fg_color="#D82C2C",
            hover_color="#B82424",
            command=self.start_block,
        )
        self.start_btn.pack(side="left", padx=10)

        self.extend_btn = ctk.CTkButton(
            btn_row,
            text="+10 min",
            width=90,
            height=45,
            state="disabled",
            command=lambda: self.extend_block(10),
        )
        self.extend_btn.pack(side="left", padx=6)

        self.stop_btn = ctk.CTkButton(
            btn_row,
            text="Emergency Stop…",
            width=160,
            height=45,
            fg_color="#555555",
            hover_color="#777777",
            state="disabled",
            command=self.request_emergency_stop,
        )
        self.stop_btn.pack(side="left", padx=10)

        self.update_summary()

    # ------------------------------------------------------------------
    # Allowlist helpers
    # ------------------------------------------------------------------

    def refresh_allowlist_box(self):
        self.allow_listbox.delete(0, "end")
        for app in sorted(self.allowlist):
            self.allow_listbox.insert("end", app)

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
                import json
                json.dump(sorted(list(self.allowlist)), f, indent=2)
            self.notify("Allowlist exported")

    def import_allowlist(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if path:
            try:
                import json
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
                # refresh menu
                self.profile_menu.configure(values=["(current)"] + list_profiles())
                self.profile_var.set(name)
                self.notify(f"Profile “{name}” saved")

    # ------------------------------------------------------------------
    # Mode / Config
    # ------------------------------------------------------------------

    def on_mode_change(self):
        mode = self.mode_var.get()
        self.timed_frame.pack_forget()
        self.pomo_frame.pack_forget()
        self.allow_frame.pack_forget()
        if mode == "timed":
            self.timed_frame.pack(fill="x", padx=20, pady=10)
        elif mode == "pomodoro":
            self.pomo_frame.pack(pady=10)
        elif mode == "allowance":
            self.allow_frame.pack(pady=10)
        self.update_summary()

    def set_duration(self, mins: int):
        self.duration_entry.delete(0, "end")
        self.duration_entry.insert(0, str(mins))

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

    def update_summary(self):
        if not hasattr(self, "summary_label"):
            return
        mode = self.mode_var.get() if hasattr(self, "mode_var") else "timed"
        apps = len(self.allowlist)
        text = f"Allowlist: {apps} app(s)\nMode: {mode.upper()}\n"
        if mode == "timed" and hasattr(self, "duration_entry"):
            text += f"Duration: {self.duration_entry.get()} minutes"
        elif mode == "restart":
            text += "Block lasts until computer restart"
        elif mode == "pomodoro" and hasattr(self, "pomo_work"):
            text += (
                f"Work {self.pomo_work.get()} min / Break {self.pomo_break.get()} min "
                f"× {self.pomo_cycles.get()} cycles"
            )
        elif mode == "allowance" and hasattr(self, "allowance_entry"):
            text += (
                f"Allowance {self.allowance_entry.get()} min → "
                f"then block {self.allow_block_entry.get()} min"
            )
        if hasattr(self, "force_var"):
            text += f"\nAction: {'Force-close' if self.force_var.get() else 'Minimize (best effort)'}"
        else:
            text += "\nAction: Force-close"
        self.summary_label.configure(text=text)

    # ------------------------------------------------------------------
    # Blocking
    # ------------------------------------------------------------------

    def start_block(self, resume: bool = False, resume_data: Optional[dict] = None):
        if not resume and not self.allowlist:
            messagebox.showwarning(
                "Empty Allowlist",
                "Please add at least one application to the allowlist first.",
            )
            return

        self.update_config()

        if not resume:
            self.current_whitelist = {a.lower() for a in self.allowlist}
            self.block_mode = self.mode_var.get()
        else:
            self.current_whitelist = set(resume_data.get("allowlist", []))
            self.block_mode = resume_data.get("mode", "timed")
            self.config["force_close"] = resume_data.get("force_close", True)

        self.stop_event.clear()
        self.is_blocking = True
        self.start_btn.configure(state="disabled")
        self.extend_btn.configure(state="normal" if self.block_mode == "timed" else "disabled")
        self.stop_btn.configure(state="normal", fg_color="#8B0000", hover_color="#A52A2A")
        self.tabs.configure(state="disabled")

        self.enforcer = Enforcer(
            whitelist=self.current_whitelist,
            force_close=self.config["force_close"],
            protect_task_manager=self.config.get("protect_task_manager", False),
        )

        def status_cb(msg: str):
            self.after(0, lambda: self.status_var.set(msg))

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
                self.runner.start_pomodoro(work, brk, cycles, resume_state, resume_end)
            elif self.block_mode == "allowance":
                allow_mins = int(self.allowance_entry.get())
                block_mins = int(self.allow_block_entry.get())
                self.runner.start_allowance(allow_mins, block_mins)

            self.save_last_session_ui()
            self._persist_active()
            if not resume:
                self.notify("Staylocked session started. Stay strong.")
            self.status_var.set("BLOCK ACTIVE — only allowlisted apps permitted")
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
        self._persist_active()
        self.notify(f"Extended by {minutes} minutes")

    def update_timer_display(self):
        if not self.is_blocking or not self.runner:
            return
        end = self.runner.block_end_time
        if end:
            remaining = (end - datetime.now()).total_seconds()
            if remaining < 0:
                remaining = 0
            mins = int(remaining // 60)
            secs = int(remaining % 60)
            self.timer_label.configure(text=f"{mins:02d}:{secs:02d}")
            total = self.last_duration * 60
            if total > 0:
                self.progress.set(max(0, 1 - remaining / total))
        else:
            self.timer_label.configure(text="UNTIL RESTART")
            self.progress.set(0)
        self.after(500, self.update_timer_display)

    def end_block(self):
        self.is_blocking = False
        self.stop_event.set()
        clear_active_session()
        self.start_btn.configure(state="normal")
        self.extend_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled", fg_color="#555555")
        self.tabs.configure(state="normal")
        self.timer_label.configure(text="")
        self.progress.set(0)
        self.status_var.set("Ready. Select apps and start a focus session.")
        self.notify("Staylocked session ended.")
        self.runner = None
        self.enforcer = None

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
            "Resume Staylocked Session?",
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
            "SoftLock will restart and resume any active session.",
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
                "Use the Emergency Stop button on the Start tab\n"
                "(requires password + phrase confirmation).",
            )
            return
        self.destroy()


def main():
    app = StayLockedApp()
    app.mainloop()