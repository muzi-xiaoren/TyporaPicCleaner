"""Pull every image reference out of a Markdown document.

Typora accepts far more ways of pointing at a picture than the Markdown spec
suggests, and this module has to know all of them.  A reference we fail to
recognise becomes an image we happily delete while a note still shows it, so
the bias throughout is towards over-collecting.

Where a construct is genuinely ambiguous -- ``![](a.png "cap")`` could be a
file called ``a.png`` or one called ``a.png "cap"`` -- we keep both readings on
a single :class:`Reference`.  Grouping them means an image matching *either*
reading counts as used, while the "broken reference" report still fires only
once for the site as a whole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .paths import IMAGE_EXTS, has_image_ext


@dataclass(frozen=True)
class Reference:
    """One link site, with every plausible reading of what it points at."""

    raws: tuple[str, ...]
    line: int
    kind: str  # markdown | reference-def | html | css | front-matter | bare

    @property
    def raw(self) -> str:
        """The most likely reading, for display."""
        return self.raws[0]


def _blank(text: str, start: int, end: int) -> str:
    """Overwrite ``text[start:end]`` with spaces, keeping newlines.

    Masking rather than deleting means every later regex match still reports
    the original line number.
    """
    chunk = "".join("\n" if ch == "\n" else " " for ch in text[start:end])
    return text[:start] + chunk + text[end:]


_FENCE_RE = re.compile(r"^([ \t]{0,3})(`{3,}|~{3,})(.*)$")


def mask_code(text: str) -> str:
    """Blank out fenced blocks and inline code spans.

    A path inside a fenced block is documentation, not a live reference; if we
    counted it, a note explaining Markdown syntax would pin an unused file
    forever.  Fences use a line state machine (nesting rules make a single
    regex unreliable) and inline spans use backtick-run matching.
    """
    offset = 0
    open_fence: str | None = None
    spans: list[tuple[int, int]] = []
    for line in text.split("\n"):
        line_end = offset + len(line)
        match = _FENCE_RE.match(line)
        if open_fence is None:
            if match:
                open_fence = match.group(2)[0] * 3
                spans.append((offset, line_end))
        else:
            spans.append((offset, line_end))
            # A closing fence uses the same character and carries no info string.
            if match and match.group(2)[0] * 3 == open_fence and not match.group(3).strip():
                open_fence = None
        offset = line_end + 1

    for start, end in spans:
        text = _blank(text, start, end)
    for match in re.finditer(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", text, re.S):
        text = _blank(text, match.start(), match.end())
    return text


def split_front_matter(text: str) -> tuple[str, str]:
    """Return ``(front_matter, body)``; front matter is empty when absent."""
    match = re.match(r"^(?:﻿)?-{3,}[ \t]*\r?\n(.*?)(?:\r?\n)-{3,}[ \t]*(?:\r?\n|$)", text, re.S)
    if not match:
        return "", text
    return match.group(1), _blank(text, 0, match.end())


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


# Inline links and images: ![alt](path "title") and [text](path).  The target
# group tolerates one level of nested parentheses so "img (1).png" survives.
_INLINE_RE = re.compile(r"!?\[(?:[^\[\]]|\[[^\[\]]*\])*\]\(([^()]*(?:\([^()]*\)[^()]*)*)\)", re.S)
_TITLE_RE = re.compile(r"""\s+(?:"[^"]*"|'[^']*'|\([^()]*\))\s*$""")
_REF_DEF_RE = re.compile(r"""^[ \t]{0,3}\[([^\]]+)\]:[ \t]*(<[^>]*>|\S+)""", re.M)
_HTML_TAG_RE = re.compile(r"<[a-zA-Z][^>]*>", re.S)
_HTML_ATTR_RE = re.compile(
    r"""\b(src|href|poster|data-src|data-original|data-original-src|content|xlink:href)"""
    r"""\s*=\s*("[^"]*"|'[^']*'|[^\s"'>]+)""",
    re.I | re.S,
)
_SRCSET_RE = re.compile(r"""\bsrcset\s*=\s*("[^"]*"|'[^']*')""", re.I | re.S)
_CSS_URL_RE = re.compile(r"""url\(\s*("[^"]*"|'[^']*'|[^)\s]*)\s*\)""", re.I)
_QUOTED_RE = re.compile(r""""([^"\n]*)"|'([^'\n]*)'""")

_IMG_EXT_ALT = "|".join(sorted(ext.lstrip(".") for ext in IMAGE_EXTS))
# A filename-shaped token ending in an image extension.  Spaces and quotes stay
# out of the class on purpose: allowing them lets the match run backwards into
# the surrounding prose and swallow the real filename.  ``:`` in the lookbehind
# stops "https://host/a.png" from yielding a bogus "//host/a.png".
_BARE_PATH_RE = re.compile(
    r"(?<![\w/\\.\-:])((?:[A-Za-z]:)?[\w./\\~%+\-]*\.(?:" + _IMG_EXT_ALT + r"))(?![\w])",
    re.I,
)


def _unquote_attr(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _readings_of_target(target: str) -> tuple[str, ...]:
    """Every way an inline-link target could be read as a path.

    Angle-bracketed targets are unambiguous.  Otherwise we return the
    title-stripped path first (the likely intent) and the untouched string as a
    fallback, since an unquoted path containing spaces is legal in Typora.
    """
    target = target.strip()
    if not target:
        return ()
    if target.startswith("<"):
        end = target.find(">")
        if end != -1:
            return (target[1:end],)
    stripped = _TITLE_RE.sub("", target).strip()
    if not stripped:
        return (target,)
    return (stripped,) if stripped == target else (stripped, target)


def extract_references(text: str, paranoid: bool = False) -> list[Reference]:
    """Every image reference site in *text*, in no particular order.

    With *paranoid* set, any bare token ending in an image extension anywhere in
    the prose also counts.  That keeps files a note merely names, at the cost of
    retaining some genuinely dead ones.
    """
    found: list[Reference] = []

    def add(raws: tuple[str, ...] | str, index: int, kind: str, source: str) -> None:
        if isinstance(raws, str):
            raws = (raws,)
        cleaned = tuple(dict.fromkeys(raw.strip() for raw in raws if raw.strip()))
        if cleaned:
            found.append(Reference(raws=cleaned, line=_line_of(source, index), kind=kind))

    front_matter, rest = split_front_matter(text)
    body = mask_code(rest)

    # Front matter is structured data, so a bare filename in there is always a
    # real reference (cover:, banner:, thumbnails: [...]).  Quoted values are
    # taken whole and then masked, so the bare scan cannot re-match their
    # fragments and invent a second, broken reference.
    for match in _QUOTED_RE.finditer(front_matter):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if value and has_image_ext(value.split("#")[0].split("?")[0]):
            add(value, match.start(), "front-matter", front_matter)
            front_matter = _blank(front_matter, match.start(), match.end())
    for match in _CSS_URL_RE.finditer(front_matter):
        add(_unquote_attr(match.group(1)), match.start(1), "front-matter", front_matter)
    for match in _BARE_PATH_RE.finditer(front_matter):
        add(match.group(1), match.start(1), "front-matter", front_matter)

    for match in _INLINE_RE.finditer(body):
        add(_readings_of_target(match.group(1)), match.start(1), "markdown", body)

    for match in _REF_DEF_RE.finditer(body):
        add(match.group(2), match.start(2), "reference-def", body)

    for match in _HTML_TAG_RE.finditer(body):
        tag, base = match.group(0), match.start()
        for attr in _HTML_ATTR_RE.finditer(tag):
            add(_unquote_attr(attr.group(2)), base + attr.start(2), "html", body)
        for srcset in _SRCSET_RE.finditer(tag):
            for part in _unquote_attr(srcset.group(1)).split(","):
                fields = part.strip().split()
                if fields:
                    add(fields[0], base + srcset.start(1), "html", body)

    for match in _CSS_URL_RE.finditer(body):
        add(_unquote_attr(match.group(1)), match.start(1), "css", body)

    if paranoid:
        for match in _BARE_PATH_RE.finditer(body):
            add(match.group(1), match.start(1), "bare", body)

    return found
