"""The look of the window: ttk styles built from the tokens, plus the few
widgets Tk does not give us.

Two decisions drive everything here.  The first is to build on ttk's ``clam``
theme rather than the platform's native one: only ``clam`` actually honours the
colours it is given, so it is the difference between "a window styled by us"
and "grey boxes with an accent we cannot apply".  The second is that colours
are never written at the call site -- they are looked up on the active
:class:`Theme`, which is what makes a dark mode a table of values in
:mod:`.palette` instead of a rewrite.

The layout it supports is the one that has settled across file-management and
clean-up tools: a quiet sidebar holding what you are working on, a content
column holding what was found, and a single accented action.  CleanMyMac groups
findings into named areas you opt into rather than one undifferentiated delete
list; TreeSize reports size per folder so bloat is measurable where it lives.
Both ideas are here -- the folder list is the opt-in, and every row carries its
own size.
"""

from __future__ import annotations

import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Callable, Dict, Optional

from .palette import (
    CHECKED, DARK, FAMILIES, LIGHT, SIZES, UNCHECKED, detect_mode, prefers_native_ttk,
)

__all__ = ["CHECKED", "UNCHECKED", "LIGHT", "DARK", "detect_mode", "Theme", "RoundedButton"]


class Theme:
    """The active palette and type scale, plus the ttk styles built from them."""

    def __init__(self, root: tk.Misc, mode: str = "auto") -> None:
        self.root = root
        self.style = ttk.Style(root)
        self.mode = "light"
        self.colors: Dict[str, str] = dict(LIGHT)
        self._family = self._pick_family()
        self._sizes = SIZES.get(sys.platform, SIZES["other"])
        self._build_fonts()
        self.apply(mode)

    # ------------------------------------------------------------------ fonts

    def _pick_family(self) -> str:
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:  # pragma: no cover - only on a broken display
            return "TkDefaultFont"
        for family in FAMILIES:
            if family in available:
                return family
        return tkfont.nametofont("TkDefaultFont").cget("family")

    def _build_fonts(self) -> None:
        self.fonts = {
            "title": tkfont.Font(family=self._family, size=self._sizes["title"], weight="bold"),
            "heading": tkfont.Font(family=self._family, size=self._sizes["heading"], weight="bold"),
            "body": tkfont.Font(family=self._family, size=self._sizes["body"]),
            "body_bold": tkfont.Font(family=self._family, size=self._sizes["body"], weight="bold"),
            "small": tkfont.Font(family=self._family, size=self._sizes["small"]),
            "small_bold": tkfont.Font(family=self._family, size=self._sizes["small"], weight="bold"),
            "tiny": tkfont.Font(family=self._family, size=self._sizes["tiny"]),
            "number": tkfont.Font(family=self._family, size=self._sizes["number"], weight="bold"),
            "mono": tkfont.Font(family="Menlo" if sys.platform == "darwin" else "Consolas",
                                size=self._sizes["small"]),
        }

    def font(self, name: str) -> tkfont.Font:
        return self.fonts[name]

    def color(self, name: str) -> str:
        return self.colors[name]

    # ------------------------------------------------------------------ styles

    def apply(self, mode: str = "auto") -> None:
        self.custom = not prefers_native_ttk(
            self.root.tk.call("tk", "windowingsystem"),
            self.root.tk.call("info", "patchlevel"),
        )
        self.mode = detect_mode() if mode == "auto" else ("dark" if mode == "dark" else "light")
        # On the native theme ttk paints its own light widgets and ignores ours,
        # so a dark palette behind them would leave unreadable pairings.
        if not self.custom:
            self.mode = "light"
        self.colors = dict(DARK if self.mode == "dark" else LIGHT)
        c = self.colors
        style = self.style
        try:
            style.theme_use("clam" if self.custom else style.theme_names()[0])
        except tk.TclError:  # pragma: no cover - clam ships with every Tk we target
            pass

        self.root.configure(background=c["bg"])
        style.configure(".", background=c["bg"], foreground=c["text"],
                        font=self.fonts["body"], borderwidth=0, focuscolor=c["bg"])

        for name, background in (("TFrame", "bg"), ("Sidebar.TFrame", "sidebar"),
                                 ("Card.TFrame", "raised")):
            style.configure(name, background=c[background])
        style.configure("Rule.TFrame", background=c["border"])

        for name, key, colour in (
            ("TLabel", "body", "text"),
            ("Title.TLabel", "title", "text"),
            ("Heading.TLabel", "heading", "text"),
            ("Muted.TLabel", "small", "muted"),
            ("Faint.TLabel", "small", "faint"),
            ("Section.TLabel", "small_bold", "muted"),
            ("Number.TLabel", "number", "text"),
            ("Warn.TLabel", "small", "warn"),
            ("Danger.TLabel", "small", "danger"),
            ("Ok.TLabel", "small", "ok"),
        ):
            style.configure(name, font=self.fonts[key], foreground=c[colour], background=c["bg"])
        # Same scale again on the two other surfaces.  ttk has no notion of
        # inheriting a background, so each one needs its own style name.
        for name, key, colour in (
            ("CardNumber.TLabel", "number", "text"),
            ("CardHeading.TLabel", "heading", "text"),
            ("CardBody.TLabel", "body", "text"),
            ("CardMuted.TLabel", "small", "muted"),
        ):
            style.configure(name, font=self.fonts[key], foreground=c[colour],
                            background=c["raised"])
        style.configure("SidebarBody.TLabel", font=self.fonts["body"],
                        foreground=c["text"], background=c["sidebar"])
        for name in ("SidebarSection.TLabel", "SidebarMuted.TLabel"):
            style.configure(name, background=c["sidebar"], foreground=c["muted"],
                            font=self.fonts["small_bold" if "Section" in name else "small"])

        style.configure("TCheckbutton", background=c["bg"], foreground=c["text"],
                        font=self.fonts["body"], indicatorcolor=c["bg"],
                        indicatorbackground=c["bg"], focusthickness=0)
        style.map("TCheckbutton",
                  background=[("active", c["bg"])],
                  indicatorcolor=[("selected", c["accent"]), ("!selected", c["raised"])],
                  foreground=[("disabled", c["faint"])])
        style.configure("Sidebar.TCheckbutton", background=c["sidebar"])
        style.map("Sidebar.TCheckbutton", background=[("active", c["sidebar"])])

        style.configure("TEntry", fieldbackground=c["raised"], foreground=c["text"],
                        bordercolor=c["border_strong"], lightcolor=c["border_strong"],
                        darkcolor=c["border_strong"], insertcolor=c["text"], padding=6)

        style.configure("Treeview", background=c["bg"], fieldbackground=c["bg"],
                        foreground=c["text"], rowheight=self._row_height(),
                        borderwidth=0, font=self.fonts["body"])
        style.map("Treeview",
                  background=[("selected", c["selection"])],
                  foreground=[("selected", c["text"])])
        style.configure("Treeview.Heading", background=c["bg"], foreground=c["muted"],
                        font=self.fonts["small"], relief="flat", borderwidth=0, padding=(8, 6))
        style.map("Treeview.Heading", background=[("active", c["hover"])])
        style.configure("Sidebar.Treeview", background=c["sidebar"], fieldbackground=c["sidebar"])
        style.map("Sidebar.Treeview", background=[("selected", c["selection"])])
        # ttk draws a sunken frame around a Treeview by default; the layout is
        # replaced rather than merely recoloured because the border is painted
        # by the element itself.  Left alone on the native theme, whose own
        # layouts are the only ones it knows how to draw.
        if self.custom:
            for layout in ("Treeview", "Sidebar.Treeview"):
                try:
                    style.layout(layout, [("Treeview.treearea", {"sticky": "nswe"})])
                except tk.TclError:  # pragma: no cover
                    pass

        # An arrowless, trackless scrollbar -- the arrows are the single most
        # dated thing in a default ttk window.
        for orient in ("Vertical", "Horizontal"):
            try:
                if not self.custom:
                    raise tk.TclError("native scrollbars keep their own layout")
                style.layout(
                    f"{orient}.TScrollbar",
                    [(f"{orient}.Scrollbar.trough",
                      {"children": [(f"{orient}.Scrollbar.thumb",
                                     {"expand": "1", "sticky": "nswe"})],
                       "sticky": "ns" if orient == "Vertical" else "ew"})],
                )
            except tk.TclError:  # pragma: no cover
                pass
            style.configure(f"{orient}.TScrollbar", background=c["border_strong"],
                            troughcolor=c["bg"], borderwidth=0, arrowsize=0, width=8)
            style.map(f"{orient}.TScrollbar", background=[("active", c["faint"])])

        style.configure("Thin.Horizontal.TProgressbar", background=c["accent"],
                        troughcolor=c["track"], borderwidth=0, thickness=3,
                        lightcolor=c["accent"], darkcolor=c["accent"])
        style.configure("TSeparator", background=c["border"])
        style.configure("TPanedwindow", background=c["border"])
        style.configure("Sash", sashthickness=1)

    def _row_height(self) -> int:
        return max(26, self.fonts["body"].metrics("linespace") + 12)


class RoundedButton(tk.Canvas):
    """A flat, rounded button.

    ttk cannot round a corner, and square buttons are what makes a Tk window
    look like a Tk window.  Drawing it costs one canvas per button and buys the
    hover and pressed states that make the interface feel answerable.
    """

    KINDS = ("primary", "secondary", "ghost", "danger")

    def __init__(self, parent: tk.Misc, theme: Theme, text: str,
                 command: Optional[Callable[[], None]] = None,
                 kind: str = "secondary", background: str = "bg",
                 min_width: int = 0, padding: int = 14) -> None:
        self.theme = theme
        self.kind = kind if kind in self.KINDS else "secondary"
        self._text = text
        self._command = command
        self._state = "normal"
        self._hover = False
        self._pressed = False
        self._surface = background
        self._min_width = min_width
        self._padding = padding
        super().__init__(parent, highlightthickness=0, bd=0, takefocus=1,
                         background=theme.color(background))
        self._resize()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda _e: self.invoke())
        self.bind("<space>", lambda _e: self.invoke())
        self.bind("<FocusIn>", lambda _e: self._draw())
        self.bind("<FocusOut>", lambda _e: self._draw())

    # ------------------------------------------------------------- public API

    def configure_text(self, text: str) -> None:
        self._text = text
        self._resize()

    def set_state(self, state: str) -> None:
        self._state = state
        self._draw()

    def invoke(self) -> None:
        if self._state != "disabled" and self._command:
            self._command()

    def restyle(self, theme: Theme) -> None:
        self.theme = theme
        self.configure(background=theme.color(self._surface))
        self._resize()

    # ---------------------------------------------------------------- drawing

    def _resize(self) -> None:
        font = self.theme.font("body")
        width = max(self._min_width, font.measure(self._text) + self._padding * 2)
        height = font.metrics("linespace") + 14
        self.configure(width=width, height=height)
        self._draw()

    def _palette(self):
        c = self.theme.color
        if self._state == "disabled":
            return c("track"), c("faint"), ""
        if self.kind == "primary":
            fill = c("accent_press") if self._pressed else c("accent_hover") if self._hover else c("accent")
            return fill, c("on_accent"), ""
        if self.kind == "danger":
            return (c("hover") if self._hover else c("bg")), c("danger"), c("border_strong")
        if self.kind == "ghost":
            return (c("hover") if self._hover else c(self._surface)), c("muted"), ""
        fill = c("hover") if (self._hover or self._pressed) else c("raised")
        return fill, c("text"), c("border_strong")

    def _draw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        fill, foreground, outline = self._palette()
        radius = min(8, height // 2)
        self._rounded(1, 1, width - 1, height - 1, radius, fill, outline)
        if self.focus_get() is self and self._state != "disabled":
            self._rounded(1, 1, width - 1, height - 1, radius, "", self.theme.color("accent"))
        self.create_text(width / 2, height / 2, text=self._text, fill=foreground,
                         font=self.theme.font("body"))

    def _rounded(self, x1, y1, x2, y2, r, fill, outline) -> None:
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        self.create_polygon(points, smooth=True, splinesteps=24,
                            fill=fill or "", outline=outline or "", width=1)

    # ----------------------------------------------------------------- events

    def _on_enter(self, _event) -> None:
        self._hover = True
        self._draw()

    def _on_leave(self, _event) -> None:
        self._hover = self._pressed = False
        self._draw()

    def _on_press(self, _event) -> None:
        if self._state == "disabled":
            return
        self._pressed = True
        self.focus_set()
        self._draw()

    def _on_release(self, event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        inside = 0 <= event.x <= int(self["width"]) and 0 <= event.y <= int(self["height"])
        if was_pressed and inside:
            self.invoke()
