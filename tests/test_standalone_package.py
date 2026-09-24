from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY_PATH = ROOT / "packaging/standalone_entry.py"
ENTRY_SPEC = importlib.util.spec_from_file_location("standalone_entry", ENTRY_PATH)
if ENTRY_SPEC is None or ENTRY_SPEC.loader is None:
    raise RuntimeError(f"cannot load standalone entry: {ENTRY_PATH}")
standalone_entry = importlib.util.module_from_spec(ENTRY_SPEC)
ENTRY_SPEC.loader.exec_module(standalone_entry)


class StandalonePackageTests(unittest.TestCase):
    def test_build_command_infers_installed_paths_and_bundled_native_writers(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            package = root / "package"
            tools = package / "tools"
            tools.mkdir(parents=True)
            item_writer = tools / "BBStandaloneItemWriter.exe"
            enemy_writer = tools / "BBStandaloneEnemyWriter.exe"
            item_writer.write_bytes(b"item-writer")
            enemy_writer.write_bytes(b"enemy-writer")
            game = root / "CUSA03173" / "dvdroot_ps4"
            output = root / "generated-overlay"
            with patch(
                "tools.build_standalone_randomizer.main", return_value=0
            ) as build_main:
                result = standalone_entry.main(
                    [
                        "build",
                        "--game-root",
                        str(game),
                        "--seed",
                        "package-seed",
                        "--output",
                        str(output),
                        "--randomize-enemies",
                        "--normalize-enemy-scaling",
                    ],
                    package_root=package,
                )
            self.assertEqual(0, result)
            build_main.assert_called_once()
            command = build_main.call_args.args[0]
            values = dict(zip(command[::2], command[1::2]))
            self.assertEqual("package-seed", values["--seed"])
            self.assertEqual(
                str(game / "param/gameparam/gameparam.parambnd.dcx"),
                values["--gameparam"],
            )
            self.assertEqual(
                str(game / "paramdef/paramdef.paramdefbnd.dcx"),
                values["--paramdef"],
            )
            self.assertEqual(str(game / "map/MapStudio"), values["--maps"])
            self.assertEqual(str(game / "script"), values["--enemy-scripts"])
            self.assertEqual(str(item_writer), values["--item-writer"])
            self.assertEqual(str(enemy_writer), values["--enemy-writer"])
            for flag in (
                "--apply",
                "--randomize-enemies",
                "--normalize-enemy-scaling",
            ):
                self.assertIn(flag, command)

    def test_item_only_build_does_not_require_enemy_inputs(self):
        parser = standalone_entry._build_parser()
        arguments = parser.parse_args(
            [
                "--game-root",
                "C:/game/dvdroot_ps4",
                "--seed",
                "items",
                "--output",
                "C:/output",
            ]
        )
        command = standalone_entry.build_arguments(arguments, Path("C:/package"))
        for absent in ("--randomize-enemies", "--maps", "--enemy-scripts", "--enemy-writer"):
            self.assertNotIn(absent, command)

    def test_export_and_verify_delegate_to_the_hardened_exporter(self):
        for command in ("export", "verify"):
            with self.subTest(command=command), patch(
                "tools.export_standalone_mod.main", return_value=17
            ) as export_main:
                arguments = [command, "--sentinel"]
                self.assertEqual(17, standalone_entry.main(arguments))
                export_main.assert_called_once_with(arguments)

    def test_hidden_enemy_planner_dispatch_supports_frozen_self_execution(self):
        with patch("tools.bb_enemizer.cli.main", return_value=9) as planner_main:
            result = standalone_entry.main(
                ["--internal-enemy-planner", "--seed", "internal"]
            )
        self.assertEqual(9, result)
        planner_main.assert_called_once_with(["--seed", "internal"])

    def test_package_script_is_self_contained_pinned_and_network_runtime_free(self):
        script = (ROOT / "packaging/build_standalone.ps1").read_text(encoding="utf-8")
        self.assertIn("7cef52a7366678448d85930eeb8e94093b179d24", script)
        self.assertIn('pythonVersion.Trim() -ne "3.12"', script)
        self.assertIn("--self-contained true", script)
        self.assertIn("-p:PublishSingleFile=true", script)
        self.assertIn('PackageName = "BBStandaloneItemWriter.exe"', script)
        self.assertIn('PackageName = "BBStandaloneEnemyWriter.exe"', script)
        self.assertIn('"--console", "--onedir"', script)
        self.assertIn('"--exclude-module", "BaseClasses"', script)
        self.assertIn('"--exclude-module", "worlds.bloodborne.client"', script)
        self.assertIn('includes_archipelago_runtime = $false', script)
        self.assertIn('includes_player_game_files = $false', script)
        self.assertIn("research\\bb_inputs.db", script)
        self.assertNotIn("build_launcher.ps1", script)
        self.assertNotIn("BBLauncher-AP", script)

    def test_readme_describes_existing_bblauncher_flow_and_safety_boundary(self):
        readme = (ROOT / "packaging/STANDALONE-README.txt").read_text(
            encoding="utf-8"
        )
        for command in (" build `", " export `", " verify `"):
            self.assertIn(command, readme)
        self.assertIn("BBLauncher\\Mods", readme)
        self.assertIn("never activates the package", readme)
        self.assertIn("does not claim that", readme)
        self.assertNotIn("BBLauncher-AP", readme)

    def test_source_entry_help_runs_without_python_site_or_network_runtime(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-S",
                str(ROOT / "packaging/standalone_entry.py"),
                "--help",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("build", completed.stdout)
        self.assertIn("export", completed.stdout)
        self.assertIn("verify", completed.stdout)


if __name__ == "__main__":
    unittest.main()
