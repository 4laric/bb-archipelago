import unittest
import copy
import tempfile
from pathlib import Path

from tools.bb_enemizer.boss_pool import (
    assign_donors,
    combine_native_plans,
    combine_ordinary_and_boss_plans,
    compose_event_patches,
)


SOURCE = '''$Event(0, Default, function() {
    $InitializeEvent(0, 10, 100);
    $InitializeEvent(0, 20, 200);
});
$Event(10, Default, function(value) {
    WaitFor(CharacterDead(value));
});
$Event(20, Default, function(value) {
    WaitFor(CharacterDead(value));
});
$Event(30, Default, function() {
    HandleBossDefeat(100);
});
'''


class BossPoolTests(unittest.TestCase):
    def test_auxiliary_actors_survive_pool_composition_and_collisions_fail(self):
        def pair(key, entity, map_name='m23_00_00_00'):
            return {
                'format': 'bb-enemizer-plan-v2', 'seed': 'actors', 'dry_run': True,
                'swaps': [{'logical_key': key, 'destination_keys': [key]}],
                'scaling': {
                    'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': 0, 'changes': [],
                    'skip_count': 1, 'skips': [{'logical_key': key, 'reason': 'unknown source or destination tier'}],
                },
                'boss_contract': {'arena': key},
                'boss_actor_additions': [{
                    'destination_map': map_name, 'destination_entity_id': entity,
                    'destination_part': 'extra-' + key,
                    'source_archetype': {'model_name': 'test-source'},
                }],
            }
        first, second = pair('a', 100), pair('b', 200)
        first['boss_actor_initializations'] = [{'destination_map': 'm23_00_00_00',
            'destination_part': 'primary-a', 'source_initialization': {'talk_id': 123}}]
        original = copy.deepcopy([first, second])
        result = combine_native_plans('actors', [second, first])
        self.assertEqual([100, 200], [row['destination_entity_id']
                                    for row in result['boss_actor_additions']])
        self.assertEqual(original, [first, second])
        self.assertEqual(123, result['boss_actor_initializations'][0]['source_initialization']['talk_id'])
        duplicate_init = pair('d', 300)
        duplicate_init['boss_actor_initializations'] = copy.deepcopy(first['boss_actor_initializations'])
        with self.assertRaisesRegex(ValueError, 'primary actor initialization'):
            combine_native_plans('actors', [first, duplicate_init])
        result['boss_actor_additions'][0]['source_archetype']['model_name'] = 'mutated'
        self.assertEqual('test-source', first['boss_actor_additions'][0]['source_archetype']['model_name'])
        duplicate = pair('c', 100, 'm23_00_00_00.msb.dcx')
        with self.assertRaisesRegex(ValueError, 'overlap an added actor'):
            combine_native_plans('actors', [first, duplicate])
        second['boss_actor_additions'][0]['destination_part'] = 'extra-a'
        with self.assertRaisesRegex(ValueError, 'overlap an added actor'):
            combine_native_plans('actors', [first, second])

    def test_generator_additions_survive_composition_and_share_entity_collision_checks(self):
        generator = {'destination_map': 'm23_00_00_00', 'destination_event': 'ap-generator',
                     'destination_event_id': 20, 'destination_entity_id': 200,
                     'spawn_part_map': {'source': 'destination'}}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'g', 'dry_run': True,
                'swaps': [], 'scaling': {
                    'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': 0, 'changes': [], 'skip_count': 0, 'skips': [],
                }, 'boss_contract': {},
                'boss_generator_additions': [generator]}
        result = combine_native_plans('g', [plan])
        self.assertEqual([generator], result['boss_generator_additions'])
        result['boss_generator_additions'][0]['spawn_part_map']['source'] = 'changed'
        self.assertEqual('destination', generator['spawn_part_map']['source'])
        with self.assertRaisesRegex(ValueError, 'overlap an added generator'):
            combine_native_plans('g', [plan, plan])
        actor_plan = copy.deepcopy(plan)
        del actor_plan['boss_generator_additions']
        actor_plan['boss_actor_additions'] = [{'destination_map': 'm23_00_00_00.msb.dcx',
            'destination_part': 'actor', 'destination_entity_id': 200}]
        with self.assertRaisesRegex(ValueError, 'overlap an added'):
            combine_native_plans('g', [plan, actor_plan])

    def test_seeded_matching_uses_each_boss_once_without_identity(self):
        graph = {key: ('a', 'b', 'c', 'd') for key in ('a', 'b', 'c', 'd')}
        first = assign_donors('one', graph)
        self.assertEqual(first, assign_donors('one', dict(reversed(list(graph.items())))))
        self.assertEqual(['a', 'b', 'c', 'd'], sorted(first.values()))
        for arena, donor in first.items():
            self.assertNotEqual(arena, donor)
        results = {tuple(assign_donors(str(seed), graph).items()) for seed in range(12)}
        self.assertGreater(len(results), 1)

    def test_impossible_pool_is_refused_instead_of_dropping_boss(self):
        with self.assertRaisesRegex(ValueError, 'no complete'):
            assign_donors('seed', {'a': ['b'], 'b': ['a'], 'c': ['b']})

    def test_same_map_disjoint_constructor_edits_compose_in_either_order(self):
        first = SOURCE.replace('$InitializeEvent(0, 10, 100);', '$InitializeEvent(0, 10, 300);')
        second = SOURCE.replace('$InitializeEvent(0, 20, 200);', '$InitializeEvent(0, 20, 400);')
        result = compose_event_patches(SOURCE, [first, second], [30])
        self.assertEqual(result, compose_event_patches(SOURCE, [second, first], [30]))
        self.assertIn('$InitializeEvent(0, 10, 300);', result)
        self.assertIn('$InitializeEvent(0, 20, 400);', result)
        self.assertIn('HandleBossDefeat(100);', result)

    def test_appended_initializers_compose_but_conflicting_slots_do_not(self):
        anchor = '    $InitializeEvent(0, 20, 200);'
        first = SOURCE.replace(anchor, anchor + '\n    $InitializeEvent(0, 40, 400);')
        second = SOURCE.replace(anchor, anchor + '\n    $InitializeEvent(0, 50, 500);')
        result = compose_event_patches(SOURCE, [first, second], [30])
        self.assertEqual(result, compose_event_patches(SOURCE, [second, first], [30]))
        self.assertEqual(1, result.count('$InitializeEvent(0, 40, 400);'))
        self.assertEqual(1, result.count('$InitializeEvent(0, 50, 500);'))
        conflict = second.replace('0, 50, 500', '0, 40, 500')
        with self.assertRaisesRegex(ValueError, 'initializer slot'):
            compose_event_patches(SOURCE, [first, conflict], [30])
        arbitrary = second.replace('$InitializeEvent(0, 50, 500);', 'SetEventFlag(500, ON);')
        with self.assertRaisesRegex(ValueError, 'literal initializers'):
            compose_event_patches(SOURCE, [first, arbitrary], [30])

    def test_conflicting_constructor_and_completion_changes_are_refused(self):
        first = SOURCE.replace('$InitializeEvent(0, 10, 100);', '$InitializeEvent(0, 10, 300);')
        second = SOURCE.replace('$InitializeEvent(0, 10, 100);', '$InitializeEvent(0, 10, 400);')
        with self.assertRaisesRegex(ValueError, 'conflicting boss constructor'):
            compose_event_patches(SOURCE, [first, second], [30])
        with self.assertRaisesRegex(ValueError, 'protected completion event 30'):
            compose_event_patches(SOURCE, [SOURCE.replace('HandleBossDefeat(100)', 'HandleBossDefeat(200)')], [30])

    def test_reciprocal_real_bosses_share_map_without_losing_progression(self):
        from tools.bb_enemizer.boss_contracts import (
            BSB_ARENA, PAARL_ARENA, BSB_PACKAGE, PAARL_PACKAGE,
            patch_contract_swap, plan_contract_swap, event_blocks,
        )
        from tools.bb_inputs import read_blob, read_prefix
        from tools.bb_enemizer.inventory import load_slots
        from tools.bb_enemizer.scaling import load_params
        bundle = Path(__file__).resolve().parents[1] / 'research/bb_inputs.db'
        sources = read_prefix(bundle, 'event/')
        source = next(blob.decode('utf-8-sig') for name, blob in sources.items()
                      if name.endswith(BSB_ARENA.event_file))
        variants = [patch_contract_swap(arena, donor, source, source)
                    for arena, donor in ((BSB_ARENA, PAARL_PACKAGE), (PAARL_ARENA, BSB_PACKAGE))]
        output = compose_event_patches(source, variants, [12301700, 12301800])
        before, after = event_blocks(source), event_blocks(output)
        self.assertEqual(before[12301700], after[12301700])
        self.assertEqual(before[12301800], after[12301800])
        self.assertIn('DisplayBossHealthBar(Enabled, 2300800, 0, 508000)', after[12304802])
        self.assertIn('DisplayBossHealthBar(Enabled, 2300810, 0, 209000)', after[12304702])
        self.assertEqual(5, after[0].count('12304808,'))
        self.assertIn('$InitializeEvent(0, 12304715);', after[0])
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / 'slots.tsv'
            inventory.write_bytes(read_blob(bundle, 'mined/msb_enemies.tsv'))
            slots = load_slots(inventory)
        npcs, effects = load_params(bundle)
        plans = [plan_contract_swap(arena, donor, slots, npcs, effects, 'reciprocal')
                 for arena, donor in ((BSB_ARENA, PAARL_PACKAGE), (PAARL_ARENA, BSB_PACKAGE))]
        plan = combine_native_plans('reciprocal', plans)
        self.assertEqual(2, plan['swap_count'])
        self.assertEqual(1, plan['scaling']['change_count'])
        self.assertEqual(1, plan['scaling']['skip_count'])
        self.assertEqual({209000, 508000}, {swap['target']['npc_param_id'] for swap in plan['swaps']})
        with self.assertRaisesRegex(ValueError, 'overlap a destination'):
            combine_native_plans('reciprocal', [plans[0], plans[0]])

    def test_combined_plan_reallocates_once_and_keeps_ordinary_evidence(self):
        def change(key, clone):
            return {
                'logical_key': key, 'source_npc_param_id': 100 + clone,
                'cloned_npc_param_id': clone, 'sp_effect_slot': 'spEffectID1',
                'minted_sp_effect_id': 60000, 'have_soul_rate': 1,
                'source_level': 1, 'destination_level': 1,
                'hp_multiplier': 1, 'attack_multiplier': 1, 'defense_multiplier': 1,
            }

        ordinary = {
            'format': 'bb-enemizer-plan-v2', 'seed': 'shared', 'dry_run': True,
            'options': {'allow_tier_mixing': False, 'preserve_locomotion': True},
            'inventory': {'logical_slots': 2}, 'rejections': [{'logical_key': 'kept', 'reason': 'protected'}],
            'swap_count': 2,
            'swaps': [
                {'logical_key': 'ordinary-change', 'destination_keys': ['m10:ordinary-change']},
                {'logical_key': 'ordinary-skip', 'destination_keys': ['m10:ordinary-skip']},
            ],
            'scaling': {
                'enabled': True, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                'change_count': 1, 'changes': [change('ordinary-change', 6000000)],
                'skip_count': 1,
                'skips': [{'logical_key': 'ordinary-skip', 'reason': 'unknown source or destination tier'}],
            },
        }
        boss = {
            'format': 'bb-enemizer-plan-v2', 'seed': 'shared', 'dry_run': True,
            'swaps': [
                {'logical_key': 'boss-change', 'destination_keys': ['m20:boss-change']},
                {'logical_key': 'boss-skip', 'destination_keys': ['m20:boss-skip']},
            ],
            'scaling': {
                'enabled': True, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                'change_count': 1, 'changes': [change('boss-change', 6000000)],
                'skip_count': 1,
                'skips': [{'logical_key': 'boss-skip', 'reason': 'no free spEffectID slot'}],
            },
            'boss_contract': {'arena': 'boss'},
            'boss_external_references': [{'destination_event_file': 'm20.emevd.dcx',
                                          'destination_event_id': 20, 'destination_actor': 200,
                                          'entity_id': 201}],
        }
        before = copy.deepcopy((ordinary, boss))
        result = combine_ordinary_and_boss_plans(ordinary, [boss])
        self.assertEqual('shared', result['seed'])
        self.assertEqual(ordinary['options'], result['options'])
        self.assertEqual({'logical_slots': 2}, result['inventory'])
        self.assertEqual(4, result['swap_count'])
        self.assertEqual([6000000, 6000001], [row['cloned_npc_param_id'] for row in result['scaling']['changes']])
        self.assertEqual({'ordinary-change', 'ordinary-skip', 'boss-change', 'boss-skip'}, {
            row['logical_key'] for row in result['scaling']['changes'] + result['scaling']['skips']
        })
        self.assertEqual(201, result['boss_external_references'][0]['entity_id'])
        result['options']['preserve_locomotion'] = False
        self.assertEqual(before, (ordinary, boss))

    def test_combined_plan_refuses_unaccounted_or_overlapping_placements(self):
        ordinary = {
            'format': 'bb-enemizer-plan-v2', 'seed': 'shared', 'dry_run': True,
            'options': {}, 'swaps': [{'logical_key': 'ordinary', 'destination_keys': ['m10:part']}],
            'scaling': {
                'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                'change_count': 0, 'changes': [], 'skip_count': 0, 'skips': [],
            },
        }
        boss = {
            'format': 'bb-enemizer-plan-v2', 'seed': 'shared', 'dry_run': True,
            'swaps': [{'logical_key': 'boss', 'destination_keys': ['m20:part']}],
            'scaling': {
                'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                'change_count': 0, 'changes': [], 'skip_count': 1,
                'skips': [{'logical_key': 'boss', 'reason': 'unknown source or destination tier'}],
            },
            'boss_contract': {'arena': 'boss'},
        }
        with self.assertRaisesRegex(ValueError, 'ordinary plan scaling does not account'):
            combine_ordinary_and_boss_plans(ordinary, [boss])
        ordinary['scaling']['skip_count'] = 1
        ordinary['scaling']['skips'] = [{'logical_key': 'ordinary', 'reason': 'unknown source or destination tier'}]
        boss['swaps'][0]['destination_keys'] = ['m10:part']
        with self.assertRaisesRegex(ValueError, 'physical destination'):
            combine_ordinary_and_boss_plans(ordinary, [boss])


if __name__ == '__main__':
    unittest.main()
