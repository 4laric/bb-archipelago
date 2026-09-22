import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.gehrman_micolash_contract import (
    ARENA_SOURCE,
    BUNDLE,
    CHASE_EVENTS,
    DEFAULT_IDS,
    DONOR_SOURCE,
    MICOLASH,
    native_plan_gehrman_at_micolash,
    patch_gehrman_at_micolash,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class GehrmanMicolashContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_terminal_progression_is_preserved_and_talk_gate_has_a_death_bridge(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_gehrman_at_micolash(self.arena, self.donor))
        for event in (
            12601850,
            12601852,
            12601854,
            12601855,
            12604855,
            12604860,
            12604861,
        ):
            self.assertEqual(before[event], after[event])
        terminal = after[12601850]
        self.assertLess(
            terminal.index("WaitFor(CharacterDead(2600850));"),
            terminal.index("WaitFor(EventFlag(72600301));"),
        )
        bridge = after[DEFAULT_IDS.terminal_bridge]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2600850));"),
            bridge.index("SetEventFlag(72600301, ON);"),
        )
        self.assertIn("EndIf(EventFlag(12601850));", bridge)

    def test_gehrman_health_camera_music_and_both_phase_controllers_are_attached(self):
        after = event_blocks(patch_gehrman_at_micolash(self.arena, self.donor))
        health = after[12604852]
        self.assertIn("SetCharacterInvincibility(2600850, Enabled);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 2600850, 0, 804000);", health)
        self.assertIn("SetCharacterEventTarget(2600850, 980700);", health)
        self.assertIn("StartTimeMeasurement(2601010, 232, Enabled);", health)
        self.assertNotIn("RequestCharacterAICommand(2600850, 10, 0);", health)
        self.assertIn(
            "WaitFor(CharacterHasEventMessage(2600850, 100));", after[12604853]
        )
        lockcam = after[12604854]
        self.assertIn("SetLockcamSlotNumber(26, 0, 1);", lockcam)
        self.assertIn("SetLockcamSlotNumber(26, 0, 0);", lockcam)
        phase = after[DEFAULT_IDS.phase_one]
        self.assertIn("WaitFor(HPRatio(2600850) < 0.5);", phase)
        self.assertIn("RequestCharacterAICommand(2600850, 100, 0);", phase)
        cleanup = after[DEFAULT_IDS.phase_cleanup]
        self.assertIn("WaitFor(CharacterHasEventMessage(2600850, 20));", cleanup)
        self.assertIn("ClearSpEffect(2600850, 5526);", cleanup)

    def test_model_specific_chase_graph_is_inert_without_setting_destination_flags(
        self,
    ):
        after = event_blocks(patch_gehrman_at_micolash(self.arena, self.donor))
        for event in CHASE_EVENTS:
            body = after[event]
            self.assertEqual("    WaitFor(InArea(10000, 0));", body.splitlines()[1])
            self.assertNotIn("2600850", body)
            self.assertNotIn("SetEventFlag", body)
        self.assertIn("if (EventFlag(12604879))", after[12601854])
        self.assertNotIn("SetCharacterImmortality", after[12604856])
        self.assertNotIn("WarpCharacterAndSetFloor", after[12604889])

    def test_constructor_starts_project_events_once_and_completed_load_cleans_owner(
        self,
    ):
        after = event_blocks(patch_gehrman_at_micolash(self.arena, self.donor))
        constructor = after[0]
        for event in DEFAULT_IDS.events():
            self.assertEqual(1, constructor.count(f"$InitializeEvent(0, {event});"))
        cleanup = after[DEFAULT_IDS.owner_cleanup]
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(12601850));"),
            cleanup.index("ChangeCharacterEnableState(980700, Disabled);"),
        )
        self.assertLess(
            cleanup.index("ChangeCharacterEnableState(980700, Disabled);"),
            cleanup.index("ForceCharacterDeath(980700, false);"),
        )

    def test_native_plan_pins_owner_reachable_placement_and_explicit_talk_suppression(
        self,
    ):
        plan = native_plan_gehrman_at_micolash(
            self.slots, self.npcs, self.effects, "gehrman-micolash"
        )
        self.assertEqual(1, plan["swap_count"])
        destination = plan["swaps"][0]["destinations"]["m26_00_00_00:c0000_0005"]
        self.assertEqual(
            {
                "map_name": "m26_00_00_00",
                "entity_id": 2600850,
                "x": 176.82,
                "y": 1037.98,
                "z": -37.82,
            },
            destination,
        )
        self.assertEqual(1, len(plan["boss_actor_additions"]))
        owner = plan["boss_actor_additions"][0]
        self.assertEqual(2100801, owner["source_entity_id"])
        self.assertEqual(980700, owner["destination_entity_id"])
        self.assertEqual("c9010_0004", owner["source_anchor_part"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(210306, binding["source_initialization"]["talk_id"])
        self.assertEqual(260311, binding["destination_original_talk_id"])
        self.assertEqual(0, binding["destination_talk_id_override"])
        self.assertIn("destination_talk_id_override", binding["required_native_fields"])
        contract = plan["boss_contract"]
        self.assertEqual("unobserved", contract["runtime_status"])
        self.assertIn("72600301", contract["terminal_policy"])

    def test_allocation_source_and_actor_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "allocation collides"):
            patch_gehrman_at_micolash(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, phase_one=DEFAULT_IDS.phase_cleanup),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Micolash arena"):
            patch_gehrman_at_micolash(
                self.arena.replace(
                    "WaitFor(EventFlag(72600301));",
                    "WaitFor(EventFlag(72600302));",
                ),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Gehrman donor"):
            patch_gehrman_at_micolash(
                self.arena,
                self.donor.replace(
                    "SetCharacterEventTarget(2100800, 2100801);",
                    "SetCharacterEventTarget(2100800, 1);",
                ),
            )
        changed_slots = [
            replace(slot, talk_id=0) if slot.entity_id == MICOLASH else slot
            for slot in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "requires pinned actor 2600850"):
            native_plan_gehrman_at_micolash(
                changed_slots, self.npcs, self.effects, "actor-drift"
            )


if __name__ == "__main__":
    unittest.main()
