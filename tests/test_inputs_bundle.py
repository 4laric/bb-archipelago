"""Tests for the inputs bundle.

The bundle's whole purpose is that the derived research can be reproduced by
someone without the game. So these check the properties that claim depends on:
that what comes out is what went in, that corruption is detected rather than
extracted, and that the bundle cannot silently stop covering the tools that read
it.

They run against the committed bundle where that is the point, and against
fixtures where the failure has to be induced.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.bb_inputs import (  # noqa: E402
    PARAM_ALLOWLIST,
    SOURCES,
    check_coverage,
    extract,
    referenced_csvs,
    verify,
)

BUNDLE = REPO / "research" / "bb_inputs.db"


def make_bundle(path: Path, files: dict[str, bytes]) -> None:
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE files (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                            size INTEGER NOT NULL, blob BLOB NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    for name, data in files.items():
        db.execute("INSERT INTO files VALUES (?,?,?,?)",
                   (name, hashlib.sha256(data).hexdigest(), len(data), zlib.compress(data)))
    db.execute("INSERT INTO meta VALUES ('schema_version','1')")
    db.commit()
    db.close()


@unittest.skipUnless(BUNDLE.exists(), "the committed bundle is missing")
class CommittedBundleTests(unittest.TestCase):
    def test_it_verifies(self):
        self.assertEqual(verify(BUNDLE), 0)

    def test_it_covers_every_param_the_tools_read(self):
        self.assertEqual(check_coverage(BUNDLE), 0)

    def test_the_allowlist_and_the_tools_agree(self):
        """If a tool starts reading a new param, this is what notices."""
        self.assertEqual(referenced_csvs() - PARAM_ALLOWLIST, set())

    def test_it_carries_all_three_source_groups(self):
        db = sqlite3.connect(BUNDLE)
        prefixes = {path.split("/", 1)[0] for (path,) in db.execute("SELECT path FROM files")}
        db.close()
        self.assertEqual(prefixes, {s.prefix for s in SOURCES})

    def test_extraction_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            self.assertEqual(extract(BUNDLE, target), 0)
            db = sqlite3.connect(BUNDLE)
            rows = db.execute("SELECT path, sha256, size FROM files").fetchall()
            db.close()
            self.assertTrue(rows)
            for path, sha, size in rows:
                on_disk = (target / path).read_bytes()
                self.assertEqual(len(on_disk), size, path)
                self.assertEqual(hashlib.sha256(on_disk).hexdigest(), sha, path)

    def test_the_lot_param_is_present_and_looks_like_a_param_table(self):
        from tools.bb_inputs import connect
        db = connect(BUNDLE)
        row = db.execute("SELECT blob FROM files WHERE path = 'params/ItemLotParam.csv'").fetchone()
        db.close()
        self.assertIsNotNone(row, "the bundle exists to carry this file above all")
        header = zlib.decompress(row[0]).split(b"\n", 1)[0].decode("utf-8-sig")
        self.assertIn("ID", header.split(","))
        self.assertTrue(any(c.startswith("lotItemId") for c in header.split(",")))


class CorruptionTests(unittest.TestCase):
    """A bundle that hands back the wrong bytes must say so, not hand them back."""

    def test_a_tampered_blob_is_caught_by_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.db"
            make_bundle(path, {"params/X.csv": b"ID,name\n1,two\n"})
            db = sqlite3.connect(path)
            db.execute("UPDATE files SET blob = ?", (zlib.compress(b"different"),))
            db.commit(); db.close()
            self.assertEqual(verify(path), 1)

    def test_extraction_refuses_a_tampered_blob(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.db"
            make_bundle(path, {"params/X.csv": b"ID,name\n1,two\n"})
            db = sqlite3.connect(path)
            db.execute("UPDATE files SET blob = ?", (zlib.compress(b"different"),))
            db.commit(); db.close()
            with self.assertRaises(SystemExit):
                extract(path, Path(tmp) / "out")

    def test_a_missing_bundle_explains_itself(self):
        with self.assertRaises(SystemExit) as caught:
            verify(Path("/nonexistent/nope.db"))
        self.assertIn("--build", str(caught.exception))


class CoverageGateTests(unittest.TestCase):
    def test_coverage_fails_when_a_referenced_param_is_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "b.db"
            make_bundle(path, {"params/EquipParamGoods.csv": b"ID\n1\n"})
            self.assertEqual(check_coverage(path), 1)

    def test_the_gate_reads_the_tools_rather_than_a_hardcoded_list(self):
        """It has to notice a new param, so it must derive the set from source."""
        found = referenced_csvs()
        self.assertIn("ItemLotParam.csv", found)
        self.assertIn("SpEffectParam.csv", found)


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPO / "tools" / "bb_inputs.py"), *args],
                              capture_output=True, text=True, encoding="utf-8", cwd=REPO)

    @unittest.skipUnless(BUNDLE.exists(), "the committed bundle is missing")
    def test_get_streams_one_file_without_extracting(self):
        result = self.run_cli("--get", "params/EquipParamGoods.csv")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ID", result.stdout.split("\n", 1)[0])

    @unittest.skipUnless(BUNDLE.exists(), "the committed bundle is missing")
    def test_get_on_an_unknown_path_fails_usefully(self):
        result = self.run_cli("--get", "params/NotAThing.csv")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--list", result.stderr)

    def test_an_action_is_required(self):
        self.assertNotEqual(self.run_cli().returncode, 0)


if __name__ == "__main__":
    unittest.main()
