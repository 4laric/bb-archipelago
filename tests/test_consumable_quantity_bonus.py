"""Coverage for the `consumable_quantity_bonus` option (bb-archipelago#295).

The option adds a flat `+X` to the delivered quantity of the reviewed
consumable classification only. Default `0` must leave slot data untouched.
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from worlds.bloodborne import (
    FULL_POOL_ITEM_KEYS,
    ITEM_ID_BY_KEY,
    ITEM_NAME_TO_ID,
    FILLER_ITEM_NAME,
    STARTING_TOOL_KEYS,
    build_runtime_slot_data,
    consumable_delivery_quantity,
)
from worlds.bloodborne.data import CONSUMABLE_ITEM_KEYS, MODEL
from worlds.bloodborne.runtime_bindings import (
    CONSUMABLE_STACK_CAPS,
    DELIVERY_FIXTURES,
    ITEM_BINDINGS,
    MAX_GRANT_QUANTITY,
    validate_runtime_item_binding,
)

ROOT = Path(__file__).resolve().parents[1]
ITEMS_BY_KEY = {item.key: item for item in MODEL.items}
# `blood_vial` is the filler item rather than a MODEL row, so its descriptor
# lives in DELIVERY_FIXTURES; every other classified key is a pool item.
BINDINGS_BY_KEY = {**DELIVERY_FIXTURES, **ITEM_BINDINGS}
# Sentinels: named rows that must appear on each side of the classification, so
# a test that iterates the tables cannot pass by iterating nothing.
ELIGIBLE_SENTINELS = ("quicksilver_bullets", "fire_paper", "antidote", "coldblood_dew")
INELIGIBLE_SENTINELS = (
    "oedon_tomb_key",        # progression key
    "saw_cleaver",           # category-0 weapon
    "hunters_mark",          # isOnlyOne good
    "third_umbilical_cord_1",  # event/goal item
    "blood_stone_shards",    # reinforcement material, deliberately excluded
    "blood_of_arianna",      # named one-per-game blood vial
)


class ClassificationTests(unittest.TestCase):
    def test_sentinels_land_on_the_expected_side(self):
        for key in ELIGIBLE_SENTINELS:
            with self.subTest(key=key):
                self.assertIn(key, CONSUMABLE_ITEM_KEYS)
        for key in INELIGIBLE_SENTINELS:
            with self.subTest(key=key):
                self.assertIn(key, ITEM_BINDINGS, "sentinel must be a real item")
                self.assertNotIn(key, CONSUMABLE_ITEM_KEYS)

    def test_every_classified_key_has_a_stack_cap(self):
        self.assertGreater(len(CONSUMABLE_ITEM_KEYS), 30)
        self.assertEqual(set(CONSUMABLE_ITEM_KEYS), set(CONSUMABLE_STACK_CAPS))

    def test_every_classified_key_is_a_category_4_good(self):
        for key in sorted(CONSUMABLE_ITEM_KEYS):
            with self.subTest(key=key):
                self.assertIn(key, BINDINGS_BY_KEY)
                self.assertEqual(4, BINDINGS_BY_KEY[key].item_category)

    def test_caps_match_the_bundled_goods_rows(self):
        with (ROOT / "research/joined/goods_runtime_ids.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            params = {
                int(row["goods_param_id"]): row
                for row in csv.DictReader(handle, delimiter="\t")
            }
        self.assertIn(1000, params)  # witness: the joined table really parsed
        examined = 0
        for key, cap in sorted(CONSUMABLE_STACK_CAPS.items()):
            with self.subTest(key=key):
                param_id = BINDINGS_BY_KEY[key].normalized_item_id & 0x0FFFFFFF
                row = params[param_id]
                # Stackable and not a one-per-game good: the eligibility rule.
                self.assertEqual("0", row["is_only_one"])
                self.assertGreater(int(row["max_num"]), 1)
                self.assertEqual(int(row["max_num"]), cap)
                base = ITEMS_BY_KEY[key].quantity if key in ITEMS_BY_KEY else 1
                self.assertLessEqual(base, cap)
                examined += 1
        self.assertEqual(examined, len(CONSUMABLE_STACK_CAPS))


class DeliveryQuantityTests(unittest.TestCase):
    def test_bonus_is_flat_and_per_copy(self):
        self.assertEqual(5, consumable_delivery_quantity("quicksilver_bullets", 3, 2))
        self.assertEqual(4, consumable_delivery_quantity("fire_paper", 2, 2))
        self.assertEqual(3, consumable_delivery_quantity("blood_vial", 1, 2))

    def test_ineligible_keys_keep_their_quantity(self):
        for key in INELIGIBLE_SENTINELS:
            with self.subTest(key=key):
                self.assertEqual(1, consumable_delivery_quantity(key, 1, 20))

    def test_clamped_to_the_goods_stack_cap(self):
        # Lead Elixir's own maxNum is 3.
        self.assertEqual(3, CONSUMABLE_STACK_CAPS["lead_elixir"])
        self.assertEqual(3, consumable_delivery_quantity("lead_elixir", 1, 20))

    def test_clamped_to_the_grant_ceiling(self):
        self.assertEqual(99, MAX_GRANT_QUANTITY)
        # Coldblood Dew's cap is 99 and the option maxes at 20, so probe the
        # ceiling directly with an out-of-range bonus.
        self.assertEqual(99, consumable_delivery_quantity("coldblood_dew", 1, 500))


class SlotDataTests(unittest.TestCase):
    def _items(self, bonus: int) -> dict:
        return build_runtime_slot_data(
            FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS,
            consumable_quantity_bonus=bonus,
        )["runtime_items"]

    def test_default_leaves_slot_data_identical(self):
        baseline = build_runtime_slot_data(FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS)
        self.assertEqual(
            baseline,
            build_runtime_slot_data(
                FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS,
                consumable_quantity_bonus=0,
            ),
        )
        self.assertGreater(len(baseline["runtime_items"]), 100)

    def test_bonus_raises_only_eligible_rows(self):
        base = self._items(0)
        bonused = self._items(3)
        self.assertEqual(set(base), set(bonused))
        raised = set()
        for key in sorted(FULL_POOL_ITEM_KEYS):
            row_id = str(ITEM_ID_BY_KEY[key])
            before = base[row_id]["quantity"]
            after = bonused[row_id]["quantity"]
            with self.subTest(key=key):
                if key in CONSUMABLE_ITEM_KEYS:
                    cap = min(CONSUMABLE_STACK_CAPS[key], MAX_GRANT_QUANTITY)
                    self.assertEqual(min(before + 3, cap), after)
                    raised.add(key)
                else:
                    self.assertEqual(before, after)
        # Witness: the loop really did examine eligible rows.
        for key in ELIGIBLE_SENTINELS:
            self.assertIn(key, raised)

    def test_filler_blood_vial_row_takes_the_bonus(self):
        row_id = str(ITEM_NAME_TO_ID[FILLER_ITEM_NAME])
        self.assertEqual(1, self._items(0)[row_id]["quantity"])
        self.assertEqual(4, self._items(3)[row_id]["quantity"])

    def test_sustain_award_is_never_bonused(self):
        slot_data = build_runtime_slot_data(
            FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS, consumable_quantity_bonus=20)
        self.assertEqual(1, slot_data["sustain_item"]["quantity"])

    def test_bonused_rows_still_pass_binding_validation(self):
        checked = 0
        for bonus in (0, 1, 20):
            items = build_runtime_slot_data(
                FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS,
                consumable_quantity_bonus=bonus,
            )["runtime_items"]
            for key in sorted(FULL_POOL_ITEM_KEYS):
                quantity = items[str(ITEM_ID_BY_KEY[key])]["quantity"]
                validate_runtime_item_binding(key, ITEM_BINDINGS[key], quantity)
                checked += 1
        self.assertEqual(checked, 3 * len(FULL_POOL_ITEM_KEYS))

    def test_pool_identity_is_unchanged_by_the_bonus(self):
        base = build_runtime_slot_data(FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS)
        bonused = build_runtime_slot_data(
            FULL_POOL_ITEM_KEYS | STARTING_TOOL_KEYS, consumable_quantity_bonus=7)
        self.assertEqual(base["runtime_locations"], bonused["runtime_locations"])
        self.assertEqual(base["goal_location"], bonused["goal_location"])
        for row_id, row in base["runtime_items"].items():
            other = dict(bonused["runtime_items"][row_id])
            self.assertEqual(
                {k: v for k, v in row.items() if k != "quantity"},
                {k: v for k, v in other.items() if k != "quantity"},
            )


class OptionWiringTests(unittest.TestCase):
    def test_option_is_a_range_zero_to_twenty_and_is_in_the_dataclass(self):
        try:
            from worlds.bloodborne import BloodborneOptions, ConsumableQuantityBonus
        except ImportError:
            self.skipTest("requires an Archipelago checkout on sys.path")
        self.assertEqual(0, ConsumableQuantityBonus.default)
        self.assertEqual(0, ConsumableQuantityBonus.range_start)
        self.assertEqual(20, ConsumableQuantityBonus.range_end)
        # The world module uses postponed annotations, so the dataclass field
        # carries the class NAME rather than the class object.
        self.assertEqual(
            ConsumableQuantityBonus.__name__,
            BloodborneOptions.__annotations__["consumable_quantity_bonus"],
        )


if __name__ == "__main__":
    unittest.main()
