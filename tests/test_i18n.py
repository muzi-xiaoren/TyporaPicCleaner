"""Translation integrity, and that the interface actually switches."""

from __future__ import annotations

import io
import os
import string
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.helpers import VaultTestCase
from typora_pic_cleaner.cli import main
from typora_pic_cleaner.i18n import CATALOGUES, EN, SUPPORTED, ZH, detect_language, set_language, t


def placeholders(template: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


class CatalogueTests(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_every_english_key_has_a_translation(self):
        self.assertEqual(set(), set(EN) - set(ZH), "keys missing from the Chinese catalogue")

    def test_no_stray_translations(self):
        self.assertEqual(set(), set(ZH) - set(EN), "keys not present in the English catalogue")

    def test_placeholders_match_across_languages(self):
        for key, english in EN.items():
            self.assertEqual(
                placeholders(english),
                placeholders(ZH[key]),
                f"placeholder mismatch for {key!r} -- formatting would silently fall back",
            )

    def test_no_empty_strings(self):
        for language, catalogue in CATALOGUES.items():
            for key, value in catalogue.items():
                self.assertTrue(value.strip(), f"{language}:{key} is empty")

    def test_chinese_is_actually_chinese(self):
        # Guards against a copy-paste that leaves an English string in place.
        untranslated = [
            key for key, value in ZH.items()
            if not key.startswith("gui.menu.lang.") and value == EN[key]
        ]
        self.assertEqual([], untranslated)

    def test_supported_languages_all_have_a_catalogue(self):
        for language in SUPPORTED:
            self.assertIn(language, CATALOGUES)


class LookupTests(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_switching_language_changes_the_text(self):
        set_language("en")
        english = t("gui.scan")
        set_language("zh")
        self.assertNotEqual(english, t("gui.scan"))

    def test_unknown_key_returns_the_key_not_an_exception(self):
        self.assertEqual("no.such.key", t("no.such.key"))

    def test_unknown_language_falls_back_to_english(self):
        set_language("kl")
        self.assertEqual(EN["gui.scan"], t("gui.scan"))

    def test_missing_placeholder_returns_the_template(self):
        # Better a raw template on screen than a traceback in front of the user.
        self.assertEqual(EN["gui.summary"], t("gui.summary", wrong=1))


class DetectionTests(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_explicit_override_wins(self):
        with mock.patch.dict(os.environ, {"TPC_LANG": "zh"}, clear=False):
            self.assertEqual("zh", detect_language())

    def test_posix_locale_is_understood(self):
        with mock.patch.dict(os.environ, {"TPC_LANG": "", "LC_ALL": "zh_CN.UTF-8"}, clear=False):
            self.assertEqual("zh", detect_language())

    def test_traditional_chinese_locale_maps_to_chinese(self):
        with mock.patch.dict(os.environ, {"TPC_LANG": "", "LC_ALL": "zh-Hant-TW"}, clear=False):
            self.assertEqual("zh", detect_language())

    def test_unrelated_locale_falls_back_to_english(self):
        with mock.patch.dict(os.environ, {"TPC_LANG": "", "LC_ALL": "de_DE.UTF-8"}, clear=False):
            with mock.patch("typora_pic_cleaner.i18n._macos_ui_language", return_value=None):
                with mock.patch("typora_pic_cleaner.i18n._windows_ui_language", return_value=None):
                    self.assertEqual("en", detect_language())


class CliLanguageTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.write("note.md", "![](img/used.png)\n")
        self.image("img/used.png")
        self.image("img/dead.png", 2048)

    def _run(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            main(argv)
        return out.getvalue()

    def test_lang_flag_switches_the_report(self):
        self.assertIn("Unreferenced images", self._run(["--lang", "en", "scan", self.vault]))
        self.assertIn("未被引用的图片", self._run(["--lang", "zh", "scan", self.vault]))

    def test_lang_flag_switches_help(self):
        # argparse builds help text at parser construction, so the language has
        # to be applied before that -- this is the regression test for it.
        with self.assertRaises(SystemExit):
            self.assertIn("笔记目录", self._run(["--lang", "zh", "scan", "--help"]))

    def test_json_layout_keys_do_not_change_with_language(self):
        import json

        english = json.loads(self._run(["--lang", "en", "scan", self.vault, "--json"]))
        chinese = json.loads(self._run(["--lang", "zh", "scan", self.vault, "--json"]))
        self.assertEqual(
            [entry["key"] for entry in english["layouts"]],
            [entry["key"] for entry in chinese["layouts"]],
        )
        self.assertNotEqual(english["layouts_text"], chinese["layouts_text"])

    def test_environment_variable_selects_the_language(self):
        with mock.patch.dict(os.environ, {"TPC_LANG": "zh"}, clear=False):
            self.assertIn("未被引用的图片", self._run(["scan", self.vault]))


if __name__ == "__main__":
    unittest.main()
