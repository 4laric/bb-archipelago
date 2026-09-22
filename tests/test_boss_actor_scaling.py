import copy
import unittest
from pathlib import Path

from tools.bb_enemizer.boss_actor_scaling import allocate_actor_scaling
from tools.bb_enemizer.scaling import load_params, npc_native_level


class BossActorScalingTests(unittest.TestCase):
    def test_boss_tiers_match_original_named_effects(self):
        npcs, effects = load_params(Path(__file__).resolve().parents[1] / 'research/bb_inputs.db')
        expected = {7420: 1, 7421: 1, 7422: 6, 7423: 11, 7424: 12,
                    7425: 13, 7426: 3, 7427: 3, 7428: 5, 7429: 7}
        for effect, tier in expected.items():
            with self.subTest(effect=effect):
                self.assertIn(f'レベル{tier}：', effects[effect]['Name'])
                self.assertEqual(tier, npc_native_level({'GameClearSpEffectID': str(effect)}, boss_tiers=True))
        self.assertEqual(1, npc_native_level(npcs[271000], boss_tiers=True))
        self.assertEqual(1, npc_native_level(npcs[272000], boss_tiers=True))
        self.assertEqual('7423', npcs[251000]['GameClearSpEffectID'])
        self.assertEqual(11, npc_native_level(npcs[251000], boss_tiers=True))

    def fixture(self):
        parent = 'm24_01_00_00:primary'
        maps = ['m24_01_00_00', 'm24_01_00_01', 'm24_01_00_11']
        additions = [{
            'source_map': 'm34_00_00_00', 'source_part': 'phase-two', 'source_anchor_part': 'core',
            'source_entity_id': 3400801,
            'source_archetype': {'model_name': 'c4510', 'npc_param_id': 451001,
                                 'think_param_id': 451000, 'chara_init_id': 0},
            'source_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'a' * 64},
            'source_initialization': {'talk_id': 0, 'unk_t18': 0,
                                      'init_anim_id': -1, 'damage_anim_id': -1},
            'destination_map': name, 'destination_anchor_part': 'primary',
            'destination_part': 'phase-two', 'destination_entity_id': 980002,
        } for name in maps]
        plan = {'swaps': [{'logical_key': parent,
                          'destination_keys': [name + ':primary' for name in maps]}],
                'boss_actor_additions': additions,
                'scaling': {'changes': [
                    {'logical_key': parent, 'cloned_npc_param_id': 6000238,
                     'source_npc_param_id': 451000, 'source_level': 11}]}}
        npcs = {451001: {'GameClearSpEffectID': '7491',
                         **{f'spEffectID{i}': str(-1 if i == 3 else 100 + i)
                            for i in range(8)}}}
        parents = {(name, 'phase-two'): parent for name in maps}
        return plan, npcs, parents

    def test_phase_states_share_one_clone_after_ordinary_and_primary_clones(self):
        plan, npcs, parents = self.fixture()
        plan['boss_actor_additions'][1]['source_map'] = 'm34_00_00_01'
        plan['boss_actor_additions'][1]['source_provenance']['part_sha256'] = 'b' * 64
        before = copy.deepcopy(plan)
        result = allocate_actor_scaling(plan, npcs, parents)
        self.assertEqual(3, len(result))
        self.assertEqual({6000239}, {row['cloned_npc_param_id'] for row in result})
        self.assertEqual({'spEffectID3'}, {row['sp_effect_slot'] for row in result})
        self.assertEqual(before, plan)
        result[0]['source_initialization']['talk_id'] = 999
        self.assertEqual(0, plan['boss_actor_additions'][0]['source_initialization']['talk_id'])

    def test_unproven_tier_occupied_slot_or_clone_cannot_publish_helper_plan(self):
        for mutation, message in (
            (lambda p, n: n[451001].update(GameClearSpEffectID='7401'), 'source tier'),
            (lambda p, n: n[451001].update(spEffectID3='999'), 'free effect slot'),
            (lambda p, n: n.update({6000239: {}}), 'occupied'),
            (lambda p, n: p['scaling']['changes'][0].update(cloned_npc_param_id=6099999), 'exhausted'),
            (lambda p, n: p['boss_actor_additions'][0].update(destination_anchor_part='other'), 'anchor'),
        ):
            with self.subTest(message=message):
                plan, npcs, parents = self.fixture()
                mutation(plan, npcs)
                with self.assertRaisesRegex(ValueError, message):
                    allocate_actor_scaling(plan, npcs, parents)

    def test_helpers_in_independent_fights_get_distinct_clones(self):
        plan, npcs, parents = self.fixture()
        other = copy.deepcopy(plan['boss_actor_additions'][0])
        other.update(destination_map='m23_00_00_00')
        other_key = 'm23_00_00_00:primary'
        plan['boss_actor_additions'].append(other)
        plan['swaps'].append({'logical_key': other_key, 'destination_keys': [other_key]})
        change = copy.deepcopy(plan['scaling']['changes'][0])
        change.update(logical_key=other_key, cloned_npc_param_id=6000239)
        plan['scaling']['changes'].append(change)
        parents['m23_00_00_00', 'phase-two'] = other_key
        result = allocate_actor_scaling(plan, npcs, parents)
        self.assertEqual({6000240, 6000241}, {row['cloned_npc_param_id'] for row in result})
        self.assertEqual(6000240, result[0]['cloned_npc_param_id'])
        self.assertEqual({6000241}, {row['cloned_npc_param_id'] for row in result[1:]})

    def test_distinct_original_helper_can_share_primary_npc_identity(self):
        plan, npcs, parents = self.fixture()
        npcs[451000] = dict(npcs[451001])
        for addition in plan['boss_actor_additions']:
            addition['source_archetype']['npc_param_id'] = 451000
        rows = allocate_actor_scaling(plan, npcs, parents)
        self.assertEqual({6000239}, {row['cloned_npc_param_id'] for row in rows})
        self.assertEqual({451000}, {row['source_archetype']['npc_param_id'] for row in rows})
        plan['boss_actor_additions'][0]['source_anchor_part'] = 'phase-two'
        with self.assertRaisesRegex(ValueError, 'distinct original actor'):
            allocate_actor_scaling(plan, npcs, parents)


if __name__ == '__main__':
    unittest.main()
