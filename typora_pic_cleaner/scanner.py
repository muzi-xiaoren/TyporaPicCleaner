"""Walk a vault: find the notes, find the pictures, guess the layout."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .paths import IMAGE_EXTS, has_image_ext

MARKDOWN_EXTS = frozenset({".md", ".markdown", ".mdown", ".mkd", ".mdwn", ".mdtxt"})

#: Directories that never hold a user's notes or pictures.  Skipping them keeps
#: the scan quick and, more importantly, stops us proposing to delete images
#: belonging to a checked-out repository or a plugin.
SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", ".obsidian", ".trash", ".idea",
        ".vscode", "__pycache__", ".venv", "venv", ".DS_Store", ".stfolder",
    }
)

TRASH_DIRNAME = ".typora-pic-trash"

#: Folder names that conventionally act as a shared image store.
SHARED_IMAGE_DIRNAMES = frozenset({"assets", "images", "image", "img", "media", "pics", "pictures", "static"})


@dataclass
class ImageFile:
    path: str
    size: int


@dataclass
class Walk:
    """Raw inventory of a tree, before any reference matching."""

    markdown: list[str] = field(default_factory=list)
    images: list[ImageFile] = field(default_factory=list)
    asset_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _prune(dirnames: list[str]) -> None:
    dirnames[:] = [
        d for d in dirnames
        if d not in SKIP_DIRS and d != TRASH_DIRNAME and not d.startswith(".")
    ]


def walk_tree(root: str, extra_exts: frozenset[str] = frozenset(),
              collect_markdown: bool = True, collect_images: bool = True) -> Walk:
    """Inventory *root* in one pass."""
    result = Walk()
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: result.errors.append(str(e))):
        _prune(dirnames)
        for dirname in dirnames:
            if dirname.lower().endswith(".assets"):
                result.asset_dirs.append(os.path.join(dirpath, dirname))
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            ext = os.path.splitext(filename)[1].lower()
            if collect_markdown and ext in MARKDOWN_EXTS:
                result.markdown.append(full)
            elif collect_images and has_image_ext(filename, extra_exts):
                try:
                    result.images.append(ImageFile(full, os.path.getsize(full)))
                except OSError as exc:  # broken symlink, permissions, race
                    result.errors.append(f"{full}: {exc}")
    return result


def merge(walks: list[Walk]) -> Walk:
    """Combine several walks, dropping paths seen twice (overlapping roots)."""
    merged = Walk()
    seen_md: set[str] = set()
    seen_img: set[str] = set()
    seen_dir: set[str] = set()
    for walk in walks:
        for path in walk.markdown:
            if path not in seen_md:
                seen_md.add(path)
                merged.markdown.append(path)
        for image in walk.images:
            if image.path not in seen_img:
                seen_img.add(image.path)
                merged.images.append(image)
        for path in walk.asset_dirs:
            if path not in seen_dir:
                seen_dir.add(path)
                merged.asset_dirs.append(path)
        merged.errors.extend(walk.errors)
    return merged


def detect_layouts(walk: Walk, image_dirs: tuple[str, ...], md_root: str) -> list[str]:
    """Describe how this vault stores its pictures.

    Purely informational, but worth printing: it is the quickest way for the
    user to notice that we are looking in the wrong place before anything gets
    moved.
    """
    layouts: list[str] = []
    if walk.asset_dirs:
        layouts.append(f"sibling .assets folders ({len(walk.asset_dirs)} found)")

    shared: set[str] = set()
    for image in walk.images:
        parent = os.path.basename(os.path.dirname(image.path)).lower()
        if parent in SHARED_IMAGE_DIRNAMES:
            shared.add(os.path.dirname(image.path))
    if shared:
        layouts.append(f"shared image folders ({len(shared)}: " + ", ".join(
            sorted(os.path.basename(p) for p in shared)[:4]) + ")")

    external = [d for d in image_dirs if not _under(d, md_root)]
    if external:
        layouts.append("global image folder outside the note tree (" + ", ".join(external) + ")")

    # Images inside a folder the user explicitly named are not "loose" -- that
    # folder is the whole point of passing --images.
    loose = sum(
        1 for image in walk.images
        if os.path.basename(os.path.dirname(image.path)).lower() not in SHARED_IMAGE_DIRNAMES
        and not os.path.dirname(image.path).lower().endswith(".assets")
        and not any(_under(image.path, image_dir) for image_dir in image_dirs)
    )
    if loose:
        layouts.append(f"{loose} image(s) sitting directly beside notes")
    return layouts or ["no images found"]


def _under(path: str, root: str) -> bool:
    try:
        return not os.path.relpath(
            os.path.realpath(path), os.path.realpath(root)
        ).startswith(os.pardir)
    except ValueError:
        return False


def read_text_best_effort(path: str) -> tuple[str, str | None]:
    """Read a note as text, returning ``(text, error)``.

    Notes written on Windows are not always UTF-8, and a mis-decoded byte in the
    middle of a filename would hide a live reference.  So the encodings are
    tried strictly first and only the last resort is lossy.
    """
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        return "", f"{path}: {exc}"
    # UTF-16 is only guessed when a BOM says so -- sniffing it on byte
    # frequency alone turns legible CJK text into mojibake.
    encodings = ("utf-8-sig", "gb18030", "cp1252")
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ("utf-16",) + encodings
    for encoding in encodings:
        try:
            return raw.decode(encoding), None
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace"), f"{path}: undecodable bytes, scanned with replacements"
