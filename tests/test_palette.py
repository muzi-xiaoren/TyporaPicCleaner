"""The palette, checked without a display.

Tk cannot always be imported, let alone opened, so these tests target the token
module alone.  They catch the one class of mistake that would otherwise reach a
user: a colour that exists in one mode and not the other, which crashes only
after they switch themes.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from typora_pic_cleaner import palette as theme


class PaletteTests(unittest.TestCase):
    def test_both_modes_define_the_same_names(self):
        self.assertEqual(set(theme.LIGHT), set(theme.DARK))

    def test_every_value_is_a_hex_colour(self):
        for name, palette in (("light", theme.LIGHT), ("dark", theme.DARK)):
            for key, value in palette.items():
                self.assertRegex(value, r"^#[0-9a-f]{6}$", f"{name}.{key}")

    def test_the_two_modes_actually_differ(self):
        self.assertNotEqual(theme.LIGHT["bg"], theme.DARK["bg"])
        self.assertNotEqual(theme.LIGHT["text"], theme.DARK["text"])

    def test_text_and_background_are_not_the_same_colour(self):
        for palette in (theme.LIGHT, theme.DARK):
            for surface in ("bg", "sidebar", "raised"):
                self.assertNotEqual(palette["text"], palette[surface])

    def test_every_colour_the_code_asks_for_exists(self):
        """A typo in a colour name is invisible until that widget is drawn."""
        source = pathlib.Path(theme.__file__).parent
        asked = set()
        for module in source.glob("*.py"):
            text = module.read_text(encoding="utf-8")
            asked |= set(re.findall(r'\.color\(\s*"([a-z_]+)"', text))
            asked |= set(re.findall(r'\bc\[\s*"([a-z_]+)"\s*\]', text))
        self.assertEqual(asked - set(theme.LIGHT), set())

    def test_every_platform_has_a_full_type_scale(self):
        names = set(theme.SIZES["other"])
        for platform, sizes in theme.SIZES.items():
            self.assertEqual(set(sizes), names, platform)
            self.assertTrue(all(size > 0 for size in sizes.values()), platform)

    def test_detect_mode_answers_with_one_of_the_two(self):
        self.assertIn(theme.detect_mode(), ("light", "dark"))
