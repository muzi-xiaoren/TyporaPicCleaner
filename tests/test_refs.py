"""The reference-extraction table: every way Typora can point at an image."""

from __future__ import annotations

import unittest

from typora_pic_cleaner.refs import (
    extract_references,
    front_matter_root_url,
    mask_code,
    split_front_matter,
)


def raws(text: str, paranoid: bool = False) -> set[str]:
    found = set()
    for ref in extract_references(text, paranoid=paranoid):
        found.update(ref.raws)
    return found


class ExtractionTests(unittest.TestCase):
    def test_standard_markdown_image(self):
        self.assertIn("assets/a.png", raws("![alt](assets/a.png)"))

    def test_angle_bracketed_path_with_spaces(self):
        self.assertIn("my pic.png", raws("![](<my pic.png>)"))

    def test_title_is_stripped_but_raw_kept_as_fallback(self):
        got = raws('![](img/a.png "a caption")')
        self.assertIn("img/a.png", got)
        self.assertIn('img/a.png "a caption"', got)

    def test_parenthesis_in_filename(self):
        self.assertIn("img (1).png", raws("![](img (1).png)"))

    def test_plain_link_to_an_image_counts(self):
        self.assertIn("files/a.gif", raws("[download](files/a.gif)"))

    def test_reference_definition(self):
        self.assertIn("./img/a.jpeg", raws("[key]: ./img/a.jpeg"))

    def test_html_img_all_quote_styles(self):
        got = raws("""<img src="a.png"><img src='b.png'><img src=c.png>""")
        self.assertEqual({"a.png", "b.png", "c.png"}, got)

    def test_html_srcset_and_poster(self):
        got = raws('<img srcset="r1.png 1x, r2.png 2x"><video poster="p.jpg"></video>')
        self.assertEqual({"r1.png", "r2.png", "p.jpg"}, got)

    def test_inline_css_url(self):
        self.assertIn("bg.png", raws("""<div style="background:url('bg.png')"></div>"""))

    def test_front_matter_scalar_and_quoted_list(self):
        got = raws('---\ncover: assets/c.png\nlist: [a/one.jpg, "b/two (2).webp"]\n---\nbody\n')
        self.assertEqual({"assets/c.png", "a/one.jpg", "b/two (2).webp"}, got)

    def test_front_matter_quoted_value_is_not_double_counted(self):
        # The bare scan must not re-match "(2).webp" out of the quoted value and
        # invent a second, broken reference.
        got = raws('---\nlist: ["b/two (2).webp"]\n---\n')
        self.assertEqual({"b/two (2).webp"}, got)

    def test_fenced_code_is_ignored(self):
        self.assertEqual(set(), raws("```md\n![](inside.png)\n```\n"))

    def test_tilde_fence_is_ignored(self):
        self.assertEqual(set(), raws("~~~\n![](inside.png)\n~~~\n"))

    def test_fence_with_info_string_does_not_close_the_block(self):
        text = "```\n![](one.png)\n```js\n![](two.png)\n```\n"
        self.assertEqual(set(), raws(text))

    def test_inline_code_is_ignored(self):
        self.assertEqual(set(), raws("use `![](inline.png)` like so"))

    def test_line_numbers_survive_masking(self):
        refs = extract_references("```\nx\n```\n\n![](a.png)\n")
        self.assertEqual([5], [ref.line for ref in refs])

    def test_paranoid_picks_up_bare_filenames(self):
        self.assertNotIn("loose.png", raws("see loose.png for details"))
        self.assertIn("loose.png", raws("see loose.png for details", paranoid=True))

    def test_paranoid_does_not_manufacture_paths_from_urls(self):
        got = raws("![](https://host.example/a.png)", paranoid=True)
        self.assertNotIn("//host.example/a.png", got)


class RootUrlTests(unittest.TestCase):
    def test_plain_value(self):
        self.assertEqual("../store", front_matter_root_url("---\ntypora-root-url: ../store\n---\n"))

    def test_quoted_values(self):
        for text in ('---\ntypora-root-url: "../s"\n---\n', "---\ntypora-root-url: '../s'\n---\n"):
            self.assertEqual("../s", front_matter_root_url(text))

    def test_windows_root_loses_the_stray_slash(self):
        # Typora writes Windows roots as "/D:/pics", which is not a usable path.
        self.assertEqual("D:/pics", front_matter_root_url("---\ntypora-root-url: /D:/pics\n---\n"))

    def test_absent(self):
        self.assertIsNone(front_matter_root_url("---\ntitle: x\n---\n"))
        self.assertIsNone(front_matter_root_url("# no front matter\n"))

    def test_only_read_from_front_matter(self):
        # A mention in the body is prose, not configuration.
        self.assertIsNone(front_matter_root_url("typora-root-url: ../store\n"))


class MaskingTests(unittest.TestCase):
    def test_mask_preserves_length_and_newlines(self):
        text = "a\n```\nsecret\n```\nb\n"
        masked = mask_code(text)
        self.assertEqual(len(text), len(masked))
        self.assertEqual(text.count("\n"), masked.count("\n"))
        self.assertNotIn("secret", masked)

    def test_split_front_matter(self):
        front, body = split_front_matter("---\nkey: value\n---\nbody\n")
        self.assertEqual("key: value", front)
        self.assertIn("body", body)

    def test_no_front_matter(self):
        front, body = split_front_matter("# Title\n---\nnot front matter\n")
        self.assertEqual("", front)
        self.assertIn("not front matter", body)

    def test_horizontal_rule_mid_document_is_not_front_matter(self):
        front, _ = split_front_matter("text\n\n---\n\nmore\n")
        self.assertEqual("", front)


if __name__ == "__main__":
    unittest.main()
