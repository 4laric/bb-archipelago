"""Tests for the vanilla-award suppression planner.

Two halves. The fixture tests prove each refusal branch fires, because a planner
that guesses is worse than one that stops: a wrong guess leaves the vanilla item
reachable and looks exactly like success.

The corpus tests run against the real committed research and pin what it
currently says, including the one item it refuses.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.plan_vanilla_suppression import build_plan, collect_lot_facts  # noqa: E402

PLACEHOLDER = {"goods_id": "1000", "name": "PLACEHOLDER"}

LOT_HEADER = ("item_lot_id\tlot_name\tslot\titem_category\titem_id\titem_param_name\t"
              "normalized_runtime_id\traw_runtime_descriptor\tquantity\tbase_points\t"
              "slot_acquisition_flag\tgeneric_acquisition_flag\tall_acquisition_flags")
TREASURE_HEADER = "map_path\tmap_name\titem_lot_id"
DROP_HEADER = "map_path\tmap_name\titem_lot_id"


def lot_row(lot: str, goods: str, *, slot_flag: str = "0", generic_flag: str = "0",
            name: str = "a lot") -> str:
    return (f"{lot}\t{name}\t01\t4\t{goods}\tparam\t0x4000\t0xB000\t1\t100\t"
            f"{slot_flag}\t{generic_flag}\t")


class FixtureBase(unittest.TestCase):
    def research(self, lots: list[str], treasures: list[str] = (),
                 drops: list[str] = ()) -> Path:
        tmp = Path(tempfile.mkdtemp())
        joined = tmp / "joined"
        joined.mkdir(parents=True)
        (joined / "lot_items.tsv").write_text("\n".join([LOT_HEADER, *lots]) + "\n",
                                              encoding="utf-8")
        (joined / "fixed_treasure_lots.tsv").write_text(
            "\n".join([TREASURE_HEADER, *treasures]) + "\n", encoding="utf-8")
        (joined / "fixed_enemy_drop_sources.tsv").write_text(
            "\n".join([DROP_HEADER, *drops]) + "\n", encoding="utf-8")
        return tmp

    def plan(self, item_goods, **kwargs):
        return build_plan(item_goods, self.research(**kwargs), PLACEHOLDER)


class HappyPathTests(FixtureBase):
    def test_a_single_lot_with_one_flag_plans_cleanly(self):
        plan = self.plan({"key": "4001"},
                         lots=[lot_row("100", "4001", generic_flag="50000001")])
        self.assertTrue(plan.ok)
        self.assertEqual(len(plan.edits), 1)
        edit = plan.edits[0]
        self.assertEqual((edit.item_lot_id, edit.acquisition_flag), ("100", "50000001"))

    def test_the_plan_carries_the_placeholder(self):
        plan = self.plan({"key": "4001"},
                         lots=[lot_row("100", "4001", generic_flag="50000001")])
        self.assertEqual(plan.placeholder, PLACEHOLDER)

    def test_placements_are_counted_across_both_sources(self):
        plan = self.plan({"key": "4001"},
                         lots=[lot_row("100", "4001", generic_flag="50000001")],
                         treasures=["m21.msb\tm21\t100", "m22.msb\tm22\t100"],
                         drops=["m23.msb\tm23\t100"])
        self.assertEqual(plan.edits[0].placements, 3)


class RefusalTests(FixtureBase):
    """Each of these is a way the edit would be wrong. None may be guessed past."""

    def test_no_lot_awards_the_item(self):
        plan = self.plan({"key": "9999"},
                         lots=[lot_row("100", "4001", generic_flag="50000001")])
        self.assertFalse(plan.ok)
        self.assertEqual(plan.refusals[0].problem, "no_lot")

    def test_several_lots_award_the_item(self):
        plan = self.plan({"key": "4001"}, lots=[
            lot_row("100", "4001", generic_flag="50000001"),
            lot_row("200", "4001", generic_flag="50000002"),
        ])
        self.assertFalse(plan.ok)
        self.assertEqual(plan.refusals[0].problem, "multiple_lots")
        self.assertIn("still satisfies", plan.refusals[0].detail)

    def test_a_lot_with_no_flag_is_refused(self):
        plan = self.plan({"key": "4001"}, lots=[lot_row("100", "4001")])
        self.assertFalse(plan.ok)
        self.assertEqual(plan.refusals[0].problem, "no_acquisition_flag")

    def test_minus_one_is_not_a_flag(self):
        """-1 and 0 both mean absent in these params; 2778 rows carry -1."""
        plan = self.plan({"key": "4001"},
                         lots=[lot_row("100", "4001", generic_flag="-1")])
        self.assertEqual(plan.refusals[0].problem, "no_acquisition_flag")

    def test_two_distinct_flags_on_one_lot_is_refused(self):
        plan = self.plan({"key": "4001"},
                         lots=[lot_row("100", "4001", slot_flag="50000001",
                                       generic_flag="50000002")])
        self.assertEqual(plan.refusals[0].problem, "flag_not_unique")

    def test_a_lot_awarding_several_rows_is_refused(self):
        plan = self.plan({"key": "4001"}, lots=[
            lot_row("100", "4001", generic_flag="50000001"),
            lot_row("100", "4002", generic_flag="50000001"),
        ])
        self.assertEqual(plan.refusals[0].problem, "multi_item_lot")

    def test_refusals_do_not_silently_become_edits(self):
        plan = self.plan({"good": "4001", "bad": "9999"},
                         lots=[lot_row("100", "4001", generic_flag="50000001")])
        self.assertEqual([e.item_key for e in plan.edits], ["good"])
        self.assertEqual([r.item_key for r in plan.refusals], ["bad"])


class LotFactTests(FixtureBase):
    def test_sibling_lots_are_reported(self):
        facts = collect_lot_facts(self.research(lots=[
            lot_row("100", "4001", generic_flag="50000001"),
            lot_row("200", "4001", generic_flag="50000002"),
        ]))
        self.assertEqual(facts["100"].other_lots_with_same_item, ["200"])

    def test_zero_and_minus_one_are_excluded_from_flags(self):
        facts = collect_lot_facts(self.research(lots=[
            lot_row("100", "4001", slot_flag="0", generic_flag="-1")]))
        self.assertEqual(facts["100"].acquisition_flags, [])


class RealCorpusTests(unittest.TestCase):
    """What the committed research actually says today."""

    @classmethod
    def setUpClass(cls):
        from tools.plan_vanilla_suppression import load_item_goods
        cls.plan = build_plan(load_item_goods(), REPO / "research", PLACEHOLDER)

    def test_nine_of_the_ten_pool_items_can_be_suppressed(self):
        self.assertEqual(len(self.plan.edits), 9)

    def test_tonsil_stone_is_refused_for_want_of_a_flag(self):
        """Lot 39000 is a Patches gift with generic_acquisition_flag -1.

        It can be suppressed, but it can never be *detected*, so it cannot be a
        check until some other signal is found for it.
        """
        refusals = {r.item_key: r for r in self.plan.refusals}
        self.assertEqual(set(refusals), {"tonsil_stone"})
        self.assertEqual(refusals["tonsil_stone"].problem, "no_acquisition_flag")

    def test_every_pool_item_resolves_to_exactly_one_lot(self):
        lots = [e.item_lot_id for e in self.plan.edits]
        self.assertEqual(len(lots), len(set(lots)))

    def test_planned_flags_agree_with_the_runtime_bindings(self):
        """Two independent derivations of the same flag must not disagree."""
        from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS
        by_item = {e.item_key: e.acquisition_flag for e in self.plan.edits}
        checked = 0
        for location_key, binding in LOCATION_BINDINGS.items():
            item_key = location_key.removeprefix("pickup_")
            if item_key not in by_item:
                continue
            checked += 1
            self.assertEqual(int(by_item[item_key]), binding.event_flag,
                             f"{location_key}: planner and runtime_bindings disagree")
        self.assertGreaterEqual(checked, 5, "the cross-check examined almost nothing")


if __name__ == "__main__":
    unittest.main()
