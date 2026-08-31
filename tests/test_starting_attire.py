from __future__ import annotations

import unittest
from pathlib import Path

from worlds.bloodborne.starting_attire import (
    SLOTS,
    STARTING_ATTIRE_CATALOG,
    build_starting_attire_choice,
)


class StartingAttireCatalogTests(unittest.TestCase):
    def test_catalog_contains_only_complete_coherent_sets(self):
        by_set = {}
        for piece in STARTING_ATTIRE_CATALOG:
            by_set.setdefault(piece.set_key, []).append(piece)
        self.assertGreaterEqual(len(by_set), 12)
        for pieces in by_set.values():
            self.assertEqual(SLOTS, tuple(piece.slot for piece in pieces))
            self.assertEqual(4, len({piece.protector_id for piece in pieces}))

    def test_selection_is_deterministic_and_seed_sensitive(self):
        first = build_starting_attire_choice("AP_TEST:1")
        self.assertEqual(first, build_starting_attire_choice("AP_TEST:1"))
        choices = {build_starting_attire_choice(f"AP_TEST:{n}")["set_key"] for n in range(20)}
        self.assertGreater(len(choices), 1)

    def test_selection_is_one_complete_set_of_category_one_grants(self):
        choice = build_starting_attire_choice("AP_TEST:1")
        self.assertEqual(set(SLOTS), set(choice["pieces"]))
        self.assertEqual(4, len(choice["grant_descriptors"]))
        self.assertTrue(all(value.startswith("1:") and value.endswith(":1")
                            for value in choice["grant_descriptors"]))

    def test_world_does_not_publish_or_activate_starting_attire_yet(self):
        world_source = (Path(__file__).parents[1] / "worlds" / "bloodborne" / "__init__.py").read_text(
            encoding="utf-8")
        self.assertNotIn("randomize_starting_attire", world_source)


if __name__ == "__main__":
    unittest.main()
