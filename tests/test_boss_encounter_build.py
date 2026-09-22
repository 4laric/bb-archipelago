import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_prefix
from tools.bb_enemizer.boss_contracts import CLERIC_ARENA, BSB_PACKAGE, patch_contract_swap, event_blocks
from tools.build_boss_encounters import (
    ARENAS, PACKAGES, GASCOIGNE_ALLOCATION, GASCOIGNE_ARENA_ATTACHMENTS,
    event_record, verify_receipt, lift_zero_argument_initializers, validate_allocations,
    is_gascoigne_donor_pair, is_gascoigne_arena_pair,
)
from tools.bb_enemizer.boss_pool import compose_event_patches
from tools.bb_enemizer.gascoigne_contract import patch_gascoigne_at_cleric
from tools.bb_enemizer.gascoigne_arena import patch_cleric_at_gascoigne

ROOT = Path(__file__).resolve().parents[1]


class EncounterBuildTests(unittest.TestCase):
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
        self.assertIn('WaitFor(EventFlag(12990004));', output[12411700])
        self.assertIn('$InitializeEvent(0, 12990001);', output[0])
        self.assertIn('$InitializeEvent(0, 12990400);', output[0])
        self.assertSetEqual(
            {12990001, 12990002, 12990003, 12990004,
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
