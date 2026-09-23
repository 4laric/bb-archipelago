"""Production process wiring stays fixture-only; it never starts the game."""

from __future__ import annotations

import tempfile
import unittest
import sys
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bb_launcher.core import ProcessSpec
from bb_launcher.workflow import ProcessPlan
from bb_launcher.integrated import wiring
from bb_launcher.client_config import _write_runtime_config


class ProductionSpawnTests(unittest.TestCase):
    def test_connect_starts_only_client_and_records_qt_emulator_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client_path = root / "bb-ap-client.exe"
            client_path.write_bytes(b"fixture executable")
            shad_path = root / "shadPS4.exe"
            shad_path.write_bytes(b"fixture emulator")
            manifest = root / "build-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            game = SimpleNamespace(root=root, base=root / "game", mods=root / "game-mods")
            plan = ProcessPlan(
                shad_build="fixture-shad", runtime_build="fixture-runtime",
                processes=(
                    ProcessSpec("shadPS4", shad_path, ("--game", "game")),
                    ProcessSpec("AP client", client_path, ("server:1", "Hunter", "cfg", "ledger")),
                ),
            )
            child = SimpleNamespace(pid=5454)
            verified = SimpleNamespace(
                installed_gameparam=root / "installed-param.dcx",
                activation_fingerprint="fingerprint",
                overlay_root=root / "overlay", active_root=root / "active",
            )
            params = {
                "game_root": str(root), "state_root": str(root / "state"),
                "process_plan": str(root / "plan.json"),
                "seed_path": str(root / "seed.json"), "player_name": "Hunter",
                "suppression_manifest": str(manifest), "password": "secret-password",
                "process_identity": {
                    "pid": 4242, "creation_time": 123456,
                    "executable": str(shad_path), "executable_sha256": "a" * 64,
                },
            }
            with (
                patch.object(wiring.GameInstall, "from_root", return_value=game),
                patch.object(wiring, "_process_plan", return_value=root / "plan.json"),
                patch("bb_launcher.workflow._request_identity", return_value={"request": {}}),
                patch("bb_launcher.workflow._composes_seed_binder", return_value=False),
                patch("bb_launcher.core.SeedCache.verify", return_value=SimpleNamespace(
                    cache_key="cache", manifest={"suppression": {"sha256": "d" * 64}})),
                patch("bb_launcher.external.load_external_receipt", return_value=SimpleNamespace(
                    files=(SimpleNamespace(path="dvdroot_ps4/gameparam.dcx", sha256="b" * 64),))),
                patch("bb_launcher.workflow.load_process_plan", return_value=plan),
                patch("bb_launcher.workflow.resolve_process_plan", side_effect=lambda value, *args, **kwargs: value),
                patch("bb_launcher.core.validate_processes"),
                patch("bb_launcher.core.sha256_file", return_value="b" * 64),
                patch("bb_launcher.workflow.process_creation_time", return_value=654321),
                patch("subprocess.Popen", return_value=child) as popen,
            ):
                spawned = wiring.production_spawn(
                    SimpleNamespace(seed="Seed", slot="Hunter", receipt_id="r",
                                    cache_key="c" * 64, package_name="Archipelago-Hunter-c"),
                    SimpleNamespace(), params, verified,
                )

            self.assertEqual(spawned["pid"], 4242)
            self.assertEqual(spawned["creation_time"], 123456)
            self.assertEqual(spawned["client_pid"], 5454)
            self.assertEqual(
                spawned["client_creation_time"],
                654321 if os.name == "nt" else None,
            )
            self.assertEqual(spawned["executable"], str(shad_path))
            command = popen.call_args.args[0]
            self.assertEqual(command[0], str(client_path))
            self.assertNotIn(str(shad_path), command)
            self.assertNotIn("secret-password", " ".join(command))
            self.assertEqual(popen.call_args.kwargs["env"]["BB_AP_PASSWORD"], "secret-password")
            self.assertEqual(popen.call_args.kwargs["stdout"], sys.stderr)
            import json
            from bb_launcher.client_config import session_paths

            config_path = session_paths(root / "state", seed="Seed", slot="Hunter").config
            runtime = json.loads(config_path.read_text(encoding="utf-8"))
            activation = runtime["external_activation"]
            self.assertEqual(activation["format"], "bb-external-activation-v1")
            self.assertEqual(activation["pid"], 4242)
            self.assertEqual(activation["process_creation_time"], 123456)
            self.assertEqual(activation["package_name"], "Archipelago-Hunter-c")
            self.assertEqual(activation["files"][0]["sha256"], "b" * 64)
            self.assertTrue(activation["invalidation_marker"].endswith(
                "external-invalidation.json"))

    def test_runtime_config_serializes_the_native_external_activation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            contract = {
                "format": "bb-external-activation-v1", "pid": 42,
                "process_creation_time": 1234,
                "executable": {"path": str(root / "shadPS4.exe"), "sha256": "a" * 64},
                "game_path": str(root / "game"), "overlay_root": str(root / "overlay"),
                "active_root": str(root / "active"), "package_name": "Archipelago-Hunter-abc",
                "files": [{"path": "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx",
                           "sha256": "b" * 64}],
                "activation_fingerprint": "c" * 64,
                "invalidation_marker": str(root / "session" / "external-invalidation.json"),
            }
            paths = _write_runtime_config(
                root / "state", seed="Seed", slot="Hunter",
                installed=root / "gameparam.parambnd.dcx", suppression_manifest=None,
                shad_log=None, external_activation=contract,
            )
            import json

            serialized = json.loads(paths.config.read_text(encoding="utf-8"))
            self.assertEqual(serialized["external_activation"], contract)
            self.assertEqual(serialized["external_activation"]["files"][0]["sha256"], "b" * 64)
            self.assertNotIn("receipt_id", serialized["external_activation"])


class ProductionPrepareOptionsTests(unittest.TestCase):
    def test_prepare_forwards_enemy_options_and_reports_cached_build_counts(self) -> None:
        from bb_launcher.workflow import EnemizerOptions

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            seed = root / "seed.json"
            seed.write_text("{}", encoding="utf-8")
            binder = root / "gameparam.parambnd.dcx"
            binder.write_bytes(b"binder")
            manifest = root / "build-manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            plan_path = root / "plan.json"
            client = root / "bb-ap-client.exe"
            client.write_bytes(b"client")
            options_payload = {
                "enabled": True, "seed": "enemy-seed", "allow_tier_mixing": True,
                "preserve_locomotion": True, "normalize_scaling": True,
                "boss_canary": False, "boss_pool": "reviewed",
                "release_contracts": True, "release_spawns": True,
                "release_chara": False,
            }
            built = SimpleNamespace(
                cache_key="c" * 64,
                manifest={"enemizer": {
                    "enabled": True, "seed": "enemy-seed", "file_count": 18,
                    "plan": {"swap_count": 72}, "ai_file_count": 18,
                    "ai": {"status": "verified"},
                }},
            )
            identity = SimpleNamespace(seed="Seed", slot="Hunter")
            prepared = SimpleNamespace(
                build=built, reused=True, identity=identity,
                plan=SimpleNamespace(processes=(ProcessSpec("AP client", client, ()),)),
            )
            captured: dict[str, object] = {}

            class FakeWorkflow:
                def __init__(self, *args, **kwargs):
                    pass

                def prepare_seed(self, settings, options, **kwargs):
                    captured["settings"] = settings
                    captured["options"] = options
                    return prepared

            receipt = SimpleNamespace(
                receipt_id="r" * 64, cache_key=built.cache_key, package_name="Archipelago-Hunter-c",
                identity=identity,
                as_dict=lambda: {"receipt_id": "r" * 64, "package_name": "Archipelago-Hunter-c"},
            )
            params = {
                "game_root": str(root), "state_root": str(root / "state"),
                "mods_root": str(root / "mods"), "seed_path": str(seed),
                "cache_root": str(root / "cache"), "server": "archipelago.gg:1",
                "player_name": "Hunter", "suppression_binder": str(binder),
                "suppression_manifest": str(manifest), "process_plan": str(plan_path),
                "fork_build": {"build": "fixture", "commit": "a" * 40,
                               "executable_sha256": "b" * 64},
                "enemizer": options_payload,
            }
            export_result = SimpleNamespace(receipt=receipt)
            game_install = SimpleNamespace(root=root)
            with (
                patch("bb_launcher.integrated.wiring.GameInstall.from_root", return_value=game_install),
                patch("bb_launcher.integrated.wiring._process_plan", return_value=plan_path),
                patch("bb_launcher.workflow.LauncherWorkflow", FakeWorkflow),
                patch("bb_launcher.workflow.EnemizerToolchain"),
                patch("bb_launcher.integrated.wiring._suppression_file",
                      side_effect=lambda p, s, kind: binder if kind == "binder" else manifest),
                patch("bb_launcher.external.export_external_package", return_value=export_result),
                patch("bb_launcher.core.sha256_file", return_value="d" * 64),
            ):
                result = wiring.production_prepare(params, "op")

            self.assertEqual(captured["options"], EnemizerOptions(**options_payload))
            self.assertEqual(result["launch_config"]["enemizer"], options_payload)
            self.assertEqual(result["enemizer"]["swap_count"], 72)
            self.assertEqual(result["enemizer"]["map_file_count"], 18)
            self.assertEqual(result["enemizer"]["ai_file_count"], 18)
            self.assertTrue(result["enemizer"]["reused"])
            self.assertEqual(result["enemizer"]["ai"], {"status": "verified"})

    def test_workflow_cache_identity_tracks_enemy_seed_and_release_flags(self) -> None:
        import test_launcher_ui as fixtures
        from bb_launcher.workflow import EnemizerOptions, LauncherWorkflow

        fixture = fixtures.LauncherUiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        toolchain = fixtures.FakeToolchain()
        workflow = LauncherWorkflow(fixture.repo, toolchain=toolchain)

        vanilla = workflow.prepare_seed(fixture.settings(), EnemizerOptions(enabled=False))
        randomized = workflow.prepare_seed(
            fixture.settings(), EnemizerOptions(enabled=True, seed="integrated-seed"))
        release = workflow.prepare_seed(
            fixture.settings(), EnemizerOptions(
                enabled=True, seed="integrated-seed", release_contracts=True,
                release_spawns=True, release_chara=True))
        changed_seed = workflow.prepare_seed(
            fixture.settings(), EnemizerOptions(
                enabled=True, seed="different-enemy-seed", release_contracts=True,
                release_spawns=True, release_chara=True))
        repeated = workflow.prepare_seed(
            fixture.settings(), EnemizerOptions(
                enabled=True, seed="different-enemy-seed", release_contracts=True,
                release_spawns=True, release_chara=True))

        self.assertEqual(len({vanilla.build.cache_key, randomized.build.cache_key,
                              release.build.cache_key, changed_seed.build.cache_key}), 4)
        self.assertFalse(vanilla.build.manifest["enemizer"]["enabled"])
        self.assertTrue(randomized.build.manifest["enemizer"]["enabled"])
        self.assertTrue(repeated.reused)
        self.assertEqual(repeated.build.cache_key, changed_seed.build.cache_key)
        self.assertEqual(len(toolchain.calls), 3)

    def test_wakeup_fallback_is_composed_only_for_planned_expanded_release_and_cached(self) -> None:
        import json

        import test_launcher_ui as fixtures
        from bb_launcher.core import BOSS_EVENT_PATH, sha256_file
        from bb_launcher.workflow import EnemizerOptions, LauncherWorkflow

        fixture = fixtures.LauncherUiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        source_event = fixture.install.patch.joinpath(*BOSS_EVENT_PATH.split("/"))
        source_event.parent.mkdir(parents=True, exist_ok=True)
        source_event.write_bytes(b"vanilla-m24-event")

        recipe = json.loads((fixture.repo / "research/enemizer/release_wakeup.json").read_text(
            encoding="utf-8"))
        initializer = recipe["awake_fallback"]["initializers"][0]
        row = {
            "logical_key": initializer["logical_key"],
            "entity_id": initializer["entity_id"],
            "map": "m24_01_00_00",
            "event_id": recipe["awake_fallback"]["event_id"],
        }

        class PlannedWakeupToolchain(fixtures.FakeToolchain):
            def __init__(self):
                super().__init__()
                self.wakeup_calls = 0

            def build(self, **values):
                built = super().build(**values)
                if values.get("release_contracts") or values.get("release_spawns") or values.get("release_chara"):
                    document = json.loads(built.plan_path.read_text(encoding="utf-8"))
                    document["wakeup_fallbacks"] = [row]
                    built.plan_path.write_text(json.dumps(document), encoding="utf-8")
                    built = type(built)(built.map_studio, document, sha256_file(built.plan_path), built.plan_path)
                return built

            def write_wakeup_fallback(self, *, plan_path, source_event, output_event,
                                      report_path, expected_fallbacks, soulsformats_next=None,
                                      progress=lambda _message: None):
                self.wakeup_calls += 1
                output_event.parent.mkdir(parents=True, exist_ok=True)
                output_event.write_bytes(source_event.read_bytes() + b"-awake")
                report = {
                    "format": "bb-enemizer-wakeup-fallback-v1", "applied": True,
                    "plan_sha256": sha256_file(plan_path),
                    "source_event_sha256": sha256_file(source_event),
                    "output_event_sha256": sha256_file(output_event),
                    "wakeup_fallbacks": list(expected_fallbacks),
                }
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report), encoding="utf-8")
                return report

        toolchain = PlannedWakeupToolchain()
        workflow = LauncherWorkflow(fixture.repo, toolchain=toolchain)
        base_options = EnemizerOptions(enabled=True, seed="wakeup-seed")
        unexpanded = workflow.prepare_seed(fixture.settings(), base_options)
        self.assertEqual(toolchain.wakeup_calls, 0)
        self.assertNotIn("wakeup_fallback", unexpanded.build.manifest["enemizer"])

        expanded_options = EnemizerOptions(
            enabled=True, seed="wakeup-seed", release_contracts=True)
        expanded = workflow.prepare_seed(fixture.settings(), expanded_options)
        self.assertEqual(toolchain.wakeup_calls, 1)
        self.assertEqual(expanded.identity.source_hashes[BOSS_EVENT_PATH], sha256_file(source_event))
        self.assertEqual(expanded.identity.options["wakeup_fallback_version"], 1)
        self.assertEqual(expanded.build.manifest["enemizer"]["wakeup_fallback"]["report"][
            "wakeup_fallbacks"], [row])
        event_file = next(record for record in expanded.build.manifest["files"]
                          if record["path"] == BOSS_EVENT_PATH)
        self.assertEqual(event_file["component"], "enemizer-wakeup-fallback")

        again = workflow.prepare_seed(fixture.settings(), expanded_options)
        self.assertTrue(again.reused)
        self.assertEqual(again.build.cache_key, expanded.build.cache_key)
        self.assertEqual(toolchain.wakeup_calls, 1)


if __name__ == "__main__":
    unittest.main()
