"""How results are worded, in particular once several folders are in play."""

from __future__ import annotations

import os

from typora_pic_cleaner.compare import analyze
from typora_pic_cleaner.report import display_path, human_report, human_size

from .helpers import VaultTestCase


class HumanSizeTests(VaultTestCase):
    def test_bytes_stay_whole_and_larger_units_get_a_decimal(self):
        self.assertEqual("900 B", human_size(900))
        self.assertEqual("1.0 KB", human_size(1024))
        self.assertEqual("1.5 MB", human_size(1024 * 1024 * 3 // 2))


class DisplayPathTests(VaultTestCase):
    def test_one_folder_shows_a_plain_relative_path(self):
        root = self.path("notes")
        self.assertEqual(
            os.path.join("img", "a.png"),
            display_path(os.path.join(root, "img", "a.png"), (root,)),
        )

    def test_several_folders_keep_the_folder_name_to_tell_them_apart(self):
        work, home = self.path("work"), self.path("home")
        self.assertEqual(
            os.path.join("work", "img", "a.png"),
            display_path(os.path.join(work, "img", "a.png"), (work, home)),
        )

    def test_the_containing_folder_wins_over_an_ancestor_also_listed(self):
        self.assertEqual(
            os.path.join("inner", "a.png"),
            display_path(self.path("outer/inner/a.png"),
                         (self.path("outer"), self.path("outer/inner"))),
        )

    def test_a_path_under_no_listed_folder_is_shown_in_full(self):
        stray = self.path("elsewhere/a.png")
        self.assertEqual(stray, display_path(stray, (self.path("notes"),)))


class ReportTests(VaultTestCase):
    def test_every_scanned_folder_is_named_in_the_header(self):
        self.write("work/note.md", "# hi")
        self.write("home/note.md", "# hi")
        text = human_report(analyze([self.path("work"), self.path("home")]))
        self.assertIn(self.path("work"), text)
        self.assertIn(self.path("home"), text)


class ImageFolderDisplayTests(VaultTestCase):
    def test_a_picture_in_an_image_folder_is_named_by_that_folder(self):
        notes, pics = self.path("notes"), self.path("pics")
        self.assertEqual(
            os.path.join("pics", "old.png"),
            display_path(os.path.join(pics, "old.png"), (notes,), (pics,)),
        )

    def test_the_notes_folder_still_wins_for_its_own_pictures(self):
        notes, pics = self.path("notes"), self.path("pics")
        self.assertEqual(
            os.path.join("img", "a.png"),
            display_path(os.path.join(notes, "img", "a.png"), (notes,), (pics,)),
        )
