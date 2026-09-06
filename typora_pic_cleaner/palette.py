"""Design tokens: the colours, the type scale, and the glyphs.

Kept apart from :mod:`.theme` so the values can be checked without a display.
CI runners and slimmed-down Python builds do not always ship ``_tkinter``, and
a palette test that cannot run is a palette test that does not protect anyone.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Dict

LIGHT: Dict[str, str] = {
    "bg": "#ffffff",
    "sidebar": "#f6f6f8",
    "raised": "#ffffff",
    "border": "#e4e4e8",
    "border_strong": "#d2d2d8",
    "text": "#1c1c20",
    "muted": "#6b6b75",
    "faint": "#9a9aa4",
    "accent": "#2563eb",
    "accent_hover": "#1d4ed8",
    "accent_press": "#1a44bd",
    "on_accent": "#ffffff",
    "danger": "#b42318",
    "warn": "#a35a00",
    "ok": "#0a7a48",
    "stripe": "#fafafb",
    "selection": "#e6eefe",
    "hover": "#f0f0f3",
    "track": "#ebebef",
}

DARK: Dict[str, str] = {
    "bg": "#1b1b1e",
    "sidebar": "#151517",
    "raised": "#232327",
    "border": "#313136",
    "border_strong": "#3d3d44",
    "text": "#f1f1f4",
    "muted": "#9d9da7",
    "faint": "#75757f",
    "accent": "#4c8dff",
    "accent_hover": "#3c7ff5",
    "accent_press": "#3271e0",
    "on_accent": "#0b1120",
    "danger": "#f78a80",
    "warn": "#e0a458",
    "ok": "#5cc999",
    "stripe": "#202024",
    "selection": "#26344d",
    "hover": "#2a2a2f",
    "track": "#2c2c31",
}

#: Point sizes per platform.  Tk's own defaults differ by a factor of nearly
#: one and a half between macOS and Windows, so a single number would be
#: unreadable on one of them.
SIZES = {
    "darwin": {"title": 20, "heading": 15, "body": 13, "small": 11, "tiny": 10, "number": 22},
    "win32": {"title": 16, "heading": 12, "body": 10, "small": 9, "tiny": 8, "number": 18},
    "other": {"title": 16, "heading": 12, "body": 10, "small": 9, "tiny": 8, "number": 18},
}

#: First match wins.  The CJK faces matter on Windows, where the default UI font
#: renders Chinese in a mismatched fallback that looks broken next to Latin text.
FAMILIES = (
    "SF Pro Text", "-apple-system", "Helvetica Neue",
    "Segoe UI Variable Text", "Segoe UI",
    "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC",
)

CHECKED = "☑"      # ballot box with check
UNCHECKED = "☐"    # ballot box


def prefers_native_ttk(windowing: str, patchlevel: str) -> bool:
    """Whether ttk must be left on the platform's own theme.

    The custom look is built on ttk's ``clam`` theme, because it is the only one
    that honours the colours it is given.  On the macOS Tk that ships with the
    system -- 8.5.9, from 2010 -- ``clam`` lays every widget out correctly and
    then paints none of them, so the window comes up blank.  Better a native
    window than an empty one; the packaged builds carry Tk 8.6 and are
    unaffected.
    """
    if windowing != "aqua":
        return False
    parts = patchlevel.split(".")
    try:
        version = (int(parts[0]), int(parts[1]))
    except (IndexError, ValueError):
        return True  # unreadable version: assume the cautious answer
    return version < (8, 6)


def detect_mode() -> str:
    """Follow the operating system's light/dark setting, defaulting to light."""
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            return "dark" if "dark" in result.stdout.strip().lower() else "light"
        except (OSError, subprocess.SubprocessError):
            return "light"
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if value else "dark"
        except Exception:
            return "light"
    return "light"


