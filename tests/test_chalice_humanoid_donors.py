"""Static source and destination contracts for three m29 humanoid bosses."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import BSB_ARENA, CLERIC_ARENA
from tools.bb_enemizer.chalice_humanoid_donors import (
    COMMON_EVENT_PINS, DONORS, SOURCE_INITIALIZATION,
    native_plan_chalice_humanoid_donor, patch_chalice_humanoid_donor,
    validate_source_map_witness,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.model import Slot
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class ChaliceHumanoidDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + CLERIC_ARENA.event_file).decode("utf-8-sig")
        cls.common = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_common_m29_routines_and_map_initializer_identity(self):
        common = event_blocks(self.common)
        for event, digest in COMMON_EVENT_PINS.items():
            self.assertEqual(digest, hashlib.sha256(common[event].encode()).hexdigest())
        self.assertEqual(3, len(DONORS))
        for donor in DONORS.values():
            with self.subTest(donor=donor.key):
                self.assertIn(str(donor.actor), donor.health_initializer)
                self.assertIn(str(donor.health_name_id), donor.health_initializer)
                self.assertIn(str(donor.completion_flag), donor.health_initializer)
                self.assertIn(str(donor.start_flag), donor.health_initializer)
                self.assertIn(str(donor.health_started_flag), donor.health_initializer)
                self.assertIn(str(donor.actor), donor.music_initializer)
                self.assertEqual(64, len(donor.map_event_zero_sha256))

    def test_cleric_adapter_keeps_progression_and_uses_native_phase_message(self):
        before = event_blocks(self.destination)
        for donor in DONORS.values():
            with self.subTest(donor=donor.key):
                patched = patch_chalice_humanoid_donor(
                    CLERIC_ARENA, donor, self.destination, self.common
                )
                after = event_blocks(patched)
                self.assertEqual(set(before), set(after))
                self.assertEqual(before[CLERIC_ARENA.completion_event],
                                 after[CLERIC_ARENA.completion_event])
                # The generic CLERIC_ARENA field aliases a model-specific
                # cloth phase; the actual Cleric guest entry is 12411703.
                self.assertEqual(before[12411703], after[12411703])
                self.assertIn(f"DisplayBossHealthBar(Enabled, {CLERIC_ARENA.actor}, 0, "
                              f"{donor.health_name_id})", after[CLERIC_ARENA.health_bar_event])
                self.assertIn("CreatePlaylog(80)", after[CLERIC_ARENA.health_bar_event])
                self.assertIn("StartTimeMeasurement(2410010, 96, Enabled)",
                              after[CLERIC_ARENA.health_bar_event])
                self.assertNotIn("12907230", after[CLERIC_ARENA.health_bar_event])
                self.assertIn("CharacterHasEventMessage(2410800, 500)",
                              after[CLERIC_ARENA.music_event])
                if donor.wake_animation is not None:
                    self.assertIn("ForceAnimationPlayback(2410800, 7001",
                                  after[CLERIC_ARENA.activation_event])
                else:
                    self.assertNotIn("ForceAnimationPlayback(2410800, 7001",
                                     after[CLERIC_ARENA.activation_event])
                self.assertNotIn("ForceAnimationPlayback(2410800, 3028",
                                 after[CLERIC_ARENA.activation_event])
                for event in (CLERIC_ARENA.phase_slots +
                              (CLERIC_ARENA.part_routine_event,
                               CLERIC_ARENA.cloth_routine_event)):
                    self.assertIn("EndEvent();", after[event])
                    self.assertNotIn("RequestCharacterAICommand", after[event])
                self.assertNotIn("12904888", patched)

    def test_native_plan_copies_exact_npc_think_and_initialization(self):
        destinations = [slot for slot in self.slots if slot.entity_id == CLERIC_ARENA.actor
                        and slot.archetype == CLERIC_ARENA.archetype]
        self.assertEqual(CLERIC_ARENA.destination_count, len(destinations))
        for donor in DONORS.values():
            with self.subTest(donor=donor.key):
                prototype = destinations[0]
                source = replace(prototype, map_name=donor.map_name,
                                 part_name=donor.part_name, entity_id=donor.actor,
                                 archetype=donor.archetype)
                plan = native_plan_chalice_humanoid_donor(
                    CLERIC_ARENA, donor, [*destinations, source],
                    self.npcs, self.effects, donor.key,
                )
                self.assertEqual("bb-enemizer-plan-v2", plan["format"])
                self.assertEqual(1, plan["swap_count"])
                self.assertEqual(500, plan["boss_contract"]["phase_music_message"])
                self.assertEqual("source-native-ai-tae", plan["boss_contract"]["phase_owner"])
                self.assertEqual(donor.wake_animation, plan["boss_contract"]["entry_animation"])
                self.assertEqual(CLERIC_ARENA.destination_count,
                                 len(plan["primary_init_source_bindings"]))
                for binding in plan["primary_init_source_bindings"]:
                    self.assertEqual(donor.map_name, binding["source_map"])
                    self.assertEqual(donor.part_sha256,
                                     binding["source_provenance"]["part_sha256"])
                    self.assertEqual(donor.archetype.npc_param_id,
                                     binding["source_archetype"]["npc_param_id"])
                    self.assertEqual(donor.archetype.think_param_id,
                                     binding["source_archetype"]["think_param_id"])
                    self.assertEqual(SOURCE_INITIALIZATION, binding["source_initialization"])

    def test_rejects_drift_missing_map_state_and_unreviewed_arena(self):
        donor = DONORS["pthumerian-elder"]
        with self.assertRaisesRegex(ValueError, "m29 donor event"):
            patch_chalice_humanoid_donor(
                CLERIC_ARENA, donor, self.destination,
                self.common.replace("SetCharacterInvincibility(chrEntityId, Enabled)",
                                    "SetCharacterInvincibility(chrEntityId, Disabled)"),
            )
        with self.assertRaisesRegex(ValueError, "Cleric arena only"):
            patch_chalice_humanoid_donor(BSB_ARENA, donor, self.destination, self.common)
        destinations = [slot for slot in self.slots if slot.entity_id == CLERIC_ARENA.actor
                        and slot.archetype == CLERIC_ARENA.archetype]
        with self.assertRaisesRegex(ValueError, "every Cleric state"):
            native_plan_chalice_humanoid_donor(
                CLERIC_ARENA, donor, destinations[:-1], self.npcs, self.effects, "missing"
            )

    def test_real_map_constructor_when_local_game_extract_is_available(self):
        directory = ROOT / "work" / "chalice" / "m29-decompiled"
        if not directory.exists():
            self.skipTest("map-specific m29 scripts are not in the distributable input bundle")
        for donor in DONORS.values():
            with self.subTest(donor=donor.key):
                source = (directory / f"{donor.map_name}.emevd.dcx.js").read_text(encoding="utf8")
                validate_source_map_witness(donor, source)


if __name__ == "__main__":
    unittest.main()
