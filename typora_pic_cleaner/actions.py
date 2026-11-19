"""Move unreferenced images out of the way -- reversibly.

Nothing here calls :func:`os.remove`.  Files go either to a manifest-backed
folder inside the vault or to the OS trash, so that a mistake in the analysis
costs the user a ``restore`` command rather than their pictures.

Each scanned folder keeps its own trash.  A picture never leaves the tree it
was found in, which makes the move a rename -- instant, and free of the copy
across drives that a single shared trash would turn into when the folders live
on different disks.  One clean-up therefore writes one batch per folder it
touched, all under the same batch id, and undoing it means restoring that id
everywhere it appears.
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
    """One folder's share of a clean-up run, as recorded on disk."""

    batch_id: str
    trash_dir: str
    anchors: list[str] = field(default_factory=list)
    entries: list[Entry] = field(default_factory=list)
    system_trash: bool = False
    failures: list[str] = field(default_factory=list)
    pruned_dirs: list[str] = field(default_factory=list)


@dataclass
class CleanResult:
    """Everything one clean-up run did, across every folder it touched."""

    batch_id: str
    batches: list[Batch] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    pruned_dirs: list[str] = field(default_factory=list)
    system_trash: bool = False

    @property
    def entries(self) -> list[Entry]:
        return [entry for batch in self.batches for entry in batch.entries]

    @property
    def moved_bytes(self) -> int:
        return sum(entry.size for entry in self.entries)

    @property
    def roots(self) -> list[str]:
        """The folders that now hold part of this run in their trash."""
        return [batch.anchors[0] for batch in self.batches if batch.entries]


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


def top_level_roots(roots: "tuple[str, ...] | list[str]") -> list[str]:
    """*roots* without duplicates and without any folder nested in another.

    These are the folders that get a trash of their own.  An image folder that
    sits inside a notes folder shares that folder's trash, so one tree never
    ends up with two histories.
    """
    unique = list(dict.fromkeys(os.path.abspath(root) for root in roots))
    return [
        root for root in unique
        if not any(other != root and is_within(root, other) for other in unique)
    ]


def _home_of(path: str, tops: list[str]) -> str:
    for top in tops:
        if is_within(path, top):
            return top
    raise UnsafePath(t("err.no_anchor", path=path))


def trash_destinations(paths: list[str], roots: tuple[str, ...]) -> list[str]:
    """The trash folders a clean-up of *paths* would write to, for telling the
    user before it happens."""
    tops = top_level_roots(roots)
    used = []
    for top in tops:
        if any(is_within(path, top) for path in paths):
            used.append(trash_root_for(top))
    return used


def move_to_trash(
    paths: list[str],
    roots: tuple[str, ...],
    system_trash: bool = False,
    extra_exts: frozenset[str] = frozenset(),
    prune_empty_dirs: bool = True,
) -> CleanResult:
    """Relocate *paths*, recording enough detail to undo it.

    Files that vanish or fail to move are collected in ``failures`` instead of
    aborting: a half-finished run still leaves valid manifests.
    """
    tops = top_level_roots(roots)
    batch_id = _fresh_batch_id(tops)
    result = CleanResult(batch_id=batch_id, system_trash=system_trash)
    by_top: dict[str, Batch] = {}

    if system_trash:
        send_to_trash = _system_trash_fn()

    try:
        for path in paths:
            batch = None
            try:
                check_safe(path, roots, extra_exts)
                top = _home_of(path, tops)
                batch = by_top.get(top)
                if batch is None:
                    batch = by_top[top] = Batch(
                        batch_id=batch_id,
                        trash_dir=os.path.join(trash_root_for(top), batch_id),
                        anchors=[top],
                        system_trash=system_trash,
                    )
                    result.batches.append(batch)
                rel = os.path.relpath(path, top)
                size = os.path.getsize(path)
                if system_trash:
                    send_to_trash(path)
                    stored = ""
                else:
                    stored = os.path.join("files", "0", rel)
                    destination = os.path.join(batch.trash_dir, stored)
                    os.makedirs(os.path.dirname(destination), exist_ok=True)
                    shutil.move(path, destination)
                batch.entries.append(Entry(anchor=0, rel=rel, stored=stored, size=size))
            except (UnsafePath, OSError) as exc:
                failure = f"{path}: {exc}"
                result.failures.append(failure)
                if batch is not None:
                    batch.failures.append(failure)

        if prune_empty_dirs:
            result.pruned_dirs = _prune_empty_dirs(
                {os.path.dirname(path) for path in paths}, roots
            )
            for batch in result.batches:
                batch.pruned_dirs = [
                    d for d in result.pruned_dirs if is_within(d, batch.anchors[0])
                ]
    finally:
        # In a ``finally`` because the manifest is the only thing that knows
        # where the moved files came from.  A Ctrl-C part-way through a large
        # clean must still leave batches that ``restore`` can put back.
        for batch in result.batches:
            if batch.entries:
                write_manifest(batch)
    return result


def _fresh_batch_id(tops: list[str]) -> str:
    """A batch id not already taken in any folder about to use it.

    The id is a second-resolution timestamp, so two cleans in the same second
    would otherwise share a folder and the second manifest would overwrite the
    first -- losing the ability to undo either one cleanly.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_id = stamp
    suffix = 2
    while any(os.path.exists(os.path.join(trash_root_for(top), batch_id)) for top in tops):
        batch_id = f"{stamp}-{suffix}"
        suffix += 1
    return batch_id


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
            if not isinstance(data, dict):
                raise ValueError("not a manifest")
        except (OSError, ValueError) as exc:
            batches.append({"batch_id": name, "error": str(exc), "entries": [],
                            "_dir": os.path.join(root, name)})
            continue
        data["_dir"] = os.path.join(root, name)
        batches.append(data)
    return batches


def _has_something_to_restore(batch: dict) -> bool:
    """Whether at least one file of *batch* could actually go back.

    A batch can be left holding only files whose place has since been taken --
    restore skips those rather than overwrite.  Offering it again would undo
    nothing, and would stand in front of every older batch that still could.
    """
    anchors = batch.get("anchors", [])
    for entry in batch.get("entries", []):
        try:
            source = os.path.join(batch["_dir"], entry["stored"])
            target = os.path.join(anchors[entry["anchor"]], entry["rel"])
        except (KeyError, IndexError, TypeError):
            continue
        if os.path.exists(source) and not os.path.exists(target):
            return True
    return False


def newest_restorable(roots) -> "tuple | None":
    """The most recent clean-up across *roots* that can still be put back.

    Three kinds of recorded batch cannot: one sent to the system trash, where
    only the operating system can return the files; an empty one; and one whose
    remaining files would all be skipped. Leaving them out here is what lets an
    interface disable its undo button honestly instead of offering it and then
    failing.

    Returns ``(root, batch)`` or ``None``.  The same run may have left batches
    in other folders too: restore it with :func:`restore_everywhere`.
    """
    best = None
    for root in top_level_roots(roots):
        for batch in list_batches(root):
            if batch.get("system_trash") or not batch.get("entries"):
                continue
            created = batch.get("created") or ""
            if best is not None and created <= best[0]:
                continue
            if _has_something_to_restore(batch):
                best = (created, root, batch)
    return (best[1], best[2]) if best else None


def batches_named(roots, batch_id: str) -> "list[tuple[str, dict]]":
    """Every ``(root, batch)`` among *roots* recorded under *batch_id*."""
    return [
        (root, batch)
        for root in top_level_roots(roots)
        for batch in list_batches(root)
        if batch.get("batch_id") == batch_id
    ]


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

    if batch.get("error"):
        # Refused outright rather than treated as an empty batch: "nothing to
        # restore, so tidy up" would delete the very files the user is after.
        raise UnsafePath(t("err.unreadable_manifest", batch=batch.get("batch_id"),
                           detail=batch["error"], path=batch["_dir"]))
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

    if not dry_run and result.restored and (result.failures or result.skipped):
        # Keep only what is still in the trash, so the history says what it
        # actually holds rather than counting files that are long back home.
        _rewrite_entries(batch, [
            entry for entry in batch.get("entries", [])
            if os.path.exists(os.path.join(batch["_dir"], entry.get("stored", "")))
            and entry.get("stored")
        ])
    if not dry_run and not result.failures and not result.skipped:
        shutil.rmtree(batch["_dir"], ignore_errors=True)
        # Leave no empty .typora-pic-trash behind once the history is gone, so a
        # fully restored vault looks untouched.
        try:
            os.rmdir(trash_root_for(md_root))
        except OSError:
            pass
    return result


def _rewrite_entries(batch: dict, entries: list) -> None:
    payload = {key: value for key, value in batch.items() if not key.startswith("_")}
    payload["entries"] = entries
    try:
        with open(os.path.join(batch["_dir"], MANIFEST_NAME), "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
    except OSError:
        pass  # the old manifest is still valid, merely over-counting


def restore_everywhere(roots, batch_id: str | None = None, dry_run: bool = False) -> RestoreResult:
    """Undo one clean-up in every folder that holds part of it.

    Without *batch_id* the most recent run is taken.  This is the counterpart
    of :func:`move_to_trash` giving each folder its own trash: the user undoes
    "the last clean", not one folder's fragment of it.
    """
    tops = top_level_roots(roots)
    recorded = [(root, batch) for root in tops for batch in list_batches(root)]
    if not recorded:
        raise UnsafePath(t("err.no_history", path=", ".join(trash_root_for(top) for top in tops)))
    if batch_id is None:
        batch_id = max(
            recorded, key=lambda pair: (pair[1].get("created") or "", pair[1].get("batch_id") or "")
        )[1].get("batch_id")
    holders = [root for root, batch in recorded if batch.get("batch_id") == batch_id]
    if not holders:
        raise UnsafePath(t("err.no_such_batch", batch=batch_id))
    combined = RestoreResult()
    for root in holders:
        part = restore_batch(root, batch_id=batch_id, dry_run=dry_run)
        combined.restored.extend(part.restored)
        combined.skipped.extend(part.skipped)
        combined.failures.extend(part.failures)
    return combined
