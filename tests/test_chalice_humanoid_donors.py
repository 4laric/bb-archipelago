"""Static source and destination contracts for three m29 humanoid bosses."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import CLERIC_ARENA
from tools.bb_enemizer.chalice_humanoid_donors import (
    COMMON_EVENT_PINS, DONORS, MARIA_HUMANOID_ARENA,
    SOURCE_INITIALIZATION, SUPPORTED_BASE_ARENAS, SUPPORTED_HUMANOID_ARENAS,
    native_plan_chalice_humanoid_donor, patch_chalice_humanoid_donor,
    validate_source_map_witness,
)
from tools.bb_enemizer.gascoigne_donor import CO_OP_RESTORE_EVENTS
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.model import Slot
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class ChaliceHumanoidDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_HUMANOID_ARENAS
        }
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

    def test_base_and_maria_adapters_preserve_lifecycle_and_native_phase(self):
        self.assertEqual(6, len(SUPPORTED_BASE_ARENAS))
        self.assertEqual(7, len(SUPPORTED_HUMANOID_ARENAS))
        for arena in SUPPORTED_HUMANOID_ARENAS:
            before = event_blocks(self.destinations[arena.key])
            for donor in DONORS.values():
                with self.subTest(arena=arena.key, donor=donor.key):
                    patched = patch_chalice_humanoid_donor(
                        arena, donor, self.destinations[arena.key], self.common
                    )
                    after = event_blocks(patched)
                    self.assertEqual(set(before), set(after))
                    self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                    co_op = (arena.co_op_entry_event if arena == MARIA_HUMANOID_ARENA
                             else CO_OP_RESTORE_EVENTS[arena.key])
                    self.assertEqual(before[co_op], after[co_op])
                    self.assertEqual(before[arena.lockcam_event], after[arena.lockcam_event])
                    self.assertIn(f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, "
                                  f"{donor.health_name_id})", after[arena.health_bar_event])
                    self.assertNotIn("12907230", after[arena.health_bar_event])
                    self.assertIn(f"CharacterHasEventMessage({arena.actor}, 500)",
                                  after[arena.music_event])
                    if arena == MARIA_HUMANOID_ARENA:
                        self.assertNotIn("CharacterHasEventMessage(3500800, 300)",
                                         after[arena.music_event])
                        self.assertIn("SetMapSoundState(3503804, Disabled)",
                                      after[arena.music_event])
                    if donor.wake_animation is not None:
                        self.assertIn(f"ForceAnimationPlayback({arena.actor}, 7001",
                                      after[arena.activation_event])
                    else:
                        self.assertNotIn(f"ForceAnimationPlayback({arena.actor}, 7001",
                                         after[arena.activation_event])
                    self.assertNotIn("PlayCutscene", after[arena.activation_event])
                    retired = [event for event in (*arena.phase_slots, arena.part_routine_event,
                                                   arena.cloth_routine_event, arena.attachment_anchor_event,
                                                   *arena.retired_combat_events)
                               if event is not None and event != co_op]
                    for event in retired:
                        self.assertIn("EndEvent();", after[event])
                        self.assertNotIn("RequestCharacterAICommand", after[event])
                    self.assertNotIn("12904888", patched)

    def test_native_plan_copies_exact_npc_think_and_initialization(self):
        for arena in SUPPORTED_HUMANOID_ARENAS:
            destinations = [slot for slot in self.slots if slot.entity_id == arena.actor
                            and slot.archetype == arena.archetype]
            self.assertEqual(arena.destination_count, len(destinations))
            for donor in DONORS.values():
                with self.subTest(arena=arena.key, donor=donor.key):
                    prototype = destinations[0]
                    source = replace(prototype, map_name=donor.map_name,
                                     part_name=donor.part_name, entity_id=donor.actor,
                                     archetype=donor.archetype)
                    plan = native_plan_chalice_humanoid_donor(
                        arena, donor, [*destinations, source],
                        self.npcs, self.effects, donor.key,
                    )
                    self.assertEqual("bb-enemizer-plan-v2", plan["format"])
                    self.assertEqual(1, plan["swap_count"])
                    self.assertEqual(500, plan["boss_contract"]["phase_music_message"])
                    self.assertEqual("source-native-ai-tae", plan["boss_contract"]["phase_owner"])
                    self.assertEqual(donor.wake_animation, plan["boss_contract"]["entry_animation"])
                    self.assertEqual(arena.destination_count,
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
                CLERIC_ARENA, donor, self.destinations[CLERIC_ARENA.key],
                self.common.replace("SetCharacterInvincibility(chrEntityId, Enabled)",
                                    "SetCharacterInvincibility(chrEntityId, Disabled)"),
            )
        with self.assertRaisesRegex(ValueError, "reviewed base arena"):
            patch_chalice_humanoid_donor(
                replace(CLERIC_ARENA, key="unsupported"), donor,
                self.destinations[CLERIC_ARENA.key], self.common)
        destinations = [slot for slot in self.slots if slot.entity_id == CLERIC_ARENA.actor
                        and slot.archetype == CLERIC_ARENA.archetype]
        with self.assertRaisesRegex(ValueError, "every arena state"):
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
