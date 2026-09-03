"""The equipment grant census covers every equipment binding and reads diagnostics back."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from tools.equipment_grant_census import census_rows, classify, main
from worlds.bloodborne import ITEM_ID_BY_KEY
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS


class EquipmentGrantCensusTests(unittest.TestCase):
    def test_every_equipment_binding_is_in_the_census_exactly_once(self):
        rows = census_rows()
        expected = {
            key for key, binding in ITEM_BINDINGS.items()
            if binding.item_category in (0, 1) and key in ITEM_ID_BY_KEY
        }
        self.assertGreater(len(expected), 50)
        self.assertEqual(expected, {row["key"] for row in rows})
        self.assertEqual(len(rows), len({row["ap_item_id"] for row in rows}))
        burial = next(row for row in rows if row["key"] == "burial_blade")
        self.assertEqual(0x004DD1E0, burial["normalized_item_id"])

    def test_script_prints_one_give_command_per_row(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["script"])
        commands = [line for line in out.getvalue().splitlines() if line.startswith("give ")]
        self.assertEqual(len(census_rows()), len(commands))
        for line in commands:
            self.assertTrue(line.split("	")[0].endswith(" CONFIRM"), line)

    def test_classify_separates_verified_from_execution_evidence(self):
        self.assertEqual("verified_slot", classify({
            "terminal_status": "completed",
            "terminal_detail": "tag=x instance insert verified at slot native_result=77",
        }))
        self.assertEqual("execution_evidence_only", classify({
            "terminal_status": "completed",
            "terminal_detail": "tag=x instance insert completed on execution evidence: slot 78 never read back",
        }))
        self.assertEqual("failed", classify({"terminal_status": "failed", "terminal_detail": ""}))

    def test_verdict_joins_diagnostics_with_the_ui_sheet(self):
        rows = census_rows()
        burial = next(row for row in rows if row["key"] == "burial_blade")
        chikage = next(row for row in rows if row["key"] == "chikage")
        root = Path(tempfile.mkdtemp())
        diagnostics = root / "delivery-diagnostics.jsonl"
        diagnostics.write_text("\n".join(json.dumps(record) for record in [
            {"tag": f"operator_grant_{chikage['ap_item_id']}", "terminal_status": "completed",
             "terminal_detail": "instance insert verified at slot native_result=77",
             "inferred_destination": "held", "native_result": 77},
            {"tag": f"operator_grant_{burial['ap_item_id']}", "terminal_status": "completed",
             "terminal_detail": "instance insert completed on execution evidence: slot 78 never read back",
             "inferred_destination": "held", "native_result": 78},
            {"tag": "ap_12", "terminal_status": "completed", "terminal_detail": "ordinary AP delivery"},
        ]) + "\n", encoding="utf-8")
        ui = root / "ui.tsv"
        ui.write_text(f"ap_item_id\tseen\n{burial['ap_item_id']}\tno\n{chikage['ap_item_id']}\tyes\n",
                      encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            main(["verdict", str(diagnostics), "--ui", str(ui)])
        lines = out.getvalue().splitlines()
        self.assertEqual(3, len(lines))  # header + two census rows; the ap_12 line is ignored
        by_id = {int(line.split("\t")[0]): line.split("\t") for line in lines[1:]}
        self.assertEqual("verified_slot", by_id[chikage["ap_item_id"]][4])
        self.assertEqual("yes", by_id[chikage["ap_item_id"]][7])
        self.assertEqual("execution_evidence_only", by_id[burial["ap_item_id"]][4])
        self.assertEqual("no", by_id[burial["ap_item_id"]][7])


if __name__ == "__main__":
    unittest.main()
