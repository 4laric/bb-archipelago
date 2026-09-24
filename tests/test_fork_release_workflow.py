"""Guard the extra launcher asset across the tag-release lifecycle."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


# The Archipelago integration job copies this suite into _ap without .github.
ROOT = next(path for path in Path(__file__).resolve().parents
            if (path / '.github/workflows/release.yaml').is_file())
FORK = "BBLauncher-AP-win-x64.zip"
ORIGINAL = "BloodborneAPLauncher-win-x64.zip"


class ForkReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github/workflows/release.yaml").read_text(
            encoding="utf-8"
        ).replace("\r\n", "\n")

    def step(self, name: str) -> str:
        # A step starts at six-space indentation. Stop at the next step or job
        # so an asset mentioned by a later step cannot satisfy this assertion.
        starts = list(re.finditer(r"^      - name: " + re.escape(name) + r"[ \t]*$",
                                  self.workflow, re.MULTILINE))
        self.assertEqual(1, len(starts), f"release step {name!r}")
        start = starts[0].start()
        end = re.search(r"^      - (?:name|uses):|^  [a-z][\w-]*:",
                        self.workflow[starts[0].end():], re.MULTILINE)
        stop = starts[0].end() + end.start() if end else len(self.workflow)
        return self.workflow[start:stop]

    def test_both_launchers_are_built_from_pinned_sources_and_shared_tools(self):
        self.assertEqual(1, self.workflow.count("repository: 4laric/BB_Launcher-AP"))
        self.assertRegex(self.workflow, r"repository: 4laric/BB_Launcher-AP\n"
                         r"\s+ref: \$\{\{ steps\.bblauncher\.outputs\.ref \}\}")

        build = self.step("Build the launcher package")
        self.assertIn("-NoArchive", build)
        fork = self.step("Package and smoke BBLauncher with the matching release tools")
        self.assertIn("-ToolsDirectory $PWD\\build\\BloodborneAPLauncher\\tools", fork)
        self.assertIn("-ClientRef ${{ steps.client-sha.outputs.sha }}", fork)
        self.assertIn("-ReleaseVersion $env:RELEASE_TAG", fork)

        source = (ROOT / "packaging/build_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn('Join-Path $tools "BBBossEncounterBuilder"', source)
        builder = (ROOT / "packaging/build_fork_bundle.ps1").read_text(encoding="utf-8")
        self.assertIn("Copy-Item -LiteralPath $ToolsDirectory", builder)

    def test_fork_is_signed_finalized_attested_hashed_and_published_with_original(self):
        signing = self.step("Authenticode-sign first-party executables")
        for executable in ("BBLauncher-AP.exe", "ap_backend\\bb-ap-backend.exe",
                           "ap_backend\\tools\\BBBossEncounterBuilder\\BBBossEncounterBuilder.exe"):
            self.assertIn(executable, signing)

        finalize = self.step("Verify signed BBLauncher and create its final archive")
        self.assertIn(FORK, finalize)
        self.assertIn("smoke_fork_bundle.py", finalize)
        attest = self.step("Attest the release artifacts")
        hashed = self.step("Hash the release artifacts")
        publish = self.step("Publish the release with the package zip")
        for asset in (FORK, ORIGINAL, "bloodborne.apworld"):
            self.assertIn(asset, attest)
            self.assertIn(asset, hashed)
            self.assertIn(asset, publish)
        self.assertEqual(1, publish.count("gh release upload"))
        for command in publish.split("gh release create")[1:]:
            self.assertIn(FORK, command)
            self.assertIn(ORIGINAL, command)

    def test_rescan_handles_new_and_historical_releases(self):
        scan = self.step("Scan release artifacts and publish permalinks")
        self.assertIn("if ($assetNames -contains 'BBLauncher-AP-win-x64.zip')", scan)
        self.assertIn("--pattern BBLauncher-AP-win-x64.zip", scan)
        self.assertIn("--pattern BloodborneAPLauncher-win-x64.zip", scan)
        self.assertIn("BBLauncher-AP.exe", scan)
        self.assertIn("ap_backend\\bb-ap-backend.exe", scan)


if __name__ == "__main__":
    unittest.main()
