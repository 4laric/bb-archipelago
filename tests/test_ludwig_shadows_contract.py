import tempfile, unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.ludwig_shadows_contract import *


class LudwigShadowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
        cls.d = read_blob(BUNDLE, LUDWIG_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "slots.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(p)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_terminal_rewards_and_three_body_predicate_are_retained(self):
        before = event_blocks(self.a)
        after = event_blocks(patch_ludwig_at_shadows(self.a, self.d))
        self.assertEqual(before[12701800], after[12701800])
        self.assertEqual(before[12701801], after[12701801])
        terminal = after[12701800]
        self.assertIn(
            "CharacterDead(2700800) && CharacterDead(2700801) && CharacterDead(2700802)",
            terminal,
        )
        bridge = after[DEFAULT_IDS.bridge]
        self.assertIn("ForceCharacterDeath(2700801, false);", bridge)
        self.assertIn("ForceCharacterDeath(2700802, false);", bridge)
        self.assertLess(
            bridge.index("ForceCharacterDeath(2700802, false);"),
            bridge.index("ForceCharacterDeath(2700800, false);"),
        )

    def test_retires_all_shadows_specific_group_and_snake_controllers(self):
        after = event_blocks(patch_ludwig_at_shadows(self.a, self.d))
        for event in (
            12704806,
            12704807,
            12704810,
            12704811,
            12704812,
            12704815,
            12704825,
            12704830,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        health = after[12704802]
        self.assertIn("SetCharacterAIState(981200, Disabled);", health)
        self.assertIn("ChangeCharacterEnableState(981200, Disabled);", health)
        for entity in (2705001, 2705002, 2705003):
            self.assertIn(f"DeactivateGenerator({entity}, Disabled);", health)
        for entity in (2700803, 2700804, 2700805, 2700810, 2700811, 2700813, 2700814):
            self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled);", health)
        self.assertIn("CreatePlaylog(82);", health)
        self.assertIn("StartTimeMeasurement(2700010, 98, Enabled);", health)
        self.assertIn("SetLockcamSlotNumber(27, 0,", after[12704804])
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase_flag})", after[12704803])
        self.assertNotIn("ForceAnimationPlayback(2700800", after[12701802])

    def test_native_plan_has_two_phase_additions_and_four_retained_primaries(self):
        p = native_plan_ludwig_at_shadows(
            self.slots, self.npcs, self.effects, "ludwig-shadows"
        )
        self.assertEqual(2, len(p["boss_actor_additions"]))
        self.assertEqual(4, len(p["boss_contract"]["retained_destination_helpers"]))
        self.assertEqual(
            {"m27_00_00_00", "m27_00_00_01"},
            {x["destination_map"] for x in p["boss_actor_additions"]},
        )
        self.assertEqual(
            {"m27_00_00_00", "m27_00_00_01"},
            {x["map"] for x in p["boss_contract"]["retained_destination_helpers"]},
        )
        self.assertEqual(
            12993441,
            p["boss_contract"]["event_ids"]["entry_notified_flag"],
        )

    def test_refuses_source_or_destination_drift(self):
        with self.assertRaisesRegex(ValueError, "Ludwig donor"):
            patch_ludwig_at_shadows(
                self.a,
                self.d.replace(
                    "SetCharacterAIState(3400800, Disabled);",
                    "SetCharacterAIState(1, Disabled);",
                    1,
                ),
            )
        with self.assertRaisesRegex(ValueError, "129934xx"):
            patch_ludwig_at_shadows(
                self.a, self.d, replace(DEFAULT_IDS, bridge=12993420)
            )

    def test_installed_quest_initializer_variant_is_preserved(self):
        installed = self.a.replace(
            "    $InitializeEvent(0, 12700907);",
            "    $InitializeEvent(0, 12700910);",
        )
        after = event_blocks(patch_ludwig_at_shadows(installed, self.d))
        self.assertIn("$InitializeEvent(0, 12700910);", after[0])
        self.assertNotIn("$InitializeEvent(0, 12700907);", after[0])
        self.assertEqual(event_blocks(installed)[12701800], after[12701800])


if __name__ == "__main__":
    unittest.main()
