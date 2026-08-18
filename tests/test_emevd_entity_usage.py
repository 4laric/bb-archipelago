import csv
import json
import unittest
from pathlib import Path

from tools.build_emevd_entity_usage import (
    event_definitions, line_uses, materialize_bundle, operation_family, parameter_uses,
)


class EmevdEntityUsageTests(unittest.TestCase):
    def test_character_operand_is_not_just_a_lexical_match(self):
        operations, code, comment = line_uses("WaitFor(CharacterDead(2100800));", 2100800)
        self.assertEqual(["CharacterDead"], operations)
        self.assertTrue(code)
        self.assertFalse(comment)
        self.assertEqual("character_operation", operation_family(operations[0]))

    def test_event_id_collision_remains_distinct(self):
        operations, code, _ = line_uses("$InitializeEvent(0, 12100800);", 12100800)
        self.assertEqual(["$InitializeEvent:event_id"], operations)
        self.assertTrue(code)
        self.assertEqual("event_id_collision", operation_family(operations[0]))

    def test_initializer_payload_is_not_an_event_id_collision(self):
        operations, code, _ = line_uses("$InitializeEvent(0, 12100800, 2100800);", 2100800)
        self.assertEqual(["$InitializeEvent:argument"], operations)
        self.assertTrue(code)
        self.assertEqual("event_argument", operation_family(operations[0]))

    def test_comment_match_is_not_code(self):
        operations, code, comment = line_uses("SetEventFlag(100, ON); // entity 2100800", 2100800)
        self.assertEqual([], operations)
        self.assertFalse(code)
        self.assertTrue(comment)

    def test_initializer_parameter_can_be_resolved_to_character_use(self):
        lines = [
            "$Event(12100000, Default, function(chrEntityId, eventFlagId) {",
            "    WaitFor(CharacterDead(chrEntityId));",
            "    SetEventFlag(eventFlagId, ON);",
            "});",
        ]
        parameters, body = event_definitions(lines)[12100000]
        self.assertEqual(["chrEntityId", "eventFlagId"], parameters)
        self.assertEqual(["resolved/CharacterDead"], parameter_uses(body, parameters[0]))
        self.assertEqual("character_operation", operation_family("resolved/CharacterDead"))

    def test_committed_census_is_complete_and_policy_neutral(self):
        root = Path(__file__).resolve().parents[1]
        summary = json.loads((root / "research/enemizer/emevd_entity_usage_summary.json").read_text())
        with (root / "research/enemizer/emevd_entity_usage.tsv").open(encoding="utf-8", newline="") as handle:
            census_rows = sum(1 for _ in csv.DictReader(handle, delimiter="\t"))
        self.assertFalse(summary["policy_changed"])
        self.assertEqual(2399, summary["physical_slots"])
        self.assertEqual(summary["physical_slots"], census_rows)

    def test_committed_bundle_carries_both_census_inputs(self):
        import tempfile
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            inventory, events = materialize_bundle(root / "research/bb_inputs.db", Path(temporary))
            self.assertTrue(inventory.is_file())
            self.assertGreater(len(list(events.glob("m*.emevd.dcx.js"))), 20)


if __name__ == "__main__":
    unittest.main()
