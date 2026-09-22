import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.micolash_moon_contract import (
    ARENA_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    DONOR_SOURCE,
    MICOLASH,
    native_plan_micolash_at_moon,
    patch_micolash_at_moon,
)
from tools.bb_enemizer.scaling import load_params


class MicolashMoonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_moon_entry_terminal_and_final_progression_remain_byte_identical(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_micolash_at_moon(self.arena, self.donor))
        for event in (
            50,
            12100800,
            12101850,
            12101851,
            12101852,
            12101853,
            12104854,
            12104855,
        ):
            self.assertEqual(before[event], after[event])
        terminal = after[12101850]
        self.assertIn("WaitFor(CharacterDead(2100810));", terminal)
        self.assertIn("HandleBossDefeat(2100810);", terminal)
        self.assertIn("$InitializeEvent(0, 9350, 5);", terminal)

    def test_source_health_enters_direct_combat_and_keeps_destination_logging(self):
        after = event_blocks(patch_micolash_at_moon(self.arena, self.donor))
        health = after[12104852]
        self.assertIn("SetCharacterDefaultBackreadState(2100810, Enabled);", health)
        self.assertIn(
            "SetNetworkUpdateRate(2100810, true, CharacterUpdateFrequency.AlwaysUpdate);",
            health,
        )
        self.assertIn("DisplayBossHealthBar(Enabled, 2100810, 0, 899000);", health)
        self.assertIn("RequestCharacterAICommand(2100810, -1, 0);", health)
        self.assertIn("RequestCharacterAIReplan(2100810);", health)
        self.assertIn("CreatePlaylog(128);", health)
        self.assertIn("StartTimeMeasurement(2100011, 146, Enabled);", health)
        self.assertNotIn("RequestCharacterAICommand(2100810, 10, 0);", health)
        self.assertNotIn("SetDistanceLimitForConversationStateProcessing", health)
        self.assertNotIn("12604731", health)

    def test_half_health_phase_is_source_state_without_dialogue_or_labyrinth_geometry(
        self,
    ):
        after = event_blocks(patch_micolash_at_moon(self.arena, self.donor))
        phase = after[DEFAULT_IDS.phase_state]
        self.assertIn("WaitFor(EventFlag(12104852) && HPRatio(2100810) <= 0.5);", phase)
        self.assertLess(
            phase.index(f"SetEventFlag({DEFAULT_IDS.phase_marker}, OFF);"),
            phase.index(f"SetEventFlag({DEFAULT_IDS.phase_marker}, ON);"),
        )
        self.assertLess(
            phase.index(f"SetEventFlag({DEFAULT_IDS.phase_marker}, ON);"),
            phase.index("RequestCharacterAICommand(2100810, -1, 0);"),
        )
        self.assertIn(
            f"WaitFor(EventFlag({DEFAULT_IDS.phase_marker}));", after[12104853]
        )
        combined = "\n".join(
            after[event] for event in (12104852, 12104853, DEFAULT_IDS.phase_state)
        )
        self.assertNotIn("WarpCharacterAndSetFloor", combined)
        self.assertNotIn("TalkToPlayer", combined)
        self.assertNotIn("72600300", combined)
        self.assertNotRegex(combined, r"(?<!\d)26020\d+(?!\d)")

    def test_moon_limb_and_player_effect_controllers_are_retired(self):
        after = event_blocks(patch_micolash_at_moon(self.arena, self.donor))
        limb = after[12104860]
        self.assertEqual("    EndEvent();", limb.splitlines()[1])
        self.assertNotIn("CreateNPCPart", limb)
        player_effect = after[12104870]
        self.assertEqual("    EndEvent();", player_effect.splitlines()[1])
        self.assertNotIn("SetCharacterImmortality(10000", player_effect)
        self.assertEqual(
            1,
            after[0].count(f"$InitializeEvent(0, {DEFAULT_IDS.phase_state});"),
        )

    def test_native_plan_pins_source_and_suppresses_map_specific_talk(self):
        plan = native_plan_micolash_at_moon(
            self.slots, self.npcs, self.effects, "micolash-moon"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertNotIn("boss_actor_additions", plan)
        destination = plan["swaps"][0]["destinations"]["m21_00_00_00:c5400_0000"]
        self.assertEqual(
            {
                "map_name": "m21_00_00_00",
                "entity_id": 2100810,
                "x": 30.0,
                "y": -8.52,
                "z": 12.0,
            },
            destination,
        )
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(260311, binding["source_initialization"]["talk_id"])
        self.assertEqual(6380, binding["source_initialization"]["unk_t18"])
        self.assertEqual(0, binding["destination_talk_id_override"])
        self.assertIn("destination_talk_id_override", binding["required_native_fields"])
        contract = plan["boss_contract"]
        self.assertEqual("unobserved", contract["runtime_status"])
        self.assertEqual(
            "donor_dialogue_and_progression_excluded",
            contract["source_map_dialogue_not_transplanted"]["policy"],
        )
        self.assertIn("events12604877 and12604879", contract["navigation_policy"])
        self.assertIn("event messages10/20", contract["spell_policy"])
        self.assertIn("runtime behavior is unobserved", contract["spell_policy"])
        audit = contract["ai_flag_audit"]
        self.assertEqual(72600300, audit["lua50_numeric_constant"])
        self.assertEqual(
            {"006380_battle.lua": 0, "006380_logic.lua": 0},
            audit["occurrences"],
        )
        self.assertEqual(12993120, contract["event_ids"]["phase_marker"])

    def test_allocation_source_destination_and_actor_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "allocation collides"):
            patch_micolash_at_moon(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, phase_marker=DEFAULT_IDS.phase_state),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Moon Presence"):
            patch_micolash_at_moon(
                self.arena.replace(
                    "HandleBossDefeat(2100810);", "HandleBossDefeat(7);"
                ),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Micolash donor"):
            patch_micolash_at_moon(
                self.arena,
                self.donor.replace(
                    "RequestCharacterAICommand(2600850, 10, 0);",
                    "RequestCharacterAICommand(2600850, 11, 0);",
                    1,
                ),
            )
        changed_slots = [
            replace(slot, talk_id=0) if slot.entity_id == MICOLASH else slot
            for slot in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "requires pinned actor 2600850"):
            native_plan_micolash_at_moon(
                changed_slots, self.npcs, self.effects, "actor-drift"
            )


if __name__ == "__main__":
    unittest.main()
