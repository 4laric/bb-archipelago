import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.laurence_contract import (
    LaurenceIds, patch_laurence_at_cleric, native_plan_laurence_at_cleric,
)
from tools.bb_enemizer.scaling import load_params
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'research/bb_inputs.db'


class LaurenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cleric = read_blob(BUNDLE, 'event/m24_01_00_00.emevd.dcx.js').decode('utf-8-sig')
        cls.laurence = read_blob(BUNDLE, 'event/m34_00_00_00.emevd.dcx.js').decode('utf-8-sig')
        cls.ids = LaurenceIds(12990300, 12990301)

    def test_actual_laurence_identity_and_five_limb_calls(self):
        self.assertIn('3400850', repr(LOCATION_BINDINGS['boss_laurence']))
        before = event_blocks(self.cleric)
        after = event_blocks(patch_laurence_at_cleric(self.cleric, self.laurence, self.ids))
        self.assertEqual(before[12411700], after[12411700])
        self.assertEqual(before[12411800], after[12411800])
        self.assertIn('DisplayBossHealthBar(Enabled, 2410800, 0, 450000)', after[12414702])
        self.assertEqual(5, after[0].count('12990300'))
        self.assertIn('CharacterHasEventMessage(2410800, 400)', after[12414703])
        self.assertIn('EntityInRadiusOfEntity(10000, 2410800, 14)', after[12414704])
        self.assertIn('ForceAnimationPlayback(2410800, 3029, false, false, false)', after[12411702])
        self.assertNotIn('3400850', after[12990300] + after[12990301])

    def test_changed_source_or_destination_is_rejected(self):
        changed_donor = self.laurence.replace('CharacterHasEventMessage(3400850, 400)',
                                             'CharacterHasEventMessage(3400850, 999)')
        with self.assertRaisesRegex(ValueError, 'unsupported Laurence source'):
            patch_laurence_at_cleric(self.cleric, changed_donor, self.ids)
        changed_arena = self.cleric.replace('ForceAnimationPlayback(2410800, 3028,',
                                            'ForceAnimationPlayback(2410800, 9999,')
        with self.assertRaisesRegex(ValueError, 'unsupported original Cleric arena'):
            patch_laurence_at_cleric(changed_arena, self.laurence, self.ids)

    def test_native_plan_binds_actual_laurence_to_all_original_cleric_states(self):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / 'slots.tsv'
            inventory.write_bytes(read_blob(BUNDLE, 'mined/msb_enemies.tsv'))
            slots = load_slots(inventory)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_laurence_at_cleric(slots, npcs, effects, self.ids, 'laurence')
        self.assertEqual(1, plan['swap_count'])
        self.assertEqual('c4500', plan['swaps'][0]['target']['model_name'])
        bindings = plan['primary_init_source_bindings']
        self.assertEqual(3, len(bindings))
        self.assertEqual({'m24_01_00_00', 'm24_01_00_01', 'm24_01_00_11'},
                         {row['destination_map'] for row in bindings})
        self.assertEqual({3400850}, {row['source_entity_id'] for row in bindings})
        with self.assertRaisesRegex(ValueError, 'three exact Cleric'):
            native_plan_laurence_at_cleric([slot for slot in slots if slot.entity_id != 3400850],
                                           npcs, effects, self.ids, 'laurence')
