"""
Reusable StayLocked widgets: timer ring, tab bar, buttons, cards.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw

from staylocked import theme
from staylocked.theme import (
    ACCENT, ACCENT_DIM, ACCENT_HOVER, BORDER, DANGER, FAINT, MUTED,
    SURFACE, SURFACE_2, SURFACE_3, TEXT, font, hex_to_rgb,
)

TRACK = "#2A2A2A"


def card(master, **kw) -> ctk.CTkFrame:
    """A rounded dark card with a subtle border."""
    opts = dict(fg_color=SURFACE, corner_radius=20, border_width=1, border_color=BORDER)
    opts.update(kw)
    return ctk.CTkFrame(master, **opts)


def button(master, text: str, command: Optional[Callable] = None, kind: str = "secondary", **kw) -> ctk.CTkButton:
    """Consistent buttons: primary (red), secondary (grey), ghost (outline), danger."""
    styles = {
        "primary": dict(fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color="#FFFFFF"),
        "secondary": dict(fg_color=SURFACE_2, hover_color=SURFACE_3, text_color=TEXT,
                          border_width=1, border_color=BORDER),
        "ghost": dict(fg_color="transparent", hover_color=SURFACE_2, text_color=MUTED,
                      border_width=1, border_color=BORDER),
        "danger": dict(fg_color="transparent", hover_color="#2A1415", text_color="#E07A7C",
                       border_width=1, border_color=DANGER),
    }
    opts = dict(height=36, corner_radius=18, font=font(13, "bold"), command=command)
    opts.update(styles[kind])
    opts.update(kw)
    return ctk.CTkButton(master, text=text, **opts)


def entry(master, width: int = 64, **kw) -> ctk.CTkEntry:
    opts = dict(width=width, height=34, justify="center", fg_color=SURFACE_2,
                border_color=BORDER, text_color=TEXT, corner_radius=10, font=font(13))
    opts.update(kw)
    return ctk.CTkEntry(master, **opts)


class TimerRing(ctk.CTkFrame):
    """Circular countdown: a ring that shrinks, with the time and a caption inside."""

    def __init__(self, master, size: int = 240, thickness: int = 13, bg: str = SURFACE):
        super().__init__(master, fg_color="transparent", width=size, height=size)
        self.size = size
        self.thickness = thickness
        self.bg = bg
        self._state: Optional[Tuple[int, str]] = None
        self._image: Optional[ctk.CTkImage] = None

        self._img_label = ctk.CTkLabel(self, text="", width=size, height=size, fg_color="transparent")
        self._img_label.place(x=0, y=0)
        time_size = max(34, int(size * 0.215))
        self.time_label = ctk.CTkLabel(self, text="25:00", font=font(time_size, "bold"),
                                       text_color=TEXT, fg_color="transparent")
        self.time_label.place(relx=0.5, rely=0.45, anchor="center")
        self.caption_label = ctk.CTkLabel(self, text="", font=font(11, "bold"),
                                          text_color=MUTED, fg_color="transparent")
        self.caption_label.place(relx=0.5, rely=0.64, anchor="center")
        self.set_ring(1.0, ACCENT)

    # -- public API ---------------------------------------------------
    def set_time(self, text: str) -> None:
        if self.time_label.cget("text") != text:
            self.time_label.configure(text=text)

    def set_caption(self, text: str) -> None:
        if self.caption_label.cget("text") != text:
            self.caption_label.configure(text=text)

    def set_ring(self, fraction: float, color: str = ACCENT) -> None:
        fraction = max(0.0, min(1.0, fraction))
        key = (int(round(fraction * 720)), color)  # re-render in half-degree steps
        if key == self._state:
            return
        self._state = key
        img = self._render(fraction, color)
        self._image = ctk.CTkImage(light_image=img, dark_image=img, size=(self.size, self.size))
        self._img_label.configure(image=self._image)

    # -- drawing ------------------------------------------------------
    def _render(self, fraction: float, color: str) -> Image.Image:
        try:
            scale = float(self._get_widget_scaling())
        except Exception:
            scale = 1.0
        px = max(8, int(round(self.size * scale)))
        ss = 4
        n = px * ss
        bg, track, fg = hex_to_rgb(self.bg), hex_to_rgb(TRACK), hex_to_rgb(color)
        img = Image.new("RGB", (n, n), bg)
        d = ImageDraw.Draw(img)
        t = self.thickness * scale * ss
        m = 3 * scale * ss
        outer = (m, m, n - m, n - m)
        inner = (m + t, m + t, n - m - t, n - m - t)
        d.ellipse(outer, fill=track)
        if fraction >= 0.999:
            d.ellipse(outer, fill=fg)
        elif fraction > 0:
            d.pieslice(outer, -90, -90 + 360 * fraction, fill=fg)
        d.ellipse(inner, fill=bg)
        if 0 < fraction < 0.999:
            r_mid = (n / 2 - m) - t / 2
            for ang in (-90, -90 + 360 * fraction):
                a = math.radians(ang)
                x, y = n / 2 + r_mid * math.cos(a), n / 2 + r_mid * math.sin(a)
                d.ellipse((x - t / 2, y - t / 2, x + t / 2, y + t / 2), fill=fg)
        return img.resize((px, px), Image.Resampling.LANCZOS)


class TabBar(ctk.CTkFrame):
    """Flat tab bar with icons and a red underline under the active tab."""

    def __init__(self, master, tabs: List[Tuple[str, str, str]], on_select: Callable[[str], None]):
        super().__init__(master, fg_color="transparent", height=46)
        self._on_select = on_select
        self._buttons: Dict[str, ctk.CTkButton] = {}
        self._underlines: Dict[str, ctk.CTkFrame] = {}
        self._icons: Dict[str, Tuple[ctk.CTkImage, ctk.CTkImage]] = {}
        self._active: Optional[str] = None
        self._enabled = True

        for key, label, icon_name in tabs:
            col = ctk.CTkFrame(self, fg_color="transparent")
            col.pack(side="left", padx=(0, 6))
            idle = theme.icon(icon_name, 16, MUTED)
            lit = theme.icon(icon_name, 16, ACCENT)
            self._icons[key] = (idle, lit)
            btn = ctk.CTkButton(
                col, text=label, image=idle, compound="left", width=96, height=38,
                corner_radius=8, fg_color="transparent", hover_color=SURFACE_2,
                text_color=MUTED, font=font(13, "bold"),
                command=lambda k=key: self._clicked(k),
            )
            btn.pack()
            line = ctk.CTkFrame(col, width=1, height=2, fg_color="transparent", corner_radius=1)
            line.pack(fill="x", padx=10)
            self._buttons[key] = btn
            self._underlines[key] = line

    def _clicked(self, key: str) -> None:
        if self._enabled:
            self._on_select(key)

    def set_active(self, key: str) -> None:
        self._active = key
        for k, btn in self._buttons.items():
            on = k == key
            btn.configure(text_color=TEXT if on else MUTED, image=self._icons[k][1 if on else 0])
            self._underlines[k].configure(fg_color=ACCENT if on else "transparent")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        for btn in self._buttons.values():
            btn.configure(state="normal" if enabled else "disabled")


class Dots(ctk.CTkFrame):
    """Row of small session dots (filled = completed)."""

    def __init__(self, master, size: int = 10):
        super().__init__(master, fg_color="transparent")
        self._size = size
        self._state: Optional[Tuple[int, int, bool]] = None

    def set(self, done: int, total: int, active: bool = False) -> None:
        total = max(0, min(total, 12))
        done = max(0, min(done, total))
        state = (done, total, active)
        if state == self._state:
            return
        self._state = state
        for child in self.winfo_children():
            child.destroy()
        for i in range(total):
            if i < done:
                color = ACCENT
            elif i == done and active:
                color = ACCENT_DIM
            else:
                color = SURFACE_3
            dot = ctk.CTkFrame(self, width=self._size, height=self._size,
                               corner_radius=self._size // 2, fg_color=color)
            if i == done and active:
                dot.configure(border_width=2, border_color=ACCENT)
            dot.pack(side="left", padx=4)
