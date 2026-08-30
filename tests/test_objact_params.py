"""Ground-truth checks for the ObjActParam mine used by later-slice logic."""

from __future__ import annotations

import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "research" / "joined" / "objact_params.tsv"


def rows() -> dict[int, dict[str, str]]:
    with ARTIFACT.open(encoding="utf-8", newline="") as handle:
        return {int(row["row_id"]): row for row in csv.DictReader(handle, delimiter="\t")}


class ObjActParamTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_id = rows()

    def test_complete_table_population_is_witnessed(self):
        self.assertEqual(186, len(self.by_id))
        self.assertEqual(20, len(next(iter(self.by_id.values()))) - 2)

    def test_known_key_doors_name_their_goods(self):
        self.assertEqual("4000", self.by_id[2410080]["spQualifiedId"])
        self.assertEqual("4010", self.by_id[2400100]["spQualifiedId"])
        self.assertEqual("4006", self.by_id[2420020]["spQualifiedId"])
        for row_id in (2410080, 2400100, 2420020):
            self.assertEqual("1", self.by_id[row_id]["spQualifiedType"])

    def test_forbidden_woods_shortcuts_require_no_item(self):
        for row_id in (2700010, 2700030):
            self.assertEqual("0", self.by_id[row_id]["spQualifiedId"])
            self.assertEqual("0", self.by_id[row_id]["spQualifiedType"])

    def test_lecture_exits_are_free_but_the_interior_key_door_is_not(self):
        for row_id in (3200000, 3200001):
            self.assertEqual("0", self.by_id[row_id]["spQualifiedId"])
            self.assertEqual("0", self.by_id[row_id]["spQualifiedType"])
        self.assertEqual("4012", self.by_id[3200030]["spQualifiedId"])
        self.assertEqual("1", self.by_id[3200030]["spQualifiedType"])
