"""Static, source-pinned Beast-Possessed Soul at the One Reborn boundary."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.chalice_beast_donors import BEAST_POSSESSED_SOUL
from tools.bb_enemizer.chalice_one_reborn import (
    BRIDGE, PRESERVED, patch_one_reborn, recipes,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.rom_one_reborn_contract import (
    ARENA_SOURCE, BUNDLE, RETIRED_EVENTS, STATES,
)
from tools.bb_enemizer.scaling import load_params


class OneRebornChaliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
        cls.source = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            slots_file = Path(directory) / "slots.tsv"
            slots_file.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(slots_file, fixed_maps_only=False)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_patch_preserves_terminal_and_retires_displaced_controllers(self):
        recipe, = recipes()
        self.assertEqual(recipe.key, ("the-one-reborn", "beast-possessed-soul"))
        before = event_blocks(self.arena)
        after = event_blocks(recipe.patch(self.arena, self.source))
        self.assertEqual(set(after), set(before) | {BRIDGE})
        for event in PRESERVED:
            self.assertEqual(after[event], before[event])
        for event in RETIRED_EVENTS:
            self.assertIn("EndEvent();", after[event])
            self.assertNotIn("RequestCharacterAICommand", after[event])
        self.assertIn("DisplayBossHealthBar(Enabled, 2800800, 0, 750000)", after[12804802])
        self.assertNotIn("CreateReferredDamagePair", after[12804802])
        self.assertNotIn("SetCharacterImmortality(2800800, Enabled)", after[12804802])
        self.assertIn("WaitFor(CharacterDead(2800800))", after[BRIDGE])
        self.assertIn("ForceCharacterDeath(2800803, false)", after[BRIDGE])
        self.assertIn("CharacterHasEventMessage(2800800, 500)", after[12804803])
        self.assertIn("EnableBossMapSound(2803803, Enabled)", after[12804803])
        for event in before:
            if event not in ({0, 12804802, 12804803, 12801802, 12801803} | set(RETIRED_EVENTS)):
                self.assertEqual(after[event], before[event])

    def test_native_plan_pins_two_actor_states_and_original_proxy(self):
        plan = recipes()[0].native_plan(self.slots, self.npcs, self.effects, "one-seed")
        self.assertEqual(plan["swap_count"], 1)
        self.assertEqual(plan["boss_contract"]["added_event_ids"], [BRIDGE])
        self.assertIn(12906806, event_blocks(self.source))
        self.assertEqual(len(plan["boss_contract"]["source_handlers"]), 0)
        self.assertEqual(len(plan["primary_init_source_bindings"]), 2)
        self.assertEqual({row["destination_map"] for row in plan["primary_init_source_bindings"]},
                         set(STATES))
        for row in plan["primary_init_source_bindings"]:
            self.assertEqual(row["source_provenance"]["part_sha256"],
                             BEAST_POSSESSED_SOUL.source_part_sha256)
            self.assertEqual(row["source_archetype"]["model_name"], "c7500")
        self.assertEqual(len(plan["boss_contract"]["retained_destination_helpers"]), 18)
        self.assertEqual(plan["scaling"]["skip_count"], 1)

    def test_source_and_destination_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "One Reborn arena"):
            patch_one_reborn(self.arena.replace("CreatePlaylog(238)", "CreatePlaylog(237)", 1),
                             self.source)
        witness = "SetCharacterInvincibility(chrEntityId, Enabled);"
        pinned = event_blocks(self.source)[12906806]
        self.assertIn(witness, pinned)
        start = self.source.index("$Event(12906806,")
        position = self.source.index(witness, start)
        self.assertLess(position, self.source.index("$Event(", start + 1))
        changed = (self.source[:position] +
                   "SetCharacterInvincibility(chrEntityId, Disabled);" +
                   self.source[position + len(witness):])
        with self.assertRaisesRegex(ValueError, "m29 combat handler"):
            patch_one_reborn(self.arena, changed)
        without_source = [row for row in self.slots
                          if row.map_name != BEAST_POSSESSED_SOUL.source_map]
        with self.assertRaisesRegex(ValueError, "exact Beast-Possessed Soul"):
            recipes()[0].native_plan(without_source, self.npcs, self.effects, "seed")


if __name__ == "__main__":
    unittest.main()
