import csv
import unittest
from collections import Counter
from pathlib import Path

from worlds.bloodborne.data import CENTRAL_YHARNAM_SLICE_ITEM_KEYS, MODEL
from worlds.bloodborne.model import ItemKind, Rule
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS
from worlds.bloodborne import (
    FULL_POOL_ITEM_KEYS,
    GOAL_LOCATION_KEY,
    ITEM_ID_BY_KEY,
    ITEM_NAME_TO_ID,
    LOCATION_ID_BY_KEY,
    LOCATION_NAME_TO_ID,
    NETWORK_LOCATIONS,
    SHUFFLABLE_ITEMS,
    build_item_pool_names,
    build_runtime_slot_data,
)

ROOT = Path(__file__).resolve().parents[1]


class BloodborneModelTests(unittest.TestCase):
    def test_model_references_are_valid(self):
        self.assertEqual([], MODEL.validate())

    def test_rule_dnf(self):
        rule = Rule.any(("a", "b"), ("c",))
        self.assertTrue(rule.allows({"a", "b"}))
        self.assertTrue(rule.allows({"c"}))
        self.assertFalse(rule.allows({"a"}))

    def test_runtime_item_bindings_cover_shufflable_items(self):
        expected = {item.key for item in SHUFFLABLE_ITEMS}
        self.assertTrue(expected <= set(ITEM_BINDINGS))

    def test_fixed_pickup_flags_cover_randomized_pickups(self):
        expected = {location.key for location in NETWORK_LOCATIONS}
        self.assertTrue(expected <= set(LOCATION_BINDINGS))
        self.assertTrue(all(LOCATION_BINDINGS[key].event_flag for key in expected))

    def test_slice_contains_the_map_and_two_bosses(self):
        # 49 in-slice fixed pickups + 2 bosses; the two clinic back-yard rows
        # (Iosefka's Clinic region) stay out of slice seeds until the world
        # grows the Amelia -> password chain (#124).
        self.assertEqual(51, len(NETWORK_LOCATIONS))
        self.assertEqual(12411700, LOCATION_BINDINGS["boss_cleric_beast"].event_flag)
        self.assertEqual(12411800, LOCATION_BINDINGS["boss_father_gascoigne"].event_flag)
        self.assertEqual("boss_father_gascoigne", GOAL_LOCATION_KEY)
        self.assertEqual(
            LOCATION_ID_BY_KEY[GOAL_LOCATION_KEY],
            build_runtime_slot_data()["goal_location"],
        )

    def test_slice_excludes_out_of_slice_fixed_rows(self):
        keys = {location.key for location in NETWORK_LOCATIONS}
        self.assertNotIn("fixed_central_yharnam_lot_2410140", keys)
        self.assertNotIn("fixed_central_yharnam_lot_2410640", keys)
        # The post-Gascoigne strip pickups stay in as Cathedral Ward checks.
        self.assertIn("fixed_blood_gem_workshop_tool", keys)
        self.assertIn("fixed_central_yharnam_lot_2410920", keys)

    def test_full_pool_places_every_validated_item_once_then_filler(self):
        counts = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
        for name in (
            "Hunter Chief Emblem",
            "Cainhurst Summons",
            "Tonsil Stone",
            "Upper Cathedral Key",
            "Orphanage Key",
            "Eye of a Blood-drunk Hunter",
            "Eye Pendant",
            "Astral Clocktower Key",
            "Celestial Dial",
            "Laurence's Skull",
            "Saw Spear",
            "Augur of Ebrietas",
        ):
            self.assertEqual(counts[name], 1, name)
        # 51 locations - 12 one-off items = 39 filler slots cycling five
        # names: first four get 8, the last gets 7.
        self.assertEqual(counts["Blood Vial"], 8)
        for name in (
            "Quicksilver Bullets x3",
            "Pebbles x3",
            "Molotov Cocktails x2",
        ):
            self.assertEqual(counts[name], 8, name)
        self.assertEqual(counts["Blood Stone Shards x2"], 7)

    def test_slice_pool_option_off_preserves_the_original_grant_shapes(self):
        """The grant shapes the first live sessions validated are unchanged.

        The two out-of-slice clinic rows (#124) shrink the location count to
        51, which only shifts the filler cycle: 51 - 2 one-off items = 49
        slots over five names, so the first four get 10 and the last gets 9.
        """
        counts = Counter(build_item_pool_names(CENTRAL_YHARNAM_SLICE_ITEM_KEYS))
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
        self.assertEqual(counts["Saw Spear"], 1)
        self.assertEqual(counts["Augur of Ebrietas"], 1)
        self.assertEqual(counts["Blood Vial"], 10)
        for name in (
            "Quicksilver Bullets x3",
            "Pebbles x3",
            "Molotov Cocktails x2",
        ):
            self.assertEqual(counts[name], 10, name)
        self.assertEqual(counts["Blood Stone Shards x2"], 9)
        slot_data = build_runtime_slot_data(CENTRAL_YHARNAM_SLICE_ITEM_KEYS)
        self.assertEqual(len(slot_data["runtime_items"]), 7)  # six slice items + Blood Vial

    def test_runtime_location_flags_are_specific_to_one_item_lot(self):
        """A short flag is valid; sharing one between lots is not."""
        with (ROOT / "research/joined/lot_items.tsv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        with (ROOT / "research/joined/fixed_treasure_lots.tsv").open(
                encoding="utf-8", newline="") as handle:
            placed_lots = {
                row["item_lot_id"] for row in csv.DictReader(handle, delimiter="\t")
                if row["item_lot_id"]
            }
        lots_by_flag = {}
        for row in rows:
            for flag in filter(None, row["all_acquisition_flags"].split(";")):
                lots_by_flag.setdefault(int(flag), set()).add(row["item_lot_id"])

        for location, binding in LOCATION_BINDINGS.items():
            if binding.item_lot_id is None:
                continue
            self.assertIn(binding.event_flag, lots_by_flag, location)
            lots = lots_by_flag[binding.event_flag]
            self.assertIn(str(binding.item_lot_id), lots, location)
            self.assertTrue(
                all(lot not in placed_lots for lot in lots - {str(binding.item_lot_id)}),
                f"{location}: acquisition flag is shared by another placed lot",
            )

        self.assertEqual({"3401810"}, lots_by_flag[9470])

    def test_runtime_location_provenance_matches_the_validation_census(self):
        """Evidence must describe the source row, not merely contain a plausible flag."""
        names_by_key = {location.key: location.name.rsplit(" - ", 1)[-1]
                        for location in MODEL.locations if not location.locked_item}
        with (ROOT / "research/validation/progression_items.tsv").open(
                encoding="utf-8", newline="") as handle:
            rows_by_name = {row["item_name"]: row for row in csv.DictReader(handle, delimiter="\t")}
        with (ROOT / "research/catalog/fixed_location_items.tsv").open(
                encoding="utf-8", newline="") as handle:
            catalog_items = list(csv.DictReader(handle, delimiter="\t"))
        with (ROOT / "research/catalog/fixed_location_catalog.tsv").open(
                encoding="utf-8", newline="") as handle:
            catalog_locations = {row["location_flag"]: row
                                 for row in csv.DictReader(handle, delimiter="\t")}

        for key, binding in LOCATION_BINDINGS.items():
            if binding.source_kind in ("boss_defeat", "interaction"):
                # Flag-only checks: no item lot to trace; the evidence string
                # must carry the flag itself.
                self.assertIsNone(binding.item_lot_id)
                self.assertIn(str(binding.event_flag), binding.evidence)
                continue
            if binding.source_kind == "script_award":
                row = rows_by_name[names_by_key[key]]
                self.assertIn(str(binding.item_lot_id), row["item_lot_ids"], key)
                self.assertIn(str(binding.event_flag), row["acquisition_flags"], key)
                self.assertIn(binding.source_kind, row["observed_sources"].split(";"), key)
                expected_ref = row["script_awards"]
            else:
                matches = [row for row in catalog_items
                           if row["location_flag"] == str(binding.event_flag)
                           and row["item_lot_id"] == str(binding.item_lot_id)
                           and row["category"] == str(binding.item_category)
                           and row["item_param_id"] == str(binding.item_id)]
                self.assertEqual(1, len(matches), key)
                expected_ref = catalog_locations[str(binding.event_flag)]["map_variants"]
            self.assertEqual(expected_ref, binding.source_ref, key)
            self.assertIn(str(binding.item_lot_id), binding.evidence, key)

    def test_progression_validation_covers_every_pool_item(self):
        from tools.validate_progression_items import EXPECTED
        validated_names = {name for name, _, _ in EXPECTED}
        pool_names = {
            item.name for item in MODEL.items
            if item.kind is ItemKind.PROGRESSION
        }
        self.assertEqual(set(), pool_names - validated_names)

    def test_hunter_chief_emblem_catalog_review_is_resolved(self):
        with (ROOT / "research/catalog/fixed_location_items.tsv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        emblem = next(row for row in rows if row["item_param_id"] == "4011")
        self.assertEqual("Hunter Chief Emblem", emblem["english_name"])
        self.assertEqual("0x40000FAB", emblem["normalized_runtime_id"])
        self.assertEqual("hunter_chief_emblem_validation", emblem["classification_reason"])

    def test_vertical_slice_ids_are_complete_and_disjoint(self):
        shufflable = {item.key for item in SHUFFLABLE_ITEMS}
        self.assertEqual(shufflable, set(ITEM_ID_BY_KEY))
        # Every model location has a permanent id (ids.tsv is append-only);
        # the datapackage map is restricted to what the slice seeds.
        self.assertTrue({location.key for location in NETWORK_LOCATIONS} <= set(LOCATION_ID_BY_KEY))
        self.assertEqual({location.name for location in NETWORK_LOCATIONS}, set(LOCATION_NAME_TO_ID))
        self.assertEqual(len(ITEM_NAME_TO_ID), len(shufflable) + 1)  # Blood Vial filler
        self.assertFalse(set(ITEM_NAME_TO_ID.values()) & set(LOCATION_ID_BY_KEY.values()))

    def test_region_progression_graph_is_acyclic(self):
        edges = {}
        for entrance in MODEL.entrances:
            edges.setdefault(entrance.source, set()).add(entrance.target)
        visiting = set()
        visited = set()

        def visit(region):
            self.assertNotIn(region, visiting, f"progression cycle at {region}")
            if region in visited:
                return
            visiting.add(region)
            for target in edges.get(region, ()):
                visit(target)
            visiting.remove(region)
            visited.add(region)

        for region in MODEL.regions:
            visit(region)

    def test_every_playable_region_contributes_a_location(self):
        populated = {location.region for location in MODEL.locations}
        self.assertEqual({"Menu"}, set(MODEL.regions) - populated)


if __name__ == "__main__":
    unittest.main()
