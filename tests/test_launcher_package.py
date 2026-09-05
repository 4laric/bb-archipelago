from __future__ import annotations

import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from bb_launcher.resources import application_root, resource_root
from bb_launcher.workflow import EnemizerToolchain, ValidationError


def load_version_metadata_module():
    path = Path(__file__).resolve().parents[1] / "packaging" / "version_metadata.py"
    spec = importlib.util.spec_from_file_location("bb_version_metadata", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LauncherPackageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.app = self.root / "app"
        tools = self.app / "tools"
        tools.mkdir(parents=True)
        for name in ("BBEnemizerWriter.exe", "MSBBMiner.exe"):
            (tools / name).write_bytes(b"fake executable")
        planner = tools / "BBEnemizerPlanner"
        planner.mkdir()
        (planner / "BBEnemizerPlanner.exe").write_bytes(b"fake executable")
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

    def test_bundled_event_writer_writes_both_overlays_without_dotnet(self):
        commands: list[list[str]] = []

        def runner(command, _cwd, _progress):
            command = [str(item) for item in command]
            commands.append(command)
            Path(command[command.index("--output") + 1]).write_bytes(b"overlay")
            Path(command[command.index("--manifest") + 1]).write_text("{}", encoding="utf-8")

        (self.app / "tools" / "BBEventWriter.exe").write_bytes(b"fake executable")
        toolchain = EnemizerToolchain(self.repo, app_root=self.app, runner=runner)
        source = self.root / "m24_00_00_00.emevd.dcx"
        source.write_bytes(b"licensed")
        rows = self.root / "rows.json"
        rows.write_text("{}", encoding="utf-8")
        toolchain.write_cathedral_event(
            source=source, output=self.root / "m24.out", manifest=self.root / "m24.json",
            soulsformats_next=None, progress=lambda _message: None,
        )
        toolchain.write_common_event(
            request_path=rows, source=source, output=self.root / "common.out",
            manifest=self.root / "common.json", soulsformats_next=None,
            progress=lambda _message: None,
        )
        self.assertEqual(
            [(Path(command[0]).name, command[1]) for command in commands],
            [("BBEventWriter.exe", "cathedral"), ("BBEventWriter.exe", "common")],
        )
        self.assertIn("--request", commands[1])
        self.assertNotIn("dotnet", " ".join(" ".join(command) for command in commands).lower())

    def test_unbundled_event_writer_needs_soulsformats(self):
        toolchain = EnemizerToolchain(self.repo, app_root=self.app)
        with self.assertRaisesRegex(ValidationError, "SoulsFormatsNEXT is required"):
            toolchain.write_cathedral_event(
                source=self.root / "m24.dcx", output=self.root / "out", manifest=self.root / "m.json",
                soulsformats_next=None, progress=lambda _message: None,
            )

    def test_every_world_resource_file_is_bundled_by_the_launcher_build(self):
        """The apworld opens its tables through importlib.resources; each one
        must exist and the build must bundle the directory, not a hand list."""
        import re
        package = self.repo / "worlds" / "bloodborne"
        referenced = set()
        for source in package.glob("*.py"):
            referenced.update(re.findall(
                r'(?:read_resource_text|joinpath)\("([A-Za-z0-9_]+\.(?:tsv|json))"\)',
                source.read_text(encoding="utf-8"),
            ))
        self.assertIn("attire_additions.tsv", referenced)
        self.assertIn("ids.tsv", referenced)
        for name in sorted(referenced):
            self.assertTrue((package / name).is_file(), name)
        script = (self.repo / "packaging" / "build_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn('Get-ChildItem -LiteralPath (Join-Path $repo "worlds\\bloodborne") -File', script)
        self.assertIn('".tsv", ".json"', script)
        self.assertIn("@worldData", script)

    def test_self_check_passes_on_a_checkout_and_reports_the_world(self):
        from bb_launcher.self_check import run_self_check
        report = self.root / "self-check.json"
        # A checkout has no bundled tools beside it; only the frozen package must.
        self.assertEqual(0, run_self_check(report, require_bundled_tools=False))
        data = json.loads(report.read_text(encoding="utf-8"))
        self.assertTrue(data["ok"], data["problems"])
        self.assertGreater(data["world"]["attire_catalog"], 68)
        self.assertGreater(data["world"]["runtime_items"], 200)
        self.assertEqual(58, data["world"]["category8_awards"])
        self.assertIn("BBEventWriter.exe", data["tools"])

    def test_self_check_fails_when_a_bundled_tool_is_required_and_missing(self):
        from bb_launcher.self_check import run_self_check
        self.assertEqual(1, run_self_check(self.root / "r.json", require_bundled_tools=True))
        data = json.loads((self.root / "r.json").read_text(encoding="utf-8"))
        self.assertTrue(any("bundled tool missing" in problem for problem in data["problems"]))

    def test_release_and_bundle_jobs_run_the_packaging_smoke(self):
        # The Archipelago-tier job copies tests/ into the Archipelago checkout
        # (_ap/, which has its own .github) inside this repository's
        # workspace, so the release configuration is found by walking up.
        workflows = next(
            candidate / ".github" / "workflows"
            for candidate in (self.repo, *self.repo.parents)
            if (candidate / ".github" / "workflows" / "release.yaml").is_file()
        )
        for name in ("release.yaml", "tests.yaml"):
            workflow = (workflows / name).read_text(encoding="utf-8")
            self.assertIn("Start-Process", workflow, name)
            self.assertIn('"--self-check"', workflow, name)
            self.assertIn("-Wait -PassThru", workflow, name)
            self.assertIn("bb-ap-client.exe\" --check-contract", workflow, name)
            self.assertIn("tools/export_runtime_contract.py", workflow, name)

    def test_exported_contract_is_the_widest_pool(self):
        from tools.export_runtime_contract import widest_slot_data
        slot_data = widest_slot_data()
        from worlds.bloodborne import ITEM_ID_BY_KEY, ITEM_NAME_TO_ID
        from worlds.bloodborne.attire import PHANTOM_ATTIRE_ITEM_KEYS
        phantom_ids = {str(ITEM_ID_BY_KEY[key]) for key in PHANTOM_ATTIRE_ITEM_KEYS}
        self.assertEqual(
            set(slot_data["runtime_items"]),
            {str(value) for value in ITEM_NAME_TO_ID.values()} - phantom_ids,
        )
        self.assertIn("sustain_item", slot_data)

    def test_the_client_is_pinned_by_commit_and_both_workflows_build_the_pin(self):
        import re
        pin = (self.repo / "packaging" / "client-ref.txt").read_text(encoding="utf-8").strip()
        self.assertRegex(pin, r"^[0-9a-f]{40}$")
        workflows = next(
            candidate / ".github" / "workflows"
            for candidate in (self.repo, *self.repo.parents)
            if (candidate / ".github" / "workflows" / "release.yaml").is_file()
        )
        for name in ("release.yaml", "tests.yaml"):
            workflow = (workflows / name).read_text(encoding="utf-8")
            self.assertIn("packaging/client-ref.txt", workflow, name)
            self.assertIn("steps.client-pin.outputs.ref", workflow, name)
            self.assertIn("-ClientRef", workflow, name)
            # No workflow may quietly default the client to a moving branch.
            self.assertNotRegex(workflow, r"client_ref \|\| '(main|codex/[^']+)'", name)
        release = (workflows / "release.yaml").read_text(encoding="utf-8")
        self.assertIn("bb-ap-client.exe --version", release)
        script = (self.repo / "packaging" / "build_launcher.ps1").read_text(encoding="utf-8")
        self.assertIn("[string]$ClientRef", script)
        self.assertIn("ref = if ($ClientRef)", script)

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

    def test_release_tag_maps_to_display_and_numeric_windows_versions(self):
        module = load_version_metadata_module()
        version = module.parse_release_version("v0.1.0-beta.1")
        self.assertEqual(version.product_version, "0.1.0-beta.1")
        self.assertEqual(version.file_version, "0.1.0.1")
        self.assertEqual(version.file_version_tuple, (0, 1, 0, 1))
        self.assertTrue(version.prerelease)

    def test_signing_canary_and_stable_tags_are_versioned_deterministically(self):
        module = load_version_metadata_module()
        canary = module.parse_release_version("v0.1.0-signing-canary.2")
        stable = module.parse_release_version("v1.2.3")
        self.assertEqual(canary.file_version, "0.1.0.2")
        self.assertEqual(canary.product_version, "0.1.0-signing-canary.2")
        self.assertEqual(stable.file_version, "1.2.3.0")
        self.assertFalse(stable.prerelease)

    def test_invalid_or_unrepresentable_release_versions_are_rejected(self):
        module = load_version_metadata_module()
        for value in ("beta.1", "v0.1", "v0.1.0-beta", "v65536.0.0"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.parse_release_version(value)

    def test_release_verifies_every_executable_version_before_signing(self):
        candidates = (
            Path.cwd() / ".github" / "workflows" / "release.yaml",
            self.repo / ".github" / "workflows" / "release.yaml",
        )
        workflow_path = next((path for path in candidates if path.is_file()), None)
        if workflow_path is None:
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        verifier = (self.repo / "packaging" / "verify_version_metadata.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("BB_RELEASE_VERSION: ${{ env.RELEASE_TAG }}", workflow)
        self.assertIn("-ReleaseVersion $env:RELEASE_TAG", workflow)
        self.assertIn("releaseRuntimeVersion", verifier)
        self.assertIn("manifest.runtime_version", verifier)
        metadata_gate = workflow.index("- name: Verify Windows version metadata")
        signing = workflow.index("- name: Authenticode-sign first-party executables")
        self.assertLess(metadata_gate, signing)
        for target in (
            "BloodborneAPLauncher.exe",
            "tools\\bb-ap-client.exe",
            "tools\\BBEnemizerPlanner\\BBEnemizerPlanner.exe",
            "tools\\BBEnemizerWriter.exe",
            "tools\\BBSuppressionWriter.exe",
            "tools\\BBToastWriter.exe",
            "tools\\BBEventWriter.exe",
            "tools\\MSBBMiner.exe",
        ):
            self.assertIn(target, verifier)
        for field in (
            "ProductName",
            "FileDescription",
            "CompanyName",
            "ProductVersion",
            "FileVersion",
            "OriginalFilename",
            "LegalCopyright",
        ):
            self.assertIn(field, verifier)

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

    def test_release_signs_and_verifies_the_explicit_catalog_before_archiving(self):
        workflow_path = Path.cwd() / ".github" / "workflows" / "release.yaml"
        if not workflow_path.is_file():
            self.assertEqual(Path.cwd().name, "_ap")
            return
        workflow = workflow_path.read_text(encoding="utf-8")
        self.assertIn("environment: release-signing", workflow)
        self.assertIn("azure/login@8216e11d8cd9b42fe925c852af8e76311ff067ac", workflow)
        self.assertIn(
            "azure/artifact-signing-action@c0ae2c1d0c1847ab81ac0ab8521bee597cfedd30",
            workflow,
        )
        self.assertIn("-NoArchive", workflow)
        for target in (
            "BloodborneAPLauncher.exe",
            "tools\\bb-ap-client.exe",
            "tools\\BBEnemizerPlanner\\BBEnemizerPlanner.exe",
            "tools\\BBSuppressionWriter.exe",
            "tools\\BBEnemizerWriter.exe",
            "tools\\BBToastWriter.exe",
            "tools\\BBEventWriter.exe",
            "tools\\MSBBMiner.exe",
        ):
            self.assertIn(target, workflow)
        signing = workflow.index("- name: Authenticode-sign first-party executables")
        verification = workflow.index("- name: Verify signatures and create the final signed archive")
        archive = workflow.index("Compress-Archive", verification)
        attestation = workflow.index("uses: actions/attest-build-provenance@v2")
        release = workflow.index('gh release create "$env:RELEASE_TAG"')
        self.assertLess(signing, verification)
        self.assertLess(verification, archive)
        self.assertLess(archive, attestation)
        self.assertLess(attestation, release)
        self.assertIn('$signature.Status -ne "Valid"', workflow)
        self.assertIn("TimeStamperCertificate", workflow)

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
            "tools/BBEnemizerPlanner/BBEnemizerPlanner.exe",
            "tools/BBSuppressionWriter.exe",
            "tools/BBEnemizerWriter.exe",
            "tools/BBToastWriter.exe",
            "tools/BBEventWriter.exe",
            "tools/MSBBMiner.exe",
        ):
            self.assertIn(f'Label = "{target}"', scan)
        self.assertIn("VirusTotal scan target is missing", scan)
        self.assertIn("$target.Label", scan)
        self.assertIn("gh release edit", scan)
        self.assertIn("https://www.virustotal.com/gui/file/$sha256", scan)


if __name__ == "__main__":
    unittest.main()
