"""Finding candidate folders, and the model behind the folder sidebar."""

from __future__ import annotations

import os

from typora_pic_cleaner.discovery import (
    Folder, FolderSet, discover, key_for, shorten, summarise, within,
)

from .helpers import VaultTestCase


class DiscoverTests(VaultTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("journal/2026-01-01.md", "# hi")
        self.write("journal/2026-01-02.md", "# ho")
        self.image("journal/2026-01-01.assets/a.png")
        self.write("tech/note.md", "# tech")
        self.image("tech/img/b.png")
        self.image("tech/img/c.png")
        self.image("wallpapers/only-pictures.png")

    def paths(self, found):
        return [os.path.relpath(c.path, self.vault) for c in found]

    def test_lists_only_folders_that_hold_notes(self):
        found = discover(self.vault)
        self.assertEqual(self.paths(found), [os.curdir, "journal", "tech"])

    def test_counts_roll_up_from_the_whole_subtree(self):
        by_name = {os.path.relpath(c.path, self.vault): c for c in discover(self.vault)}
        self.assertEqual((by_name["tech"].notes, by_name["tech"].images), (1, 2))
        # The root sees everything below it, wallpapers included.
        self.assertEqual((by_name[os.curdir].notes, by_name[os.curdir].images), (3, 4))

    def test_own_notes_distinguishes_a_notes_folder_from_a_container(self):
        by_name = {os.path.relpath(c.path, self.vault): c for c in discover(self.vault)}
        self.assertEqual(by_name[os.curdir].own_notes, 0)
        self.assertEqual(by_name["journal"].own_notes, 2)

    def test_depth_limits_the_rows_but_not_the_counts(self):
        self.write("tech/deep/deeper/buried.md", "# buried")
        shallow = discover(self.vault, max_depth=1)
        self.assertNotIn(os.path.join("tech", "deep"), self.paths(shallow))
        by_name = {os.path.relpath(c.path, self.vault): c for c in shallow}
        self.assertEqual(by_name["tech"].notes, 2)

    def test_parent_points_at_the_containing_row(self):
        found = {c.path: c for c in discover(self.vault)}
        self.assertIsNone(found[os.path.realpath(self.vault)].parent)
        self.assertEqual(found[self.path("tech")].parent, os.path.realpath(self.vault))

    def test_skips_the_directories_a_scan_would_skip(self):
        self.write(".git/hooks/notes.md", "# not yours")
        self.write("node_modules/pkg/readme.md", "# vendored")
        self.assertEqual(self.paths(discover(self.vault)), [os.curdir, "journal", "tech"])

    def test_a_folder_with_no_notes_anywhere_yields_nothing(self):
        self.assertEqual(discover(self.path("wallpapers")), [])

    def test_summarise_counts_a_hand_added_folder(self):
        self.assertEqual(summarise(self.path("tech")), (1, 2))
        # No notes, but the pictures still have to be reported: this is exactly
        # what the image-folder list is for.
        self.assertEqual(summarise(self.path("wallpapers")), (0, 1))


class PathHelperTests(VaultTestCase):
    def test_within_is_strict(self):
        self.assertTrue(within(self.path("a/b"), self.path("a")))
        self.assertFalse(within(self.path("a"), self.path("a")))
        self.assertFalse(within(self.path("a"), self.path("b")))

    def test_key_for_ignores_spelling(self):
        self.assertEqual(key_for(self.path("a/b")), key_for(self.path("a/./b")))


class FolderSetTests(VaultTestCase):
    def test_add_refuses_a_duplicate_path(self):
        folders = FolderSet([Folder("/notes")])
        self.assertFalse(folders.add(Folder("/notes", selected=False)))
        self.assertEqual(len(folders), 1)
        self.assertTrue(folders.get("/notes").selected)

    def test_merge_refreshes_counts_but_keeps_the_users_tick(self):
        folders = FolderSet([Folder("/notes", selected=False)])
        added = folders.merge([Folder("/notes", selected=True, notes=9, images=4, counted=True)])
        self.assertEqual(added, 0)
        self.assertFalse(folders.get("/notes").selected)
        self.assertEqual((folders.get("/notes").notes, folders.get("/notes").images), (9, 4))

    def test_merge_reports_and_appends_new_folders(self):
        folders = FolderSet([Folder("/notes")])
        self.assertEqual(folders.merge([Folder("/notes"), Folder("/other")]), 1)
        self.assertEqual([f.path for f in folders], ["/notes", "/other"])

    def test_selected_paths_drops_a_folder_its_parent_already_covers(self):
        folders = FolderSet([Folder(self.path("a")), Folder(self.path("a/b"))])
        self.assertEqual(folders.selected_paths(), [self.path("a")])
        folders.toggle(self.path("a"))
        self.assertEqual(folders.selected_paths(), [self.path("a/b")])

    def test_selected_paths_keeps_order_which_anchors_the_undo_history(self):
        folders = FolderSet([Folder("/second"), Folder("/first")])
        self.assertEqual(folders.selected_paths(), ["/second", "/first"])

    def test_missing_folders_are_never_scanned_and_never_toggle(self):
        folders = FolderSet([Folder(self.path("gone")), Folder(self.path("here"))])
        os.makedirs(self.path("here"))
        folders.refresh_missing()
        self.assertEqual(folders.selected_paths(), [self.path("here")])
        folders.toggle(self.path("gone"))
        self.assertTrue(folders.get(self.path("gone")).selected)

    def test_remove_takes_the_nested_folders_with_it(self):
        folders = FolderSet([Folder(self.path("a")), Folder(self.path("a/b")),
                             Folder(self.path("c"))])
        self.assertEqual(folders.remove([self.path("a")]), 2)
        self.assertEqual([f.path for f in folders], [self.path("c")])

    def test_set_all_leaves_missing_folders_alone(self):
        folders = FolderSet([Folder("/a", selected=False),
                             Folder("/b", selected=False, missing=True)])
        folders.set_all(True)
        self.assertTrue(folders.get("/a").selected)
        self.assertFalse(folders.get("/b").selected)

    def test_render_order_puts_every_ancestor_first(self):
        folders = FolderSet([Folder(self.path("a/b/c")), Folder(self.path("a")),
                             Folder(self.path("a/b"))])
        order = [os.path.relpath(k, key_for(self.vault)) for k in folders.render_order()]
        self.assertEqual(order, ["a", os.path.join("a", "b"), os.path.join("a", "b", "c")])


class ShortenTests(VaultTestCase):
    def test_a_short_path_is_left_alone(self):
        short = os.path.join("notes", "work")
        self.assertEqual(short, shorten(short))

    def test_the_home_prefix_becomes_a_tilde(self):
        self.assertEqual("~" + os.sep + "Notes",
                         shorten(os.path.join(os.path.expanduser("~"), "Notes")))

    def test_a_long_path_keeps_its_tail(self):
        shortened = shorten(os.path.join(
            os.sep, "a", "very", "long", "chain", "of", "directories", "that", "keeps", "notes"))
        self.assertTrue(shortened.startswith("\u2026" + os.sep))
        self.assertTrue(shortened.endswith("notes"))
        self.assertLessEqual(len(shortened), 34)

    def test_the_result_never_mixes_separators(self):
        """A sidebar row reading ``...\\Users/me`` looks like a bug to a user."""
        shortened = shorten(os.path.join(os.sep, "a" * 12, "b" * 12, "c" * 12, "notes"))
        self.assertNotIn("/" if os.sep == "\\" else "\\", shortened)


class NestingTests(VaultTestCase):
    def test_parent_is_the_deepest_listed_folder_that_contains_it(self):
        folders = FolderSet([Folder(self.path("a")), Folder(self.path("a/b")),
                             Folder(self.path("a/b/c"))])
        self.assertEqual(folders.parent_of(self.path("a/b/c")), key_for(self.path("a/b")))

    def test_a_folder_with_nothing_above_it_has_no_parent(self):
        folders = FolderSet([Folder(self.path("a")), Folder(self.path("b"))])
        self.assertIsNone(folders.parent_of(self.path("a")))

    def test_nesting_survives_a_restart_because_it_is_derived(self):
        # The list comes back from the settings file as flat paths, with no
        # record of which row sat under which.
        folders = FolderSet([Folder(self.path("vault/tech")), Folder(self.path("vault"))])
        self.assertEqual(folders.parent_of(self.path("vault/tech")), key_for(self.path("vault")))

    def test_a_hand_added_folder_slots_under_one_that_was_found(self):
        folders = FolderSet([Folder(self.path("vault"))])
        folders.add(Folder(self.path("vault/extra")))
        self.assertEqual(folders.parent_of(self.path("vault/extra")), key_for(self.path("vault")))


class NoiseFilterTests(VaultTestCase):
    """A search of a whole drive has to come back with a readable answer."""

    def names(self, parent=None):
        return {os.path.relpath(c.path, parent or self.vault) for c in discover(parent or self.vault)}

    def test_software_trees_are_never_offered(self):
        self.write("Notes/diary.md", "# mine")
        for junk in ("anaconda3/Lib/site-packages/pkg", "Program Files/app",
                     "$RECYCLE.BIN/x", "AppData/Roaming/app", "Library/thing"):
            self.write(junk + "/notes.md", "# not mine")
        self.assertEqual(self.names(), {os.curdir, "Notes"})

    def test_a_folder_of_packaged_documentation_is_left_out(self):
        self.write("Notes/diary.md", "# mine")
        self.write("somelib/README.md", "# lib")
        self.write("somelib/CHANGELOG.md", "# lib")
        self.write("somelib/LICENSE.md", "# lib")
        self.assertEqual(self.names(), {os.curdir, "Notes"})

    def test_one_real_note_is_enough_to_keep_a_folder(self):
        self.write("project/README.md", "# lib")
        self.write("project/设计稿.md", "# mine")
        self.assertIn("project", self.names())

    def test_boilerplate_is_not_credited_to_the_parents_count(self):
        self.write("Notes/diary.md", "# mine")
        for index in range(20):
            self.write("lib%d/README.md" % index, "# lib")
        root = next(c for c in discover(self.vault) if c.depth == 0)
        self.assertEqual(root.notes, 1)
        self.assertEqual(root.skipped_notes, 20)

    def test_names_a_person_might_really_use_are_not_boilerplate(self):
        for name in ("todo", "index", "notes", "history"):
            with self.subTest(name=name):
                self.write("f_%s/%s.md" % (name, name), "# mine")
        self.assertEqual(
            self.names() - {os.curdir},
            {"f_todo", "f_index", "f_notes", "f_history"},
        )

    def test_an_explicitly_named_software_folder_is_still_counted_in_full(self):
        """The filter guides the search; it never overrules a direct request.

        The row's number has to match what a scan of it would see, or the user
        is looking at two different truths.
        """
        self.write("anaconda3/pkg/README.md", "# lib")
        self.image("anaconda3/pkg/logo.png")
        self.assertEqual(summarise(self.path("anaconda3/pkg")), (1, 1))

    def test_an_image_only_folder_reports_its_pictures(self):
        """The usual case for the image-folder list, which holds no notes."""
        self.image("图库/a.png")
        self.image("图库/b.png")
        self.assertEqual(summarise(self.path("图库")), (0, 2))
