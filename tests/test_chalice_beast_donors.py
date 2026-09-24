"""Static contracts for Watchdog, Abhorrent Beast, and Beast-possessed Soul."""
from __future__ import annotations

import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import BSB_ARENA, CLERIC_ARENA
from tools.bb_enemizer.chalice_beast_donors import (
    ABHORRENT, ATTACHMENT_IDS, BEAST_POSSESSED_SOUL, DONORS,
    SOURCE_EVENT_SHA256, SOURCE_INITIALIZATION, WATCHDOG,
    chalice_beast_recipes, native_plan_chalice_beast, patch_chalice_beast,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class ChaliceBeastDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + CLERIC_ARENA.event_file).decode("utf-8-sig")
        cls.common = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_explicit_source_handler_pins_and_reserved_ids(self):
        self.assertEqual(3, len(DONORS))
        source = event_blocks(self.common)
        for event, digest in SOURCE_EVENT_SHA256.items():
            self.assertEqual(digest, hashlib.sha256(source[event].encode()).hexdigest())
        self.assertEqual((), BEAST_POSSESSED_SOUL.source_handlers)
        self.assertEqual(5, len(WATCHDOG.source_handlers))
        self.assertEqual(5, len(ABHORRENT.source_handlers))
        self.assertEqual(10, len(set(sum(ATTACHMENT_IDS.values(), ()))))
        self.assertEqual({("cleric-beast", donor.key) for donor in DONORS},
                         {recipe.key for recipe in chalice_beast_recipes()})

    def test_patch_preserves_destination_progression_and_imports_only_combat(self):
        before = event_blocks(self.destination)
        for donor in DONORS:
            with self.subTest(donor=donor.key):
                after = event_blocks(patch_chalice_beast(
                    CLERIC_ARENA, donor, self.destination, self.common))
                ids = set(ATTACHMENT_IDS.get(donor.key, ()))
                self.assertEqual(set(before) | ids, set(after))
                self.assertEqual(before[CLERIC_ARENA.completion_event],
                                 after[CLERIC_ARENA.completion_event])
                self.assertEqual(before[12411703], after[12411703])
                self.assertIn(f"DisplayBossHealthBar(Enabled, 2410800, 0, {donor.health_bar_label})",
                              after[CLERIC_ARENA.health_bar_event])
                self.assertIn("CreatePlaylog(80)", after[CLERIC_ARENA.health_bar_event])
                self.assertNotIn("ForceAnimationPlayback(2410800, 3028",
                                 after[CLERIC_ARENA.activation_event])
                self.assertNotIn("CharacterHasEventMessage(2410800, 100)",
                                 after[CLERIC_ARENA.music_event])
                self.assertIn("EnableBossMapSound(2413802, Enabled)",
                              after[CLERIC_ARENA.music_event])
                for event in (12414707, 12414708, 12414710, 12414720):
                    self.assertIn("EndEvent();", after[event])
                    self.assertNotIn("RequestCharacterAICommand", after[event])
                for event in ids:
                    self.assertIn("RequestCharacterAIReplan", after[event])
                for event in before:
                    if event not in (0, CLERIC_ARENA.activation_event,
                                     CLERIC_ARENA.music_event, CLERIC_ARENA.health_bar_event,
                                     12414707, 12414708, 12414710, 12414720):
                        self.assertEqual(before[event], after[event])

    def test_exact_source_actor_and_three_destination_bindings(self):
        destinations = [row for row in self.slots if row.entity_id == CLERIC_ARENA.actor
                        and row.archetype == CLERIC_ARENA.archetype]
        self.assertEqual(3, len(destinations))
        for donor in DONORS:
            with self.subTest(donor=donor.key):
                source = replace(destinations[0], map_name=donor.source_map,
                                 part_name=donor.source_part, entity_id=donor.source_entity,
                                 archetype=donor.source_archetype)
                plan = native_plan_chalice_beast(CLERIC_ARENA, donor,
                                                   [*destinations, source],
                                                   self.npcs, self.effects, donor.key)
                self.assertEqual(1, plan["swap_count"])
                self.assertEqual(donor.source_map_sha256,
                                 plan["boss_contract"]["source_map_sha256"])
                self.assertEqual(donor.source_constructor_sha256,
                                 plan["boss_contract"]["source_constructor_sha256"])
                self.assertEqual(3, len(plan["primary_init_source_bindings"]))
                for binding in plan["primary_init_source_bindings"]:
                    self.assertEqual(donor.source_part_sha256,
                                     binding["source_provenance"]["part_sha256"])
                    self.assertEqual(SOURCE_INITIALIZATION,
                                     binding["source_initialization"])
                    self.assertEqual(donor.source_archetype.think_param_id,
                                     binding["source_archetype"]["think_param_id"])

    def test_drift_and_unreviewed_arena_fail_closed(self):
        witness = "NPCPartType.Part1, 400, 1, 0.75"
        self.assertIn(witness, self.common)
        with self.assertRaisesRegex(ValueError, "m29 combat handler"):
            patch_chalice_beast(CLERIC_ARENA, WATCHDOG, self.destination,
                                self.common.replace(witness, "NPCPartType.Part1, 401, 1, 0.75", 1))
        with self.assertRaisesRegex(ValueError, "unsupported chalice beast route"):
            patch_chalice_beast(BSB_ARENA, WATCHDOG, self.destination, self.common)
        destinations = [row for row in self.slots if row.entity_id == CLERIC_ARENA.actor
                        and row.archetype == CLERIC_ARENA.archetype]
        with self.assertRaisesRegex(ValueError, "exact original m29 actor"):
            native_plan_chalice_beast(CLERIC_ARENA, WATCHDOG,
                                      destinations, self.npcs, self.effects, "seed")

    def test_local_map_constructor_and_original_model_when_available(self):
        # The map-specific scripts and game binaries are not distributed in the
        # repository; CI still verifies their retained pins and generic handlers.
        directory = ROOT / "work/chalice"
        if not directory.exists():
            self.skipTest("original map-specific chalice extract unavailable")
        for donor in DONORS:
            with self.subTest(donor=donor.key):
                file = directory / donor.source_map / "source" / f"{donor.source_map}.emevd.dcx.js"
                if not file.exists():
                    self.skipTest("map-specific chalice decompile unavailable")
                constructor = event_blocks(file.read_text(encoding="utf-8-sig"))[0]
                self.assertEqual(donor.source_constructor_sha256,
                                 hashlib.sha256(constructor.encode()).hexdigest())
                self.assertIn("$InitializeEvent(0, 12906806, 2900100,", constructor)
                for index, handler in enumerate(donor.source_handlers, start=1):
                    self.assertIn(f"$InitializeEvent(0, {handler}, 2900100, {index}, {index});",
                                  constructor)


if __name__ == "__main__":
    unittest.main()
