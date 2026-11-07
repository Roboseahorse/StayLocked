"""
Running-apps picker: a searchable list with app icons.

Usage from app.py:

    from staylocked.running_apps import show_running_apps_dialog

    def add_running_apps(self):
        def on_add(names):
            self.allowlist.update(names)
            save_allowlist(self.allowlist)
            self.refresh_allowlist_box()
        show_running_apps_dialog(self, on_add, already=self.allowlist)
"""

from __future__ import annotations

import ctypes
import hashlib
import sys
import tkinter as tk
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

import customtkinter as ctk
import psutil
from PIL import Image, ImageDraw, ImageFont

from staylocked.enforcer import SYSTEM_WHITELIST

# ----------------------------------------------------------------------
# Look and feel (matches the rest of the app)
# ----------------------------------------------------------------------

BG = "#1A1A1A"
LIST_BG = "#252525"
LIST_BG_RGB = (0x25, 0x25, 0x25)
TEXT = "#F2F2F2"
MUTED = "#8A8A8A"
ACCENT = "#D82C2C"
ACCENT_HOVER = "#A52A2A"

ICON_PX = 32     # size icons are rendered at
ICON_SHOWN = 24  # size icons are displayed at

IS_WIN = sys.platform == "win32"

# ----------------------------------------------------------------------
# Windows API (only loaded on Windows)
# ----------------------------------------------------------------------

if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HICON),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", wintypes.DWORD),
            ("szDisplayName", wintypes.WCHAR * 260),
            ("szTypeName", wintypes.WCHAR * 80),
        ]

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    # Explicit prototypes: without these, 64-bit handles get truncated.
    shell32.SHGetFileInfoW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW),
        wintypes.UINT, wintypes.UINT,
    ]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t

    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.DrawIconEx.argtypes = [
        wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.HICON,
        ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT,
    ]
    user32.DrawIconEx.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL
    user32.FillRect.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.HBRUSH]
    user32.FillRect.restype = ctypes.c_int

    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateDIBSection.argtypes = [
        wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
        ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
    ]
    gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    gdi32.DeleteDC.restype = wintypes.BOOL
    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH
    gdi32.GdiFlush.argtypes = []
    gdi32.GdiFlush.restype = wintypes.BOOL

    dwmapi.DwmGetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long

    SHGFI_ICON = 0x100
    SHGFI_LARGEICON = 0x0
    SHGFI_USEFILEATTRIBUTES = 0x10
    FILE_ATTRIBUTE_NORMAL = 0x80
    DI_NORMAL = 0x3
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x80
    WS_EX_APPWINDOW = 0x40000
    DWMWA_CLOAKED = 14


def _pids_with_visible_windows() -> Optional[set]:
    """PIDs that own a normal, visible, titled window. None if unsupported."""
    if not IS_WIN:
        return None
    try:
        pids: set = set()

        def callback(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                if user32.GetWindowTextLengthW(hwnd) == 0:
                    return True
                ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                if (ex_style & WS_EX_TOOLWINDOW) and not (ex_style & WS_EX_APPWINDOW):
                    return True
                cloaked = ctypes.c_int(0)
                dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
                )
                if cloaked.value:
                    return True
                pid = wintypes.DWORD(0)
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    pids.add(pid.value)
            except Exception:
                pass
            return True

        enum_proc = WNDENUMPROC(callback)  # keep a reference while enumerating
        user32.EnumWindows(enum_proc, 0)
        return pids
    except Exception:
        return None


# ----------------------------------------------------------------------
# Icons
# ----------------------------------------------------------------------

_PALETTE = [
    "#3B6EA5", "#8E5A9B", "#4C8C6B", "#B5651D",
    "#A04848", "#4A7F8C", "#7A6A3A", "#5C5F9E",
]

_icon_cache: Dict[str, "ctk.CTkImage"] = {}


def _draw_hicon(hicon, size: int, bg_rgb: Tuple[int, int, int]) -> Optional[Image.Image]:
    """Draw an HICON onto a solid background and return it as a PIL image."""
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = size
    bmi.bmiHeader.biHeight = -size  # top-down
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB
    bits = ctypes.c_void_p()
    hbmp = gdi32.CreateDIBSection(screen_dc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    brush = None
    old = None
    try:
        if not hbmp or not bits.value:
            return None
        old = gdi32.SelectObject(mem_dc, hbmp)
        r, g, b = bg_rgb
        brush = gdi32.CreateSolidBrush(r | (g << 8) | (b << 16))
        rect = wintypes.RECT(0, 0, size, size)
        user32.FillRect(mem_dc, ctypes.byref(rect), brush)
        user32.DrawIconEx(mem_dc, 0, 0, hicon, size, size, 0, None, DI_NORMAL)
        gdi32.GdiFlush()
        buf = ctypes.string_at(bits.value, size * size * 4)
        return Image.frombuffer("RGB", (size, size), buf, "raw", "BGRX", 0, 1).copy()
    finally:
        if old:
            gdi32.SelectObject(mem_dc, old)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if brush:
            gdi32.DeleteObject(brush)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)


def _win_icon_image(exe_path: Optional[str]) -> Optional[Image.Image]:
    info = SHFILEINFOW()
    if exe_path and Path(exe_path).exists():
        ok = shell32.SHGetFileInfoW(
            exe_path, 0, ctypes.byref(info), ctypes.sizeof(info),
            SHGFI_ICON | SHGFI_LARGEICON,
        )
    else:
        # Unreadable or protected process: use Windows' generic exe icon.
        ok = shell32.SHGetFileInfoW(
            "app.exe", FILE_ATTRIBUTE_NORMAL, ctypes.byref(info), ctypes.sizeof(info),
            SHGFI_ICON | SHGFI_LARGEICON | SHGFI_USEFILEATTRIBUTES,
        )
    if not ok or not info.hIcon:
        return None
    try:
        return _draw_hicon(info.hIcon, ICON_PX, LIST_BG_RGB)
    finally:
        user32.DestroyIcon(info.hIcon)


def _letter_icon(name: str) -> Image.Image:
    """Coloured rounded square with the app's first letter (fallback icon)."""
    digest = hashlib.md5(name.encode("utf-8", "ignore")).digest()
    colour = _PALETTE[digest[0] % len(_PALETTE)]
    img = Image.new("RGB", (ICON_PX, ICON_PX), LIST_BG_RGB)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((2, 2, ICON_PX - 3, ICON_PX - 3), radius=8, fill=colour)
    letter = (name[:1] or "?").upper()
    font = None
    for candidate in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(candidate, 18)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    left, top, right, bottom = draw.textbbox((0, 0), letter, font=font)
    x = (ICON_PX - (right - left)) / 2 - left
    y = (ICON_PX - (bottom - top)) / 2 - top
    draw.text((x, y), letter, fill="#FFFFFF", font=font)
    return img


def get_icon(name: str, exe: Optional[str]) -> "ctk.CTkImage":
    key = (exe or name).lower()
    cached = _icon_cache.get(key)
    if cached is not None:
        return cached
    img = None
    if IS_WIN:
        try:
            img = _win_icon_image(exe)
        except Exception:
            img = None
    if img is None:
        img = _letter_icon(name)
    icon = ctk.CTkImage(light_image=img, dark_image=img, size=(ICON_SHOWN, ICON_SHOWN))
    _icon_cache[key] = icon
    return icon


# ----------------------------------------------------------------------
# Collecting apps
# ----------------------------------------------------------------------

def _collect_running_apps() -> Tuple[Dict[str, dict], bool]:
    """Return ({process_name: {exe, windowed}}, can_filter_by_window)."""
    skip = {n.lower() for n in SYSTEM_WHITELIST}
    skip.add(Path(sys.executable).name.lower())
    window_pids = _pids_with_visible_windows()

    apps: Dict[str, dict] = {}
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if not name or name in skip:
                continue
            entry = apps.setdefault(name, {"exe": None, "windowed": False})
            if not entry["exe"] and proc.info.get("exe"):
                entry["exe"] = proc.info["exe"]
            if window_pids is not None and proc.info.get("pid") in window_pids:
                entry["windowed"] = True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return apps, window_pids is not None


def _friendly_name(process_name: str) -> str:
    base = process_name[:-4] if process_name.lower().endswith(".exe") else process_name
    base = base.replace("_", " ").replace("-", " ")
    return base[:1].upper() + base[1:]


# ----------------------------------------------------------------------
# The dialog
# ----------------------------------------------------------------------

def show_running_apps_dialog(
    parent,
    on_add: Callable[[set], None],
    already: Optional[Iterable[str]] = None,
) -> None:
    """Open the picker. on_add receives the set of chosen process names."""
    already_set = {a.lower() for a in (already or [])}
    entries, can_filter = _collect_running_apps()
    order = sorted(entries, key=lambda n: (n in already_set, n))

    top = ctk.CTkToplevel(parent)
    top.title("Add Running Apps")
    top.configure(fg_color=BG)
    top.minsize(400, 480)
    width, height = 480, 660
    try:
        x = parent.winfo_rootx() + (parent.winfo_width() - width) // 2
        y = parent.winfo_rooty() + max((parent.winfo_height() - height) // 2, 0)
        top.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    except Exception:
        top.geometry(f"{width}x{height}")
    top.transient(parent)

    def _grab():
        try:
            top.grab_set()
            search.focus_set()
        except Exception:
            pass

    top.after(150, _grab)
    top.bind("<Escape>", lambda _e: top.destroy())

    # ---- header: search + view switch -------------------------------
    header = ctk.CTkFrame(top, fg_color="transparent")
    header.pack(fill="x", padx=14, pady=(14, 6))

    search = ctk.CTkEntry(
        header, placeholder_text="🔍  Search apps…", height=36,
        fg_color=LIST_BG, border_color="#3A3A3A", text_color=TEXT,
    )
    search.pack(fill="x")

    view = ctk.CTkSegmentedButton(
        header, values=["Apps", "All processes"], command=lambda _v: refresh(),
        selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
        unselected_color=LIST_BG, unselected_hover_color="#333333",
    )
    if can_filter:
        view.set("Apps")
        view.pack(fill="x", pady=(8, 0))
    else:
        view.set("All processes")

    hint = ctk.CTkLabel(
        header, text="", text_color=MUTED, font=ctk.CTkFont(size=11),
        anchor="w", justify="left", wraplength=430,
    )
    hint.pack(fill="x", pady=(6, 0))

    # ---- list ---------------------------------------------------------
    listf = ctk.CTkScrollableFrame(top, fg_color=LIST_BG, corner_radius=8)
    listf.pack(fill="both", expand=True, padx=14, pady=6)
    listf.grid_columnconfigure(0, weight=1)

    empty_label = ctk.CTkLabel(listf, text="No matching apps", text_color=MUTED)

    rows: Dict[str, ctk.CTkFrame] = {}
    selected_vars: Dict[str, tk.BooleanVar] = {}

    # ---- footer -------------------------------------------------------
    footer = ctk.CTkFrame(top, fg_color="transparent")
    footer.pack(fill="x", padx=14, pady=(4, 14))

    count_label = ctk.CTkLabel(footer, text="", text_color=MUTED, anchor="w")
    count_label.pack(side="left")

    def add_selected():
        names = {n for n, v in selected_vars.items() if v.get()}
        top.destroy()
        if names:
            on_add(names)

    add_btn = ctk.CTkButton(footer, text="Add Selected", width=140, command=add_selected)
    add_btn.pack(side="right")
    ctk.CTkButton(
        footer, text="Cancel", width=80, fg_color="#555555",
        hover_color="#666666", command=top.destroy,
    ).pack(side="right", padx=(0, 8))

    def update_count():
        n = sum(1 for v in selected_vars.values() if v.get())
        count_label.configure(text=f"{n} selected" if n else "")
        add_btn.configure(
            text=f"Add Selected ({n})" if n else "Add Selected",
            state="normal" if n else "disabled",
        )

    # ---- rows ---------------------------------------------------------
    def build_row(name: str) -> ctk.CTkFrame:
        info = entries[name]
        is_added = name in already_set
        var = tk.BooleanVar(value=False)
        selected_vars[name] = var

        row = ctk.CTkFrame(listf, fg_color="transparent", corner_radius=6)
        row.grid_columnconfigure(2, weight=1)

        cb = ctk.CTkCheckBox(
            row, text="", variable=var, width=24, checkbox_width=20, checkbox_height=20,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, command=update_count,
        )
        cb.grid(row=0, column=0, padx=(8, 4), pady=6)

        icon = ctk.CTkLabel(row, text="", image=get_icon(name, info["exe"]), width=ICON_SHOWN)
        icon.grid(row=0, column=1, padx=(0, 8), pady=6)

        title = ctk.CTkLabel(
            row, text=_friendly_name(name), anchor="w", font=ctk.CTkFont(size=13),
            text_color=MUTED if is_added else TEXT,
        )
        title.grid(row=0, column=2, sticky="ew")

        tag = ctk.CTkLabel(
            row, text="already added" if is_added else name, anchor="e",
            text_color=MUTED, font=ctk.CTkFont(size=11),
        )
        tag.grid(row=0, column=3, padx=(8, 10))

        if is_added:
            cb.configure(state="disabled")
        else:
            def toggle(_event=None):
                var.set(not var.get())
                update_count()

            for widget in (row, icon, title, tag):
                widget.bind("<Button-1>", toggle)

        return row

    def refresh():
        query = search.get().strip().lower()
        show_all = (not can_filter) or view.get() == "All processes"
        names = [
            n for n in order
            if (show_all or entries[n]["windowed"])
            and (not query or query in n or query in _friendly_name(n).lower())
        ]

        hint.configure(
            text="" if show_all else
            "Apps with open windows. Use “All processes” for background or tray apps."
        )

        top.configure(cursor="watch")
        top.update_idletasks()
        for r in rows.values():
            r.grid_remove()
        empty_label.grid_remove()
        for i, n in enumerate(names):
            row = rows.get(n)
            if row is None:
                row = rows[n] = build_row(n)
            row.grid(row=i, column=0, sticky="ew", padx=4, pady=1)
        if not names:
            empty_label.grid(row=0, column=0, pady=30)
        top.configure(cursor="")
        update_count()

    search.bind("<KeyRelease>", lambda _e: refresh())
    refresh()
