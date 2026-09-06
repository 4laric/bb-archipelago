import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path
from worlds.bloodborne.attire import ATTIRE_CATALOG
from worlds.bloodborne.insight_armor import build_insight_armor_suppression

ROOT = Path(__file__).resolve().parents[1]

class InsightPlanTests(unittest.TestCase):
    def test_complete_census_and_npc_exclusion(self):
        rows = build_insight_armor_suppression({p.item_key for p in ATTIRE_CATALOG})
        self.assertEqual(len(rows), 80)
        self.assertEqual(len({r['row_id'] for r in rows}), 80)
        self.assertEqual({r['qwc_id'] for r in rows}, {5910, 5090, 5091, 6675})
    def test_only_items_in_pool_are_suppressed(self):
        self.assertEqual(len(build_insight_armor_suppression(set())), 0)
        keys = {p.item_key for p in ATTIRE_CATALOG if not p.dlc}
        rows = build_insight_armor_suppression(keys)
        self.assertEqual(len(rows), 60)
        self.assertNotIn(6675, {r['qwc_id'] for r in rows})

