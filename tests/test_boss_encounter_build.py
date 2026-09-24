import hashlib
import json
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.bb_inputs import read_prefix
from tools.bb_enemizer.boss_contracts import CLERIC_ARENA, BSB_PACKAGE, patch_contract_swap, event_blocks
from tools.build_boss_encounters import (
    ARENAS, PACKAGES, GASCOIGNE_ALLOCATION, GASCOIGNE_ARENA_ATTACHMENTS,
    event_record, verify_receipt, lift_zero_argument_initializers, validate_allocations,
    build, disable_player_scaling,
    is_gascoigne_donor_pair, is_gascoigne_arena_pair, reviewed_compatibility, verify_retained_helpers, pin_region_requirements, pin_actor_requirements, pin_object_requirements,
)
from tools.bb_enemizer.boss_pool import compose_event_patches, assign_donors
from tools.bb_enemizer.gascoigne_contract import patch_gascoigne_at_cleric
from tools.bb_enemizer.gascoigne_arena import patch_cleric_at_gascoigne

ROOT = Path(__file__).resolve().parents[1]


class EncounterBuildTests(unittest.TestCase):
    def test_player_disables_every_combined_scaling_clone_before_native_write(self):
        plan = {
            'swaps': [{'logical_key': 'ordinary'}, {'logical_key': 'boss'}],
            'options': {'allow_tier_mixing': True},
            'scaling': {'enabled': True, 'changes': [{'logical_key': 'ordinary'}],
                        'skips': [{'logical_key': 'boss', 'reason': 'no free spEffectID slot'}]},
            'boss_actor_scaling': [{'parent_logical_key': 'ordinary'}],
        }
        disabled = disable_player_scaling(plan)
        self.assertIs(disabled, plan)
        self.assertEqual({'enabled': False, 'change_count': 0, 'changes': []},
                         {key: disabled['scaling'][key]
                          for key in ('enabled', 'change_count', 'changes')})
        self.assertEqual([
            {'logical_key': key, 'reason': 'disabled by player'}
            for key in ('boss', 'ordinary')], disabled['scaling']['skips'])
        self.assertEqual(2, disabled['scaling']['skip_count'])
        self.assertFalse(disabled['options']['normalize_scaling'])
        self.assertNotIn('boss_actor_scaling', disabled)
        with self.assertRaisesRegex(ValueError, 'does not cover'):
            disable_player_scaling({'swaps': plan['swaps'], 'options': {},
                                    'scaling': {'changes': [], 'skips': []}})

    def test_reusable_specialized_donor_routes_reach_the_compiler_pin_gate(self):
        from tools.bb_enemizer.laurence_donor import SUPPORTED_LAURENCE_ARENAS
        from tools.bb_enemizer.logarius_donor import SUPPORTED_LOGARIUS_ARENAS
        from tools.bb_enemizer.orphan_donor import ARENAS as SUPPORTED_ORPHAN_ARENAS

        self.assertEqual(7, len(SUPPORTED_LAURENCE_ARENAS))
        self.assertEqual(9, len(SUPPORTED_LOGARIUS_ARENAS))
        pairs = [(arena.key, donor)
                 for donor, arenas in (('laurence', SUPPORTED_LAURENCE_ARENAS),
                                       ('martyr-logarius', SUPPORTED_LOGARIUS_ARENAS))
                 for arena in arenas]
        pairs.extend((arena, donor) for arena in ('laurence', 'father-gascoigne') for donor in (
            'cleric-beast', 'blood-starved-beast', 'darkbeast-paarl',
            'vicar-amelia', 'amygdala', 'ebrietas'))
        pairs.append(('laurence', 'lady-maria'))
        pairs.extend((arena.key, 'orphan-of-kos') for arena in SUPPORTED_ORPHAN_ARENAS)
        self.assertEqual(35, len(pairs))
        with tempfile.TemporaryDirectory() as temporary:
            compiler = Path(temporary) / 'untrusted-compiler.exe'
            compiler.write_bytes(b'not the pinned compiler')
            for arena, donor in pairs:
                with self.subTest(arena=arena, donor=donor):
                    args = SimpleNamespace(arena=arena, donor=donor,
                                           pool=None, seed='donor-recipe', darkscript=compiler)
                    with self.assertRaisesRegex(ValueError, 'requires pinned DarkScript'):
                        build(args)

    def test_authored_actor_pins_are_verified_instead_of_replaced_with_current_input(self):
        part = {'name': 'core', 'entity_id': 123, 'source_archetype': {'model_name': 'c1000'},
                'source_initialization': {'talk_id': 0}, 'fingerprint': 'a' * 64}
        requirement = {'source_map': 'm32_00_00_00', 'source_part': 'core',
                       'source_entity_id': 123, 'source_archetype': part['source_archetype'],
                       'source_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'a' * 64},
                       'source_initialization': {'talk_id': 0}}
        with patch('tools.build_boss_encounters.inspect_actor_map', return_value={'parts': [part]}):
            self.assertEqual([requirement], pin_actor_requirements(None, [requirement]))
            part['fingerprint'] = 'b' * 64
            with self.assertRaisesRegex(ValueError, 'reviewed actor source_provenance'):
                pin_actor_requirements(None, [requirement])
            part['fingerprint'] = 'a' * 64
            part['source_initialization'] = {'talk_id': 1}
            with self.assertRaisesRegex(ValueError, 'reviewed actor source_initialization'):
                pin_actor_requirements(None, [requirement])

    def test_region_geometry_and_both_original_anchors_must_match_reviewed_pins(self):
        requirement = {'source_map': 'm32_00_00_00', 'source_region': 'warp',
                       'source_entity_id': 3202800,
                       'source_provenance': {'format': 'bb-boss-region-pin-v1', 'region_sha256': 'a' * 64},
                       'source_anchor_part': 'core', 'destination_map': 'm24_02_00_00',
                       'destination_anchor_part': 'core',
                       'source_anchor_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'b' * 64},
                       'destination_anchor_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'b' * 64}}
        region = {'name': 'warp', 'entity_id': 3202800, 'fingerprint': 'a' * 64}
        args = SimpleNamespace(_region_pin_cache={'m32_00_00_00': {'regions': [region]}})
        actor_report = {'parts': [{'name': 'core', 'fingerprint': 'b' * 64}]}
        with patch('tools.build_boss_encounters.inspect_actor_map', return_value=actor_report):
            self.assertEqual([requirement], pin_region_requirements(args, [requirement]))
            region['fingerprint'] = 'c' * 64
            with self.assertRaisesRegex(ValueError, 'region requirement'):
                pin_region_requirements(args, [requirement])
            region['fingerprint'] = 'a' * 64
            for role in ('source', 'destination'):
                requirement[role + '_anchor_provenance']['part_sha256'] = 'c' * 64
                with self.assertRaisesRegex(ValueError, role + ' region anchor'):
                    pin_region_requirements(args, [requirement])
                requirement[role + '_anchor_provenance']['part_sha256'] = 'b' * 64

    def test_object_model_and_native_fields_require_reviewed_source_fingerprint(self):
        requirement = {'source_map': 'm26_00_00_00', 'source_part': 'marker',
                       'source_entity_id': 2601857,
                       'source_provenance': {'format': 'bb-boss-object-pin-v1', 'part_sha256': 'a' * 64},
                       'source_anchor_part': 'core', 'destination_map': 'm24_02_00_00',
                       'destination_anchor_part': 'core',
                       'source_anchor_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'b' * 64},
                       'destination_anchor_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': 'b' * 64}}
        obj = {'name': 'marker', 'entity_id': 2601857, 'fingerprint': 'a' * 64}
        args = SimpleNamespace(_object_pin_cache={'m26_00_00_00': {'objects': [obj]}})
        with patch('tools.build_boss_encounters.inspect_actor_map',
                   return_value={'parts': [{'name': 'core', 'fingerprint': 'b' * 64}]}):
            self.assertEqual([requirement], pin_object_requirements(args, [requirement]))
            obj['fingerprint'] = 'c' * 64
            with self.assertRaisesRegex(ValueError, 'object requirement'):
                pin_object_requirements(args, [requirement])

    def test_retired_helper_controller_requires_the_original_native_actor(self):
        helper = {'map': 'm25_00_00_00', 'part': 'c9010_0002', 'entity_id': 2500802,
                  'archetype': {'model_name': 'c9010', 'npc_param_id': 232000,
                                'think_param_id': 232000, 'chara_init_id': 0},
                  'source_provenance': {'part_sha256': 'a' * 64},
                  'source_initialization': {'talk_id': 0, 'unk_t18': -1,
                                            'init_anim_id': -1, 'damage_anim_id': -1}}
        part = {'name': helper['part'], 'entity_id': helper['entity_id'],
                'source_archetype': helper['archetype'], 'fingerprint': 'a' * 64,
                'source_initialization': helper['source_initialization']}
        plan = {'boss_contract': {'retained_destination_helpers': [helper]}}
        with patch('tools.build_boss_encounters.inspect_actor_map', return_value={'parts': [part]}):
            verify_retained_helpers(None, plan)
            # Same NPC identity is insufficient: the helper's native actor may
            # have moved or changed initialization while the inventory stayed.
            part['fingerprint'] = 'b' * 64
            with self.assertRaisesRegex(ValueError, 'original native pin'):
                verify_retained_helpers(None, plan)

    def test_reviewed_pool_includes_gascoigne_without_reusing_or_omitting_donors(self):
        graph = reviewed_compatibility()
        self.assertEqual(22, len(graph))
        assignments = []
        for seed in (f'seed-{index}' for index in range(256)):
            assignment = assign_donors(seed, graph)
            assignments.append(assignment)
            self.assertEqual(set(graph), set(assignment))
            self.assertEqual(set(graph), set(assignment.values()))
            self.assertIn(assignment['ludwig'], ('cleric-beast', 'laurence'))
            self.assertIn(assignment['living-failures'], ('blood-starved-beast', 'lady-maria', 'laurence'))
            for arena, donor in assignment.items():
                self.assertNotEqual(arena, donor)
                self.assertIn(donor, graph[arena])
        self.assertGreaterEqual(len({tuple(sorted(assignment.items())) for assignment in assignments}), 48)
        for arena in graph:
            self.assertGreaterEqual(len({a[arena] for a in assignments}), 2, arena)
        for donor in graph:
            self.assertGreaterEqual(len({arena for a in assignments for arena, value in a.items() if value == donor}), 2, donor)
        for arena, donor in (('martyr-logarius', 'mergos-wet-nurse'), ('mergos-wet-nurse', 'darkbeast-paarl'), ('rom', 'celestial-emissary')):
            self.assertTrue(any(assignment[arena] == donor for assignment in assignments))

    def test_allocated_event_cannot_alias_original_actor_or_operand_in_another_map(self):
        with self.assertRaisesRegex(ValueError, 'original corpus'):
            validate_allocations(ROOT / 'research/bb_inputs.db', [], [{'added_event_ids': [2410810]}], {})
        with self.assertRaisesRegex(ValueError, 'across output maps'):
            validate_allocations(ROOT / 'research/bb_inputs.db', [],
                                 [{'added_event_ids': [12990001]}, {'added_event_ids': [12990001]}], {})

    def test_native_no_payload_initializer_requires_a_declared_no_argument_target(self):
        source = '$Event(0, Default, function() {\n    InitializeEvent(0, 123);\n});\n' + \
                 '$Event(123, Default, function() {\n    EndEvent();\n});\n'
        result = lift_zero_argument_initializers(source)
        self.assertEqual(source.replace('    InitializeEvent', '    $InitializeEvent'), result)
        with self.assertRaisesRegex(ValueError, 'zero-parameter event'):
            lift_zero_argument_initializers(source.replace('$Event(123, Default, function()',
                                                           '$Event(123, Default, function(actor)'))

    @classmethod
    def setUpClass(cls):
        sources = {Path(name).name: blob.decode('utf-8-sig')
                   for name, blob in read_prefix(ROOT / 'research/bb_inputs.db', 'event/').items()}
        cls.before = sources[CLERIC_ARENA.event_file]
        cls.after = patch_contract_swap(CLERIC_ARENA, BSB_PACKAGE, cls.before, sources[BSB_PACKAGE.event_file])
        original, patched = event_blocks(cls.before), event_blocks(cls.after)
        cls.changed = [key for key in original if original[key] != patched[key]]
        # Binary fingerprint inspection is exercised by native tests. Here a
        # distinct fingerprint witnesses every edit selected from real scripts.
        cls.pins = {str(key): hashlib.sha256(str(key).encode()).hexdigest() for key in cls.changed}

    def test_record_binds_real_edit_set_and_both_arena_completions(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / 'm24_01_00_00.emevd.dcx'
            original.write_bytes(b'original event binary')
            result = event_record(original, self.before, self.after, self.pins, [12411700, 12411800])
            self.assertEqual(9, len(result['changed_event_ids']))
            self.assertEqual(sorted(self.changed), result['changed_event_ids'])
            self.assertEqual([12411700, 12411800], result['protected_completion_event_ids'])
            self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), result['original_event_sha256'])

    def test_unrelated_boss_progression_change_is_refused(self):
        blocks = event_blocks(self.after)
        # Change inside the actual declaration body, so it is part of the event.
        changed = self.after.replace(blocks[12411800], blocks[12411800].replace('HandleBossDefeat(', 'ForceCharacterDeath('))
        with self.assertRaisesRegex(ValueError, 'completion event 12411800'):
            event_record(Path('unused'), self.before, changed, self.pins, [12411700, 12411800])

    def test_missing_compiled_fingerprint_refuses_record(self):
        incomplete = dict(self.pins)
        del incomplete[str(self.changed[0])]
        with self.assertRaisesRegex(ValueError, 'compiled event fingerprint'):
            event_record(Path('unused'), self.before, self.after, incomplete, [12411700])

    def test_terminal_bridge_only_changes_combat_wait_preserving_rewards(self):
        from tools.bb_enemizer.boss_pool import compose_event_patches
        bridge = 98000123  # Synthetic test allocation; not a registered game ID.
        terminal = {'event_id': 12411700, 'original_actor': 2410800, 'bridge_event_id': bridge}
        after = self.after.replace('WaitFor(CharacterDead(2410800));', f'WaitFor(EventFlag({bridge}));')
        after += f'\n$Event({bridge}, Default, function() {{\n    WaitFor(CharacterDead(999));\n}});\n'
        pins = {**self.pins, '12411700': 'c' * 64, str(bridge): 'd' * 64}
        with tempfile.TemporaryDirectory() as temporary:
            original = Path(temporary) / 'original.emevd.dcx'
            original.write_bytes(b'original')
            record = event_record(original, self.before, after, pins, [12411700, 12411800], (terminal,))
            self.assertEqual([terminal], record['terminal_predicates'])
            self.assertIn(12411700, record['changed_event_ids'])
            self.assertEqual([bridge], record['added_event_ids'])
            composed = compose_event_patches(self.before, [after], [12411700, 12411800], (terminal,))
            self.assertEqual(event_blocks(after), event_blocks(composed))
            corrupted = after.replace('AwardAchievement(21);', 'AwardAchievement(14);')
            with self.assertRaisesRegex(ValueError, 'non-predicate progression'):
                event_record(original, self.before, corrupted, pins, [12411700, 12411800], (terminal,))
            with self.assertRaisesRegex(ValueError, 'non-predicate progression'):
                compose_event_patches(self.before, [corrupted], [12411700, 12411800], (terminal,))

    def test_reciprocal_gascoigne_variants_compose_with_both_m24_completions_protected(self):
        gascoigne_donor = patch_gascoigne_at_cleric(self.before, GASCOIGNE_ALLOCATION)
        gascoigne_arena = patch_cleric_at_gascoigne(
            self.before, self.before, GASCOIGNE_ARENA_ATTACHMENTS)
        donor_pair = (ARENAS['cleric-beast'], PACKAGES['father-gascoigne'])
        arena_pair = (ARENAS['father-gascoigne'], PACKAGES['cleric-beast'])
        self.assertTrue(is_gascoigne_donor_pair(*donor_pair))
        self.assertTrue(is_gascoigne_arena_pair(*arena_pair))
        self.assertFalse(is_gascoigne_donor_pair(*arena_pair))
        terminal = ({'event_id': 12411700, 'original_actor': 2410800,
                     'bridge_event_id': GASCOIGNE_ALLOCATION.terminal_bridge_event_id},)
        combined = compose_event_patches(self.before, [gascoigne_donor, gascoigne_arena],
                                         [12411700, 12411800], terminal)
        original, output = event_blocks(self.before), event_blocks(combined)
        self.assertEqual(original[12411800], output[12411800])
        self.assertIn('WaitFor(EventFlag(12414783));', output[12411700])
        self.assertIn('$InitializeEvent(0, 12414780);', output[0])
        self.assertIn('$InitializeEvent(0, 12990400);', output[0])
        self.assertSetEqual(
            {12414780, 12414781, 12414782, 12414783,
             *GASCOIGNE_ARENA_ATTACHMENTS.values()},
            set(output).difference(original),
        )

    def test_receipt_detects_mutation_and_unlisted_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'dvdroot_ps4/event/m24_01_00_00.emevd.dcx'
            output.parent.mkdir(parents=True)
            output.write_bytes(b'verified event')
            receipt = {'format': 'bb-boss-encounters-v1', 'applied': True, 'files': [{
                'path': output.relative_to(root).as_posix(), 'size': output.stat().st_size,
                'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            }]}
            (root / 'boss-encounters-report.json').write_text(json.dumps(receipt))
            self.assertEqual(receipt, verify_receipt(root))
            output.write_bytes(b'altered event')
            with self.assertRaisesRegex(ValueError, 'output changed'):
                verify_receipt(root)
            output.write_bytes(b'verified event')
            (root / 'unexpected').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'file set'):
                verify_receipt(root)


if __name__ == '__main__':
    unittest.main()
