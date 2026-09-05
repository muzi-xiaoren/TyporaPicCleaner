"""A tiny settings file: the interface language and the chosen folders.

Worth persisting because both are answers the user should only have to give
once.  The language matters most to someone whose system is set to one language
but who wants the tool in another; the folder list matters because working out
which of a dozen directories hold notes -- and which of those you deliberately
excluded -- is the tedious part of every run.
"""

from __future__ import annotations

import json
import os
import sys
from typing import List, Tuple

APP_DIRNAME = "typora-pic-cleaner"
CONFIG_NAME = "config.json"


def config_dir() -> str:
    """Where settings live, following each platform's convention.

    ``TPC_CONFIG`` overrides it, which is also how the tests keep their hands
    off the real user's file.
    """
    override = os.environ.get("TPC_CONFIG")
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "TyporaPicCleaner")
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_DIRNAME)


def config_path() -> str:
    return os.path.join(config_dir(), CONFIG_NAME)


def load() -> dict:
    """Read the settings, treating any problem as "no settings yet".

    A corrupt or unreadable file must never stop the tool from starting.
    """
    try:
        with open(config_path(), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save(**values: object) -> bool:
    """Merge *values* into the settings file; returns whether it was written."""
    data = load()
    data.update(values)
    try:
        os.makedirs(config_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except OSError:
        # Read-only home, sandboxing, a full disk: losing a preference is not
        # worth interrupting the user over.
        return False


def load_language() -> str | None:
    language = load().get("language")
    return language if isinstance(language, str) and language else None


def save_language(language: str) -> bool:
    return save(language=language)


def load_note_folders() -> List[Tuple[str, bool]]:
    """The remembered notes folders as ``(path, selected)``, in the saved order.

    Order is preserved because the first folder anchors the undo history; a
    reshuffle between runs would scatter it across several trash folders.
    """
    out: List[Tuple[str, bool]] = []
    seen = set()
    for entry in load().get("note_folders") or []:
        if isinstance(entry, str):
            path, selected = entry, True
        elif isinstance(entry, dict) and isinstance(entry.get("path"), str):
            path, selected = entry["path"], bool(entry.get("selected", True))
        else:
            continue
        key = os.path.normcase(path)
        if path and key not in seen:
            seen.add(key)
            out.append((path, selected))
    return out


def save_note_folders(folders: List[Tuple[str, bool]]) -> bool:
    return save(
        note_folders=[{"path": path, "selected": bool(selected)} for path, selected in folders]
    )


def _load_paths(key: str) -> List[str]:
    values = load().get(key) or []
    out: List[str] = []
    seen = set()
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        folded = os.path.normcase(value)
        if folded not in seen:
            seen.add(folded)
            out.append(value)
    return out


def load_image_folders() -> List[str]:
    return _load_paths("image_folders")


def save_image_folders(folders: List[str]) -> bool:
    return save(image_folders=list(folders))


def load_scan_parents() -> List[str]:
    """Folders the user has pointed the finder at before, most recent first."""
    return _load_paths("scan_parents")


def save_scan_parents(parents: List[str]) -> bool:
    return save(scan_parents=list(parents)[:8])
