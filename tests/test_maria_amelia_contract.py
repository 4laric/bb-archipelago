import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.maria_amelia_contract import (
    MariaAmeliaAttachmentIds,
    maria_at_amelia_external_reference_requirement,
    maria_at_amelia_plan,
    native_plan_maria_at_amelia,
    patch_maria_at_amelia,
)
from tools.bb_enemizer.maria_contract import MARIA_EVENT_FILE, MARIA_EVENT_TARGET, MARIA_PACKAGE
from tools.bb_enemizer.boss_contracts import AMELIA_ARENA
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class MariaAmeliaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(BUNDLE, "event/" + MARIA_EVENT_FILE).decode("utf-8-sig")
        cls.amelia = read_blob(BUNDLE, "event/" + AMELIA_ARENA.event_file).decode("utf-8-sig")
        cls.ids = MariaAmeliaAttachmentIds(12414922)

    def test_patch_preserves_amelia_terminal_and_cutscene_while_retaining_only_maria_combat(self):
        before = event_blocks(self.amelia)
        after = event_blocks(patch_maria_at_amelia(self.amelia, self.maria, self.ids))
        self.assertEqual(before[12401800], after[12401800])
        self.assertIn("PlayCutsceneToPlayer(24000060", after[12401802])
        self.assertNotIn("ForceAnimationPlayback(2400800, 7000", after[12401802])
        self.assertNotIn("ForceAnimationPlayback(2400800, 7001", after[12401802])
        self.assertEqual({12414922}, set(after) - set(before))
        self.assertIn("DisplayBossHealthBar(Enabled, 2400800, 0, 452000)", after[12404802])
        self.assertIn("SetCharacterEventTarget(2400800, 3500801)", after[12404802])
        self.assertIn("EntityInRadiusOfEntity(10000, 2400800, 8)", after[12404804])
        self.assertIn("SetLockcamSlotNumber(24, 0, 1)", after[12404804])
        self.assertIn("ClearSpEffect(2400800, 5526)", after[12414922])
        self.assertIn("function(unused_npcPartId, unused_npcPartId2", after[12404810])
        self.assertIn("function(unused_spEffectId", after[12404820])
        self.assertEqual("$Event(12404830, Restart, function() {\n    EndEvent();\n});", after[12404830])
        self.assertNotIn("AwardAchievement(37)", "\n".join(after.values()))
        self.assertNotIn("PlayCutsceneAndWarpPlayer(35000010", "\n".join(after.values()))

    def test_plan_declares_primary_initialization_and_exact_opaque_target_witness(self):
        plan = maria_at_amelia_plan(self.ids)
        self.assertEqual("vicar-amelia", plan["arena"])
        self.assertEqual("lady-maria", plan["donor"])
        opaque = plan["opaque_external_references"]
        self.assertEqual(3500801, opaque[0]["original_source_id"])
        self.assertEqual(12404802, opaque[0]["destination_event"])
        self.assertEqual(2400800, opaque[0]["destination_actor"])
        requirement = maria_at_amelia_external_reference_requirement()
        self.assertEqual(MARIA_EVENT_TARGET, requirement["entity_id"])
        self.assertEqual("m35_00_00_00", requirement["source_map"])
        self.assertEqual("m24_00_", requirement["destination_map_prefix"])
        self.assertEqual((13504802, 3500800),
                         (requirement["source_event_id"], requirement["source_actor"]))
        self.assertEqual((12404802, 2400800),
                         (requirement["destination_event_id"], requirement["destination_actor"]))

    def test_native_plan_covers_both_amelia_states_and_requires_maria_source_init(self):
        with tempfile.TemporaryDirectory() as directory:
            slots_path = Path(directory) / "slots.tsv"
            slots_path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(slots_path)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_maria_at_amelia(slots, npcs, effects, self.ids, "maria-amelia")
        self.assertEqual("bb-enemizer-plan-v2", plan["format"])
        self.assertEqual("c4520", plan["swaps"][0]["target"]["model_name"])
        bindings = plan["primary_init_source_bindings"]
        self.assertEqual(2, len(bindings))
        self.assertEqual({"m24_00_00_00", "m24_00_00_01"},
                         {binding["destination_map"] for binding in bindings})
        self.assertEqual({"m35_00_00_00"}, {binding["source_map"] for binding in bindings})
        self.assertEqual({"c4520_0002"}, {binding["source_part"] for binding in bindings})
        self.assertEqual({"c5020_0000"}, {binding["destination_part"] for binding in bindings})

    def test_adapter_refuses_an_original_literal_as_the_project_owned_cleanup_event(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_maria_at_amelia(self.amelia, self.maria, MariaAmeliaAttachmentIds(12404807))


if __name__ == "__main__":
    unittest.main()
