import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_living_failures_contract import (
    ARENA_HASHES,
    BSB_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    LIVING_FAILURES_SOURCE,
    BsbLivingFailuresIds,
    native_plan_bsb_at_living_failures,
    patch_bsb_at_living_failures,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbLivingFailuresContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = (
            read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        cls.failures = (
            read_blob(BUNDLE, LIVING_FAILURES_SOURCE)
            .decode("utf-8-sig")
            .replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_visible_primary_and_proxy_bridge_preserve_the_terminal(self):
        before = event_blocks(self.failures)
        after = event_blocks(patch_bsb_at_living_failures(self.failures, self.bsb))
        self.assertEqual(before[13501850], after[13501850])
        self.assertIn("WaitFor(HPRatio(3500850) == 0);", after[13501850])
        health = after[13504852]
        self.assertIn("DisplayBossHealthBar(Enabled, 3500851, 0, 209000);", health)
        self.assertNotIn("CreateReferredDamagePair", health)
        bridge = after[DEFAULT_IDS.death_to_proxy]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(3500851));"),
            bridge.index("ForceCharacterDeath(3500850, false);"),
        )
        self.assertIn("EndIf(EventFlag(13501850));", bridge)

    def test_living_failures_entry_fog_retry_and_coop_bodies_are_retained(self):
        before = event_blocks(self.failures)
        after = event_blocks(patch_bsb_at_living_failures(self.failures, self.bsb))
        self.assertEqual(before[13501852], after[13501852])
        for event in (13504850, 13504851, 13504855, 13504856, 13504857):
            self.assertEqual(before[event], after[event], event)
        entry = after[13501851]
        self.assertIn("WaitFor(", entry)
        self.assertIn("SetEventFlag(13504858, ON);", entry)
        self.assertNotIn("ForceAnimationPlayback(3500851", entry)
        self.assertNotIn("RequestCharacterAIReplan(3500851);", entry)

    def test_wave_generator_and_support_controllers_are_retired_without_early_death(
        self,
    ):
        after = event_blocks(patch_bsb_at_living_failures(self.failures, self.bsb))
        for event in (
            13504865,
            13504880,
            13504881,
            13504885,
            13504890,
            13504895,
            13505655,
            13505656,
            13505661,
            13505662,
            13505680,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1], event)
        retire = after[DEFAULT_IDS.retire_helpers]
        for generator in range(3503814, 3503818):
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", retire)
        wait = retire.index("WaitFor(EventFlag(13501850));")
        for actor in (3500852, 3500853, 3500854, 3500860):
            self.assertIn(f"ChangeCharacterEnableState({actor}, Disabled);", retire)
            self.assertGreater(
                retire.rindex(f"ForceCharacterDeath({actor}, false);"), wait
            )

    def test_bsb_music_camera_and_phases_are_destination_bound(self):
        after = event_blocks(patch_bsb_at_living_failures(self.failures, self.bsb))
        self.assertIn("SetMapSoundState(3503812, Disabled);", after[13504853])
        self.assertIn("InArea(10000, 3502812)", after[13504853])
        self.assertIn("EventFlag(12991801)", after[13504853])
        self.assertIn("SetLockcamSlotNumber(35, 0, 1);", after[13504854])
        self.assertNotIn("SetLockcamSlotNumber(23,", after[13504854])
        self.assertEqual(2, after[13504854].count("EndIf(EventFlag(13501850));"))
        self.assertLess(
            after[13504854].index("EndIf(EventFlag(13501850));"),
            after[13504854].index("WaitFor("),
        )
        self.assertLess(
            after[13504854].rindex("EndIf(EventFlag(13501850));"),
            after[13504854].index("SetLockcamSlotNumber"),
        )
        self.assertIn("HPRatio(3500851) < 0.67", after[DEFAULT_IDS.phase_one])
        self.assertIn(
            "HPRatio(3500851) < 0.33 && EventFlag(12991800)",
            after[DEFAULT_IDS.phase_two],
        )
        copied = "\n".join(
            after[event]
            for event in (13504852, 13504853, 13504854, *DEFAULT_IDS.values())
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:123|230)\d+(?!\d)")

    def test_maria_and_noncombat_constructor_lines_remain_exact(self):
        before = event_blocks(self.failures)
        after = event_blocks(patch_bsb_at_living_failures(self.failures, self.bsb))
        for event in (
            13501800,
            13501801,
            13501802,
            13501803,
            13504800,
            13504801,
            13504802,
            13504803,
            13504804,
            13504805,
            13504806,
            13504807,
            13504822,
        ):
            self.assertEqual(before[event], after[event], event)
        remove = re.compile(r"\n    \$InitializeEvent\(0, 129918(?:00|01|02|03)\);")
        self.assertEqual(before[0], remove.sub("", after[0]))

    def test_native_plan_uses_visible_body_and_pins_every_retained_helper(self):
        plan = native_plan_bsb_at_living_failures(
            self.slots, self.npcs, self.effects, "living-failures"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(
            3500851,
            plan["swaps"][0]["destinations"][plan["swaps"][0]["destination_keys"][0]][
                "entity_id"
            ],
        )
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual("c4030_0000", binding["destination_part"])
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(
            {3500850, 3500852, 3500853, 3500854, 3500860},
            {row["entity_id"] for row in retained},
        )
        for row in retained:
            self.assertRegex(row["source_provenance"]["part_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(plan["scaling"]["enabled"])

    def test_ids_and_pinned_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "129918xx"):
            patch_bsb_at_living_failures(
                self.failures,
                self.bsb,
                replace(DEFAULT_IDS, phase_two=DEFAULT_IDS.phase_one),
            )
        with self.assertRaisesRegex(ValueError, "BSB donor"):
            patch_bsb_at_living_failures(
                self.failures,
                self.bsb.replace(
                    "HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "Living Failures arena"):
            patch_bsb_at_living_failures(
                self.failures.replace(
                    "HandleBossDefeat(3500850)", "HandleBossDefeat(7)"
                ),
                self.bsb,
            )


if __name__ == "__main__":
    unittest.main()
