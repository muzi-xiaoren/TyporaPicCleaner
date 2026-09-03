"""Path normalisation: the layer that decides whether two spellings are one file."""

from __future__ import annotations

import os
import unittest

from typora_pic_cleaner.paths import (
    PathKeyer,
    has_image_ext,
    is_within,
    reference_variants,
    resolve_reference,
)


def anchored(*parts: str) -> str:
    """An absolute path on whatever drive the tests are running from.

    A bare "\\v\\notes" is drive-*relative* on Windows, so comparing it against
    what the resolver returns would only ever pass on POSIX.
    """
    return os.path.abspath(os.path.join(os.sep, *parts))


class VariantTests(unittest.TestCase):
    def test_percent_encoding_yields_both_readings(self):
        self.assertEqual({"a/b%20c.png", "a/b c.png"}, set(reference_variants("a/b%20c.png")))

    def test_backslashes_are_offered_as_separators(self):
        self.assertIn("note.assets/pic.png", reference_variants(r"note.assets\pic.png"))

    def test_angle_brackets_are_unwrapped(self):
        self.assertEqual(["my pic.png"], reference_variants("<my pic.png>"))

    def test_fragment_and_query_are_offered_stripped(self):
        self.assertIn("a.png", reference_variants("a.png#anchor"))
        self.assertIn("a.png", reference_variants("a.png?v=2"))
        # The unstripped form stays, because both characters are legal in names.
        self.assertIn("a.png#anchor", reference_variants("a.png#anchor"))

    def test_remote_and_data_urls_are_dropped(self):
        for raw in ("https://x/a.png", "http://x/a.png", "data:image/png;base64,AA", "ftp://x/a.png"):
            self.assertEqual([], reference_variants(raw), raw)

    def test_unknown_scheme_is_dropped(self):
        self.assertEqual([], reference_variants("typora://internal/a.png"))

    def test_windows_drive_letter_is_not_a_scheme(self):
        self.assertIn(r"C:\pics\a.png", reference_variants(r"C:\pics\a.png"))

    def test_file_url_is_unwrapped(self):
        self.assertIn("/home/me/a.png", reference_variants("file:///home/me/a.png"))

    def test_windows_file_url_keeps_the_drive(self):
        self.assertIn("C:/pics/a.png", reference_variants("file:///C:/pics/a.png"))


class ResolveTests(unittest.TestCase):
    def test_relative_resolves_against_the_note_first(self):
        got = resolve_reference("img/a.png", anchored("v", "notes"), (anchored("v"),))
        self.assertEqual(anchored("v", "notes", "img", "a.png"), got[0])

    def test_extra_bases_are_also_tried(self):
        got = resolve_reference("img/a.png", anchored("v", "notes"), (anchored("v"),))
        self.assertIn(anchored("v", "img", "a.png"), got)

    def test_root_relative_link_resolves_against_the_vault(self):
        got = resolve_reference("/img/a.png", anchored("v", "notes"), (anchored("v"),))
        self.assertIn(anchored("v", "img", "a.png"), got)

    def test_parent_traversal_is_resolved_not_rejected(self):
        # Resolution stays honest about where the link points; refusing to act on
        # an outside path is the containment guard's job, not this function's.
        got = resolve_reference("../../etc/a.png", anchored("v", "notes"), ())
        self.assertEqual([anchored("etc", "a.png")], got)


class GuardTests(unittest.TestCase):
    def test_is_within_accepts_descendants_and_the_root_itself(self):
        root = anchored("vault")
        self.assertTrue(is_within(os.path.join(root, "a", "b.png"), root))
        self.assertTrue(is_within(root, root))

    def test_is_within_rejects_siblings_and_traversal(self):
        root = anchored("vault")
        self.assertFalse(is_within(anchored("vault-other", "a.png"), root))
        self.assertFalse(is_within(os.path.join(root, "..", "etc", "a.png"), root))

    def test_extension_whitelist(self):
        self.assertTrue(has_image_ext("a.PNG"))
        self.assertTrue(has_image_ext("a.webp"))
        self.assertFalse(has_image_ext("a.md"))
        self.assertFalse(has_image_ext("a.png.txt"))
        self.assertTrue(has_image_ext("a.psd", frozenset({".psd"})))


class KeyerTests(unittest.TestCase):
    def test_dot_segments_normalise_to_the_same_key(self):
        keyer = PathKeyer()
        base = anchored("v", "notes")
        self.assertEqual(
            keyer.key(os.path.join(base, "..", "notes", "a.png")),
            keyer.key(os.path.join(base, "a.png")),
        )

    def test_case_folding_matches_the_filesystem(self):
        keyer = PathKeyer()
        same = keyer.key("/v/A.PNG") == keyer.key("/v/a.png")
        self.assertEqual(keyer.fold_case, same)


if __name__ == "__main__":
    unittest.main()
