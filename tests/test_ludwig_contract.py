import unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.ludwig_contract import LudwigIds, EVENTS, patch_ludwig_at_cleric
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

ROOT=Path(__file__).resolve().parents[1]; BUNDLE=ROOT/'research/bb_inputs.db'
class LudwigContractTests(unittest.TestCase):
 @classmethod
 def setUpClass(c):
  c.source=read_blob(BUNDLE,'event/m34_00_00_00.emevd.dcx.js').decode('utf-8-sig');c.cleric=read_blob(BUNDLE,'event/m24_01_00_00.emevd.dcx.js').decode('utf-8-sig')
 def ids(self): return LudwigIds(980002,12990200,{e:12990201+i for i,e in enumerate(EVENTS)},'ap_ludwig_phase2','test allocation')
 def test_identity_is_ludwig_not_laurence(self):
  self.assertIn('3400800',repr(LOCATION_BINDINGS['boss_ludwig']))
  self.assertIn('3400850',repr(LOCATION_BINDINGS['boss_laurence']))
 def test_terminal_only_substitutes_bridge_predicate_and_never_maps_laurence(self):
  before=event_blocks(self.cleric); after=event_blocks(patch_ludwig_at_cleric(self.cleric,self.source,self.ids()))
  restored=after[12411700].replace('WaitFor(EventFlag(12990200));','WaitFor(CharacterDead(2410800));')
  self.assertEqual(before[12411700],restored)
  self.assertNotIn('13401850',after[12411700])
  self.assertIn('WaitFor(CharacterDead(2410800) || CharacterDead(980002))',after[12990200])
  self.assertIn('$InitializeEvent(0, 12990200);',after[0])
 def test_normal_branch_copies_three_limb_initializers_with_original_arity(self):
  after=event_blocks(patch_ludwig_at_cleric(self.cleric,self.source,self.ids()))
  zero=after[0]; limb=str(self.ids().event_ids[13404830])
  self.assertEqual(3,zero.count(limb)); self.assertIn(', 300, 480, 7001, 152);',zero);self.assertIn(', 150, 482, 7004, 72);',zero);self.assertIn(', 150, 481, 7002, 72);',zero)
 def test_transplanted_events_have_no_m34_lifecycle_literals(self):
  after=event_blocks(patch_ludwig_at_cleric(self.cleric,self.source,self.ids()))
  copied='\n'.join(after[i] for i in self.ids().event_ids.values())
  for literal in ('9471','13400999','34000030','3402806','3402807','3402900','9180'):
   self.assertNotIn(literal,copied)
  self.assertIn('RequestCharacterAICommand(2410800, 100',copied)
 def test_source_drift_refused(self):
  with self.assertRaisesRegex(ValueError,'unsupported original Ludwig donor'):
   patch_ludwig_at_cleric(self.cleric,self.source.replace('RequestCharacterAICommand(3400800, 100','RequestCharacterAICommand(3400800, 999',1),self.ids())
if __name__=='__main__': unittest.main()
