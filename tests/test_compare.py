"""End-to-end analysis over real directory trees."""

from __future__ import annotations

import os
import unittest

from tests.helpers import VaultTestCase
from typora_pic_cleaner.compare import analyze
from typora_pic_cleaner.paths import PathKeyer


class SiblingAssetsTests(VaultTestCase):
    def test_used_and_unused_in_a_sibling_assets_folder(self):
        self.write("note.md", "![](note.assets/used.png)\n")
        self.image("note.assets/used.png")
        self.image("note.assets/dead.png")
        result = analyze(self.vault)
        self.assertSameFiles([i.path for i in result.unreferenced], ["note.assets/dead.png"])
        self.assertEqual(1, result.referenced)

    def test_reference_from_a_note_in_another_folder(self):
        self.write("a/one.md", "![](../b/shared.png)\n")
        self.image("b/shared.png")
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_cjk_and_space_in_filename(self):
        self.write("note.md", "![](<图 片/我的 图.png>)\n![](img/%E4%B8%AD%E6%96%87.png)\n")
        self.image("图 片/我的 图.png")
        self.image("img/中文.png")
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_fenced_code_does_not_keep_an_image_alive(self):
        self.write("note.md", "```md\n![](img/documented.png)\n```\n")
        self.image("img/documented.png")
        self.assertEqual(1, len(analyze(self.vault).unreferenced))

    def test_paranoid_mode_keeps_a_merely_mentioned_file(self):
        self.write("note.md", "The banner lives at img/banner.png today.\n")
        self.image("img/banner.png")
        self.assertEqual(1, len(analyze(self.vault).unreferenced))
        self.assertEqual([], analyze(self.vault, paranoid=True).unreferenced)

    def test_hidden_and_vcs_folders_are_never_proposed(self):
        self.write("note.md", "no images\n")
        self.image(".git/objects/blob.png")
        self.image(".obsidian/plugin/icon.png")
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_extra_extension_opt_in(self):
        self.write("note.md", "no images\n")
        self.image("img/layer.psd")
        self.assertEqual([], analyze(self.vault).unreferenced)
        result = analyze(self.vault, extra_exts=frozenset({".psd"}))
        self.assertEqual(1, len(result.unreferenced))


class CaseSensitivityTests(VaultTestCase):
    def test_case_differing_reference_matches_on_case_insensitive_volumes(self):
        self.write("note.md", "![](img/Photo.PNG)\n")
        self.image("img/photo.png")
        result = analyze(self.vault)
        if PathKeyer(self.vault).fold_case:
            self.assertEqual([], result.unreferenced, "should match, this volume ignores case")
        else:
            self.assertEqual(1, len(result.unreferenced))
            self.assertEqual(1, len(result.broken))


class BrokenAndExternalTests(VaultTestCase):
    def test_missing_target_is_reported_broken(self):
        self.write("note.md", "![](img/gone.png)\n")
        broken = analyze(self.vault).broken
        self.assertEqual(1, len(broken))
        self.assertEqual("img/gone.png", broken[0].raw)
        self.assertEqual(1, broken[0].line)

    def test_remote_urls_are_not_broken_references(self):
        self.write("note.md", "![](https://example.com/a.png)\n![](data:image/png;base64,AA)\n")
        self.assertEqual([], analyze(self.vault).broken)

    def test_ambiguous_title_syntax_reports_one_broken_site_not_two(self):
        self.write("note.md", '![](img/gone.png "caption")\n')
        self.assertEqual(1, len(analyze(self.vault).broken))

    def test_existing_file_outside_the_tree_is_surfaced_not_ignored(self):
        outside = os.path.join(os.path.dirname(self.vault), "outside-pic.png")
        with open(outside, "wb") as handle:
            handle.write(b"\x89PNG")
        self.addCleanup(os.remove, outside)
        self.write("notes/note.md", "![](../../outside-pic.png)\n")
        result = analyze(self.vault)
        self.assertEqual(1, len(result.external))
        self.assertEqual([], result.broken)


class GlobalImageFolderTests(VaultTestCase):
    def test_images_outside_the_note_tree_are_scanned_when_declared(self):
        pics = os.path.join(self.vault, "..", os.path.basename(self.vault) + "-pics")
        pics = os.path.abspath(pics)
        os.makedirs(pics, exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(pics, ignore_errors=True))
        for name in ("used.png", "dead.png"):
            with open(os.path.join(pics, name), "wb") as handle:
                handle.write(b"\x89PNG")
        self.write("note.md", f"<img src=\"{os.path.join(pics, 'used.png')}\">\n")
        result = analyze(self.vault, image_dirs=(pics,))
        self.assertEqual([os.path.join(pics, "dead.png")], [i.path for i in result.unreferenced])


class TyporaRootUrlTests(VaultTestCase):
    """Typora lets a note redefine "/" per file; ignoring that deletes live images."""

    def test_relative_root_url_inside_the_vault(self):
        self.write(
            "notes/deep/post.md",
            "---\ntypora-root-url: ../../store\n---\n![](/pics/live.png)\n",
        )
        self.image("store/pics/live.png")
        result = analyze(self.vault)
        self.assertEqual([], result.unreferenced, "the image is in use")
        self.assertEqual([], result.broken)

    def test_absolute_root_url(self):
        self.image("store/pics/live.png")
        self.write(
            "notes/post.md",
            f"---\ntypora-root-url: {os.path.join(self.vault, 'store')}\n---\n![](/pics/live.png)\n",
        )
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_quoted_root_url(self):
        self.write(
            "notes/post.md",
            '---\ntypora-root-url: "../store"\n---\n![](/pics/live.png)\n',
        )
        self.image("store/pics/live.png")
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_root_url_does_not_widen_what_may_be_deleted(self):
        # A root outside the scanned tree is used for matching only: its files
        # are never inventoried, so they can never be proposed for deletion.
        outside = os.path.abspath(os.path.join(self.vault, "..", os.path.basename(self.vault) + "-store"))
        os.makedirs(os.path.join(outside, "pics"), exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(outside, ignore_errors=True))
        for name in ("live.png", "dead.png"):
            with open(os.path.join(outside, "pics", name), "wb") as handle:
                handle.write(b"\x89PNG")
        self.write("post.md", f"---\ntypora-root-url: {outside}\n---\n![](/pics/live.png)\n")
        result = analyze(self.vault)
        self.assertEqual([], result.unreferenced)
        self.assertEqual([], result.broken, "the link resolves through the declared root")

    def test_a_note_without_root_url_is_unaffected(self):
        self.write("a.md", "---\ntitle: plain\n---\n![](/pics/x.png)\n")
        self.image("pics/x.png")
        self.assertEqual([], analyze(self.vault).unreferenced)

    def test_root_url_is_per_file_not_global(self):
        self.write("a.md", "---\ntypora-root-url: ./store-a\n---\n![](/pics/a.png)\n")
        self.write("b.md", "---\ntypora-root-url: ./store-b\n---\n![](/pics/b.png)\n")
        self.image("store-a/pics/a.png")
        self.image("store-b/pics/b.png")
        self.image("store-a/pics/stale.png")
        result = analyze(self.vault)
        self.assertSameFiles([i.path for i in result.unreferenced], ["store-a/pics/stale.png"])


class OrphanAssetsTests(VaultTestCase):
    def test_assets_folder_whose_note_is_gone(self):
        self.image("dead.assets/pic.png")
        self.write("other.md", "nothing\n")
        self.assertSameFiles(analyze(self.vault).orphan_asset_dirs, ["dead.assets"])

    def test_assets_folder_with_its_note_present_is_not_an_orphan(self):
        self.write("live.md", "no link to the folder\n")
        self.image("live.assets/pic.png")
        result = analyze(self.vault)
        self.assertEqual([], result.orphan_asset_dirs)
        self.assertEqual(1, len(result.unreferenced))  # the picture is still dead

    def test_assets_folder_still_linked_from_elsewhere_is_not_an_orphan(self):
        self.image("dead.assets/pic.png")
        self.write("other.md", "![](dead.assets/pic.png)\n")
        self.assertEqual([], analyze(self.vault).orphan_asset_dirs)


class LayoutDetectionTests(VaultTestCase):
    def test_layout_summary_names_what_it_found(self):
        self.write("note.md", "![](note.assets/a.png)\n")
        self.image("note.assets/a.png")
        self.image("assets/b.png")
        keys = [key for key, _params in analyze(self.vault).layouts]
        self.assertIn("layout.sibling_assets", keys)
        self.assertIn("layout.shared_folders", keys)


if __name__ == "__main__":
    unittest.main()


class SeveralNotesFoldersTests(VaultTestCase):
    """Scanning folders together, which is what stops a shared picture dying."""

    def setUp(self) -> None:
        super().setUp()
        self.write("work/note.md", "![](../shared/logo.png)\n")
        self.write("home/diary.md", "# nothing linked\n")
        self.image("shared/logo.png")
        self.image("shared/nobody.png")

    def test_a_picture_one_folder_links_survives_a_scan_of_both(self):
        analysis = analyze([self.path("work"), self.path("shared")])
        self.assertSameFiles(
            [image.path for image in analysis.unreferenced], ["shared/nobody.png"]
        )

    def test_scanning_the_image_folder_alone_would_have_condemned_it(self):
        # The regression this feature exists for: on its own, ``shared`` has no
        # note pointing at ``logo.png``, so the old single-folder scan called it
        # unreferenced and offered to delete a picture that is in use.
        analysis = analyze(self.path("shared"))
        self.assertSameFiles(
            [image.path for image in analysis.unreferenced],
            ["shared/logo.png", "shared/nobody.png"],
        )

    def test_notes_from_every_folder_are_counted_once(self):
        analysis = analyze([self.path("work"), self.path("home"), self.path("shared")])
        self.assertEqual(analysis.md_count, 2)
        self.assertEqual(analysis.total_images, 2)

    def test_repeating_a_folder_does_not_double_count_it(self):
        analysis = analyze([self.path("work"), self.path("work")])
        self.assertEqual(analysis.md_roots, (self.path("work"),))
        self.assertEqual(analysis.md_count, 1)

    def test_overlapping_folders_inventory_each_file_once(self):
        analysis = analyze([self.vault, self.path("shared")])
        self.assertEqual(analysis.total_images, 2)
        self.assertEqual(analysis.md_count, 2)

    def test_the_first_folder_anchors_the_undo_history(self):
        analysis = analyze([self.path("home"), self.path("work")])
        self.assertEqual(analysis.md_root, self.path("home"))

    def test_roots_covers_every_tree_files_may_leave(self):
        analysis = analyze([self.path("work")], image_dirs=(self.path("shared"),))
        self.assertEqual(analysis.roots, (self.path("work"), self.path("shared")))

    def test_a_string_is_still_accepted_as_one_folder(self):
        self.assertEqual(analyze(self.path("work")).md_roots, (self.path("work"),))

    def test_no_folders_at_all_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            analyze([])

    def test_a_link_into_an_unlisted_folder_is_reported_not_assumed(self):
        analysis = analyze([self.path("work")])
        self.assertEqual(len(analysis.external), 1)
        self.assertEqual(analysis.external[0].resolved, self.path("shared/logo.png"))
