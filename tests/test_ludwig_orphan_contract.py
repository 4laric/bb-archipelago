import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.ludwig_orphan_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LUDWIG_SOURCE,
    ORPHAN_SOURCE,
    LudwigOrphanIds,
    native_plan_ludwig_at_orphan,
    patch_ludwig_at_orphan,
)
from tools.bb_enemizer.scaling import load_params


class LudwigOrphanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ludwig = read_blob(BUNDLE, LUDWIG_SOURCE).decode("utf-8-sig").replace(
            "\r\n", "\n"
        )
        cls.orphan = read_blob(BUNDLE, ORPHAN_SOURCE).decode("utf-8-sig").replace(
            "\r\n", "\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)

    def test_preserves_orphan_terminal_progression_and_shadow(self):
        before = event_blocks(self.orphan)
        after = event_blocks(patch_ludwig_at_orphan(self.orphan, self.ludwig))
        for event in (13601800, 13601801, 13601802, 13601803):
            self.assertEqual(before[event], after[event])
        self.assertIn("WaitFor(chr || chr2);", after[13601800])
        self.assertIn("3600802", after[13601802])
        self.assertEqual(set(before).union(DEFAULT_IDS.values()), set(after))

    def test_copies_normal_two_phase_graph_without_source_only_condition(self):
        after = event_blocks(patch_ludwig_at_orphan(self.orphan, self.ludwig))
        health = after[13604802]
        phase = after[DEFAULT_IDS.event_ids[13404825]]
        copied = "\n".join(
            after[event] for event in (*DEFAULT_IDS.event_ids.values(), 13604802)
        )
        self.assertIn("CreateReferredDamagePair(3600800, 3600801);", health)
        self.assertIn("ChangeCharacterEnableState(3600801, Disabled);", health)
        self.assertIn("ChangeCharacterEnableState(3600803, Disabled);", health)
        self.assertNotIn("13400999", copied)
        self.assertIn(
            "WarpCharacterAndCopyFloor(3600801, TargetEntityType.Character, 3600800, -1, 3600800);",
            phase,
        )
        self.assertIn("ChangeCharacterEnableState(3600801, Enabled);", phase)
        self.assertNotIn("3402900", phase)
        self.assertNotIn("3402806", phase)

    def test_replaces_destination_combat_but_preserves_fog_and_uses_destination_camera(self):
        before = event_blocks(self.orphan)
        after = event_blocks(patch_ludwig_at_orphan(self.orphan, self.ludwig))
        for event in (13604800, 13604801, 13604805):
            self.assertEqual(before[event], after[event])
        for event in (13604820, 13604830, 13604840, 13604850):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        self.assertIn("SetLockcamSlotNumber(36, 0, 1)", after[13604804])
        self.assertIn("SetLockcamSlotNumber(36, 0, 0)", after[13604804])
        self.assertNotIn("SetLockcamSlotNumber(34,", after[13604804])
        self.assertEqual(1, after[0].count("$InitializeEvent(0, 13604804);"))

    def test_cleanup_waits_for_original_completion_before_forcing_unused_bodies(self):
        after = event_blocks(patch_ludwig_at_orphan(self.orphan, self.ludwig))
        cleanup = after[DEFAULT_IDS.cleanup_event]
        wait = cleanup.index("WaitFor(EventFlag(13601800));")
        self.assertGreater(cleanup.index("ForceCharacterDeath(3600800, false);"), wait)
        self.assertGreater(cleanup.index("ForceCharacterDeath(3600801, false);"), wait)
        self.assertGreater(cleanup.index("ForceCharacterDeath(3600803, false);"), wait)
        self.assertNotIn("ForceCharacterDeath", after[13604802])
        self.assertNotIn("ForceCharacterDeath", after[DEFAULT_IDS.event_ids[13404825]])

    def test_ids_and_pins_fail_closed(self):
        collision = replace(DEFAULT_IDS, cleanup_event=12991420)
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_ludwig_at_orphan(self.orphan, self.ludwig, collision)
        with self.assertRaisesRegex(ValueError, "Ludwig donor"):
            patch_ludwig_at_orphan(
                self.orphan,
                self.ludwig.replace("HPRatio(3400800) < 0.9", "HPRatio(3400800) < 0.4", 1),
            )
        with self.assertRaisesRegex(ValueError, "Orphan arena"):
            patch_ludwig_at_orphan(
                self.orphan.replace("HandleBossDefeat(3600800)", "HandleBossDefeat(99)", 1),
                self.ludwig,
            )

    def test_native_plan_binds_two_existing_primary_actors_and_two_scaling_outcomes(self):
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_ludwig_at_orphan(self.slots, npcs, effects, "ludwig-orphan")
        self.assertEqual(2, plan["swap_count"])
        self.assertEqual(2, len(plan["swaps"]))
        self.assertEqual(["c4510", "c4510"], [row["target"]["model_name"] for row in plan["swaps"]])
        self.assertEqual([451000, 451001], [row["target"]["npc_param_id"] for row in plan["swaps"]])
        self.assertEqual(2, len(plan["primary_init_source_bindings"]))
        self.assertEqual(
            [3400800, 3400801],
            [row["source_entity_id"] for row in plan["primary_init_source_bindings"]],
        )
        self.assertEqual(
            [3600800, 3600801],
            [row["destination_entity_id"] for row in plan["primary_init_source_bindings"]],
        )
        self.assertEqual(1, plan["boss_contract"]["encounter_count"])
        self.assertEqual(2, plan["boss_contract"]["logical_swap_count"])
        accounted = plan["scaling"]["changes"] + plan["scaling"]["skips"]
        self.assertEqual(2, len(accounted))
        self.assertEqual(
            {row["logical_key"] for row in plan["swaps"]},
            {row["logical_key"] for row in accounted},
        )


if __name__ == "__main__":
    unittest.main()
