import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_prefix
from tools.bb_enemizer.boss_contracts import CLERIC_ARENA, BSB_PACKAGE, patch_contract_swap, event_blocks
from tools.build_boss_encounters import event_record, verify_receipt

ROOT = Path(__file__).resolve().parents[1]


class EncounterBuildTests(unittest.TestCase):
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
