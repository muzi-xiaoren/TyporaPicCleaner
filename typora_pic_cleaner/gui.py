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
from .actions import UnsafePath, list_batches, move_to_trash, restore_batch, trash_root_for
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
        root.geometry("1080x700")
        root.minsize(880, 560)
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
        prefs.save(paranoid=bool(self.paranoid.get()), appearance=self.appearance)

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
        self.root.configure(background=self.theme.color("bg"))
        self._build_menubar()
        self._build_header()
        self._build_body()
        self._build_footer()
        self._render_status()
        self._render_rows()
        self._render_stats()

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
        body = ttk.Frame(self.root, style="TFrame")
        body.pack(fill="both", expand=True)
        self._build_sidebar(body)
        ttk.Frame(body, style="Rule.TFrame", width=1).pack(side="left", fill="y")
        self._build_content(body)

    def _build_sidebar(self, parent: tk.Misc) -> None:
        side = ttk.Frame(parent, style="Sidebar.TFrame", width=SIDEBAR_WIDTH,
                         padding=(PAD, PAD, PAD, PAD))
        side.pack(side="left", fill="y")
        side.pack_propagate(False)

        self._section(side, t("gui.section.notes"))
        self.notes_list = FolderList(side, self.theme, on_change=self._folders_changed, height=9)
        self.notes_list.pack(fill="both", expand=True)
        self.notes_list.set_folders(self.notes_folders)
        self._button_row(side, (
            (t("gui.btn.find"), self._find_folders, "primary"),
            (t("gui.btn.add"), self._add_notes_folder, "secondary"),
            (t("gui.btn.remove"), self.notes_list.remove_selected, "ghost"),
        ))
        ttk.Label(side, text=t("gui.hint.notes"), style="SidebarMuted.TLabel",
                  wraplength=SIDEBAR_WIDTH - PAD * 2, justify="left").pack(anchor="w", pady=(6, 0))

        self._section(side, t("gui.section.images"), top=18)
        self.image_list = FolderList(side, self.theme, on_change=self._folders_changed, height=4)
        self.image_list.pack(fill="x")
        self.image_list.set_folders(self.image_folders)
        self._button_row(side, (
            (t("gui.btn.add"), self._add_image_folder, "secondary"),
            (t("gui.btn.remove"), self.image_list.remove_selected, "ghost"),
        ))
        ttk.Label(side, text=t("gui.hint.images"), style="SidebarMuted.TLabel",
                  wraplength=SIDEBAR_WIDTH - PAD * 2, justify="left").pack(anchor="w", pady=(6, 0))

        self._section(side, t("gui.section.options"), top=18)
        ttk.Checkbutton(side, text=t("gui.cautious"), variable=self.paranoid,
                        style="Sidebar.TCheckbutton").pack(anchor="w")
        ttk.Checkbutton(side, text=t("gui.use_system_trash"), variable=self.system_trash,
                        style="Sidebar.TCheckbutton").pack(anchor="w", pady=(4, 0))
        # The one failure mode a careful list cannot rule out: notes that link
        # these pictures but live in no folder on this list.  It belongs beside
        # the list, because widening the list is the fix.
        ttk.Label(side, text=t("gui.caution"), style="SidebarMuted.TLabel",
                  wraplength=SIDEBAR_WIDTH - PAD * 2, justify="left").pack(
            anchor="w", side="bottom", pady=(12, 0))

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

    def _build_content(self, parent: tk.Misc) -> None:
        content = ttk.Frame(parent, style="TFrame", padding=(PAD + 4, PAD, PAD + 4, 0))
        content.pack(side="left", fill="both", expand=True)
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
        self.status_label = ttk.Label(footer, text="", style="Muted.TLabel",
                                      wraplength=560, justify="left")
        self.status_label.pack(side="left", fill="x", expand=True)

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
        destination = (t("cli.clean.system_trash") if self.system_trash.get()
                       else trash_root_for(self.analysis.md_root))
        if not messagebox.askyesno(
            t("gui.confirm.move_title"),
            t("gui.confirm.move_body", count=len(chosen),
              size=human_size(sum(row["size"] for row in chosen)), destination=destination),
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

    def _undo_root(self) -> Optional[str]:
        """The folder holding the most recent clean-up.

        Searched across every ticked folder rather than assuming the first: the
        list can be reordered between runs, and an undo that silently looks in
        the wrong place is worse than no undo button.
        """
        newest, newest_root = None, None
        for root in self.notes_list.selected_paths():
            for batch in list_batches(root):
                created = batch.get("created") or ""
                if newest is None or created > newest:
                    newest, newest_root = created, root
        return newest_root

    def _restore(self) -> None:
        roots = self.notes_list.selected_paths()
        if not roots:
            messagebox.showerror(t("gui.title"), t("gui.err.pick_cleaned_folder"))
            return
        root = self._undo_root()
        if root is None:
            messagebox.showinfo(t("gui.title"),
                                t("gui.info.no_history", path=trash_root_for(roots[0])))
            return
        newest = list_batches(root)[0]
        if not messagebox.askyesno(
            t("gui.confirm.undo_title"),
            t("gui.confirm.undo_body", count=len(newest.get("entries", [])),
              batch=newest.get("batch_id"), created=newest.get("created")),
        ):
            return
        try:
            result = restore_batch(root)
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
            Folder(path=c.path, selected=True, notes=c.notes, images=c.images, counted=True)
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
