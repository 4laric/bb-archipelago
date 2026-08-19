"""Client tests. These need Archipelago on the path, so they are the AP tier.

They exist because the client shipped for two days unable to start: `main()`
read `args.name`, which `get_base_parser` does not define, and nothing ever
constructed the parser to find out. Every assertion here is one the crash would
have failed.
"""

from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path

try:
    from worlds.bloodborne import client as bb_client
    AP_AVAILABLE = True
except ImportError:                      # pragma: no cover - environment dependent
    AP_AVAILABLE = False


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class ParserTests(unittest.TestCase):
    """`launch()` must be able to produce every attribute `main()` reads."""

    def test_parser_supplies_every_attribute_main_reads(self):
        args = bb_client.build_parser().parse_args([])
        for attribute in ("name", "connect", "password", "work_dir", "url"):
            self.assertTrue(hasattr(args, attribute),
                            f"main() reads args.{attribute} and the parser does not define it")

    def test_name_is_accepted_and_carried(self):
        args = bb_client.build_parser().parse_args(["--name", "Tester"])
        self.assertEqual(args.name, "Tester")

    def test_defaults_are_none_not_missing(self):
        args = bb_client.build_parser().parse_args([])
        self.assertIsNone(args.name)
        self.assertIsNone(args.connect)

    def test_work_dir_has_a_default(self):
        self.assertTrue(bb_client.build_parser().parse_args([]).work_dir)

    def test_a_connection_url_is_accepted_positionally(self):
        """The component registers supports_uri=True, so this path must work."""
        from CommonClient import handle_url_arg
        parser = bb_client.build_parser()
        args = handle_url_arg(parser.parse_args(["archipelago://Tester:hunter2@localhost:38281"]),
                              parser=bb_client.build_parser())
        self.assertEqual(args.name, "Tester")
        self.assertEqual(args.password, "hunter2")
        # Upstream sets connect to the whole netloc, userinfo included. Asserting
        # the host is present rather than equality, so this test tracks our parser
        # rather than pinning an upstream quirk we do not own.
        self.assertIn("localhost:38281", args.connect)

    def test_a_bare_url_without_credentials_still_parses(self):
        from CommonClient import handle_url_arg
        args = handle_url_arg(bb_client.build_parser().parse_args(["archipelago://localhost:38281"]),
                              parser=bb_client.build_parser())
        self.assertEqual(args.connect, "localhost:38281")
        self.assertIsNone(args.name)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class AttachReportTests(unittest.TestCase):
    """Inspection is best-effort and must never stop the client starting."""

    def test_never_raises_and_always_says_something(self):
        lines = bb_client.attach_report_lines()
        self.assertIsInstance(lines, list)
        self.assertTrue(lines)
        self.assertTrue(all(isinstance(line, str) for line in lines))

    def test_reports_the_reason_when_it_cannot_inspect(self):
        """Off Windows, or with no shadPS4 running, it explains rather than dying."""
        import worlds.bloodborne.memory as memory
        original = memory.attach_and_verify
        try:
            memory.attach_and_verify = lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("no running process named shadPS4.exe"))
            lines = bb_client.attach_report_lines()
        finally:
            memory.attach_and_verify = original
        self.assertEqual(len(lines), 1)
        self.assertIn("shadPS4 not inspected", lines[0])
        self.assertIn("no running process", lines[0])


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class GrantCommandTests(unittest.TestCase):
    def test_every_shufflable_item_produces_a_command(self):
        from worlds.bloodborne import ITEM_ID_BY_KEY
        for key, ap_id in ITEM_ID_BY_KEY.items():
            self.assertIsNotNone(bb_client.grant_command(ap_id),
                                 f"{key} has no deliverable grant command")

    def test_the_filler_item_produces_a_command(self):
        self.assertIsNotNone(bb_client.grant_command(0xBB0100))

    def test_an_unknown_id_produces_none_rather_than_raising(self):
        self.assertIsNone(bb_client.grant_command(0x7FFFFFFF))

    def test_commands_are_ascii_and_well_formed(self):
        line = bb_client.grant_command(0xBB0100)
        line.encode("ascii")
        parts = line.split()
        self.assertEqual(parts[:2], [bb_client.BRIDGE_PROTOCOL, "GRANT"])
        self.assertEqual(len(parts), 7)
        self.assertTrue(parts[2].startswith("0x") and parts[3].startswith("0x"))

    def test_protocol_and_harness_versions_move_together(self):
        self.assertEqual(bb_client.RUNTIME_BUILD, "bb-0.1.0-r5")
        self.assertEqual(bb_client.BRIDGE_PROTOCOL, "BBGRANT1")
        self.assertEqual(bb_client.HARNESS_VERSION, "bb-native-grant-v5")

    def test_state_reconciliation_is_versioned_tagged_and_terminal(self):
        base = {"build": bb_client.RUNTIME_BUILD, "protocol": bb_client.BRIDGE_PROTOCOL,
                "harness": bb_client.HARNESS_VERSION, "tag": "received_3"}
        self.assertEqual(bb_client.grant_state_outcome(
            {**base, "status": "completed"}, "received_3"), "success")
        self.assertEqual(bb_client.grant_state_outcome(
            {**base, "status": "failed"}, "received_3"), "failure")
        self.assertEqual(bb_client.grant_state_outcome(
            {**base, "status": "completed"}, "received_4"), "pending")
        self.assertEqual(bb_client.grant_state_outcome(
            {**base, "protocol": "old", "status": "completed"}, "received_3"), "incompatible")


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class ManualCheckTests(unittest.TestCase):
    def test_a_check_is_appended_to_the_journal(self):
        from worlds.bloodborne import LOCATION_ID_BY_KEY, WORLD_VERSION
        location = LOCATION_ID_BY_KEY["boss_mergos_wet_nurse"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bb_client.journal_check(root, location)
            bb_client.journal_check(root, location)
            records = [json.loads(line) for line in (
                root / bb_client.CHECK_JOURNAL).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["location_name"], "Mergo's Wet Nurse")
        self.assertEqual(records[0]["location_id"], location)
        self.assertEqual(records[0]["world_version"], WORLD_VERSION)
        self.assertTrue(records[0]["timestamp"].endswith("+00:00"))

    def test_a_typo_gets_a_nearby_location_name(self):
        suggestions = bb_client.location_suggestions("Mergos Loft - Mergos Wet Nurs")
        self.assertIn("Mergo's Wet Nurse", suggestions)


if __name__ == "__main__":
    unittest.main()
