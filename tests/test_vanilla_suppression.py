"""Tests for the vanilla-award suppression planner.

Two halves. The fixture tests prove each refusal branch fires, because a planner
that guesses is worse than one that stops: a wrong guess leaves the vanilla item
reachable and looks exactly like success.

The corpus tests run against the real committed research and pin what it
currently says, including the one item it refuses.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.plan_vanilla_suppression import build_plan, collect_lot_facts  # noqa: E402

PLACEHOLDER = {"goods_id": "1000", "name": "PLACEHOLDER", "quantity": 1}

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
        from tools.plan_vanilla_suppression import build_complete_plan
        cls.plan = build_complete_plan(REPO / "research", PLACEHOLDER)

    def test_the_slice_pool_item_can_be_suppressed(self):
        item_edits = [edit for edit in self.plan.edits if not edit.item_key.startswith("location:")]
        self.assertEqual(sorted(edit.item_key for edit in item_edits),
                         ["oedon_tomb_key", "saw_spear"])
        by_key = {edit.item_key: edit for edit in item_edits}
        self.assertEqual(by_key["saw_spear"].item_category, "0")

    def test_the_script_award_key_is_suppressed_on_its_flagless_lot(self):
        """The shape the automatic search cannot plan, planned deliberately.

        Lot 31000 is awarded by EMEVD (event 12411800 -> AwardItemLot) and has
        no acquisition flag, so both of the planner's refusal branches would
        have fired on it. The edit must exist, must name the real lot, and must
        carry the row's literal getItemFlagId rather than an invented flag --
        the writers compare that value against the params before touching them.
        """
        edits = [edit for edit in self.plan.edits if edit.item_key == "oedon_tomb_key"]
        self.assertEqual(1, len(edits))
        edit = edits[0]
        self.assertEqual(("4", "4000", "31000", "-1"),
                         (edit.item_category, edit.goods_id, edit.item_lot_id,
                          edit.acquisition_flag))
        self.assertEqual(0, edit.placements)  # script-awarded: no MSB or drop placement

    def test_a_stale_script_award_review_is_refused_rather_than_planned(self):
        """The declaration is checked against the corpus, not trusted.

        If another lot starts awarding the item, editing only the reviewed ones
        leaves the vanilla key reachable and the plan still looks green.
        """
        from dataclasses import replace
        from tools.plan_vanilla_suppression import Plan, plan_script_awards
        from worlds.bloodborne.runtime_bindings import SCRIPT_AWARD_SUPPRESSIONS

        declared = SCRIPT_AWARD_SUPPRESSIONS["oedon_tomb_key"]
        patched = replace(declared, unreferenced_lot_ids=())
        plan = Plan(placeholder=PLACEHOLDER)
        SCRIPT_AWARD_SUPPRESSIONS["oedon_tomb_key"] = patched
        try:
            plan_script_awards(plan, REPO / "research", set())
        finally:
            SCRIPT_AWARD_SUPPRESSIONS["oedon_tomb_key"] = declared
        self.assertEqual(["review_is_stale"], [r.problem for r in plan.refusals])
        self.assertEqual(0, len(plan.edits))
        self.assertIn("27100000", plan.refusals[0].detail)  # witness: the dropped row

    def test_the_reviewed_unreferenced_lot_is_reachable_from_nothing(self):
        """"Nothing reaches lot 27100000" is a census, so count the census.

        The declaration edits 31000 and leaves 27100000 alone. That is only
        safe while no committed source can award 27100000, and a test that
        asserted the absence without proving it looked at a populated corpus
        would pass on an empty read.
        """
        import csv
        rows = list(csv.DictReader(
            (REPO / "research/joined/fixed_enemy_drop_sources.tsv").open(encoding="utf-8"),
            delimiter="\t"))
        treasures = list(csv.DictReader(
            (REPO / "research/joined/fixed_treasure_lots.tsv").open(encoding="utf-8"),
            delimiter="\t"))
        self.assertGreater(len(rows), 1000)      # witness: the drop corpus is real
        self.assertGreater(len(treasures), 100)  # witness: the treasure corpus is real
        reachable = ({row["item_lot_id"] for row in rows}
                     | {row["item_lot_id"] for row in treasures})
        self.assertIn("2410100", reachable)      # witness: a known lot is found this way
        self.assertNotIn("27100000", reachable)

    def test_every_physical_pickup_and_award_group_can_be_suppressed(self):
        location_edits = [edit for edit in self.plan.edits if edit.item_key.startswith("location:")]
        # 421 manifest rows and five separately-published slice treasures,
        # minus Saw Spear's lot (already covered by the pool-item edit), plus 27
        # continuation rows in shared-acquisition-flag award groups.
        self.assertEqual(len(location_edits), 454)
        self.assertEqual(
            {edit.item_lot_id for edit in location_edits if "related_lot" in edit.item_key},
            {
                # Hunter Set (Central Yharnam)
                "2410611", "2410612", "2410613",
                # Top Hat and Black Church sets (Cathedral Ward)
                "2400121", "2400122", "2400123",
                "2400291", "2400292", "2400293",
                # Rumpled Yharnam set, and the m24_00 chest whose flag is
                # numbered in the m24_01 range
                "2400541", "2410580",
                # Charred Hunter Garb (Old Yharnam)
                "2300401", "2300402",
                # Executioner and Knight sets (Castle Cainhurst)
                "2501021", "2501022", "2501071", "2501072",
                # White Church and Graveguard sets (Forbidden Woods)
                "2700151", "2700152", "2700153", "2700411", "2700412",
                # Yahar'gul Black Hood set
                "2800521", "2800522", "2800523",
                # Lecture Building Student Uniform continuations
                "3200541", "3200731",
            },
        )

    def test_the_slice_plan_has_no_refusals(self):
        self.assertEqual([], self.plan.refusals)

    def test_every_pool_item_resolves_to_exactly_one_lot(self):
        lots = [e.item_lot_id for e in self.plan.edits]
        self.assertEqual(len(lots), len(set(lots)))

    def test_planned_flags_agree_with_the_runtime_bindings(self):
        """Two independent derivations of the same flag must not disagree."""
        from worlds.bloodborne import NETWORK_LOCATIONS
        from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS
        by_lot = {e.item_lot_id: e.acquisition_flag for e in self.plan.edits}
        checked = 0
        for location in NETWORK_LOCATIONS:
            binding = LOCATION_BINDINGS[location.key]
            if binding.item_lot_id is None:
                continue
            checked += 1
            self.assertEqual(int(by_lot[str(binding.item_lot_id)]), binding.event_flag,
                             f"{location.key}: planner and runtime_bindings disagree")
        # 421 in-slice fixed pickups plus five published treasures carry lots;
        # bosses and the skull interaction do not, and the
        # four unseeded-but-suppressed rows (clinic pair, post-Rom ribbon, and
        # the NG+-only lot 2410295 from #220) are not network locations, so
        # they are not iterated here.
        self.assertEqual(checked, 426)

    def test_the_unseeded_ng_plus_lot_is_still_suppressed(self):
        """#220 unseeded lot 2410295 but deliberately kept its plan edit.

        The corpse does spawn on NG+. If the edit were dropped, an NG+ player
        running an Archipelago seed would pick up a vanilla Bold Hunter's Mark
        from a pickup the multiworld does not know about. Suppression scope is
        wider than seed scope on purpose, and this is the third row in it.
        """
        by_lot = {e.item_lot_id: e for e in self.plan.edits}
        self.assertIn("2410295", by_lot)
        self.assertEqual("52410295", by_lot["2410295"].acquisition_flag)
        from worlds.bloodborne import NETWORK_LOCATIONS
        self.assertNotIn("fixed_central_yharnam_lot_2410295",
                         {location.key for location in NETWORK_LOCATIONS})

    def test_canonical_plan_digest_matches_the_runtime_contract(self):
        from tools.plan_vanilla_suppression import build_complete_plan, serialize_plan
        from worlds.bloodborne import SUPPRESSION_PLAN_SHA256

        plan = build_complete_plan(
            REPO / "research", {"goods_id": "1000", "name": "Blood Vial"}
        )
        digest = hashlib.sha256(serialize_plan(plan).encode("utf-8")).hexdigest()
        self.assertEqual(digest, SUPPRESSION_PLAN_SHA256)


if __name__ == "__main__":
    unittest.main()
