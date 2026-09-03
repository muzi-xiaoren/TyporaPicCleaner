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
from .report import human_size


class App:
    def __init__(self, root: tk.Tk, initial_root: str = "") -> None:
        self.root = root
        self.analysis: Analysis | None = None
        self.results: "queue.Queue[tuple[str, object]]" = queue.Queue()

        root.title("Typora Pic Cleaner")
        root.geometry("940x600")
        root.minsize(760, 460)

        self.notes_dir = tk.StringVar(value=initial_root)
        self.image_dir = tk.StringVar()
        self.paranoid = tk.BooleanVar(value=False)
        self.system_trash = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Pick your Typora notes folder, then scan.")

        self._build_paths_frame()
        self._build_options_frame()
        self._build_table()
        self._build_status_bar()
        self.root.after(120, self._drain_results)

    # ---------------------------------------------------------------- layout

    def _build_paths_frame(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 10, 10, 4))
        frame.pack(fill="x")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Notes folder").grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.notes_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(frame, text="Browse...", command=self._pick_notes).grid(row=0, column=2)

        ttk.Label(frame, text="Image folder").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame, textvariable=self.image_dir).grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(frame, text="Browse...", command=self._pick_images).grid(row=1, column=2, pady=(6, 0))
        ttk.Label(
            frame,
            text="Optional: only needed when Typora saves images outside the notes folder.",
            foreground="#666",
        ).grid(row=2, column=1, sticky="w", padx=6)

    def _build_options_frame(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 6))
        frame.pack(fill="x")
        ttk.Checkbutton(
            frame, text="Cautious mode (also keep images merely named in the text)",
            variable=self.paranoid,
        ).pack(side="left")
        ttk.Checkbutton(frame, text="Use system trash", variable=self.system_trash).pack(side="left", padx=(14, 0))

        self.scan_button = ttk.Button(frame, text="Scan", command=self._scan)
        self.scan_button.pack(side="right")
        self.delete_button = ttk.Button(frame, text="Move selected to trash", command=self._clean, state="disabled")
        self.delete_button.pack(side="right", padx=6)
        self.restore_button = ttk.Button(frame, text="Undo last clean", command=self._restore)
        self.restore_button.pack(side="right", padx=6)

    def _build_table(self) -> None:
        frame = ttk.Frame(self.root, padding=(10, 0))
        frame.pack(fill="both", expand=True)

        toolbar = ttk.Frame(frame)
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="Select all", command=lambda: self._set_all(True)).pack(side="left")
        ttk.Button(toolbar, text="Select none", command=lambda: self._set_all(False)).pack(side="left", padx=4)
        self.summary = ttk.Label(toolbar, text="")
        self.summary.pack(side="right")

        columns = ("keep", "size", "path")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="extended")
        self.tree.heading("keep", text="Delete?")
        self.tree.heading("size", text="Size")
        self.tree.heading("path", text="Unreferenced image")
        self.tree.column("keep", width=70, anchor="center", stretch=False)
        self.tree.column("size", width=90, anchor="e", stretch=False)
        self.tree.column("path", width=700, anchor="w")
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
        ttk.Label(
            bar,
            text="Files go to a recoverable trash. Scan the folder that contains ALL "
                 "notes linking these images -- links from outside it cannot be seen.",
            foreground="#8a5a00",
            wraplength=520,
            justify="right",
        ).pack(side="right")

    # --------------------------------------------------------------- helpers

    def _pick_notes(self) -> None:
        chosen = filedialog.askdirectory(title="Select your Typora notes folder")
        if chosen:
            self.notes_dir.set(chosen)

    def _pick_images(self) -> None:
        chosen = filedialog.askdirectory(title="Select the folder Typora saves images into")
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

    def _refresh_summary(self) -> None:
        chosen = [item for item in self.tree.get_children() if self.checked.get(item, True)]
        total = sum(self.sizes.get(item, 0) for item in chosen)
        self.summary.configure(text=f"{len(chosen)} selected, {human_size(total)}")
        self.delete_button.configure(state="normal" if chosen else "disabled")

    # ---------------------------------------------------------------- actions

    def _scan(self) -> None:
        notes = self.notes_dir.get().strip()
        if not os.path.isdir(notes):
            messagebox.showerror("Typora Pic Cleaner", "Please choose an existing notes folder first.")
            return
        image_dirs = tuple(d for d in [self.image_dir.get().strip()] if d)
        # Every Tk variable has to be read here, on the main thread: touching one
        # from the worker raises "main thread is not in main loop".
        paranoid = self.paranoid.get()
        self.scan_button.configure(state="disabled")
        self.delete_button.configure(state="disabled")
        self.status.set("Scanning...")

        def work() -> None:
            try:
                analysis = analyze(notes, image_dirs=image_dirs, paranoid=paranoid)
                self.results.put(("scan", analysis))
            except Exception as exc:  # surfaced in the UI rather than a dead thread
                self.results.put(("error", exc))

        threading.Thread(target=work, daemon=True).start()

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

        notes = [
            f"{analysis.md_count} notes, {analysis.total_images} images",
            f"{analysis.referenced} referenced",
            f"{len(analysis.unreferenced)} unreferenced",
        ]
        if analysis.broken:
            notes.append(f"{len(analysis.broken)} broken links")
        if analysis.orphan_asset_dirs:
            notes.append(f"{len(analysis.orphan_asset_dirs)} orphaned .assets folders")
        if analysis.external:
            notes.append(f"{len(analysis.external)} links outside the scanned folder")
        self.status.set(" | ".join(notes))
        self._refresh_summary()

    def _clean(self) -> None:
        if not self.analysis:
            return
        selected = [self.paths[item] for item in self.tree.get_children() if self.checked.get(item, True)]
        if not selected:
            return
        total = human_size(sum(self.sizes[item] for item in self.tree.get_children() if self.checked.get(item, True)))
        destination = "the system trash" if self.system_trash.get() else trash_root_for(self.analysis.md_root)
        if not messagebox.askyesno(
            "Move to trash?",
            f"Move {len(selected)} file(s) ({total}) to:\n{destination}\n\n"
            "Nothing is erased -- use \"Undo last clean\" to put them back.",
        ):
            return
        roots = (self.analysis.md_root,) + self.analysis.image_dirs
        try:
            batch = move_to_trash(
                selected, roots=roots, md_root=self.analysis.md_root,
                system_trash=self.system_trash.get(),
            )
        except UnsafePath as exc:
            messagebox.showerror("Typora Pic Cleaner", str(exc))
            return
        message = f"Moved {len(batch.entries)} file(s), {human_size(batch.moved_bytes)}."
        if batch.failures:
            message += f"\n\n{len(batch.failures)} could not be moved:\n" + "\n".join(batch.failures[:8])
        messagebox.showinfo("Typora Pic Cleaner", message)
        self._scan()

    def _restore(self) -> None:
        notes = self.notes_dir.get().strip()
        if not os.path.isdir(notes):
            messagebox.showerror("Typora Pic Cleaner", "Please choose the notes folder that was cleaned.")
            return
        batches = list_batches(notes)
        if not batches:
            messagebox.showinfo("Typora Pic Cleaner", f"No clean-up history under\n{trash_root_for(notes)}")
            return
        newest = batches[0]
        count = len(newest.get("entries", []))
        if not messagebox.askyesno(
            "Undo last clean?",
            f"Put back {count} file(s) from batch {newest.get('batch_id')} ({newest.get('created')})?",
        ):
            return
        try:
            result = restore_batch(notes)
        except UnsafePath as exc:
            messagebox.showerror("Typora Pic Cleaner", str(exc))
            return
        message = f"Restored {len(result.restored)} file(s)."
        if result.skipped:
            message += f"\n\nSkipped {len(result.skipped)} (a file already exists there):\n" + "\n".join(result.skipped[:8])
        if result.failures:
            message += f"\n\nFailed {len(result.failures)}:\n" + "\n".join(result.failures[:8])
        messagebox.showinfo("Typora Pic Cleaner", message)
        self._scan()

    def _drain_results(self) -> None:
        try:
            while True:
                kind, payload = self.results.get_nowait()
                self.scan_button.configure(state="normal")
                if kind == "scan":
                    self._show_analysis(payload)  # type: ignore[arg-type]
                else:
                    self.status.set("Scan failed.")
                    messagebox.showerror("Typora Pic Cleaner", str(payload))
        except queue.Empty:
            pass
        self.root.after(120, self._drain_results)


def main(initial_root: str = "") -> int:
    root = tk.Tk()
    App(root, initial_root=initial_root)
    root.mainloop()
    return 0
