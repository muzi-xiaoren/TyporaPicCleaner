"""A ticked list of folders: the sidebar's one real widget.

Tk has no checkbox column, so the tick is a glyph drawn in the tree column and
clicks are routed by hand.  That is a small price for keeping the whole list in
one Treeview: hierarchy, keyboard selection and scrolling all come for free,
and a search result drops straight in as a tree.

The widget owns no decisions.  Everything about which folders count lives in
:class:`~typora_pic_cleaner.discovery.FolderSet`, which is testable without a
display; this file only draws it and turns clicks into calls.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, List, Optional

from .discovery import Folder, FolderSet, shorten
from .i18n import t
from .palette import CHECKED, UNCHECKED
from .theme import Theme


class FolderList(ttk.Frame):
    def __init__(self, parent: tk.Misc, theme: Theme,
                 on_change: Optional[Callable[[], None]] = None,
                 surface: str = "sidebar", height: int = 8) -> None:
        super().__init__(parent, style="Sidebar.TFrame" if surface == "sidebar" else "TFrame")
        self.theme = theme
        self.on_change = on_change
        self.surface = surface
        self.model = FolderSet()

        style = "Sidebar.Treeview" if surface == "sidebar" else "Treeview"
        self.tree = ttk.Treeview(self, columns=("counts",), show="tree", height=height,
                                 selectmode="extended", style=style)
        self.tree.column("#0", width=190, stretch=True)
        self.tree.column("counts", width=118, anchor="e", stretch=False)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.tree.bind("<Button-1>", self._on_click, add="+")
        self.tree.bind("<space>", self._on_space)
        self.tree.bind("<Delete>", lambda _e: self.remove_selected())
        self.tree.bind("<BackSpace>", lambda _e: self.remove_selected())
        self.restyle(theme)

    # ------------------------------------------------------------------ state

    def restyle(self, theme: Theme) -> None:
        self.theme = theme
        self.configure(style="Sidebar.TFrame" if self.surface == "sidebar" else "TFrame")
        self.tree.tag_configure("covered", foreground=theme.color("faint"))
        self.tree.tag_configure("missing", foreground=theme.color("danger"))
        self.tree.tag_configure("normal", foreground=theme.color("text"))
        self.refresh()

    def folders(self) -> List[Folder]:
        return self.model.folders()

    def selected_paths(self) -> List[str]:
        return self.model.selected_paths()

    def set_folders(self, folders: List[Folder]) -> None:
        self.model = FolderSet(folders)
        self.model.refresh_missing()
        self.refresh()

    def merge(self, folders: List[Folder]) -> int:
        added = self.model.merge(folders)
        self.refresh()
        return added

    def remove_selected(self) -> None:
        if not self.model.remove(list(self.tree.selection())):
            return
        self.refresh()
        self._changed()

    # ---------------------------------------------------------------- display

    def refresh(self) -> None:
        selection = [item for item in self.tree.selection() if self.model.get(item)]
        self.tree.delete(*self.tree.get_children())
        covered = self.model.covered()
        for key in self.model.render_order():
            folder = self.model.get(key)
            parent = self._parent_item(key)
            label = folder.name if parent else shorten(folder.path)
            glyph = CHECKED if folder.selected else UNCHECKED
            tags = ("missing",) if folder.missing else ("covered",) if key in covered else ("normal",)
            self.tree.insert(parent, "end", iid=key, text=f"{glyph}  {label}",
                             values=(self._counts(folder, key in covered),), tags=tags,
                             open=True)
        if selection:
            self.tree.selection_set([item for item in selection if self.tree.exists(item)])

    def _parent_item(self, key: str) -> str:
        """The row this one nests under -- guaranteed to be inserted already,
        because :meth:`FolderSet.render_order` puts ancestors first."""
        parent = self.model.parent_of(key)
        return parent if parent and self.tree.exists(parent) else ""

    def _counts(self, folder: Folder, is_covered: bool) -> str:
        if folder.missing:
            return t("gui.folder.missing")
        if is_covered:
            return t("gui.folder.covered")
        if not folder.counted:
            return ""
        return t("gui.folder.counts", notes=folder.notes, images=folder.images)

    # ----------------------------------------------------------------- events

    def _on_click(self, event: tk.Event):
        if self.tree.identify_region(event.x, event.y) not in ("tree", "cell"):
            return None
        if "indicator" in (self.tree.identify_element(event.x, event.y) or ""):
            return None  # the disclosure triangle keeps its job
        item = self.tree.identify_row(event.y)
        if item:
            self.model.toggle(item)
            self.refresh()
            self._changed()
        return "break"

    def _on_space(self, _event):
        for item in self.tree.selection():
            self.model.toggle(item)
        self.refresh()
        self._changed()
        return "break"

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()
