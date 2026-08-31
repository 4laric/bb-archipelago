from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.audit_shop_randomization import audit  # noqa: E402


class ShopRandomizationAuditTests(unittest.TestCase):
    def test_all_ten_gate_identities_are_independently_witnessed(self):
        report = audit(REPO)
        self.assertEqual(10, report["gate_count"])
        self.assertEqual(set(range(12101000, 12101010)),
                         {row["qwc_id"] for row in report["gates"]})
        self.assertEqual(set(range(4110, 4120)),
                         {row["goods_id"] for row in report["gates"]})

    def test_all_badges_are_in_the_world_model(self):
        report = audit(REPO)
        self.assertTrue(report["ready"])
        self.assertEqual(10, report["modeled_badge_count"])
        self.assertEqual([], report["missing_badges"])


if __name__ == "__main__":
    unittest.main()
