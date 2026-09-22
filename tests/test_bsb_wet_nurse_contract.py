import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_wet_nurse_contract import (
    BUNDLE,
    BSB_SOURCE,
    DEFAULT_IDS,
    WET_NURSE_SOURCE,
    BsbWetNurseIds,
    native_plan_bsb_at_wet_nurse,
    patch_bsb_at_wet_nurse,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbWetNurseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
        cls.nurse = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_direct_bsb_health_keeps_proxy_only_as_native_terminal_operand(self):
        before = event_blocks(self.nurse)
        after = event_blocks(patch_bsb_at_wet_nurse(self.nurse, self.bsb))
        health = after[12604802]
        self.assertIn("DisplayBossHealthBar(Enabled, 2600800, 0, 209000)", health)
        self.assertNotIn("CreateReferredDamagePair", health)
        self.assertNotIn("SetCharacterImmortality(2600800", health)
        self.assertIn("SetCharacterAIState(2600802, Disabled);", health)
        self.assertIn("SetCharacterHPBarDisplay(2600802, Disabled);", health)
        self.assertIn("SetCharacterAIState(2600801, Disabled);", health)
        self.assertIn("ChangeCharacterEnableState(2600801, Disabled);", health)
        self.assertIn("SetEventFlag(12604732, ON);", health)
        for actor in (2600800, 2600801, 2600802):
            self.assertIn(
                f"SetNetworkUpdateAuthority({actor}, AuthorityLevel.Forced);", health
            )
        self.assertEqual(before[12601800], after[12601800])
        self.assertEqual(before[12604804], after[12604804])
        self.assertIn("HandleBossDefeat(2600803);", after[12601800])
        self.assertIn("!CharacterDead(2600803)", after[12604804])

    def test_death_bridge_waits_for_real_bsb_death_before_terminating_proxy(self):
        after = event_blocks(patch_bsb_at_wet_nurse(self.nurse, self.bsb))
        bridge = after[DEFAULT_IDS.death_to_proxy]
        wait = bridge.index("WaitFor(CharacterDead(2600800));")
        kill = bridge.index("ForceCharacterDeath(2600802, false);")
        self.assertLess(wait, kill)
        self.assertIn("EndIf(EventFlag(12601800));", bridge[:wait])
        self.assertEqual(
            set(event_blocks(self.nurse)) | set(DEFAULT_IDS.values()), set(after)
        )

    def test_bsb_phase_and_music_use_direct_core_but_destination_arena_bindings(self):
        after = event_blocks(patch_bsb_at_wet_nurse(self.nurse, self.bsb))
        self.assertIn("HPRatio(2600800) < 0.67", after[DEFAULT_IDS.phase_one])
        self.assertIn(
            "HPRatio(2600800) < 0.33 && EventFlag(12991600)",
            after[DEFAULT_IDS.phase_two],
        )
        self.assertIn("SetMapSoundState(2603802, Disabled)", after[12604803])
        self.assertIn("InArea(10000, 2602801)", after[12604803])
        self.assertIn("EventFlag(12991601)", after[12604803])
        copied = "\n".join(
            after[event] for event in (12604802, 12604803, *DEFAULT_IDS.values())
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:123|230)\d+(?!\d)")

    def test_every_competing_native_core_or_support_controller_is_suppressed(self):
        after = event_blocks(patch_bsb_at_wet_nurse(self.nurse, self.bsb))
        for event in (12604810, 12604815, 12604820, 12604830, 12604840):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1], event)
        all_bodies = "\n".join(after.values())
        disabled_support = re.findall(
            r"ChangeCharacterEnableState\(2600801, Disabled\)", all_bodies
        )
        self.assertGreater(len(disabled_support), 0)
        self.assertNotRegex(
            all_bodies, r"ChangeCharacterEnableState\(2600801, Enabled\)"
        )
        terminal = after[12601800]
        self.assertIn("ForceCharacterDeath(2600801, false);", terminal)
        self.assertIn("ForceCharacterDeath(2600800, false);", terminal)

    def test_plan_has_one_primary_swap_exact_pins_and_retained_helpers(self):
        plan = native_plan_bsb_at_wet_nurse(
            self.slots, self.npcs, self.effects, "nurse"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c2090", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual("m26_00_00_00", binding["destination_map"])
        self.assertEqual(
            "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
            binding["source_provenance"]["part_sha256"],
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual({2600801, 2600802}, {row["entity_id"] for row in retained})
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])
        self.assertTrue(plan["scaling"]["enabled"])

    def test_ids_and_source_or_destination_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129916xx"):
            patch_bsb_at_wet_nurse(
                self.nurse,
                self.bsb,
                replace(DEFAULT_IDS, phase_two=DEFAULT_IDS.phase_one),
            )
        with self.assertRaisesRegex(ValueError, "129916xx"):
            patch_bsb_at_wet_nurse(
                self.nurse, self.bsb, BsbWetNurseIds(12991599, 12991601, 12991602)
            )
        with self.assertRaisesRegex(ValueError, "unsupported original BSB donor"):
            patch_bsb_at_wet_nurse(
                self.nurse,
                self.bsb.replace("HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5"),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Wet Nurse arena"):
            patch_bsb_at_wet_nurse(
                self.nurse.replace("HandleBossDefeat(2600803)", "HandleBossDefeat(7)"),
                self.bsb,
            )


if __name__ == "__main__":
    unittest.main()
