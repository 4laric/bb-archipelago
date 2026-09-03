from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

from bb_launcher.core import (
    CATHEDRAL_EVENT_PATH,
    COMMON_EVENT_PATH,
    OWNER_NAME,
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    SUPPRESSION_PATH,
    ConflictError,
    ValidationError,
)
from bb_launcher.core import EarlyExit
from bb_launcher.plan import DEFAULT_SERVER
from bb_launcher.ui import (
    ENEMY_FIELDS,
    FIELD_DEFINITIONS,
    LauncherApp,
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
        self.starting_calls: list[dict] = []
        self.event_calls: list[tuple[str, dict]] = []

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

    def write_seed_weapons(self, **values):
        self.starting_calls.append(values)
        values["output_binder"].write_bytes(values["input_binder"].read_bytes() + b"-starting")

    event_failure: Exception | None = None

    def write_cathedral_event(self, **values):
        self.event_calls.append(("cathedral", dict(values)))
        if self.event_failure is not None:
            raise self.event_failure
        values["output"].parent.mkdir(parents=True, exist_ok=True)
        values["output"].write_bytes(b"verified-cathedral-overlay")
        values["manifest"].write_text("{}", encoding="utf-8")

    def write_common_event(self, **values):
        record = dict(values)
        record["rows"] = json.loads(values["request_path"].read_text(encoding="utf-8"))
        self.event_calls.append(("common", record))
        if self.event_failure is not None:
            raise self.event_failure
        values["output"].parent.mkdir(parents=True, exist_ok=True)
        values["output"].write_bytes(b"verified-common-overlay")
        values["manifest"].write_text("{}", encoding="utf-8")


class LauncherUiWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repo = Path(__file__).resolve().parents[1]
        self.install = make_install(self.root / "game")
        vanilla = self.install.patch.joinpath(*SUPPRESSION_PATH.split("/"))
        vanilla.parent.mkdir(parents=True)
        vanilla.write_bytes(b"vanilla-gameparam")
        cathedral = self.install.patch.joinpath(*CATHEDRAL_EVENT_PATH.split("/"))
        cathedral.parent.mkdir(parents=True)
        cathedral.write_bytes(b"licensed-cathedral-event")
        common = self.install.patch.joinpath(*COMMON_EVENT_PATH.split("/"))
        common.parent.mkdir(parents=True, exist_ok=True)
        common.write_bytes(b"licensed-common-event")
        paramdef = self.install.patch / "dvdroot_ps4" / "paramdef" / "paramdef.paramdefbnd.dcx"
        paramdef.parent.mkdir(parents=True)
        paramdef.write_bytes(b"paramdef")
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
                            "arguments": ["--game", "{game_path}"],
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

    def test_starting_weapon_request_composes_seed_specific_binder(self):
        payload = json.loads(self.request.read_text(encoding="utf-8"))
        payload.update({
            "randomize_starting_weapons": True,
            "starting_weapons": {
                "right_hand": [9000000, 5100000, 2000000],
                "left_hand": [6000000, 14000000],
            },
        })
        self.request.write_text(json.dumps(payload), encoding="utf-8")
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo, toolchain=toolchain,
            process_launcher=lambda _processes: [Process(10), Process(11)],
        )
        result = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False), EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertEqual(1, len(toolchain.starting_calls))
        active = self.install.mods.joinpath(*SUPPRESSION_PATH.split("/"))
        self.assertEqual(b"suppressed-gameparam-starting", active.read_bytes())
        config = json.loads(result.client_config.read_text(encoding="utf-8"))
        manifest_path = Path(config["suppression_manifest"])
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(digest(active.read_bytes()), manifest["output_gameparam_sha256"])
        self.assertEqual(payload["starting_weapons"], manifest["seed_weapon_edits"]["choices"])

    def test_requirement_removal_composes_without_starting_randomization(self):
        payload = json.loads(self.request.read_text(encoding="utf-8"))
        payload.update({
            "remove_weapon_requirements": True,
            "weapon_requirement_families": [2000000, 2010000],
        })
        self.request.write_text(json.dumps(payload), encoding="utf-8")
        toolchain = FakeToolchain()
        result = LauncherWorkflow(
            self.repo, toolchain=toolchain,
            process_launcher=lambda _processes: [Process(10), Process(11)],
        ).randomize_and_launch(
            self.settings(enemy_inputs=False), EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertEqual(1, len(toolchain.starting_calls))
        config = json.loads(result.client_config.read_text(encoding="utf-8"))
        manifest = json.loads(Path(config["suppression_manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["weapon_requirement_families"],
                         manifest["seed_weapon_edits"]["requirement_families"])

    def test_shop_randomization_composes_without_weapon_edits(self):
        payload = json.loads(self.request.read_text(encoding="utf-8"))
        gates = list(range(12101000, 12101010))
        payload.update({
            "randomize_shops": True,
            "shop_gate_permutation": {
                str(stock): unlock for stock, unlock in zip(gates, reversed(gates))
            },
        })
        self.request.write_text(json.dumps(payload), encoding="utf-8")
        toolchain = FakeToolchain()
        result = LauncherWorkflow(
            self.repo, toolchain=toolchain,
            process_launcher=lambda _processes: [Process(10), Process(11)],
        ).randomize_and_launch(
            self.settings(enemy_inputs=False), EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertEqual(1, len(toolchain.starting_calls))
        manifest = json.loads(Path(json.loads(
            result.client_config.read_text(encoding="utf-8")
        )["suppression_manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(payload["shop_gate_permutation"],
                         manifest["seed_weapon_edits"]["shop_gate_permutation"])

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
        active_event = self.install.mods.joinpath(*CATHEDRAL_EVENT_PATH.split("/"))
        self.assertEqual(b"verified-cathedral-overlay", active_event.read_bytes())
        owner = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(12401898, owner["cathedral_event"]["laurence_witness_flag"])

    def test_event_overlays_are_written_from_the_licensed_sources_without_a_compiler(self):
        toolchain = FakeToolchain()
        workflow = LauncherWorkflow(
            self.repo, toolchain=toolchain,
            process_launcher=lambda _processes: [Process(10), Process(11)],
        )
        workflow.randomize_and_launch(
            replace(self.settings(enemy_inputs=False), darkscript=None),
            EnemizerOptions(enabled=False), process_is_running=lambda: False,
        )
        self.assertEqual(["cathedral", "common"], [kind for kind, _ in toolchain.event_calls])
        cathedral = toolchain.event_calls[0][1]
        self.assertEqual(
            self.install.patch.joinpath(*CATHEDRAL_EVENT_PATH.split("/")), cathedral["source"]
        )
        common = toolchain.event_calls[1][1]
        self.assertEqual(
            self.install.patch.joinpath(*COMMON_EVENT_PATH.split("/")), common["source"]
        )
        rows = common["rows"]["category8_awards"]
        from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
        self.assertEqual(len(CATEGORY8_AWARDS), len(rows))
        self.assertEqual(
            [row.token_goods_id for row in CATEGORY8_AWARDS],
            [row["token_goods_id"] for row in rows],
        )
        self.assertLessEqual({"token_goods_id", "item_lot_id", "ack_flag"}, set(rows[0]))

    def test_cathedral_build_failure_preserves_diagnostics_and_does_not_activate(self):
        toolchain = FakeToolchain()
        toolchain.event_failure = RuntimeError("writer rejected source")
        progress: list[str] = []
        with self.assertRaisesRegex(RuntimeError, "writer rejected source"):
            LauncherWorkflow(
                self.repo, toolchain=toolchain,
                process_launcher=lambda _processes: [],
            ).randomize_and_launch(
                self.settings(enemy_inputs=False), EnemizerOptions(enabled=False),
                progress=progress.append, process_is_running=lambda: False,
            )
        self.assertFalse(self.install.mods.exists())
        self.assertIn("Preserved failed enemizer build diagnostics", "\n".join(progress))

    def _skew_the_installed_gameparam(self) -> None:
        self.install.patch.joinpath(*SUPPRESSION_PATH.split("/")).write_bytes(
            b"an install one re-copy behind"
        )

    def test_binder_skew_refuses_the_whole_launch_without_the_override(self):
        # The control for bb-archipelago#183: no knob, no launch, nothing
        # activated -- exactly today's behavior.
        launched: list = []
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda processes: launched.extend(processes) or [],
        )
        self._skew_the_installed_gameparam()
        with self.assertRaises(ValidationError) as raised:
            workflow.randomize_and_launch(
                self.settings(),
                EnemizerOptions(enabled=True),
                process_is_running=lambda: False,
            )
        self.assertIn("does not match the installed game", str(raised.exception))
        self.assertEqual(
            {"launched": [], "overlay_activated": False},
            {
                "launched": [spec.name for spec in launched],
                "overlay_activated": (self.install.mods / OWNER_NAME).exists(),
            },
        )

    def test_binder_skew_launches_under_the_override_loudly_and_on_the_record(self):
        launched: list = []
        progress: list[str] = []
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda processes: launched.extend(processes)
            or [Process(21), Process(22)],
        )
        self._skew_the_installed_gameparam()
        result = workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(enabled=True),
            allow_suppression_mismatch=True,
            progress=progress.append,
            process_is_running=lambda: False,
        )
        self.assertEqual((21, 22), result.process_ids)
        self.assertEqual(["shadPS4", "AP client"], [spec.name for spec in launched])
        # The loud line rode the same progress sink the launch log tails.
        bypass_lines = [line for line in progress if SUPPRESSION_OVERRIDE_KNOB in line]
        self.assertEqual(1, len(bypass_lines))
        self.assertIn(SUPPRESSION_CHECK_SOURCE, bypass_lines[0])
        self.assertIn("BYPASSED", bypass_lines[0])
        # Recorded, so a bug report filed against this overlay is attributable.
        owner = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        section = owner["suppression_validation"]
        self.assertTrue(section["overridden"])
        self.assertEqual(SUPPRESSION_OVERRIDE_KNOB, section["knob"])
        self.assertEqual([SUPPRESSION_CHECK_SOURCE], section["bypassed"])

    def test_seed_plan_skew_is_bypassable_and_named_in_the_record(self):
        manifest = json.loads(self.suppression_manifest.read_text(encoding="utf-8"))
        manifest["plan_sha256"] = digest(b"a different seed's plan")
        self.suppression_manifest.write_text(json.dumps(manifest), encoding="utf-8")
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda _processes: [Process(31), Process(32)],
        )
        with self.assertRaises(ValidationError):
            workflow.randomize_and_launch(
                self.settings(),
                EnemizerOptions(enabled=True),
                process_is_running=lambda: False,
            )
        workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(enabled=True),
            allow_suppression_mismatch=True,
            process_is_running=lambda: False,
        )
        owner = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(
            [SUPPRESSION_CHECK_PLAN], owner["suppression_validation"]["bypassed"]
        )

    def test_an_ordinary_launch_records_no_override_section_at_all(self):
        # Byte-identical default: the key's absence is what says "validated".
        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda _processes: [Process(41), Process(42)],
        )
        progress: list[str] = []
        workflow.randomize_and_launch(
            self.settings(),
            EnemizerOptions(enabled=True),
            allow_suppression_mismatch=True,
            progress=progress.append,
            process_is_running=lambda: False,
        )
        owner = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(
            {"override_lines": 0, "recorded_section": False, "cache_key": owner["cache_key"]},
            {
                "override_lines": len(
                    [line for line in progress if SUPPRESSION_OVERRIDE_KNOB in line]
                ),
                "recorded_section": "suppression_validation" in owner,
                "cache_key": owner["cache_key"],
            },
        )

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

    def test_the_client_log_sits_beside_the_ledger_and_is_reported(self):
        launched: list = []

        def launch(processes):
            launched.extend(processes)
            return [Process(10), Process(11)]

        workflow = LauncherWorkflow(
            self.repo, toolchain=FakeToolchain(), process_launcher=launch
        )
        result = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        client = [spec for spec in launched if spec.name == "AP client"][0]
        shad = [spec for spec in launched if spec.name == "shadPS4"][0]
        self.assertEqual(client.log_path, result.ledger.parent / "client.log")
        self.assertEqual(result.client_log, client.log_path)
        # Both generated children are captured into the same session folder,
        # so an emulator boot crash carries evidence too (#175).
        self.assertEqual(shad.log_path, result.ledger.parent / "shadps4.log")
        self.assertEqual(result.shad_process_log, shad.log_path)
        self.assertNotEqual(client.log_path, shad.log_path)

    def test_an_early_exit_is_watched_for_and_carried_on_the_result(self):
        early = EarlyExit("AP client", 1, Path("client.log"), "OpenProcess error 5")
        seen: list = []

        def watcher(started, processes, **_kwargs):
            seen.append((tuple(started), tuple(spec.name for spec in processes)))
            return early

        workflow = LauncherWorkflow(
            self.repo,
            toolchain=FakeToolchain(),
            process_launcher=lambda _processes: [Process(1), Process(2)],
            process_watcher=watcher,
        )
        progress: list[str] = []
        result = workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            progress=progress.append,
            process_is_running=lambda: False,
        )
        self.assertIs(result.early_exit, early)
        self.assertEqual(seen[0][1], ("shadPS4", "AP client"))
        self.assertIn("exited immediately", "\n".join(progress))
        self.assertNotIn("Randomized Bloodborne launch started.", progress)

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

    def test_ui_contract_offers_the_override_checkbox_and_never_persists_it(self):
        """bb-archipelago#183: opt-in per session, and impossible to leave on.

        The UI writes every other toggle into the saved setup; this one is
        absent from both the save and the load on purpose, so an operator who
        used it once cannot silently launch a player's seed unvalidated a week
        later.
        """
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("Allow suppression binder mismatch (operators only, not saved)", source)
        self.assertIn("allow_suppression_mismatch=allow_suppression_mismatch", source)
        save = source.split("def _save_settings")[1].split("def _load_settings_if_present")[0]
        load = source.split("def _load_settings_if_present")[1].split("def _generate_plan")[0]
        # The control: the neighbouring toggles ARE persisted, so this is a
        # statement about this knob, not about an inert pair of blocks.
        self.assertIn("allow_tier_mixing", save)
        self.assertIn("allow_tier_mixing", load)
        self.assertNotIn("allow_suppression_mismatch", save)
        self.assertNotIn("allow_suppression_mismatch", load)

    def test_ui_contract_offers_research_captures_and_never_persists_it(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn("Enable research captures (playtest diagnostics, not saved)", source)
        self.assertIn("research_captures=research_captures", source)
        save = source.split("def _save_settings")[1].split("def _load_settings_if_present")[0]
        load = source.split("def _load_settings_if_present")[1].split("def _generate_plan")[0]
        self.assertNotIn("research_captures", save)
        self.assertNotIn("research_captures", load)

    def _build_widget_tree(self):
        """(parent-of-var, widgets-by-parent-var) read out of `_build` itself.

        The defect this guards (bb-archipelago#190) is a parenting question,
        and the suite cannot open a real window: CI is headless Linux. So the
        layout is read structurally out of the AST rather than grepped for a
        string that could survive the widget moving.
        """
        import ast

        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        build = next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "_build"
        )
        parent_of: dict[str, str] = {}
        texts_by_parent: dict[str, set[str]] = {}
        tabs: dict[str, str] = {}
        for node in ast.walk(build):
            if not isinstance(node, ast.Call):
                continue
            # notebook.add(frame, text="...")
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "add"
                and isinstance(node.func.value, ast.Name)
                and node.args
                and isinstance(node.args[0], ast.Name)
            ):
                label = next(
                    (kw.value.value for kw in node.keywords
                     if kw.arg == "text" and isinstance(kw.value, ast.Constant)),
                    None,
                )
                if label is not None:
                    tabs[label] = node.args[0].id
                continue
            if not node.args or not isinstance(node.args[0], ast.Name):
                continue
            parent = node.args[0].id
            for keyword in node.keywords:
                if keyword.arg == "text" and isinstance(keyword.value, ast.Constant):
                    texts_by_parent.setdefault(parent, set()).add(keyword.value.value)
            for statement in ast.walk(build):
                if isinstance(statement, ast.Assign) and statement.value is node:
                    for target in statement.targets:
                        if isinstance(target, ast.Name):
                            parent_of[target.id] = parent
                        elif isinstance(target, ast.Attribute):
                            parent_of[f"self.{target.attr}"] = parent
        return tabs, parent_of, texts_by_parent

    def test_ui_contract_tabs_the_setup_and_the_enemizer(self):
        """The normal flow stays small; advanced controls have their own tab.

        A single tall column let Tk crush the only weighted row to zero on a
        short display, taking the Randomize Enemies toggle with it.
        """
        tabs, parent_of, texts_by_parent = self._build_widget_tree()
        self.assertEqual(set(tabs), {"Setup", "Enemy randomization", "Troubleshooting"})
        enemy_tab = tabs["Enemy randomization"]
        setup_tab = tabs["Setup"]
        troubleshooting_tab = tabs["Troubleshooting"]
        self.assertEqual(parent_of[enemy_tab], "notebook")
        self.assertEqual(parent_of[setup_tab], "notebook")
        self.assertLessEqual(
            {
                "Randomize Enemies",
                "Allow tier mixing (experimental: no scaling)",
                "Preserve locomotion (experimental: incomplete tags)",
                "Enemy seed",
            },
            texts_by_parent[enemy_tab],
        )
        # The operator override is available without cluttering normal setup.
        self.assertIn(
            "Allow suppression binder mismatch (operators only, not saved)",
            texts_by_parent[troubleshooting_tab],
        )
        self.assertNotIn(
            "Allow suppression binder mismatch (operators only, not saved)",
            texts_by_parent[enemy_tab],
        )

    def test_ui_contract_keeps_the_log_and_status_out_of_the_notebook(self):
        """The progress log is launch progress, so no tab can hide it."""
        tabs, parent_of, _texts = self._build_widget_tree()
        tab_frames = set(tabs.values())
        for widget in ("self.log", "self.status_text"):
            frame = parent_of[widget]
            self.assertNotIn(frame, tab_frames, f"{widget} is inside a notebook tab")
            self.assertEqual(parent_of[frame], "outer", f"{widget} is not top-level")
        # The control: the enemizer controls ARE inside a tab, so this is a
        # statement about the log, not about a build with no tabs at all.
        self.assertTrue(tab_frames)

    def _theme_style_calls(self):
        """(configure-kwargs, map-kwargs, laid-out-styles) read out of `_apply_theme`.

        Source-level for the same reason as `_build_widget_tree`: CI is
        headless, so no real Style object can be interrogated. Values are kept
        as AST nodes so a test can tell a THEME_ constant from a literal.
        """
        import ast

        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        theme = next(
            node for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.FunctionDef) and node.name == "_apply_theme"
        )
        configured: dict[str, dict[str, ast.expr]] = {}
        mapped: dict[str, dict[str, ast.expr]] = {}
        laid_out: set[str] = set()
        for node in ast.walk(theme):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            name = node.args[0].value
            kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
            if node.func.attr == "configure":
                configured.setdefault(name, {}).update(kwargs)
            elif node.func.attr == "map":
                mapped.setdefault(name, {}).update(kwargs)
            elif node.func.attr == "layout":
                laid_out.add(name)
        return configured, mapped, laid_out

    def test_ui_contract_themes_the_notebook_with_the_palette_constants(self):
        """bb-archipelago#198: the #191 notebook was never given a theme entry.

        Unthemed, clam draws the selected tab as an empty dashed rectangle and
        the unselected one as a grey ghost on the dark panel. The colours must
        come from the THEME_ constants, not from fresh literals that can drift
        away from the rest of the window.
        """
        import ast

        configured, mapped, laid_out = self._theme_style_calls()
        # The control: the widgets that were always themed are visible here, so
        # a helper that found nothing cannot pass this test.
        self.assertIn("TButton", configured)
        self.assertIn("TButton", mapped)

        self.assertIn("TNotebook", configured)
        self.assertIn("TNotebook.Tab", configured)
        self.assertIn("TNotebook.Tab", mapped)

        tab = configured["TNotebook.Tab"]
        for option in ("background", "foreground", "padding"):
            self.assertIn(option, tab, f"TNotebook.Tab has no {option}")
        for option in ("background", "foreground", "bordercolor", "focuscolor"):
            value = tab[option]
            self.assertIsInstance(
                value, ast.Name, f"TNotebook.Tab {option} is a literal, not a THEME_ constant"
            )
            self.assertTrue(
                value.id.startswith("THEME_"),
                f"TNotebook.Tab {option} uses {value.id}, not a THEME_ constant",
            )
        self.assertIsInstance(
            configured["TNotebook"]["background"], ast.Name
        )
        self.assertTrue(configured["TNotebook"]["background"].id.startswith("THEME_"))

        # The selected/active states are the illegible ones in the screenshot,
        # so both must be remapped for both colours.
        for option in ("background", "foreground"):
            states = mapped["TNotebook.Tab"][option]
            self.assertIsInstance(states, ast.List)
            named = {
                element.elts[0].value
                for element in states.elts
                if isinstance(element, ast.Tuple) and isinstance(element.elts[0], ast.Constant)
            }
            self.assertLessEqual({"selected", "active"}, named, f"{option} misses a state")
        selected_fg = next(
            element.elts[1] for element in mapped["TNotebook.Tab"]["foreground"].elts
            if element.elts[0].value == "selected"
        )
        self.assertIsInstance(selected_fg, ast.Name)
        self.assertTrue(selected_fg.id.startswith("THEME_"))

        # The dashed border is a focus element in clam's stock tab layout; the
        # fix relayouts the tab to drop it.
        self.assertIn("TNotebook.Tab", laid_out)

    def test_ui_contract_gates_the_enemizer_inputs_across_both_tabs(self):
        """The enemizer path fields moved tabs; the disable group must follow."""
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        build = source.split("def _build")[1].split("def _browse")[0]
        self.assertIn("if name in ENEMY_FIELDS", build)
        self.assertEqual(
            ENEMY_FIELDS, {"map_studio_source", "enemy_inventory", "soulsformats_next"}
        )
        self.assertIn("self._enemy_widgets.extend((entry, button))", build)
        self.assertIn("self._enemy_widgets.extend((seed_entry, tier, locomotion))", build)
        toggle = source.split("def _toggle_enemy_fields")[1].split("def _state_root")[0]
        self.assertIn("for widget in self._enemy_widgets", toggle)
        self.assertIn('widget.configure(state=state)', toggle)
        # Neither weighted panel can be starved to nothing again.
        self.assertIn("outer.rowconfigure(2, weight=1, minsize=", build)
        self.assertIn("outer.rowconfigure(3, weight=2, minsize=", build)

    def test_ui_contract_exposes_a_session_status_panel(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('text="Session status"', source)
        self.assertIn('text="Refresh"', source)
        self.assertIn("gather_readiness", source)
        self.assertIn("result.client_config", source)
        self.assertIn("result.ledger", source)
        self.assertIn("self._set_session_details_visible(False)", source)
        self.assertIn('text="Show Details"', source)
        self.assertIn("self._set_session_details_visible(True)", source)

    def test_seed_identity_is_selected_from_the_seed_not_free_typed(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('state="readonly"', source)
        self.assertIn("archive_slots(chosen)", source)
        self.assertIn("self.seed_summary.set", source)
        self.assertIn('bind("<<ComboboxSelected>>"', source)
        self.assertIn('bind("<FocusOut>"', source)

    def test_everyday_launch_controls_disclose_only_when_needed(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertIn('text="Advanced enemy options"', source)
        self.assertIn("self._enemy_advanced_widgets", source)
        self.assertIn("widget.grid_remove()", source)
        self.assertIn("self._show_player_choice(len(names) > 1)", source)
        self.assertIn("self._show_player_choice(False)", source)

    def test_launch_gate_names_missing_setup_instead_of_failing_late(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        gate = source.split("def _refresh_launch_gate")[1].split("def _state_root")[0]
        self.assertIn('("AP seed", self.fields["ap_request"]', gate)
        self.assertIn('("shadPS4", self.fields["shad_executable"]', gate)
        self.assertIn('("game folder", self.fields["game_root"]', gate)
        self.assertIn('missing.append("player")', gate)
        self.assertIn('self.launch_hint.set("Needed: "', gate)
        self.assertIn('self.launch_button.configure(state="disabled")', gate)

    def test_ui_contract_wires_the_secondary_actions(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        for label in (
            "Launch Vanilla", "Undo Last Build", "Rebuild", "Open Logs & Diagnostics",
            "Check Setup",
        ):
            self.assertIn(f'text="{label}"', source)
        for method in ("launch_vanilla", "restore_previous", "force_rebuild"):
            self.assertIn(method, source)

    def test_ui_contract_can_generate_the_launch_plan(self):
        source = (self.repo / "bb_launcher" / "ui.py").read_text(encoding="utf-8")
        self.assertNotIn('text="Generate Launch Plan"', source)
        self.assertIn('"shad_executable"', source)
        self.assertNotIn('"ce_executable"', source)  # bb-archipelago#153
        self.assertIn("ap_server", source)
        self.assertIn("generate_process_plan", source)
        start = source.split("def _start(self)")[1].split("def _confirm_elevation")[0]
        self.assertIn("self._generate_plan()", start)
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

    def test_a_deleted_old_package_repairs_the_suppression_pair_atomically(self):
        from bb_launcher.ui import repair_stale_packaged_suppression_paths

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "current" / "work" / "vanilla-suppression-build"
            current.mkdir(parents=True)
            binder = current / "gameparam.parambnd.dcx"
            manifest = current / "build-manifest.json"
            binder.write_bytes(b"binder")
            manifest.write_text("{}", encoding="utf-8")
            old = root / "deleted-playtest"

            repairs = repair_stale_packaged_suppression_paths(
                {
                    "suppression_binder": str(old / "gameparam.parambnd.dcx"),
                    "suppression_manifest": str(old / "build-manifest.json"),
                },
                {
                    "suppression_binder": str(binder),
                    "suppression_manifest": str(manifest),
                },
            )
            self.assertEqual(
                repairs,
                {"suppression_binder": str(binder), "suppression_manifest": str(manifest)},
            )

    def test_a_valid_operator_suppression_pair_is_preserved(self):
        from bb_launcher.ui import repair_stale_packaged_suppression_paths

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected_binder = root / "selected.parambnd.dcx"
            selected_manifest = root / "selected.json"
            selected_binder.write_bytes(b"selected")
            selected_manifest.write_text("{}", encoding="utf-8")
            self.assertEqual(
                {},
                repair_stale_packaged_suppression_paths(
                    {
                        "suppression_binder": str(selected_binder),
                        "suppression_manifest": str(selected_manifest),
                    },
                    {
                        "suppression_binder": str(root / "bundled.parambnd.dcx"),
                        "suppression_manifest": str(root / "bundled.json"),
                    },
                ),
            )

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
        # bb-archipelago#177: a vanilla launch resolves {game_path} too, so the
        # emulator is handed the real game directory and never has to consult
        # its own (possibly empty) library config.
        self.assertEqual(
            launched[-2:], [("--game", str(self.install.base)), ()]
        )
        preserved = [
            path for path in self.root.glob("game/.*") if "bb-ap-disabled" in path.name
        ]
        self.assertEqual(len(preserved), 1)

    def test_a_stale_bare_id_plan_refuses_before_the_overlay_is_touched(self):
        # bb-archipelago#177: every playtester has a pre-#177 plan on disk, and
        # write_process_plan will not overwrite one without force. A launch
        # that used it would boot shadPS4 into "Game ID or file path not
        # found" -- after a full build. Refuse it at the same point a client
        # placeholder is refused: before anything is mutated.
        launched: list[tuple[str, ...]] = []

        def launch(processes):
            launched.extend(tuple(spec.arguments) for spec in processes)
            return [Process(10), Process(11)]

        workflow = LauncherWorkflow(
            self.repo, toolchain=FakeToolchain(), process_launcher=launch
        )
        # Control: the current plan launches, so the launcher list is witnessed
        # non-empty before the stale plan is asked to add nothing to it.
        workflow.randomize_and_launch(
            self.settings(enemy_inputs=False),
            EnemizerOptions(enabled=False),
            process_is_running=lambda: False,
        )
        self.assertEqual(len(launched), 2)
        self.assertTrue(self.install.mods.is_dir())

        value = json.loads(self.process_plan.read_text(encoding="utf-8"))
        value["processes"][0]["arguments"] = ["CUSA03173"]
        self.process_plan.write_text(json.dumps(value), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "bare game ID"):
            workflow.randomize_and_launch(
                self.settings(enemy_inputs=False),
                EnemizerOptions(enabled=False),
                process_is_running=lambda: False,
            )
        with self.assertRaisesRegex(ValidationError, "regenerate the launch plan"):
            workflow.launch_vanilla(self.settings(), process_is_running=lambda: False)
        # Nothing was spawned, and the active overlay was not moved aside --
        # the refusal costs the player neither a build nor a reinstall.
        self.assertEqual(len(launched), 2)
        self.assertTrue(self.install.mods.is_dir())

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
        self.assertEqual(first.cache_key, second.cache_key)
        active = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(active["cache_key"], second.cache_key)
        self.assertEqual(active["identity"]["seed"], "other-seed")

        restored = workflow.restore_previous(
            self.settings(enemy_inputs=False), process_is_running=lambda: False
        )
        self.assertEqual(restored, first.cache_key)
        active = json.loads((self.install.mods / OWNER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(active["cache_key"], first.cache_key)
        self.assertNotEqual(active["identity"]["seed"], "other-seed")

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


class FakeMessagebox:
    """Records every dialog in call order, so a test can witness which fired."""

    def __init__(self):
        self.calls: list[tuple[str, str, str]] = []

    def showinfo(self, title, message, **_kwargs):
        self.calls.append(("info", title, message))

    def showerror(self, title, message, **_kwargs):
        self.calls.append(("error", title, message))


class FakeRoot:
    def after(self, _delay, callback=None, *args):
        if callback is not None:
            callback(*args)


class FakeApp:
    """The exact surface LauncherApp._finished touches, with no Tk involved."""

    def __init__(self):
        self.messagebox = FakeMessagebox()
        self.root = FakeRoot()
        self.log: list[str] = []
        self.busy: list[bool] = []
        self.refreshed = 0

    _set_busy = lambda self, value: self.busy.append(value)

    def _append_log(self, message):
        self.log.append(message)

    def _refresh_status(self):
        self.refreshed += 1

    def _check_grants_armed(self):
        pass


class Result:
    def __init__(self, **values):
        self.cache_key = "0" * 64
        self.enemizer_enabled = False
        self.client_config = Path("runtime-config.json")
        self.ledger = Path("ledger.json")
        self.client_log = Path("client.log")
        self.shad_process_log = Path("shadps4.log")
        self.early_exit = None
        self.grants_bridge = False
        self.__dict__.update(values)


class LauncherUiEarlyExitTests(unittest.TestCase):
    def test_a_client_early_exit_replaces_the_success_popup_with_its_message(self):
        message = "OpenProcess error 5: run the launcher as administrator"
        log = Path("state") / "sessions" / "abc" / "client.log"
        app = FakeApp()
        LauncherApp._finished(
            app,
            Result(early_exit=EarlyExit("AP client", 1, log, message), client_log=log),
        )
        self.assertEqual([kind for kind, _title, _body in app.messagebox.calls], ["error"])
        _kind, title, body = app.messagebox.calls[0]
        self.assertEqual(title, "AP client stopped")
        self.assertIn(message, body)
        self.assertIn("exit code 1", body)
        self.assertIn(str(log), body)
        self.assertIn(f"Client log: {log}", app.log)

    def test_a_shadps4_early_exit_names_shadps4_in_the_title_and_body(self):
        # bb-archipelago#175: the dialog blamed the AP client whichever child
        # died.  The title and body must name the process that exited.
        message = "Fatal: failed to load mod file at boot"
        log = Path("state") / "sessions" / "abc" / "shadps4.log"
        app = FakeApp()
        LauncherApp._finished(
            app,
            Result(early_exit=EarlyExit("shadPS4", 1, log, message), shad_process_log=log),
        )
        _kind, title, body = app.messagebox.calls[0]
        self.assertEqual(title, "shadPS4 stopped")
        self.assertTrue(body.startswith("shadPS4 exited with exit code 1"))
        self.assertIn(message, body)
        self.assertIn(str(log), body)
        self.assertNotIn("AP client", body)
        self.assertIn(f"shadPS4 log: {log}", app.log)

    def test_a_healthy_launch_still_reports_success_and_names_the_client_log(self):
        app = FakeApp()
        LauncherApp._finished(app, Result())
        self.assertEqual(
            [(kind, title) for kind, title, _body in app.messagebox.calls],
            [("info", "Bloodborne AP started")],
        )
        self.assertIn("Client log: client.log", app.log)
        self.assertIn("shadPS4 log: shadps4.log", app.log)
