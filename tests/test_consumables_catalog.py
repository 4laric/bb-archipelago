from __future__ import annotations

import csv
import unittest
from pathlib import Path

from worlds.bloodborne.data import DLC_ITEM_KEYS, MODEL
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS


REPO = Path(__file__).resolve().parents[1]

CATALOG = {
    "hunters_mark": (100, 1),
    "blood_of_arianna": (701, 1),
    "blood_of_adella": (702, 1),
    "iosefkas_blood_vial": (703, 1),
    "blood_of_adeline": (706, 1),
    "delayed_molotov_cocktails": (1201, 2),
    "rope_molotov_cocktails": (1250, 2),
    "delayed_rope_molotov_cocktails": (1251, 2),
    "shining_coins": (1410, 5),
    "coldblood_dew_1": (1510, 1),
    "coldblood_dew_2": (1511, 1),
    "thick_coldblood_4": (1513, 1),
    "thick_coldblood_5": (1514, 1),
    "frenzied_coldblood_7": (1516, 1),
    "frenzied_coldblood_9": (1518, 1),
    "kin_coldblood_10": (1519, 1),
    "kin_coldblood_12": (1591, 1),
    "great_one_coldblood": (1592, 1),
    "old_great_one_coldblood": (1593, 1),
}


class ConsumablesCatalogTests(unittest.TestCase):
    def test_bindings_are_exact_bundled_goods_rows(self):
        with (REPO / "research/joined/goods_runtime_ids.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            params = {int(row["goods_param_id"]): row for row in csv.DictReader(handle, delimiter="\t")}
        items = {item.key: item for item in MODEL.items}
        for key, (param_id, quantity) in CATALOG.items():
            with self.subTest(key=key):
                self.assertIn(param_id, params)
                self.assertEqual(0x40000000 | param_id, ITEM_BINDINGS[key].normalized_item_id)
                self.assertEqual(0xB0000000 | param_id, ITEM_BINDINGS[key].raw_descriptor)
                self.assertEqual(quantity, items[key].quantity)
                self.assertLessEqual(quantity, int(params[param_id]["max_num"]))

    def test_only_old_hunters_goods_are_dlc_gated(self):
        expected = {
            "delayed_molotov_cocktails",
            "delayed_rope_molotov_cocktails",
            "blood_of_adeline",
        }
        self.assertEqual(expected, set(CATALOG) & DLC_ITEM_KEYS)

    def test_cut_revered_great_one_coldblood_stays_excluded(self):
        self.assertNotIn("revered_great_one_coldblood", ITEM_BINDINGS)
        self.assertNotIn(1594, {param for param, _ in CATALOG.values()})


if __name__ == "__main__":
    unittest.main()
