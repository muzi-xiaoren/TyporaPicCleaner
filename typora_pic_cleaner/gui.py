"""A small Tkinter front end over the same analysis the CLI uses.

Tkinter ships with CPython on both macOS and Windows, which keeps the packaged
binary dependency-free.  The window deliberately mirrors the CLI's safety
model: scanning is the default action, every file starts out ticked but can be
unticked, and the delete button spells out where the files are going.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .actions import UnsafePath, list_batches, move_to_trash, restore_batch, trash_root_for
from .compare import Analysis, analyze
from . import prefs
from .i18n import get_language, set_language, t
from .report import human_size


class App:
    def __init__(self, root: tk.Tk, initial_root: str = "") -> None:
        self.root = root
        self.analysis: Analysis | None = None
        self.results: "queue.Queue[tuple[str, object]]" = queue.Queue()
        # Widgets whose label is a fixed string, so switching language can
        # rewrite them in place instead of rebuilding the window.
        self._labelled: list[tuple[tk.Widget, str]] = []

        root.title(t("gui.title"))
        root.geometry("980x620")
        root.minsize(780, 480)

        self.notes_dir = tk.StringVar(value=initial_root)
        self.image_dir = tk.StringVar()
        self.paranoid = tk.BooleanVar(value=False)
        self.system_trash = tk.BooleanVar(value=False)
        self.language = tk.StringVar(value=get_language())
        self.status = tk.StringVar(value=t("gui.status.start"))
        self._status_is_default = True

        self._build_menu()
        self._build_paths_frame()
        self._build_options_frame()
        self._build_table()
        self._build_status_bar()
        self.root.after(120, self._drain_results)

    # ---------------------------------------------------------------- layout

    def _track(self, widget: tk.Widget, key: str) -> tk.Widget:
        self._labelled.append((widget, key))
        return widget

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        self._language_menu = tk.Menu(menubar, tearoff=False)
        for code in ("en", "zh"):
            self._language_menu.add_radiobutton(
                label=t(f"gui.menu.lang.{code}"),
                value=code,
                variable=self.language,
                command=self._change_language,
            )
        menubar.add_cascade(label=t("gui.menu.language"), menu=self._language_menu)
        self._menubar = menubar
        self.root.configure(menu=menubar)

    def _build_paths_frame(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)

        self._track(ttk.Label(frame, text=t("gui.notes_folder")), "gui.notes_folder").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Entry(frame, textvariable=self.notes_dir).grid(row=0, column=1, sticky="ew", padx=6)
        self._track(
            ttk.Button(frame, text=t("gui.browse"), command=self._pick_notes), "gui.browse"
        ).grid(row=0, column=2)

        self._track(ttk.Label(frame, text=t("gui.image_folder")), "gui.image_folder").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Entry(frame, textvariable=self.image_dir).grid(
            row=1, column=1, sticky="ew", padx=6, pady=(6, 0)
        )
        self._track(
            ttk.Button(frame, text=t("gui.browse"), command=self._pick_images), "gui.browse"
        ).grid(row=1, column=2, pady=(6, 0))
        self._track(
            ttk.Label(frame, text=t("gui.image_folder.hint"), foreground="#666"),
            "gui.image_folder.hint",
        ).grid(row=2, column=1, sticky="w", padx=6)

    def _build_options_frame(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 6))
        frame.pack(fill="x")
        self._track(
            ttk.Checkbutton(frame, text=t("gui.cautious"), variable=self.paranoid), "gui.cautious"
        ).pack(side="left")
        self._track(
            ttk.Checkbutton(frame, text=t("gui.use_system_trash"), variable=self.system_trash),
            "gui.use_system_trash",
        ).pack(side="left", padx=(14, 0))

        self.scan_button = ttk.Button(frame, text=t("gui.scan"), command=self._scan)
        self._track(self.scan_button, "gui.scan").pack(side="right")
        self.delete_button = ttk.Button(
            frame, text=t("gui.move_selected"), command=self._clean, state="disabled"
        )
        self._track(self.delete_button, "gui.move_selected").pack(side="right", padx=6)
        self.restore_button = ttk.Button(frame, text=t("gui.undo"), command=self._restore)
        self._track(self.restore_button, "gui.undo").pack(side="right", padx=6)

    def _build_table(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 0))
        frame.pack(fill="both", expand=True)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 4))
        self._track(
            ttk.Button(toolbar, text=t("gui.select_all"), command=lambda: self._set_all(True)),
            "gui.select_all",
        ).pack(side="left")
        self._track(
            ttk.Button(toolbar, text=t("gui.select_none"), command=lambda: self._set_all(False)),
            "gui.select_none",
        ).pack(side="left", padx=4)
        self.summary = ttk.Label(toolbar, text="")
        self.summary.pack(side="right")

        columns = ("keep", "size", "path")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        self.tree.column("keep", width=80, anchor="center", stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("path", width=700, anchor="w")
        self._retranslate_headings()
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<space>", lambda _event: self._toggle_selected())
        self.tree.bind("<Button-1>", self._on_click)

        self.checked: dict[str, bool] = {}
        self.paths: dict[str, str] = {}
        self.sizes: dict[str, int] = {}

    def _build_status_bar(self) -> None:
        bar = ttk.Frame(self.root, padding=(10, 6))
        bar.pack(fill="x")
        ttk.Label(bar, textvariable=self.status, foreground="#444").pack(side="left")
        # The one failure mode a careful list cannot rule out: notes that link
        # these images but live outside the folder being scanned.  Worth saying
        # on screen, not only in the README.
        self._track(
            ttk.Label(
                bar, text=t("gui.caution"), foreground="#8a5a00", wraplength=520, justify="right"
            ),
            "gui.caution",
        ).pack(side="right")

    # ------------------------------------------------------------- language

    def _retranslate_headings(self) -> None:
        self.tree.heading("keep", text=t("gui.column.delete"))
        self.tree.heading("size", text=t("gui.column.size"))
        self.tree.heading("path", text=t("gui.column.path"))

    def _change_language(self) -> None:
        set_language(self.language.get())
        # Remembered so the choice survives a restart, which matters most for
        # the people who need it: those whose system language is not the one
        # they want the tool in.
        prefs.save_language(self.language.get())
        self.root.title(t("gui.title"))
        for widget, key in self._labelled:
            widget.configure(text=t(key))
        self._retranslate_headings()
        # Rebuilt rather than relabelled: menu entry text is fixed at creation.
        self._build_menu()
        if self._status_is_default:
            self.status.set(t("gui.status.start"))
        elif self.analysis:
            self._set_status_from(self.analysis)
        self._refresh_summary()

    # --------------------------------------------------------------- helpers

    def _pick_notes(self) -> None:
        chosen = filedialog.askdirectory(title=t("gui.pick_notes_title"))
        if chosen:
            self.notes_dir.set(chosen)

    def _pick_images(self) -> None:
        chosen = filedialog.askdirectory(title=t("gui.pick_images_title"))
        if chosen:
            self.image_dir.set(chosen)

    def _on_click(self, event: tk.Event) -> None:
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#1":
            return
        item = self.tree.identify_row(event.y)
        if item:
            self._toggle(item)

    def _toggle_selected(self) -> None:
        for item in self.tree.selection():
            self._toggle(item)

    def _toggle(self, item: str) -> None:
        self.checked[item] = not self.checked.get(item, True)
        self.tree.set(item, "keep", "x" if self.checked[item] else "")
        self._refresh_summary()

    def _set_all(self, value: bool) -> None:
        for item in self.tree.get_children():
            self.checked[item] = value
            self.tree.set(item, "keep", "x" if value else "")
        self._refresh_summary()

    def _selected_items(self) -> list[str]:
        return [item for item in self.tree.get_children() if self.checked.get(item, True)]

    def _refresh_summary(self) -> None:
        chosen = self._selected_items()
        total = sum(self.sizes.get(item, 0) for item in chosen)
        self.summary.configure(text=t("gui.summary", count=len(chosen), size=human_size(total)))
        self.delete_button.configure(state="normal" if chosen else "disabled")

    # ---------------------------------------------------------------- actions

    def _scan(self) -> None:
        notes = self.notes_dir.get().strip()
        if not os.path.isdir(notes):
            messagebox.showerror(t("gui.title"), t("gui.err.pick_notes_first"))
            return
        image_dirs = tuple(d for d in [self.image_dir.get().strip()] if d)
        # Every Tk variable has to be read here, on the main thread: touching one
        # from the worker raises "main thread is not in main loop".
        paranoid = self.paranoid.get()
        self.scan_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self.status.set(t("gui.status.scanning"))
        self._status_is_default = False

        def work() -> None:
            try:
                analysis = analyze(notes, image_dirs=image_dirs, paranoid=paranoid)
                self.results.put(("scan", analysis))
            except Exception as exc:  # surfaced in the UI rather than a dead thread
                self.results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

    def _set_status_from(self, analysis: Analysis) -> None:
        notes = [
            t("gui.stat.notes_images", notes=analysis.md_count, images=analysis.total_images),
            t("gui.stat.referenced", count=analysis.referenced),
            t("gui.stat.unreferenced", count=len(analysis.unreferenced)),
        ]
        if analysis.broken:
            notes.append(t("gui.stat.broken", count=len(analysis.broken)))
        if analysis.orphan_asset_dirs:
            notes.append(t("gui.stat.orphans", count=len(analysis.orphan_asset_dirs)))
        if analysis.external:
            notes.append(t("gui.stat.external", count=len(analysis.external)))
        self.status.set(" | ".join(notes))
        self._status_is_default = False

    def _show_analysis(self, analysis: Analysis) -> None:
        self.analysis = analysis
        self.tree.delete(*self.tree.get_children())
        self.checked.clear()
        self.paths.clear()
        self.sizes.clear()
        for image in analysis.unreferenced:
            try:
                shown = os.path.relpath(image.path, analysis.md_root)
                if shown.startswith(os.pardir):
                    shown = image.path
            except ValueError:
                shown = image.path
            item = self.tree.insert("", "end", values=("x", human_size(image.size), shown))
            self.checked[item] = True
            self.paths[item] = image.path
            self.sizes[item] = image.size
        self._set_status_from(analysis)
        self._refresh_summary()

    def _clean(self) -> None:
        if not self.analysis:
            return
        items = self._selected_items()
        if not items:
            return
        selected = [self.paths[item] for item in items]
        total = human_size(sum(self.sizes[item] for item in items))
        destination = (
            t("cli.clean.system_trash")
            if self.system_trash.get()
            else trash_root_for(self.analysis.md_root)
        )
        if not messagebox.askyesno(
            t("gui.confirm.move_title"),
            t("gui.confirm.move_body", count=len(selected), size=total, destination=destination),
        ):
            return
        roots = (self.analysis.md_root,) + self.analysis.image_dirs
        try:
            batch = move_to_trash(
                selected,
                roots=roots,
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

    def _restore(self) -> None:
        notes = self.notes_dir.get().strip()
        if not os.path.isdir(notes):
            messagebox.showerror(t("gui.title"), t("gui.err.pick_cleaned_folder"))
            return
        batches = list_batches(notes)
        if not batches:
            messagebox.showinfo(t("gui.title"), t("gui.info.no_history", path=trash_root_for(notes)))
            return
        newest = batches[0]
        if not messagebox.askyesno(
            t("gui.confirm.undo_title"),
            t(
                "gui.confirm.undo_body",
                count=len(newest.get("entries", [])),
                batch=newest.get("batch_id"),
                created=newest.get("created"),
            ),
        ):
            return
        try:
            result = restore_batch(notes)
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

    def _drain_results(self) -> None:
        try:
            while True:
                kind, payload = self.results.get_nowait()
                self.scan_button.configure(state="normal")
                if kind == "scan":
                    self._show_analysis(payload)  # type: ignore[arg-type]
                else:
                    self.status.set(t("gui.status.scan_failed"))
                    messagebox.showerror(t("gui.title"), str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_results)


def main(initial_root: str = "") -> int:
    set_language(None)
    root = tk.Tk()
    App(root, initial_root=initial_root)
    root.mainloop()
    return 0
