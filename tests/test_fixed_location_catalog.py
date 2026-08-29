from __future__ import annotations

import csv
import unittest
from pathlib import Path

from worlds.bloodborne import (
    LOCATION_ID_BY_KEY,
    SUPPRESSION_MANIFEST_FORMAT,
    SUPPRESSION_PLAN_SHA256,
    build_runtime_slot_data,
)
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

        from tools.build_fixed_location_slice import SLICE_MAPS

        seen_maps = set()
        for selected in FIXED_LOCATIONS:
            source = catalog[selected.event_flag]
            self.assertIn(source["canonical_map"], SLICE_MAPS)
            seen_maps.add(source["canonical_map"])
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
        # Witness: the loop above covered every slice map, not just the first.
        self.assertEqual(seen_maps, set(SLICE_MAPS))

    def test_canary_is_the_live_validated_bullet_lot(self):
        canary = next(
            row for row in FIXED_LOCATIONS
            if row.key == "fixed_iosefka_courtyard_bullets"
        )
        self.assertEqual(2410800, canary.item_lot_id)
        self.assertEqual(52410800, canary.event_flag)
        self.assertTrue(canary.vanilla_award_suppressed)

    def test_every_seeded_map_contributes_checks(self):
        from collections import Counter
        counts = Counter(row.region for row in FIXED_LOCATIONS)
        self.assertEqual(counts["Cathedral Ward"], 61)   # 59 m24_00 + the two Oedon strip rows
        self.assertEqual(counts["Old Yharnam"], 54)
        self.assertEqual(counts["Central Yharnam"], 47)
        self.assertEqual(counts["Iosefka's Clinic"], 2)
        self.assertEqual(counts["Hemwick Charnel Lane"], 32)
        self.assertEqual(counts["Castle Cainhurst"], 26)

    def test_manifest_is_the_complete_first_cycle_map_slice(self):
        from tools.build_fixed_location_slice import (
            EXCLUDED_FLAGS,
            REPLACEMENT_FLAGS,
            build_rows,
        )

        # Prior 222 rows plus 80 Forbidden Woods rows.
        self.assertEqual(302, len(FIXED_LOCATIONS))
        self.assertEqual(
            [row.__dict__ for row in FIXED_LOCATIONS],
            [
                {
                    "key": row["key"],
                    "name": row["name"],
                    "region": row["region"],
                    "event_flag": int(row["location_flag"]),
                    "item_lot_id": int(row["item_lot_id"]),
                    "item_category": int(row["item_category"]),
                    "item_id": int(row["item_id"]),
                    "classification": row["classification"],
                    "source_kind": row["source_kind"],
                    "source_ref": row["source_ref"],
                    "vanilla_award_suppressed": row["vanilla_award_suppressed"] == "True",
                }
                for row in build_rows(ROOT)
            ],
        )
        selected_flags = {row.event_flag for row in FIXED_LOCATIONS}
        self.assertTrue(selected_flags.isdisjoint(REPLACEMENT_FLAGS))
        # Every replacement collapses onto a row that is either shipped here or
        # deliberately excluded (52400480 ships from data.py under its own key).
        self.assertTrue(set(REPLACEMENT_FLAGS.values()) <= selected_flags | set(EXCLUDED_FLAGS))

    def test_every_selected_location_has_a_stable_id_and_wire_binding(self):
        from worlds.bloodborne import NETWORK_LOCATIONS
        slot_data = build_runtime_slot_data()
        wire = slot_data["runtime_locations"]
        seeded = {location.key for location in NETWORK_LOCATIONS}
        ids = []
        for location in FIXED_LOCATIONS:
            ap_id = LOCATION_ID_BY_KEY[location.key]
            ids.append(ap_id)
            # Rows the bounded slice does not seed (today: the clinic
            # back-yard pair, #124) keep their permanent id but get no wire
            # binding — the client only tracks flags for checks in the seed.
            if location.key not in seeded:
                continue
            self.assertEqual(location.event_flag, wire[str(ap_id)]["event_flag"])
            self.assertEqual(
                location.vanilla_award_suppressed,
                wire[str(ap_id)]["vanilla_award_suppressed"],
            )
        self.assertEqual(len(ids), len(set(ids)))

    def test_selected_location_names_and_flags_are_unique(self):
        self.assertEqual(len(FIXED_LOCATIONS), len({row.name for row in FIXED_LOCATIONS}))
        self.assertEqual(len(FIXED_LOCATIONS), len({row.event_flag for row in FIXED_LOCATIONS}))

    def test_suppression_claim_has_a_seed_owned_install_witness_contract(self):
        slot_data = build_runtime_slot_data()
        requirement = slot_data["suppression"]
        self.assertEqual(requirement["manifest_format"], SUPPRESSION_MANIFEST_FORMAT)
        self.assertEqual(requirement["plan_sha256"], SUPPRESSION_PLAN_SHA256)
        self.assertRegex(requirement["plan_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            requirement["required"],
            any(
                row["vanilla_award_suppressed"]
                for row in slot_data["runtime_locations"].values()
            ),
        )


if __name__ == "__main__":
    unittest.main()
