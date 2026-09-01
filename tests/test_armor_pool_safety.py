"""Fail-closed boundaries for admitting category-1 attire to the AP pool."""

from __future__ import annotations

import unittest
from pathlib import Path

from worlds.bloodborne.data import ATTIRE_ITEM_KEYS, SLICE_POOL_SUPPRESSION_KEYS
from worlds.bloodborne.runtime_bindings import (
    INFERRED_CATEGORY_1_EVIDENCE,
    ITEM_BINDINGS,
    RuntimeItemBinding,
    validate_runtime_item_binding,
)
from worlds.bloodborne.starting_attire import STARTING_ATTIRE_CATALOG


ROOT = Path(__file__).resolve().parents[1]


class ArmorPoolSafetyTests(unittest.TestCase):
    def test_every_catalog_piece_has_one_category_one_runtime_binding(self):
        expected_feed = {
            "head": "attire_head",
            "body": "attire_chest",
            "arms": "attire_hands",
            "legs": "attire_legs",
        }
        self.assertEqual(
            {piece.item_key for piece in STARTING_ATTIRE_CATALOG},
            ATTIRE_ITEM_KEYS,
        )
        for piece in STARTING_ATTIRE_CATALOG:
            with self.subTest(piece=piece.item_key):
                binding = ITEM_BINDINGS[piece.item_key]
                self.assertEqual(1, binding.item_category)
                self.assertEqual(0x10000000 | piece.protector_id,
                                 binding.normalized_item_id)
                self.assertEqual(0x90000000 | piece.protector_id,
                                 binding.raw_descriptor)
                self.assertEqual(INFERRED_CATEGORY_1_EVIDENCE,
                                 binding.descriptor_evidence)
                self.assertEqual(expected_feed[piece.slot], binding.feed_effect)
                self.assertIsNone(binding.reinforcement_level)
                validate_runtime_item_binding(piece.item_key, binding, 1)

    def test_category_one_validation_refuses_unsafe_shapes(self):
        good = dict(
            normalized_item_id=0x10002AF8,
            raw_descriptor=0x90002AF8,
            evidence="test fixture",
            item_category=1,
            descriptor_evidence=INFERRED_CATEGORY_1_EVIDENCE,
            feed_effect="attire_chest",
        )
        mutations = (
            {"raw_descriptor": 0x80002AF8},
            {"normalized_item_id": 0x10002AF9},
            {"descriptor_evidence": "goods_formula_observed"},
            {"feed_effect": "right_hand_weapon"},
            {"reinforcement_level": 0},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                validate_runtime_item_binding(
                    "unsafe_attire", RuntimeItemBinding(**(good | mutation)), 1)
        with self.assertRaises(ValueError):
            validate_runtime_item_binding("unsafe_attire", RuntimeItemBinding(**good), 2)

    def test_armor_does_not_trigger_global_natural_source_suppression(self):
        # Armor checks own suppression through their location bindings. Global
        # item suppression would also chase shops, duplicate lots, and NG-cycle
        # copies merely because the same wearable can arrive from AP.
        self.assertTrue(ATTIRE_ITEM_KEYS.isdisjoint(SLICE_POOL_SUPPRESSION_KEYS))

    def test_dlc_set_boundary_is_explicit_in_the_reviewed_contract(self):
        catalog_sets = {piece.set_key for piece in STARTING_ATTIRE_CATALOG}
        dlc_sets = {"old_hunter", "maria_hunter", "constable", "yamamura"}
        self.assertTrue(dlc_sets <= catalog_sets)
        self.assertEqual(4, len(dlc_sets))

    def test_armor_pool_design_contract_is_documented(self):
        text = (ROOT / "docs" / "ARMOR-POOL.md").read_text(encoding="utf-8")
        self.assertIn("must also require\n`include_dlc`", text)
        self.assertIn("Do not add every armor key to `POOL_SUPPRESSION_ITEM_KEYS`", text)
        self.assertIn("save, reload", text)


if __name__ == "__main__":
    unittest.main()
