import sqlite3
import zlib
from pathlib import Path

import unittest

from tools.patch_hemwick_gate import ACCESS_FLAG, BOUNDARY, GATE_EVENT, patch

ROOT = Path(__file__).parents[1]


def bundled_source(map_name):
    db = sqlite3.connect(ROOT / "research" / "bb_inputs.db")
    try:
        row = db.execute("SELECT blob FROM files WHERE path = ?",
                         (f"event/{map_name}.emevd.dcx.js",)).fetchone()
    finally:
        db.close()
    assert row is not None
    return zlib.decompress(row[0])


class HemwickGatePatchTests(unittest.TestCase):
    def test_access_flag_is_unowned_in_the_bundled_event_corpus(self):
        db = sqlite3.connect(ROOT / "research" / "bb_inputs.db")
        try:
            rows = db.execute(
                "SELECT path, blob FROM files WHERE path LIKE 'event/%.js'"
            ).fetchall()
        finally:
            db.close()
        collisions = [
            path for path, blob in rows
            if str(ACCESS_FLAG).encode() in zlib.decompress(blob)
        ]
        self.assertEqual([], collisions)

    def test_patch_replaces_only_the_owned_boundary_initializer(self):
        for map_name in sorted(BOUNDARY):
            with self.subTest(map_name=map_name):
                source = bundled_source(map_name)
                slot, obj, sfx = BOUNDARY[map_name]
                output = patch(source, map_name).decode()
                self.assertNotIn(f"$InitializeEvent({slot}, 7600, {obj}, {sfx});", output)
                self.assertIn(f"$InitializeEvent(0, {GATE_EVENT[map_name]});", output)
                self.assertEqual(output.count(f"DeactivateObject({obj}, Enabled);"), 1)
                self.assertEqual(output.count(f"SpawnMapSFX({sfx});"), 1)
                self.assertEqual(output.count(f"EventFlag({ACCESS_FLAG})"), 2)

    def test_patch_rejects_an_unsupported_shape(self):
        source = bundled_source("m22_00_00_00")
        with self.assertRaisesRegex(ValueError, "exactly one boundary initializer"):
            patch(source.replace(b"2201999", b"2201998", 1),
                  "m22_00_00_00", verify_source=False)
