from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import replace
from contextlib import redirect_stderr
from pathlib import Path

from tools.bb_standalone.schema import GAMEPARAM_PATH, PARAMDEF_PATH
from tools.build_standalone_randomizer import (
    BUILD_FORMAT,
    RECEIPT_FORMAT,
    BuildConfig,
    EnemyOptions,
    _parse_args,
    _run,
    build,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ScalingDefaultsTests(unittest.TestCase):
    def test_builder_and_cli_default_scaling_on_with_explicit_off_override(self):
        self.assertTrue(EnemyOptions().normalize_scaling)
        required = [
            "--seed", "sample", "--gameparam", "gameparam.dcx",
            "--paramdef", "paramdef.dcx", "--item-writer", "writer.exe",
            "--output", "overlay", "--apply",
        ]
        self.assertTrue(_parse_args(required).enemy_options.normalize_scaling)
        self.assertFalse(_parse_args(required + [
            "--no-normalize-enemy-scaling",
        ]).enemy_options.normalize_scaling)


class FakeToolchain:
    def __init__(self, fixture: "StandaloneBuildTests") -> None:
        self.fixture = fixture
        self.commands: list[list[str]] = []
        self.fail_on: str | None = None
        self.mutate_source = False
        self.scaled_source_bytes: bytes | None = None
        self.planner_inventory_bytes: bytes | None = None

    def __call__(self, command, **kwargs):
        command = [str(value) for value in command]
        self.commands.append(command)
        if "--standalone-items" in command:
            if self.fail_on == "items":
                raise subprocess.CalledProcessError(1, command)
            index = command.index("--standalone-items")
            plan, source, output = (
                Path(command[index + 1]),
                Path(command[index + 3]),
                Path(command[index + 5]),
            )
            output.write_bytes(b"items:" + source.read_bytes())
            receipt = {
                "format": "bb-standalone-item-receipt-v1",
                "seed": self.fixture.seed,
                "plan_sha256": digest(plan),
                "source_sha256": digest(source),
                "output_sha256": digest(output),
                "locations": 1,
                "award_targets": 1,
                "runtime_validated": False,
            }
            if self.mutate_source:
                source.write_bytes(b"mutated original")
            return subprocess.CompletedProcess(command, 0, json.dumps(receipt, indent=2) + "\n", "")
        if "tools.bb_enemizer.cli" in command:
            if self.fail_on == "planner":
                raise subprocess.CalledProcessError(1, command)
            output = Path(command[command.index("--output") + 1])
            self.planner_inventory_bytes = Path(
                command[command.index("--inventory") + 1]
            ).read_bytes()
            seed = command[command.index("--seed") + 1]
            release_files = [
                Path(command[index + 1]).stem.removeprefix("release_")
                for index, argument in enumerate(command[:-1])
                if argument == "--release-file"
            ]
            output.write_text(
                json.dumps(
                    {
                        "format": "bb-enemizer-plan-v2",
                        "seed": seed,
                        "dry_run": True,
                        "options": {"release_tranches": sorted(release_files)},
                        "swaps": [{"logical_key": "m21_00:test"}],
                        "wakeup_fallbacks": ([{
                            "logical_key": "m24_01_00_00:c1120_0009",
                            "entity_id": 2410148, "map": "m24_01_00_00",
                            "event_id": 12415130,
                        }] if "wakeup" in release_files else []),
                        "scaling": {
                            "enabled": "--normalize-scaling" in command,
                            "mechanism": "inferred_static_npc_clone_sp_effect",
                            "change_count": 1,
                            "skip_count": 0,
                            "changes": [{}],
                            "skips": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "planned\n", "")
        if "--wakeup-fallback" in command:
            index = command.index("--wakeup-fallback")
            plan, source, output, report_path = map(Path, command[index + 1:index + 5])
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(b"wakeup:" + source.read_bytes())
            report_path.write_text(json.dumps({
                "format": "bb-enemizer-wakeup-fallback-v1", "applied": True,
                "plan_sha256": digest(plan),
                "source_event_sha256": digest(source),
                "output_event_sha256": digest(output),
                "wakeup_fallbacks": json.loads(plan.read_text())["wakeup_fallbacks"],
            }), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "wakeup\n", "")
        if "--scaled" in command:
            if self.fail_on == "scaled":
                raise subprocess.CalledProcessError(1, command)
            index = command.index("--scaled")
            plan, source, output = (
                Path(command[index + 1]),
                Path(command[index + 2]),
                Path(command[index + 6]),
            )
            self.scaled_source_bytes = source.read_bytes()
            binder = output / GAMEPARAM_PATH
            binder.parent.mkdir(parents=True)
            binder.write_bytes(b"scaled:" + source.read_bytes())
            applied_plan = output / "bb-enemizer-plan.json"
            applied_plan.write_text(json.dumps({"native_scaled": True}), encoding="utf-8")
            maps = output / "dvdroot_ps4/map/MapStudio"
            maps.mkdir(parents=True)
            (maps / "m21_00_00_00.msb.dcx").write_bytes(b"scaled map")
            scripts = output / "dvdroot_ps4/script"
            scripts.mkdir(parents=True)
            (scripts / "m21_00_00_00.luabnd.dcx").write_bytes(b"scaled script")
            (output / "dvdroot_ps4/script.json").write_text(json.dumps({
                "format": "bb-enemizer-ai-v1", "applied": True,
                "plan_sha256": digest(applied_plan), "maps": [{
                    "map": "m21_00_00_00.luabnd.dcx", "missing_goals_after": 0,
                    "output_sha256": digest(scripts / "m21_00_00_00.luabnd.dcx"),
                }],
            }), encoding="utf-8")
            (output / "scaling-report.json").write_text(
                json.dumps(
                    {
                        "format": "bb-enemizer-scaling-v1",
                        "applied": True,
                        "source_plan_sha256": digest(plan),
                        "source_gameparam_sha256": digest(source),
                        "output_gameparam_sha256": digest(binder),
                        "output_plan_sha256": digest(applied_plan),
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "scaled\n", "")
        if "--ai" in command:
            if self.fail_on == "ai":
                raise subprocess.CalledProcessError(1, command)
            index = command.index("--ai")
            plan, binder, output = (
                Path(command[index + 1]),
                Path(command[index + 2]),
                Path(command[index + 5]),
            )
            # The AI pass must inspect the item-modified binder, never vanilla.
            if not binder.read_bytes().startswith(b"items:"):
                raise AssertionError("AI did not receive the composed item binder")
            output.mkdir(parents=True)
            script = output / "m21_00_00_00.luabnd.dcx"
            script.write_bytes(b"ai")
            Path(str(output) + ".json").write_text(
                json.dumps(
                    {
                        "format": "bb-enemizer-ai-v1",
                        "applied": True,
                        "plan_sha256": digest(plan),
                        "maps": [
                            {
                                "map": script.name,
                                "output_sha256": digest(script),
                                "missing_goals_after": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, "ai\n", "")
        if self.fail_on == "maps":
            raise subprocess.CalledProcessError(1, command)
        output = Path(command[-2])
        output.mkdir(parents=True)
        (output / "m21_00_00_00.msb.dcx").write_bytes(b"map")
        return subprocess.CompletedProcess(command, 0, "maps\n", "")


class StandaloneBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        inputs = self.root / "originals"
        inputs.mkdir()
        self.gameparam = inputs / "gameparam.parambnd.dcx"
        self.paramdef = inputs / "paramdef.paramdefbnd.dcx"
        self.gameparam.write_bytes(b"original gameparam")
        self.paramdef.write_bytes(b"original paramdef")
        tools = self.root / "native-tools"
        tools.mkdir()
        self.dotnet = tools / "dotnet.exe"
        self.item_writer = tools / "BBSuppressionWriter.dll"
        self.enemy_writer = tools / "BBEnemizerWriter.dll"
        self.inventory = tools / "inventory.tsv"
        for path, value in (
            (self.dotnet, b"dotnet"),
            (self.item_writer, b"item writer"),
            (self.enemy_writer, b"enemy writer"),
            (self.inventory, b"inventory"),
        ):
            path.write_bytes(value)
        self.maps = inputs / "MapStudio"
        self.scripts = inputs / "script"
        self.maps.mkdir()
        self.scripts.mkdir()
        (self.maps / "m21_00_00_00.msb.dcx").write_bytes(b"original map")
        (self.scripts / "m21_00_00_00.luabnd.dcx").write_bytes(b"original script")
        self.wakeup_event = inputs / "m24_01_00_00.emevd.dcx"
        self.wakeup_event.write_bytes(b"original wakeup")
        self.output = self.root / "result" / "overlay"
        self.seed = "standalone-build-test"
        self.toolchain = FakeToolchain(self)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan(self, seed, sources, options):
        self.assertEqual(self.seed, seed)
        self.assertEqual(digest(self.gameparam), sources[GAMEPARAM_PATH])
        self.assertEqual(digest(self.paramdef), sources[PARAMDEF_PATH])
        return {
            "format": "bb-standalone-item-plan-v1",
            "seed": seed,
            "generator_build": "test-build",
            "options": {},
            "source_hashes": dict(sources),
            "catalog_sha256": "0" * 64,
            "placements": [{}],
            "unsupported": [],
        }

    def config(self, *, enemies=False, scaling=False, expanded=False) -> BuildConfig:
        return BuildConfig(
            seed=self.seed,
            gameparam=self.gameparam,
            paramdef=self.paramdef,
            item_writer=self.item_writer,
            output=self.output,
            dotnet=self.dotnet,
            enemy_options=EnemyOptions(
                enabled=enemies, seed="local-enemies" if enemies else None,
                normalize_scaling=scaling,
                expanded_coverage=expanded,
            ),
            maps=self.maps if enemies else None,
            scripts=self.scripts if enemies else None,
            enemy_writer=self.enemy_writer if enemies else None,
            enemy_inventory=self.inventory,
            wakeup_event=self.wakeup_event if expanded else None,
        )

    def test_item_only_build_has_native_command_identity_and_receipt(self):
        before = self.gameparam.read_bytes(), self.paramdef.read_bytes()
        receipt = build(self.config(), runner=self.toolchain, planner=self.plan)

        command = self.toolchain.commands[0]
        self.assertEqual(
            [str(self.dotnet), "--roll-forward", "Major", str(self.item_writer),
             "--standalone-items"],
            command[:5],
        )
        self.assertEqual("--apply", command[-1])
        self.assertEqual(b"items:original gameparam", (self.output / GAMEPARAM_PATH).read_bytes())
        identity = json.loads((self.output / "standalone-build-identity.json").read_text())
        self.assertEqual(BUILD_FORMAT, identity["format"])
        self.assertEqual(digest(self.gameparam), identity["source_hashes"][GAMEPARAM_PATH])
        self.assertNotIn("server", json.dumps(identity).lower())
        self.assertNotIn("recipient", json.dumps(identity).lower())
        self.assertEqual(RECEIPT_FORMAT, receipt["format"])
        self.assertEqual(before, (self.gameparam.read_bytes(), self.paramdef.read_bytes()))
        recorded = {row["path"]: row["sha256"] for row in receipt["files"]}
        self.assertEqual(
            digest(self.output / GAMEPARAM_PATH), recorded[GAMEPARAM_PATH]
        )
        self.assertFalse(list(self.output.parent.glob(".bb-standalone-*")))

    def test_enemy_maps_and_ai_compose_after_item_writer(self):
        build(self.config(enemies=True), runner=self.toolchain, planner=self.plan)
        planner, maps, ai = self.toolchain.commands[1:]
        self.assertIn("tools.bb_enemizer.cli", planner)
        self.assertIn("--allow-tier-mixing", planner)
        self.assertEqual("local-enemies", planner[planner.index("--seed") + 1])
        self.assertEqual(str(self.maps), maps[-3])
        self.assertIn("--ai", ai)
        ai_index = ai.index("--ai")
        self.assertNotEqual(self.gameparam, Path(ai[ai_index + 2]))
        self.assertTrue((self.output / GAMEPARAM_PATH).read_bytes().startswith(b"items:"))
        self.assertTrue((self.output / "dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx").is_file())
        self.assertTrue((self.output / "dvdroot_ps4/script/m21_00_00_00.luabnd.dcx").is_file())
        self.assertTrue((self.output / "enemy-ai-receipt.json").is_file())
        self.assertFalse((self.output / "dvdroot_ps4/script.json").exists())
        identity = json.loads((self.output / "standalone-build-identity.json").read_text())
        self.assertIn("dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx",
                      identity["source_hashes"])
        self.assertIn("dvdroot_ps4/script/m21_00_00_00.luabnd.dcx",
                      identity["source_hashes"])

    def test_expanded_enemy_release_composes_pinned_wakeup_event(self):
        build(self.config(enemies=True, expanded=True), runner=self.toolchain,
              planner=self.plan)
        planner = next(command for command in self.toolchain.commands
                       if "tools.bb_enemizer.cli" in command)
        release_files = [Path(planner[index + 1]).name
                         for index, argument in enumerate(planner[:-1])
                         if argument == "--release-file"]
        self.assertEqual(
            ["release_contracts.json", "release_spawns.json",
             "release_chara.json", "release_wakeup.json"], release_files)
        self.assertEqual(planner, [flag for flag in planner if not flag.startswith("--boss")])
        self.assertIn("--allow-tier-mixing", planner)
        event = self.output / "dvdroot_ps4/event/m24_01_00_00.emevd.dcx"
        self.assertEqual(b"wakeup:original wakeup", event.read_bytes())
        identity = json.loads((self.output / "standalone-build-identity.json").read_text())
        self.assertTrue(identity["options"]["enemies"]["expanded_coverage"])
        self.assertEqual(digest(self.wakeup_event),
                         identity["source_hashes"]["dvdroot_ps4/event/m24_01_00_00.emevd.dcx"])
        receipt = json.loads((self.output / "standalone-build-receipt.json").read_text())
        self.assertEqual(digest(event), receipt["wakeup_writer"]["output_event_sha256"])

    def test_expanded_enemy_release_requires_enemies_and_event_before_writer(self):
        with self.assertRaisesRegex(ValueError, "requires enemy randomization"):
            build(self.config(expanded=True), runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.toolchain.commands)
        without_mixing = replace(
            self.config(enemies=True),
            enemy_options=EnemyOptions(enabled=True, allow_tier_mixing=False),
        )
        with self.assertRaisesRegex(ValueError, "requires mixed tiers"):
            build(without_mixing, runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.toolchain.commands)
        config = self.config(enemies=True, expanded=True)
        self.wakeup_event.unlink()
        with self.assertRaisesRegex(ValueError, "original wakeup event"):
            build(config, runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.toolchain.commands)

    def test_scaling_starts_from_item_modified_binder(self):
        receipt = build(
            self.config(enemies=True, scaling=True),
            runner=self.toolchain,
            planner=self.plan,
        )
        self.assertTrue((self.output / "enemy-ai-receipt.json").is_file())
        self.assertFalse((self.output / "dvdroot_ps4/script.json").exists())
        scaled = next(command for command in self.toolchain.commands if "--scaled" in command)
        index = scaled.index("--scaled")
        staged_items = Path(scaled[index + 2])
        self.assertNotEqual(self.gameparam, staged_items)
        self.assertEqual(b"items:original gameparam", self.toolchain.scaled_source_bytes)
        self.assertEqual(
            b"scaled:items:original gameparam",
            (self.output / GAMEPARAM_PATH).read_bytes(),
        )
        self.assertEqual(
            digest(self.output / GAMEPARAM_PATH), receipt["composed_gameparam_sha256"]
        )

    def test_default_enemy_inventory_is_materialized_from_pinned_bundle(self):
        config = self.config(enemies=True)
        config = BuildConfig(
            **{**config.__dict__, "enemy_inventory": None}
        )
        build(config, runner=self.toolchain, planner=self.plan)
        self.assertTrue(self.toolchain.planner_inventory_bytes)
        identity = json.loads((self.output / "standalone-build-identity.json").read_text())
        self.assertEqual(
            hashlib.sha256(self.toolchain.planner_inventory_bytes).hexdigest(),
            identity["tool_hashes"]["enemy_inventory"],
        )
        self.assertRegex(identity["tool_hashes"]["enemy_inventory_bundle"], r"^[0-9a-f]{64}$")

    def test_failure_cleans_staging_and_publishes_nothing(self):
        self.toolchain.fail_on = "ai"
        with self.assertRaises(subprocess.CalledProcessError):
            build(self.config(enemies=True), runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.output.parent.glob(".bb-standalone-*")))
        self.assertEqual(b"original gameparam", self.gameparam.read_bytes())

    def test_existing_output_is_rejected_before_any_tool_runs(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, "overwrite"):
            build(self.config(), runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.toolchain.commands, "an existing output must refuse before invoking tools")

    def test_input_mutation_fails_closed_and_cleans_output(self):
        self.toolchain.mutate_source = True
        with self.assertRaisesRegex(ValueError, "receipt|changed"):
            build(self.config(), runner=self.toolchain, planner=self.plan)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.output.parent.glob(".bb-standalone-*")))


class SubprocessOutputTests(unittest.TestCase):
    def test_child_progress_goes_to_stderr_and_receipt_remains_captured(self):
        command = [sys.executable, "-c", "print('native progress')"]
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as log:
            with redirect_stderr(log):
                uncaptured = _run(command, subprocess.run)
            log.seek(0)
            self.assertIn("native progress", log.read())
        self.assertIsNone(uncaptured.stdout)
        captured = _run(command, subprocess.run, capture=True)
        self.assertEqual("native progress\n", captured.stdout)


if __name__ == "__main__":
    unittest.main()
