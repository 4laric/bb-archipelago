import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import CHANGED_EVENTS, COMPLETION_EVENT, event_blocks, patch_event_source, plan_canary
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.build_boss_canary import compile_events

BUNDLE = Path(__file__).resolve().parents[1] / 'research/bb_inputs.db'


class BossCanaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        files = read_prefix(BUNDLE, 'event/')
        cls.destination = next(v.decode('utf-8-sig') for k, v in files.items() if k.endswith('m24_01_00_00.emevd.dcx.js'))
        cls.donor = next(v.decode('utf-8-sig') for k, v in files.items() if k.endswith('m23_00_00_00.emevd.dcx.js'))

    def test_only_reviewed_events_change_and_progression_is_preserved(self):
        before = event_blocks(self.destination)
        after = event_blocks(patch_event_source(self.destination, self.donor))
        self.assertEqual(set(before), set(after))
        self.assertEqual(CHANGED_EVENTS, sorted(k for k in before if before[k] != after[k]))
        self.assertEqual(before[COMPLETION_EVENT], after[COMPLETION_EVENT])
        for event_id in (12414707, 12414708):
            self.assertIn('2410800', after[event_id])
            self.assertNotIn('2300800', after[event_id])
            self.assertNotIn('12301800', after[event_id])
        self.assertIn('7010', after[12414707])
        self.assertIn('7011', after[12414708])
        self.assertNotIn('IssueShortWarpRequest', after[12411702])
        self.assertIn('7001', after[12411702])
        self.assertIn('unused_npcPartId', after[12414710])

    def test_source_drift_is_refused(self):
        with self.assertRaisesRegex(ValueError, 'unsupported original'):
            patch_event_source(self.destination.replace('3028', '3029'), self.donor)
        with self.assertRaisesRegex(ValueError, 'unsupported original'):
            patch_event_source(self.destination, self.donor.replace('7010', '7012'))

    def test_compiler_success_without_expected_file_is_refused(self):
        with tempfile.TemporaryDirectory() as temp, patch('tools.build_boss_canary.subprocess.run') as run:
            run.return_value.stdout = b'per-file error'
            run.return_value.stderr = b''
            with self.assertRaisesRegex(ValueError, 'per-file error'):
                compile_events(Path('compiler'), 'compile', Path(temp), Path(temp) / 'output', 'missing')
            self.assertTrue((Path(temp) / 'output').is_dir())

    def test_canary_requires_all_original_map_states_and_normalization(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'slots.tsv'
            path.write_bytes(read_blob(BUNDLE, 'mined/msb_enemies.tsv'))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        plan = plan_canary(slots, npcs, effects)
        self.assertEqual(1, plan['swap_count'])
        self.assertEqual(3, len(plan['swaps'][0]['destination_keys']))
        self.assertEqual(1, plan['scaling']['change_count'])
        with self.assertRaisesRegex(ValueError, 'provenance'):
            plan_canary([s for s in slots if s.map_name != 'm24_01_00_01'], npcs, effects)


if __name__ == '__main__':
    unittest.main()
