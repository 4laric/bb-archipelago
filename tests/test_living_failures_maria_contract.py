import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.living_failures_maria_contract import (
    ARENA_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    LivingFailuresMariaIds,
    living_failures_maria_helper_scaling_parents,
    native_plan_living_failures_at_maria,
    patch_living_failures_at_maria,
)
from tools.bb_enemizer.scaling import load_params


class LivingFailuresMariaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_maria_terminal_entry_fog_coop_and_progression_are_retained(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_living_failures_at_maria(self.source, self.source))
        for event in (13501800, 13501807, 13504800, 13504801, 13504805):
            self.assertEqual(before[event], after[event], event)
        self.assertIn("PlayCutsceneAndWarpPlayer(35000010", after[13501801])
        self.assertIn("ForceAnimationPlayback(3500800, 9000", after[13501801])
        self.assertIn("ForceAnimationPlayback(3500800, 9060", after[13501801])
        self.assertIn("AwardAchievement(37)", after[13501800])
        self.assertIn("SetEventFlag(6675, ON)", after[13501800])
        self.assertNotIn("CharacterHasEventMessage", after[13504822])

    def test_aggregate_health_death_and_completed_load_cleanup_cover_owned_bodies(self):
        after = event_blocks(patch_living_failures_at_maria(self.source, self.source))
        health = after[13504802]
        self.assertIn("CreateReferredDamagePair(3500800, 980400);", health)
        for actor in (980401, 980402, 980403):
            self.assertIn(f"CreateReferredDamagePair({actor}, 980400);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 980400, 0, 403000);", health)
        death = after[DEFAULT_IDS.death_cleanup]
        self.assertIn("WaitFor(HPRatio(980400) == 0);", death)
        self.assertIn("ForceCharacterDeath(chrEntityId, true);", death)
        cleanup = after[DEFAULT_IDS.lifecycle_cleanup]
        self.assertIn("WaitFor(EventFlag(13501800));", cleanup)
        self.assertEqual(
            {980400, 980401, 980402, 980403},
            {
                int(actor)
                for actor in re.findall(
                    r"ChangeCharacterEnableState\((\d+), Disabled\);", cleanup
                )
            },
        )
        self.assertNotIn("980404", cleanup)

    def test_controller_initializers_music_camera_generators_and_support_are_closed(
        self,
    ):
        after = event_blocks(patch_living_failures_at_maria(self.source, self.source))
        for event in DEFAULT_IDS.event_values():
            self.assertRegex(after[0], rf"\$InitializeEvent\([^,]+, {event}(?:,|\))")
        music = after[13504803]
        self.assertIn("SetMapSoundState(3503802, Disabled);", music)
        self.assertIn("SetMapSoundState(3503803, Disabled);", music)
        self.assertIn("InArea(10000, 3502802)", music)
        self.assertIn("EndIf(EventFlag(13501800));", music)
        self.assertNotIn("SetMapSoundState(980405", music)
        camera = after[13504804]
        self.assertIn("SetLockcamSlotNumber(35, 0, 1);", camera)
        self.assertIn("CharacterDead(980400)", camera)
        for generator in (980405, 980406, 980407, 980408):
            self.assertIn(
                f"DeactivateGenerator({generator}, Disabled);",
                after[DEFAULT_IDS.generator_schedule],
            )
        self.assertIn(
            "RequestCharacterAICommand(980404, 40, 0);",
            after[DEFAULT_IDS.support_controller],
        )

    def test_native_plan_has_explicit_relocated_physical_graph_and_same_bank_receipt(
        self,
    ):
        plan = native_plan_living_failures_at_maria(
            self.slots, self.npcs, self.effects, "lf-maria"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(
            {980400, 980401, 980402, 980403, 980404},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {
                "ap_lfm_spawn_1",
                "ap_lfm_spawn_2",
                "ap_lfm_spawn_3",
                "ap_lfm_spawn_4",
                "ap_lfm_universe_sfx",
            },
            {row["destination_region"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(4, len(plan["boss_generator_additions"]))
        self.assertEqual(5, len(plan["boss_sfx_additions"]))
        self.assertEqual(
            {"h000060"},
            {
                row["destination_part_name"]
                for row in (
                    *plan["boss_generator_additions"],
                    *plan["boss_sfx_additions"],
                )
            },
        )
        for row in (
            *plan["boss_actor_additions"],
            *plan["boss_region_additions"],
            *plan["boss_sfx_additions"],
        ):
            self.assertEqual("c4520_0002", row["destination_anchor_part"])
        merge = plan["boss_ffx_merges"][0]
        self.assertEqual(merge["source_file"], merge["destination_file"])
        self.assertEqual(merge["source_sha256"], merge["destination_sha256"])
        self.assertEqual(
            [640320, 640321, 640322, 640323, 640324],
            merge["required_effect_ids"],
        )
        self.assertEqual("preserve_destination_union_source_v1", merge["policy"])
        parents = living_failures_maria_helper_scaling_parents(plan)
        self.assertEqual(5, len(parents))
        self.assertEqual({plan["swaps"][0]["logical_key"]}, set(parents.values()))

    def test_exact_constructor_multiplicity_and_project_namespace(self):
        after = event_blocks(patch_living_failures_at_maria(self.source, self.source))
        expected_counts = {
            DEFAULT_IDS.player_effect: 1,
            DEFAULT_IDS.wave_selection: 1,
            DEFAULT_IDS.wave_commands: 1,
            DEFAULT_IDS.wave_animation: 2,
            DEFAULT_IDS.wave_reset: 4,
            DEFAULT_IDS.death_cleanup: 4,
            DEFAULT_IDS.generator_schedule: 1,
            DEFAULT_IDS.combat_tracker: 4,
            DEFAULT_IDS.combat_counter: 1,
            DEFAULT_IDS.generator_controller: 1,
            DEFAULT_IDS.support_controller: 1,
            DEFAULT_IDS.lifecycle_cleanup: 1,
        }
        for event, count in expected_counts.items():
            self.assertEqual(
                count,
                len(
                    re.findall(rf"\$InitializeEvent\([^,]+, {event}(?:,|\))", after[0])
                ),
                event,
            )
        self.assertEqual(
            set(DEFAULT_IDS.event_values()),
            {event for event in after if 12992400 <= event <= 12992499},
        )

    def test_source_drift_and_allocation_collisions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "allocation collides"):
            patch_living_failures_at_maria(
                self.source,
                self.source,
                replace(DEFAULT_IDS, player_effect=DEFAULT_IDS.wave_selection),
            )
        with self.assertRaisesRegex(ValueError, "Living Failures donor"):
            patch_living_failures_at_maria(
                self.source,
                self.source.replace(
                    "HPRatio(3500850) < 0.6", "HPRatio(3500850) < 0.5", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "Maria arena"):
            patch_living_failures_at_maria(
                self.source.replace("AwardAchievement(37)", "AwardAchievement(7)"),
                self.source,
            )


if __name__ == "__main__":
    unittest.main()
