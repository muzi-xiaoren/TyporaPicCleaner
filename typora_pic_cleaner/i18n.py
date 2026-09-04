"""User-facing strings in English and Simplified Chinese.

Both catalogues are keyed identically and a test enforces that, so a missing
translation is a failing build rather than an English string leaking into a
Chinese window.

Language selection order: an explicit ``--lang`` / ``set_language`` call, then
the ``TPC_LANG`` environment variable, then the operating system's UI language.
"""

from __future__ import annotations

import locale
import os
import subprocess
import sys

DEFAULT = "en"
SUPPORTED = ("en", "zh")

EN: dict[str, str] = {
    # -- report -----------------------------------------------------------
    "report.notes_root": "Notes root",
    "report.image_dir": "Image dir",
    "report.layout": "Layout",
    "report.scanned": "Scanned",
    "report.scanned.value": "{notes} note(s), {images} image(s); {referenced} referenced, {unreferenced} unreferenced",
    "report.unreferenced.header": "Unreferenced images ({count}, {size} reclaimable):",
    "report.unreferenced.none": "Unreferenced images: none -- nothing to clean.",
    "report.more_with_hint": "... and {count} more (use --limit 0 to list all)",
    "report.more": "... and {count} more",
    "report.orphans.header": "Orphaned .assets folders ({count}, the note file is gone):",
    "report.broken.header": "Broken references ({count}, the note points at a missing file):",
    "report.external.header": (
        "References outside the scanned tree ({count}): these files exist but were not "
        "checked, so nothing about them is safe to delete."
    ),
    "report.warnings.header": "Warnings ({count}):",
    # -- layout detection -------------------------------------------------
    "layout.sibling_assets": "sibling .assets folders ({count} found)",
    "layout.shared_folders": "shared image folders ({count}: {names})",
    "layout.global_folder": "global image folder outside the note tree ({dirs})",
    "layout.loose": "{count} image(s) sitting directly beside notes",
    "layout.none": "no images found",
    # -- cli --------------------------------------------------------------
    "cli.description": "Find and remove images your Typora notes no longer reference.",
    "cli.help.root": "note folder to scan (default: current directory)",
    "cli.help.images": "extra folder holding images, e.g. Typora's global image folder; repeatable",
    "cli.help.paranoid": "also treat any bare filename in the prose as a reference (keeps more, deletes less)",
    "cli.help.ext": "additional image extension to consider; repeatable",
    "cli.help.limit": "max rows per section, 0 for all (default: 50)",
    "cli.help.json": "emit machine-readable JSON instead of a table",
    "cli.help.lang": "interface language (default: follow the system)",
    "cli.help.scan": "report unreferenced images without touching anything",
    "cli.help.fail_on_findings": "exit 2 when unreferenced images exist",
    "cli.help.clean": "move unreferenced images to a recoverable trash",
    "cli.help.yes": "skip the confirmation prompt",
    "cli.help.trash_system": "use the OS trash instead of the in-vault trash (needs the send2trash package)",
    "cli.help.no_prune": "keep folders that end up empty",
    "cli.help.restore": "undo a previous clean",
    "cli.help.restore_root": "note folder that was cleaned",
    "cli.help.id": "batch id to restore (default: the most recent)",
    "cli.help.list": "list recorded batches and exit",
    "cli.help.dry_run": "show what would be restored",
    "cli.help.gui": "open the graphical interface",
    "cli.help.gui_root": "folder to pre-fill",
    "cli.scan.footer": (
        "Nothing has been deleted. Review the list above, then run the same command "
        "with 'clean' to move these files to the trash."
    ),
    "cli.clean.about_to": "About to move {count} file(s) ({size}) to {destination}.",
    "cli.clean.system_trash": "the system trash",
    "cli.clean.prompt": "Proceed? [y/N] ",
    "cli.clean.declined": "Nothing was moved.",
    "cli.clean.moved": "Moved {count} file(s), {size}.",
    "cli.clean.pruned": "Removed {count} empty folder(s).",
    "cli.clean.failures": "{count} file(s) could not be moved:",
    "cli.clean.undo_hint": "Batch id {batch}. Undo with:",
    "cli.restore.none": "No clean-up history under {path}",
    "cli.restore.batch_line": "{count} file(s), {size}",
    "cli.restore.system_trash_tag": " (system trash)",
    "cli.restore.done": "Restored {count} file(s).",
    "cli.restore.would": "Would restore {count} file(s).",
    "cli.restore.skipped": "skipped: {detail}",
    "cli.restore.failed": "failed: {detail}",
    "cli.error.not_a_directory": "not a directory: {path}",
    "cli.error.prefix": "error: {message}",
    "cli.aborted": "aborted",
    # -- guard rails and other failures -----------------------------------
    "err.not_an_image": "refusing to touch a non-image file: {path}",
    "err.outside_roots": "refusing to touch a file outside the scanned roots: {path}",
    "err.already_trashed": "already in the trash: {path}",
    "err.no_anchor": "no anchor root for {path}",
    "err.needs_send2trash": (
        "--trash-system needs the send2trash package (pip install send2trash); "
        "omit the flag to use the in-vault trash instead"
    ),
    "err.no_history": "no clean-up history found under {path}",
    "err.no_such_batch": "no batch named {batch}",
    "err.batch_in_system_trash": (
        "batch {batch} went to the system trash; restore it from Finder or the Recycle Bin"
    ),
    "err.missing_from_trash": "{path}: missing from the trash",
    "err.already_exists": "{path}: already exists",
    "err.undecodable": "{path}: undecodable bytes, scanned with replacements",
    # -- gui --------------------------------------------------------------
    "gui.title": "Typora Pic Cleaner",
    "gui.notes_folder": "Notes folder",
    "gui.image_folder": "Image folder",
    "gui.browse": "Browse...",
    "gui.image_folder.hint": "Optional: only needed when Typora saves images outside the notes folder.",
    "gui.cautious": "Cautious mode (also keep images merely named in the text)",
    "gui.use_system_trash": "Use system trash",
    "gui.scan": "Scan",
    "gui.move_selected": "Move selected to trash",
    "gui.undo": "Undo last clean",
    "gui.select_all": "Select all",
    "gui.select_none": "Select none",
    "gui.column.delete": "Delete?",
    "gui.column.size": "Size",
    "gui.column.path": "Unreferenced image",
    "gui.summary": "{count} selected, {size}",
    "gui.status.start": "Pick your Typora notes folder, then scan.",
    "gui.status.scanning": "Scanning...",
    "gui.status.scan_failed": "Scan failed.",
    "gui.caution": (
        "Files go to a recoverable trash. Scan the folder that contains ALL notes "
        "linking these images -- links from outside it cannot be seen."
    ),
    "gui.pick_notes_title": "Select your Typora notes folder",
    "gui.pick_images_title": "Select the folder Typora saves images into",
    "gui.err.pick_notes_first": "Please choose an existing notes folder first.",
    "gui.err.pick_cleaned_folder": "Please choose the notes folder that was cleaned.",
    "gui.stat.notes_images": "{notes} notes, {images} images",
    "gui.stat.referenced": "{count} referenced",
    "gui.stat.unreferenced": "{count} unreferenced",
    "gui.stat.broken": "{count} broken links",
    "gui.stat.orphans": "{count} orphaned .assets folders",
    "gui.stat.external": "{count} links outside the scanned folder",
    "gui.confirm.move_title": "Move to trash?",
    "gui.confirm.move_body": (
        "Move {count} file(s) ({size}) to:\n{destination}\n\n"
        "Nothing is erased -- use \"Undo last clean\" to put them back."
    ),
    "gui.confirm.undo_title": "Undo last clean?",
    "gui.confirm.undo_body": "Put back {count} file(s) from batch {batch} ({created})?",
    "gui.info.moved": "Moved {count} file(s), {size}.",
    "gui.info.move_failures": "{count} could not be moved:",
    "gui.info.restored": "Restored {count} file(s).",
    "gui.info.restore_skipped": "Skipped {count} (a file already exists there):",
    "gui.info.restore_failed": "Failed {count}:",
    "gui.info.no_history": "No clean-up history under\n{path}",
    "gui.menu.language": "Language",
    "gui.menu.lang.en": "English",
    "gui.menu.lang.zh": "简体中文",
}

ZH: dict[str, str] = {
    # -- report -----------------------------------------------------------
    "report.notes_root": "笔记目录",
    "report.image_dir": "图片目录",
    "report.layout": "存放方式",
    "report.scanned": "扫描结果",
    "report.scanned.value": "{notes} 篇笔记、{images} 张图片；{referenced} 张被引用，{unreferenced} 张未被引用",
    "report.unreferenced.header": "未被引用的图片（{count} 张，可回收 {size}）：",
    "report.unreferenced.none": "未被引用的图片：没有，无需清理。",
    "report.more_with_hint": "……还有 {count} 项（用 --limit 0 列出全部）",
    "report.more": "……还有 {count} 项",
    "report.orphans.header": "孤儿 .assets 目录（{count} 个，对应的笔记已不存在）：",
    "report.broken.header": "失效引用（{count} 处，笔记引用了不存在的文件）：",
    "report.external.header": (
        "指向扫描范围之外的引用（{count} 处）：这些文件确实存在但未被检查，"
        "因此不能据此判断任何文件可删。"
    ),
    "report.warnings.header": "警告（{count} 条）：",
    # -- layout detection -------------------------------------------------
    "layout.sibling_assets": "同名 .assets 目录（找到 {count} 个）",
    "layout.shared_folders": "统一图片目录（{count} 个：{names}）",
    "layout.global_folder": "笔记目录之外的全局图片目录（{dirs}）",
    "layout.loose": "{count} 张图片直接散落在笔记旁边",
    "layout.none": "没有找到图片",
    # -- cli --------------------------------------------------------------
    "cli.description": "找出并清理 Typora 笔记里已经没人引用的图片。",
    "cli.help.root": "要扫描的笔记目录（默认：当前目录）",
    "cli.help.images": "额外的图片目录，例如 Typora 的全局图片文件夹；可重复指定",
    "cli.help.paranoid": "正文里光是提到某个文件名也算引用（保留更多、删得更少）",
    "cli.help.ext": "额外要当作图片的扩展名；可重复指定",
    "cli.help.limit": "每节最多显示多少行，0 为全部（默认：50）",
    "cli.help.json": "输出机器可读的 JSON，而不是表格",
    "cli.help.lang": "界面语言（默认：跟随系统）",
    "cli.help.scan": "只报告未被引用的图片，不改动任何文件",
    "cli.help.fail_on_findings": "存在未被引用的图片时退出码为 2",
    "cli.help.clean": "把未被引用的图片移到可恢复的回收站",
    "cli.help.yes": "跳过确认提示",
    "cli.help.trash_system": "使用系统回收站而非笔记目录内的回收站（需要 send2trash 包）",
    "cli.help.no_prune": "保留因清理而变空的目录",
    "cli.help.restore": "撤销上一次清理",
    "cli.help.restore_root": "被清理过的笔记目录",
    "cli.help.id": "要还原的批次号（默认：最近一次）",
    "cli.help.list": "列出已记录的清理批次并退出",
    "cli.help.dry_run": "只显示会还原什么，不实际还原",
    "cli.help.gui": "打开图形界面",
    "cli.help.gui_root": "预填到界面里的目录",
    "cli.scan.footer": (
        "没有删除任何文件。请先人工过一遍上面的清单，确认无误后把命令换成 "
        "clean，才会把这些文件移到回收站。"
    ),
    "cli.clean.about_to": "即将把 {count} 个文件（{size}）移动到 {destination}。",
    "cli.clean.system_trash": "系统回收站",
    "cli.clean.prompt": "确认继续？[y/N] ",
    "cli.clean.declined": "没有移动任何文件。",
    "cli.clean.moved": "已移动 {count} 个文件，共 {size}。",
    "cli.clean.pruned": "已删除 {count} 个变空的目录。",
    "cli.clean.failures": "有 {count} 个文件无法移动：",
    "cli.clean.undo_hint": "批次号 {batch}。撤销请执行：",
    "cli.restore.none": "{path} 下没有清理历史",
    "cli.restore.batch_line": "{count} 个文件，共 {size}",
    "cli.restore.system_trash_tag": "（系统回收站）",
    "cli.restore.done": "已还原 {count} 个文件。",
    "cli.restore.would": "将会还原 {count} 个文件。",
    "cli.restore.skipped": "已跳过：{detail}",
    "cli.restore.failed": "失败：{detail}",
    "cli.error.not_a_directory": "不是一个目录：{path}",
    "cli.error.prefix": "错误：{message}",
    "cli.aborted": "已中止",
    # -- guard rails and other failures -----------------------------------
    "err.not_an_image": "拒绝操作非图片文件：{path}",
    "err.outside_roots": "拒绝操作扫描范围之外的文件：{path}",
    "err.already_trashed": "已经在回收站里了：{path}",
    "err.no_anchor": "找不到 {path} 所属的根目录",
    "err.needs_send2trash": (
        "--trash-system 需要 send2trash 包（pip install send2trash）；"
        "去掉这个参数即可使用笔记目录内的回收站"
    ),
    "err.no_history": "{path} 下没有找到清理历史",
    "err.no_such_batch": "没有名为 {batch} 的批次",
    "err.batch_in_system_trash": "批次 {batch} 移到了系统回收站，请在访达或回收站里还原",
    "err.missing_from_trash": "{path}：回收站里找不到这个文件",
    "err.already_exists": "{path}：该位置已存在文件",
    "err.undecodable": "{path}：存在无法解码的字节，已用替换字符扫描",
    # -- gui --------------------------------------------------------------
    "gui.title": "Typora 图片清理",
    "gui.notes_folder": "笔记目录",
    "gui.image_folder": "图片目录",
    "gui.browse": "浏览…",
    "gui.image_folder.hint": "可选：仅当 Typora 把图片存在笔记目录之外时才需要填。",
    "gui.cautious": "保守模式（正文里光是提到文件名也保留）",
    "gui.use_system_trash": "使用系统回收站",
    "gui.scan": "扫描",
    "gui.move_selected": "把勾选项移到回收站",
    "gui.undo": "撤销上次清理",
    "gui.select_all": "全选",
    "gui.select_none": "全不选",
    "gui.column.delete": "删除",
    "gui.column.size": "大小",
    "gui.column.path": "未被引用的图片",
    "gui.summary": "已勾选 {count} 项，共 {size}",
    "gui.status.start": "请选择 Typora 笔记目录，然后点扫描。",
    "gui.status.scanning": "正在扫描…",
    "gui.status.scan_failed": "扫描失败。",
    "gui.caution": (
        "文件会移到可恢复的回收站。请选择包含「所有」引用这些图片的笔记的目录——"
        "范围之外的引用工具看不见。"
    ),
    "gui.pick_notes_title": "选择 Typora 笔记目录",
    "gui.pick_images_title": "选择 Typora 存放图片的目录",
    "gui.err.pick_notes_first": "请先选择一个存在的笔记目录。",
    "gui.err.pick_cleaned_folder": "请选择之前被清理过的笔记目录。",
    "gui.stat.notes_images": "{notes} 篇笔记、{images} 张图片",
    "gui.stat.referenced": "{count} 张被引用",
    "gui.stat.unreferenced": "{count} 张未被引用",
    "gui.stat.broken": "{count} 处失效引用",
    "gui.stat.orphans": "{count} 个孤儿 .assets 目录",
    "gui.stat.external": "{count} 处引用指向扫描范围之外",
    "gui.confirm.move_title": "移到回收站？",
    "gui.confirm.move_body": (
        "把 {count} 个文件（{size}）移动到：\n{destination}\n\n"
        "不会真正删除——点「撤销上次清理」即可放回原位。"
    ),
    "gui.confirm.undo_title": "撤销上次清理？",
    "gui.confirm.undo_body": "把批次 {batch}（{created}）的 {count} 个文件放回原位？",
    "gui.info.moved": "已移动 {count} 个文件，共 {size}。",
    "gui.info.move_failures": "有 {count} 个无法移动：",
    "gui.info.restored": "已还原 {count} 个文件。",
    "gui.info.restore_skipped": "已跳过 {count} 个（原位置已有文件）：",
    "gui.info.restore_failed": "失败 {count} 个：",
    "gui.info.no_history": "以下目录没有清理历史：\n{path}",
    "gui.menu.language": "语言",
    "gui.menu.lang.en": "English",
    "gui.menu.lang.zh": "简体中文",
}

CATALOGUES = {"en": EN, "zh": ZH}

_current = DEFAULT


def _normalise(tag: str | None) -> str | None:
    """Map a locale tag such as ``zh_CN.UTF-8`` onto a supported language."""
    if not tag:
        return None
    lowered = tag.replace("-", "_").lower()
    if lowered.startswith("zh"):
        return "zh"
    if lowered.startswith("en"):
        return "en"
    return None


def _macos_ui_language() -> str | None:
    """Ask macOS for its UI language.

    Python's ``locale`` reports the POSIX locale, which on macOS stays at
    ``en_US`` even when the interface is Chinese -- so the preference has to be
    read from the defaults database instead.
    """
    if sys.platform != "darwin":
        return None
    try:
        output = subprocess.run(
            ["defaults", "read", "-g", "AppleLanguages"],
            capture_output=True, text=True, timeout=3, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for token in output.replace("(", " ").replace(")", " ").replace(",", " ").split():
        language = _normalise(token.strip().strip('"'))
        if language:
            return language
    return None


def _windows_ui_language() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()  # type: ignore[attr-defined]
        return _normalise(locale.windows_locale.get(lcid))
    except Exception:
        return None


def detect_language() -> str:
    """Best guess at the language this user reads, defaulting to English."""
    for source in (
        os.environ.get("TPC_LANG"),
        os.environ.get("LC_ALL"),
        os.environ.get("LC_MESSAGES"),
        os.environ.get("LANG"),
        os.environ.get("LANGUAGE"),
    ):
        language = _normalise(source)
        if language:
            return language
    for probe in (_macos_ui_language, _windows_ui_language):
        language = probe()
        if language:
            return language
    try:
        return _normalise(locale.getdefaultlocale()[0]) or DEFAULT
    except (ValueError, TypeError):
        return DEFAULT


def set_language(language: str | None) -> str:
    """Select the active language; ``None`` or ``"auto"`` means detect."""
    global _current
    if language in (None, "", "auto"):
        _current = detect_language()
    elif language in CATALOGUES:
        _current = language
    else:
        _current = DEFAULT
    return _current


def get_language() -> str:
    return _current


def t(key: str, **kwargs: object) -> str:
    """Look up *key* in the active catalogue and fill in its placeholders.

    Falls back to English and finally to the key itself, so a typo shows up as
    a visible marker instead of raising in front of the user.
    """
    template = CATALOGUES.get(_current, EN).get(key) or EN.get(key) or key
    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return template
