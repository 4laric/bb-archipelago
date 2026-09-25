import unittest
import copy
import tempfile
from itertools import permutations
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
    def test_character_bank_bindings_survive_composition_and_reject_destination_overlap(self):
        row = {'source_map': 'm24_02_00_00', 'source_part': 'c2570_0001',
               'source_entity_id': 2420811, 'source_character': 'c2570',
               'destination_map': 'm23_00_00_00', 'destination_part': 'giant',
               'destination_entity_id': 984000, 'source_ffx_file': 'frpg_sfxbnd_m24_02.ffxbnd.dcx',
               'destination_ffx_file': 'frpg_sfxbnd_m23.ffxbnd.dcx',
               'roots': [{'source_tae_entry_id': 3000000, 'witness': {'effect_id': 625700}}]}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'bank', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_character_ffx_bank_requirements': [row]}
        self.assertEqual([row], combine_native_plans('bank', [plan])[
            'boss_character_ffx_bank_requirements'])
        second_bank = copy.deepcopy(row)
        second_bank['source_ffx_file'] = 'frpg_sfxbnd_m24.ffxbnd.dcx'
        second_bank['roots'][0]['witness']['effect_id'] = 625701
        two_banks = copy.deepcopy(plan)
        two_banks['boss_character_ffx_bank_requirements'].append(second_bank)
        self.assertEqual([second_bank, row], combine_native_plans('bank', [two_banks])[
            'boss_character_ffx_bank_requirements'])
        same_root = copy.deepcopy(two_banks)
        same_root['boss_character_ffx_bank_requirements'][1]['roots'][0]['witness']['effect_id'] = 625700
        with self.assertRaisesRegex(ValueError, 'repeat a character FFX root across banks'):
            combine_native_plans('bank', [same_root])
        with self.assertRaisesRegex(ValueError, 'character FFX bank destination'):
            combine_native_plans('bank', [plan, copy.deepcopy(plan)])
        ordinary = {**copy.deepcopy(plan), 'options': {},
                    'swaps': [{'logical_key': 'ordinary', 'destination_keys': ['m24_00_00_00:ordinary']}]}
        ordinary['scaling'].update(skip_count=1, skips=[{'logical_key': 'ordinary'}])
        ordinary.pop('boss_contract')
        with self.assertRaisesRegex(ValueError, 'already carries boss metadata'):
            combine_ordinary_and_boss_plans(ordinary, [plan])
        ordinary.pop('boss_character_ffx_bank_requirements')
        combined = combine_ordinary_and_boss_plans(ordinary, [plan])
        self.assertEqual([row], combined['boss_character_ffx_bank_requirements'])
        combined_two_banks = combine_ordinary_and_boss_plans(ordinary, [two_banks])
        self.assertEqual([second_bank, row],
                         combined_two_banks['boss_character_ffx_bank_requirements'])
        combined['boss_character_ffx_bank_requirements'][0]['roots'][0]['witness']['effect_id'] = 123
        self.assertEqual(625700, row['roots'][0]['witness']['effect_id'])

    def test_character_effect_witnesses_survive_both_compositions_and_refuse_disagreement(self):
        row = {'source_map': 'm36_00_00_00', 'source_part': 'c4540_0000',
               'source_entity_id': 3600800, 'source_character': 'c4540',
               'source_anibnd_sha256': 'a' * 64, 'direct_effect_ids': [645400],
               'typed_event_witnesses': [{'animation_id': 0, 'effect_id': 645400}]}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'characters', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_character_ffx_requirements': [row]}
        second = copy.deepcopy(plan)
        combined = combine_native_plans('characters', [plan, second])
        self.assertEqual([row], combined['boss_character_ffx_requirements'])
        ordinary = copy.deepcopy(plan)
        ordinary['options'] = {}
        ordinary['swaps'] = [{'logical_key': 'ordinary', 'destination_keys': ['m24_00_00_00:ordinary']}]
        ordinary['scaling'].update(skip_count=1, skips=[{'logical_key': 'ordinary'}])
        ordinary.pop('boss_contract')
        ordinary.pop('boss_character_ffx_requirements')
        with self.assertRaisesRegex(ValueError, 'already carries boss metadata'):
            combine_ordinary_and_boss_plans(dict(ordinary, boss_character_ffx_requirements=[row]), [plan])
        both = combine_ordinary_and_boss_plans(ordinary, [plan, second])
        self.assertEqual([row], both['boss_character_ffx_requirements'])
        both['boss_character_ffx_requirements'][0]['direct_effect_ids'].append(123)
        self.assertEqual([645400], row['direct_effect_ids'])
        second['boss_character_ffx_requirements'][0]['source_anibnd_sha256'] = 'b' * 64
        with self.assertRaisesRegex(ValueError, 'disagree on character FFX provenance'):
            combine_native_plans('characters', [plan, second])
        second = copy.deepcopy(plan)
        second['boss_character_ffx_requirements'][0]['source_character'] = 'c4541'
        with self.assertRaisesRegex(ValueError, 'disagree on character FFX provenance'):
            combine_native_plans('characters', [plan, second])
        duplicate = copy.deepcopy(plan)
        duplicate['boss_character_ffx_requirements'].append(copy.deepcopy(row))
        with self.assertRaisesRegex(ValueError, 'repeats a character FFX actor binding'):
            combine_native_plans('characters', [duplicate])
        second = copy.deepcopy(plan)
        second['boss_character_ffx_requirements'][0].update(source_part='c4540_0001', source_entity_id=3600801)
        self.assertEqual(2, len(combine_native_plans('characters', [plan, second])[
            'boss_character_ffx_requirements']))

    def test_multi_tae_proofs_preserve_every_entry_and_refuse_changed_shared_actor(self):
        entries = [
            {'source_tae_entry_id': index, 'source_tae_entry': f'chr/c0000/tae/a{index:02}.tae',
             'source_tae_sha256': str(index + 1) * 64, 'source_animation_count': 1,
             'decoded_event_types': [96, 100, 118],
             'typed_event_witnesses': [{'animation_id': 0, 'event_index': 0,
                 'event_type': 96, 'parameter_offset': 160, 'effect_id': 7000 + index}],
             'direct_effect_ids': [7000 + index]}
            for index in range(2)
        ]
        row = {'format': 'bb-boss-character-ffx-requirement-v2',
               'source_map': 'm26_00_00_00', 'source_part': 'shared-human',
               'source_entity_id': 2600800, 'source_character': 'c0000',
               'source_anibnd_file': 'c0000.anibnd.dcx',
               'source_anibnd_sha256': 'a' * 64, 'source_tae_entries': entries,
               'direct_effect_ids': [7000, 7001]}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'multi-tae', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_character_ffx_requirements': [row]}
        ordinary = copy.deepcopy(plan)
        ordinary.pop('boss_contract')
        ordinary.pop('boss_character_ffx_requirements')
        ordinary['options'] = {}
        ordinary['swaps'] = [{'logical_key': 'ordinary',
                             'destination_keys': ['m24_00_00_00:ordinary']}]
        ordinary['scaling'].update(skip_count=1, skips=[{'logical_key': 'ordinary'}])
        result = combine_ordinary_and_boss_plans(ordinary, [plan, copy.deepcopy(plan)])
        self.assertEqual([row], result['boss_character_ffx_requirements'])
        # Mutation of a nested receipt/plan must not rewrite another donor's proof.
        result['boss_character_ffx_requirements'][0]['source_tae_entries'][1][
            'typed_event_witnesses'][0]['effect_id'] = 9999
        self.assertEqual(7001, entries[1]['typed_event_witnesses'][0]['effect_id'])
        for field, value in (('source_tae_entry_id', 3),
                             ('source_tae_entry', 'chr/c0000/tae/a03.tae'),
                             ('source_tae_sha256', 'b' * 64),
                             ('decoded_event_types', [96, 99, 100, 108, 109, 112, 118])):
            changed = copy.deepcopy(plan)
            changed['boss_character_ffx_requirements'][0]['source_tae_entries'][1][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, 'disagree on character FFX provenance'):
                combine_native_plans('multi-tae', [plan, changed])
        truncated = copy.deepcopy(plan)
        truncated['boss_character_ffx_requirements'][0]['source_tae_entries'].pop()
        with self.assertRaisesRegex(ValueError, 'disagree on character FFX provenance'):
            combine_native_plans('multi-tae', [plan, truncated])

    def test_effect_composition_unions_pinned_banks_and_rejects_native_collisions(self):
        effect = {'destination_map': 'm34_00_00_00', 'destination_event': 'meteor',
                  'destination_event_id': 980032, 'destination_entity_id': 980027}
        merge = {'source_file': 'frpg_sfxbnd_m35.ffxbnd.dcx',
                 'destination_file': 'frpg_sfxbnd_m34.ffxbnd.dcx',
                 'source_sha256': 'a' * 64, 'destination_sha256': 'b' * 64,
                 'policy': 'preserve_destination_union_source_v1', 'required_effect_ids': [640320]}
        requirement = {
            'format': 'bb-boss-emevd-ffx-requirement-v1',
            'source_map': 'm35_00_00_00', 'destination_map': 'm34_00_00_00',
            'source_event_file': 'm35_00_00_00.emevd.dcx',
            'source_event_sha256': 'd' * 64, 'source_event_id': 13504820,
            'destination_event_file': 'm34_00_00_00.emevd.dcx',
            'destination_event_id': 12990020, 'effect_id': 640320,
        }
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'effects', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_sfx_additions': [effect], 'boss_ffx_merges': [merge],
                'boss_emevd_ffx_requirements': [requirement]}
        second = copy.deepcopy(plan)
        second['boss_sfx_additions'][0].update(destination_event='meteor2',
            destination_event_id=980033, destination_entity_id=980028)
        second['boss_ffx_merges'][0]['required_effect_ids'] = [640321, 640320]
        second['boss_emevd_ffx_requirements'][0].update(
            destination_event_id=12990021, effect_id=640321)
        combined = combine_native_plans('effects', [plan, second])
        self.assertEqual([dict(merge, required_effect_ids=[640320, 640321])], combined['boss_ffx_merges'])
        self.assertEqual([effect, second['boss_sfx_additions'][0]], combined['boss_sfx_additions'])
        self.assertEqual([requirement, second['boss_emevd_ffx_requirements'][0]],
                         combined['boss_emevd_ffx_requirements'])
        self.assertEqual([640320], merge['required_effect_ids'])
        second['boss_ffx_merges'][0]['source_sha256'] = 'c' * 64
        with self.assertRaisesRegex(ValueError, 'FFX binder provenance'):
            combine_native_plans('effects', [plan, second])
        for field in ('destination_event', 'destination_event_id', 'destination_entity_id'):
            other = copy.deepcopy(second)
            other.pop('boss_ffx_merges')
            other['boss_sfx_additions'][0][field] = effect[field]
            with self.assertRaisesRegex(ValueError, 'overlap an added SFX'):
                combine_native_plans('effects', [plan, other])
        other = copy.deepcopy(plan)
        other.pop('boss_sfx_additions')
        other['boss_generator_additions'] = [dict(effect, destination_map='m34_00_00_00.msb.dcx')]
        for plans in ([plan, other], [other, plan]):
            with self.assertRaisesRegex(ValueError, 'overlap an added'):
                combine_native_plans('effects', plans)
        duplicate_requirement = copy.deepcopy(second)
        duplicate_requirement.pop('boss_sfx_additions')
        duplicate_requirement.pop('boss_ffx_merges')
        duplicate_requirement['boss_emevd_ffx_requirements'] = [copy.deepcopy(requirement)]
        with self.assertRaisesRegex(ValueError, 'overlap an EMEVD FFX requirement'):
            combine_native_plans('effects', [plan, duplicate_requirement])

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

    def test_region_composition_preserves_geometry_and_rejects_cross_kind_collisions(self):
        region = {'destination_map': 'm23_00_00_00', 'destination_region': 'warp',
                  'destination_entity_id': 980100, 'source_provenance': {'region_sha256': 'a' * 64}}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'r', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_region_additions': [region]}
        result = combine_native_plans('r', [plan])
        self.assertEqual([region], result['boss_region_additions'])
        result['boss_region_additions'][0]['source_provenance']['region_sha256'] = 'b' * 64
        self.assertEqual('a' * 64, region['source_provenance']['region_sha256'])
        with self.assertRaisesRegex(ValueError, 'overlap an added region'):
            combine_native_plans('r', [plan, plan])
        for field, row in (
                ('boss_actor_additions', {'destination_part': 'helper'}),
                ('boss_generator_additions', {'destination_event': 'spawn', 'destination_event_id': 8})):
            other = copy.deepcopy(plan)
            del other['boss_region_additions']
            other[field] = [dict(row, destination_map='m23_00_00_00.msb.dcx',
                                destination_entity_id=980100)]
            for pair in ([plan, other], [other, plan]):
                with self.assertRaisesRegex(ValueError, 'overlap an added'):
                    combine_native_plans('r', pair)
        # Unbound native point regions may share -1, but never their names.
        second = copy.deepcopy(plan)
        region['destination_entity_id'] = -1
        second['boss_region_additions'][0].update(destination_entity_id=-1, destination_region='other')
        self.assertEqual(2, len(combine_native_plans('r', [plan, second])['boss_region_additions']))

    def test_objects_share_part_and_entity_namespaces_and_survive_ordinary_composition(self):
        obj = {'destination_map': 'm26_00_00_00', 'destination_part': 'marker',
               'destination_entity_id': 980200, 'source_provenance': {'part_sha256': 'a' * 64}}
        plan = {'format': 'bb-enemizer-plan-v2', 'seed': 'o', 'dry_run': True,
                'swaps': [], 'scaling': {'enabled': False,
                    'mechanism': 'inferred_static_npc_clone_sp_effect', 'change_count': 0,
                    'changes': [], 'skip_count': 0, 'skips': []}, 'boss_contract': {},
                'boss_object_additions': [obj]}
        ordinary = {'format': 'bb-enemizer-plan-v2', 'seed': 'o', 'dry_run': True, 'options': {},
                    'swaps': [{'logical_key': 'ordinary', 'destination_keys': ['ordinary']}],
                    'scaling': {'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                                'change_count': 0, 'changes': [], 'skip_count': 1,
                                'skips': [{'logical_key': 'ordinary', 'reason': 'unknown tier'}]}}
        result = combine_ordinary_and_boss_plans(ordinary, [plan])
        self.assertEqual([obj], result['boss_object_additions'])
        result['boss_object_additions'][0]['source_provenance']['part_sha256'] = 'b' * 64
        self.assertEqual('a' * 64, obj['source_provenance']['part_sha256'])
        with self.assertRaisesRegex(ValueError, 'already carries boss metadata'):
            combine_ordinary_and_boss_plans(dict(ordinary, boss_object_additions=[obj]), [plan])
        for row in (dict(obj, destination_entity_id=980201), dict(obj, destination_part='other')):
            other = copy.deepcopy(plan)
            del other['boss_object_additions']
            other['boss_actor_additions'] = [row]
            for pair in ([plan, other], [other, plan]):
                with self.assertRaisesRegex(ValueError, 'overlap an added'):
                    combine_native_plans('o', pair)

    def test_seeded_matching_uses_each_boss_once_without_identity(self):
        graph = {key: ('a', 'b', 'c', 'd') for key in ('a', 'b', 'c', 'd')}
        first = assign_donors('one', graph)
        self.assertEqual(first, assign_donors('one', dict(reversed(list(graph.items())))))
        self.assertEqual(['a', 'b', 'c', 'd'], sorted(first.values()))
        for arena, donor in first.items():
            self.assertNotEqual(arena, donor)
        results = {tuple(assign_donors(str(seed), graph).items()) for seed in range(12)}
        self.assertGreater(len(results), 1)

    def test_seeded_matching_respects_route_and_joint_asset_conflicts(self):
        graph = {arena: ('a', 'b', 'c', 'd') for arena in 'abcd'}
        original = assign_donors('conflicts', graph)
        routes = frozenset(original.items())
        first, second = tuple(sorted(routes))[:2]
        self.assertEqual(original, assign_donors('conflicts', graph,
                                                forbidden_combinations=[]))
        banned_route = assign_donors('conflicts', graph,
                                     forbidden_combinations=[{first}])
        self.assertNotEqual(first[1], banned_route[first[0]])
        joint = assign_donors('conflicts', graph,
                              forbidden_combinations=[{first, second}])
        self.assertFalse({first, second}.issubset(joint.items()))
        self.assertEqual(joint, assign_donors('conflicts', dict(reversed(list(graph.items()))),
                                              forbidden_combinations=[{second, first}]))
        # A two-route conflict must not turn either individual route into a ban.
        for retained, excluded in ((first, second), (second, first)):
            alternatives = [{(retained[0], donor)} for donor in graph[retained[0]]
                            if donor != retained[1]]
            forced = assign_donors('conflicts', graph,
                forbidden_combinations=[{first, second}, *alternatives])
            self.assertEqual(retained[1], forced[retained[0]])
            self.assertNotEqual(excluded[1], forced[excluded[0]])
        with self.assertRaisesRegex(ValueError, 'no complete'):
            assign_donors('conflicts', graph,
                          forbidden_combinations=[{('a', donor)} for donor in graph['a']])

    def test_impossible_pool_is_refused_instead_of_dropping_boss(self):
        with self.assertRaisesRegex(ValueError, 'no complete'):
            assign_donors('seed', {'a': ['b'], 'b': ['a'], 'c': ['b']})
        # Every arena has candidates and the union covers every donor, but
        # three arenas compete for only two distinct donors. A global union
        # or nonempty-candidate check cannot detect this impossible pool.
        graph = {'a': ['d', 'e'], 'b': ['d', 'e'], 'c': ['d', 'e'],
                 'd': ['a', 'b', 'c'], 'e': ['a', 'b', 'c']}
        with self.assertRaisesRegex(ValueError, 'no complete'):
            assign_donors('hall-subset', graph)

        # Independent exhaustive oracle: every four-boss directed graph,
        # compared with permutations rather than another matching algorithm.
        roster = ('a', 'b', 'c', 'd')
        edges = [(a, d) for a in roster for d in roster if a != d]
        candidates = list(permutations(roster))
        for mask in range(1 << len(edges)):
            graph = {arena: [] for arena in roster}
            for index, (arena, donor) in enumerate(edges):
                if mask & (1 << index):
                    graph[arena].append(donor)
            possible = any(all(donor in graph[arena]
                               for arena, donor in zip(roster, assignment))
                           for assignment in candidates)
            if possible:
                assignment = assign_donors('exhaustive', graph)
                self.assertEqual(set(roster), set(assignment))
                self.assertEqual(set(roster), set(assignment.values()))
                for arena in roster:
                    self.assertIn(assignment[arena], graph[arena])
            else:
                with self.assertRaisesRegex(ValueError, 'no complete'):
                    assign_donors('exhaustive', graph)

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

    def test_distinct_bullet_owners_compose_preserving_package_order(self):
        anchor = '    $InitializeEvent(0, 20, 200);'
        first = SOURCE.replace(anchor, anchor + '\n    $InitializeEvent(0, 40);')
        group = ('\n    $InitializeEvent(0, 50);\n    CreateBulletOwner(983700);'
                 '\n    $InitializeEvent(0, 51);')
        second = SOURCE.replace(anchor, anchor + group)
        result = compose_event_patches(SOURCE, [first, second], [30])
        self.assertEqual(result, compose_event_patches(SOURCE, [second, first], [30]))
        self.assertIn(group, result)
        duplicate = first.replace('$InitializeEvent(0, 40);',
                                  'CreateBulletOwner(983700);\n    $InitializeEvent(0, 40);')
        with self.assertRaisesRegex(ValueError, 'bullet owner'):
            compose_event_patches(SOURCE, [duplicate, second], [30])
        for expression in ('0', '-1', 'owner_id'):
            with self.assertRaises(ValueError):
                compose_event_patches(SOURCE, [first, second.replace('983700', expression)], [30])

    def test_leading_readiness_resets_commute_but_mixed_or_late_writes_do_not(self):
        header = '$Event(0, Default, function() {'
        self.assertIn(header, SOURCE)
        first = SOURCE.replace(header, header + '\n    SetEventFlag(12995105, OFF);')
        second = SOURCE.replace(header, header + '\n    SetEventFlag(12995905, OFF);')
        result = compose_event_patches(SOURCE, [first, second], [30])
        self.assertEqual(result, compose_event_patches(SOURCE, [second, first], [30]))
        for flag in (12995105, 12995905):
            reset = f'SetEventFlag({flag}, OFF);'
            self.assertEqual(1, result.count(reset))
            self.assertLess(result.index(reset), result.index('$InitializeEvent('))
        for invalid in (
            second.replace('12995905, OFF', '12995905, ON'),
            second.replace('SetEventFlag(12995905, OFF);',
                           'SetEventFlag(12995905, OFF);\n    $InitializeEvent(0, 99);'),
        ):
            with self.assertRaisesRegex(ValueError, 'literal initializers'):
                compose_event_patches(SOURCE, [first, invalid], [30])
        anchor = '    $InitializeEvent(0, 20, 200);'
        late = [SOURCE.replace(anchor, anchor + f'\n    SetEventFlag({flag}, OFF);')
                for flag in (12995105, 12995905)]
        with self.assertRaisesRegex(ValueError, 'literal initializers'):
            compose_event_patches(SOURCE, late, [30])

    def test_conflicting_constructor_and_completion_changes_are_refused(self):
        first = SOURCE.replace('$InitializeEvent(0, 10, 100);', '$InitializeEvent(0, 10, 300);')
        second = SOURCE.replace('$InitializeEvent(0, 10, 100);', '$InitializeEvent(0, 10, 400);')
        with self.assertRaisesRegex(ValueError, 'conflicting boss constructor'):
            compose_event_patches(SOURCE, [first, second], [30])
        with self.assertRaisesRegex(ValueError, 'protected completion event 30'):
            compose_event_patches(SOURCE, [SOURCE.replace('HandleBossDefeat(100)', 'HandleBossDefeat(200)')], [30])

    def test_constructor_range_boundary_is_adjacent_but_its_interior_conflicts(self):
        first = '    $InitializeEvent(0, 10, 100);'
        second = '    $InitializeEvent(0, 20, 200);'
        removed = SOURCE.replace(first + '\n' + second + '\n', '')
        inserted = SOURCE.replace(first, '    $InitializeEvent(0, 40, 400);\n' + first)
        expected = removed.replace('$Event(0, Default, function() {',
                                   '$Event(0, Default, function() {\n    $InitializeEvent(0, 40, 400);')
        for variants in ([removed, inserted], [inserted, removed]):
            self.assertEqual(expected, compose_event_patches(SOURCE, variants, [30]))
        interior = SOURCE.replace(second, '    $InitializeEvent(0, 50, 500);\n' + second)
        for variants in ([removed, interior], [interior, removed]):
            with self.assertRaisesRegex(ValueError, 'overlapping boss constructor'):
                compose_event_patches(SOURCE, variants, [30])

    def test_gascoigne_navigation_retirement_composes_with_adjacent_orphan_initializers(self):
        from tools.bb_inputs import read_blob
        from tools.bb_enemizer.boss_canary import event_blocks
        from tools.bb_enemizer.boss_contracts import PAARL_PACKAGE
        from tools.bb_enemizer.gascoigne_arena_contract import patch_portable_donor_at_gascoigne
        from tools.bb_enemizer.orphan_contract import patch_orphan_at_cleric
        from tools.build_boss_encounters import ORPHAN_ALLOCATION
        bundle = Path(__file__).resolve().parents[1] / 'research/bb_inputs.db'
        def source(name):
            return read_blob(bundle, 'event/' + name).decode('utf-8-sig')
        original = source('m24_01_00_00.emevd.dcx.js')
        gascoigne = patch_portable_donor_at_gascoigne(
            original, PAARL_PACKAGE, source(PAARL_PACKAGE.event_file))
        cleric = patch_orphan_at_cleric(
            original, source('m36_00_00_00.emevd.dcx.js'), ORPHAN_ALLOCATION)
        result = compose_event_patches(original, [gascoigne, cleric], [12411800])
        self.assertEqual(result, compose_event_patches(original, [cleric, gascoigne], [12411800]))
        before, after = event_blocks(original), event_blocks(result)
        self.assertEqual(event_blocks(cleric)[12411700], after[12411700])
        self.assertEqual(before[12411800], after[12411800])
        self.assertNotIn('$InitializeEvent(0, 12415238,', after[0])
        self.assertNotIn('$InitializeEvent(1, 12415238,', after[0])
        for event in (12990601, 12990602, 12990603, 12990604, 12990605, 12414886, 12414887):
            self.assertEqual(1, after[0].count(f'$InitializeEvent(0, {event});'))

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
        self.assertEqual(2, plan['scaling']['change_count'])
        self.assertEqual(0, plan['scaling']['skip_count'])
        self.assertEqual({6000000, 6000001},
                         {row['cloned_npc_param_id'] for row in plan['scaling']['changes']})
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

    def test_one_pairs_initialization_anchor_cannot_land_on_another_pairs_swap(self):
        """bb-archipelago#451: a different pair's actor transplant crashed the
        native writer when it landed on a Part another pair's own primary
        actor initialization still expected to hold that pair's own actor.
        Swaps, actor additions and initializations previously tracked
        occupancy in three separate, never-cross-checked sets."""

        def plan(logical_key, destination_key, **extra):
            return {
                'format': 'bb-enemizer-plan-v2', 'seed': 's', 'dry_run': True,
                'swaps': [{'logical_key': logical_key, 'destination_keys': [destination_key]}],
                'scaling': {
                    'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': 0, 'changes': [], 'skip_count': 1,
                    'skips': [{'logical_key': logical_key, 'reason': 'unknown source or destination tier'}],
                },
                'boss_contract': {'arena': logical_key},
                **extra,
            }

        pair_a = plan('pairA', 'm24_02_00_00:c1000_0000')
        pair_b = plan('pairB', 'm24_05_00_00:c2000_0000', boss_actor_initializations=[{
            'source_map': 's', 'source_part': 'sp', 'source_entity_id': 1,
            'source_archetype': {'model_name': 'x', 'npc_param_id': 1,
                                  'think_param_id': 1, 'chara_init_id': 0},
            'destination_map': 'm24_02_00_00', 'destination_part': 'c1000_0000',
            'destination_entity_id': 999,
        }])
        with self.assertRaisesRegex(ValueError, 'overlap a physical actor placement'):
            combine_native_plans('s', [pair_a, pair_b])

        # A pair's own swap and its own initialization of that swap sharing
        # a Part is the ordinary case (re-stamping dialogue/animation IDs on
        # the actor the pair already swapped) and must stay allowed.
        self_reuse = plan('pairC', 'm24_09_00_00:c3000_0000', boss_actor_initializations=[{
            'source_map': 's', 'source_part': 'sp', 'source_entity_id': 1,
            'source_archetype': {'model_name': 'a', 'npc_param_id': 5,
                                  'think_param_id': 5, 'chara_init_id': 0},
            'destination_map': 'm24_09_00_00', 'destination_part': 'c3000_0000',
            'destination_entity_id': 998,
        }])
        result = combine_native_plans('s', [self_reuse])
        self.assertEqual(1, len(result['boss_actor_initializations']))


if __name__ == '__main__':
    unittest.main()
