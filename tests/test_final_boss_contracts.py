import unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.final_boss_contracts import *
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
  self.assertEqual('$Event(12104860, Default, function() {\n    EndEvent();\n});',after[12104860])
 def test_moon_at_gehrman_keeps_endgame_terminal_cutscene_and_attaches_limbs(self):
  before=event_blocks(self.source); after=event_blocks(patch_moon_at_gehrman(self.source,FinalAttachmentIds(12104917,12104918)))
  self.assertEqual(before[12101800],after[12101800]); self.assertEqual(before[12101802],after[12101802])
  self.assertIn('DisplayBossHealthBar(Enabled, 2100800, 0, 540000)',after[12104802]); self.assertIn('CharacterHasEventMessage(2100800, 500)',after[12104803])
  self.assertEqual(5,after[0].count('12104917'))
  self.assertIn('CreateNPCPart(2100800',after[12104917]); self.assertIn('CharacterHasEventMessage(2100800, 10)',after[12104918])
  self.assertEqual('$Event(12104807, Default, function() {\n    EndEvent();\n});',after[12104807])
 def test_collision_and_source_drift_refuse(self):
  with self.assertRaisesRegex(ValueError,'collides'): patch_gehrman_at_moon(self.source,FinalAttachmentIds(12104860,12104908))
  with self.assertRaisesRegex(ValueError,'unsupported original'):
   patch_moon_at_gehrman(self.source.replace('DisplayBossHealthBar(Enabled, 2100800, 0, 804000)','DisplayBossHealthBar(Enabled, 2100800, 0, 7)'),FinalAttachmentIds(12104917,12104918))
if __name__=='__main__': unittest.main()
