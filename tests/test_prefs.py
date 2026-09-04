"""The settings file: it must remember a choice, and never break startup."""

from __future__ import annotations

import json
import os
import unittest

from tests.helpers import ConfigIsolationMixin
from typora_pic_cleaner import prefs
from typora_pic_cleaner.i18n import detect_language, set_language


class PrefsTests(ConfigIsolationMixin):
    def setUp(self):
        self.directory = self.isolate_config()
        self.addCleanup(set_language, "en")

    def test_absent_file_reads_as_empty(self):
        self.assertEqual({}, prefs.load())
        self.assertIsNone(prefs.load_language())

    def test_round_trip(self):
        self.assertTrue(prefs.save_language("zh"))
        self.assertEqual("zh", prefs.load_language())

    def test_saving_merges_rather_than_replaces(self):
        prefs.save(other="keep me")
        prefs.save_language("zh")
        data = prefs.load()
        self.assertEqual("keep me", data["other"])
        self.assertEqual("zh", data["language"])

    def test_corrupt_file_does_not_raise(self):
        os.makedirs(self.directory, exist_ok=True)
        with open(prefs.config_path(), "w", encoding="utf-8") as handle:
            handle.write("{not json at all")
        self.assertEqual({}, prefs.load())
        self.assertIsNone(prefs.load_language())

    def test_non_object_json_is_ignored(self):
        os.makedirs(self.directory, exist_ok=True)
        with open(prefs.config_path(), "w", encoding="utf-8") as handle:
            json.dump(["not", "a", "mapping"], handle)
        self.assertEqual({}, prefs.load())

    def test_unwritable_location_reports_failure_instead_of_raising(self):
        # A regular file where a parent directory is expected: makedirs cannot
        # succeed, and losing a preference must not raise at the user.
        blocker = os.path.join(self.directory, "blocker")
        os.makedirs(self.directory, exist_ok=True)
        with open(blocker, "w", encoding="utf-8") as handle:
            handle.write("not a directory")
        os.environ["TPC_CONFIG"] = os.path.join(blocker, "settings")
        self.assertFalse(prefs.save_language("zh"))
        self.assertIsNone(prefs.load_language())


class PreferenceOrderTests(ConfigIsolationMixin):
    def setUp(self):
        self.isolate_config()
        self.addCleanup(set_language, "en")
        for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE", "TPC_LANG"):
            os.environ.pop(name, None)

    def test_saved_choice_beats_the_system_language(self):
        # The whole point: an English system, a user who wants Chinese.
        os.environ["LANG"] = "en_US.UTF-8"
        prefs.save_language("zh")
        self.assertEqual("zh", detect_language())

    def test_environment_variable_beats_the_saved_choice(self):
        prefs.save_language("zh")
        os.environ["TPC_LANG"] = "en"
        self.assertEqual("en", detect_language())

    def test_no_saved_choice_falls_through_to_the_locale(self):
        os.environ["LANG"] = "zh_CN.UTF-8"
        self.assertEqual("zh", detect_language())


if __name__ == "__main__":
    unittest.main()
