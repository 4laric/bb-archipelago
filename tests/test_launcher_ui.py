from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from bb_launcher.core import (
    OWNER_NAME,
    SUPPRESSION_PATH,
    ConflictError,
    ValidationError,
)
from bb_launcher.plan import DEFAULT_SERVER
from bb_launcher.ui import (
    FIELD_DEFINITIONS,
    default_field_values,
    derive_ap_request,
    derive_game_root_for_shad,
    derive_map_studio_for_game_root,
    request_enemy_seed,
    settings_from_fields,
)
from bb_launcher.workflow import (
    EnemizerBuild,
    EnemizerOptions,
    EnemizerToolchain,
    LauncherSettings,
    LauncherWorkflow,
    WorkflowError,
    load_process_plan,
)
from tests.test_launcher_core import make_install


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class Process:
    def __init__(self, pid: int):
        self.pid = pid


class FakeToolchain:
    def __init__(self):
        self.calls: list[dict] = []

    def build(self, **values):
        self.calls.append(values)
        output = values["output_root"] / "MapStudio"
        output.mkdir(parents=True)
        (output / "m24_01_00_00.msb.dcx").write_bytes(b"randomized-map")
        plan = {
            "format": "bb-enemizer-plan-v2",
            "seed": values["seed"],
            "dry_run": True,
            "swaps": [{"logical_key": "one"}, {"logical_key": "two"}],
        }
        return EnemizerBuild(output, plan, digest(json.dumps(plan).encode()))


class LauncherUiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.install = make_install(self.root / "game")
        vanilla = self.install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        vanilla.parent.mkdir(parents=True)
        vanilla.write_bytes(b"vanilla-gameparam")
        self.suppression = self.root / "suppressed.parambnd.dcx"
        self.suppression.write_bytes(b"suppressed-gameparam")
        self.suppression_manifest = self.root / "suppression-build.json"
        self.suppression_manifest.write_text(
            json.dumps(
                {
                    "format": "bb-vanilla-suppression-build-v1",
                    "source_gameparam_sha256": digest(b"vanilla-gameparam"),
                    "plan_sha256": digest(b"plan"),
                    "output_gameparam_sha256": digest(b"suppressed-gameparam"),
                    "output_relative_path": "param/gameparam/gameparam.parambnd.dcx",
                    "installed": False,
                }
            ),
            encoding="utf-8",
        )
        self.maps = self.root / "source-MapStudio"
        self.maps.mkdir()
        (self.maps / "m24_01_00_00.msb.dcx").write_bytes(b"source-map")
        self.inventory = self.root / "msb_enemies.tsv"
        self.inventory.write_text("map_path\tmap_name\n", encoding="utf-8")
        self.souls = self.root / "SoulsFormatsNEXT"
        self.souls.mkdir()
        self.request = self.root / "slot.bbenemizer.json"
        self.request.write_text(
            json.dumps(
                {
                    "format": "bb-enemizer-request-v1",
                    "player": 1,
                    "player_name": "Hunter",
                    "world_version": "0.1.0",
                    "runtime_build": "bb-runtime-r1",
                    "enemizer": True,
                    "enemizer_seed": "seed-name:1",
                    "suppression": {"plan_sha256": digest(b"plan")},
                }
            ),
            encoding="utf-8",
        )
        self.shad = self.root / "shadPS4.exe"
        self.client = self.root / "bb-ap-client.exe"
        self.shad.write_bytes(b"shad")
        self.client.write_bytes(b"client")
        self.process_plan = self.root / "process-plan.json"
        self.process_plan.write_text(
            json.dumps(
                {
                    "format": "bb-launcher-process-plan-v1",
                    "shad_build": "0.18.0",
                    "runtime_build": "bb-runtime-r1",
                    "processes": [
                        {
                            "name": "shadPS4",
                            "executable": self.shad.name,
                            "sha256": digest(b"shad"),
                            "arguments": ["--game", "CUSA03173"],
                        },
                        {
                            "name": "AP client",
                            "executable": self.client.name,
                            "sha256": digest(b"client"),
                            "arguments": [],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def settings(self, *, enemy_inputs: bool = True) -> LauncherSettings:
        return LauncherSettings(
            game_root=self.install.root,
            cache_root=self.root / "cache",
            ap_request=self.request,
            suppression_binder=self.suppression,
            suppression_manifest=self.suppression_manifest,
            process_plan=self.process_plan,
            map_studio_source=self.maps if enemy_inputs else None,
            enemy_inventory=self.inventory if enemy_inputs else None,
            soulsformats_next=self.souls if enemy_inputs else None,
            state_root=self.root / "state",
            shad_log=self.root / "shad_log.txt",
        )

    def test_process_plan_resolves_paths_and_pins_component_hashes(self):
        plan = load_process_plan(self.process_plan)
        self.assertEqual(plan.shad_build, "0.18.0")
        self.assertEqual(plan.runtime_build, "bb-runtime-r1")
        self.assertEqual(plan.processes[0].executable, self.shad.resolve())
        self.assertEqual(plan.processes[0].expected_sha256, digest(b"shad"))

    def test_randomize_enemies_runs_toolchain_caches_maps_activates_and_launches(self):
        toolchain = FakeToolchain()
        launched = []

        def launch(processes):
            launched.extend(processes)
            return [Process(10), Process(11)]

        progress: list[str] = []
        workflow = LauncherWorkflow(self.repo, toolchain=toolchain, process_launcher=launch)
        result = workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(
                enabled=True,
                seed="custom-enemy-seed",
                allow_tier_mixing=True,
                preserve_locomotion=True,
            ),
            progress=progress.append,
            process_is_running=lambda: False,
        )
        self.assertTrue(result.enemizer_enabled)
        self.assertEqual(result.enemizer_swaps, 2)
        self.assertEqual(result.process_ids, (10, 11))
        self.assertEqual(len(toolchain.calls), 1)
        self.assertEqual(toolchain.calls[0]["seed"], "custom-enemy-seed")
        self.assertTrue(toolchain.calls[0]["allow_tier_mixing"])
        self.assertTrue(toolchain.calls[0]["preserve_locomotion"])
        self.assertEqual([spec.name for spec in launched], ["shadPS4", "AP client"])
        active_map = self.install.mods / "dvdroot_ps4" / "map" / "MapStudio" / "m24_01_00_00.msb.dcx"
        self.assertEqual(active_map.read_bytes(), b"randomized-map")
        owner = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertTrue(owner["enemizer"]["enabled"])
        self.assertIn("Planning deterministic enemy swaps", "\n".join(progress))

    def test_verified_enemy_cache_is_reused_without_running_writer_again(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(1), Process(2)],
        )
        first = workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(enabled=True),
            process_is_running=lambda: False,
        )
        second = workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(enabled=True),
            process_is_running=lambda: False,
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(len(toolchain.calls), 1)

    def test_disabling_enemy_randomization_needs_no_enemy_toolchain_inputs(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(3), Process(4)],
        )
        result = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertFalse(result.enemizer_enabled)
        self.assertEqual(result.enemizer_swaps, 0)
        self.assertEqual(len(toolchain.calls), 0)
        map_root = self.install.mods / "dvdroot_ps4" / "map" / "MapStudio"
        self.assertFalse(map_root.exists())

    def test_packaged_toolchain_discovers_installed_maps_and_needs_no_dev_inputs(self):
        installed_maps = self.install.base / "dvdroot_ps4" / "map" / "MapStudio"
        installed_maps.mkdir(parents=True)
        (installed_maps / "m24_01_00_00.msb.dcx").write_bytes(b"installed-source-map")
        toolchain = FakeToolchain()
        toolchain.is_bundled = True
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(5), Process(6)],
        )
        result = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=True),
            process_is_running=lambda: False,
        )
        self.assertTrue(result.enemizer_enabled)
        self.assertEqual(toolchain.calls[0]["map_studio_source"], installed_maps)
        self.assertIsNone(toolchain.calls[0]["inventory"])
        self.assertIsNone(toolchain.calls[0]["soulsformats_next"])

    def test_runtime_mismatch_refuses_before_toolchain_or_activation(self):
        value = json.loads(self.process_plan.read_text(encoding="utf-8"))
        value["runtime_build"] = "wrong-runtime"
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(self.repo, toolchain=toolchain)
        with self.assertRaisesRegex(ValidationError, "seed requires runtime"):
            workflow.randomize_and_launch(
                self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
            )
        self.assertEqual(len(toolchain.calls), 0)
        self.assertFalse(self.install.mods.exists())

    def test_launch_result_reports_whether_a_grants_bridge_was_pinned(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(1), Process(2)],
        )
        result = workflow.randomize_and_launch(
            self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
        )
        self.assertFalse(result.grants_bridge)

        ce = self.root / "cheatengine.exe"
        ce.write_bytes(b"ce")
        table = self.root / "grant.CT"
        table.write_bytes(b"table")
        value = json.loads(self.process_plan.read_text(encoding="utf-8"))
        value["processes"].append(
            {
                "name": "CE bridge",
                "executable": ce.name,
                "sha256": digest(b"ce"),
                "arguments": [table.name],
            }
        )
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(1), Process(2), Process(3)],
        )
        result = workflow.randomize_and_launch(
            self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
        )
        self.assertTrue(result.grants_bridge)

    def _pin_ce_bridge(self) -> None:
        """Add the CE bridge entry the packaged plan carries for item grants."""
        ce = self.root / "cheatengine.exe"
        ce.write_bytes(b"ce")
        table = self.root / "grant.CT"
        table.write_bytes(b"table")
        value = json.loads(self.process_plan.read_text(encoding="utf-8"))
        value["processes"].append(
            {
                "name": "CE bridge",
                "executable": ce.name,
                "sha256": digest(b"ce"),
                "arguments": [table.name],
            }
        )
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")

    def test_a_stray_cheat_engine_refuses_the_launch_with_the_remedy(self):
        # bb-archipelago#137 (Garbo, v0.1.0-playtest.7): with CE already open,
        # Windows hands the grant table to that instance, the bridge never
        # arms, and the session runs with checks reporting and no item ever
        # delivered. The launch must refuse rather than proceed degraded.
        self._pin_ce_bridge()
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: self.fail("a refused launch spawned processes"),
            process_running=lambda name: name == "cheatengine.exe",
        )
        with self.assertRaises(ConflictError) as raised:
            workflow.randomize_and_launch(
                self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
            )
        message = str(raised.exception)
        self.assertIn("Cheat Engine is already running", message)
        self.assertIn("Close Cheat Engine and press Launch again", message)
        self.assertIn("administrator", message)  # the elevation-mismatch note
        self.assertEqual(len(toolchain.calls), 0)
        self.assertFalse(self.install.mods.exists())

    def test_no_stray_cheat_engine_lets_the_bridge_launch(self):
        # The control for the refusal above: same plan, nothing running.
        self._pin_ce_bridge()
        launched: list = []
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda processes: launched.append(list(processes))
            or [Process(1), Process(2), Process(3)],
            process_running=lambda _name: False,
        )
        result = workflow.randomize_and_launch(
            self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
        )
        self.assertTrue(result.grants_bridge)
        self.assertEqual(len(launched), 1)
        self.assertIn("CE bridge", [spec.name for spec in launched[0]])

    def test_a_plan_without_a_bridge_ignores_a_running_cheat_engine(self):
        launched: list = []
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda processes: launched.append(list(processes)) or [Process(1)],
            process_running=lambda _name: True,
        )
        result = workflow.randomize_and_launch(
            self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
        )
        self.assertFalse(result.grants_bridge)
        self.assertEqual(len(launched), 1)

    def test_vanilla_launch_also_refuses_a_stray_cheat_engine(self):
        self._pin_ce_bridge()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda _processes: self.fail("a refused launch spawned processes"),
            process_running=lambda name: name == "cheatengine-x86_64.exe",
        )
        with self.assertRaisesRegex(ConflictError, "cheatengine-x86_64.exe"):
            workflow.launch_vanilla(self.settings(), process_is_running=lambda: False)

    def test_unsuppressed_binder_refuses_before_enemy_generation(self):
        vanilla = self.install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        self.suppression.write_bytes(vanilla.read_bytes())
        manifest = json.loads(self.suppression_manifest.read_text(encoding="utf-8"))
        manifest["output_gameparam_sha256"] = digest(vanilla.read_bytes())
        self.suppression_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        toolchain = FakeToolchain()
        with self.assertRaisesRegex(ValidationError, "byte-identical to vanilla"):
            LauncherWorkflow(self.repo, toolchain=toolchain).randomize_and_launch(
                self.settings(), EnemizerOptions(enabled=True), process_is_running=lambda: False
            )
        self.assertEqual(len(toolchain.calls), 0)

    def test_toolchain_passes_enemy_options_and_requires_compressed_writer_output(self):
        commands: list[list[str]] = []

        def runner(command, _cwd, _progress):
            command = list(command)
            commands.append(command)
            if "tools.bb_enemizer.cli" in command:
                output = Path(command[command.index("--output") + 1])
                output.write_text(
                    json.dumps(
                        {
                            "format": "bb-enemizer-plan-v2",
                            "seed": "enemy-seed",
                            "dry_run": True,
                            "swaps": [{"logical_key": "one"}],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                output = Path(command[-2])
                output.mkdir()
                (output / "m24_01_00_00.msb.dcx").write_bytes(b"map")

        output_root = self.root / "generated"
        result = EnemizerToolchain(self.repo, runner=runner).build(
            seed="enemy-seed",
            inventory=self.inventory,
            map_studio_source=self.maps,
            soulsformats_next=self.souls,
            output_root=output_root,
            allow_tier_mixing=True,
            preserve_locomotion=True,
            progress=lambda _message: None,
        )
        self.assertEqual(len(commands), 2)
        self.assertIn("--allow-tier-mixing", commands[0])
        self.assertIn("--preserve-locomotion", commands[0])
        self.assertEqual(result.map_studio, output_root / "MapStudio")

    def test_toolchain_accepts_precreated_output_root(self):
        # The launch workflow stages enemizer builds in a tempfile.mkdtemp
        # directory, so the toolchain must tolerate output_root existing.
        def runner(command, _cwd, _progress):
            command = list(command)
            if "tools.bb_enemizer.cli" in command:
                output = Path(command[command.index("--output") + 1])
                output.write_text(
                    json.dumps(
                        {
                            "format": "bb-enemizer-plan-v2",
                            "seed": "enemy-seed",
                            "dry_run": True,
                            "swaps": [{"logical_key": "one"}],
                        }
                    ),
                    encoding="utf-8",
                )
            else:
                output = Path(command[-2])
                output.mkdir()
                (output / "m24_01_00_00.msb.dcx").write_bytes(b"map")

        output_root = Path(tempfile.mkdtemp(prefix=".enemizer-build-", dir=self.root))
        result = EnemizerToolchain(self.repo, runner=runner).build(
            seed="enemy-seed",
            inventory=self.inventory,
            map_studio_source=self.maps,
            soulsformats_next=self.souls,
            output_root=output_root,
            allow_tier_mixing=False,
            preserve_locomotion=False,
            progress=lambda _message: None,
        )
        self.assertEqual(result.map_studio, output_root / "MapStudio")

    def test_toolchain_refuses_zero_safe_swaps_before_writer(self):
        calls = 0

        def runner(command, _cwd, _progress):
            nonlocal calls
            calls += 1
            output = Path(command[command.index("--output") + 1])
            output.write_text(
                json.dumps(
                    {"format": "bb-enemizer-plan-v2", "seed": "seed", "dry_run": True, "swaps": []}
                ),
                encoding="utf-8",
            )

        with self.assertRaisesRegex(ValidationError, "zero safe swaps"):
            EnemizerToolchain(self.repo, runner=runner).build(
                seed="seed",
                inventory=self.inventory,
                map_studio_source=self.maps,
                soulsformats_next=self.souls,
                output_root=self.root / "zero",
                allow_tier_mixing=False,
                preserve_locomotion=False,
                progress=lambda _message: None,
            )
        self.assertEqual(calls, 1)

    def test_request_seed_and_form_settings_are_ui_independent(self):
        self.assertEqual(request_enemy_seed(self.request), "seed-name:1")
        fields = {name: "" for name, _label, _kind in FIELD_DEFINITIONS}
        fields.update(
            {
                "game_root": str(self.install.root),
                "cache_root": str(self.root / "cache"),
                "ap_request": str(self.request),
                "suppression_binder": str(self.suppression),
                "suppression_manifest": str(self.suppression_manifest),
                "process_plan": str(self.process_plan),
            }
        )
        settings = settings_from_fields(fields)
        self.assertEqual(settings.ap_request, self.request.resolve())
        self.assertIsNone(settings.enemy_inventory)

    def test_ui_contract_exposes_a_real_randomize_enemies_control(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('text="Randomize Enemies"', source)
        self.assertIn('text="Randomize & Launch"', source)
        self.assertIn("tools.bb_enemizer.cli", (self.repo / "bb_launcher" / "workflow.py").read_text())
        self.assertIn("BBEnemizerWriter.csproj", (self.repo / "bb_launcher" / "workflow.py").read_text())

    def test_ui_contract_exposes_a_session_status_panel(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('text="Session status"', source)
        self.assertIn('text="Refresh"', source)
        self.assertIn("gather_readiness", source)
        self.assertIn("result.client_config", source)
        self.assertIn("result.ledger", source)

    def test_ui_contract_wires_the_secondary_actions(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        for label in ("Launch Vanilla", "Restore Previous", "Rebuild Seed", "Open Diagnostics"):
            self.assertIn(f'text="{label}"', source)
        for method in ("launch_vanilla", "restore_previous", "force_rebuild"):
            self.assertIn(method, source)

    def test_ui_contract_can_generate_the_launch_plan(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('text="Generate Launch Plan"', source)
        self.assertIn('"shad_executable"', source)
        self.assertNotIn('"ce_executable"', source)  # bb-archipelago#153
        self.assertIn("ap_server", source)
        self.assertIn("generate_process_plan", source)
        self.assertIn('application_root() / "tools" / "bb-ap-client.exe"', source)

    def test_ui_contract_has_a_bloodborne_theme(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("_apply_theme", source)
        self.assertIn('theme_use("clam")', source)
        self.assertIn('#8f1d24', source)  # blood accent
        self.assertIn('#c2a14d', source)  # lamp-light gold
        self.assertIn('#0d1117', source)  # night background

    def test_default_field_values_fill_only_verified_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "work" / "vanilla-suppression-build"
            build.mkdir(parents=True)
            binder = build / "gameparam.parambnd.dcx"
            manifest = build / "build-manifest.json"
            binder.write_bytes(b"binder")
            manifest.write_bytes(b"{}")

            values = default_field_values(
                state_root=root / "state", package_roots=(root,)
            )
            self.assertEqual(values["cache_root"], str(root / "state" / "seeds"))
            self.assertEqual(values["state_root"], str(root / "state"))
            self.assertEqual(values["process_plan"], str(root / "state" / "process-plan.json"))
            self.assertTrue(values["shad_log"].endswith("shad_log.txt"))
            self.assertEqual(values["suppression_binder"], str(binder))
            self.assertEqual(values["suppression_manifest"], str(manifest))

            empty = root / "elsewhere"
            empty.mkdir()
            values = default_field_values(
                state_root=root / "state", package_roots=(empty,)
            )
            self.assertEqual(values["cache_root"], str(root / "state" / "seeds"))
            self.assertNotIn("suppression_binder", values)
            self.assertNotIn("suppression_manifest", values)

    def test_derive_game_root_from_the_shad_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shad = root / "shadPS4.exe"
            shad.write_bytes(b"shad")
            install = make_install(root / "games" / "bb")
            derived = derive_game_root_for_shad(shad)
            self.assertEqual(derived, install.root)

            empty = root / "empty"
            empty.mkdir()
            self.assertIsNone(derive_game_root_for_shad(empty / "shadPS4.exe"))

    def test_default_field_values_offer_ap_request_only_when_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "Archipelago" / "out" / "seed1"
            out.mkdir(parents=True)
            older = out / "AP_1_P1_First.bbenemizer.json"
            newer = out / "AP_2_P1_Second.bbseed.json"
            older.write_bytes(b"{}")
            newer.write_bytes(b"{}")
            os.utime(older, (1_000_000, 1_000_000))
            os.utime(newer, (2_000_000, 2_000_000))

            values = default_field_values(
                state_root=root / "state", package_roots=(), repo_root=root
            )
            self.assertEqual(values["ap_request"], str(newer))

            values = default_field_values(
                state_root=root / "state", package_roots=(), repo_root=root / "missing"
            )
            self.assertNotIn("ap_request", values)

    def test_default_field_values_prefer_the_players_own_request(self):
        # A multi-Bloodborne multiworld drops one request per Bloodborne
        # player; auto-fill must not grab the other player's file.
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "Archipelago" / "out" / "seed1"
            out.mkdir(parents=True)
            bas = out / "AP_1_P1_Bas.bbenemizer.json"
            oz = out / "AP_1_P2_oz.bbseed.json"
            bas.write_text(
                json.dumps({"format": "bb-enemizer-request-v1", "player_name": "Bas"}),
                encoding="utf-8",
            )
            oz.write_text(
                json.dumps({"format": "bb-seed-request-v1", "player_name": "oz"}),
                encoding="utf-8",
            )
            os.utime(bas, (1_000_000, 1_000_000))
            os.utime(oz, (2_000_000, 2_000_000))  # oz's is newer

            values = default_field_values(
                state_root=root / "state", package_roots=(), repo_root=root,
                player_name="Bas",
            )
            self.assertEqual(values["ap_request"], str(bas))

            # No matching request: fall back to the newest overall.
            values = default_field_values(
                state_root=root / "state", package_roots=(), repo_root=root,
                player_name="nobody",
            )
            self.assertEqual(values["ap_request"], str(oz))

    def test_derive_map_studio_prefers_the_patch_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = make_install(root / "game")
            relative = Path("dvdroot_ps4", "map", "MapStudio")
            base_maps = install.base / relative
            patch_maps = install.patch / relative
            base_maps.mkdir(parents=True)
            self.assertEqual(derive_map_studio_for_game_root(install.root), base_maps)
            patch_maps.mkdir(parents=True)
            self.assertEqual(derive_map_studio_for_game_root(install.root), patch_maps)
        self.assertIsNone(derive_map_studio_for_game_root(Path("does-not-exist")))

    def test_default_server_matches_multiserver_default_port(self):
        self.assertEqual(DEFAULT_SERVER, "localhost:38281")

    def test_launch_vanilla_resolves_before_moving_the_overlay(self):
        toolchain = FakeToolchain()
        launched: list[tuple[str, ...]] = []

        def launch(processes):
            launched.extend(tuple(spec.arguments) for spec in processes)
            return [Process(10), Process(11)]

        workflow = LauncherWorkflow(self.repo, toolchain=toolchain, process_launcher=launch)
        workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertTrue(self.install.mods.is_dir())

        # A plan still carrying a client placeholder refuses BEFORE the active
        # overlay is touched.
        value = json.loads(self.process_plan.read_text(encoding="utf-8"))
        value["processes"][1]["arguments"] = ["{runtime_config}", "{ledger}"]
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "vanilla launch"):
            workflow.launch_vanilla(self.settings(), process_is_running=lambda: False)
        self.assertTrue(self.install.mods.is_dir())

        value["processes"][1]["arguments"] = []
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")
        pids = workflow.launch_vanilla(self.settings(), process_is_running=lambda: False)
        self.assertEqual(pids, (10, 11))
        self.assertFalse(self.install.mods.exists())
        self.assertEqual(launched[-2:], [("--game", "CUSA03173"), ()])
        preserved = [
            path for path in self.root.glob("game/.*") if "bb-ap-disabled" in path.name
        ]
        self.assertEqual(len(preserved), 1)

    def test_restore_previous_reactivates_the_prior_seed(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(1), Process(2)],
        )
        first = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        request = json.loads(self.request.read_text(encoding="utf-8"))
        request["seed_name"] = "other-seed"
        self.request.write_text(json.dumps(request), encoding="utf-8")
        second = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertNotEqual(first.cache_key, second.cache_key)
        active = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(active["cache_key"], second.cache_key)

        restored = workflow.restore_previous(
            self.settings(enemy_inputs=False), process_is_running=lambda: False
        )
        self.assertEqual(restored, first.cache_key)
        active = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(active["cache_key"], first.cache_key)

    def test_force_rebuild_evicts_the_cache_and_replans(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=toolchain,
            process_launcher=lambda _processes: [Process(1), Process(2)],
        )
        options = EnemizerOptions(enabled=False)
        first = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False), options, process_is_running=lambda: False
        )
        second = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False), options, process_is_running=lambda: False
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        rebuilt = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            options,
            force_rebuild=True,
            process_is_running=lambda: False,
        )
        self.assertFalse(rebuilt.reused)
        self.assertEqual(rebuilt.cache_key, first.cache_key)


if __name__ == "__main__":
    unittest.main()
