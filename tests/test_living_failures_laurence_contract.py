import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.living_failures_laurence_contract import (
    ARENA_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    DONOR_SOURCE,
    LivingFailuresLaurenceIds,
    native_plan_living_failures_at_laurence,
    patch_living_failures_at_laurence,
)
from tools.bb_enemizer.scaling import load_params


class LivingFailuresLaurenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = (
            read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        cls.donor = (
            read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_aggregate_health_and_death_cleanup_preserve_laurence_terminal(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_living_failures_at_laurence(self.arena, self.donor))
        self.assertEqual(before[13401850], after[13401850])
        self.assertIn("WaitFor(CharacterDead(3400850));", after[13401850])
        health = after[13404852]
        self.assertIn("CreateReferredDamagePair(3400850, 980008);", health)
        for body in (980009, 980010, 980011):
            self.assertIn(f"CreateReferredDamagePair({body}, 980008);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 980008, 0, 403000);", health)
        cleanup = after[DEFAULT_IDS.death_cleanup]
        self.assertIn("WaitFor(HPRatio(980008) == 0);", cleanup)
        self.assertIn("ForceCharacterDeath(chrEntityId, true);", cleanup)
        self.assertIn(
            f"$InitializeEvent(0, {DEFAULT_IDS.death_cleanup}, 3400850);", after[0]
        )
        lifecycle = after[DEFAULT_IDS.lifecycle_cleanup]
        self.assertIn("WaitFor(EventFlag(13401850));", lifecycle)
        self.assertEqual(
            {980008, 980009, 980010, 980011},
            {
                int(entity)
                for entity in re.findall(
                    r"ChangeCharacterEnableState\((\d+), Disabled\);", lifecycle
                )
            },
        )
        self.assertEqual(4, lifecycle.count("ForceCharacterDeath("))
        self.assertEqual(
            1,
            after[0].count(f"$InitializeEvent(0, {DEFAULT_IDS.lifecycle_cleanup});"),
        )

    def test_destination_cutscene_fog_progression_and_ludwig_events_are_retained(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_living_failures_at_laurence(self.arena, self.donor))
        for event in (13401800, 13401850, 13404855):
            self.assertEqual(before[event], after[event], event)
        self.assertIn("PlayCutsceneAndWarpPlayer(34000010", after[13401851])
        self.assertIn("PlayerHasItem(ItemType.Goods, 4014)", after[13401851])
        self.assertIn("ForceAnimationPlayback(3400850, 9060", after[13401851])
        self.assertIn("ForceAnimationPlayback(3400850, 9000", after[13404861])
        self.assertNotIn("7001", after[13401851])
        self.assertNotIn("7002", after[13404861])
        for event in range(13404820, 13404826):
            self.assertEqual(before[event], after[event], event)

    def test_full_controller_closure_has_mapped_generators_support_music_and_camera(
        self,
    ):
        after = event_blocks(patch_living_failures_at_laurence(self.arena, self.donor))
        for event in DEFAULT_IDS.event_values():
            self.assertRegex(
                after[0], rf"\$InitializeEvent\([^,]+, {event}(?:,|\))", event
            )
        for generator in range(980013, 980017):
            self.assertIn(
                f"DeactivateGenerator({generator}, Disabled);",
                after[DEFAULT_IDS.generator_schedule],
            )
        support = after[DEFAULT_IDS.support_controller]
        self.assertIn("RequestCharacterAICommand(980012, 40, 0);", support)
        self.assertIn("CharacterHasEventMessage(980011, 40)", support)
        camera = after[13404854]
        self.assertIn("SetLockcamSlotNumber(34, 0, 1);", camera)
        self.assertIn("SetLockcamSlotNumber(34, 0, 0);", camera)
        self.assertNotIn("SetLockcamSlotNumber(35,", camera)
        music = after[13404853]
        self.assertIn("SetMapSoundState(3403852, Disabled);", music)
        self.assertIn("InArea(10000, 3402852)", music)
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase_music_flag})", music)
        self.assertNotIn("13501800", music)
        copied = "\n".join(
            after[event]
            for event in (13404852, 13404853, 13404854, *DEFAULT_IDS.event_values())
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:135|350)\d+(?!\d)")

    def test_native_plan_declares_all_pinned_actor_region_generator_and_sfx_requirements(
        self,
    ):
        plan = native_plan_living_failures_at_laurence(
            self.slots, self.npcs, self.effects, "lf-laurence"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(5, len(plan["boss_actor_additions"]))
        self.assertEqual(
            {980008, 980009, 980010, 980011, 980012},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        for addition in plan["boss_actor_additions"]:
            self.assertRegex(
                addition["source_provenance"]["part_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertRegex(
                addition["source_provenance"]["anchor_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertEqual("c4500_0000", addition["destination_anchor_part"])
        self.assertEqual(5, len(plan["boss_region_additions"]))
        self.assertEqual(
            {
                "ap_lf_spawn_1",
                "ap_lf_spawn_2",
                "ap_lf_spawn_3",
                "ap_lf_spawn_4",
                "ap_lf_universe_sfx",
            },
            {row["destination_region"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(4, len(plan["boss_generator_additions"]))
        self.assertEqual(
            {980013, 980014, 980015, 980016},
            {row["destination_entity_id"] for row in plan["boss_generator_additions"]},
        )
        for generator in plan["boss_generator_additions"]:
            self.assertEqual("h000027", generator["destination_part_name"])
            self.assertEqual(1, len(generator["spawn_part_map"]))
            self.assertEqual(1, len(generator["spawn_point_map"]))
        self.assertEqual(5, len(plan["boss_sfx_additions"]))
        self.assertEqual(
            {640320, 640321, 640322, 640323, 640324},
            {row["effect_id"] for row in plan["boss_sfx_additions"]},
        )
        self.assertEqual(
            {144, 145, 146, 147, 148},
            {row["source_event_id"] for row in plan["boss_sfx_additions"]},
        )
        self.assertEqual(
            {980032, 980033, 980034, 980035, 980036},
            {row["destination_event_id"] for row in plan["boss_sfx_additions"]},
        )
        merge = plan["boss_ffx_merges"][0]
        self.assertEqual("preserve_destination_union_source_v1", merge["policy"])
        self.assertEqual(
            [640320, 640321, 640322, 640323, 640324], merge["required_effect_ids"]
        )
        self.assertRegex(merge["source_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(merge["destination_sha256"], r"^[0-9a-f]{64}$")
        for sfx in plan["boss_sfx_additions"]:
            self.assertRegex(
                sfx["source_provenance"]["event_sha256"], r"^[0-9a-f]{64}$"
            )
            self.assertEqual("c4500_0000", sfx["destination_anchor_part"])
        self.assertEqual(
            "not_integrated_pending_builder_ffx_receipt",
            plan["boss_contract"]["writer_status"],
        )
        self.assertTrue(plan["scaling"]["enabled"])

    def test_pinned_drift_and_allocation_collisions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "allocation collides"):
            patch_living_failures_at_laurence(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, player_effect=DEFAULT_IDS.wave_selection),
            )
        with self.assertRaisesRegex(ValueError, "Living Failures donor"):
            patch_living_failures_at_laurence(
                self.arena,
                self.donor.replace(
                    "HPRatio(3500850) < 0.6", "HPRatio(3500850) < 0.5", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "Laurence arena"):
            patch_living_failures_at_laurence(
                self.arena.replace("HandleBossDefeat(3400850)", "HandleBossDefeat(7)"),
                self.donor,
            )

    def test_exact_installed_event_zero_alternate_is_accepted(self):
        installed = self.donor
        for bundled, original in (
            (
                "$InitializeEvent(12, 13501200, 3501170, 13504270, 1, 3500070, 0, -1);",
                "$InitializeEvent(13, 13501200, 3501170, 13504270, 1, 3500070, 0, -1);",
            ),
            (
                "    $InitializeEvent(0, 13500460, 3500930, 103170);\n"
                "    $InitializeEvent(1, 13500460, 3500941, 103152);",
                "    $InitializeEvent(0, 13500460, 3500930, 103170, 13501900);",
            ),
            (
                "$InitializeEvent(0, 13505900, 13505910, 13505911, 13505912, 3502890, 0, 0);",
                "$InitializeEvent(0, 13505900, 13505910, 13505911, 13505912, 3502890, 0, 6001);",
            ),
            (
                "    $InitializeEvent(0, 13504460, 3500940, 3502930, 3502810, 3502811, 101130, 13504450, 3502813);\n});",
                "    $InitializeEvent(0, 13504460, 3500940, 3502930, 3502810, 3502811, 101130, 13504450, 3502813);\n"
                "    $InitializeEvent(0, 13500000);\n});",
            ),
        ):
            self.assertEqual(1, installed.count(bundled))
            installed = installed.replace(bundled, original, 1)
        patch_living_failures_at_laurence(self.arena, installed)


if __name__ == "__main__":
    unittest.main()
