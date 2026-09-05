"""Cross-file seed/world drift observed in #362; no game needed."""
from dataclasses import asdict
import unittest
from unittest.mock import Mock, patch

from bb_launcher.workflow import _validate_category8_bridge_rows, ValidationError, LauncherWorkflow
from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
from tools.check_category8_event_runtime import parse_dump


class BridgeContractTests(unittest.TestCase):
    def test_full_current_table_and_seed_subset_are_compatible(self):
        self.assertGreater(len(CATEGORY8_AWARDS), 15)
        rows = [asdict(row) for row in CATEGORY8_AWARDS]
        _validate_category8_bridge_rows(rows)
        _validate_category8_bridge_rows([rows[15]])
        _validate_category8_bridge_rows([])

    def test_field_session_old_lot_is_migrated_without_changing_token_or_ack(self):
        row = asdict(CATEGORY8_AWARDS[15])
        self.assertEqual((row['token_goods_id'], row['item_lot_id'], row['ack_flag']),
                         (9815, 98000150, 12400913))
        row['item_lot_id'] = 98000015
        result = _validate_category8_bridge_rows([row])[0]
        self.assertEqual(result, {**row, 'item_lot_id': 98000150})
        self.assertEqual(row['item_lot_id'], 98000015, 'original seed must not be edited')

    def test_mismatch_stops_before_plan_or_cache_or_process_actions(self):
        row = asdict(CATEGORY8_AWARDS[15])
        row['item_lot_id'] = 12345678
        launcher = Mock()
        workflow = LauncherWorkflow('.', process_launcher=launcher)
        with patch('bb_launcher.workflow.GameInstall.from_root'), \
             patch('bb_launcher.workflow._request_identity', return_value={'category8_awards': [row]}), \
             patch('bb_launcher.workflow.load_process_plan') as plan:
            with self.assertRaisesRegex(ValidationError, 'seed/bridge mismatch'):
                workflow.randomize_and_launch(Mock(), Mock())
            plan.assert_not_called()
            launcher.assert_not_called()

    def test_each_protocol_field_is_checked(self):
        for field in ('token_goods_id', 'item_lot_id', 'gemgen_id', 'ack_flag', 'source_lot_id'):
            with self.subTest(field=field):
                row = asdict(CATEGORY8_AWARDS[15])
                row[field] += 1
                with self.assertRaisesRegex(ValidationError, field):
                    _validate_category8_bridge_rows([row])

    def test_unknown_row_is_not_silently_treated_as_inert(self):
        row = asdict(CATEGORY8_AWARDS[15])
        row['item_key'] = 'future_unreviewed_row'
        with self.assertRaisesRegex(ValidationError, 'not in.*catalog'):
            _validate_category8_bridge_rows([row])

    def test_model_refuses_empty_or_truncated_or_unsupported_dump(self):
        for text in ('', 'event 0 rest=Default instructions=1 parameters=0',
                     'event 0 rest=Default instructions=1 parameters=0\n  [0] 1[0] 00 layer=01'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_dump(text)
