from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bb_launcher.resources import application_root, resource_root
from bb_launcher.workflow import EnemizerToolchain, ValidationError


class LauncherPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.app = self.root / "app"
        tools = self.app / "tools"
        tools.mkdir(parents=True)
        for name in ("BBEnemizerPlanner.exe", "BBEnemizerWriter.exe", "MSBBMiner.exe"):
            (tools / name).write_bytes(b"fake executable")
        self.maps = self.root / "MapStudio"
        self.maps.mkdir()
        (self.maps / "m24_01_00_00.msb.dcx").write_bytes(b"compressed map")

    def tearDown(self):
        self.temporary.cleanup()

    def test_checkout_resource_roots_are_the_repository(self):
        self.assertEqual(resource_root(), self.repo)
        self.assertEqual(application_root(), self.repo)

    def test_bundled_toolchain_mines_plans_and_writes_without_python_or_dotnet(self):
        commands: list[list[str]] = []

        def runner(command, _cwd, _progress):
            command = [str(item) for item in command]
            commands.append(command)
            executable = Path(command[0]).name
            if executable == "MSBBMiner.exe":
                output = Path(command[2])
                output.mkdir()
                (output / "msb_enemies.tsv").write_text("map_path\tmap_name\n", encoding="utf-8")
            elif executable == "BBEnemizerPlanner.exe":
                output = Path(command[command.index("--output") + 1])
                output.write_text(
                    json.dumps(
                        {
                            "format": "bb-enemizer-plan-v2",
                            "seed": "package-seed",
                            "dry_run": True,
                            "swaps": [{"logical_key": "one"}],
                        }
                    ),
                    encoding="utf-8",
                )
            elif executable == "BBEnemizerWriter.exe":
                output = Path(command[3])
                output.mkdir()
                (output / "m24_01_00_00.msb.dcx").write_bytes(b"randomized")

        toolchain = EnemizerToolchain(self.repo, app_root=self.app, runner=runner)
        self.assertTrue(toolchain.is_bundled)
        result = toolchain.build(
            seed="package-seed",
            inventory=None,
            map_studio_source=self.maps,
            soulsformats_next=None,
            output_root=self.root / "output",
            allow_tier_mixing=False,
            preserve_locomotion=False,
            progress=lambda _message: None,
        )
        self.assertEqual(
            [Path(command[0]).name for command in commands],
            ["MSBBMiner.exe", "BBEnemizerPlanner.exe", "BBEnemizerWriter.exe"],
        )
        self.assertEqual(commands[0][-1], "--fixed-maps-only")
        self.assertEqual(result.map_studio.name, "MapStudio")
        self.assertNotIn("dotnet", " ".join(" ".join(command) for command in commands).lower())
        self.assertNotIn("tools.bb_enemizer.cli", " ".join(" ".join(command) for command in commands))

    def test_partial_package_does_not_claim_to_be_bundled(self):
        (self.app / "tools" / "MSBBMiner.exe").unlink()
        toolchain = EnemizerToolchain(self.repo, app_root=self.app)
        self.assertFalse(toolchain.is_bundled)
        with self.assertRaisesRegex(ValidationError, "enemy inventory is required"):
            toolchain.build(
                seed="seed",
                inventory=None,
                map_studio_source=self.maps,
                soulsformats_next=None,
                output_root=self.root / "partial",
                allow_tier_mixing=False,
                preserve_locomotion=False,
                progress=lambda _message: None,
            )

    def test_package_contract_is_self_contained_and_excludes_game_files(self):
        script = (self.repo / "packaging" / "build_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("--self-contained true", script)
        self.assertIn("-p:PublishSingleFile=true", script)
        self.assertIn('includes_game_files = $false', script)
        self.assertIn("package-manifest.json", script)
        self.assertIn('Join-Path $repo "SECURITY.md"', script)
        self.assertIn('Join-Path $tools "bb-ap-client.exe"', script)
        self.assertIn('path = "tools/bb-ap-client.exe"', script)
        self.assertIn("$clientRecord", script)
        self.assertIn("Cannot rebuild the package while it is running", script)
        self.assertIn("Get-Process", script)
        self.assertIn("catch [UnauthorizedAccessException]", script)
        driver = (self.repo / "build.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$Package", driver)
        self.assertIn("build_vanilla_suppression.ps1", driver)
        self.assertIn("build_launcher.ps1", driver)
        self.assertIn("cargo build --release -p bb-archipelago", driver)
        self.assertIn("[Text.UTF8Encoding]::new($false)", script)
        suppression_builder = (self.repo / "tools" / "build_vanilla_suppression.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[Text.UTF8Encoding]::new($false)", suppression_builder)
        self.assertNotIn(
            "ConvertTo-Json | Set-Content -LiteralPath $Manifest -Encoding utf8",
            suppression_builder,
        )
        miner = (self.repo / "tools" / "msbb_miner" / "Program.cs").read_text(encoding="utf-8")
        self.assertIn('.EndsWith(".msb.dcx"', miner)
        writer = (self.repo / "tools" / "bb_enemizer_writer" / "Program.cs").read_text(
            encoding="utf-8"
        )
        self.assertIn('.EndsWith(".msb", StringComparison.OrdinalIgnoreCase)', writer)
        self.assertIn('bare + ".msb.dcx"', writer)

    def test_release_build_stamps_the_exact_client_checkout(self):
        candidates = (
            Path.cwd() / ".github" / "workflows" / "release.yaml",
            self.repo / ".github" / "workflows" / "release.yaml",
        )
        workflow_path = next((path for path in candidates if path.is_file()), None)
        if workflow_path is None:
            # The AP tier copies tests/ into its _ap checkout but deliberately
            # does not install repository automation. The unit tier runs this
            # same test against the real checkout and owns this static gate.
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("git -C _client rev-parse HEAD", workflow)
        self.assertIn("BB_BUILD_SHA: ${{ steps.client-sha.outputs.sha }}", workflow)
        self.assertLess(
            workflow.index("git -C _client rev-parse HEAD"),
            workflow.index("cargo build --release -p bb-archipelago"),
        )

    def test_release_attests_both_artifacts_before_upload(self):
        candidates = (
            Path.cwd() / ".github" / "workflows" / "release.yaml",
            self.repo / ".github" / "workflows" / "release.yaml",
        )
        workflow_path = next((path for path in candidates if path.is_file()), None)
        if workflow_path is None:
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("uses: actions/attest-build-provenance@v2", workflow)
        self.assertIn("build/BloodborneAPLauncher-win-x64.zip", workflow)
        self.assertIn("build/bloodborne.apworld", workflow)
        self.assertLess(
            workflow.index("uses: actions/attest-build-provenance@v2"),
            workflow.index('gh release create "$env:RELEASE_TAG"'),
        )

    def test_release_notes_hash_both_artifacts_before_release_creation(self):
        candidates = (
            Path.cwd() / ".github" / "workflows" / "release.yaml",
            self.repo / ".github" / "workflows" / "release.yaml",
        )
        workflow_path = next((path for path in candidates if path.is_file()), None)
        if workflow_path is None:
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("Get-FileHash $f -Algorithm SHA256", workflow)
        self.assertIn("$env:GITHUB_REPOSITORY/actions/runs/$env:GITHUB_RUN_ID", workflow)
        self.assertIn('"build\\BloodborneAPLauncher-win-x64.zip"', workflow)
        self.assertIn('"build\\bloodborne.apworld"', workflow)
        self.assertLess(
            workflow.index("- name: Hash the release artifacts"),
            workflow.index("gh release create"),
        )

    def test_release_virustotal_scan_is_bounded_and_non_blocking(self):
        workflow_path = Path.cwd() / ".github" / "workflows" / "release.yaml"
        if not workflow_path.is_file():
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        scan = workflow[workflow.index("  virustotal:") :]
        self.assertIn("needs: package", scan)
        self.assertIn("needs.package.result == 'success'", scan)
        self.assertIn("inputs.scan_only", scan)
        self.assertIn("continue-on-error: true", scan)
        self.assertIn("secrets.VIRUSTOTAL_API_KEY", scan)
        self.assertIn("if: env.VIRUSTOTAL_API_KEY != ''", scan)
        self.assertIn("/api/v3/files/upload_url", scan)
        self.assertIn("/api/v3/files\"", scan)
        self.assertIn("& curl.exe", scan)
        self.assertIn('--form "file=@$($path.FullName)"', scan)
        self.assertNotIn("-Form @{ file = $path }", scan)
        self.assertIn("ConvertFrom-Json", scan)
        self.assertIn("upload returned no analysis id", scan)
        self.assertIn("$attempt -le 12", scan)
        self.assertIn("Start-Sleep -Seconds 15", scan)
        self.assertGreaterEqual(scan.count("Start-Sleep -Seconds 16"), 2)
        self.assertIn("Expand-Archive -LiteralPath $archive", scan)
        for target in (
            "BloodborneAPLauncher.exe",
            "tools/bb-ap-client.exe",
            "tools/BBEnemizerPlanner.exe",
            "tools/BBSuppressionWriter.exe",
            "tools/BBEnemizerWriter.exe",
            "tools/BBToastWriter.exe",
            "tools/MSBBMiner.exe",
        ):
            self.assertIn(f'Label = "{target}"', scan)
        self.assertIn("VirusTotal scan target is missing", scan)
        self.assertIn("$target.Label", scan)
        self.assertIn("gh release edit", scan)
        self.assertIn("https://www.virustotal.com/gui/file/$sha256", scan)


if __name__ == "__main__":
    unittest.main()
