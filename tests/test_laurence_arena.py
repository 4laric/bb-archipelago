import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.laurence_arena import (
    BUNDLE, DEFAULT_IDS, LAURENCE_COMPLETION, LaurenceClericIds,
    patch_cleric_at_laurence, native_plan_cleric_at_laurence,
)
from tools.bb_enemizer.scaling import load_params


class ClericLaurenceArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laurence = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        cls.cleric = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")

    def test_preserves_laurence_and_ludwig_completion_progression(self):
        before = event_blocks(self.laurence)
        after = event_blocks(patch_cleric_at_laurence(self.laurence, self.cleric))
        self.assertEqual(before[13401800], after[13401800])
        self.assertEqual(before[LAURENCE_COMPLETION], after[LAURENCE_COMPLETION])
        self.assertIn("PlayerHasItem(ItemType.Goods, 4014)", after[13401851])
        self.assertIn("PlayCutsceneAndWarpPlayer(34000010", after[13401851])
        self.assertIn("ForceAnimationPlayback(3400850, 3028", after[13401851])
        self.assertNotIn("ForceAnimationPlayback(3400850, 7002", after[13404861])

    def test_maps_full_cleric_combat_and_destination_camera_without_m24_leak(self):
        after = event_blocks(patch_cleric_at_laurence(self.laurence, self.cleric))
        self.assertIn("DisplayBossHealthBar(Enabled, 3400850, 0, 500000)", after[13404852])
        self.assertIn("CharacterHasEventMessage(3400850, 100)", after[13404853])
        self.assertIn("SetLockcamSlotNumber(34, 0, 1)", after[13404854])
        self.assertNotIn("SetLockcamSlotNumber(24, 1,", after[13404854])
        self.assertIn("HPRatio(3400850) < 0.7", after[DEFAULT_IDS.phase])
        self.assertIn("ChangeCharactersCloth(3400850, 15, 2)", after[DEFAULT_IDS.cloth_phase])
        self.assertIn("CreateNPCPart(3400850", after[13404870])
        self.assertIn("ChangeCharacterDispmask(3400850", after[13404875])
        self.assertEqual(5, after[0].count("13404870"))
        self.assertEqual(5, after[0].count("13404875"))
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.phase)))
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.cloth_phase)))
        before = event_blocks(self.laurence)
        for event in (13404820, 13404821, 13404822, 13404823, 13404824, 13404825):
            self.assertEqual(before[event], after[event])

    def test_rejects_pinned_source_drift(self):
        changed = self.laurence.replace("DisplayBossHealthBar(Enabled, 3400850, 0, 450000)",
                                        "DisplayBossHealthBar(Enabled, 3400850, 0, 1)")
        with self.assertRaisesRegex(ValueError, "unsupported original Laurence arena"):
            patch_cleric_at_laurence(changed, self.cleric)

    def test_rejects_project_event_ids_present_in_the_original_corpus(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_cleric_at_laurence(self.laurence, self.cleric,
                                     LaurenceClericIds(13404820, DEFAULT_IDS.cloth_phase))

    def test_native_plan_binds_the_canonical_cleric_talk_zero_source(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_cleric_at_laurence(slots, npcs, effects, "cleric-laurence")
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5000", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m24_01_00_00", binding["source_map"])
        self.assertEqual(0, binding["source_talk_id"])
        self.assertEqual("m34_00_00_00", binding["destination_map"])
        self.assertEqual(0, binding["destination_original_talk_id"])


if __name__ == "__main__":
    unittest.main()
