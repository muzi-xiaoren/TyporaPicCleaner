"""Command line interface: ``discover`` lists folders, ``scan`` looks,
``clean`` moves, ``restore`` undoes."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .actions import UnsafePath, list_batches, move_to_trash, restore_batch, trash_root_for
from .compare import analyze
from .discovery import DEFAULT_MAX_DEPTH, discover
from .i18n import SUPPORTED, set_language, t
from .report import human_report, human_size, json_report


def _normalise_exts(values: list[str] | None) -> frozenset[str]:
    return frozenset("." + value.lower().lstrip(".") for value in (values or []))


def _preselect_language(argv: list[str]) -> None:
    """Apply ``--lang`` before the parser is built.

    argparse bakes help strings in at construction time, so the language has to
    be settled first or ``--help`` would always come out in the detected one.
    """
    for index, token in enumerate(argv):
        if token == "--lang" and index + 1 < len(argv):
            set_language(argv[index + 1])
            return
        if token.startswith("--lang="):
            set_language(token.split("=", 1)[1])
            return
    set_language(None)


def _add_scan_args(parser: argparse.ArgumentParser) -> None:
    # Several folders at once, because Typora users rarely keep everything in
    # one tree -- and scanning them separately would call a picture used by
    # another folder's note unreferenced.
    parser.add_argument("root", nargs="*", default=["."], help=t("cli.help.root"))
    parser.add_argument("--images", action="append", metavar="DIR", default=[], help=t("cli.help.images"))
    parser.add_argument("--paranoid", action="store_true", help=t("cli.help.paranoid"))
    parser.add_argument("--ext", action="append", metavar=".EXT", default=[], help=t("cli.help.ext"))
    parser.add_argument("--limit", type=int, default=50, help=t("cli.help.limit"))
    parser.add_argument("--json", action="store_true", help=t("cli.help.json"))


def _run_analysis(args: argparse.Namespace):
    roots = [os.path.abspath(root) for root in (args.root or ["."])]
    for root in roots:
        if not os.path.isdir(root):
            raise UnsafePath(t("cli.error.not_a_directory", path=root))
    return analyze(
        roots,
        image_dirs=tuple(args.images),
        paranoid=args.paranoid,
        extra_exts=_normalise_exts(args.ext),
    )


def cmd_scan(args: argparse.Namespace) -> int:
    analysis = _run_analysis(args)
    if args.json:
        json.dump(json_report(analysis), sys.stdout, ensure_ascii=False, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        sys.stdout.write(human_report(analysis, limit=args.limit))
        if analysis.unreferenced:
            sys.stdout.write("\n" + t("cli.scan.footer") + "\n")
    if args.fail_on_findings and analysis.unreferenced:
        return 2
    return 0


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\n" + t("cli.aborted") + "\n")
        return False


def cmd_clean(args: argparse.Namespace) -> int:
    analysis = _run_analysis(args)
    sys.stdout.write(human_report(analysis, limit=args.limit))
    if not analysis.unreferenced:
        return 0

    destination = t("cli.clean.system_trash") if args.trash_system else trash_root_for(analysis.md_root)
    sys.stdout.write(
        "\n"
        + t(
            "cli.clean.about_to",
            count=len(analysis.unreferenced),
            size=human_size(analysis.reclaimable_bytes),
            destination=destination,
        )
        + "\n"
    )
    if not args.yes and not _confirm(t("cli.clean.prompt")):
        sys.stdout.write(t("cli.clean.declined") + "\n")
        return 1

    batch = move_to_trash(
        [image.path for image in analysis.unreferenced],
        roots=analysis.roots,
        md_root=analysis.md_root,
        system_trash=args.trash_system,
        extra_exts=_normalise_exts(args.ext),
        prune_empty_dirs=not args.no_prune,
    )
    sys.stdout.write(
        t("cli.clean.moved", count=len(batch.entries), size=human_size(batch.moved_bytes)) + "\n"
    )
    if batch.pruned_dirs:
        sys.stdout.write(t("cli.clean.pruned", count=len(batch.pruned_dirs)) + "\n")
    if batch.failures:
        sys.stderr.write(t("cli.clean.failures", count=len(batch.failures)) + "\n")
        for failure in batch.failures:
            sys.stderr.write(f"  {failure}\n")
    if not args.trash_system:
        sys.stdout.write(
            t("cli.clean.undo_hint", batch=batch.batch_id) + "\n"
            f"  typora-pic-cleaner restore {analysis.md_root} --id {batch.batch_id}\n"
        )
    return 1 if batch.failures else 0


def cmd_restore(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.root)
    if args.list:
        batches = list_batches(root)
        if not batches:
            sys.stdout.write(t("cli.restore.none", path=trash_root_for(root)) + "\n")
            return 0
        for batch in batches:
            entries = batch.get("entries", [])
            summary = t(
                "cli.restore.batch_line",
                count=len(entries),
                size=human_size(sum(entry.get("size", 0) for entry in entries)),
            )
            where = t("cli.restore.system_trash_tag") if batch.get("system_trash") else ""
            sys.stdout.write(
                f"{batch.get('batch_id', '?')}  {batch.get('created', '?')}  {summary}{where}\n"
            )
        return 0

    result = restore_batch(root, batch_id=args.id, dry_run=args.dry_run)
    key = "cli.restore.would" if args.dry_run else "cli.restore.done"
    sys.stdout.write(t(key, count=len(result.restored)) + "\n")
    for path in result.skipped:
        sys.stdout.write("  " + t("cli.restore.skipped", detail=path) + "\n")
    for failure in result.failures:
        sys.stderr.write("  " + t("cli.restore.failed", detail=failure) + "\n")
    return 1 if result.failures else 0


def cmd_discover(args: argparse.Namespace) -> int:
    parent = os.path.abspath(args.parent)
    if not os.path.isdir(parent):
        raise UnsafePath(t("cli.error.not_a_directory", path=parent))
    found = discover(parent, max_depth=args.depth)
    if args.json:
        json.dump(
            [
                {
                    "path": c.path, "depth": c.depth, "notes": c.notes,
                    "images": c.images, "own_notes": c.own_notes,
                    "skipped_notes": c.skipped_notes,
                }
                for c in found
            ],
            sys.stdout, ensure_ascii=False, indent=2,
        )
        sys.stdout.write("\n")
        return 0
    if not found:
        sys.stdout.write(t("cli.discover.none", path=parent) + "\n")
        return 0
    for candidate in found:
        label = candidate.path if candidate.depth == 0 else candidate.name
        sys.stdout.write(
            "  " * candidate.depth
            + label
            + "  "
            + t("cli.discover.counts", notes=candidate.notes, images=candidate.images)
            + "\n"
        )
    hidden = max((c.skipped_notes for c in found), default=0)
    if hidden:
        sys.stdout.write("\n" + t("cli.discover.skipped", count=hidden) + "\n")
    sys.stdout.write("\n" + t("cli.discover.footer") + "\n")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    roots = [os.path.abspath(root) for root in args.root if root != "."]
    return gui_main(initial_roots=roots)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typora-pic-cleaner",
        description=t("cli.description"),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--lang", choices=("auto",) + SUPPORTED, help=t("cli.help.lang"))
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help=t("cli.help.scan"))
    _add_scan_args(scan)
    scan.add_argument("--fail-on-findings", action="store_true", help=t("cli.help.fail_on_findings"))
    scan.set_defaults(func=cmd_scan)

    clean = subparsers.add_parser("clean", help=t("cli.help.clean"))
    _add_scan_args(clean)
    clean.add_argument("-y", "--yes", action="store_true", help=t("cli.help.yes"))
    clean.add_argument("--trash-system", action="store_true", help=t("cli.help.trash_system"))
    clean.add_argument("--no-prune", action="store_true", help=t("cli.help.no_prune"))
    clean.set_defaults(func=cmd_clean)

    restore = subparsers.add_parser("restore", help=t("cli.help.restore"))
    restore.add_argument("root", nargs="?", default=".", help=t("cli.help.restore_root"))
    restore.add_argument("--id", help=t("cli.help.id"))
    restore.add_argument("--list", action="store_true", help=t("cli.help.list"))
    restore.add_argument("--dry-run", action="store_true", help=t("cli.help.dry_run"))
    restore.set_defaults(func=cmd_restore)

    found = subparsers.add_parser("discover", help=t("cli.help.discover"))
    found.add_argument("parent", nargs="?", default=".", help=t("cli.help.discover_parent"))
    found.add_argument("--depth", type=int, default=DEFAULT_MAX_DEPTH, help=t("cli.help.depth"))
    found.add_argument("--json", action="store_true", help=t("cli.help.json"))
    found.set_defaults(func=cmd_discover)

    gui = subparsers.add_parser("gui", help=t("cli.help.gui"))
    gui.add_argument("root", nargs="*", default=[], help=t("cli.help.gui_root"))
    gui.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    _preselect_language(list(argv) if argv is not None else sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Packaged builds handle the no-argument case in run_gui.py by opening
        # the GUI; from a shell, help is the more useful answer.
        parser.print_help()
        return 1
    try:
        return args.func(args)
    except UnsafePath as exc:
        sys.stderr.write(t("cli.error.prefix", message=str(exc)) + "\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\n" + t("cli.aborted") + "\n")
        return 130
