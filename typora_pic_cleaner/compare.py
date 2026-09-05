"""Decide which images on disk no note points at any more."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence, Union

from .paths import PathKeyer, is_within, resolve_reference
from .refs import Reference, extract_references, front_matter_root_url
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
    #: Every notes folder that was scanned.  More than one is the normal case:
    #: people keep several unrelated Typora folders, and comparing them in a
    #: single pass is what stops a picture shared between two of them from
    #: looking unreferenced in each.
    md_roots: tuple[str, ...]
    image_dirs: tuple[str, ...]
    layouts: list[tuple[str, dict]] = field(default_factory=list)
    md_count: int = 0
    total_images: int = 0
    referenced: int = 0
    unreferenced: list[ImageFile] = field(default_factory=list)
    broken: list[RefSite] = field(default_factory=list)
    external: list[RefSite] = field(default_factory=list)
    orphan_asset_dirs: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def md_root(self) -> str:
        """The folder that anchors the undo history and relative display paths."""
        return self.md_roots[0]

    @property
    def roots(self) -> tuple[str, ...]:
        """Every tree files may be moved out of, for the deletion guard rails."""
        return self.md_roots + self.image_dirs

    @property
    def reclaimable_bytes(self) -> int:
        return sum(image.size for image in self.unreferenced)


def _delete_roots(md_roots: tuple[str, ...], image_dirs: tuple[str, ...]) -> tuple[str, ...]:
    return md_roots + tuple(
        d for d in image_dirs if not any(is_within(d, root) for root in md_roots)
    )


def _normalise_roots(md_roots: "Union[str, Sequence[str]]") -> tuple[str, ...]:
    """Accept one folder or many, and drop duplicates while keeping the order.

    The first survivor stays first on purpose: it is where the trash folder and
    the undo history go, so it must not drift between runs.
    """
    if isinstance(md_roots, str):
        md_roots = [md_roots]
    seen: dict[str, None] = {}
    for root in md_roots:
        seen.setdefault(os.path.abspath(root), None)
    if not seen:
        raise ValueError("at least one notes folder is required")
    return tuple(seen)


def analyze(
    md_roots: "Union[str, Sequence[str]]",
    image_dirs: tuple[str, ...] = (),
    paranoid: bool = False,
    extra_exts: frozenset[str] = frozenset(),
) -> Analysis:
    """Compare every image under the given roots against every reference.

    *md_roots* is one notes folder or several; they are scanned as a single
    corpus, so a picture in one folder that a note in another links to counts
    as referenced.  *image_dirs* may point outside all of them (Typora's global
    image folder), in which case those trees are scanned for pictures but not
    for notes.
    """
    roots = _normalise_roots(md_roots)
    image_dirs = tuple(os.path.abspath(d) for d in image_dirs)
    existing = [root for root in roots if os.path.isdir(root)]
    keyer = PathKeyer(existing[0] if existing else None)

    walks = [walk_tree(root, extra_exts) for root in roots]
    for image_dir in image_dirs:
        if not any(is_within(image_dir, root) for root in roots):
            walks.append(walk_tree(image_dir, extra_exts, collect_markdown=False))
    walk = merge(walks)

    analysis = Analysis(md_roots=roots, image_dirs=image_dirs)
    analysis.errors.extend(walk.errors)
    analysis.md_count = len(walk.markdown)
    analysis.total_images = len(walk.images)
    analysis.layouts = detect_layouts(walk, image_dirs, roots)

    on_disk = {keyer.key(image.path): image for image in walk.images}
    extra_bases = roots + image_dirs
    delete_roots = _delete_roots(roots, image_dirs)
    hit_keys: set[str] = set()

    for md_path in walk.markdown:
        text, error = read_text_best_effort(md_path)
        if error:
            analysis.errors.append(error)
        md_dir = os.path.dirname(md_path)
        bases = _bases_for(md_dir, extra_bases, front_matter_root_url(text))
        for ref in extract_references(text, paranoid=paranoid):
            candidates: list[str] = []
            for raw in ref.raws:
                candidates.extend(resolve_reference(raw, md_dir, bases))
            if not candidates:
                continue  # remote URL or data: -- nothing on this disk to keep
            matched = [c for c in candidates if keyer.key(c) in on_disk]
            if matched:
                hit_keys.update(keyer.key(c) for c in matched)
                continue
            found = [c for c in candidates if os.path.exists(c)]
            if found:
                # The file is real but lives outside the trees we scanned, so we
                # cannot reason about it -- surface it instead of ignoring it.
                if not any(is_within(found[0], root) for root in delete_roots):
                    analysis.external.append(_site(md_path, ref, found[0]))
                continue
            analysis.broken.append(_site(md_path, ref, None))

    analysis.referenced = len(hit_keys)
    analysis.unreferenced = sorted(
        (image for key, image in on_disk.items() if key not in hit_keys),
        key=lambda image: (-image.size, image.path),
    )
    analysis.orphan_asset_dirs = _orphan_asset_dirs(walk, analysis.unreferenced, keyer)
    return analysis


def _bases_for(
    md_dir: str, extra_bases: tuple[str, ...], root_url: str | None
) -> tuple[str, ...]:
    """Resolution bases for one note, honouring its own ``typora-root-url``.

    Put first so it wins for the ``/pics/a.png`` form it exists to serve.  It is
    used for matching only and never widens what may be deleted: a root outside
    the scanned tree still has none of its files inventoried.
    """
    if not root_url:
        return extra_bases
    base = root_url if os.path.isabs(root_url) or root_url[1:2] == ":" else os.path.join(md_dir, root_url)
    return (os.path.abspath(base),) + extra_bases


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
