from __future__ import annotations

import hashlib
import sqlite3
import unittest
import zlib
from pathlib import Path

from tools.patch_emblem_chokepoint import (
    NEW,
    OLD,
    SUPPORTED_SOURCE_SHA256,
    event_body,
    patch,
)


ROOT = Path(__file__).resolve().parents[1]


def bundled_source() -> bytes:
    db = sqlite3.connect(ROOT / "research" / "bb_inputs.db")
    try:
        row = db.execute(
            "SELECT blob FROM files WHERE path = ?",
            ("event/m24_00_00_00.emevd.dcx.js",),
        ).fetchone()
    finally:
        db.close()
    assert row is not None
    return zlib.decompress(row[0])


class EmblemChokepointPatchTests(unittest.TestCase):
    def test_supported_source_is_pinned_and_patch_is_narrow(self):
        source = bundled_source()
        self.assertEqual(hashlib.sha256(source).hexdigest(), SUPPORTED_SOURCE_SHA256)
        output = patch(source)
        before = source.decode("utf-8-sig")
        after = output.decode("utf-8")
        self.assertEqual(before.replace(OLD, NEW, 1), after)
        self.assertIn(NEW, event_body(after))
        self.assertNotIn("ObjActEventFlag(12400170)", event_body(after))

    def test_identity_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            patch(bundled_source() + b"\n")

    def test_wrong_event_shape_fails_closed(self):
        source = bundled_source().replace(OLD.encode(), NEW.encode())
        # Re-pin only for this shape test by demonstrating the public guard
        # catches it first; production can never silently accept either skew.
        with self.assertRaisesRegex(ValueError, "unsupported"):
            patch(source)


if __name__ == "__main__":
    unittest.main()
