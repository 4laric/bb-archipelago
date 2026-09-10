"""Synthetic receipt composition and stale/mixed overlay detection."""
import json
import tempfile
import unittest
from pathlib import Path

from tools.verify_boss_canary import (ADAPTER, AI, AI_REPORT, CHANGED_EVENTS, COMPLETION_EVENT,
    EVENT, EXPECTED_FILES, GAMEPARAM, PLAN, RECEIPT, SCALING, SOURCE_PLAN, digest, verify, worksheet)


class BossCanaryVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in EXPECTED_FILES:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(name.encode())
        plan = {'boss_adapter': ADAPTER, 'required_event_overlay': EVENT, 'swap_count': 1,
                'swaps': [{'logical_key': 'synthetic'}], 'scaling': {'applied': True}}
        self.write(PLAN, plan)
        self.write(SOURCE_PLAN, plan)
        self.write(SCALING, {'applied': True, 'source_plan_sha256': digest(self.root / SOURCE_PLAN),
            'output_plan_sha256': digest(self.root / PLAN), 'output_gameparam_sha256': digest(self.root / GAMEPARAM),
            'source_gameparam_sha256': 'a' * 64, 'paramdef_sha256': 'b' * 64})
        self.write(AI_REPORT, {'applied': True, 'plan_sha256': digest(self.root / PLAN),
            'gameparam_sha256': 'a' * 64, 'paramdef_sha256': 'b' * 64,
            'maps': [{'map': Path(AI).name, 'missing_goals_after': 0, 'output_sha256': digest(self.root / AI)}]})
        self.receipt = {'format': 'bb-boss-adapter-v1', 'adapter': ADAPTER, 'applied': True,
            'completion_event': COMPLETION_EVENT, 'ap_location': 'boss_cleric_beast',
            'changed_events': CHANGED_EVENTS, 'output_event_sha256': digest(self.root / EVENT)}
        self.seal()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value), encoding='utf-8')

    def seal(self):
        self.receipt['files'] = [{'path': name, 'sha256': digest(self.root / name),
                                 'size': (self.root / name).stat().st_size} for name in sorted(EXPECTED_FILES)]
        self.write(RECEIPT, self.receipt)

    def test_consistent_build_has_unrun_worksheet_tied_to_receipt(self):
        result = verify(self.root)
        self.assertEqual(10, result['files_verified'])
        self.assertFalse(result['runtime_validated'])
        text = worksheet(result)
        self.assertIn(digest(self.root / RECEIPT), text)
        self.assertIn('12411700', text)
        self.assertEqual(11, text.count('| Not run |'))

    def test_one_altered_map_is_refused_even_at_same_size(self):
        name = next(name for name in EXPECTED_FILES if name.endswith('.msb.dcx'))
        path = self.root / name
        path.write_bytes(b'x' * path.stat().st_size)
        with self.assertRaisesRegex(ValueError, 'file changed'):
            verify(self.root)

    def test_extra_overlay_file_and_missing_map_are_refused(self):
        extra = self.root / 'extra.txt'
        extra.write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'unexpected files'):
            verify(self.root)
        extra.unlink()
        (self.root / AI).unlink()
        with self.assertRaisesRegex(ValueError, 'missing or unexpected'):
            verify(self.root)

    def test_old_duplicate_and_traversal_file_receipts_are_refused(self):
        good = self.receipt['files']
        for rows in ([], good + [good[0]], [{**good[0], 'path': '../outside'}] + good[1:]):
            with self.subTest(rows=len(rows)):
                self.receipt['files'] = rows
                self.write(RECEIPT, self.receipt)
                with self.assertRaisesRegex(ValueError, 'every canary file exactly once'):
                    verify(self.root)

    def test_individually_sealed_but_mixed_ai_plan_is_refused(self):
        path = self.root / AI_REPORT
        ai = json.loads(path.read_text())
        ai['plan_sha256'] = 'c' * 64
        self.write(AI_REPORT, ai)
        self.seal()
        with self.assertRaisesRegex(ValueError, 'AI plan provenance'):
            verify(self.root)

    def test_unresolved_goal_and_wrong_completion_contract_are_refused(self):
        ai = json.loads((self.root / AI_REPORT).read_text())
        ai['maps'][0]['missing_goals_after'] = 1
        self.write(AI_REPORT, ai)
        self.seal()
        with self.assertRaisesRegex(ValueError, 'missing goals'):
            verify(self.root)
        self.receipt['completion_event'] = 12301800
        self.write(RECEIPT, self.receipt)
        with self.assertRaisesRegex(ValueError, 'completion contract'):
            verify(self.root)


if __name__ == '__main__':
    unittest.main()
