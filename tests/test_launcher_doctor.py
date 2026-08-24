from __future__ import annotations

import hashlib
import json
import socket
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.cli import main as cli_main
from bb_launcher.client_config import session_paths
from bb_launcher.core import SERIAL, SUPPRESSION_PATH, GameInstall
from bb_launcher.readiness import BRIDGE_STATE_NAME
from bb_launcher.doctor import FAIL, PASS, SKIP, WARN, format_report, run_doctor
from bb_launcher.workflow import PROCESS_PLAN_FORMAT, SETTINGS_FORMAT, LauncherSettings


VANILLA = b"vanilla gameparam payload"
SUPPRESSED = b"suppressed gameparam payload"
PLAN_HASH = hashlib.sha256(b"suppression plan").hexdigest()
RUNTIME = "bb-runtime-r9"


def write_sfo(path: Path, values: dict[str, str]) -> None:
    keys = bytearray()
    data = bytearray()
    entries: list[bytes] = []
    for key, value in values.items():
        key_offset = len(keys)
        keys.extend(key.encode("utf-8") + b"\0")
        encoded = value.encode("utf-8") + b"\0"
        entries.append(
            struct.pack("<HHIII", key_offset, 0x0204, len(encoded), len(encoded), len(data))
        )
        data.extend(encoded)
    key_table = 20 + 16 * len(entries)
    payload = struct.pack("<4s4I", b"\0PSF", 0x00000101, key_table, key_table + len(keys), len(entries))
    payload += b"".join(entries) + bytes(keys) + bytes(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class DoctorFixture:
    """A complete synthetic player chain under one temp directory."""

    def __init__(self, root: Path):
        self.root = root
        base = root / "game" / SERIAL
        patch = root / "game" / f"{SERIAL}-patch"
        write_sfo(base / "sce_sys" / "param.sfo", {"TITLE_ID": SERIAL, "APP_VER": "01.00"})
        write_sfo(patch / "sce_sys" / "param.sfo", {"TITLE_ID": SERIAL, "APP_VER": "01.09"})
        self.gameparam = patch / "dvdroot_ps4" / "param" / "gameparam" / "gameparam.parambnd.dcx"
        self.gameparam.parent.mkdir(parents=True)
        self.gameparam.write_bytes(VANILLA)
        maps = patch / "dvdroot_ps4" / "map" / "MapStudio"
        maps.mkdir(parents=True)
        (maps / "m22_00_00_00.msb.dcx").write_bytes(b"map")

        self.request_path = root / "seed.bbenemizer.json"
        self.request_path.write_text(
            json.dumps(
                {
                    "format": "bb-enemizer-request-v1",
                    "player": 1,
                    "player_name": "Hunter",
                    "seed_name": "AP_test",
                    "runtime_build": RUNTIME,
                    "world_version": "0.1.0",
                    "enemizer_seed": "enemy-seed",
                    "suppression": {"plan_sha256": PLAN_HASH},
                }
            ),
            encoding="utf-8",
        )

        self.binder = root / "binder.parambnd.dcx"
        self.binder.write_bytes(SUPPRESSED)
        self.manifest_path = root / "build-manifest.json"
        self.manifest_path.write_text(
            json.dumps(
                {
                    "format": "bb-vanilla-suppression-build-v1",
                    "installed": False,
                    "source_gameparam_sha256": sha256(VANILLA),
                    "plan_sha256": PLAN_HASH,
                    "output_relative_path": "param/gameparam/gameparam.parambnd.dcx",
                    "output_gameparam_sha256": sha256(SUPPRESSED),
                }
            ),
            encoding="utf-8",
        )

        shad_exe = root / "shadPS4.exe"
        shad_exe.write_bytes(b"shad")
        client_exe = root / "bb-ap-client.exe"
        client_exe.write_bytes(b"client")
        self.plan_path = root / "process-plan.json"
        self.plan_path.write_text(
            json.dumps(
                {
                    "format": PROCESS_PLAN_FORMAT,
                    "shad_build": "0.18.0",
                    "runtime_build": RUNTIME,
                    "processes": [
                        {
                            "name": "shadPS4",
                            "executable": str(shad_exe),
                            "sha256": sha256(b"shad"),
                            "arguments": ["CUSA03173"],
                        },
                        {
                            "name": "AP client",
                            "executable": str(client_exe),
                            "sha256": sha256(b"client"),
                            "arguments": [
                                "localhost:38281",
                                "Hunter",
                                "{runtime_config}",
                                "{ledger}",
                                "--assume-correct-save",
                            ],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        self.settings_path = root / "launcher-settings.json"
        self.settings_path.write_text(
            json.dumps(self.settings_dict()), encoding="utf-8"
        )

    def settings_dict(self) -> dict:
        return {
            "format": SETTINGS_FORMAT,
            "game_root": str(self.root / "game"),
            "cache_root": str(self.root / "cache"),
            "ap_request": str(self.request_path),
            "suppression_binder": str(self.binder),
            "suppression_manifest": str(self.manifest_path),
            "process_plan": str(self.plan_path),
            # Keep session state inside the fixture: the doctor now reads
            # bridge state for its item-grants line.
            "state_root": str(self.root / "state"),
        }

    def settings(self) -> LauncherSettings:
        return LauncherSettings.from_dict(self.settings_dict(), relative_to=self.root)


def finding(report, name: str):
    matches = [item for item in report.findings if item.name == name]
    assert len(matches) == 1, f"expected exactly one {name!r} finding, got {matches}"
    return matches[0]


def no_processes(_name: str) -> bool:
    return False


def probe_ok(_host: str, _port: int) -> None:
    return None


def run(fixture: DoctorFixture, **kwargs):
    options = {"process_running": no_processes, "probe": probe_ok}
    options.update(kwargs)
    return run_doctor(fixture.settings(), **options)


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = DoctorFixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_happy_chain_passes_end_to_end(self):
        report = run(self.fixture)
        self.assertTrue(report.ok, format_report(report))
        self.assertEqual(report.count(FAIL), 0)
        for name in (
            "game installation",
            "AP seed request",
            "launch plan",
            "runtime build agreement",
            "suppression binder and manifest",
            "installed gameparam",
            "MapStudio source",
            "AP server",
            "blocking processes",
        ):
            self.assertEqual(finding(report, name).status, PASS, name)

    def test_slot_agreement_passes_when_names_match(self):
        report = run(self.fixture, player_name="Hunter")
        result = finding(report, "request slot agreement")
        self.assertEqual(result.status, PASS)

    def test_slot_agreement_fails_on_another_players_request(self):
        # Bas pointing at oz's request file: the launcher would connect him
        # as oz and steal oz's checks.
        report = run(self.fixture, player_name="Bas")
        result = finding(report, "request slot agreement")
        self.assertEqual(result.status, FAIL)
        self.assertIn("'Hunter'", result.detail)
        self.assertIn("'Bas'", result.detail)
        self.assertFalse(report.ok)

    def test_slot_agreement_warns_without_a_player_name(self):
        report = run(self.fixture)
        result = finding(report, "request slot agreement")
        self.assertEqual(result.status, WARN)

    def test_slot_agreement_skips_when_the_request_is_broken(self):
        self.fixture.request_path.write_text("not json", encoding="utf-8")
        report = run(self.fixture, player_name="Hunter")
        result = finding(report, "request slot agreement")
        self.assertEqual(result.status, SKIP)

    def test_tampered_patch_layer_that_is_the_suppressed_build_is_named(self):
        # The 2026-08-22 tamper case: a hand-installed suppression output in
        # the patch layer made the source hash mismatch opaque.
        self.fixture.gameparam.write_bytes(SUPPRESSED)
        report = run(self.fixture)
        result = finding(report, "installed gameparam")
        self.assertEqual(result.status, FAIL)
        self.assertIn("already modified", result.detail)
        self.assertIn(str(self.fixture.gameparam), result.detail)
        self.assertIn("restore", result.remedy.lower())

    def test_unknown_gameparam_modification_is_named(self):
        self.fixture.gameparam.write_bytes(b"someone elses experiment")
        report = run(self.fixture)
        result = finding(report, "installed gameparam")
        self.assertEqual(result.status, FAIL)
        self.assertIn("neither", result.detail)
        self.assertIn(str(self.fixture.gameparam), result.detail)

    def test_plan_hash_mismatch_between_seed_and_manifest(self):
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        manifest["plan_sha256"] = sha256(b"a different seeds plan")
        self.fixture.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report = run(self.fixture)
        result = finding(report, "suppression binder and manifest")
        self.assertEqual(result.status, FAIL)
        self.assertIn("plan hash", result.detail)

    def test_runtime_mismatch_between_request_and_plan(self):
        plan = json.loads(self.fixture.plan_path.read_text(encoding="utf-8"))
        plan["runtime_build"] = "bb-runtime-r8"
        self.fixture.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        report = run(self.fixture)
        self.assertEqual(finding(report, "runtime build agreement").status, FAIL)

    def test_request_without_world_version_fails_the_request_check(self):
        request = json.loads(self.fixture.request_path.read_text(encoding="utf-8"))
        del request["world_version"]
        self.fixture.request_path.write_text(json.dumps(request), encoding="utf-8")
        report = run(self.fixture)
        result = finding(report, "AP seed request")
        self.assertEqual(result.status, FAIL)
        self.assertIn("world_version", result.detail)

    def test_elevation_warns_when_a_spawner_is_running_and_launcher_unelevated(self):
        with patch("bb_launcher.doctor.launcher_is_elevated", return_value=False):
            report = run(
                self.fixture,
                process_running=lambda name: name == "bblauncher.exe",
            )
        result = finding(report, "elevation")
        self.assertEqual(result.status, WARN)
        self.assertIn("bblauncher.exe", result.detail)
        self.assertIn("administrator", result.remedy)

    def test_elevation_passes_when_the_launcher_is_elevated(self):
        with patch("bb_launcher.doctor.launcher_is_elevated", return_value=True):
            report = run(
                self.fixture,
                process_running=lambda name: name == "bblauncher.exe",
            )
        self.assertEqual(finding(report, "elevation").status, PASS)

    def test_item_grants_warn_without_the_ce_bridge(self):
        report = run(self.fixture)
        result = finding(report, "item grants")
        self.assertEqual(result.status, WARN)
        self.assertIn("Generate Launch Plan", result.remedy)

    def test_item_grants_pass_with_the_ce_bridge(self):
        root = self.fixture.root
        ce_exe = root / "cheatengine.exe"
        ce_exe.write_bytes(b"ce")
        table = root / "grant.CT"
        table.write_bytes(b"table")
        plan = json.loads(self.fixture.plan_path.read_text(encoding="utf-8"))
        plan["processes"].append(
            {
                "name": "CE bridge",
                "executable": str(ce_exe),
                "sha256": sha256(b"ce"),
                "arguments": [str(table)],
            }
        )
        self.fixture.plan_path.write_text(json.dumps(plan), encoding="utf-8")
        report = run(self.fixture)
        self.assertEqual(finding(report, "item grants").status, PASS)

    def _pin_ce_bridge(self) -> None:
        root = self.fixture.root
        ce_exe = root / "cheatengine.exe"
        ce_exe.write_bytes(b"ce")
        table = root / "grant.CT"
        table.write_bytes(b"table")
        plan = json.loads(self.fixture.plan_path.read_text(encoding="utf-8"))
        plan["processes"].append(
            {
                "name": "CE bridge",
                "executable": str(ce_exe),
                "sha256": sha256(b"ce"),
                "arguments": [str(table)],
            }
        )
        self.fixture.plan_path.write_text(json.dumps(plan), encoding="utf-8")

    def test_a_stray_cheat_engine_fails_the_doctor_when_the_bridge_is_pinned(self):
        # bb-archipelago#137: with a bridge in the plan this is no longer a
        # warning -- launching now delivers nothing.
        self._pin_ce_bridge()
        report = run(self.fixture, process_running=lambda name: name == "cheatengine.exe")
        stray = finding(report, "running process cheatengine.exe")
        self.assertEqual(stray.status, FAIL)
        self.assertIn("close every Cheat Engine window", stray.remedy)
        grants = finding(report, "item grants")
        self.assertEqual(grants.status, FAIL)
        self.assertIn("already running", grants.detail)
        self.assertFalse(report.ok)

    def test_item_grants_reports_that_the_harness_has_not_reported_yet(self):
        self._pin_ce_bridge()
        report = run(self.fixture)
        grants = finding(report, "item grants")
        self.assertEqual(grants.status, PASS)
        self.assertIn("has not reported yet", grants.detail)

    def test_item_grants_reports_a_bridge_that_has_reported(self):
        self._pin_ce_bridge()
        paths = session_paths(
            self.fixture.root / "state", seed="AP_test", slot="Hunter"
        )
        paths.bridge_root.mkdir(parents=True, exist_ok=True)
        (paths.bridge_root / BRIDGE_STATE_NAME).write_text(
            "build=bb-0.1.0-r5\nprotocol=BBGRANT1\nharness=bb-native-grant-v5\n"
            "status=executing\npid=5040\n",
            encoding="utf-8",
        )
        report = run(self.fixture)
        grants = finding(report, "item grants")
        self.assertEqual(grants.status, PASS)
        self.assertIn("has reported", grants.detail)

    def test_server_probe_states(self):
        def refused(_host: str, _port: int) -> None:
            raise ConnectionRefusedError("no listener")

        report = run(self.fixture, probe=refused)
        result = finding(report, "AP server")
        self.assertEqual(result.status, FAIL)
        self.assertIn("nothing is listening", result.detail)

        def timed_out(_host: str, _port: int) -> None:
            raise socket.timeout("timed out")

        report = run(self.fixture, probe=timed_out)
        self.assertEqual(finding(report, "AP server").status, WARN)

        report = run(self.fixture, server="not-a-host-port")
        self.assertEqual(finding(report, "AP server").status, FAIL)

    def test_running_shad_blocks_and_ce_warns(self):
        report = run(
            self.fixture,
            process_running=lambda name: name == "shadps4.exe",
        )
        result = finding(report, "blocking processes")
        self.assertEqual(result.status, FAIL)
        self.assertIn("already running", result.detail)

        report = run(
            self.fixture,
            process_running=lambda name: name == "cheatengine.exe",
        )
        warnings = [item for item in report.findings if item.status == WARN]
        self.assertTrue(
            any(item.name == "running process cheatengine.exe" for item in warnings)
        )
        self.assertTrue(report.ok)

    def test_bad_game_root_skips_dependent_checks(self):
        self.fixture.gameparam.unlink()
        broken = self.fixture.settings_dict()
        broken["game_root"] = str(self.fixture.root / "not-a-game")
        settings = LauncherSettings.from_dict(broken, relative_to=self.fixture.root)
        report = run_doctor(
            settings, process_running=no_processes, probe=probe_ok
        )
        self.assertEqual(finding(report, "game installation").status, FAIL)
        self.assertEqual(finding(report, "installed gameparam").status, SKIP)
        self.assertEqual(finding(report, "MapStudio source").status, FAIL)

    def test_enemizer_off_skips_map_check(self):
        report = run(self.fixture, randomize_enemies=False)
        self.assertEqual(finding(report, "MapStudio source").status, SKIP)

    def test_report_is_ascii_and_summarizes(self):
        text = format_report(run(self.fixture))
        text.encode("ascii")
        self.assertIn("Doctor:", text.splitlines()[-1])

    def test_cli_exit_codes_follow_the_report(self):
        import contextlib
        import io

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli_main(["doctor", "--settings", str(self.fixture.settings_path)])
        # The CLI probes the real machine: the fixture's localhost:38281 may or
        # may not be listening, so only the settings-driven checks are stable.
        self.assertIn("game installation", out.getvalue())

        broken = self.fixture.settings_dict()
        broken["game_root"] = str(self.fixture.root / "not-a-game")
        self.fixture.settings_path.write_text(json.dumps(broken), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            code = cli_main(["doctor", "--settings", str(self.fixture.settings_path)])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
