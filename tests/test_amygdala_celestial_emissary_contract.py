import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.amygdala_celestial_emissary_contract import (
    AMYGDALA_SOURCE,
    BUNDLE,
    CELESTIAL_SOURCE,
    DEFAULT_IDS,
    EBRIETAS_EVENTS,
    GENERATORS,
    GIANT,
    SUPPORT,
    TERMINAL,
    WAVES,
    AmygdalaCelestialIds,
    native_plan_amygdala_at_celestial_emissary,
    patch_amygdala_at_celestial_emissary,
)
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class AmygdalaCelestialEmissaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.amygdala = read_blob(BUNDLE, AMYGDALA_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        cls.celestial = read_blob(BUNDLE, CELESTIAL_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        with tempfile.TemporaryDirectory() as directory:
            slots_file = Path(directory) / "slots.tsv"
            slots_file.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(slots_file)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self):
        return event_blocks(patch_amygdala_at_celestial_emissary(self.celestial, self.amygdala))

    def test_giant_terminal_is_byte_identical_and_amygdala_death_bridges_afterward(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        self.assertEqual(before[TERMINAL], after[TERMINAL])
        self.assertIn("WaitFor(CharacterDead(2420811));", after[TERMINAL])
        bridge = after[DEFAULT_IDS.death_to_giant]
        self.assertLess(bridge.index("WaitFor(CharacterDead(2420810));"), bridge.index("ForceCharacterDeath(2420811, false);"))
        self.assertIn("EndIf(EventFlag(12421700));", bridge)

    def test_entry_and_destination_fog_boundaries(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        for event in (12421701, 12424705, 12424710, 12424711):
            self.assertEqual(before[event], after[event], event)
        entry = after[12421702]
        self.assertIn("InArea(10000, 2422815)", entry)
        self.assertIn("ForceAnimationPlayback(2420810, 7003", entry)
        self.assertIn("ForceAnimationPlayback(2420810, 7006", entry)
        self.assertIn("ForceAnimationPlayback(2420810, 7002", entry)
        self.assertIn("SetCharacterGravity(2420810, Enabled);", entry)
        coop = after[12421703]
        self.assertIn("EventFlag(12424700)", coop)
        self.assertIn("SetEventFlag(12421702, ON);", coop)

    def test_health_music_camera_and_phase_graph_are_destination_bound(self):
        after = self.patched()
        health = after[12424702]
        self.assertIn("DisplayBossHealthBar(Enabled, 2420810, 0, 512000);", health)
        self.assertIn("SetCharacterAIState(2420811, Disabled);", health)
        self.assertIn("SetNetworkUpdateAuthority(2420811, AuthorityLevel.Forced);", health)
        music = after[12424703]
        self.assertIn("SetMapSoundState(2423812, Disabled);", music)
        self.assertIn("InArea(10000, 2422812)", music)
        self.assertIn("CharacterHasEventMessage(2420810, 10)", music)
        camera = after[12424704]
        self.assertIn("SetLockcamSlotNumber(24, 2, 1);", camera)
        self.assertIn("SetLockcamSlotNumber(24, 2, 0);", camera)
        self.assertNotIn("SetLockcamSlotNumber(33,", camera)
        self.assertLess(camera.index("EndIf(EventFlag(12421700));"), camera.index("WaitFor("))
        self.assertIn("HPRatio(2420810) < 0.7", after[DEFAULT_IDS.phase_one])
        self.assertIn("HPRatio(2420810) < 0.3 && EventFlag(12992500)", after[DEFAULT_IDS.phase_two])

    def test_all_body_part_initializers_and_routines_are_transplanted(self):
        after = self.patched()
        constructor = after[0]
        self.assertIn("$InitializeEvent(0, 12992502, 3311, 3311, NPCPartType.Part13, 9, 13);", constructor)
        self.assertIn("$InitializeEvent(1, 12992502, 3322, 3322, NPCPartType.Part14, 8, 14);", constructor)
        for slot, part in enumerate(range(3301, 3311)):
            self.assertIn(f"$InitializeEvent({slot}, 12992503, {part}, {part},", constructor)
        self.assertIn("$InitializeEvent(0, 12992504);", constructor)
        self.assertIn("CreateNPCPart(2420810, npcPartId,", after[DEFAULT_IDS.hitmask])
        self.assertIn("CreateNPCPart(2420810, npcPartId,", after[DEFAULT_IDS.limbs])
        self.assertIn("CreateNPCPart(2420810, 3300, NPCPartType.Part1", after[DEFAULT_IDS.body_part])

    def test_celestial_controllers_are_retired_without_early_giant_death(self):
        after = self.patched()
        for event in (12424770, 12424780, 12424784, 12424785, 12424787, 12424790, 12424791, 12424792, 12424795):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1], event)
        retire = after[DEFAULT_IDS.retire_celestial]
        for generator in GENERATORS:
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", retire)
        wait = retire.index("WaitFor(EventFlag(12421700));")
        for actor in (*WAVES, *SUPPORT):
            self.assertIn(f"ChangeCharacterEnableState({actor}, Disabled);", retire)
            self.assertGreater(retire.rindex(f"ForceCharacterDeath({actor}, false);"), wait)
        self.assertNotIn("ForceCharacterDeath(2420811", retire)

    def test_shared_ebrietas_and_unrelated_destination_events_remain_exact(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        for event in EBRIETAS_EVENTS:
            self.assertEqual(before[event], after[event], event)
        remove = re.compile(r"\n    \$InitializeEvent\([^\n]*129925\d+[^\n]*\);")
        self.assertEqual(before[0], remove.sub("", after[0]))

    def test_native_plan_pins_primary_and_retained_destination_entities(self):
        plan = native_plan_amygdala_at_celestial_emissary(self.slots, self.npcs, self.effects, "celestial")
        self.assertEqual(1, plan["swap_count"])
        destination = plan["swaps"][0]["destinations"][plan["swaps"][0]["destination_keys"][0]]
        self.assertEqual(2420810, destination["entity_id"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m33_00_00_00", binding["source_map"])
        self.assertEqual("c2500_0000", binding["destination_part"])
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual({GIANT, *WAVES, *SUPPORT}, {row["entity_id"] for row in retained})
        for row in retained:
            self.assertRegex(row["source_provenance"]["part_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(plan["scaling"]["enabled"])

    def test_ids_and_source_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "129925xx"):
            patch_amygdala_at_celestial_emissary(self.celestial, self.amygdala, replace(DEFAULT_IDS, phase_two=DEFAULT_IDS.phase_one))
        with self.assertRaisesRegex(ValueError, "Amygdala donor"):
            patch_amygdala_at_celestial_emissary(self.celestial, self.amygdala.replace("HPRatio(3300800) < 0.7", "HPRatio(3300800) < 0.5", 1))
        with self.assertRaisesRegex(ValueError, "Celestial arena"):
            patch_amygdala_at_celestial_emissary(self.celestial.replace("HandleBossDefeat(2420811)", "HandleBossDefeat(7)"), self.amygdala)


if __name__ == "__main__":
    unittest.main()
