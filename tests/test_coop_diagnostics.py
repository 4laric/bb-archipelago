import argparse
import io
import json
import os
from pathlib import Path
import queue
import tempfile
import unittest
from unittest.mock import patch

from tools import coop_diagnostics as diag


class CoopDiagnosticsTests(unittest.TestCase):
    def test_gpu_unavailable_values_are_not_zero(self):
        rows = diag.parse_gpu_csv('0, GPU-123, RTX test, 12288, 8000, 25, [N/A], [Not Supported]\n')
        self.assertEqual(rows[0]['memory_used_mib'], 8000)
        self.assertIsNone(rows[0]['temperature_c'])
        self.assertIsNone(rows[0]['power_w'])

    def test_gpu_bad_shape_fails(self):
        for value in ('', '0, GPU-123\n'):
            with self.assertRaises(ValueError):
                diag.parse_gpu_csv(value)

    def test_multiple_gpus_keep_identity(self):
        text = '0, GPU-A, first, 4096, 10, 0, 40, 3\n1, GPU-B, second, 12288, 9000, 95, 70, 90\n'
        self.assertEqual([x['uuid'] for x in diag.parse_gpu_csv(text)], ['GPU-A', 'GPU-B'])

    def test_identification_refuses_missing_process(self):
        with self.assertRaises(ValueError):
            diag.identify({'processes': []}, {'A': 42})

    def test_pid_reuse_and_exit_are_failures(self):
        identity = {'A': {'pid': 42, 'started_utc': 'first', 'executable': 'game.exe'}}
        item = {'pid': 42, 'status': 'ok', 'started_utc': 'first', 'executable': 'game.exe'}
        self.assertIsNone(diag.check_identity({'processes': [item]}, identity))
        item['started_utc'] = 'second'
        self.assertIn('identity changed', diag.check_identity({'processes': [item]}, identity))
        self.assertIn('unavailable', diag.check_identity({'processes': []}, identity))

    def test_labels_use_input_timestamp_and_one_sequence(self):
        commands = queue.Queue()
        commands.put(({'time_ms': 100, 'monotonic_ns': 200}, 'mark A bell_before'))
        commands.put(({'time_ms': 101, 'monotonic_ns': 300}, 'stop'))
        output = io.StringIO()
        writer = diag.Recorder(output)
        writer.write('sample')
        self.assertTrue(diag.drain_commands(commands, writer))
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row['seq'] for row in rows], [1, 2, 3])
        self.assertEqual(rows[1]['time_ms'], 100)
        self.assertEqual(rows[1]['label'], 'bell_before')

    def test_failed_setup_emits_failure_without_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(host_pid=42, guest_pid=None, interval=5,
                                      duration=10, output=Path(directory) / 'capture.jsonl')
            with patch.object(diag, 'snapshot', side_effect=RuntimeError('planted failure')):
                self.assertEqual(diag.record(args), 2)
            rows = [json.loads(line) for line in args.output.read_text().splitlines()]
            self.assertEqual([x['type'] for x in rows], ['header', 'probe_install_failed'])
            with self.assertRaises(FileExistsError):
                diag.record(args)

    def test_duplicate_pids_rejected_before_output(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(host_pid=42, guest_pid=42, interval=5,
                                      duration=10, output=Path(directory) / 'capture.jsonl')
            with self.assertRaises(ValueError):
                diag.record(args)
            self.assertFalse(args.output.exists())

    def test_failure_during_capture_has_footer(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(host_pid=42, guest_pid=None, interval=5,
                                      duration=10, output=Path(directory) / 'capture.jsonl')
            item = {'pid': 42, 'name': 'test', 'status': 'ok', 'started_utc': 'first',
                    'executable': __file__}
            with patch.object(diag, 'snapshot', side_effect=[{'processes': [item]}, RuntimeError('lost')]), \
                    patch.object(diag, 'read_commands'):
                self.assertEqual(diag.record(args), 2)
            rows = [json.loads(line) for line in args.output.read_text().splitlines()]
            self.assertEqual(rows[-2]['type'], 'diagnostic_failure')
            self.assertEqual(rows[-1]['reason'], 'sampler_failure')

    def test_successful_capture_records_sample_and_operator_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(host_pid=42, guest_pid=None, interval=5,
                                      duration=10, output=Path(directory) / 'capture.jsonl')
            item = {'pid': 42, 'name': 'test', 'status': 'ok', 'started_utc': 'first',
                    'executable': __file__}
            original_drain = diag.drain_commands
            calls = 0

            def controlled_drain(commands, recorder):
                nonlocal calls
                calls += 1
                if calls == 2:
                    commands.put((diag.stamp(), 'mark A planted_action'))
                    commands.put((diag.stamp(), 'stop'))
                return original_drain(commands, recorder)

            with patch.object(diag, 'snapshot', return_value={'processes': [item]}), \
                    patch.object(diag, 'read_commands'), \
                    patch.object(diag, 'drain_commands', side_effect=controlled_drain):
                self.assertEqual(diag.record(args), 0)
            rows = [json.loads(line) for line in args.output.read_text().splitlines()]
            self.assertEqual([x['type'] for x in rows],
                             ['header', 'ready', 'sample', 'marker', 'marker', 'footer'])
            self.assertEqual(rows[3]['label'], 'planted_action')
            self.assertEqual(rows[-1]['reason'], 'operator_stop')

    def test_interval_and_duration_bounds(self):
        for interval, duration in [(0, 10), (float('nan'), 10), (5, float('inf')), (5, 1801)]:
            with tempfile.TemporaryDirectory() as directory:
                args = argparse.Namespace(host_pid=42, guest_pid=None, interval=interval,
                                          duration=duration, output=Path(directory) / 'capture.jsonl')
                with self.assertRaises(ValueError):
                    diag.record(args)
                self.assertFalse(args.output.exists())


@unittest.skipUnless(os.name == 'nt', 'Windows telemetry positive control')
class WindowsPositiveControl(unittest.TestCase):
    def test_sampler_captures_known_process_and_planted_allocation(self):
        # This controls OS telemetry only; it does not start Bloodborne or shadPS4.
        before = diag.snapshot([os.getpid()])
        allocation = bytearray(64 * 1024 * 1024)
        after = diag.snapshot([os.getpid()])
        first, second = before['processes'][0], after['processes'][0]
        self.assertEqual(first['status'], 'ok')
        self.assertEqual(second['pid'], os.getpid())
        self.assertEqual(first['started_utc'], second['started_utc'])
        self.assertGreaterEqual(second['private_bytes'] - first['private_bytes'], 48 * 1024 * 1024)
        self.assertGreater(after['system']['available_ram_bytes'], 0)
        self.assertEqual(len(allocation), 64 * 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
