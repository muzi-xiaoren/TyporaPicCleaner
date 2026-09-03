"""Shared scaffolding: build a throwaway vault on disk."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest


class VaultTestCase(unittest.TestCase):
    """A temp directory plus helpers for writing notes and dummy images."""

    def setUp(self) -> None:
        self.vault = os.path.realpath(tempfile.mkdtemp(prefix="tpc-test-"))
        self.addCleanup(shutil.rmtree, self.vault, ignore_errors=True)

    def path(self, relative: str) -> str:
        return os.path.join(self.vault, relative.replace("/", os.sep))

    def write(self, relative: str, content: str) -> str:
        full = self.path(relative)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(content)
        return full

    def image(self, relative: str, size: int = 64) -> str:
        full = self.path(relative)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as handle:
            handle.write(b"\x89PNG" + b"\0" * max(0, size - 4))
        return full

    def assertSameFiles(self, actual, expected) -> None:
        self.assertEqual(
            sorted(os.path.relpath(p, self.vault) for p in actual),
            sorted(e.replace("/", os.sep) for e in expected),
        )
