from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.mine_esd_awards import Miner


SCRIPT = """
def t240001_x0():
    if EventFlag(7001) == 0:
        assert t240001_x1(lot1=12345)

def t240001_x1(lot1=_):
    AwardItemLot(lot1)

def t240001_x2():
    if not GetEventFlag(7002):
        AwardItemLotWithoutAnyMessages(22000)

def t240001_x3(lot2=_):
    AwardItemLot(lot2 + 5)
"""


class EsdAwardMinerTests(unittest.TestCase):
    def test_resolves_forwarded_lots_and_received_flag(self):
        rows = Miner("m24/t240001.py", SCRIPT).run()
        row = next(row for row in rows if row.item_lot == 12345)
        self.assertEqual((row.gate_flag, row.gate_sense), (7001, 0))
        self.assertEqual(row.resolution, "call_argument")

    def test_recognizes_no_message_variant_and_negated_gate(self):
        rows = Miner("t240001.py", SCRIPT).run()
        row = next(row for row in rows if row.item_lot == 22000)
        self.assertEqual((row.gate_flag, row.gate_sense), (7002, 0))

    def test_unbound_runtime_awards_are_retained(self):
        rows = Miner("t240001.py", SCRIPT).run()
        row = next(row for row in rows if row.function == "t240001_x3")
        self.assertIsNone(row.item_lot)
        self.assertIn("unresolved", row.resolution)

    def test_cli_refuses_an_empty_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run(
                [sys.executable, "tools/mine_esd_awards.py", "--root", temporary],
                cwd=ROOT, capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("no talk corpus", result.stderr)

    def test_cli_emits_review_only_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "t240001.py").write_text(SCRIPT, encoding="utf-8")
            output = root / "awards.tsv"
            result = subprocess.run(
                [sys.executable, "tools/mine_esd_awards.py", "--root", str(root),
                 "--output", str(output)], cwd=ROOT, capture_output=True, text=True,
            )
            with output.open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(rows)
        self.assertEqual({row["suppression_status"] for row in rows}, {"review_required"})


if __name__ == "__main__":
    unittest.main()
