"""
StayLocked visual theme: colours, fonts and small hand-drawn vector icons.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

import customtkinter as ctk
from PIL import Image, ImageDraw

# ----------------------------------------------------------------------
# Colours
# ----------------------------------------------------------------------

BG = "#111111"          # window background
SURFACE = "#181818"     # cards
SURFACE_2 = "#222222"   # inputs, chips, list backgrounds
SURFACE_3 = "#2D2D2D"   # selected pills / hover
BORDER = "#2C2C2C"
TEXT = "#F2F2F2"
MUTED = "#8A8A8A"
FAINT = "#5A5A5A"

ACCENT = "#E5383B"
ACCENT_HOVER = "#C92A2D"
ACCENT_DIM = "#3B1D1F"
GREEN = "#3DC38A"       # "apps are free" phases (breaks, allowance)
DANGER = "#7A1F22"

FONT_FAMILY = "Segoe UI"


def font(size: int, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


# ----------------------------------------------------------------------
# Icons (drawn with PIL at 8x then downscaled, so edges are smooth)
# ----------------------------------------------------------------------

_SS = 8
_icon_cache: Dict[Tuple[str, int, str], ctk.CTkImage] = {}


def _line(d: ImageDraw.ImageDraw, p1, p2, width: float, fill) -> None:
    d.line([p1, p2], fill=fill, width=int(width))
    r = width / 2
    for x, y in (p1, p2):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _draw_timer(d, n, c):
    cx, cy, r = n * 0.5, n * 0.57, n * 0.33
    w = n * 0.10
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=c, width=int(w))
    _line(d, (n * 0.5, n * 0.10), (n * 0.5, n * 0.19), w, c)
    _line(d, (n * 0.40, n * 0.09), (n * 0.60, n * 0.09), w * 0.8, c)
    _line(d, (cx, cy), (cx, cy - r * 0.55), w * 0.9, c)
    _line(d, (cx, cy), (cx + r * 0.45, cy + r * 0.2), w * 0.9, c)


def _draw_list(d, n, c):
    w = n * 0.09
    for y in (0.27, 0.5, 0.73):
        r = n * 0.055
        d.ellipse((n * 0.19 - r, n * y - r, n * 0.19 + r, n * y + r), fill=c)
        _line(d, (n * 0.36, n * y), (n * 0.84, n * y), w, c)


def _draw_gear(d, n, c):
    cx = cy = n / 2
    outer, inner, teeth = n * 0.44, n * 0.33, 8
    pts = []
    for i in range(teeth):
        base = 2 * math.pi * i / teeth
        step = 2 * math.pi / teeth
        for frac, rad in ((0.0, inner), (0.18, outer), (0.50 - 0.18, outer), (0.50, inner)):
            a = base + step * frac - math.pi / 2
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    d.polygon(pts, fill=c)
    hole = n * 0.15
    d.ellipse((cx - hole, cy - hole, cx + hole, cy + hole), fill=(0, 0, 0, 0))


def _draw_play(d, n, c):
    d.polygon([(n * 0.30, n * 0.18), (n * 0.30, n * 0.82), (n * 0.82, n * 0.5)], fill=c)


def _draw_lock(d, n, c):
    w = n * 0.11
    # body
    d.rounded_rectangle((n * 0.25, n * 0.47, n * 0.75, n * 0.88), radius=n * 0.08, fill=c)
    # shackle: arc on top with straight legs running into the body
    r, cy = n * 0.165, n * 0.34
    d.arc((n * 0.5 - r, cy - r, n * 0.5 + r, cy + r), 180, 360, fill=c, width=int(w))
    for x in (n * 0.5 - r + w / 2 - 1, n * 0.5 + r - w / 2 + 1):
        d.rectangle((x - w / 2, cy, x + w / 2, n * 0.52), fill=c)


def _draw_stop(d, n, c):
    d.rounded_rectangle((n * 0.24, n * 0.24, n * 0.76, n * 0.76), radius=n * 0.1, fill=c)


_PAINTERS = {
    "timer": _draw_timer,
    "list": _draw_list,
    "gear": _draw_gear,
    "play": _draw_play,
    "lock": _draw_lock,
    "stop": _draw_stop,
}


def icon_image(name: str, px: int = 18, color: str = TEXT) -> Image.Image:
    """Return a smooth RGBA PIL icon, 2x the logical size (for crisp display)."""
    out = px * 2
    n = out * _SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _PAINTERS[name](d, n, hex_to_rgb(color) + (255,))
    return img.resize((out, out), Image.Resampling.LANCZOS)


def icon(name: str, px: int = 18, color: str = TEXT) -> ctk.CTkImage:
    key = (name, px, color)
    cached = _icon_cache.get(key)
    if cached is None:
        img = icon_image(name, px, color)
        cached = ctk.CTkImage(light_image=img, dark_image=img, size=(px, px))
        _icon_cache[key] = cached
    return cached


def logo_image(px: int = 36) -> ctk.CTkImage:
    """Red rounded square with a white padlock (app mark)."""
    key = ("logo", px, "")
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    out = px * 2
    n = out * _SS
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, n - 1, n - 1), radius=n * 0.26, fill=hex_to_rgb(ACCENT) + (255,))
    lock = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lock)
    _draw_lock(ld, n, (255, 255, 255, 255))
    # keyhole
    kc = hex_to_rgb(ACCENT) + (255,)
    r = n * 0.06
    ld.ellipse((n * 0.5 - r, n * 0.63 - r, n * 0.5 + r, n * 0.63 + r), fill=kc)
    _line(ld, (n * 0.5, n * 0.64), (n * 0.5, n * 0.75), n * 0.05, kc)
    scaled = lock.resize((int(n * 0.74), int(n * 0.74)), Image.Resampling.LANCZOS)
    img = img.resize((out, out), Image.Resampling.LANCZOS)
    scaled = scaled.resize((int(out * 0.74), int(out * 0.74)), Image.Resampling.LANCZOS)
    img.alpha_composite(scaled, ((out - scaled.width) // 2, (out - scaled.height) // 2 + int(out * 0.01)))
    cached = ctk.CTkImage(light_image=img, dark_image=img, size=(px, px))
    _icon_cache[key] = cached
    return cached
