import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.witch_amygdala_contract import (
    AMYGDALA_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    WITCH_SOURCE,
    native_plan_witch_at_amygdala,
    patch_witch_at_amygdala,
)


class WitchAmygdalaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, AMYGDALA_SOURCE).decode("utf-8-sig")
        cls.witch = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_pair_revival_and_terminal_lifecycle_keep_both_witches(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_witch_at_amygdala(self.arena, self.witch))
        start = after[DEFAULT_IDS.second_start]
        self.assertIn("WaitFor(HPRatio(3300800) <= 0.5);", start)
        self.assertIn("ChangeCharacterEnableState(980800, Enabled);", start)
        revival = after[DEFAULT_IDS.revival]
        constructor = after[0]
        self.assertIn(
            "$InitializeEvent(0, 12993004, 3300800, 980800, 980810, 12993040);",
            constructor,
        )
        self.assertIn(
            "$InitializeEvent(1, 12993004, 980800, 3300800, 980815, 12993041);",
            constructor,
        )
        self.assertIn("SetCharacterImmortality(chrEntityId, Enabled);", revival)
        self.assertIn("ForceCharacterDeath(chrEntityId, false);", revival)
        self.assertIn("ForceCharacterDeath(chrEntityId2, false);", revival)
        self.assertIn(
            "IssueShortWarpRequest(chrEntityId, TargetEntityType.Area", revival
        )
        cleanup = after[DEFAULT_IDS.completion_cleanup]
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(13301800));"),
            cleanup.index("ForceCharacterDeath(980800, false);"),
        )
        self.assertEqual(before[13301800], after[13301800])
        self.assertIn("WaitFor(CharacterDead(3300800));", after[13301800])

    def test_source_combat_replaces_model_specific_amygdala_controllers(self):
        after = event_blocks(patch_witch_at_amygdala(self.arena, self.witch))
        activation = after[13301802]
        self.assertIn("ChangeCharacterEnableState(3300800, Disabled);", activation)
        self.assertIn("ForceAnimationPlayback(3300800, 3011", activation)
        self.assertNotIn("ForceAnimationPlayback(3300800, 7003", activation)
        music = after[13304803]
        self.assertIn("SetMapSoundState(3303802, Disabled);", music)
        self.assertIn(
            "CharacterHPValue(3300800) == 1 || CharacterHPValue(980800) == 1", music
        )
        self.assertIn("SetLockcamSlotNumber(33, 0, 1);", after[13304804])
        for event in (13304807, 13304808, 13304820, 13304830, 13304840):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        copied = "\n".join(after[event] for event in DEFAULT_IDS.events())
        self.assertNotRegex(copied, r"(?<!\d)(?:122|220)\d+(?!\d)")

    def test_native_plan_requires_full_actor_region_and_generator_closure(self):
        plan = native_plan_witch_at_amygdala(
            self.slots, self.npcs, self.effects, "witch-amygdala"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c2100", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(4, len(plan["boss_actor_additions"]))
        self.assertEqual(
            {980800, 980801, 980802, 980803},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(20, len(plan["boss_region_additions"]))
        self.assertEqual(
            set(range(980810, 980818)) | set(range(980820, 980832)),
            {row["destination_entity_id"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(3, len(plan["boss_generator_additions"]))
        for index, generator in enumerate(plan["boss_generator_additions"]):
            self.assertEqual("h002301", generator["destination_part_name"])
            self.assertEqual(
                {f"ap_witch_spawn_{4 * index + n:02d}" for n in range(4)},
                set(generator["spawn_point_map"].values()),
            )
            self.assertEqual(
                {f"ap_witch_minion_{index}"}, set(generator["spawn_part_map"].values())
            )
        self.assertEqual(
            {
                "actor_additions",
                "region_additions",
                "generator_additions",
                "generator_collision",
                "destination_anchor",
            },
            set(plan["boss_contract"]["native_requirements"]),
        )
        self.assertEqual(
            {"map": "m33_00_00_00", "part": "c5120_0001", "collision_name": "h002301"},
            {
                key: plan["boss_contract"]["native_requirements"]["destination_anchor"][
                    key
                ]
                for key in ("map", "part", "collision_name")
            },
        )

    def test_collision_and_source_or_destination_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129930xx"):
            patch_witch_at_amygdala(
                self.arena,
                self.witch,
                replace(DEFAULT_IDS, insight_flag=DEFAULT_IDS.phase),
            )
        with self.assertRaisesRegex(ValueError, "129930xx"):
            patch_witch_at_amygdala(
                self.arena,
                self.witch,
                replace(
                    DEFAULT_IDS,
                    insight_flag=DEFAULT_IDS.minion_count_flag + 1,
                ),
            )
        with self.assertRaisesRegex(ValueError, "helper IDs"):
            patch_witch_at_amygdala(
                self.arena,
                self.witch,
                replace(
                    DEFAULT_IDS, generator_entity_first=DEFAULT_IDS.spawn_first_entity
                ),
            )
        with self.assertRaisesRegex(ValueError, "Amygdala arena"):
            patch_witch_at_amygdala(
                self.arena.replace("HandleBossDefeat(3300800)", "HandleBossDefeat(7)"),
                self.witch,
            )
        with self.assertRaisesRegex(ValueError, "Witch donor"):
            patch_witch_at_amygdala(
                self.arena,
                self.witch.replace(
                    "WaitFor(HPRatio(2200800) <= 0.5);", "WaitFor(HPRatio(1) <= 0.5);"
                ),
            )


if __name__ == "__main__":
    unittest.main()
