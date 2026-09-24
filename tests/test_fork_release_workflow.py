"""Guard the extra launcher asset across the tag-release lifecycle."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


# The Archipelago integration job copies this suite into _ap without .github.
ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / '.github/workflows/release.yaml').is_file())
FORK = "BBLauncher-AP-win-x64.zip"
ORIGINAL = "BloodborneAPLauncher-win-x64.zip"


class ForkReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        workflow = yaml.load(
            (ROOT / ".github/workflows/release.yaml").read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )
        cls.package_steps = workflow["jobs"]["package"]["steps"]
        cls.scan_steps = workflow["jobs"]["virustotal"]["steps"]

    def step(self, name: str, *, scan: bool = False) -> dict:
        steps = self.scan_steps if scan else self.package_steps
        matches = [step for step in steps if step.get("name") == name]
        self.assertEqual(1, len(matches), f"release step {name!r}")
        return matches[0]

    def test_both_launchers_are_built_from_pinned_sources_and_shared_tools(self):
        checkout = [step for step in self.package_steps
                    if step.get("with", {}).get("repository") == "4laric/BB_Launcher-AP"]
        self.assertEqual(1, len(checkout))
        self.assertIn("steps.bblauncher.outputs.ref", checkout[0]["with"]["ref"])

        build = self.step("Build the launcher package")["run"]
        self.assertIn("-NoArchive", build)
        fork = self.step("Package and smoke BBLauncher with the matching release tools")["run"]
        self.assertIn("-ToolsDirectory $PWD\\build\\BloodborneAPLauncher\\tools", fork)
        self.assertIn("-ClientRef ${{ steps.client-sha.outputs.sha }}", fork)
        self.assertIn("-ReleaseVersion $env:RELEASE_TAG", fork)

        source = (ROOT / "packaging/build_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $tools "BBBossEncounterBuilder"', source)
        builder = (ROOT / "packaging/build_fork_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("Copy-Item -LiteralPath $ToolsDirectory", builder)

    def test_fork_is_signed_finalized_attested_hashed_and_published_with_original(self):
        signing = self.step("Authenticode-sign first-party executables")["with"]["files"]
        for executable in ("BBLauncher-AP.exe", "ap_backend\\bb-ap-backend.exe",
                           "ap_backend\\tools\\BBBossEncounterBuilder\\BBBossEncounterBuilder.exe"):
            self.assertIn(executable, signing)

        finalize = self.step("Verify signed BBLauncher and create its final archive")["run"]
        self.assertIn(FORK, finalize)
        self.assertIn("smoke_fork_bundle.py", finalize)
        attest = self.step("Attest the release artifacts")["with"]["subject-path"]
        hashed = self.step("Hash the release artifacts")["run"]
        publish = self.step("Publish the release with the package zip")["run"]
        for asset in (FORK, ORIGINAL, "bloodborne.apworld"):
            self.assertIn(asset, attest)
            self.assertIn(asset, hashed)
            self.assertIn(asset, publish)
        self.assertEqual(1, publish.count("gh release upload"))
        for command in publish.split("gh release create")[1:]:
            self.assertIn(FORK, command)
            self.assertIn(ORIGINAL, command)

    def test_rescan_handles_new_and_historical_releases(self):
        scan = self.step("Scan release artifacts and publish permalinks", scan=True)["run"]
        self.assertIn("if ($assetNames -contains 'BBLauncher-AP-win-x64.zip')", scan)
        self.assertIn("--pattern BBLauncher-AP-win-x64.zip", scan)
        self.assertIn("--pattern BloodborneAPLauncher-win-x64.zip", scan)
        self.assertIn("BBLauncher-AP.exe", scan)
        self.assertIn("ap_backend\\bb-ap-backend.exe", scan)


if __name__ == "__main__":
    unittest.main()
