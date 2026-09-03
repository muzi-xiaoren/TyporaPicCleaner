"""Decide which images on disk no note points at any more."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .paths import PathKeyer, has_image_ext, is_within, resolve_reference
from .refs import Reference, extract_references
from .scanner import ImageFile, Walk, detect_layouts, merge, read_text_best_effort, walk_tree


@dataclass
class RefSite:
    """A reference plus the note it was found in."""

    md: str
    line: int
    raw: str
    kind: str
    resolved: str | None = None


@dataclass
class Analysis:
    md_root: str
    image_dirs: tuple[str, ...]
    layouts: list[str] = field(default_factory=list)
    md_count: int = 0
    total_images: int = 0
    referenced: int = 0
    unreferenced: list[ImageFile] = field(default_factory=list)
    broken: list[RefSite] = field(default_factory=list)
    external: list[RefSite] = field(default_factory=list)
    orphan_asset_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(image.size for image in self.unreferenced)


def _delete_roots(md_root: str, image_dirs: tuple[str, ...]) -> tuple[str, ...]:
    return (md_root,) + tuple(d for d in image_dirs if not is_within(d, md_root))


def analyze(
    md_root: str,
    image_dirs: tuple[str, ...] = (),
    paranoid: bool = False,
    extra_exts: frozenset[str] = frozenset(),
) -> Analysis:
    """Compare every image under the given roots against every reference.

    *image_dirs* may point outside *md_root* (Typora's global image folder), in
    which case those trees are scanned for pictures but not for notes.
    """
    md_root = os.path.abspath(md_root)
    image_dirs = tuple(os.path.abspath(d) for d in image_dirs)
    keyer = PathKeyer(md_root if os.path.isdir(md_root) else None)

    walks = [walk_tree(md_root, extra_exts)]
    for image_dir in image_dirs:
        if not is_within(image_dir, md_root):
            walks.append(walk_tree(image_dir, extra_exts, collect_markdown=False))
    walk = merge(walks)

    analysis = Analysis(md_root=md_root, image_dirs=image_dirs)
    analysis.errors.extend(walk.errors)
    analysis.md_count = len(walk.markdown)
    analysis.total_images = len(walk.images)
    analysis.layouts = detect_layouts(walk, image_dirs, md_root)

    on_disk = {keyer.key(image.path): image for image in walk.images}
    extra_bases = (md_root,) + image_dirs
    roots = _delete_roots(md_root, image_dirs)
    hit_keys: set[str] = set()

    for md_path in walk.markdown:
        text, error = read_text_best_effort(md_path)
        if error:
            analysis.errors.append(error)
        md_dir = os.path.dirname(md_path)
        for ref in extract_references(text, paranoid=paranoid):
            candidates: list[str] = []
            for raw in ref.raws:
                candidates.extend(resolve_reference(raw, md_dir, extra_bases))
            if not candidates:
                continue  # remote URL or data: -- nothing on this disk to keep
            matched = [c for c in candidates if keyer.key(c) in on_disk]
            if matched:
                hit_keys.update(keyer.key(c) for c in matched)
                continue
            existing = [c for c in candidates if os.path.exists(c)]
            if existing:
                # The file is real but lives outside the trees we scanned, so we
                # cannot reason about it -- surface it instead of ignoring it.
                if not any(is_within(existing[0], root) for root in roots):
                    analysis.external.append(_site(md_path, ref, existing[0]))
                continue
            analysis.broken.append(_site(md_path, ref, None))

    analysis.referenced = len(hit_keys)
    analysis.unreferenced = sorted(
        (image for key, image in on_disk.items() if key not in hit_keys),
        key=lambda image: (-image.size, image.path),
    )
    analysis.orphan_asset_dirs = _orphan_asset_dirs(walk, analysis.unreferenced, keyer)
    return analysis


def _site(md: str, ref: Reference, resolved: str | None) -> RefSite:
    return RefSite(md=md, line=ref.line, raw=ref.raw, kind=ref.kind, resolved=resolved)


def _orphan_asset_dirs(walk: Walk, unreferenced: list[ImageFile], keyer: PathKeyer) -> list[str]:
    """``foo.assets`` folders whose ``foo.md`` is gone and whose images are all dead.

    Both halves of that test matter.  A missing note alone is not enough: the
    same folder may still be linked from a different note, and every one of its
    pictures has to be unused before the folder itself counts as an orphan.
    """
    md_keys = {keyer.key(path) for path in walk.markdown}
    dead_keys = {keyer.key(image.path) for image in unreferenced}
    images_by_dir: dict[str, list[str]] = {}
    for image in walk.images:
        images_by_dir.setdefault(keyer.key(os.path.dirname(image.path)), []).append(image.path)

    orphans: list[str] = []
    for asset_dir in walk.asset_dirs:
        stem = os.path.basename(asset_dir)[: -len(".assets")]
        parent = os.path.dirname(asset_dir)
        if any(
            keyer.key(os.path.join(parent, stem + ext)) in md_keys
            for ext in (".md", ".markdown", ".mdown", ".mkd")
        ):
            continue
        contents = images_by_dir.get(keyer.key(asset_dir), [])
        if contents and all(keyer.key(path) in dead_keys for path in contents):
            orphans.append(asset_dir)
    return sorted(orphans)
