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
