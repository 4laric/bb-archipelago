"""The Cathedral Ward avatar's Beast rune award (bb-archipelago#388).

A Cathedral Ward enemy's death event hands out a Caryll rune directly. Neither
award lot carries an acquisition flag, so the fixed-treasure catalog never saw
the pickup and the acquisition-flag suppression pass could not reach it either:
the rune arrived in an AP seed as a vanilla drop.

These tests check the two halves of the fix against the committed corpus --
the check's witness is the event's own saved defeat flag, and both branches of
the event are suppressed -- rather than against the declaration that asserts
them.
"""

from __future__ import annotations

import csv
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCATION_KEY = "enemy_cathedral_ward_avatar"
DEFEAT_FLAG = 12400861
DEATH_EVENT = 12400860
ENTITY = 2400450
RUNE_LOT = 75002400
REPLACEMENT_LOT = 75002405


def _event_source() -> str:
    """The bundled EMEVD decompile, read through the inputs bundle."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "tools/bb_inputs.py", "--get", "event/m24_00_00_00.emevd.dcx.js"],
        cwd=ROOT, capture_output=True, check=True)
    return result.stdout.decode("utf-8")


def _lot_rows() -> dict[str, dict[str, str]]:
    with (ROOT / "research/joined/lot_items.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) > 1000, "witness: the lot corpus is real"
    return {row["item_lot_id"]: row for row in rows}


class DeathEventEvidenceTests(unittest.TestCase):
    """What the game's own script says, not what the declaration claims."""

    @classmethod
    def setUpClass(cls):
        cls.source = _event_source()
        match = re.search(
            r"\$Event\(%d, Default, function\(\) \{(.*?)\n\}\);" % DEATH_EVENT,
            cls.source, re.DOTALL)
        assert match is not None, "event %d not found in m24_00_00_00" % DEATH_EVENT
        cls.body = match.group(1)

    def test_the_witness_is_the_events_own_saved_defeat_flag(self):
        # Set once, on death; read back on a later load to disable the
        # character. That read-back is what makes it save-backed rather than
        # a session-local event-slot flag, and it is why an already-defeated
        # save reconciles the check instead of resending it.
        self.assertIn("SetEventFlag(%d, ON);" % DEFEAT_FLAG, self.body)
        self.assertIn("if (EventFlag(%d))" % DEFEAT_FLAG, self.body)
        self.assertIn("ChangeCharacterEnableState(%d, Disabled);" % ENTITY, self.body)

    def test_the_death_condition_names_no_killer(self):
        """Environmental and friendly kills must complete the check too."""
        self.assertIn("WaitFor(CharacterDead(%d));" % ENTITY, self.body)
        for excluded in ("CharacterDamagedBy", "AttackedBy", "KilledBy"):
            self.assertNotIn(excluded, self.body)

    def test_both_award_branches_are_accounted_for(self):
        self.assertIn("AwardItemLot(%d);" % RUNE_LOT, self.body)
        self.assertIn("AwardItemLot(%d);" % REPLACEMENT_LOT, self.body)
        self.assertEqual(2, self.body.count("AwardItemLot("))
        # The branch selector. It is read, never written, here or anywhere in
        # this map: the fix must not clear it.
        self.assertIn("if (!EventFlag(6333))", self.body)
        self.assertNotIn("SetEventFlag(6333", self.source)

    def test_the_defeat_flag_is_not_a_boss_flag(self):
        """A boss flag would already be modelled, and must not be reused."""
        from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

        boss_flags = {binding.event_flag for binding in LOCATION_BINDINGS.values()
                      if binding.source_kind == "boss_defeat"}
        self.assertGreater(len(boss_flags), 15)  # witness: the census is populated
        self.assertNotIn(DEFEAT_FLAG, boss_flags)
        self.assertNotIn("HandleBossDefeat", self.body)


class CheckAndSuppressionTests(unittest.TestCase):
    def test_the_check_is_seeded_in_the_cathedral_ward(self):
        from worlds.bloodborne import NETWORK_LOCATIONS
        from worlds.bloodborne.data import LOCATIONS, ONE_TIME_ENEMY_LOCATION_KEYS

        location = next(row for row in LOCATIONS if row.key == LOCATION_KEY)
        self.assertEqual("Cathedral Ward", location.region)
        self.assertTrue(location.vanilla_award_suppressed)
        # No rule: the entity stands in the m24_00 map body, in the same region
        # as every other m24_00 fixed pickup, and the death event is not gated
        # on any other flag.
        self.assertEqual((frozenset(),), location.rule.any_of)
        self.assertIn(LOCATION_KEY, {row.key for row in NETWORK_LOCATIONS})
        # Unlike hunter_yurie this check is not option-gated: its vanilla award
        # is replaced unconditionally, so gating it would delete the rune.
        self.assertNotIn(LOCATION_KEY, ONE_TIME_ENEMY_LOCATION_KEYS)

    def test_the_binding_detects_the_defeat_flag_and_no_lot(self):
        from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

        binding = LOCATION_BINDINGS[LOCATION_KEY]
        self.assertEqual(DEFEAT_FLAG, binding.event_flag)
        self.assertIsNone(binding.item_lot_flag)
        # Neither lot is a detection target, so naming one here would invite a
        # later reader to poll a flag that does not exist.
        self.assertIsNone(binding.item_lot_id)
        self.assertEqual("one_time_enemy", binding.source_kind)
        self.assertEqual(8, binding.item_category)
        self.assertEqual(102401, binding.item_id)

    def test_receiving_the_rune_elsewhere_cannot_complete_the_check(self):
        """The witness must be the encounter, never the item.

        An acquisition flag would fire on any copy of the rune, including one
        delivered by AP from another world. The declared witness is the death
        event's flag, and both award lots carry no acquisition flag at all.
        """
        from worlds.bloodborne.runtime_bindings import (
            EVENT_AWARD_SUPPRESSIONS, LOCATION_BINDINGS,
        )

        rows = _lot_rows()
        for declared in EVENT_AWARD_SUPPRESSIONS.values():
            with self.subTest(lot=declared.item_lot_id):
                row = rows[str(declared.item_lot_id)]
                self.assertEqual("-1", row["generic_acquisition_flag"])
                self.assertEqual("", (row["all_acquisition_flags"] or "").strip())
                self.assertEqual(DEFEAT_FLAG, declared.witness_flag)
        self.assertEqual(DEFEAT_FLAG, LOCATION_BINDINGS[LOCATION_KEY].event_flag)

    def test_both_branches_are_declared_against_the_real_param_rows(self):
        from worlds.bloodborne.runtime_bindings import EVENT_AWARD_SUPPRESSIONS

        rows = _lot_rows()
        declared = {row.item_lot_id: row for row in EVENT_AWARD_SUPPRESSIONS.values()}
        self.assertEqual({RUNE_LOT, REPLACEMENT_LOT}, set(declared))
        self.assertEqual((8, 102401),
                         (declared[RUNE_LOT].item_category, declared[RUNE_LOT].item_id))
        self.assertEqual((4, 1500), (declared[REPLACEMENT_LOT].item_category,
                                     declared[REPLACEMENT_LOT].item_id))
        for lot, entry in declared.items():
            with self.subTest(lot=lot):
                row = rows[str(lot)]
                self.assertEqual(str(entry.item_category), row["item_category"])
                self.assertEqual(str(entry.item_id), row["item_id"])
                # One item row per lot, so replacing the row cannot collaterally
                # suppress a second award.
                self.assertEqual("02", row["slot"])

    def test_the_planner_replaces_both_lots(self):
        from tools.plan_vanilla_suppression import build_complete_plan

        plan = build_complete_plan(ROOT / "research",
                                   {"goods_id": "1000", "name": "Blood Vial"})
        self.assertGreater(len(plan.edits), 700)  # witness: the plan is real
        by_lot = {edit.item_lot_id: edit for edit in plan.edits}
        for lot in (RUNE_LOT, REPLACEMENT_LOT):
            with self.subTest(lot=lot):
                edit = by_lot[str(lot)]
                self.assertEqual("-1", edit.acquisition_flag)
                self.assertTrue(edit.item_key.startswith("event:"))
                self.assertIn(str(DEFEAT_FLAG), edit.reason)
        # Nothing else in the 1024xx rune family was swept up: lot 27070's
        # Beast recipe 102402 is a separate NPC-death source with its own
        # acquisition flag and stays vanilla (#388 explicitly scopes it out).
        self.assertNotIn("27070", by_lot)

    def test_a_stale_declaration_is_refused_rather_than_planned(self):
        from dataclasses import replace

        from tools.plan_vanilla_suppression import Plan, plan_event_awards
        from worlds.bloodborne.runtime_bindings import EVENT_AWARD_SUPPRESSIONS

        key = "cathedral_ward_avatar_beast_rune"
        original = EVENT_AWARD_SUPPRESSIONS[key]
        plan = Plan(placeholder={"goods_id": "1000", "name": "Blood Vial", "quantity": 1})
        EVENT_AWARD_SUPPRESSIONS[key] = replace(original, item_id=999999)
        try:
            plan_event_awards(plan, ROOT / "research", set())
        finally:
            EVENT_AWARD_SUPPRESSIONS[key] = original
        self.assertEqual(["event_award_declaration_mismatch"],
                         [refusal.problem for refusal in plan.refusals])
        # The other branch is still planned, so the refusal is specific.
        self.assertEqual([str(REPLACEMENT_LOT)],
                         [edit.item_lot_id for edit in plan.edits])


class ApReplacementTests(unittest.TestCase):
    def test_the_rune_is_still_reachable_as_an_ap_item(self):
        from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
        from worlds.bloodborne.data import ITEMS

        award = next(row for row in CATEGORY8_AWARDS if row.source_lot_id == RUNE_LOT)
        self.assertEqual(102401, award.gemgen_id)
        self.assertIn(award.item_key, {item.key for item in ITEMS})

    def test_the_replacement_is_a_base_game_item(self):
        from worlds.bloodborne.data import DLC_ITEM_KEYS
        from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

        award = next(row for row in CATEGORY8_AWARDS if row.source_lot_id == RUNE_LOT)
        self.assertNotIn(award.item_key, DLC_ITEM_KEYS)


if __name__ == "__main__":
    unittest.main()
