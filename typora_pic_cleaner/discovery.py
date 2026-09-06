"""The folders worth scanning: finding them, and keeping the user's choice.

Typora has no notion of a "vault": people end up with several unrelated note
folders, often nested a couple of levels under one parent.  Pointing the tool
at that parent and being shown what is inside -- with note and picture counts
-- is a much better first move than a file-picker that accepts a single path.

:func:`discover` does the finding.  :class:`FolderSet` holds the answer
afterwards: which folders are ticked, what a repeat search may overwrite, and
which of them a scan should actually be given.  Nothing here touches Tk, so all
of it can be tested on a machine with no display.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .paths import has_image_ext
from .scanner import MARKDOWN_EXTS, prune_dirnames

#: How far below the chosen parent folders are offered.  Deeper directories are
#: still counted -- they just roll up into an ancestor rather than becoming
#: their own row, which keeps the list readable for a deep tree.
DEFAULT_MAX_DEPTH = 3

#: Trees a search must not wander into.  Their Markdown is documentation that
#: shipped with some software, not anything the user wrote, and offering them
#: turns a list of four real folders into a list of forty.  Only the *search*
#: skips these: a folder added by hand is always honoured, whatever it is
#: called, because then the user has said so explicitly.
UNINTERESTING_DIRS = frozenset({
    # Windows system and recycle trees
    "$recycle.bin", "$winreagent", "system volume information", "recovery",
    "appdata", "program files", "program files (x86)", "programdata", "windows",
    # macOS
    "library", "applications",
    # Python and package managers
    "site-packages", "dist-packages", "__pypackages__", ".tox", "vendor",
    "anaconda", "anaconda3", "miniconda", "miniconda3", "miniforge3",
})

#: Note names that come with a package rather than from a person.  A folder
#: whose Markdown is all called README or CHANGELOG is a source tree, and this
#: catches the ones no list of directory names could.
#: Deliberately narrow.  A folder is dropped only when *every* note in it is
#: on this list, so a name a person might really use -- todo, index, notes --
#: stays off it: the cost of guessing wrong is a real folder the search never
#: offers, and the user would have no idea it was missing.
BOILERPLATE_STEMS = frozenset({
    "readme", "changelog", "changes", "license", "licence", "copying",
    "contributing", "code_of_conduct", "security", "authors", "upgrading",
    "installation",
})


@dataclass
class Folder:
    """A folder on the user's list, and whether it is ticked for scanning.

    Kept separate from :class:`Candidate` because a folder can arrive by hand
    rather than from a search, may since have been deleted, and carries the one
    piece of state a search cannot recreate: the user's own choice.
    """

    path: str
    selected: bool = True
    notes: int = 0
    images: int = 0
    missing: bool = False
    counted: bool = False

    @property
    def name(self) -> str:
        return os.path.basename(self.path) or self.path


@dataclass
class Candidate:
    """One folder that could be scanned, with what it holds."""

    path: str
    #: Directory this sits in, or ``None`` for the folder the user chose.
    parent: Optional[str]
    depth: int
    #: Notes and pictures in the whole subtree, not just directly inside.
    notes: int
    images: int
    #: Notes sitting directly in this folder, which is what tells "a real notes
    #: folder" apart from "a parent that merely contains some".
    own_notes: int
    #: Markdown left out of ``notes`` for looking like packaged documentation,
    #: kept so the caller can say how much noise was filtered rather than
    #: silently disagreeing with the user's own file count.
    skipped_notes: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path) or self.path


def shorten(path: str, limit: int = 34) -> str:
    """A path short enough for the sidebar, trimmed from the left.

    The sidebar is narrow and a Treeview truncates on the right, so a long path
    shown in full would leave the user reading ``/Users/me/Library/Applica``.
    The tail is the part that identifies a folder, so the head is what goes.
    """
    home = os.path.expanduser("~")
    if home and path.startswith(home + os.sep):
        path = "~" + path[len(home):]
    if len(path) <= limit:
        return path
    pieces = [piece for piece in path.replace("\\", "/").split("/") if piece]
    if not pieces:
        return path
    kept = pieces[-1]
    for piece in reversed(pieces[:-1]):
        # Rejoined with the platform's own separator: the pieces were split on
        # both, so a fixed one would hand Windows a mixed path.
        candidate = piece + os.sep + kept
        if len(candidate) + 2 > limit:
            break
        kept = candidate
    return "\u2026" + os.sep + kept


class FolderSet:
    """The user's folder list, with no widget attached.

    Split out from the sidebar because this is where the decisions live -- what
    is ticked, what a repeat search may overwrite, which folder is made
    redundant by an ancestor -- and none of them should need a display to
    verify.
    """

    def __init__(self, folders: Optional[List[Folder]] = None) -> None:
        self._by_key: Dict[str, Folder] = {}
        self._order: List[str] = []
        for folder in folders or []:
            self.add(folder)

    def __len__(self) -> int:
        return len(self._order)

    def __iter__(self):
        return (self._by_key[key] for key in self._order)

    def keys(self) -> List[str]:
        return list(self._order)

    def get(self, path: str) -> Optional[Folder]:
        return self._by_key.get(key_for(path))

    def folders(self) -> List[Folder]:
        return list(self)

    def add(self, folder: Folder) -> bool:
        """Add a folder; ``False`` if that path was already on the list."""
        key = key_for(folder.path)
        if key in self._by_key:
            return False
        self._by_key[key] = folder
        self._order.append(key)
        return True

    def merge(self, folders: List[Folder]) -> int:
        """Fold a fresh search into the list, returning how many were new.

        Counts are refreshed, but a tick is never overwritten: unticking a
        drafts folder once has to survive every later search that finds it
        again, or the memory is worthless.
        """
        added = 0
        for folder in folders:
            existing = self._by_key.get(key_for(folder.path))
            if existing is None:
                self.add(folder)
                added += 1
                continue
            existing.notes = folder.notes
            existing.images = folder.images
            existing.counted = existing.counted or folder.counted
            existing.missing = folder.missing
        return added

    def remove(self, paths: List[str]) -> int:
        """Drop *paths* and anything nested inside them."""
        doomed = set()
        for path in paths:
            doomed.add(key_for(path))
            doomed.update(key for key in self._order if within(key, path))
        self._order = [key for key in self._order if key not in doomed]
        for key in doomed:
            self._by_key.pop(key, None)
        return len(doomed)

    def toggle(self, path: str) -> None:
        folder = self.get(path)
        if folder is not None and not folder.missing:
            folder.selected = not folder.selected

    def set_all(self, value: bool) -> None:
        for folder in self:
            if not folder.missing:
                folder.selected = value

    def refresh_missing(self) -> None:
        for folder in self:
            folder.missing = not os.path.isdir(folder.path)

    def covered(self) -> set:
        """Ticked folders that another ticked folder already contains."""
        ticked = [key for key in self._order
                  if self._by_key[key].selected and not self._by_key[key].missing]
        return {key for key in ticked
                if any(other != key and within(key, other) for other in ticked)}

    def selected_paths(self) -> List[str]:
        """What to actually scan: ticked, present, and not nested in each other.

        Handing both a parent and its child to the scan would inventory the
        child twice.  Harmless for the verdict, but it doubles the note count on
        screen, and a number the user cannot reconcile reads as a bug.
        """
        covered = self.covered()
        return [self._by_key[key].path for key in self._order
                if self._by_key[key].selected
                and not self._by_key[key].missing
                and key not in covered]

    def parent_of(self, path: str) -> Optional[str]:
        """The deepest other folder on the list that contains *path*.

        Worked out from the paths rather than remembered, so the tree still
        nests correctly after a restart, and a folder added by hand slots under
        one that was found by a search.
        """
        key = key_for(path)
        best = None
        for other in self._order:
            if other != key and within(key, other) and (best is None or len(other) > len(best)):
                best = other
        return best

    def render_order(self) -> List[str]:
        """Keys with every ancestor ahead of its descendants, for a tree view."""
        return sorted(self._order, key=lambda key: key.count(os.sep))


def key_for(path: str) -> str:
    """The spelling-independent identity of a path, for use as a dict key."""
    return os.path.normcase(os.path.abspath(path))


def within(path: str, root: str) -> bool:
    """Is *path* strictly inside *root*?  A folder does not contain itself."""
    path, root = key_for(path), key_for(root)
    if path == root:
        return False
    try:
        return not os.path.relpath(path, root).startswith(os.pardir)
    except ValueError:
        return False


def discover(
    parent: str,
    max_depth: int = DEFAULT_MAX_DEPTH,
    extra_exts: frozenset = frozenset(),
) -> List[Candidate]:
    """Folders under *parent* whose subtree holds at least one note of the
    user's own.

    Returned parents-first, so the list can be poured straight into a tree view.
    Software trees and packaged documentation are left out entirely -- see
    :data:`UNINTERESTING_DIRS` and :data:`BOILERPLATE_STEMS` -- because a search
    that answers with four hundred rows is no better than no search at all.
    """
    parent = os.path.abspath(parent)
    notes: Dict[str, int] = {}
    images: Dict[str, int] = {}
    own: Dict[str, int] = {}
    skipped: Dict[str, int] = {}
    visited: List[str] = []

    for dirpath, dirnames, filenames in os.walk(parent, onerror=lambda _e: None):
        prune_dirnames(dirnames)
        dirnames[:] = [d for d in dirnames if d.lower() not in UNINTERESTING_DIRS]
        visited.append(dirpath)
        note_count = image_count = boilerplate = 0
        for filename in filenames:
            stem, ext = os.path.splitext(filename)
            if ext.lower() in MARKDOWN_EXTS:
                # Counted apart, and never credited upwards: a thousand vendored
                # READMEs under one folder would otherwise make its row read as
                # the biggest pile of notes on the disk.
                if stem.lower() in BOILERPLATE_STEMS:
                    boilerplate += 1
                else:
                    note_count += 1
            elif has_image_ext(filename, extra_exts):
                image_count += 1
        own[dirpath] = note_count
        # Credit every ancestor up to the chosen parent, so a folder's row
        # reports its whole subtree even when the notes live three levels down.
        current = dirpath
        while True:
            notes[current] = notes.get(current, 0) + note_count
            images[current] = images.get(current, 0) + image_count
            skipped[current] = skipped.get(current, 0) + boilerplate
            if _same(current, parent):
                break
            upwards = os.path.dirname(current)
            if upwards == current:
                break
            current = upwards

    found: List[Candidate] = []
    for dirpath in visited:
        depth = _depth(dirpath, parent)
        if depth > max_depth or not notes.get(dirpath):
            continue
        found.append(
            Candidate(
                path=dirpath,
                parent=None if depth == 0 else os.path.dirname(dirpath),
                depth=depth,
                notes=notes.get(dirpath, 0),
                images=images.get(dirpath, 0),
                own_notes=own.get(dirpath, 0),
                skipped_notes=skipped.get(dirpath, 0),
            )
        )
    return found


def summarise(path: str, extra_exts: frozenset = frozenset()) -> Tuple[int, int]:
    """``(notes, images)`` in one folder's subtree, counted without any filter.

    For a folder the user added by hand.  The search's idea of what is worth
    offering must not apply here: the number beside the row has to match what a
    scan of that folder would actually see, and a scan counts every Markdown
    file it finds.
    """
    notes = images = 0
    for _dirpath, dirnames, filenames in os.walk(path, onerror=lambda _e: None):
        prune_dirnames(dirnames)
        for filename in filenames:
            if os.path.splitext(filename)[1].lower() in MARKDOWN_EXTS:
                notes += 1
            elif has_image_ext(filename, extra_exts):
                images += 1
    return notes, images


def _depth(path: str, parent: str) -> int:
    if _same(path, parent):
        return 0
    try:
        relative = os.path.relpath(path, parent)
    except ValueError:
        return DEFAULT_MAX_DEPTH + 1
    return relative.count(os.sep) + 1


def _same(left: str, right: str) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))
