from __future__ import annotations

import hashlib
import sqlite3
import unittest
import zlib
from pathlib import Path

from tools.patch_laurence_skull import (
    EVENT,
    NEW_GUARD,
    NEW_TAIL,
    OLD_GUARD,
    OLD_TAIL,
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


class LaurenceSkullPatchTests(unittest.TestCase):
    def test_supported_source_is_pinned_and_only_target_event_changes(self):
        source = bundled_source()
        self.assertEqual(hashlib.sha256(source).hexdigest(), SUPPORTED_SOURCE_SHA256)
        before = source.decode("utf-8-sig").replace("\r\n", "\n")
        after = patch(source).decode("utf-8")
        old_body = event_body(before)
        new_body = old_body.replace(OLD_GUARD, NEW_GUARD, 1).replace(
            OLD_TAIL, NEW_TAIL, 1
        )
        start = before.index(f"$Event({EVENT},")
        expected = before[:start] + new_body + before[start + len(old_body) :]
        self.assertEqual(expected, after)

        body = event_body(after)
        self.assertIn("SetEventFlag(12401898, ON);", body)
        self.assertNotIn("SetEventFlag(12401803, ON);", body)
        self.assertIn("RestartEvent();", body)

    def test_interaction_event_no_longer_completes_its_password_flag(self):
        body = event_body(patch(bundled_source()).decode("utf-8"))
        self.assertNotIn("EndIf(ThisEvent());", body)
        self.assertIn("EndIf(EventFlag(12401898));", body)
        self.assertEqual(EVENT, "12401803")

    def test_identity_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            patch(bundled_source() + b"\n")


if __name__ == "__main__":
    unittest.main()
