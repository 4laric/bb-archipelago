import tempfile
import unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.ludwig_arena import (
    BUNDLE,
    DEFAULT_IDS,
    LudwigClericIds,
    patch_cleric_at_ludwig,
    native_plan_cleric_at_ludwig,
)
from tools.bb_enemizer.scaling import load_params


class ClericLudwigArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ludwig = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        cls.cleric = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )

    def test_preserves_both_m34_terminals_and_defers_phase_two_death(self):
        before = event_blocks(self.ludwig)
        after = event_blocks(patch_cleric_at_ludwig(self.ludwig, self.cleric))
        self.assertEqual(before[13401800], after[13401800])
        self.assertEqual(before[13401850], after[13401850])
        cleanup = after[DEFAULT_IDS.phase_two_cleanup]
        self.assertIn("ChangeCharacterEnableState(3400801, Disabled);", cleanup)
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(13401800));"),
            cleanup.index("ForceCharacterDeath(3400801, false);"),
        )
        self.assertNotIn(
            "ForceCharacterDeath(3400801",
            "\n".join(
                after[x]
                for x in (
                    0,
                    13404802,
                    13404820,
                    13404821,
                    13404822,
                    13404823,
                    13404824,
                    13404825,
                )
            ),
        )

    def test_removes_ludwig_aggregate_combat_and_adds_full_cleric_package(self):
        after = event_blocks(patch_cleric_at_ludwig(self.ludwig, self.cleric))
        before = event_blocks(self.ludwig)
        self.assertNotIn("CreateReferredDamagePair", after[13404802])
        self.assertNotIn("3400801", after[13404802])
        self.assertIn("EndIf(EventFlag(9471));", after[13404802])
        self.assertIn("if (EventFlag(13400999)) {", after[13404802])
        self.assertIn("SetSpEffect(3400800, 8040, false);", after[13404802])
        self.assertIn(
            "DisplayBossHealthBar(Enabled, 3400800, 0, 500000)", after[13404802]
        )
        self.assertIn("CharacterHasEventMessage(3400800, 100)", after[13404803])
        self.assertIn("SetLockcamSlotNumber(34, 0, 1)", after[13404804])
        self.assertNotIn("SetLockcamSlotNumber(24, 1,", after[13404804])
        for event in (
            13404820,
            13404821,
            13404822,
            13404823,
            13404824,
            13404825,
            13404830,
            13404835,
            13404840,
            13404841,
        ):
            self.assertIn("EndEvent();", after[event])
        self.assertIn("HPRatio(3400800) < 0.7", after[DEFAULT_IDS.phase])
        self.assertIn(
            "ChangeCharactersCloth(3400800, 15, 2)", after[DEFAULT_IDS.cloth_phase]
        )
        self.assertIn("CreateNPCPart(3400800", after[DEFAULT_IDS.limbs])
        self.assertIn("ChangeCharacterDispmask(3400800", after[DEFAULT_IDS.cloth])
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.phase)))
        self.assertEqual(5, after[0].count(str(DEFAULT_IDS.limbs)))
        self.assertEqual(5, after[0].count(str(DEFAULT_IDS.cloth)))
        self.assertEqual(before[13401850], after[13401850])

    def test_refuses_original_operand_collision(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_cleric_at_ludwig(
                self.ludwig,
                self.cleric,
                LudwigClericIds(13404820, 12990701, 12990702, 12990703, 12990704),
            )

    def test_native_plan_binds_canonical_talk_zero_cleric(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "i"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(p)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_cleric_at_ludwig(slots, npcs, effects, "ludwig-cleric")
        self.assertEqual("c5000", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m24_01_00_00", binding["source_map"])
        self.assertEqual(0, binding["source_talk_id"])
        self.assertEqual("m34_00_00_00", binding["destination_map"])
        self.assertTrue(plan["scaling"]["enabled"])


if __name__ == "__main__":
    unittest.main()
