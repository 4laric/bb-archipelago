import unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.final_boss_contracts import *
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
import tempfile
ROOT=Path(__file__).resolve().parents[1]; B=ROOT/'research/bb_inputs.db'
class FinalBossContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(c): c.source=read_blob(B,'event/m21_00_00_00.emevd.dcx.js').decode('utf-8-sig')
 def test_gehrman_at_moon_keeps_moon_transition_and_installs_selfbuff_cleanup(self):
  before=event_blocks(self.source); after=event_blocks(patch_gehrman_at_moon(self.source,FinalAttachmentIds(12104907,12104908)))
  self.assertEqual(before[12101850],after[12101850]); self.assertEqual(before[12101852],after[12101852])
  self.assertIn('DisplayBossHealthBar(Enabled, 2100810, 0, 804000)',after[12104852]); self.assertIn('SetCharacterEventTarget(2100810, 2100801)',after[12104852])
  self.assertIn('RequestCharacterAICommand(2100810, 100, 0)',after[12104907]); self.assertIn('ClearSpEffect(2100810, 5526)',after[12104908])
  self.assertIn('CharacterHasEventMessage(2100810, 100)',after[12104853]); self.assertIn('EntityInRadiusOfEntity(10000, 2100810, 8)',after[12104854])
  self.assertEqual('$Event(12104860, Default, function(unused_npcPartId, unused_npcPartId2, unused_npcPartGroupIdx, unused_npcPartHP, unused_spEffectId, unused_spEffectId2, unused_animationId) {\n    EndEvent();\n});',after[12104860])
 def test_moon_at_gehrman_keeps_endgame_terminal_cutscene_and_attaches_limbs(self):
  before=event_blocks(self.source); after=event_blocks(patch_moon_at_gehrman(self.source,FinalAttachmentIds(12104917,12104918)))
  self.assertEqual(before[12101800],after[12101800]); self.assertEqual(before[12101802],after[12101802])
  self.assertIn('DisplayBossHealthBar(Enabled, 2100800, 0, 540000)',after[12104802]); self.assertIn('CharacterHasEventMessage(2100800, 500)',after[12104803])
  self.assertEqual(5,after[0].count('12104917'))
  self.assertIn('CreateNPCPart(2100800',after[12104917]); self.assertIn('CharacterHasEventMessage(2100800, 10)',after[12104918])
  self.assertEqual('$Event(12104807, Default, function() {\n    EndEvent();\n});',after[12104807])

 def test_native_plan_validates_inventory_talk_and_emits_primary_binding(self):
  with tempfile.TemporaryDirectory() as directory:
   inventory=Path(directory)/"slots.tsv"; inventory.write_bytes(read_blob(B, "mined/msb_enemies.tsv"))
   slots=load_slots(inventory)
  npcs,effects=load_params(B)
  plan=plan_final_boss_swap(slots,npcs,effects,arena=MOON_ARENA,donor=GEHRMAN_ARENA,attachment_ids=FinalAttachmentIds(12104907,12104908),seed="final")
  self.assertEqual("bb-enemizer-plan-v2",plan["format"]); self.assertEqual("c8050",plan["swaps"][0]["target"]["model_name"])
  binding=plan["boss_contract"]["primary_init_source_bindings"][0]
  self.assertEqual(210306,binding["source_talk_id"]); self.assertEqual(2100810,binding["destination_entity_id"])
  self.assertIn("provenance",binding["required_native_fields"])
  reverse=plan_final_boss_swap(slots,npcs,effects,arena=GEHRMAN_ARENA,donor=MOON_ARENA,attachment_ids=FinalAttachmentIds(12104917,12104918),seed="final")
  self.assertEqual("moon-at-gehrman",reverse["boss_contract"]["patch"])
  self.assertEqual(0,reverse["boss_contract"]["primary_init_source_bindings"][0]["source_talk_id"])
  moon=next(slot for slot in slots if slot.entity_id==2100810)
  moon=type(moon)(moon.map_path,moon.map_name,moon.part_name,moon.entity_id,99,moon.collision_name,moon.dummy,moon.x,moon.y,moon.z,moon.archetype)
  with self.assertRaisesRegex(ValueError,"TalkID"):
   plan_final_boss_swap([slot for slot in slots if slot.entity_id!=2100810]+[moon],npcs,effects,arena=MOON_ARENA,donor=GEHRMAN_ARENA,attachment_ids=FinalAttachmentIds(12104907,12104908),seed="final")

 def test_collision_and_source_drift_refuse(self):
  with self.assertRaisesRegex(ValueError,'collides'): patch_gehrman_at_moon(self.source,FinalAttachmentIds(12104860,12104908))
  with self.assertRaisesRegex(ValueError,'unsupported original'):
   patch_moon_at_gehrman(self.source.replace('DisplayBossHealthBar(Enabled, 2100800, 0, 804000)','DisplayBossHealthBar(Enabled, 2100800, 0, 7)'),FinalAttachmentIds(12104917,12104918))
if __name__=='__main__': unittest.main()
