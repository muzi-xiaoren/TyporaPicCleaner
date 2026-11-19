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
    restore_everywhere,
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
        batch = move_to_trash([note, good], roots=(self.vault,))
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
            [i.path for i in result.unreferenced], roots=(self.vault,)
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
        batch = move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,))
        with open(os.path.join(batch.batches[0].trash_dir, MANIFEST_NAME), encoding="utf-8") as handle:
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
        move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,))
        self.assertFalse(os.path.isdir(self.path("only-images")))
        self.assertTrue(os.path.isdir(self.vault))

    def test_restore_refuses_to_overwrite_a_replacement_file(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,))
        replacement = self.image("img/dead.png", 999)  # user put a new picture there
        result = restore_batch(self.vault)
        self.assertEqual([], result.restored)
        self.assertEqual(1, len(result.skipped))
        self.assertEqual(999, os.path.getsize(replacement), "the replacement must be untouched")

    def test_restore_keeps_history_when_something_was_skipped(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,))
        self.image("img/dead.png", 999)
        restore_batch(self.vault)
        self.assertEqual(1, len(list_batches(self.vault)), "history must stay for a second attempt")

    def test_history_disappears_after_a_clean_restore(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png", 100)
        move_to_trash([dead], roots=(self.vault,))
        restore_batch(self.vault)
        self.assertEqual([], list_batches(self.vault))
        self.assertFalse(os.path.exists(trash_root_for(self.vault)), "empty trash root should go too")

    def test_restore_named_batch(self):
        self.write("note.md", "text\n")
        first = move_to_trash([self.image("img/a.png")], roots=(self.vault,))
        self.image("img/b.png")
        move_to_trash([self.path("img/b.png")], roots=(self.vault,))
        restore_batch(self.vault, batch_id=first.batch_id)
        self.assertTrue(os.path.exists(self.path("img/a.png")))
        self.assertFalse(os.path.exists(self.path("img/b.png")))

    def test_restore_with_no_history_explains_itself(self):
        with self.assertRaises(UnsafePath):
            restore_batch(self.vault)

    def test_dry_run_restore_moves_nothing(self):
        self.write("note.md", "text\n")
        dead = self.image("img/dead.png")
        move_to_trash([dead], roots=(self.vault,))
        result = restore_batch(self.vault, dry_run=True)
        self.assertEqual(1, len(result.restored))
        self.assertFalse(os.path.exists(dead))
        self.assertEqual(1, len(list_batches(self.vault)))

    def test_a_second_scan_ignores_the_trash_folder(self):
        result = self._dead_vault()
        move_to_trash([i.path for i in result.unreferenced], roots=(self.vault,))
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
            [i.path for i in result.unreferenced], roots=(self.vault, pics)
        )
        self.assertEqual(1, len(batch.entries))
        self.assertEqual([pics], batch.roots, "kept in the image folder's own trash")
        self.assertFalse(os.path.exists(dead))
        self.assertFalse(os.path.exists(trash_root_for(self.vault)), "nothing crossed folders")
        restore_everywhere([self.vault, pics])
        self.assertTrue(os.path.exists(dead), "restored back into the external folder")
        self.assertFalse(os.path.exists(trash_root_for(pics)))

    def test_an_image_folder_inside_the_notes_shares_their_trash(self):
        self.write("note.md", "no links\n")
        dead = self.image("pics/dead.png")
        batch = move_to_trash([dead], roots=(self.vault, self.path("pics")))
        self.assertEqual([self.vault], batch.roots)


class SeveralFoldersTests(VaultTestCase):
    """One clean-up, a trash per folder, one undo."""

    def setUp(self):
        super().setUp()
        self.work, self.home = self.path("work"), self.path("home")
        self.first = self.image("work/a.png")
        self.second = self.image("home/b.png")
        self.batch = move_to_trash([self.first, self.second], roots=(self.work, self.home))

    def test_each_picture_stays_in_its_own_folders_trash(self):
        self.assertEqual([self.work, self.home], self.batch.roots)
        for root, name in ((self.work, "a.png"), (self.home, "b.png")):
            stored = os.path.join(trash_root_for(root), self.batch.batch_id, "files", "0", name)
            self.assertTrue(os.path.exists(stored), stored)

    def test_both_halves_share_one_batch_id(self):
        ids = {b["batch_id"] for root in (self.work, self.home) for b in list_batches(root)}
        self.assertEqual({self.batch.batch_id}, ids)

    def test_one_undo_restores_every_folder(self):
        result = restore_everywhere([self.work, self.home])
        self.assertEqual(2, len(result.restored))
        self.assertTrue(os.path.exists(self.first) and os.path.exists(self.second))

    def test_undo_needs_only_the_folders_it_is_given(self):
        restore_everywhere([self.home])
        self.assertTrue(os.path.exists(self.second))
        self.assertFalse(os.path.exists(self.first), "work was not named, so it stays trashed")

    def test_an_unknown_batch_id_is_refused(self):
        with self.assertRaises(UnsafePath):
            restore_everywhere([self.work, self.home], batch_id="19990101-000000")


class PartialRestoreTests(VaultTestCase):
    def setUp(self):
        super().setUp()
        self.kept = self.image("img/kept.png")
        self.taken = self.image("img/taken.png")
        move_to_trash([self.kept, self.taken], roots=(self.vault,))
        self.image("img/taken.png")  # the user put something else there meanwhile
        restore_batch(self.vault)

    def test_the_history_then_lists_only_what_is_still_in_the_trash(self):
        entries = list_batches(self.vault)[0]["entries"]
        self.assertEqual(["taken.png"], [os.path.basename(e["rel"]) for e in entries])

    def test_a_batch_that_could_only_be_skipped_is_no_longer_offered(self):
        self.assertIsNone(newest_restorable([self.vault]))

    def test_it_is_offered_again_once_the_way_is_clear(self):
        os.remove(self.taken)
        self.assertIsNotNone(newest_restorable([self.vault]))


class NewestRestorableTests(VaultTestCase):
    """What the undo button is allowed to promise."""

    def setUp(self):
        super().setUp()
        self.image("img/a.png")
        self.image("img/b.png")

    def clean(self, name, **kwargs):
        path = self.image("img/%s.png" % name)
        return move_to_trash([path], roots=(self.vault,), **kwargs)

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
        path = os.path.join(batch.batches[0].trash_dir, MANIFEST_NAME)
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
        batch = move_to_trash([picture], roots=(other,))
        found = newest_restorable([self.vault, other])
        self.assertEqual(found[0], other)
        self.assertEqual(found[1]["batch_id"], batch.batch_id)


class DamagedHistoryTests(VaultTestCase):
    def _trash_one(self) -> str:
        self.write("note.md", "text\n")
        batch = move_to_trash([self.image("img/dead.png")], roots=(self.vault,))
        return batch.batches[0].trash_dir

    def test_an_unreadable_manifest_is_refused_and_its_files_are_left_alone(self):
        trash_dir = self._trash_one()
        with open(os.path.join(trash_dir, MANIFEST_NAME), "w", encoding="utf-8") as handle:
            handle.write("{ not json")
        with self.assertRaises(UnsafePath):
            restore_batch(self.vault)
        self.assertTrue(
            os.path.exists(os.path.join(trash_dir, "files", "0", "img", "dead.png")),
            "a batch that cannot be read must never be tidied away",
        )

    def test_a_manifest_that_is_not_an_object_counts_as_unreadable(self):
        trash_dir = self._trash_one()
        with open(os.path.join(trash_dir, MANIFEST_NAME), "w", encoding="utf-8") as handle:
            handle.write("[]")
        self.assertIn("error", list_batches(self.vault)[0])
        self.assertIsNone(newest_restorable([self.vault]))

    def test_an_interrupted_clean_still_records_what_it_moved(self):
        self.write("note.md", "text\n")
        first, second = self.image("img/a.png"), self.image("img/b.png")
        real_move = shutil.move
        calls = []

        def move_then_stop(source, destination):
            if calls:
                raise KeyboardInterrupt
            calls.append(source)
            return real_move(source, destination)

        with mock.patch.object(actions.shutil, "move", side_effect=move_then_stop):
            with self.assertRaises(KeyboardInterrupt):
                move_to_trash([first, second], roots=(self.vault,))
        self.assertFalse(os.path.exists(first))
        restore_batch(self.vault)
        self.assertTrue(os.path.exists(first), "the half-finished batch has to be undoable")
        self.assertTrue(os.path.exists(second))


if __name__ == "__main__":
    unittest.main()
