import re
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_logarius_contract import (
    BUNDLE,
    BSB_SOURCE,
    LOGARIUS_SOURCE,
    BsbLogariusIds,
    DEFAULT_IDS,
    native_plan_bsb_at_logarius,
    patch_bsb_at_logarius,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbLogariusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
        cls.logarius = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_destination_completion_reward_fog_and_entry_remain_cainhurst_owned(self):
        before = event_blocks(self.logarius)
        after = event_blocks(patch_bsb_at_logarius(self.logarius, self.bsb))
        for event_id in (12501800, 12501801, 12501803, 12504805, 12504810, 12504811):
            self.assertEqual(before[event_id], after[event_id])
        restored_entry = after[12501802].replace(
            "ForceAnimationPlayback(2500800, 7001,",
            "ForceAnimationPlayback(2500800, 7000,",
        )
        self.assertEqual(before[12501802], restored_entry)
        self.assertIn("PlayCutsceneToPlayer(25000020", after[12501802])
        self.assertIn("AwardAchievement(26)", after[12501800])

    def test_bsb_health_music_camera_and_phases_use_cainhurst_operands(self):
        after = event_blocks(patch_bsb_at_logarius(self.logarius, self.bsb))
        health = after[12504802]
        self.assertIn("WaitFor(EventFlag(12504800))", health)
        self.assertIn("EventFlag(12504223)", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 2500800, 0, 209000)", health)
        self.assertIn("SetMapSoundState(2503802, Disabled)", after[12504803])
        self.assertIn("InArea(10000, 2502802)", after[12504803])
        self.assertIn("EventFlag(12991301)", after[12504803])
        self.assertIn("EndIf(EventFlag(12501800))", after[12504804])
        self.assertIn("SetLockcamSlotNumber(25, 0, 1)", after[12504804])
        self.assertIn("HPRatio(2500800) < 0.67", after[DEFAULT_IDS.phase_one])
        self.assertIn(
            "HPRatio(2500800) < 0.33 && EventFlag(12991300)",
            after[DEFAULT_IDS.phase_two],
        )
        copied = "\n".join(
            after[event]
            for event in (
                12504802,
                12504803,
                12504804,
                DEFAULT_IDS.phase_one,
                DEFAULT_IDS.phase_two,
            )
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:123|230)\d+(?!\d)")

    def test_constructor_starts_each_active_controller_once(self):
        after = event_blocks(patch_bsb_at_logarius(self.logarius, self.bsb))
        constructor = after[0]
        for event_id in (
            12504802,
            12504803,
            12504804,
            DEFAULT_IDS.phase_one,
            DEFAULT_IDS.phase_two,
            DEFAULT_IDS.helper_cleanup,
        ):
            self.assertEqual(
                1,
                len(
                    re.findall(
                        r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                        constructor,
                    )
                ),
                event_id,
            )

    def test_apparent_extra_bsb_references_are_unrelated_action_button_ids(self):
        donor = event_blocks(self.bsb)
        for event_id in (12304730, 12304731):
            self.assertIn("ActionButtonInArea(2300800, 2301810)", donor[event_id])
            body_without_action_button = donor[event_id].replace(
                "ActionButtonInArea(2300800, 2301810)",
                "ActionButtonInArea(ACTION, AREA)",
            )
            self.assertNotIn("2300800", body_without_action_button)

    def test_logarius_helpers_are_inert_alive_until_completion_then_cleaned(self):
        before = event_blocks(self.logarius)
        after = event_blocks(patch_bsb_at_logarius(self.logarius, self.bsb))
        for event_id in (12504806, 12504807, 12504808):
            self.assertEqual("    EndEvent();", after[event_id].splitlines()[1])
        cleanup = after[DEFAULT_IDS.helper_cleanup]
        wait = cleanup.index("WaitFor(EventFlag(12501800));")
        self.assertIn("SetCharacterImmortality(2500801, Enabled);", cleanup[:wait])
        self.assertNotIn("ForceCharacterDeath", cleanup[:wait])
        self.assertIn("SetCharacterImmortality(2500801, Disabled);", cleanup[wait:])
        self.assertIn("ForceCharacterDeath(2500801, false);", cleanup[wait:])
        self.assertIn("ForceCharacterDeath(2500802, false);", cleanup[wait:])
        self.assertEqual(set(before) | set(DEFAULT_IDS.values()), set(after))

    def test_native_plan_pins_bsb_source_and_retained_three_actor_destination(self):
        plan = native_plan_bsb_at_logarius(
            self.slots, self.npcs, self.effects, "bsb-logarius"
        )
        self.assertEqual("c2090", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual(
            "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
            binding["source_provenance"]["part_sha256"],
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual({2500801, 2500802}, {row["entity_id"] for row in retained})
        self.assertEqual(
            {"c2321", "c9010"}, {row["archetype"]["model_name"] for row in retained}
        )
        self.assertTrue(plan["scaling"]["enabled"])
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_ids_donor_drift_destination_drift_and_missing_helper_refuse(self):
        with self.assertRaisesRegex(ValueError, "129913xx"):
            patch_bsb_at_logarius(
                self.logarius, self.bsb, BsbLogariusIds(12991300, 12991300, 12991302)
            )
        with self.assertRaisesRegex(ValueError, "unsupported original BSB donor"):
            patch_bsb_at_logarius(
                self.logarius,
                self.bsb.replace("HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5"),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Logarius arena"):
            patch_bsb_at_logarius(
                self.logarius.replace(
                    "HandleBossDefeat(2500800)", "HandleBossDefeat(9)"
                ),
                self.bsb,
            )
        without_owner = [slot for slot in self.slots if slot.entity_id != 2500802]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_bsb_at_logarius(
                without_owner, self.npcs, self.effects, "missing-owner"
            )


if __name__ == "__main__":
    unittest.main()
