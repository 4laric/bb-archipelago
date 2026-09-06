"""worlds/bloodborne/probe_marks.py: the client's /mark console command helper."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from worlds.bloodborne.probe_marks import append_mark, read_marks


class AppendMarkTests(unittest.TestCase):
    def test_a_mark_is_written_as_one_jsonl_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            record = append_mark(path, "control", now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc))
            self.assertEqual("mark", record["kind"])
            self.assertEqual("control", record["label"])
            self.assertEqual("2026-09-06T00:00:00+00:00", record["at"])
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(1, len(lines))
            self.assertEqual(record, json.loads(lines[0]))

    def test_marks_append_across_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            append_mark(path, "one", now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc))
            append_mark(path, "two", now=lambda: datetime(2026, 9, 6, 0, 0, 5, tzinfo=timezone.utc))
            self.assertEqual(2, len(path.read_text(encoding="utf-8").splitlines()))

    def test_an_empty_label_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            with self.assertRaises(ValueError):
                append_mark(path, "   ")
            self.assertFalse(path.exists(), "a refused mark must not create the file")

    def test_a_missing_parent_directory_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "marks.jsonl"
            append_mark(path, "x", now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc))
            self.assertTrue(path.exists())


class ReadMarksTests(unittest.TestCase):
    def test_reads_back_every_written_mark(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            append_mark(path, "a", now=lambda: datetime(2026, 9, 6, tzinfo=timezone.utc))
            append_mark(path, "b", now=lambda: datetime(2026, 9, 6, 0, 0, 1, tzinfo=timezone.utc))
            marks = read_marks(path)
            self.assertEqual(["a", "b"], [m["label"] for m in marks])

    def test_a_missing_file_reads_as_no_marks(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(0, len(read_marks(Path(directory) / "absent.jsonl")))

    def test_a_blank_or_corrupt_line_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            path.write_text('{"kind": "mark", "label": "a", "at": "x"}\n\nnot json\n',
                             encoding="utf-8")
            self.assertEqual(1, len(read_marks(path)))

    def test_a_non_mark_line_is_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "marks.jsonl"
            path.write_text('{"kind": "other"}\n', encoding="utf-8")
            self.assertEqual(0, len(read_marks(path)))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
