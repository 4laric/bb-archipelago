import unittest
import tempfile
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.maria_contract import (
    MARIA_ARENA, MARIA_EVENT_FILE, MARIA_EVENT_TARGET, MARIA_PACKAGE, MariaClericAttachmentIds, ClericMariaAttachmentIds, patch_cleric_at_maria, native_plan_maria_at_cleric, native_plan_cleric_at_maria,
    maria_at_cleric_plan, cleric_at_maria_plan, patch_maria_at_cleric,
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

    def test_plan_preserves_unplaced_event_target_as_opaque_literal(self):
        plan = maria_at_cleric_plan(MariaClericAttachmentIds(12414922))
        self.assertEqual("experimental", plan["status"])
        self.assertEqual(MARIA_EVENT_TARGET, plan["opaque_external_references"][0]["original_source_id"])
        self.assertEqual(12414922, plan["attachments"][0]["destination_event"])
        inverse = cleric_at_maria_plan()
        self.assertIn(MARIA_ARENA.completion_event, inverse["preserved_destination_events"])
        self.assertIn(MARIA_ARENA.cutscene_entry_event, inverse["preserved_destination_events"])

    def test_installed_patch_health_authority_is_preserved_and_unknown_source_refused(self):
        blocks = event_blocks(self.maria)
        health = blocks[13504802]
        patched = self.maria.replace('\r\n', '\n').replace(
            health, health.replace('AuthorityLevel.Normal', 'AuthorityLevel.Forced'))
        ids = ClericMariaAttachmentIds(13504907, 13504908, 13504910, 13504920)
        result = event_blocks(patch_cleric_at_maria(patched, self.cleric, ids))
        self.assertIn('SetNetworkUpdateAuthority(3500800, AuthorityLevel.Forced)', result[13504802])
        self.assertIn('DisplayBossHealthBar(Enabled, 3500800, 0, 500000)', result[13504802])
        corrupt = patched.replace('SetNetworkUpdateAuthority(3500800, AuthorityLevel.Forced)',
                                  'SetNetworkUpdateAuthority(3500801, AuthorityLevel.Forced)')
        with self.assertRaisesRegex(ValueError, 'unsupported original Maria arena event 13504802'):
            patch_cleric_at_maria(corrupt, self.cleric, ids)

    def test_adapter_preserves_cleric_terminal_and_copies_only_combat_cleanup(self):
        before = event_blocks(self.cleric)
        after = event_blocks(patch_maria_at_cleric(
            self.cleric, self.maria, MariaClericAttachmentIds(12414922),
        ))
        self.assertEqual(before[12411700], after[12411700])
        self.assertEqual(set(after) - set(before), {12414922})
        self.assertIn("DisplayBossHealthBar(Enabled, 2410800, 0, 452000)", after[12414702])
        self.assertIn("SetCharacterEventTarget(2410800, 3500801)", after[12414702])
        self.assertNotIn("ForceAnimationPlayback(2410800, 3028", after[12411702])
        self.assertIn("EntityInRadiusOfEntity(10000, 2410800, 8)", after[12414704])
        self.assertIn("SetLockcamSlotNumber(24, 1, 1)", after[12414704])
        self.assertIn("ClearSpEffect(2410800, 5526)", after[12414922])
        self.assertIn("function(unused_npcPartId, unused_npcPartId2", after[12414710])
        self.assertIn("function(unused_spEffectId", after[12414720])
        self.assertNotIn("AwardAchievement(37)", "\n".join(after.values()))
        self.assertNotIn("PlayCutsceneAndWarpPlayer(35000010", "\n".join(after.values()))

    def test_cleric_at_maria_preserves_terminal_cutscene_and_appends_combat(self):
        before = event_blocks(self.maria)
        after = event_blocks(patch_cleric_at_maria(self.maria, self.cleric,
            ClericMariaAttachmentIds(13504907, 13504908, 13504910, 13504920)))
        self.assertEqual(before[13501800], after[13501800])
        self.assertEqual(before[13501801], after[13501801])
        self.assertIn("CreateNPCPart(3500800", after[13504910])
        self.assertIn("ChangeCharactersCloth(3500800", after[13504908])
        self.assertEqual(5, after[0].count("13504910"))
        self.assertEqual(5, after[0].count("13504920"))
        self.assertIn("$InitializeEvent(0, 13504907);", after[0])
        self.assertNotIn("SetCharacterEventTarget(3500800, 3500801)", after[13504802])
        self.assertEqual("$Event(13504822, Default, function() {\n    EndEvent();\n});", after[13504822])

    def test_reciprocal_native_plans_use_inventory_and_preserve_progression_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        forward = native_plan_maria_at_cleric(slots, npcs, effects, MariaClericAttachmentIds(12414922), "maria")
        reverse = native_plan_cleric_at_maria(slots, npcs, effects,
            ClericMariaAttachmentIds(13504907, 13504908, 13504910, 13504920), "maria")
        self.assertEqual("bb-enemizer-plan-v2", forward["format"])
        self.assertEqual("c4520", forward["swaps"][0]["target"]["model_name"])
        self.assertEqual("c5000", reverse["swaps"][0]["target"]["model_name"])
        self.assertEqual(3, len(forward["primary_init_source_bindings"]))
        self.assertEqual({"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"}, {x["destination_map"] for x in forward["primary_init_source_bindings"]})
        self.assertEqual(3500800, forward["primary_init_source_bindings"][0]["source_entity_id"])
        self.assertEqual("m24_01_00_00", reverse["primary_init_source_bindings"][0]["source_map"])
        self.assertIn(13501800, reverse["boss_contract"]["preserved_destination_events"])

    def test_adapter_rejects_any_original_literal_collision(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_maria_at_cleric(
                self.cleric, self.maria, MariaClericAttachmentIds(12414707),
            )


if __name__ == "__main__":
    unittest.main()
