"""Turn an :class:`~typora_pic_cleaner.compare.Analysis` into something readable."""

from __future__ import annotations

import os
from dataclasses import asdict

from .compare import Analysis

_UNITS = ("B", "KB", "MB", "GB", "TB")


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _rel(path: str, root: str) -> str:
    try:
        relative = os.path.relpath(path, root)
    except ValueError:
        return path
    return path if relative.startswith(os.pardir) else relative


def human_report(
    analysis: Analysis,
    limit: int = 50,
    show_broken: bool = True,
    show_external: bool = True,
) -> str:
    root = analysis.md_root
    lines: list[str] = []
    lines.append(f"Notes root : {root}")
    for image_dir in analysis.image_dirs:
        lines.append(f"Image dir  : {image_dir}")
    lines.append("Layout     : " + "; ".join(analysis.layouts))
    lines.append(
        f"Scanned    : {analysis.md_count} note(s), {analysis.total_images} image(s); "
        f"{analysis.referenced} referenced, {len(analysis.unreferenced)} unreferenced"
    )
    lines.append("")

    if analysis.unreferenced:
        shown = analysis.unreferenced[:limit] if limit else analysis.unreferenced
        lines.append(
            f"Unreferenced images ({len(analysis.unreferenced)}, "
            f"{human_size(analysis.reclaimable_bytes)} reclaimable):"
        )
        width = max(len(human_size(image.size)) for image in shown)
        for image in shown:
            lines.append(f"  {human_size(image.size):>{width}}  {_rel(image.path, root)}")
        if limit and len(analysis.unreferenced) > limit:
            lines.append(f"  ... and {len(analysis.unreferenced) - limit} more (use --limit 0 to list all)")
    else:
        lines.append("Unreferenced images: none -- nothing to clean.")
    lines.append("")

    if analysis.orphan_asset_dirs:
        lines.append(f"Orphaned .assets folders ({len(analysis.orphan_asset_dirs)}, note file is gone):")
        for path in analysis.orphan_asset_dirs:
            lines.append(f"  {_rel(path, root)}")
        lines.append("")

    if show_broken and analysis.broken:
        lines.append(f"Broken references ({len(analysis.broken)}, the note points at a missing file):")
        for site in analysis.broken[:limit] if limit else analysis.broken:
            lines.append(f"  {_rel(site.md, root)}:{site.line}  [{site.kind}]  {site.raw}")
        if limit and len(analysis.broken) > limit:
            lines.append(f"  ... and {len(analysis.broken) - limit} more")
        lines.append("")

    if show_external and analysis.external:
        lines.append(
            f"References outside the scanned tree ({len(analysis.external)}): "
            "these files exist but were not checked, so nothing about them is safe to delete."
        )
        for site in analysis.external[:limit] if limit else analysis.external:
            lines.append(f"  {_rel(site.md, root)}:{site.line}  ->  {site.resolved}")
        lines.append("")

    if analysis.errors:
        lines.append(f"Warnings ({len(analysis.errors)}):")
        for error in analysis.errors[:limit] if limit else analysis.errors:
            lines.append(f"  {error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def json_report(analysis: Analysis) -> dict:
    payload = asdict(analysis)
    payload["reclaimable_bytes"] = analysis.reclaimable_bytes
    payload["unreferenced_count"] = len(analysis.unreferenced)
    return payload
