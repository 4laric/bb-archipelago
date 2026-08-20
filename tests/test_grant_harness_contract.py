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
        self.assertIn("local build=[[bb-0.1.0-r5]]", self.text)
        self.assertIn("local protocol=[[BBGRANT1]]", self.text)
        self.assertIn("local harness=[[bb-native-grant-v5]]", self.text)
        self.assertIn('"build=",build', self.text)
        self.assertIn('"\\nprotocol=",protocol', self.text)
        self.assertIn('"\\nharness=",harness', self.text)
        self.assertIn("$build='bb-0.1.0-r5'", self.helper)
        self.assertIn("$protocol='BBGRANT1'", self.helper)
        self.assertIn("$harness='bb-native-grant-v5'", self.helper)

    def test_table_paths_are_portable_and_setup_failures_are_actionable(self):
        self.assertNotIn(r"C:\Users\alari", self.text)
        self.assertIn('local roamingAppData=os.getenv("APPDATA")', self.text)
        self.assertIn("local root=getTempFolder()", self.text)
        self.assertNotIn("directoryExists", self.text)
        self.assertNotIn("createDirectory", self.text)
        self.assertIn(r'local shadLog=roamingAppData..[[\shadPS4\log\shad_log.txt]]', self.text)
        self.assertIn('showMessage("Bloodborne AP table setup failed:', self.text)
        self.assertIn("local function startBloodborneHarness()", self.text)
        self.assertIn("local started,startError=pcall(startBloodborneHarness)", self.text)
        self.assertIn("tostring(startError)", self.text)

    def test_stale_log_base_falls_back_to_live_signature_resolution(self):
        self.assertIn('AOBScan("44 89 E0 48 83 C4 28 5B 41 5C 41 5D 41 5E 41 5F")', self.text)
        self.assertIn("local candidate=consume-consumeRva", self.text)
        self.assertIn("matchBytes(candidate+heartbeatRva,heartbeatOriginal)", self.text)
        self.assertIn("if #candidates~=1 then", self.text)
        self.assertIn('"Logged eboot base "..logged.." was stale or invalid;', self.text)
        self.assertNotIn('openProcess("shadPS4.exe")', self.text)
        self.assertIn("local attachedPid=getOpenedProcessID()", self.text)
        self.assertIn("local pid=attachedPid", self.text)
        self.assertLess(self.text.index("local attachedPid=getOpenedProcessID()"), self.text.index("local base,baseError=readEbootBase()"))

    def test_bootstrap_is_visible_and_never_inserts_an_absent_vial(self):
        self.assertIn("local bootstrapVialPending=true", self.text)
        self.assertIn("local bootstrapVialNormalized=0xB00003E8", self.text)
        self.assertIn("local bootstrapVialHeldCap=20", self.text)
        self.assertIn("local bootstrapBulletNormalized=0xB0000384", self.text)
        self.assertIn("local function findUniqueItemByLowId(lowId)", self.text)
        self.assertIn("runtimeId%0x10000000==lowId", self.text)
        self.assertIn("if tryBootstrapVial() then return end", self.text)
        self.assertIn('finishBootstrap("bootstrap_complete"', self.text)
        self.assertIn('finishBootstrap("bootstrap_skipped"', self.text)
        self.assertIn('showMessage("Bloodborne AP bootstrap "..outcome', self.text)
        self.assertIn('status=="bootstrap_complete" and "SUCCESS"', self.text)
        self.assertIn('status=="bootstrap_skipped" and "SKIPPED"', self.text)
        self.assertIn("BOOTSTRAP BULLET REFUNDED", self.text)
        self.assertIn("absent Blood Vial insertion is disabled", self.text)
        self.assertNotIn("BOOTSTRAP VIAL QUEUED", self.text)
        self.assertNotIn('os.remove(commandPath)\n        active=nil\n        return\n      end\n      append', self.text)

    def test_intel_sfx_workaround_is_verified_in_live_memory(self):
        self.assertIn("local intelSfxRva=0x28F83E0", self.text)
        self.assertIn("local intelSfxByte=readBytes(base+intelSfxRva,1,true)", self.text)
        self.assertIn("Intel SFX workaround is not active in the attached Bloodborne process", self.text)

    def test_native_descriptor_selects_the_validated_source_by_item_category(self):
        self.assertNotIn("mov dword ptr [rsp+4],0", self.text)
        self.assertIn("mov qword ptr [rsp+8],0", self.text)
        self.assertIn("mov [rsp+10],eax", self.text)
        self.assertIn("mov dword ptr [rsp+14],0", self.text)
        self.assertIn("mov eax,[bbAutoDescriptor+10]", self.text)
        self.assertIn("and eax,F0000000", self.text)
        self.assertIn("cmp eax,80000000", self.text)
        self.assertIn("lea rsi,[bbAutoDescriptor]", self.text)
        self.assertIn("local descriptor=request+0x60", self.text)
        self.assertIn("writeInteger(descriptor+0x10,command.normalized)", self.text)
        self.assertIn('["8050DBE30"]=base+0x50DBE30', self.text)
        self.assertNotIn("sub rsp,20", self.text)
        self.assertNotIn("add rsp,20", self.text)

    def test_unversioned_commands_are_rejected_and_removed(self):
        self.assertIn('if t[1]~=protocol then return nil,"Unsupported grant protocol;', self.text)
        self.assertIn('if not command then state("command_rejected",why); os.remove(commandPath)', self.text)

    def test_native_verify_has_a_terminal_retry_budget(self):
        self.assertIn("local maxVerifyPolls=20", self.text)
        self.assertIn('state("failed",string.format("tag=%s expected_after=', self.text)
        self.assertIn("native_result=%s retry_budget=%d", self.text)

    def test_manual_diagnostic_waits_for_a_real_consumable_trigger(self):
        self.assertIn('trigger~="AUTO" and trigger~="MANUAL"', self.text)
        self.assertIn("cmp dword ptr [bbAutoManualTrigger],0", self.text)
        self.assertIn('command.manualTrigger and "manual_consumable"', self.text)
        self.assertIn("[ValidateSet('AUTO','MANUAL')]", self.helper)
        self.assertIn("local maxManualWaitPolls=1200", self.text)
        self.assertIn("manual trigger timed out after %d polls", self.text)
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
