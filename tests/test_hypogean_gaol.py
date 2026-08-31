import json
import unittest
from pathlib import Path

from worlds.bloodborne.data import (
    ALTERNATE_GAOL_ENTRANCE_NAMES,
    ALTERNATE_GAOL_LOCATION_KEYS,
    ENTRANCES,
    ITEMS,
    LOCATIONS,
)
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS


ROOT = Path(__file__).resolve().parents[1]


class HypogeanGaolLogicTests(unittest.TestCase):
    def test_paarl_is_a_bound_optional_boss_check(self):
        locations = {location.key: location for location in LOCATIONS}
        paarl = locations["boss_darkbeast_paarl"]
        self.assertEqual("Graveyard of the Darkbeast", paarl.region)
        self.assertEqual("event_darkbeast_paarl_defeated", paarl.locked_item)
        self.assertEqual({"boss_darkbeast_paarl"}, set(ALTERNATE_GAOL_LOCATION_KEYS))
        self.assertEqual(12301700, LOCATION_BINDINGS[paarl.key].event_flag)

    def test_early_abduction_requires_bsb_but_late_route_does_not(self):
        entrances = {entrance.name: entrance for entrance in ENTRANCES}
        self.assertEqual(
            {"event_blood_starved_beast_defeated"},
            entrances["Snatcher abduction"].rule.referenced_items,
        )
        self.assertFalse(
            entrances["Blood Moon path to Hypogean Gaol"].rule.referenced_items
        )
        self.assertEqual(
            {"event_darkbeast_paarl_defeated"},
            entrances["Paarl's rear gate"].rule.referenced_items,
        )
        self.assertEqual(
            {
                "Snatcher abduction", "Blood Moon path to Hypogean Gaol",
                "Descent to Paarl", "Paarl's rear gate",
            },
            set(ALTERNATE_GAOL_ENTRANCE_NAMES),
        )

    def test_progression_snatcher_is_explicitly_preserved(self):
        policies = json.loads(
            (ROOT / "research/enemizer/slot_policy.json").read_text(encoding="utf-8")
        )
        policy = policies["m24_00_00_00:c2020_0000"]
        self.assertFalse(policy["randomize"])
        self.assertIn("guaranteed Snatcher", policy["reason"])
        self.assertIn("Hypogean Gaol progression", policy["reason"])

    def test_paarl_event_item_exists(self):
        events = {item.key for item in ITEMS}
        self.assertIn("event_darkbeast_paarl_defeated", events)


if __name__ == "__main__":
    unittest.main()
