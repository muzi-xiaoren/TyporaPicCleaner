"""The window: a sidebar of folders you tick, a list of pictures you untick.

Two ideas shape it.  The first is that choosing what to scan is the real work,
so it gets the sidebar rather than a single text field: folders are searched
for, ticked, added by hand, and remembered between launches.  The second is
that nothing here is allowed to surprise the user -- scanning is the default
action, every finding starts ticked but can be dropped, and the button that
deletes says where the files are going before it moves one.

Every colour and font lives in :mod:`.palette` and :mod:`.theme`, and every
decision about which folders count lives in ``discovery.FolderSet``; this
module only arranges them.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

from . import prefs
from .actions import (
    UnsafePath, move_to_trash, newest_restorable, restore_batch, trash_root_for,
)
from .compare import Analysis, analyze
from .discovery import Folder, discover, shorten, summarise
from .folderlist import FolderList
from .i18n import get_language, set_language, t
from .palette import CHECKED, UNCHECKED
from .report import display_path, human_size
from .theme import RoundedButton, Theme

SIDEBAR_WIDTH = 320
PAD = 16


class App:
    def __init__(self, root: tk.Tk, initial_roots: Optional[List[str]] = None) -> None:
        self.root = root
        self.analysis: Optional[Analysis] = None
        self.results: "queue.Queue[tuple]" = queue.Queue()
        self.rows: List[dict] = []
        self.busy = False
        #: Labels whose text has to re-flow when a sash moves.
        self._wrapping: List[tuple] = []
        self._sash_main = prefs.load_pixel("sash_main", SIDEBAR_WIDTH)
        self._sash_side = prefs.load_pixel("sash_side", 320)

        self.appearance = prefs.load().get("appearance") or "auto"
        self.theme = Theme(root, self.appearance)

        self.notes_folders = self._restore_notes_folders(initial_roots or [])
        self.image_folders = [
            Folder(path=path, selected=True, missing=not os.path.isdir(path))
            for path in prefs.load_image_folders()
        ]
        self.paranoid = tk.BooleanVar(value=bool(prefs.load().get("paranoid")))
        self.system_trash = tk.BooleanVar(value=False)
        self.language = tk.StringVar(value=get_language())
        self.appearance_var = tk.StringVar(value=self.appearance)
        self.status_key = "gui.status.start"
        self.status_params: dict = {}
        self.status_text: Optional[str] = None

        root.title(t("gui.title"))
        root.geometry("1120x760")
        root.minsize(900, 660)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        self.root.after(120, self._drain_results)

    # ------------------------------------------------------------------ state

    def _restore_notes_folders(self, initial_roots: List[str]) -> List[Folder]:
        folders: List[Folder] = []
        seen = set()
        for path in initial_roots:
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen:
                seen.add(key)
                folders.append(Folder(path=path, selected=True, missing=not os.path.isdir(path)))
        for path, selected in prefs.load_note_folders():
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            folders.append(
                Folder(path=path, selected=selected, missing=not os.path.isdir(path))
            )
        return folders

    def _capture(self) -> None:
        """Pull the widgets' state back into plain data, before they are torn down."""
        if hasattr(self, "notes_list"):
            self.notes_folders = self.notes_list.folders()
            self.image_folders = self.image_list.folders()

    def _persist(self) -> None:
        self._capture()
        prefs.save_note_folders([(f.path, f.selected) for f in self.notes_folders])
        prefs.save_image_folders([f.path for f in self.image_folders if f.selected])
        positions = self._sash_positions()
        self._sash_main = positions.get("sash_main", self._sash_main)
        self._sash_side = positions.get("sash_sidebar", self._sash_side)
        prefs.save(paranoid=bool(self.paranoid.get()), appearance=self.appearance,
                   sash_main=self._sash_main, sash_side=self._sash_side)

    def _on_close(self) -> None:
        self._persist()
        self.root.destroy()

    # ----------------------------------------------------------------- layout

    def _build(self) -> None:
        # Everything goes, menus included: rebuilding is how the window
        # changes language or theme, and a kept-around tk.Menu would leak one
        # copy per switch.
        for child in list(self.root.winfo_children()):
            child.destroy()
        self._wrapping = []
        self.root.configure(background=self.theme.color("bg"))
        self._build_menubar()
        self._build_header()
        self._build_body()
        self._build_footer()
        self._render_status()
        self._render_rows()
        self._render_stats()
        self._refresh_undo_state()

    def _rebuild(self) -> None:
        self._capture()
        self._build()

    # header ---------------------------------------------------------------

    def _build_header(self) -> None:
        header = ttk.Frame(self.root, style="TFrame", padding=(PAD + 4, PAD, PAD + 4, 12))
        header.pack(fill="x")
        left = ttk.Frame(header, style="TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text=t("gui.title"), style="Title.TLabel").pack(anchor="w")
        ttk.Label(left, text=t("gui.subtitle"), style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        gear = RoundedButton(header, self.theme, "⚙  " + t("gui.menu.settings"),
                             command=self._popup_settings, kind="ghost")
        gear.pack(side="right", anchor="n")
        self.gear = gear

        self.progress = ttk.Progressbar(self.root, mode="indeterminate",
                                        style="Thin.Horizontal.TProgressbar")
        self.rule = ttk.Frame(self.root, style="Rule.TFrame", height=1)
        self.rule.pack(fill="x")

    def _build_menubar(self) -> None:
        menubar = tk.Menu(self.root)
        language = tk.Menu(menubar, tearoff=False)
        for code in ("en", "zh"):
            language.add_radiobutton(label=t(f"gui.menu.lang.{code}"), value=code,
                                     variable=self.language, command=self._change_language)
        menubar.add_cascade(label=t("gui.menu.language"), menu=language)
        appearance = tk.Menu(menubar, tearoff=False)
        for mode in ("auto", "light", "dark"):
            appearance.add_radiobutton(label=t(f"gui.menu.appearance.{mode}"), value=mode,
                                       variable=self.appearance_var,
                                       command=self._change_appearance)
        menubar.add_cascade(label=t("gui.menu.appearance"), menu=appearance)
        self.root.configure(menu=menubar)

    def _popup_settings(self) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        for code in ("en", "zh"):
            menu.add_radiobutton(label=t(f"gui.menu.lang.{code}"), value=code,
                                 variable=self.language, command=self._change_language)
        menu.add_separator()
        for mode in ("auto", "light", "dark"):
            menu.add_radiobutton(label=t(f"gui.menu.appearance.{mode}"), value=mode,
                                 variable=self.appearance_var, command=self._change_appearance)
        x = self.gear.winfo_rootx()
        y = self.gear.winfo_rooty() + self.gear.winfo_height() + 4
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # body -----------------------------------------------------------------

    def _build_body(self) -> None:
        # Panes rather than a fixed split: a folder list showing
        # ``E:\\...\\anaconda3\\envs`` needs more width than one showing
        # ``~/Notes``, and only the person looking at it knows which they have.
        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True)
        body.add(self._build_sidebar(body), weight=0)
        body.add(self._build_content(body), weight=1)
        self.body = body
        self.root.after(80, self._restore_sashes)

    def _restore_sashes(self) -> None:
        for panes, position in ((self.body, self._sash_main),
                                (self.sidebar_panes, self._sash_side)):
            try:
                panes.sashpos(0, position)
            except tk.TclError:  # not laid out yet, or a single pane
                pass

    def _sash_positions(self) -> dict:
        """Where the dividers are, ignoring the zero an unmapped pane reports."""
        found = {}
        for name, panes in (("sash_main", getattr(self, "body", None)),
                            ("sash_sidebar", getattr(self, "sidebar_panes", None))):
            if panes is None:
                continue
            try:
                position = int(panes.sashpos(0))
            except (tk.TclError, ValueError):
                continue
            if position > 60:
                found[name] = position
        return found

    def _build_sidebar(self, parent: tk.Misc) -> ttk.Frame:
        side = ttk.Frame(parent, style="Sidebar.TFrame", width=SIDEBAR_WIDTH,
                         padding=(PAD, PAD, PAD, PAD))
        # A second sash inside the sidebar, so someone with a deep folder tree
        # can trade the image list's height for it.
        panes = ttk.PanedWindow(side, orient="vertical")
        panes.pack(fill="both", expand=True)
        upper = ttk.Frame(panes, style="Sidebar.TFrame")
        lower = ttk.Frame(panes, style="Sidebar.TFrame")
        panes.add(upper, weight=1)
        panes.add(lower, weight=0)
        self.sidebar_panes = panes
        side.bind("<Configure>", lambda _event: self._rewrap())

        self._section(upper, t("gui.section.notes"))
        self.notes_list = FolderList(upper, self.theme, on_change=self._folders_changed, height=6)
        self.notes_list.pack(fill="both", expand=True)
        self.notes_list.set_folders(self.notes_folders)
        self._button_row(upper, (
            (t("gui.btn.find"), self._find_folders, "primary"),
            (t("gui.btn.add"), self._add_notes_folder, "secondary"),
            (t("gui.btn.remove"), self.notes_list.remove_selected, "ghost"),
        ))
        self._hint(upper, t("gui.hint.notes"))

        self._section(lower, t("gui.section.images"), top=18)
        self.image_list = FolderList(lower, self.theme, on_change=self._folders_changed, height=3)
        self.image_list.pack(fill="x")
        self.image_list.set_folders(self.image_folders)
        self._button_row(lower, (
            (t("gui.btn.add"), self._add_image_folder, "secondary"),
            (t("gui.btn.remove"), self.image_list.remove_selected, "ghost"),
        ))
        self._hint(lower, t("gui.hint.images"))

        self._section(lower, t("gui.section.options"), top=18)
        ttk.Checkbutton(lower, text=t("gui.cautious"), variable=self.paranoid,
                        style="Sidebar.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(lower, text=t("gui.use_system_trash"), variable=self.system_trash,
                        style="Sidebar.TCheckbutton").pack(anchor="w", pady=(4, 0))
        return side

    def _hint(self, parent: tk.Misc, text: str) -> None:
        label = ttk.Label(parent, text=text, style="SidebarMuted.TLabel",
                          wraplength=SIDEBAR_WIDTH - PAD * 2, justify="left")
        label.pack(anchor="w", pady=(6, 0))
        self._wrapping.append((label, parent, PAD * 2 + 10))

    def _rewrap(self) -> None:
        """Re-flow the explanatory text when a sash moves."""
        for label, container, inset in self._wrapping:
            width = container.winfo_width() - inset
            if width > 90:
                label.configure(wraplength=width)

    def _section(self, parent: tk.Misc, text: str, top: int = 0) -> None:
        ttk.Label(parent, text=text.upper() if text.isascii() else text,
                  style="SidebarSection.TLabel").pack(anchor="w", pady=(top, 6))

    def _button_row(self, parent: tk.Misc, buttons) -> None:
        row = ttk.Frame(parent, style="Sidebar.TFrame")
        row.pack(fill="x", pady=(8, 0))
        for index, (label, command, kind) in enumerate(buttons):
            button = RoundedButton(row, self.theme, label, command=command, kind=kind,
                                   background="sidebar", padding=10)
            button.pack(side="left", padx=(0 if index == 0 else 6, 0))

    def _build_content(self, parent: tk.Misc) -> ttk.Frame:
        content = ttk.Frame(parent, style="TFrame", padding=(PAD + 4, PAD, PAD + 4, 0))
        self._build_stats(content)

        toolbar = ttk.Frame(content, style="TFrame")
        toolbar.pack(fill="x", pady=(PAD, 8))
        RoundedButton(toolbar, self.theme, t("gui.select_all"),
                      command=lambda: self._set_all(True), kind="ghost", padding=10).pack(side="left")
        RoundedButton(toolbar, self.theme, t("gui.select_none"),
                      command=lambda: self._set_all(False), kind="ghost", padding=10).pack(
            side="left", padx=(6, 0))
        self.summary = ttk.Label(toolbar, text="", style="Muted.TLabel")
        self.summary.pack(side="right")

        table = ttk.Frame(content, style="TFrame")
        table.pack(fill="both", expand=True)
        columns = ("check", "size", "path")
        self.tree = ttk.Treeview(table, columns=columns, show="headings", selectmode="extended")
        self.tree.column("check", width=44, anchor="center", stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("path", width=520, anchor="w")
        self.tree.heading("check", text="")
        self.tree.heading("size", text=t("gui.column.size"))
        self.tree.heading("path", text=t("gui.column.path"))
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.tag_configure("odd", background=self.theme.color("stripe"))
        self.tree.tag_configure("even", background=self.theme.color("bg"))
        self.tree.bind("<Button-1>", self._on_row_click, add="+")
        self.tree.bind("<space>", self._on_row_space)
        self.tree.bind("<Double-1>", self._reveal_selected)

        self.empty = ttk.Label(table, text="", style="Faint.TLabel", justify="center")
        return content

    def _build_stats(self, parent: tk.Misc) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=(PAD, 14))
        card.pack(fill="x")
        self.stat_card = card
        self.tiles: Dict[str, ttk.Label] = {}
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x")
        for index, key in enumerate(("notes", "images", "unreferenced", "reclaimable")):
            cell = ttk.Frame(row, style="Card.TFrame")
            cell.pack(side="left", expand=True, fill="x")
            value = ttk.Label(cell, text="--", style="CardNumber.TLabel")
            value.pack(anchor="w")
            ttk.Label(cell, text=t(f"gui.tile.{key}"), style="CardMuted.TLabel").pack(anchor="w")
            self.tiles[key] = value
            if index < 3:
                ttk.Frame(row, style="Rule.TFrame", width=1).pack(side="left", fill="y", padx=8)
        self.bar = tk.Canvas(card, height=6, highlightthickness=0, bd=0,
                             background=self.theme.color("raised"))
        self.bar.pack(fill="x", pady=(12, 0))
        self.bar.bind("<Configure>", lambda _e: self._draw_bar())

    def _build_footer(self) -> None:
        ttk.Frame(self.root, style="Rule.TFrame", height=1).pack(fill="x")
        footer = ttk.Frame(self.root, style="TFrame", padding=(PAD + 4, 12))
        footer.pack(fill="x")
        text = ttk.Frame(footer, style="TFrame")
        text.pack(side="left", fill="x", expand=True)
        self.status_label = ttk.Label(text, text="", style="Muted.TLabel",
                                      wraplength=560, justify="left")
        self.status_label.pack(anchor="w")
        # The one failure mode a careful list cannot rule out: notes that link
        # these pictures but live in no folder on the list.  It sits by the
        # button that does the moving, where it is read last.
        caution = ttk.Label(text, text=t("gui.caution"), style="Warn.TLabel",
                            wraplength=560, justify="left")
        caution.pack(anchor="w", pady=(2, 0))
        self._wrapping.append((caution, text, 12))
        self.status_label.configure(wraplength=560)
        self._wrapping.append((self.status_label, text, 12))
        footer.bind("<Configure>", lambda _event: self._rewrap())

        self.clean_button = RoundedButton(footer, self.theme, t("gui.move_selected"),
                                          command=self._clean, kind="primary")
        self.clean_button.pack(side="right")
        self.clean_button.set_state("disabled")
        self.scan_button = RoundedButton(footer, self.theme, t("gui.scan"),
                                         command=self._scan, kind="secondary", min_width=96)
        self.scan_button.pack(side="right", padx=(0, 8))
        self.undo_button = RoundedButton(footer, self.theme, t("gui.undo"),
                                         command=self._restore, kind="ghost")
        self.undo_button.pack(side="right", padx=(0, 8))
        self.undo_button.set_state("disabled")

    # ------------------------------------------------------------- appearance

    def _change_language(self) -> None:
        set_language(self.language.get())
        prefs.save_language(self.language.get())
        self.root.title(t("gui.title"))
        self._rebuild()

    def _change_appearance(self) -> None:
        self.appearance = self.appearance_var.get()
        prefs.save(appearance=self.appearance)
        self.theme.apply(self.appearance)
        self._rebuild()

    # ------------------------------------------------------------ folder list

    def _folders_changed(self) -> None:
        self._persist()
        self._render_status()
        self._refresh_undo_state()

    def _find_folders(self) -> None:
        if self.busy:
            return
        parents = prefs.load_scan_parents()
        start = next((p for p in parents if os.path.isdir(p)), os.path.expanduser("~"))
        parent = filedialog.askdirectory(title=t("gui.pick_parent_title"), initialdir=start)
        if not parent:
            return
        prefs.save_scan_parents([parent] + [p for p in parents if p != parent])
        self._set_busy(True, "gui.status.finding", {"path": shorten(parent)})

        def work() -> None:
            try:
                self.results.put(("discover", discover(parent)))
            except Exception as exc:
                self.results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _add_notes_folder(self) -> None:
        chosen = filedialog.askdirectory(title=t("gui.pick_notes_title"))
        if not chosen:
            return
        notes, images = summarise(chosen)
        self.notes_list.merge([Folder(path=chosen, selected=True, notes=notes,
                                      images=images, counted=True)])
        self._folders_changed()

    def _add_image_folder(self) -> None:
        chosen = filedialog.askdirectory(title=t("gui.pick_images_title"))
        if not chosen:
            return
        notes, images = summarise(chosen)
        self.image_list.merge([Folder(path=chosen, selected=True, notes=notes,
                                      images=images, counted=True)])
        self._folders_changed()

    # ---------------------------------------------------------------- results

    def _render_stats(self) -> None:
        analysis = self.analysis
        if analysis is None:
            for label in self.tiles.values():
                label.configure(text="--")
        else:
            self.tiles["notes"].configure(text=str(analysis.md_count))
            self.tiles["images"].configure(text=str(analysis.total_images))
            self.tiles["unreferenced"].configure(text=str(len(analysis.unreferenced)))
            self.tiles["reclaimable"].configure(text=human_size(analysis.reclaimable_bytes))
        self._draw_bar()

    def _draw_bar(self) -> None:
        canvas = self.bar
        canvas.delete("all")
        width = canvas.winfo_width()
        height = int(canvas["height"])
        if width <= 1:
            return
        track = self.theme.color("track")
        canvas.create_rectangle(0, 0, width, height, fill=track, outline="")
        analysis = self.analysis
        if not analysis or not analysis.total_images:
            return
        used = analysis.referenced / analysis.total_images
        canvas.create_rectangle(0, 0, max(2, width * used), height,
                                fill=self.theme.color("ok"), outline="")
        canvas.create_rectangle(width * used, 0, width, height,
                                fill=self.theme.color("warn"), outline="")

    def _render_rows(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            item = self.tree.insert(
                "", "end",
                values=(CHECKED if row["checked"] else UNCHECKED,
                        human_size(row["size"]), row["display"]),
                tags=("odd" if index % 2 else "even",),
            )
            row["item"] = item
        if self.rows:
            self.empty.place_forget()
        else:
            self.empty.configure(text=self._empty_text())
            self.empty.place(relx=0.5, rely=0.42, anchor="center")
        self._refresh_summary()

    def _empty_text(self) -> str:
        if not self.notes_list.selected_paths():
            return t("gui.empty.no_folders")
        if self.analysis is None:
            return t("gui.empty.not_scanned")
        return t("gui.empty.nothing_found")

    def _refresh_summary(self) -> None:
        chosen = [row for row in self.rows if row["checked"]]
        total = sum(row["size"] for row in chosen)
        self.summary.configure(
            text=t("gui.summary", count=len(chosen), size=human_size(total)) if self.rows else ""
        )
        if hasattr(self, "clean_button"):
            self.clean_button.set_state("normal" if chosen and not self.busy else "disabled")

    def _on_row_click(self, event: tk.Event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        item = self.tree.identify_row(event.y)
        if item:
            self._toggle_item(item)
        return "break"

    def _on_row_space(self, _event):
        for item in self.tree.selection():
            self._toggle_item(item, refresh=False)
        self._refresh_summary()
        return "break"

    def _toggle_item(self, item: str, refresh: bool = True) -> None:
        for row in self.rows:
            if row.get("item") == item:
                row["checked"] = not row["checked"]
                self.tree.set(item, "check", CHECKED if row["checked"] else UNCHECKED)
                break
        if refresh:
            self._refresh_summary()

    def _set_all(self, value: bool) -> None:
        for row in self.rows:
            row["checked"] = value
            if row.get("item"):
                self.tree.set(row["item"], "check", CHECKED if value else UNCHECKED)
        self._refresh_summary()

    def _reveal_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        paths = [row["path"] for row in self.rows if row.get("item") == selection[0]]
        if paths:
            reveal(paths[0])

    # ---------------------------------------------------------------- actions

    def _set_busy(self, busy: bool, key: str = "", params: Optional[dict] = None) -> None:
        self.busy = busy
        self.scan_button.set_state("disabled" if busy else "normal")
        if busy:
            self.clean_button.set_state("disabled")
            self.progress.pack(fill="x", before=self.rule)
            self.progress.start(12)
            self.status_key, self.status_params, self.status_text = key, params or {}, None
            self._render_status()
        else:
            self.progress.stop()
            self.progress.pack_forget()
            self._refresh_summary()

    def _scan(self) -> None:
        if self.busy:
            return
        roots = self.notes_list.selected_paths()
        if not roots:
            messagebox.showerror(t("gui.title"), t("gui.err.pick_notes_first"))
            return
        image_dirs = tuple(
            folder.path for folder in self.image_list.folders()
            if folder.selected and os.path.isdir(folder.path)
        )
        # Every Tk variable is read here, on the main thread: touching one from
        # the worker raises "main thread is not in main loop".
        paranoid = self.paranoid.get()
        self._persist()
        self._set_busy(True, "gui.status.scanning", {"count": len(roots)})

        def work() -> None:
            try:
                self.results.put(("scan", analyze(roots, image_dirs=image_dirs, paranoid=paranoid)))
            except Exception as exc:
                self.results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _show_analysis(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.rows = [
            {"path": image.path, "size": image.size, "checked": True,
             "display": display_path(image.path, analysis.md_roots, analysis.image_dirs), "item": None}
            for image in analysis.unreferenced
        ]
        self._render_rows()
        self._render_stats()
        self._refresh_undo_state()
        self.status_text = self._summary_line(analysis)
        self._render_status()

    def _summary_line(self, analysis: Analysis) -> str:
        parts = [
            t("gui.stat.notes_images", notes=analysis.md_count, images=analysis.total_images),
            t("gui.stat.referenced", count=analysis.referenced),
            t("gui.stat.unreferenced", count=len(analysis.unreferenced)),
        ]
        if analysis.broken:
            parts.append(t("gui.stat.broken", count=len(analysis.broken)))
        if analysis.orphan_asset_dirs:
            parts.append(t("gui.stat.orphans", count=len(analysis.orphan_asset_dirs)))
        if analysis.external:
            parts.append(t("gui.stat.external", count=len(analysis.external)))
        return "  ·  ".join(parts)

    def _render_status(self) -> None:
        if not hasattr(self, "status_label"):
            return
        text = self.status_text if self.status_text else t(self.status_key, **self.status_params)
        self.status_label.configure(text=text)

    def _clean(self) -> None:
        if not self.analysis or self.busy:
            return
        chosen = [row for row in self.rows if row["checked"]]
        if not chosen:
            return
        system = self.system_trash.get()
        destination = (t("cli.clean.system_trash") if system
                       else trash_root_for(self.analysis.md_root))
        if not messagebox.askyesno(
            t("gui.confirm.move_title"),
            t("gui.confirm.move_body_system" if system else "gui.confirm.move_body",
              count=len(chosen), size=human_size(sum(row["size"] for row in chosen)),
              destination=destination),
        ):
            return
        try:
            batch = move_to_trash(
                [row["path"] for row in chosen],
                roots=self.analysis.roots,
                md_root=self.analysis.md_root,
                system_trash=self.system_trash.get(),
            )
        except UnsafePath as exc:
            messagebox.showerror(t("gui.title"), str(exc))
            return
        message = t("gui.info.moved", count=len(batch.entries), size=human_size(batch.moved_bytes))
        if batch.failures:
            message += "\n\n" + t("gui.info.move_failures", count=len(batch.failures)) + "\n"
            message += "\n".join(batch.failures[:8])
        messagebox.showinfo(t("gui.title"), message)
        self._scan()

    def _undoable(self) -> Optional[tuple]:
        """The newest clean-up that can actually be put back, as ``(root, batch)``.

        Every ticked folder is searched, not just the first: the list can be
        reordered between launches, and an undo that quietly looks in the wrong
        place is worse than no undo button.
        """
        return newest_restorable(self.notes_list.selected_paths())

    def _refresh_undo_state(self) -> None:
        """Light the undo button only when it has something to undo.

        A button that is always lit and then explains itself in an error dialog
        is telling the user the same untruth as a confirmation that promises an
        undo which cannot happen.
        """
        if hasattr(self, "undo_button"):
            self.undo_button.set_state("normal" if self._undoable() else "disabled")

    def _restore(self) -> None:
        roots = self.notes_list.selected_paths()
        if not roots:
            messagebox.showerror(t("gui.title"), t("gui.err.pick_cleaned_folder"))
            return
        found = self._undoable()
        if found is None:
            messagebox.showinfo(t("gui.title"),
                                t("gui.info.no_history", path=trash_root_for(roots[0])))
            return
        root, newest = found
        if not messagebox.askyesno(
            t("gui.confirm.undo_title"),
            t("gui.confirm.undo_body", count=len(newest.get("entries", [])),
              batch=newest.get("batch_id"), created=newest.get("created")),
        ):
            return
        try:
            result = restore_batch(root, batch_id=newest.get("batch_id"))
        except UnsafePath as exc:
            messagebox.showerror(t("gui.title"), str(exc))
            return
        message = t("gui.info.restored", count=len(result.restored))
        if result.skipped:
            message += "\n\n" + t("gui.info.restore_skipped", count=len(result.skipped)) + "\n"
            message += "\n".join(result.skipped[:8])
        if result.failures:
            message += "\n\n" + t("gui.info.restore_failed", count=len(result.failures)) + "\n"
            message += "\n".join(result.failures[:8])
        messagebox.showinfo(t("gui.title"), message)
        self._scan()

    # ----------------------------------------------------------------- worker

    def _drain_results(self) -> None:
        try:
            while True:
                kind, payload = self.results.get_nowait()
                self._set_busy(False)
                if kind == "scan":
                    self._show_analysis(payload)
                elif kind == "discover":
                    self._absorb_discovery(payload)
                else:
                    self.status_key, self.status_params = "gui.status.scan_failed", {}
                    self.status_text = None
                    self._render_status()
                    messagebox.showerror(t("gui.title"), str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_results)

    def _absorb_discovery(self, candidates) -> None:
        found = [
            # Unticked on purpose.  A search that ticks everything it finds has
            # made the choice for the user, and on a whole drive that means
            # scanning tens of thousands of files nobody asked about.
            Folder(path=c.path, selected=False, notes=c.notes, images=c.images, counted=True)
            for c in candidates
        ]
        added = self.notes_list.merge(found)
        self.notes_folders = self.notes_list.folders()
        self._persist()
        self.status_text = None
        if not found:
            self.status_key, self.status_params = "gui.status.found_none", {}
        else:
            self.status_key = "gui.status.found"
            self.status_params = {"count": len(found), "added": added}
        self._render_status()
        self._render_rows()


def reveal(path: str) -> None:
    """Show a file in the platform's file manager, ignoring any failure.

    Purely a convenience for checking a picture before deleting it, so a
    missing file manager must not raise into the interface.
    """
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except (OSError, subprocess.SubprocessError):
        pass


def main(initial_roots: Optional[List[str]] = None) -> int:
    set_language(None)
    root = tk.Tk()
    App(root, initial_roots=initial_roots)
    root.mainloop()
    return 0
