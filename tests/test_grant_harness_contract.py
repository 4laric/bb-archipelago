from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_NAME = "Bloodborne-native-item-grant-auto-v2.CT"
TABLE = next(path for path in (ROOT / "tables" / TABLE_NAME,
                               ROOT.parent / "tables" / TABLE_NAME) if path.exists())
HELPER = next(path for path in (ROOT / "tools" / "send_native_item_grant.ps1",
                                ROOT.parent / "tools" / "send_native_item_grant.ps1") if path.exists())


class GrantHarnessContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = TABLE.read_text(encoding="utf-8")
        cls.helper = HELPER.read_text(encoding="utf-8")

    def test_wire_and_harness_versions_are_visible_in_state(self):
        self.assertIn("local build=[[bb-0.1.0-r3]]", self.text)
        self.assertIn("local protocol=[[BBGRANT1]]", self.text)
        self.assertIn("local harness=[[bb-native-grant-v3]]", self.text)
        self.assertIn('"build=",build', self.text)
        self.assertIn('"\\nprotocol=",protocol', self.text)
        self.assertIn('"\\nharness=",harness', self.text)
        self.assertIn("$build='bb-0.1.0-r3'", self.helper)
        self.assertIn("$protocol='BBGRANT1'", self.helper)
        self.assertIn("$harness='bb-native-grant-v3'", self.helper)

    def test_unversioned_commands_are_rejected_and_removed(self):
        self.assertIn('if t[1]~=protocol then return nil,"Unsupported grant protocol;', self.text)
        self.assertIn('if not command then state("command_rejected",why); os.remove(commandPath)', self.text)

    def test_native_verify_has_a_terminal_retry_budget(self):
        self.assertIn("local maxVerifyPolls=20", self.text)
        self.assertIn('state("failed",string.format("tag=%s expected_after=', self.text)
        self.assertIn("native_result=%s retry_budget=%d", self.text)
        self.assertIn("active=nil", self.text)

    def test_auto_expected_count_is_persisted_before_the_write(self):
        self.assertIn("autoExpected", self.text)
        self.assertIn('"\\nexpected_before=",tostring(stateExpectedBefore)', self.text)
        self.assertIn('"\\nexpected_after=",tostring(stateExpectedAfter)', self.text)
        self.assertIn('state("executing"', self.text)
        self.assertIn("prior.tag==command.tag", self.text)
        self.assertIn("if actual==wanted then", self.text)
        self.assertIn('state("recovered_complete"', self.text)
        self.assertIn('state("completed",string.format("tag=%s native_result=', self.text)
        self.assertIn('state("completed",string.format("tag=%s direct before=', self.text)
        self.assertIn('prior.status=="completed"', self.text)


if __name__ == "__main__":
    unittest.main()
