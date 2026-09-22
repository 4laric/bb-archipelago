import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.one_reborn_ebrietas_contract import *


class OneRebornEbrietasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = read_blob(BUNDLE, ONE_REBORN_SOURCE).decode("utf-8-sig")
        cls.arena = read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "slots.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(p)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_full_multipart_combat_closure_and_terminal_boundary(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_one_reborn_at_ebrietas(self.arena, self.donor))
        self.assertEqual(before[12421800], after[12421800])
        self.assertEqual(before[12421801], after[12421801])
        self.assertIn("CreateReferredDamagePair(2420800, 981002);", after[12424802])
        self.assertIn("CreateReferredDamagePair(981000, 981002);", after[12424802])
        self.assertIn(
            "DisplayBossHealthBar(Enabled, 981002, 0, 507000);", after[12424802]
        )
        bridge = after[DEFAULT_IDS.bridge]
        self.assertLess(
            bridge.index("WaitFor(HPRatio(981002) <= 0);"),
            bridge.index("ForceCharacterDeath(2420800, false);"),
        )
        self.assertIn("ForceCharacterDeath(981000, false);", bridge)
        self.assertIn(
            "SetCharacterEventTarget(chrEntityId, 981000);",
            after[DEFAULT_IDS.caster_react],
        )
        self.assertIn("$InitializeEvent(0, 12993219, 981004);", after[0])
        self.assertIn("$InitializeEvent(1, 12993220, 981007);", after[0])
        self.assertIn(
            "RequestCharacterAICommand(981008, 1, 0);", after[DEFAULT_IDS.phase_one]
        )
        self.assertIn("WaitFor(EventFlag(12421800));", after[DEFAULT_IDS.cleanup])

    def test_preserves_destination_celestial_and_retires_model_specific_events(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_one_reborn_at_ebrietas(self.arena, self.donor))
        for event in (12421803,):
            self.assertEqual(before[event], after[event])
        for event in (12424804, 12424870, 12424871, 12424980, 12424990):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        copied = "\n".join(after[e] for e in DEFAULT_IDS.events())
        self.assertNotRegex(
            copied,
            r"(?<!\d)(?:280|1280|1281|1282|1283|1284|1285|1286|1287|1289)\d+(?!\d)",
        )

    def test_entry_music_camera_and_notification_are_adapted_to_destination(self):
        after = event_blocks(patch_one_reborn_at_ebrietas(self.arena, self.donor))
        source = event_blocks(self.donor)
        self.assertIn("CharacterHasEventMessage(2800800, 300)", source[12804803])
        self.assertIn("CharacterHasEventMessage(2420800, 300)", after[12424803])
        self.assertNotIn("ForceAnimationPlayback", after[12421802])
        self.assertNotIn("SetCharacterImmortality", after[12421802])
        self.assertNotIn("5647", after[12421802])
        self.assertIn("HasDamageType(2420800, 10000", after[12421802])
        self.assertEqual(
            2, after[DEFAULT_IDS.camera].count("SetLockcamSlotNumber(24, 2,")
        )
        self.assertNotIn("12804223", after[12424802])
        self.assertIn("SetEventFlag(12993244, ON);", after[12424802])
        self.assertIn("CreatePlaylog(104);", after[12424802])
        self.assertNotIn("CreateBulletOwner(2420801)", after[0])
        self.assertIn(
            "ChangeCharacterEnableState(2420801, Disabled)", after[DEFAULT_IDS.cleanup]
        )

    def test_retired_parameterized_events_keep_compilable_argument_slots(self):
        after = event_blocks(patch_one_reborn_at_ebrietas(self.arena, self.donor))
        original = event_blocks(self.arena)[12424870]
        self.assertIn("function(npcPartId,", original)
        self.assertIn("function(unused_npcPartId,", after[12424870])
        self.assertEqual(
            original.splitlines()[0].count(","),
            after[12424870].splitlines()[0].count(","),
        )

    def test_native_plan_requires_all_nine_helpers_in_both_states(self):
        plan = native_plan_one_reborn_at_ebrietas(
            self.slots, self.npcs, self.effects, "one-reborn-ebrietas"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(18, len(plan["boss_actor_additions"]))
        self.assertEqual(
            {981000, 981001, 981002, 981003, 981004, 981005, 981006, 981007, 981008},
            {r["destination_entity_id"] for r in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            0, plan["boss_contract"]["native_requirements"]["generator_additions"]
        )
        self.assertEqual(
            0, plan["boss_contract"]["native_requirements"]["region_additions"]
        )
        self.assertEqual(18, len(plan["boss_actor_scaling_requirements"]))
        self.assertEqual(
            2,
            sum(
                r["strategy"] == "reviewed_same_source_npc_helper_clone_required"
                for r in plan["boss_actor_scaling_requirements"]
            ),
        )

    def test_rejects_drift_and_colliding_project_event(self):
        with self.assertRaisesRegex(ValueError, "One Reborn donor"):
            patch_one_reborn_at_ebrietas(
                self.arena,
                self.donor.replace(
                    "CreateReferredDamagePair(2800800, 2800803)",
                    "CreateReferredDamagePair(1, 2800803)",
                ),
            )
        with self.assertRaisesRegex(ValueError, "129932xx"):
            patch_one_reborn_at_ebrietas(
                self.arena, self.donor, replace(DEFAULT_IDS, camera=12993203)
            )

    def test_entry_notification_cannot_alias_any_caster_counter_bit(self):
        for bit in range(4):
            with self.subTest(bit=bit), self.assertRaisesRegex(
                ValueError, "collision-free"
            ):
                patch_one_reborn_at_ebrietas(
                    self.arena,
                    self.donor,
                    replace(
                        DEFAULT_IDS,
                        notification_flag=DEFAULT_IDS.caster_count_flag + bit,
                    ),
                )


if __name__ == "__main__":
    unittest.main()
