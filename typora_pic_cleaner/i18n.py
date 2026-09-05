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

from . import prefs

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
    "cli.help.root": "notes folder to scan; give several and they are compared as one corpus (default: current directory)",
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
    "cli.help.gui_root": "notes folder(s) to open the window with",
    "cli.help.discover": "list the folders under a directory that contain notes",
    "cli.help.discover_parent": "folder to look inside (default: current directory)",
    "cli.help.depth": "how many levels below that folder to list",
    "cli.discover.none": "No folder under {path} contains notes.",
    "cli.discover.counts": "({notes} notes, {images} images)",
    "cli.discover.footer": "Pass any of these to scan/clean -- several at once are compared as one corpus.",
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
    "gui.cautious": "Cautious mode (also keep images merely named in the text)",
    "gui.use_system_trash": "Use system trash",
    "gui.scan": "Scan",
    "gui.move_selected": "Move selected to trash",
    "gui.undo": "Undo last clean",
    "gui.select_all": "Select all",
    "gui.select_none": "Select none",
    "gui.column.size": "Size",
    "gui.column.path": "Unreferenced image",
    "gui.summary": "{count} selected, {size}",
    "gui.status.start": "Find or add your Typora notes folders, then scan.",
    "gui.status.scanning": "Scanning {count} folder(s)...",
    "gui.status.scan_failed": "Scan failed.",
    "gui.caution": (
        "Files go to a recoverable trash. Scan the folder that contains ALL notes "
        "linking these images -- links from outside it cannot be seen."
    ),
    "gui.pick_notes_title": "Select your Typora notes folder",
    "gui.pick_images_title": "Select the folder Typora saves images into",
    "gui.err.pick_notes_first": "Tick at least one existing notes folder first.",
    "gui.err.pick_cleaned_folder": "Tick the notes folder that was cleaned.",
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
    "gui.subtitle": "Find the pictures your notes stopped pointing at.",
    "gui.section.notes": "Notes folders",
    "gui.section.images": "Image folders",
    "gui.section.options": "Options",
    "gui.btn.find": "Find folders\u2026",
    "gui.btn.add": "Add\u2026",
    "gui.btn.remove": "Remove",
    "gui.hint.notes": "Tick the folders to scan. Ticking a folder covers everything inside it.",
    "gui.hint.images": "Only needed when Typora saves pictures outside your notes folders.",
    "gui.folder.counts": "{notes} md \u00b7 {images} img",
    "gui.folder.covered": "in parent",
    "gui.folder.missing": "missing",
    "gui.tile.notes": "Notes",
    "gui.tile.images": "Images",
    "gui.tile.unreferenced": "Unreferenced",
    "gui.tile.reclaimable": "Reclaimable",
    "gui.menu.settings": "Settings",
    "gui.menu.appearance": "Appearance",
    "gui.menu.appearance.auto": "Follow system",
    "gui.menu.appearance.light": "Light",
    "gui.menu.appearance.dark": "Dark",
    "gui.pick_parent_title": "Choose a folder to search for notes folders in",
    "gui.status.finding": "Looking through {path}\u2026",
    "gui.status.found": "Found {count} folder(s), {added} new. Untick any you do not want scanned.",
    "gui.status.found_none": "No folder in there contains notes. Try the folder one level up.",
    "gui.empty.no_folders": "Tick at least one notes folder on the left.",
    "gui.empty.not_scanned": "Press Scan to see which pictures nothing points at.",
    "gui.empty.nothing_found": "Nothing unreferenced \u2014 every picture is in use.",
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
    "cli.help.root": "要扫描的笔记目录，可以写多个，会作为一个整体一起比对（默认：当前目录）",
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
    "cli.help.gui_root": "启动界面时先加好的笔记目录",
    "cli.help.discover": "列出某个目录下含有笔记的文件夹",
    "cli.help.discover_parent": "要在其中查找的目录（默认：当前目录）",
    "cli.help.depth": "向下列几层",
    "cli.discover.none": "{path} 下面没有含笔记的文件夹。",
    "cli.discover.counts": "（{notes} 篇笔记，{images} 张图片）",
    "cli.discover.footer": "把其中任意几个传给 scan/clean 即可；多个文件夹会作为一个整体一起比对。",
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
    "gui.cautious": "保守模式（正文里光是提到文件名也保留）",
    "gui.use_system_trash": "使用系统回收站",
    "gui.scan": "扫描",
    "gui.move_selected": "把勾选项移到回收站",
    "gui.undo": "撤销上次清理",
    "gui.select_all": "全选",
    "gui.select_none": "全不选",
    "gui.column.size": "大小",
    "gui.column.path": "未被引用的图片",
    "gui.summary": "已勾选 {count} 项，共 {size}",
    "gui.status.start": "先查找或添加 Typora 笔记文件夹，然后扫描。",
    "gui.status.scanning": "正在扫描 {count} 个文件夹…",
    "gui.status.scan_failed": "扫描失败。",
    "gui.caution": (
        "文件会移到可恢复的回收站。请选择包含「所有」引用这些图片的笔记的目录——"
        "范围之外的引用工具看不见。"
    ),
    "gui.pick_notes_title": "选择 Typora 笔记目录",
    "gui.pick_images_title": "选择 Typora 存放图片的目录",
    "gui.err.pick_notes_first": "请先勾选至少一个存在的笔记文件夹。",
    "gui.err.pick_cleaned_folder": "请勾选之前被清理过的笔记文件夹。",
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
    "gui.subtitle": "\u627e\u51fa\u7b14\u8bb0\u5df2\u7ecf\u4e0d\u518d\u5f15\u7528\u7684\u56fe\u7247\u3002",
    "gui.section.notes": "\u7b14\u8bb0\u6587\u4ef6\u5939",
    "gui.section.images": "\u56fe\u7247\u6587\u4ef6\u5939",
    "gui.section.options": "\u9009\u9879",
    "gui.btn.find": "\u67e5\u627e\u6587\u4ef6\u5939\u2026",
    "gui.btn.add": "\u6dfb\u52a0\u2026",
    "gui.btn.remove": "\u79fb\u9664",
    "gui.hint.notes": "\u52fe\u9009\u8981\u626b\u63cf\u7684\u6587\u4ef6\u5939\uff1b\u52fe\u4e0a\u4e0a\u7ea7\u5c31\u5305\u542b\u4e86\u5b83\u4e0b\u9762\u7684\u5168\u90e8\u5185\u5bb9\u3002",
    "gui.hint.images": "\u4ec5\u5f53 Typora \u628a\u56fe\u7247\u5b58\u5728\u7b14\u8bb0\u6587\u4ef6\u5939\u4e4b\u5916\u65f6\u624d\u9700\u8981\u6dfb\u52a0\u3002",
    "gui.folder.counts": "{notes} \u7bc7 \u00b7 {images} \u5f20",
    "gui.folder.covered": "\u5df2\u542b\u5728\u4e0a\u7ea7",
    "gui.folder.missing": "\u5df2\u4e0d\u5b58\u5728",
    "gui.tile.notes": "\u7b14\u8bb0",
    "gui.tile.images": "\u56fe\u7247",
    "gui.tile.unreferenced": "\u672a\u88ab\u5f15\u7528",
    "gui.tile.reclaimable": "\u53ef\u56de\u6536",
    "gui.menu.settings": "\u8bbe\u7f6e",
    "gui.menu.appearance": "\u5916\u89c2",
    "gui.menu.appearance.auto": "\u8ddf\u968f\u7cfb\u7edf",
    "gui.menu.appearance.light": "\u6d45\u8272",
    "gui.menu.appearance.dark": "\u6df1\u8272",
    "gui.pick_parent_title": "\u9009\u62e9\u8981\u5728\u5176\u4e2d\u67e5\u627e\u7b14\u8bb0\u6587\u4ef6\u5939\u7684\u76ee\u5f55",
    "gui.status.finding": "\u6b63\u5728\u67e5\u627e {path}\u2026",
    "gui.status.found": "\u627e\u5230 {count} \u4e2a\u6587\u4ef6\u5939\uff0c\u5176\u4e2d {added} \u4e2a\u662f\u65b0\u7684\u3002\u4e0d\u60f3\u626b\u7684\u53ef\u4ee5\u53d6\u6d88\u52fe\u9009\u3002",
    "gui.status.found_none": "\u8fd9\u4e2a\u76ee\u5f55\u91cc\u6ca1\u6709\u542b\u7b14\u8bb0\u7684\u6587\u4ef6\u5939\uff0c\u8bd5\u8bd5\u518d\u4e0a\u4e00\u5c42\u3002",
    "gui.empty.no_folders": "\u8bf7\u5148\u5728\u5de6\u4fa7\u52fe\u9009\u81f3\u5c11\u4e00\u4e2a\u7b14\u8bb0\u6587\u4ef6\u5939\u3002",
    "gui.empty.not_scanned": "\u70b9\u53f3\u4e0b\u89d2\u7684\u626b\u63cf\uff0c\u770b\u770b\u54ea\u4e9b\u56fe\u7247\u5df2\u7ecf\u6ca1\u4eba\u5f15\u7528\u3002",
    "gui.empty.nothing_found": "\u6ca1\u6709\u672a\u88ab\u5f15\u7528\u7684\u56fe\u7247\uff0c\u5168\u90fd\u5728\u7528\u3002",
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
    """Best guess at the language this user reads, defaulting to English.

    Order of authority: the ``TPC_LANG`` environment variable, then a language
    the user picked in the interface before, then POSIX locale variables, then
    the operating system's own UI language.  The saved choice outranks the OS
    on purpose -- someone running an English system who switched the tool to
    Chinese meant it, and should not have to redo it on every launch.
    """
    for source in (
        os.environ.get("TPC_LANG"),
        prefs.load_language(),
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
