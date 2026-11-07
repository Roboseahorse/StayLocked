"""
Emergency stop dialog – intentionally high-friction.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import messagebox


def show_emergency_stop_dialog(
    parent,
    emergency_password: str = "",
    on_confirmed: Optional[Callable[[], None]] = None,
) -> None:
    """
    Show a multi-step confirmation dialog.
    Requires optional password + random phrase + final yes/no.
    """
    words = [
        "focus", "discipline", "commit", "persist", "integrity",
        "resolve", "willpower", "dedication", "strength", "clarity",
        "grit", "purpose", "effort", "patience", "courage",
    ]
    phrase = " ".join(random.sample(words, 4)) + " " + str(random.randint(1000, 9999))

    top = ctk.CTkToplevel(parent)
    top.title("Emergency Stop — Confirmation Required")
    top.geometry("520x400")
    top.transient(parent)
    top.grab_set()
    top.attributes("-topmost", True)

    ctk.CTkLabel(
        top,
        text="⚠ EMERGENCY STOP",
        font=ctk.CTkFont(size=20, weight="bold"),
        text_color="#D82C2C",
    ).pack(pady=15)

    ctk.CTkLabel(
        top,
        text=(
            "Stopping early defeats the purpose of a focus block.\n"
            "Only use this if there is a genuine emergency."
        ),
        justify="center",
        wraplength=450,
    ).pack(pady=5)

    pw_entry = None
    if emergency_password:
        ctk.CTkLabel(top, text="Enter your emergency password:").pack(pady=(15, 2))
        pw_entry = ctk.CTkEntry(top, width=250, show="•")
        pw_entry.pack()

    ctk.CTkLabel(
        top,
        text="Type the following phrase exactly to confirm:",
        text_color="#aaaaaa",
    ).pack(pady=(15, 2))

    ctk.CTkLabel(
        top,
        text=phrase,
        font=ctk.CTkFont(size=14, weight="bold"),
        text_color="#F2F2F2",
    ).pack(pady=5)

    entry = ctk.CTkEntry(top, width=400)
    entry.pack(pady=5)
    entry.focus_set()

    def attempt():
        if emergency_password:
            if not pw_entry or pw_entry.get() != emergency_password:
                messagebox.showerror("Wrong", "Incorrect emergency password.", parent=top)
                return
        if entry.get().strip() != phrase:
            messagebox.showerror("Wrong", "Phrase does not match. Try again.", parent=top)
            return
        if messagebox.askyesno(
            "Final Confirmation",
            "Are you absolutely sure you want to end the focus block early?",
            parent=top,
        ):
            top.destroy()
            if on_confirmed:
                on_confirmed()

    ctk.CTkButton(
        top,
        text="Confirm Emergency Stop",
        fg_color="#8B0000",
        hover_color="#A52A2A",
        command=attempt,
    ).pack(pady=20)

    ctk.CTkButton(
        top,
        text="Cancel — Keep Locking",
        command=top.destroy,
    ).pack()
