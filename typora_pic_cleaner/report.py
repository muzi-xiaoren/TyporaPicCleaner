"""Turn an :class:`~typora_pic_cleaner.compare.Analysis` into something readable."""

from __future__ import annotations

import os
from dataclasses import asdict

from .compare import Analysis
from .i18n import t

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
    # The label column is padded to the widest translated label so the values
    # still line up in Chinese, where labels are shorter but wider on screen.
    labels = [t("report.notes_root"), t("report.image_dir"), t("report.layout"), t("report.scanned")]
    width = max(len(label) for label in labels)
    lines.append(f"{t('report.notes_root'):<{width}} : {root}")
    for image_dir in analysis.image_dirs:
        lines.append(f"{t('report.image_dir'):<{width}} : {image_dir}")
    lines.append(
        f"{t('report.layout'):<{width}} : "
        + "; ".join(t(key, **params) for key, params in analysis.layouts)
    )
    lines.append(
        f"{t('report.scanned'):<{width}} : "
        + t(
            "report.scanned.value",
            notes=analysis.md_count,
            images=analysis.total_images,
            referenced=analysis.referenced,
            unreferenced=len(analysis.unreferenced),
        )
    )
    lines.append("")

    if analysis.unreferenced:
        shown = analysis.unreferenced[:limit] if limit else analysis.unreferenced
        lines.append(
            t(
                "report.unreferenced.header",
                count=len(analysis.unreferenced),
                size=human_size(analysis.reclaimable_bytes),
            )
        )
        size_width = max(len(human_size(image.size)) for image in shown)
        for image in shown:
            lines.append(f"  {human_size(image.size):>{size_width}}  {_rel(image.path, root)}")
        if limit and len(analysis.unreferenced) > limit:
            lines.append("  " + t("report.more_with_hint", count=len(analysis.unreferenced) - limit))
    else:
        lines.append(t("report.unreferenced.none"))
    lines.append("")

    if analysis.orphan_asset_dirs:
        lines.append(t("report.orphans.header", count=len(analysis.orphan_asset_dirs)))
        for path in analysis.orphan_asset_dirs:
            lines.append(f"  {_rel(path, root)}")
        lines.append("")

    if show_broken and analysis.broken:
        lines.append(t("report.broken.header", count=len(analysis.broken)))
        for site in analysis.broken[:limit] if limit else analysis.broken:
            lines.append(f"  {_rel(site.md, root)}:{site.line}  [{site.kind}]  {site.raw}")
        if limit and len(analysis.broken) > limit:
            lines.append("  " + t("report.more", count=len(analysis.broken) - limit))
        lines.append("")

    if show_external and analysis.external:
        lines.append(t("report.external.header", count=len(analysis.external)))
        for site in analysis.external[:limit] if limit else analysis.external:
            lines.append(f"  {_rel(site.md, root)}:{site.line}  ->  {site.resolved}")
        lines.append("")

    if analysis.errors:
        lines.append(t("report.warnings.header", count=len(analysis.errors)))
        for error in analysis.errors[:limit] if limit else analysis.errors:
            lines.append(f"  {error}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def json_report(analysis: Analysis) -> dict:
    payload = asdict(analysis)
    payload["reclaimable_bytes"] = analysis.reclaimable_bytes
    payload["unreferenced_count"] = len(analysis.unreferenced)
    # Keys stay in the payload for scripts; the rendered sentences are for
    # humans and would otherwise change with the interface language.
    payload["layouts"] = [{"key": key, "params": params} for key, params in analysis.layouts]
    payload["layouts_text"] = [t(key, **params) for key, params in analysis.layouts]
    return payload
