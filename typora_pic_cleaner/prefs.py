"""A tiny settings file, currently holding only the interface language.

Worth persisting because the common case is a user whose system is set to one
language but who wants the tool in another: without this, every launch would
undo their choice.
"""

from __future__ import annotations

import json
import os
import sys

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
