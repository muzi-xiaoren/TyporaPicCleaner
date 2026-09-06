"""Guard rails, the trash round trip, and restore's refusal to clobber."""

from __future__ import annotations

import json
import os
import shutil
import unittest
from unittest import mock

from tests.helpers import VaultTestCase
from typora_pic_cleaner import actions
from typora_pic_cleaner.actions import (
    MANIFEST_NAME,
    UnsafePath,
    check_safe,
    list_batches,
    move_to_trash,
    newest_restorable,
    restore_batch,
    trash_root_for,
)
from typora_pic_cleaner.compare import analyze


class GuardRailTests(VaultTestCase):
    def test_non_image_is_refused(self):
        note = self.write("note.md", "text\n")
        with self.assertRaises(UnsafePath):
            check_safe(note, (self.vault,))

    def test_file_outside_the_roots_is_refused(self):
        outside = os.path.join(os.path.dirname(self.vault), "escape.png")
        with self.assertRaises(UnsafePath):
            check_safe(outside, (self.vault,))

    def test_traversal_out_of_the_root_is_refused(self):
        with self.assertRaises(UnsafePath):
            check_safe(os.path.join(self.vault, "..", "escape.png"), (self.vault,))

    def test_a_file_already_in_the_trash_is_refused(self):
        staged = self.image(".typora-pic-trash/20200101-000000/files/0/a.png")
        with self.assertRaises(UnsafePath):
            check_safe(staged, (self.vault,))

    def test_a_plain_image_inside_the_root_is_accepted(self):
        check_safe(self.image("img/a.png"), (self.vault,))

    def test_move_records_a_failure_instead_of_aborting(self):
        good = self.image("img/good.png")
        note = self.write("note.md", "text\n")
        batch = move_to_trash([note, good], roots=(self.vault,), md_root=self.vault)
        self.assertEqual(1, len(batch.entries))
        self.assertEqual(1, len(batch.failures))
        self.assertTrue(os.path.exists(note), "the note must be left alone")
        self.assertFalse(os.path.exists(good))


class RoundTripTests(VaultTestCase):
    def _dead_vault(self):
        self.write("note.md", "![](note.assets/used.png)\n")
        self.image("note.assets/used.png")
        self.image("note.assets/dead.png", 4096)
        self.image("assets/also-dead.jpg", 128)
        return analyze(self.vault)

    def test_clean_then_restore_returns_every_file(self):
        result = self._dead_vault()
        before = {p: os.path.getsize(p) for p in (self.path("note.assets/dead.png"), self.path("assets/also-dead.jpg"))}
        batch = move_to_trash(
            [i.path for i in result.unreferenced], roots=(self.vault,), md_root=self.vault
        )
        self.assertEqual(2, len(batch.entries))
        self.assertEqual([], batch.failures)
        for path in before:
            self.assertFalse(os.path.exists(path))
        self.assertTrue(os.path.exists(self.path("note.assets/used.png")), "used image must survive")

        restored = restore_batch(self.vault)
        self.assertEqual(2, len(restored.restored))
        self.assertEqual([], restored.failures)
        for path, size in before.items():
            self.assertTrue(os.path.exists(path))
            self.assertEqual(size, os.path.getsize(path))

    def test_manifest_is_written_and_readable(self):
        result = self._dead_vault()
        batch = move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,), md_root=self.vault)
        with open(os.path.join(batch.trash_dir, MANIFEST_NAME), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(1, data["version"])
        self.assertEqual(2, len(data["entries"]))
        self.assertEqual([self.vault], data["anchors"])
        listed = list_batches(self.vault)
        self.assertEqual(1, len(listed))
        self.assertEqual(batch.batch_id, listed[0]["batch_id"])

    def test_emptied_folders_are_pruned_but_the_root_survives(self):
        self.write("note.md", "text\n")
        self.image("only-images/a.png")
        result = analyze(self.vault)
        move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,), md_root=self.vault)
        self.assertFalse(os.path.isdir(self.path("only-images")))
        self.assertTrue(os.path.isdir(self.vault))

    def test_restore_refuses_to_overwrite_a_replacement_file(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,), md_root=self.vault)
        replacement = self.image("img/dead.png", 999)  # user put a new picture there
        result = restore_batch(self.vault)
        self.assertEqual([], result.restored)
        self.assertEqual(1, len(result.skipped))
        self.assertEqual(999, os.path.getsize(replacement), "the replacement must be untouched")

    def test_restore_keeps_history_when_something_was_skipped(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,), md_root=self.vault)
        self.image("img/dead.png", 999)
        restore_batch(self.vault)
        self.assertEqual(1, len(list_batches(self.vault)), "history must stay for a second attempt")

    def test_history_disappears_after_a_clean_restore(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,), md_root=self.vault)
        restore_batch(self.vault)
        self.assertEqual([], list_batches(self.vault))
        self.assertFalse(os.path.exists(trash_root_for(self.vault)), "empty trash root should go too")

    def test_restore_named_batch(self):
        self.write("note.md", "text\n")
        first = move_to_trash([self.image("img/a.png")], roots=(self.vault,), md_root=self.vault)
        self.image("img/b.png")
        move_to_trash([self.path("img/b.png")], roots=(self.vault,), md_root=self.vault)
        restore_batch(self.vault, batch_id=first.batch_id)
        self.assertTrue(os.path.exists(self.path("img/a.png")))
        self.assertFalse(os.path.exists(self.path("img/b.png")))

    def test_restore_with_no_history_explains_itself(self):
        with self.assertRaises(UnsafePath):
            restore_batch(self.vault)

    def test_dry_run_restore_moves_nothing(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png")
        move_to_trash([dead], roots=(self.vault,), md_root=self.vault)
        result = restore_batch(self.vault, dry_run=True)
        self.assertEqual(1, len(result.restored))
        self.assertFalse(os.path.exists(dead))
        self.assertEqual(1, len(list_batches(self.vault)))

    def test_a_second_scan_ignores_the_trash_folder(self):
        result = self._dead_vault()
        move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,), md_root=self.vault)
        again = analyze(self.vault)
        self.assertEqual([], again.unreferenced, "trashed files must not be re-listed")


class ExternalAnchorTests(VaultTestCase):
    def test_a_file_from_the_declared_image_folder_round_trips(self):
        pics = os.path.abspath(os.path.join(self.vault, "..", os.path.basename(self.vault) + "-pics"))
        os.makedirs(pics, exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(pics, ignore_errors=True))
        dead = os.path.join(pics, "dead.png")
        with open(dead, "wb") as handle:
            handle.write(b"\x89PNG")
        self.write("note.md", "no links\n")

        result = analyze(self.vault, image_dirs=(pics,))
        batch = move_to_trash(
            [i.path for i in result.unreferenced], roots=(self.vault, pics), md_root=self.vault
        )
        self.assertEqual(1, len(batch.entries))
        self.assertEqual(1, batch.entries[0].anchor, "must be anchored to the image folder")
        self.assertFalse(os.path.exists(dead))
        restore_batch(self.vault)
        self.assertTrue(os.path.exists(dead), "restored back into the external folder")


if __name__ == "__main__":
    unittest.main()


class NewestRestorableTests(VaultTestCase):
    """What the undo button is allowed to promise."""

    def setUp(self):
        super().setUp()
        self.image("img/a.png")
        self.image("img/b.png")

    def clean(self, name, **kwargs):
        path = self.image("img/%s.png" % name)
        return move_to_trash([path], roots=(self.vault,), md_root=self.vault, **kwargs)

    def test_no_history_means_nothing_to_offer(self):
        self.assertIsNone(newest_restorable([self.vault]))

    def test_an_in_vault_batch_is_offered(self):
        batch = self.clean("one")
        found = newest_restorable([self.vault])
        self.assertIsNotNone(found)
        self.assertEqual(found[0], self.vault)
        self.assertEqual(found[1]["batch_id"], batch.batch_id)

    def test_a_system_trash_batch_is_never_offered(self):
        with mock.patch.object(actions, "_system_trash_fn", lambda: os.remove):
            self.clean("two", system_trash=True)
        self.assertIsNone(newest_restorable([self.vault]))

    def test_a_later_system_trash_run_does_not_hide_an_earlier_undo(self):
        wanted = self.clean("three")
        with mock.patch.object(actions, "_system_trash_fn", lambda: os.remove):
            self.clean("four", system_trash=True)
        found = newest_restorable([self.vault])
        self.assertIsNotNone(found)
        self.assertEqual(found[1]["batch_id"], wanted.batch_id)

    def stamp(self, batch, created):
        """Rewrite a batch's timestamp, so ordering is asserted rather than raced."""
        path = os.path.join(batch.trash_dir, MANIFEST_NAME)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["created"] = created
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def test_the_more_recent_clean_is_the_one_offered(self):
        older, newer = self.clean("five"), self.clean("six")
        self.stamp(older, "2026-01-01T00:00:00")
        self.stamp(newer, "2026-02-01T00:00:00")
        self.assertEqual(newest_restorable([self.vault])[1]["batch_id"], newer.batch_id)

    def test_a_folder_further_down_the_list_is_still_searched(self):
        """The first folder is not privileged: the list gets reordered."""
        other = os.path.join(os.path.dirname(self.vault), os.path.basename(self.vault) + "-two")
        os.makedirs(os.path.join(other, "img"))
        self.addCleanup(shutil.rmtree, other, ignore_errors=True)
        picture = os.path.join(other, "img", "seven.png")
        with open(picture, "wb") as handle:
            handle.write(b"\x89PNG")
        batch = move_to_trash([picture], roots=(other,), md_root=other)
        found = newest_restorable([self.vault, other])
        self.assertEqual(found[0], other)
        self.assertEqual(found[1]["batch_id"], batch.batch_id)
