"""Command line interface: ``scan`` looks, ``clean`` moves, ``restore`` undoes."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .actions import UnsafePath, list_batches, move_to_trash, restore_batch, trash_root_for
from .compare import analyze
from .report import human_report, human_size, json_report


def _normalise_exts(values: list[str] | None) -> frozenset[str]:
    return frozenset("." + value.lower().lstrip(".") for value in (values or []))


def _add_scan_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("root", nargs="?", default=".", help="note folder to scan (default: current directory)")
    parser.add_argument(
        "--images", action="append", metavar="DIR", default=[],
        help="extra folder holding images, e.g. Typora's global image folder; repeatable",
    )
    parser.add_argument(
        "--paranoid", action="store_true",
        help="also treat any bare filename in the prose as a reference (keeps more, deletes less)",
    )
    parser.add_argument(
        "--ext", action="append", metavar=".EXT", default=[],
        help="additional image extension to consider; repeatable",
    )
    parser.add_argument("--limit", type=int, default=50, help="max rows per section, 0 for all (default: 50)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of a table")


def _run_analysis(args: argparse.Namespace):
    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        raise UnsafePath(f"not a directory: {root}")
    return analyze(
        root,
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
            sys.stdout.write(
                "\nNothing has been deleted. Review the list above, then run the same "
                "command with 'clean' to move these files to the trash.\n"
            )
    if args.fail_on_findings and analysis.unreferenced:
        return 2
    return 0


def _confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        sys.stderr.write("\naborted\n")
        return False


def cmd_clean(args: argparse.Namespace) -> int:
    analysis = _run_analysis(args)
    sys.stdout.write(human_report(analysis, limit=args.limit))
    if not analysis.unreferenced:
        return 0

    destination = "the system trash" if args.trash_system else trash_root_for(analysis.md_root)
    sys.stdout.write(
        f"\nAbout to move {len(analysis.unreferenced)} file(s) "
        f"({human_size(analysis.reclaimable_bytes)}) to {destination}.\n"
    )
    if not args.yes and not _confirm("Proceed? [y/N] "):
        sys.stdout.write("Nothing was moved.\n")
        return 1

    roots = (analysis.md_root,) + analysis.image_dirs
    batch = move_to_trash(
        [image.path for image in analysis.unreferenced],
        roots=roots,
        md_root=analysis.md_root,
        system_trash=args.trash_system,
        extra_exts=_normalise_exts(args.ext),
        prune_empty_dirs=not args.no_prune,
    )
    sys.stdout.write(f"Moved {len(batch.entries)} file(s), {human_size(batch.moved_bytes)}.\n")
    if batch.pruned_dirs:
        sys.stdout.write(f"Removed {len(batch.pruned_dirs)} empty folder(s).\n")
    if batch.failures:
        sys.stderr.write(f"{len(batch.failures)} file(s) could not be moved:\n")
        for failure in batch.failures:
            sys.stderr.write(f"  {failure}\n")
    if not args.trash_system:
        sys.stdout.write(
            f"Batch id {batch.batch_id}. Undo with:\n"
            f"  typora-pic-cleaner restore {analysis.md_root} --id {batch.batch_id}\n"
        )
    return 1 if batch.failures else 0


def cmd_restore(args: argparse.Namespace) -> int:
    root = os.path.abspath(args.root)
    if args.list:
        batches = list_batches(root)
        if not batches:
            sys.stdout.write(f"No clean-up history under {trash_root_for(root)}\n")
            return 0
        for batch in batches:
            entries = batch.get("entries", [])
            total = human_size(sum(entry.get("size", 0) for entry in entries))
            where = " (system trash)" if batch.get("system_trash") else ""
            sys.stdout.write(
                f"{batch.get('batch_id', '?')}  {batch.get('created', '?')}  "
                f"{len(entries)} file(s), {total}{where}\n"
            )
        return 0

    result = restore_batch(root, batch_id=args.id, dry_run=args.dry_run)
    verb = "Would restore" if args.dry_run else "Restored"
    sys.stdout.write(f"{verb} {len(result.restored)} file(s).\n")
    for path in result.skipped:
        sys.stdout.write(f"  skipped: {path}\n")
    for failure in result.failures:
        sys.stderr.write(f"  failed: {failure}\n")
    return 1 if result.failures else 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    return gui_main(initial_root=os.path.abspath(args.root) if args.root != "." else "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="typora-pic-cleaner",
        description="Find and remove images your Typora notes no longer reference.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    scan = subparsers.add_parser("scan", help="report unreferenced images without touching anything")
    _add_scan_args(scan)
    scan.add_argument("--fail-on-findings", action="store_true", help="exit 2 when unreferenced images exist")
    scan.set_defaults(func=cmd_scan)

    clean = subparsers.add_parser("clean", help="move unreferenced images to a recoverable trash")
    _add_scan_args(clean)
    clean.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")
    clean.add_argument(
        "--trash-system", action="store_true",
        help="use the OS trash instead of the in-vault trash (needs the send2trash package)",
    )
    clean.add_argument("--no-prune", action="store_true", help="keep folders that end up empty")
    clean.set_defaults(func=cmd_clean)

    restore = subparsers.add_parser("restore", help="undo a previous clean")
    restore.add_argument("root", nargs="?", default=".", help="note folder that was cleaned")
    restore.add_argument("--id", help="batch id to restore (default: the most recent)")
    restore.add_argument("--list", action="store_true", help="list recorded batches and exit")
    restore.add_argument("--dry-run", action="store_true", help="show what would be restored")
    restore.set_defaults(func=cmd_restore)

    gui = subparsers.add_parser("gui", help="open the graphical interface")
    gui.add_argument("root", nargs="?", default=".", help="folder to pre-fill")
    gui.set_defaults(func=cmd_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
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
        sys.stderr.write(f"error: {exc}\n")
        return 1
    except KeyboardInterrupt:
        sys.stderr.write("\naborted\n")
        return 130
