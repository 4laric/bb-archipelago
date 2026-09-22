import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.gascoigne_witch_contract import *
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class GascoigneWitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, GASCOIGNE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)
        cls.before = event_blocks(cls.arena)
        cls.after = event_blocks(
            patch_gascoigne_at_witch(cls.arena, cls.donor)
        )

    def test_two_body_terminal_is_byte_identical_and_bridge_waits_for_gascoigne(self):
        self.assertEqual(self.before[12201800], self.after[12201800])
        self.assertIn(
            "WaitFor(CharacterDead(2200800) && CharacterDead(2200801));",
            self.after[12201800],
        )
        bridge = self.after[DEFAULT_IDS.death_bridge]
        wait = bridge.index("WaitFor(humanDead || beastDead);")
        self.assertLess(wait, bridge.index("ForceCharacterDeath(2200800, false);"))
        self.assertLess(wait, bridge.index("ForceCharacterDeath(2200801, false);"))
        self.assertIn("beastDead = CharacterDead(981800);", bridge)

        # The terminal proxy stays alive while hidden.  Killing it during
        # retirement would let a human-form disable/death finish Hemwick early.
        retire = self.after[DEFAULT_IDS.retirement]
        completion = retire.index("WaitFor(EventFlag(12201800));")
        self.assertNotIn("ForceCharacterDeath(2200801", retire)
        self.assertLess(
            retire.index("ChangeCharacterEnableState(2200801, Disabled);"),
            completion,
        )

    def test_entry_health_phase_camera_and_music_cover_both_forms(self):
        entry = self.after[12201802]
        self.assertNotIn("PlayerInsightAmount", entry)
        self.assertNotIn("3011", entry)
        self.assertIn("ChangeCharacterEnableState(2200800, Enabled);", entry)
        self.assertIn("SetEventFlag(12204800, ON);", entry)

        health = self.after[12204802]
        self.assertIn("CreateReferredDamagePair(2200800, 981800);", health)
        for entity, name in ((2200800, 271000), (981800, 272000)):
            self.assertIn(f"SetSpEffect({entity}, 7500, true);", health)
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, {entity}, 0, {name});", health
            )
        self.assertIn("CreatePlaylog(88);", health)
        self.assertIn("StartTimeMeasurement(2200010, 104, Enabled);", health)

        phase = self.after[DEFAULT_IDS.phase]
        self.assertIn("HPRatio(2200800) < 0.34", phase)
        self.assertIn("WarpCharacterAndCopyFloor(981800", phase)
        self.assertLess(
            phase.index("ChangeCharacterEnableState(2200800, Disabled);"),
            phase.index("SetCharacterAIState(981800, Enabled);"),
        )
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase})", self.after[12204803])
        self.assertNotIn("CharacterHPValue(2200801)", self.after[12204803])
        self.assertEqual(4, self.after[12204804].count("SetLockcamSlotNumber(22, 0,"))
        self.assertNotIn("SetLockcamSlotNumber(24, 1,", self.after[12204804])

    def test_witch_controllers_are_retired_but_completion_cleanup_is_preserved(self):
        for event in (12201801, 12201803, 12201804, 12204805):
            self.assertEqual(self.before[event], self.after[event])
        for event in (
            12204807,
            12204808,
            12204810,
            12204811,
            12204812,
            12204814,
            12204820,
            12204830,
            12204832,
            12204835,
            12204838,
            12204839,
            12204840,
            12204841,
            12204842,
            12204843,
        ):
            self.assertEqual("    EndEvent();", self.after[event].splitlines()[1])
        retire = self.after[DEFAULT_IDS.retirement]
        for entity in (2205000, 2205001, 2205002):
            self.assertIn(f"DeactivateGenerator({entity}, Disabled);", retire)
        for entity in (2200810, 2200811, 2200812):
            self.assertIn(
                f"ChangeCharacterEnableState({entity}, Disabled);", retire
            )
        self.assertLess(
            retire.index("WaitFor(EventFlag(12201800));"),
            retire.index("ChangeCharacterEnableState(981800, Disabled);"),
        )

    def test_native_plan_pins_both_forms_and_retains_terminal_proxy(self):
        plan = native_plan_gascoigne_at_witch(
            self.slots, self.npcs, self.effects, "gascoigne-witch"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c2710", plan["swaps"][0]["target"]["model_name"])
        primary = plan["primary_init_source_bindings"][0]
        self.assertEqual(HUMAN_PIN, primary["source_provenance"]["part_sha256"])
        self.assertEqual(HUMAN_INITIALIZATION, primary["source_initialization"])
        self.assertEqual(241330, primary["source_talk_id"])
        self.assertEqual(0, primary["destination_original_talk_id"])
        self.assertEqual(0, primary["destination_talk_id_override"])
        self.assertIn("destination_talk_id_override", primary["required_native_fields"])

        beast = plan["boss_actor_additions"][0]
        self.assertEqual(981800, beast["destination_entity_id"])
        self.assertEqual(BEAST_PART, beast["source_part"])
        self.assertEqual(HUMAN_PART, beast["source_anchor_part"])
        self.assertEqual(BEAST_PIN, beast["source_provenance"]["part_sha256"])
        self.assertEqual(HUMAN_PIN, beast["source_provenance"]["anchor_sha256"])
        self.assertEqual(BEAST_INITIALIZATION, beast["source_initialization"])
        self.assertEqual(1, len(plan["boss_actor_scaling_requirements"]))

        proxy = plan["boss_contract"]["retained_destination_helpers"][0]
        self.assertEqual(2200801, proxy["entity_id"])
        self.assertEqual(SECOND_PIN, proxy["source_provenance"]["part_sha256"])
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_collisions_and_original_source_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "129940xx"):
            patch_gascoigne_at_witch(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, phase=DEFAULT_IDS.human_special),
            )
        with self.assertRaisesRegex(ValueError, "9818xx"):
            patch_gascoigne_at_witch(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, beast_entity=GASCOIGNE_BEAST),
            )
        with self.assertRaisesRegex(ValueError, "Gascoigne donor"):
            patch_gascoigne_at_witch(
                self.arena,
                self.donor.replace("CreateReferredDamagePair(2410810", "CreateReferredDamagePair(7"),
            )
        with self.assertRaisesRegex(ValueError, "Witch arena"):
            patch_gascoigne_at_witch(
                self.arena.replace("HandleBossDefeat(2200800)", "HandleBossDefeat(7)"),
                self.donor,
            )

        drifted = [
            replace(slot, talk_id=0)
            if slot.map_name == SOURCE_MAP and slot.entity_id == GASCOIGNE_HUMAN
            else slot
            for slot in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "TalkID drift"):
            native_plan_gascoigne_at_witch(
                drifted, self.npcs, self.effects, "gascoigne-witch"
            )


if __name__ == "__main__":
    unittest.main()
