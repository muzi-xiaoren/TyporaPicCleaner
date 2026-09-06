"""Move unreferenced images out of the way -- reversibly.

Nothing here calls :func:`os.remove`.  Files go either to a manifest-backed
folder inside the vault or to the OS trash, so that a mistake in the analysis
costs the user a ``restore`` command rather than their pictures.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .i18n import t
from .paths import has_image_ext, is_within
from .scanner import TRASH_DIRNAME

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1


class UnsafePath(Exception):
    """Raised when a path fails the guard rails and must not be touched."""


@dataclass
class Entry:
    anchor: int
    rel: str
    stored: str
    size: int


@dataclass
class Batch:
    """One clean-up run, as recorded on disk."""

    batch_id: str
    trash_dir: str
    anchors: list[str] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    system_trash: bool = False
    failures: list[str] = field(default_factory=list)
    pruned_dirs: list[str] = field(default_factory=list)

    @property
    def moved_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)


def trash_root_for(md_root: str) -> str:
    return os.path.join(os.path.abspath(md_root), TRASH_DIRNAME)


def check_safe(path: str, roots: tuple[str, ...], extra_exts: frozenset[str] = frozenset()) -> None:
    """Two independent guard rails, both of which must pass.

    Extension whitelist: even a wildly wrong analysis can only ever move image
    files.  Containment: a reference such as ``../../../Documents`` must not be
    able to steer us out of the tree the user actually pointed at.
    """
    if not has_image_ext(path, extra_exts):
        raise UnsafePath(t("err.not_an_image", path=path))
    if not any(is_within(path, root) for root in roots):
        raise UnsafePath(t("err.outside_roots", path=path))
    if TRASH_DIRNAME in os.path.abspath(path).split(os.sep):
        raise UnsafePath(t("err.already_trashed", path=path))


def _anchor_for(path: str, roots: tuple[str, ...]) -> int:
    """Index of the deepest root containing *path* (deepest wins for nesting)."""
    best, best_len = -1, -1
    for index, root in enumerate(roots):
        if is_within(path, root) and len(root) > best_len:
            best, best_len = index, len(root)
    if best < 0:
        raise UnsafePath(t("err.no_anchor", path=path))
    return best


def move_to_trash(
    paths: list[str],
    roots: tuple[str, ...],
    md_root: str,
    system_trash: bool = False,
    extra_exts: frozenset[str] = frozenset(),
    prune_empty_dirs: bool = True,
) -> Batch:
    """Relocate *paths*, recording enough detail to undo it.

    Files that vanish or fail to move are collected in ``batch.failures``
    instead of aborting: a half-finished run still leaves a valid manifest.
    """
    batch_id, trash_dir = _fresh_batch_dir(md_root)
    batch = Batch(batch_id=batch_id, trash_dir=trash_dir, anchors=list(roots), system_trash=system_trash)

    if system_trash:
        send_to_trash = _system_trash_fn()

    for path in paths:
        try:
            check_safe(path, roots, extra_exts)
            anchor = _anchor_for(path, roots)
            rel = os.path.relpath(path, roots[anchor])
            size = os.path.getsize(path)
            if system_trash:
                send_to_trash(path)
                stored = ""
            else:
                stored = os.path.join("files", str(anchor), rel)
                destination = os.path.join(trash_dir, stored)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.move(path, destination)
            batch.entries.append(Entry(anchor=anchor, rel=rel, stored=stored, size=size))
        except (UnsafePath, OSError) as exc:
            batch.failures.append(f"{path}: {exc}")

    if prune_empty_dirs:
        batch.pruned_dirs = _prune_empty_dirs(
            {os.path.dirname(path) for path in paths}, roots
        )
    if batch.entries or batch.failures:
        write_manifest(batch)
    return batch


def _fresh_batch_dir(md_root: str) -> tuple[str, str]:
    """A batch id that is not already taken.

    The id is a second-resolution timestamp, so two cleans in the same second
    would otherwise share a folder and the second manifest would overwrite the
    first -- losing the ability to undo either one cleanly.
    """
    root = trash_root_for(md_root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_id = stamp
    suffix = 2
    while os.path.exists(os.path.join(root, batch_id)):
        batch_id = f"{stamp}-{suffix}"
        suffix += 1
    return batch_id, os.path.join(root, batch_id)


def _system_trash_fn():
    try:
        from send2trash import send2trash  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise UnsafePath(t("err.needs_send2trash")) from exc
    return send2trash


def _prune_empty_dirs(dirs: set[str], roots: tuple[str, ...]) -> list[str]:
    """Remove directories emptied by the move, walking upwards.

    Stops at every scanned root, so the vault's own top-level folders survive
    even when they end up empty.
    """
    removed: list[str] = []
    root_reals = {os.path.realpath(root) for root in roots}
    for start in sorted(dirs, key=len, reverse=True):
        current = start
        while current and os.path.realpath(current) not in root_reals:
            if not any(is_within(current, root) for root in roots):
                break
            try:
                if os.listdir(current):
                    break
                os.rmdir(current)
            except OSError:
                break
            removed.append(current)
            current = os.path.dirname(current)
    return removed


def write_manifest(batch: Batch) -> str:
    os.makedirs(batch.trash_dir, exist_ok=True)
    path = os.path.join(batch.trash_dir, MANIFEST_NAME)
    payload = {
        "version": MANIFEST_VERSION,
        "tool": "typora-pic-cleaner",
        "batch_id": batch.batch_id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "system_trash": batch.system_trash,
        "anchors": batch.anchors,
        "entries": [asdict(entry) for entry in batch.entries],
        "pruned_dirs": batch.pruned_dirs,
        "failures": batch.failures,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path


def list_batches(md_root: str) -> list[dict]:
    """Every recorded clean-up under *md_root*, newest first."""
    root = trash_root_for(md_root)
    batches: list[dict] = []
    if not os.path.isdir(root):
        return batches
    for name in sorted(os.listdir(root), reverse=True):
        manifest = os.path.join(root, name, MANIFEST_NAME)
        if not os.path.isfile(manifest):
            continue
        try:
            with open(manifest, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            batches.append({"batch_id": name, "error": str(exc), "entries": []})
            continue
        data["_dir"] = os.path.join(root, name)
        batches.append(data)
    return batches


def newest_restorable(roots) -> "tuple | None":
    """The most recent clean-up across *roots* that can still be put back.

    Two kinds of recorded batch cannot: one sent to the system trash, where only
    the operating system can return the files, and an empty one. Skipping them
    here is what lets an interface disable its undo button honestly instead of
    offering it and then failing.

    Returns ``(root, batch)`` or ``None``.
    """
    best = None
    for root in roots:
        for batch in list_batches(root):
            if batch.get("system_trash") or not batch.get("entries"):
                continue
            created = batch.get("created") or ""
            if best is None or created > best[0]:
                best = (created, root, batch)
    return (best[1], best[2]) if best else None


@dataclass
class RestoreResult:
    restored: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)


def restore_batch(md_root: str, batch_id: str | None = None, dry_run: bool = False) -> RestoreResult:
    """Put a batch's files back where they came from.

    An existing file at the destination is never overwritten -- the user may
    have replaced the picture since -- it is reported as skipped instead.
    """
    batches = list_batches(md_root)
    if not batches:
        raise UnsafePath(t("err.no_history", path=trash_root_for(md_root)))
    if batch_id:
        matching = [b for b in batches if b.get("batch_id") == batch_id or os.path.basename(b.get("_dir", "")) == batch_id]
        if not matching:
            raise UnsafePath(t("err.no_such_batch", batch=batch_id))
        batch = matching[0]
    else:
        batch = batches[0]

    if batch.get("system_trash"):
        raise UnsafePath(t("err.batch_in_system_trash", batch=batch.get("batch_id")))

    result = RestoreResult()
    anchors = batch.get("anchors", [])
    for entry in batch.get("entries", []):
        try:
            source = os.path.join(batch["_dir"], entry["stored"])
            target = os.path.join(anchors[entry["anchor"]], entry["rel"])
            if os.path.exists(target):
                result.skipped.append(t("err.already_exists", path=target))
                continue
            if not os.path.exists(source):
                result.failures.append(t("err.missing_from_trash", path=source))
                continue
            if not dry_run:
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.move(source, target)
            result.restored.append(target)
        except (OSError, KeyError, IndexError) as exc:
            result.failures.append(f"{entry}: {exc}")

    if not dry_run and not result.failures and not result.skipped:
        shutil.rmtree(batch["_dir"], ignore_errors=True)
        # Leave no empty .typora-pic-trash behind once the history is gone, so a
        # fully restored vault looks untouched.
        try:
            os.rmdir(trash_root_for(md_root))
        except OSError:
            pass
    return result
