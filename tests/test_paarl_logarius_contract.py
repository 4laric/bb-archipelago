import re
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.paarl_logarius_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LOGARIUS_SOURCE,
    PAARL_SOURCE,
    PaarlLogariusIds,
    native_plan_paarl_at_logarius,
    patch_paarl_at_logarius,
)
from tools.bb_enemizer.scaling import load_params


class PaarlLogariusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paarl = read_blob(BUNDLE, PAARL_SOURCE).decode("utf-8-sig")
        cls.logarius = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_cainhurst_progression_is_preserved_while_paarl_wakes_natively(self):
        before = event_blocks(self.logarius)
        after = event_blocks(patch_paarl_at_logarius(self.logarius, self.paarl))
        for event_id in (12501800, 12501801, 12501803, 12504805, 12504810, 12504811):
            self.assertEqual(before[event_id], after[event_id])
        activation = after[12501802]
        self.assertIn("PlayCutsceneToPlayer(25000020", activation)
        self.assertIn("SetCharacterInvincibility(2500800, Enabled)", activation)
        self.assertIn("ForceAnimationPlayback(2500800, 7000, true", activation)
        self.assertIn("ForceAnimationPlayback(2500800, 7001, false", activation)
        self.assertIn("WaitFixedTimeFrames(70)", activation)
        self.assertIn("SetCharacterInvincibility(2500800, Disabled)", activation)
        self.assertLess(
            activation.index("SetCharacterInvincibility(2500800, Disabled)"),
            activation.index("SetEventFlag(12504800, ON)"),
        )

    def test_paarl_combat_package_uses_cainhurst_operands(self):
        after = event_blocks(patch_paarl_at_logarius(self.logarius, self.paarl))
        health = after[12504802]
        self.assertIn("EventFlag(12504223)", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 2500800, 0, 508000)", health)
        music = after[12504803]
        self.assertIn("SetMapSoundState(2503802, Disabled)", music)
        self.assertIn("CharacterHasEventMessage(2500800, 20)", music)
        self.assertIn("InArea(10000, 2502802)", music)
        camera = after[12504804]
        self.assertIn("EndIf(EventFlag(12501800))", camera)
        self.assertIn("SetLockcamSlotNumber(25, 0, 1)", camera)
        self.assertIn("SetLockcamSlotNumber(25, 0, 0)", camera)
        self.assertIn("HPRatio(2500800) < 0.67", after[DEFAULT_IDS.phase])
        limb = after[DEFAULT_IDS.limb]
        self.assertIn("CreateNPCPart(2500800", limb)
        self.assertIn("CharacterHasEventMessage(2500800, 300)", limb)
        coop = after[DEFAULT_IDS.coop_entry]
        self.assertIn("SetCharacterInvincibility(2500800, Disabled)", coop)
        self.assertIn("SetEventFlag(12501802, ON)", coop)
        copied = "\n".join(
            after[i]
            for i in (
                12504802,
                12504803,
                12504804,
                DEFAULT_IDS.phase,
                DEFAULT_IDS.coop_entry,
                DEFAULT_IDS.limb,
            )
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:123\d{5}|230\d{4})(?!\d)")

    def test_constructor_copies_exact_phase_coop_and_five_limb_bindings(self):
        before = event_blocks(self.paarl)[0]
        after = event_blocks(patch_paarl_at_logarius(self.logarius, self.paarl))[0]
        expected_counts = {
            12504802: 1,
            12504803: 1,
            12504804: 1,
            DEFAULT_IDS.phase: 1,
            DEFAULT_IDS.coop_entry: 1,
            DEFAULT_IDS.limb: 5,
            DEFAULT_IDS.helper_cleanup: 1,
        }
        for event_id, expected in expected_counts.items():
            self.assertEqual(
                expected,
                len(
                    re.findall(
                        r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                        after,
                    )
                ),
            )
        donor_limb_calls = [
            line.replace("12304715", str(DEFAULT_IDS.limb), 1)
            for line in before.splitlines()
            if "12304715" in line
        ]
        self.assertEqual(5, len(donor_limb_calls))
        for call in donor_limb_calls:
            self.assertIn(call, after)

    def test_logarius_helpers_are_inert_until_destination_completion(self):
        before = event_blocks(self.logarius)
        after = event_blocks(patch_paarl_at_logarius(self.logarius, self.paarl))
        for event_id in (12504806, 12504807, 12504808):
            self.assertEqual("    EndEvent();", after[event_id].splitlines()[1])
        cleanup = after[DEFAULT_IDS.helper_cleanup]
        wait = cleanup.index("WaitFor(EventFlag(12501800));")
        self.assertIn("SetCharacterImmortality(2500801, Enabled);", cleanup[:wait])
        self.assertNotIn("ForceCharacterDeath", cleanup[:wait])
        self.assertIn("ForceCharacterDeath(2500801, false);", cleanup[wait:])
        self.assertIn("ForceCharacterDeath(2500802, false);", cleanup[wait:])
        self.assertEqual(set(before) | set(DEFAULT_IDS.values()), set(after))

    def test_native_plan_pins_both_paarl_states_and_retained_helpers(self):
        plan = native_plan_paarl_at_logarius(
            self.slots, self.npcs, self.effects, "paarl-logarius"
        )
        self.assertEqual("c5080", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual(
            "cac704506e58dfd3f2c57113d919fafe0a70d01b7a40b869deffa3c6e22cc0a2",
            binding["source_provenance"]["part_sha256"],
        )
        state_pins = plan["boss_contract"]["source_state_pins"]
        self.assertEqual({"m23_00_00_00", "m23_00_00_01"}, set(state_pins))
        self.assertEqual(
            "6c8a693b9c846922a1113726ec69a11b47973c5e367a94757ad82d3fbf3081ee",
            state_pins["m23_00_00_01"]["part_sha256"],
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual({2500801, 2500802}, {row["entity_id"] for row in retained})
        self.assertEqual(
            set(
                map(
                    str,
                    (
                        12301700,
                        12301701,
                        12301702,
                        12301703,
                        12304730,
                        12304702,
                        12304703,
                        12304704,
                        12304707,
                        12304715,
                    ),
                )
            ),
            set(plan["boss_contract"]["source_actor_event_closure"]),
        )
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_collision_source_destination_and_roster_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129915xx"):
            patch_paarl_at_logarius(
                self.logarius,
                self.paarl,
                PaarlLogariusIds(12991500, 12991500, 12991502, 12991503),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Paarl donor"):
            patch_paarl_at_logarius(
                self.logarius,
                self.paarl.replace(
                    "CharacterHasSpEffect(2300810, 5402)",
                    "CharacterHasSpEffect(2300810, 9)",
                ),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Logarius arena"):
            patch_paarl_at_logarius(
                self.logarius.replace(
                    "HandleBossDefeat(2500800)", "HandleBossDefeat(9)"
                ),
                self.paarl,
            )
        without_owner = [slot for slot in self.slots if slot.entity_id != 2500802]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_paarl_at_logarius(
                without_owner, self.npcs, self.effects, "missing-owner"
            )


if __name__ == "__main__":
    unittest.main()
