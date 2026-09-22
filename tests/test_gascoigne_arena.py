import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.gascoigne_arena import (
    BUNDLE,
    ClericGascoigneIds,
    native_plan_cleric_at_gascoigne,
    patch_cleric_at_gascoigne,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class ClericGascoigneArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")
        cls.ids = ClericGascoigneIds(12990400, 12990401, 12990402, 12990403, 12990404)

    def test_preserves_gascoigne_or_terminal_and_cutscene_without_premature_beast_death(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_cleric_at_gascoigne(self.source, self.source, self.ids))
        self.assertEqual(before[12411800], after[12411800])
        self.assertEqual(before[12411802], after[12411802])
        self.assertEqual(set(after) - set(before), set(self.ids.values()))
        cleanup = after[self.ids.beast_cleanup]
        self.assertIn("ChangeCharacterEnableState(2410811, Disabled);", cleanup)
        self.assertIn("WaitFor(EventFlag(12411800));", cleanup)
        self.assertLess(cleanup.index("WaitFor(EventFlag(12411800));"),
                        cleanup.index("ForceCharacterDeath(2410811, false);"))
        self.assertNotIn("ForceCharacterDeath(2410811", "\n".join(
            after[event] for event in (0, 12411802, 12414802, 12414807, 12414808, 12414809)))

    def test_replaces_only_paired_health_branch_and_suppresses_all_gascoigne_phase_events(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_cleric_at_gascoigne(self.source, self.source, self.ids))
        self.assertNotIn("CreateReferredDamagePair", after[12414802])
        self.assertNotIn("2410811", after[12414802])
        self.assertIn("SetCharacterAIState(2410810, Enabled);", after[12414802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2410810, 0, 500000)", after[12414802])
        self.assertIn("CharacterHasEventMessage(2410810, 100)", after[12414803])
        for event in (12414807, 12414808, 12414809):
            self.assertIn("EndEvent();", after[event])
            self.assertNotIn("WarpCharacterAndCopyFloor", after[event])
        self.assertEqual(before[12414804], after[12414804])

    def test_copies_all_twelve_cleric_initializer_witnesses_to_explicit_owned_events(self):
        after = event_blocks(patch_cleric_at_gascoigne(self.source, self.source, self.ids))
        self.assertEqual(1, after[0].count("12990400"))
        self.assertEqual(1, after[0].count("12990401"))
        self.assertEqual(5, after[0].count("12990402"))
        self.assertEqual(5, after[0].count("12990403"))
        self.assertEqual(1, after[0].count("12990404"))
        self.assertIn("HPRatio(2410810) < 0.7", after[12990400])
        self.assertIn("ChangeCharactersCloth(2410810, 15, 2)", after[12990401])
        self.assertIn("CreateNPCPart(2410810", after[12990402])
        self.assertIn("ChangeCharacterDispmask(2410810", after[12990403])

    def test_native_plan_imports_cleric_talk_zero_over_gascoigne_talk_241330_for_all_states(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_cleric_at_gascoigne(slots, npcs, effects, self.ids, "cleric-gascoigne")
        self.assertEqual("c5000", plan["swaps"][0]["target"]["model_name"])
        bindings = plan["primary_init_source_bindings"]
        self.assertEqual(3, len(bindings))
        self.assertEqual({"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"},
                         {binding["destination_map"] for binding in bindings})
        self.assertEqual({0}, {binding["source_talk_id"] for binding in bindings})
        self.assertEqual({241330}, {binding["destination_original_talk_id"] for binding in bindings})

    def test_refuses_a_project_event_id_already_present_in_the_original_corpus(self):
        ids = ClericGascoigneIds(12414807, 12990401, 12990402, 12990403, 12990404)
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_cleric_at_gascoigne(self.source, self.source, ids)


if __name__ == "__main__":
    unittest.main()
