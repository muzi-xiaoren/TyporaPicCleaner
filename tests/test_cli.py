"""The command layer: exit codes, JSON shape, and the confirmation prompt."""

from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from tests.helpers import VaultTestCase
from typora_pic_cleaner.cli import main


def run(argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class ScanCommandTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.write("note.md", "![](img/used.png)\n")
        self.image("img/used.png")
        self.image("img/dead.png", 2048)

    def test_scan_reports_without_deleting(self):
        code, out, _ = run(["scan", self.vault])
        self.assertEqual(0, code)
        self.assertIn("dead.png", out)
        self.assertIn("Nothing has been deleted", out)
        self.assertTrue(os.path.exists(self.path("img/dead.png")))

    def test_scan_json_shape(self):
        _, out, _ = run(["scan", self.vault, "--json"])
        payload = json.loads(out)
        self.assertEqual(1, payload["unreferenced_count"])
        self.assertEqual(2048, payload["reclaimable_bytes"])
        self.assertEqual(1, payload["referenced"])
        self.assertTrue(payload["unreferenced"][0]["path"].endswith("dead.png"))

    def test_fail_on_findings_exit_code(self):
        self.assertEqual(2, run(["scan", self.vault, "--fail-on-findings"])[0])

    def test_clean_vault_exits_zero_with_fail_on_findings(self):
        os.remove(self.path("img/dead.png"))
        self.assertEqual(0, run(["scan", self.vault, "--fail-on-findings"])[0])

    def test_missing_directory_is_an_error_not_a_crash(self):
        code, _, err = run(["scan", os.path.join(self.vault, "nope")])
        self.assertEqual(1, code)
        self.assertIn("not a directory", err)

    def test_no_command_prints_help(self):
        code, out, _ = run([])
        self.assertEqual(1, code)
        self.assertIn("usage", out)


class CleanCommandTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.write("note.md", "![](img/used.png)\n")
        self.image("img/used.png")
        self.dead = self.image("img/dead.png", 2048)

    def test_declining_the_prompt_keeps_everything(self):
        with mock.patch("builtins.input", return_value="n"):
            code, out, _ = run(["clean", self.vault])
        self.assertEqual(1, code)
        self.assertIn("Nothing was moved", out)
        self.assertTrue(os.path.exists(self.dead))

    def test_accepting_the_prompt_moves_the_file(self):
        with mock.patch("builtins.input", return_value="y"):
            code, out, _ = run(["clean", self.vault])
        self.assertEqual(0, code)
        self.assertFalse(os.path.exists(self.dead))
        self.assertIn("Undo with", out)

    def test_yes_flag_skips_the_prompt(self):
        code, out, _ = run(["clean", self.vault, "-y"])
        self.assertEqual(0, code)
        self.assertFalse(os.path.exists(self.dead))
        self.assertTrue(os.path.exists(self.path("img/used.png")))

    def test_clean_then_restore_via_cli(self):
        run(["clean", self.vault, "-y"])
        code, out, _ = run(["restore", self.vault])
        self.assertEqual(0, code)
        self.assertIn("Restored 1", out)
        self.assertTrue(os.path.exists(self.dead))

    def test_restore_list(self):
        run(["clean", self.vault, "-y"])
        code, out, _ = run(["restore", self.vault, "--list"])
        self.assertEqual(0, code)
        self.assertIn("1 file(s)", out)

    def test_restore_list_with_no_history(self):
        code, out, _ = run(["restore", self.vault, "--list"])
        self.assertEqual(0, code)
        self.assertIn("No clean-up history", out)

    def test_clean_with_nothing_to_do_does_not_prompt(self):
        os.remove(self.dead)
        with mock.patch("builtins.input", side_effect=AssertionError("must not prompt")):
            code, out, _ = run(["clean", self.vault])
        self.assertEqual(0, code)
        self.assertIn("nothing to clean", out)

    def test_ext_flag_is_honoured_end_to_end(self):
        psd = self.image("img/layer.psd", 10)
        run(["clean", self.vault, "-y"])
        self.assertTrue(os.path.exists(psd), "not an image by default")
        run(["clean", self.vault, "-y", "--ext", "psd"])
        self.assertFalse(os.path.exists(psd))


if __name__ == "__main__":
    unittest.main()
