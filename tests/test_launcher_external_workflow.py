from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import shutil
import tempfile
import time
import types
import unittest
from unittest.mock import patch

from bb_launcher.core import SeedIdentity, deactivate_overlay, ValidationError, sha256_file
from bb_launcher.external import BBLauncherBuildPin, export_external_package
from bb_launcher.external_workflow import (LOCAL_CANDIDATE_COMMIT, LOCAL_CANDIDATE_SHA,
    FILETIME_EPOCH, verify_before_boot, connect_external)
from bb_launcher.workflow import LauncherWorkflow
from tests.test_launcher_connect import ConnectToRunningTests


class ExternalWorkflowTests(unittest.TestCase):
    process = ConnectToRunningTests.process
    workflow = ConnectToRunningTests.workflow
    snapshot_overlay = ConnectToRunningTests.snapshot_overlay
    tearDown = ConnectToRunningTests.tearDown
    def setUp(self):
        ConnectToRunningTests.setUp(self)
        deactivate_overlay(self.install, process_is_running=lambda: False)
        self.mods = self.root / "BBLauncher" / "Mods"
        self.mods.mkdir(parents=True)
        self.pin = BBLauncherBuildPin("2026-08-09-f092023", LOCAL_CANDIDATE_COMMIT, LOCAL_CANDIDATE_SHA, True)
        self.exported = export_external_package(self.build, SeedIdentity.from_dict(self.build.manifest["identity"]),
            mods_root=self.mods, state_root=self.root / "state", install=self.install, bblauncher=self.pin,
            client_version="sha256:" + sha256_file(self.root / "bb-ap-client.exe"),
            allow_live_acceptance_candidate=True)
        self.active = self.mods.parent / "Mods-Active (DO NOT DELETE)" / self.exported.receipt.package_name
        self.active.parent.mkdir()
        self.exported.package_path.joinpath("dvdroot_ps4").rename(self.active)
        self.exported.package_path.rmdir()
        shutil.copytree(self.active, self.install.mods / "dvdroot_ps4")
        self.settings = replace(self.fixture.settings(), integration_mode="bblauncher",
            bblauncher_mods=self.mods, bblauncher_executable=self.fixture.shad_exe,
            bblauncher_receipt=self.exported.receipt_path)
        self.running = []
        self.workflow_instance = self.workflow(lambda _: False, lambda: tuple(self.running))
        self.pin_patch = patch("bb_launcher.external_workflow._pin", return_value=self.pin)
        self.pin_patch.start()
        self.addCleanup(self.pin_patch.stop)

    def arm(self):
        return verify_before_boot(self.workflow_instance, self.settings, allow_live_acceptance_candidate=True)

    def boot(self):
        self.running = [replace(self.process(), creation_time=FILETIME_EPOCH + 99999999999999999)]

    def connect(self):
        return connect_external(self.workflow_instance, self.settings, player_name="Hunter", allow_live_acceptance_candidate=True)

    def test_external_starts_only_capable_pinned_client(self):
        self.arm()
        self.boot()
        before = self.snapshot_overlay()
        result = self.connect()
        self.assertEqual([p.name for p in self.launched], ["AP client"])
        self.assertEqual(self.launched[0].arguments.count("--require-external-activation-v1"), 2)
        config = json.loads(result.client_config.read_text())
        self.assertEqual(config["external_activation"]["pid"], 41)
        self.assertEqual(config["external_activation"]["process_creation_time"], self.running[0].creation_time)
        self.assertEqual(Path(config["external_activation"]["invalidation_marker"]),
                         result.client_config.parent / "external-invalidation.json")
        self.assertEqual(Path(config["installed_gameparam"]), self.install.mods / "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx")
        self.assertEqual(before, self.snapshot_overlay())
        self.assertFalse((self.install.mods / ".bb-ap-owner.json").exists())

    def test_external_requires_observation_before_boot(self):
        self.boot()
        with self.assertRaises(ValidationError):
            self.connect()
        self.assertFalse(self.launched)

    def test_external_cannot_verify_while_running(self):
        self.boot()
        with self.assertRaisesRegex(ValidationError, "Stop shadPS4"):
            self.arm()

    def test_external_verify_refuses_receipt_for_another_selected_seed(self):
        request = json.loads(self.fixture.request_path.read_text(encoding="utf-8"))
        request["seed_name"] = "AP_another_seed_with_the_same_cached_bytes"
        self.fixture.request_path.write_text(json.dumps(request), encoding="utf-8")
        with self.assertRaisesRegex(ValidationError, "seed/slot does not match"):
            self.arm()
        self.assertFalse((self.root / "state" / "external-boot-observations").exists())

    def test_external_state_and_cache_cannot_overlap_bblauncher_managed_root(self):
        managed_root = self.mods.parent

        def snapshot():
            return tuple(sorted(
                (path.relative_to(managed_root).as_posix(), "directory" if path.is_dir()
                 else sha256_file(path))
                for path in managed_root.rglob("*")
            ))

        cases = (
            replace(self.settings, state_root=self.active.parent),
            replace(self.settings, state_root=self.active / "state"),
            replace(self.settings, cache_root=self.active.parent),
        )
        for settings in cases:
            with self.subTest(state=settings.state_root, cache=settings.cache_root):
                before = snapshot()
                with self.assertRaisesRegex(ValidationError, "managed Mods/config/backup root"):
                    verify_before_boot(
                        self.workflow_instance, settings, player_name="Hunter",
                        allow_live_acceptance_candidate=True,
                    )
                self.assertEqual(snapshot(), before)

    def test_external_requires_new_process(self):
        self.arm()
        self.running = [replace(self.process(), creation_time=1)]
        with self.assertRaisesRegex(ValidationError, "fresh game boot"):
            self.connect()

    def test_external_changed_file_blocks_before_spawn(self):
        self.arm()
        self.boot()
        (self.install.mods / self.exported.receipt.files[0].path).write_bytes(b"changed")
        with self.assertRaises(ValidationError):
            self.connect()
        self.assertFalse(self.launched)

    def test_external_no_process_waits(self):
        self.arm()
        with self.assertRaisesRegex(ValidationError, "Waiting for game"):
            self.connect()

    def test_external_multiple_processes_rejected(self):
        self.arm()
        self.boot()
        self.running.append(replace(self.running[0], pid=42))
        with self.assertRaisesRegex(ValidationError, "additional"):
            self.connect()

    def test_external_wrong_executable_rejected(self):
        self.arm()
        self.boot()
        self.running[0] = replace(self.running[0], executable=self.root / "different.exe")
        with self.assertRaisesRegex(ValidationError, "differs"):
            self.connect()

    def test_external_missing_privilege_identity_rejected(self):
        self.arm()
        self.running = [self.process()]
        with self.assertRaisesRegex(ValidationError, "privilege"):
            self.connect()

    def test_external_standalone_mutations_refused(self):
        from bb_launcher.workflow import EnemizerOptions
        for action in (lambda: self.workflow_instance.randomize_and_launch(self.settings, EnemizerOptions()),
                       lambda: self.workflow_instance.launch_vanilla(self.settings),
                       lambda: self.workflow_instance.restore_previous(self.settings)):
            with self.assertRaisesRegex(ValidationError, "BBLauncher owns"):
                action()

    def test_compatible_pinned_client_update_does_not_require_reexport(self):
        self.arm()
        self.boot()
        client = self.root / "bb-ap-client.exe"
        client.write_bytes(b"different reviewed client")
        plan = json.loads(self.fixture.plan_path.read_text(encoding="utf-8"))
        plan["processes"][1]["sha256"] = sha256_file(client)
        self.fixture.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        result = self.connect()
        self.assertEqual(result.process_ids, (731,))
        self.assertEqual([process.executable for process in self.launched], [client])

    def test_late_activation_drift_refuses_before_state_writes(self):
        from bb_launcher import external_workflow
        self.arm()
        self.boot()
        before = {
            path.relative_to(self.root / "state").as_posix(): path.read_bytes()
            for path in (self.root / "state").rglob("*") if path.is_file()
        }
        original = external_workflow._verify
        calls = 0

        def drift(*args, **kwargs):
            nonlocal calls
            calls += 1
            install, receipt, verified = original(*args, **kwargs)
            if calls == 2:
                verified = replace(verified, activation_fingerprint="0" * 64)
            return install, receipt, verified

        with patch("bb_launcher.external_workflow._verify", side_effect=drift):
            with self.assertRaisesRegex(ValidationError, "changed during connection"):
                self.connect()
        after = {
            path.relative_to(self.root / "state").as_posix(): path.read_bytes()
            for path in (self.root / "state").rglob("*") if path.is_file()
        }
        self.assertEqual(after, before)
        self.assertFalse(self.launched)

    def test_ui_never_calls_old_session_health_verified_without_this_connection(self):
        from bb_launcher.client_config import session_paths
        from bb_launcher.external_ui import BBLauncherPanel
        result = None
        self.arm()
        self.boot()
        result = self.connect()
        paths = session_paths(
            self.root / "state", seed=self.exported.receipt.identity.seed,
            slot=self.exported.receipt.identity.slot,
        )
        paths.client_health.write_text(json.dumps({
            "format": "bb-client-health-v1", "updated_unix_ms": time.time() * 1000,
            "process_alive": True, "ap_connected": True, "delivery_armed": True,
            "detail": "old healthy session",
        }), encoding="utf-8")
        shown = []
        panel = BBLauncherPanel.__new__(BBLauncherPanel)
        panel.candidate = types.SimpleNamespace(get=lambda: True)
        panel.connected_receipt_id = None
        panel.connected_fingerprint = None
        panel.app = types.SimpleNamespace(
            _state_root=lambda: self.root / "state",
            _set_status_text=shown.append,
            client_health=types.SimpleNamespace(set=lambda _value: None),
        )
        panel.refresh_status(self.settings)
        self.assertIn("Activation unverified", shown[-1])
        runtime = json.loads(result.client_config.read_text(encoding="utf-8"))
        panel.connected_receipt_id = self.exported.receipt.receipt_id
        panel.connected_fingerprint = runtime["external_activation"]["activation_fingerprint"]
        panel.refresh_status(self.settings)
        self.assertIn("Ready:", shown[-1])

    def test_ui_does_not_remember_a_client_that_exited_during_startup(self):
        from bb_launcher.external_ui import BBLauncherPanel
        completed = []
        panel = BBLauncherPanel.__new__(BBLauncherPanel)
        panel.connected_receipt_id = None
        panel.connected_fingerprint = None
        panel.app = types.SimpleNamespace(
            _finished=lambda result, action: completed.append((result, action))
        )
        result = types.SimpleNamespace(early_exit=types.SimpleNamespace())
        panel.finished("connect", result, ("receipt", "fingerprint"))
        self.assertIsNone(panel.connected_receipt_id)
        self.assertIsNone(panel.connected_fingerprint)
        self.assertEqual(completed, [(result, "BBLauncher client connection")])

class PrepareOnlyTests(unittest.TestCase):
    def test_preparation_builds_without_activation_process_or_ledger_writes(self):
        from tests.test_launcher_ui import LauncherUiWorkflowTests, FakeToolchain
        from bb_launcher.workflow import EnemizerOptions
        fixture = LauncherUiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        settings = fixture.settings(enemy_inputs=False)
        settings.state_root.mkdir()
        ledger = settings.state_root / "sessions" / "existing" / "ledger.json"
        ledger.parent.mkdir(parents=True)
        ledger.write_bytes(b"existing durable state")
        def snapshot(root):
            return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        before_game, before_state = snapshot(fixture.install.root), snapshot(settings.state_root)
        workflow = LauncherWorkflow(fixture.repo, toolchain=FakeToolchain(),
                                    process_launcher=lambda _: self.fail("preparation spawned a process"),
                                    process_running=lambda _: self.fail("preparation requires no running process"))
        with patch("bb_launcher.workflow.activate_build", side_effect=AssertionError("activated")):
            result = workflow.prepare_seed(settings, EnemizerOptions(enabled=False))
        self.assertTrue(result.build.path.is_dir())
        self.assertEqual(before_game, snapshot(fixture.install.root))
        self.assertEqual(before_state, snapshot(settings.state_root))

    def test_external_settings_round_trip(self):
        from bb_launcher.workflow import LauncherSettings
        from tests.test_launcher_doctor import DoctorFixture
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DoctorFixture(Path(tmp))
            settings = replace(fixture.settings(), integration_mode="bblauncher", bblauncher_mods=Path(tmp)/"Mods", bblauncher_receipt=Path(tmp)/"receipt.json", bblauncher_executable=Path(tmp)/"BB_Launcher.exe")
            self.assertEqual(settings, LauncherSettings.from_dict(settings.as_dict()))

    def test_standalone_refuses_process_plan_changed_during_preparation(self):
        from tests.test_launcher_ui import LauncherUiWorkflowTests, FakeToolchain
        from bb_launcher.workflow import EnemizerOptions
        fixture = LauncherUiWorkflowTests()
        fixture.setUp()
        self.addCleanup(fixture.tearDown)
        settings = fixture.settings(enemy_inputs=False)
        workflow = LauncherWorkflow(fixture.repo, toolchain=FakeToolchain(),
                                    process_launcher=lambda _: self.fail("launched"))
        original = workflow.prepare_seed

        def changed(*args, **kwargs):
            plan = json.loads(settings.process_plan.read_text(encoding="utf-8"))
            plan["processes"][1]["arguments"] = ["different.example:38281"]
            settings.process_plan.write_text(json.dumps(plan), encoding="utf-8")
            return original(*args, **kwargs)

        with patch.object(workflow, "prepare_seed", side_effect=changed), patch(
                "bb_launcher.workflow.activate_build", side_effect=AssertionError("activated")):
            with self.assertRaisesRegex(ValidationError, "changed during seed preparation"):
                workflow.randomize_and_launch(
                    settings, EnemizerOptions(enabled=False),
                    process_is_running=lambda: False,
                )
