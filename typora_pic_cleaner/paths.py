"""Path normalisation helpers shared by the scanner and the comparator.

Everything in here exists to answer one question correctly on both macOS and
Windows: *are these two path strings the same file?*  Getting that wrong in
either direction is expensive -- a false "different" deletes a picture that is
still in use.
"""

from __future__ import annotations

import os
import sys
import tempfile
from urllib.parse import unquote

#: Extensions we are willing to consider "an image" -- and therefore willing to
#: delete.  Anything outside this set is never touched, no matter what.
IMAGE_EXTS: frozenset[str] = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".jpe", ".gif", ".webp", ".bmp", ".svg",
        ".avif", ".heic", ".heif", ".tif", ".tiff", ".ico", ".jfif", ".apng",
    }
)

#: Schemes whose targets do not live on this disk, so there is nothing to clean.
_REMOTE_SCHEME_PREFIXES = ("http:", "https:", "ftp:", "ftps:", "data:", "mailto:")


def is_case_insensitive_fs(probe_dir: str | None = None) -> bool:
    """Return True when *probe_dir*'s filesystem ignores case in filenames.

    Probed empirically rather than guessed from the platform, because a
    case-sensitive volume on macOS and a case-insensitive share on Linux both
    happen in the wild.  Falls back to the platform default if probing fails.
    """
    try:
        with tempfile.NamedTemporaryFile(prefix="tpcCASE", dir=probe_dir) as handle:
            return os.path.exists(handle.name.upper()) or os.path.exists(
                handle.name.lower()
            )
    except OSError:
        return sys.platform in ("darwin", "win32")


class PathKeyer:
    """Turns paths into comparable keys for one particular filesystem."""

    def __init__(self, probe_dir: str | None = None) -> None:
        self.fold_case = is_case_insensitive_fs(probe_dir)

    def key(self, path: str) -> str:
        """Normalise *path* into a value that compares equal for equal files."""
        # realpath also normalises "." / ".." and collapses separators, and it
        # keeps working on paths that do not exist.
        normalised = os.path.normcase(os.path.realpath(os.path.abspath(path)))
        return normalised.lower() if self.fold_case else normalised


def has_image_ext(path: str, extra_exts: frozenset[str] = frozenset()) -> bool:
    return os.path.splitext(path)[1].lower() in (IMAGE_EXTS | extra_exts)


def is_within(path: str, root: str) -> bool:
    """True when *path* is *root* itself or lives underneath it.

    The deletion guard rail: a reference like ``../../../etc/x.png`` must never
    let us move a file that sits outside the tree the user pointed us at.
    """
    root_real = os.path.realpath(os.path.abspath(root))
    path_real = os.path.realpath(os.path.abspath(path))
    try:
        return not os.path.relpath(path_real, root_real).startswith(os.pardir)
    except ValueError:
        # Different drives on Windows -- definitively outside.
        return False


def _strip_angle_brackets(raw: str) -> str:
    if len(raw) >= 2 and raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1]
    return raw


def _from_file_url(raw: str) -> str:
    rest = raw[len("file://"):]
    # file:///C:/pics/a.png -> C:/pics/a.png ; file:///home/x -> /home/x
    if len(rest) >= 3 and rest[0] == "/" and rest[2] == ":":
        return rest[1:]
    return rest


def _looks_remote(raw: str) -> bool:
    lowered = raw.lower()
    return any(lowered.startswith(prefix) for prefix in _REMOTE_SCHEME_PREFIXES)


def _has_foreign_scheme(raw: str) -> bool:
    """True for ``scheme:`` prefixes that are not a Windows drive letter.

    A scheme needs two or more characters per RFC 3986, which is exactly what
    lets us tell ``typora://`` apart from ``C:\\pics``.
    """
    head = raw.split(":", 1)[0]
    if len(head) < 2 or ":" not in raw:
        return False
    return head[0].isalpha() and all(ch.isalnum() or ch in "+-." for ch in head)


def reference_variants(raw: str) -> list[str]:
    """Expand one written-down link into every path string it might mean.

    Typora, hand-editing and copy-paste between platforms produce the same
    picture spelled several ways: percent-encoded, backslash-separated, with a
    trailing ``#anchor``.  We deliberately return *all* plausible readings and
    later treat the image as referenced if any of them matches, because an
    extra match only ever preserves a file.
    """
    raw = _strip_angle_brackets(raw.strip())
    if not raw or _looks_remote(raw):
        return []
    if raw.lower().startswith("file://"):
        raw = _from_file_url(raw)
    elif _has_foreign_scheme(raw):
        return []

    seeds = {raw}
    decoded = unquote(raw)
    if decoded != raw:
        seeds.add(decoded)

    variants: set[str] = set()
    for seed in seeds:
        variants.add(seed)
        if "\\" in seed:
            variants.add(seed.replace("\\", "/"))
        # Drop ?query / #fragment, but only as an *extra* candidate: both
        # characters are legal in filenames and Typora does emit them.
        for sep in ("#", "?"):
            head = seed.split(sep, 1)[0]
            if head and head != seed:
                variants.add(head)
                if "\\" in head:
                    variants.add(head.replace("\\", "/"))
    return [v for v in variants if v.strip() not in ("", ".", "..")]


def resolve_reference(raw: str, base_dir: str, extra_bases: tuple[str, ...] = ()) -> list[str]:
    """Absolute paths a reference could point at, from *base_dir* outward.

    Relative links resolve against the Markdown file's own directory (what
    Typora does).  *extra_bases* -- typically the vault root and the configured
    global image folder -- are tried too, so a root-relative link written
    without a leading slash still counts as a reference.
    """
    out: list[str] = []
    seen: set[str] = set()
    for variant in reference_variants(raw):
        has_drive = len(variant) >= 2 and variant[1] == ":"
        if has_drive:
            candidates = [variant]
        elif variant.startswith(("/", "\\")):
            # A leading slash is ambiguous: it may be a real absolute path, or
            # Typora writing a path relative to the configured image root.  Try
            # it literally first, then against each base.
            stripped = variant.lstrip("/\\")
            candidates = [variant]
            candidates += [os.path.join(base, stripped) for base in (base_dir,) + extra_bases]
        else:
            candidates = [os.path.join(base_dir, variant)]
            candidates += [os.path.join(base, variant) for base in extra_bases]
        for candidate in candidates:
            absolute = os.path.abspath(candidate)
            if absolute not in seen:
                seen.add(absolute)
                out.append(absolute)
    return out
