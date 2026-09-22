import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.maria_contract import (
    MARIA_ARENA, MARIA_EVENT_FILE, MARIA_EVENT_TARGET, MARIA_PACKAGE,
    MariaClericAttachmentIds, MariaTargetBinding, cleric_at_maria_plan,
    maria_at_cleric_plan, patch_maria_at_cleric,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class MariaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(BUNDLE, "event/" + MARIA_EVENT_FILE).decode("utf-8-sig")
        cls.cleric = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")

    def test_package_pins_full_relevant_source_graph(self):
        blocks = event_blocks(self.maria)
        self.assertEqual("c4520", MARIA_PACKAGE.archetype.model_name)
        self.assertEqual(452000, MARIA_PACKAGE.health_bar_label)
        self.assertEqual((13504822,), MARIA_PACKAGE.phase_events)
        self.assertIn("SetCharacterEventTarget(3500800, 3500801)", blocks[13504802])
        self.assertIn("CharacterHasEventMessage(3500800, 100)", blocks[13504803])
        self.assertIn("CharacterHasEventMessage(3500800, 300)", blocks[13504803])
        self.assertIn("ClearSpEffect(3500800, 5526)", blocks[13504822])
        self.assertIn("PlayCutsceneAndWarpPlayer(35000010", blocks[13501801])
        self.assertIn("AwardAchievement(37)", blocks[13501800])

    def test_plan_marks_unplaced_event_target_as_blocking_not_a_generated_id(self):
        plan = maria_at_cleric_plan(MariaClericAttachmentIds(12414922))
        self.assertEqual("blocked-until-event-target-binding", plan["status"])
        self.assertEqual(MARIA_EVENT_TARGET, plan["unresolved"]["source_event_target"])
        self.assertEqual(12414922, plan["attachments"][0]["destination_event"])
        inverse = cleric_at_maria_plan()
        self.assertIn(MARIA_ARENA.completion_event, inverse["preserved_destination_events"])
        self.assertIn(MARIA_ARENA.cutscene_entry_event, inverse["preserved_destination_events"])

    def test_adapter_refuses_to_omit_maria_ai_target(self):
        with self.assertRaisesRegex(ValueError, "unresolved event target 3500801"):
            patch_maria_at_cleric(self.cleric, self.maria, MariaClericAttachmentIds(12414922))

    def test_adapter_preserves_cleric_terminal_and_copies_only_combat_cleanup(self):
        before = event_blocks(self.cleric)
        after = event_blocks(patch_maria_at_cleric(
            self.cleric, self.maria, MariaClericAttachmentIds(12414922),
            MariaTargetBinding(3500801, 2410801, {"kind": "native-pinned-placeholder", "part": "verified-by-writer"}),
        ))
        self.assertEqual(before[12411700], after[12411700])
        self.assertEqual(set(after) - set(before), {12414922})
        self.assertIn("DisplayBossHealthBar(Enabled, 2410800, 0, 452000)", after[12414702])
        self.assertIn("SetCharacterEventTarget(2410800, 2410801)", after[12414702])
        self.assertNotIn("ForceAnimationPlayback(2410800, 3028", after[12411702])
        self.assertIn("EntityInRadiusOfEntity(10000, 2410800, 8)", after[12414704])
        self.assertIn("SetLockcamSlotNumber(24, 1, 1)", after[12414704])
        self.assertIn("ClearSpEffect(2410800, 5526)", after[12414922])
        self.assertNotIn("AwardAchievement(37)", "\n".join(after.values()))
        self.assertNotIn("PlayCutsceneAndWarpPlayer(35000010", "\n".join(after.values()))

    def test_adapter_rejects_any_original_literal_collision(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_maria_at_cleric(
                self.cleric, self.maria, MariaClericAttachmentIds(12414707),
                MariaTargetBinding(3500801, 2410801, {"kind": "test"}),
            )


if __name__ == "__main__":
    unittest.main()
