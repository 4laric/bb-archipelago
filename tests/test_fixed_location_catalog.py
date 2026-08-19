from __future__ import annotations

import csv
import unittest
from pathlib import Path

from worlds.bloodborne import LOCATION_ID_BY_KEY, build_runtime_slot_data
from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS


ROOT = Path(__file__).resolve().parents[1]


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class FixedLocationCatalogTests(unittest.TestCase):
    def test_selected_rows_are_exact_catalog_rows_with_item_evidence(self):
        catalog = {
            int(row["location_flag"]): row
            for row in rows(ROOT / "research/catalog/fixed_location_catalog.tsv")
        }
        items = rows(ROOT / "research/catalog/fixed_location_items.tsv")
        event_refs = rows(ROOT / "research/joined/fixed_location_event_refs.tsv")

        for selected in FIXED_LOCATIONS:
            source = catalog[selected.event_flag]
            self.assertEqual("m24_01_00_00", source["canonical_map"])
            self.assertIn(str(selected.item_lot_id), source["item_lot_ids"].split(";"))
            self.assertEqual(selected.classification, source["classification"])
            self.assertEqual(selected.source_ref, source["map_variants"])
            self.assertTrue(any(
                row["location_flag"] == str(selected.event_flag)
                and row["item_lot_id"] == str(selected.item_lot_id)
                and row["category"] == str(selected.item_category)
                and row["item_param_id"] == str(selected.item_id)
                for row in items
            ))
            self.assertTrue(any(
                row["acquisition_flag"] == str(selected.event_flag)
                and row["item_lot_id"] == str(selected.item_lot_id)
                for row in event_refs
            ))

    def test_canary_is_the_live_validated_bullet_lot(self):
        canary = next(
            row for row in FIXED_LOCATIONS
            if row.key == "fixed_iosefka_courtyard_bullets"
        )
        self.assertEqual(2410800, canary.item_lot_id)
        self.assertEqual(52410800, canary.event_flag)
        self.assertFalse(canary.vanilla_award_suppressed)

    def test_every_selected_location_has_a_stable_id_and_wire_binding(self):
        slot_data = build_runtime_slot_data()
        wire = slot_data["runtime_locations"]
        ids = []
        for location in FIXED_LOCATIONS:
            ap_id = LOCATION_ID_BY_KEY[location.key]
            ids.append(ap_id)
            self.assertEqual(location.event_flag, wire[str(ap_id)]["event_flag"])
            self.assertEqual(
                location.vanilla_award_suppressed,
                wire[str(ap_id)]["vanilla_award_suppressed"],
            )
        self.assertEqual(len(ids), len(set(ids)))

    def test_selected_location_names_and_flags_are_unique(self):
        self.assertEqual(len(FIXED_LOCATIONS), len({row.name for row in FIXED_LOCATIONS}))
        self.assertEqual(len(FIXED_LOCATIONS), len({row.event_flag for row in FIXED_LOCATIONS}))


if __name__ == "__main__":
    unittest.main()
