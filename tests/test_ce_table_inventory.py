from __future__ import annotations

import unittest

from tools.audit_ce_tables import audit, manifest_rows, unresolved_tables


class CheatEngineTableInventoryTests(unittest.TestCase):
    def test_manifest_exactly_covers_every_unresolved_fixed_address_table(self):
        rows = manifest_rows()
        self.assertEqual(34, len(rows), "reviewed v0.17 inventory changed")
        self.assertEqual({row["table"] for row in rows}, unresolved_tables())

    def test_every_legacy_table_has_a_reviewed_disposition_and_rationale(self):
        rows = manifest_rows()
        self.assertEqual(34, len(rows), "empty input would make the coverage assertions meaningless")
        unexpected = {row["disposition"] for row in rows} - {"archive", "retire"}
        missing_reasons = [row["table"] for row in rows if not row["reason"].strip()]
        self.assertFalse(unexpected, f"invalid dispositions: {sorted(unexpected)}")
        self.assertFalse(missing_reasons, f"missing rationales: {missing_reasons}")

    def test_current_table_keeps_its_launch_relative_guard(self):
        errors = audit()
        self.assertFalse(errors, "\n".join(errors))


if __name__ == "__main__":
    unittest.main()
