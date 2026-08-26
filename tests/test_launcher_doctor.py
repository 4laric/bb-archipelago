from __future__ import annotations

import contextlib
import hashlib
import io
import json
import socket
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.cli import main as cli_main
from bb_launcher.client_config import session_paths
from bb_launcher.core import (
    MAP_PREFIX,
    SERIAL,
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    SUPPRESSION_PATH,
    USER_MODS_DIR_NAME,
    GameInstall,
)
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

        self.request_path = root / "seed.bbseed.json"
        self.request_path.write_text(
            json.dumps(
                {
                    "format": "bb-seed-request-v1",
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
        self.shad_exe = shad_exe
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
                            "arguments": ["{game_path}"],
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
            "AP seed file",
            "launch plan",
            "runtime build agreement",
            "suppression binder and manifest",
            "installed gameparam",
            "MapStudio source",
            "user mods",
            "AP server",
            "blocking processes",
        ):
            self.assertEqual(finding(report, name).status, PASS, name)

    def test_a_pre_177_plan_is_reported_stale_instead_of_dying_at_runtime(self):
        # bb-archipelago#177: the plan the launcher used to generate invokes
        # shadPS4 with the bare game ID, which the emulator resolves only
        # against its own install_dirs -- empty on a never-configured copy.
        # oz's launcher game-folder field was correct and it still failed, so
        # the Doctor has to name the plan, not the folder.
        value = json.loads(self.fixture.plan_path.read_text(encoding="utf-8"))
        self.assertEqual(value["processes"][0]["arguments"], ["{game_path}"])
        value["processes"][0]["arguments"] = [SERIAL]
        self.fixture.plan_path.write_text(json.dumps(value), encoding="utf-8")
        report = run(self.fixture)
        result = finding(report, "launch plan game argument")
        self.assertEqual(result.status, FAIL)
        self.assertIn("bare game ID", result.detail)
        self.assertIn("regenerate the launch plan", result.remedy)
        self.assertFalse(report.ok)
        # The plan itself still loads and hashes clean: this is a *stale* plan,
        # not a broken one, and the two findings must not be confused.
        self.assertEqual(finding(report, "launch plan").status, PASS)

    def test_a_current_plan_names_the_game_directory_by_path(self):
        report = run(self.fixture)
        result = finding(report, "launch plan game argument")
        self.assertEqual(result.status, PASS)
        self.assertIn(str(self.fixture.root / "game" / SERIAL), result.detail)

    def test_the_shadps4_version_gate_fails_the_bblauncher_bundled_016(self):
        # oz passed every Doctor gate with the 0.16.0 copy bundled inside the
        # third-party BBLauncher and only found out at runtime (#177 point 1).
        report = run(self.fixture, read_shad_version=lambda _path: "0.16.0.0")
        result = finding(report, "shadPS4 version")
        self.assertEqual(result.status, FAIL)
        self.assertIn("0.16.0.0", result.detail)
        self.assertIn("0.18.0", result.detail)
        self.assertIn("BBLauncher", result.remedy)
        self.assertFalse(report.ok)

    def test_the_shadps4_version_gate_accepts_the_supported_build(self):
        seen: list[Path] = []

        def read(path: Path) -> str:
            seen.append(path)
            # A real Windows resource carries the four-part form.
            return "0.18.0.0"

        report = run(self.fixture, read_shad_version=read)
        result = finding(report, "shadPS4 version")
        self.assertEqual(result.status, PASS)
        self.assertEqual(seen, [self.fixture.shad_exe])
        self.assertIn("0.18.0.0", result.detail)

    def test_an_unreadable_version_resource_skips_rather_than_guesses(self):
        report = run(self.fixture, read_shad_version=lambda _path: None)
        result = finding(report, "shadPS4 version")
        self.assertEqual(result.status, SKIP)
        self.assertTrue(report.ok)

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

    def test_modified_gameparam_remedies_name_the_pre_modded_repack(self):
        """bb-archipelago#198: the common real cause, in both FAIL branches.

        Players hitting this are usually running a repack that ships its own
        param edits, not a corrupted dump, so the remedy names that case, points
        at a clean 01.09 patch layer, and says what the operator override costs.
        """
        for payload in (SUPPRESSED, b"someone elses experiment"):
            self.fixture.gameparam.write_bytes(payload)
            result = finding(run(self.fixture), "installed gameparam")
            self.assertEqual(result.status, FAIL)
            remedy = result.remedy or ""
            self.assertIn("repack", remedy)
            self.assertIn("Bloodborne (feat. shadPS4)", remedy)
            self.assertIn("01.09", remedy)
            self.assertIn(SUPPRESSION_OVERRIDE_KNOB, remedy)
        # The control: a healthy install carries no remedy at all, so this is a
        # statement about the failure branches.
        self.fixture.gameparam.write_bytes(VANILLA)
        healthy = finding(run(self.fixture), "installed gameparam")
        self.assertEqual(healthy.status, PASS)
        self.assertIsNone(healthy.remedy)

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
        result = finding(report, "AP seed file")
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

    def _user_mod(self, relative: str, content: bytes = b"user") -> Path:
        path = self.fixture.root / "game" / USER_MODS_DIR_NAME
        path = path.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_user_mods_pass_names_the_merged_count(self):
        self._user_mod("dvdroot_ps4/chr/c0000.bnd.dcx")
        self._user_mod("dvdroot_ps4/action/script/c0000.hks")
        result = finding(run(self.fixture), "user mods")
        self.assertEqual(result.status, PASS)
        self.assertIn("2 file(s)", result.detail)

    def test_user_gameparam_is_reported_as_an_exclusion(self):
        self._user_mod(SUPPRESSION_PATH)
        self._user_mod("dvdroot_ps4/chr/c0000.bnd.dcx")
        result = finding(run(self.fixture), "user mods")
        self.assertEqual(result.status, WARN)
        self.assertIn("ap-owned", result.detail)
        self.assertIn(SUPPRESSION_PATH, result.detail)
        self.assertIsNotNone(result.remedy)

    def test_wrapper_folder_mods_warn_loudly_and_name_the_wrapper(self):
        """The oz playtest.9 shape: mods dropped in as their shipped folders."""

        self._user_mod("Boczkek's FPS boost Lite/dvdroot_ps4/chr/c0000.bnd.dcx")
        self._user_mod("Boczkek's FPS boost Lite/dvdroot_ps4/chr/c1000.bnd.dcx")
        self._user_mod("Half Cloth Physics with Blood/dvdroot_ps4/chr/c2000.bnd.dcx")
        self._user_mod("dvdroot_ps4/parts/wp.partsbnd.dcx")
        result = finding(run(self.fixture), "user mods")
        self.assertEqual(result.status, WARN)
        self.assertIn("Boczkek's FPS boost Lite (2 file(s))", result.detail)
        self.assertIn("Half Cloth Physics with Blood (1 file(s))", result.detail)
        self.assertIn("3 file(s) can never load", result.detail)
        self.assertIn("1 file(s) from", result.detail)
        self.assertIsNotNone(result.remedy)
        self.assertIn(
            "move the contents of Boczkek's FPS boost Lite up one level so "
            "paths start with dvdroot_ps4/",
            result.remedy,
        )

    def test_user_maps_warn_only_while_the_enemizer_is_on(self):
        self._user_mod(f"{MAP_PREFIX}m24_01_00_00.msb.dcx")
        self.assertEqual(finding(run(self.fixture), "user mods").status, WARN)
        report = run(self.fixture, randomize_enemies=False)
        self.assertEqual(finding(report, "user mods").status, PASS)

    def test_absent_user_directory_passes(self):
        result = finding(run(self.fixture), "user mods")
        self.assertEqual(result.status, PASS)
        self.assertIn(USER_MODS_DIR_NAME, result.detail)

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
        self.assertEqual(finding(report, "user mods").status, SKIP)

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


class DoctorSuppressionOverrideTests(unittest.TestCase):
    """bb-archipelago#183: Doctor must agree with the launch lane.

    An override that fires at launch but still FAILs in Doctor sends the
    operator chasing a refusal that will not happen -- so the same two skews
    become WARN here, each naming the knob, and never a silent PASS.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.fixture = DoctorFixture(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def skew_the_plan(self) -> None:
        manifest = json.loads(self.fixture.manifest_path.read_text(encoding="utf-8"))
        manifest["plan_sha256"] = hashlib.sha256(b"a different seed's plan").hexdigest()
        self.fixture.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def test_plan_skew_fails_without_the_knob(self):
        self.skew_the_plan()
        report = run(self.fixture)
        item = finding(report, "suppression binder and manifest")
        self.assertEqual(FAIL, item.status)
        self.assertFalse(report.ok)

    def test_plan_skew_warns_naming_the_knob_under_the_knob(self):
        self.skew_the_plan()
        report = run(self.fixture, allow_suppression_mismatch=True)
        item = finding(report, "suppression binder and manifest")
        self.assertEqual(WARN, item.status)
        self.assertIn(SUPPRESSION_OVERRIDE_KNOB, item.detail)
        self.assertIn(SUPPRESSION_CHECK_PLAN, item.detail)
        self.assertIn(SUPPRESSION_OVERRIDE_KNOB, item.remedy or "")
        # WARN does not sink the report, but it is visible in the rendering.
        self.assertTrue(report.ok)
        self.assertIn("[WARN] suppression binder and manifest", format_report(report))

    def test_installed_gameparam_skew_fails_without_the_knob(self):
        self.fixture.gameparam.write_bytes(b"an install one re-copy behind")
        report = run(self.fixture)
        self.assertEqual(FAIL, finding(report, "installed gameparam").status)

    def test_installed_gameparam_skew_warns_naming_expected_and_found(self):
        self.fixture.gameparam.write_bytes(b"an install one re-copy behind")
        report = run(self.fixture, allow_suppression_mismatch=True)
        item = finding(report, "installed gameparam")
        self.assertEqual(WARN, item.status)
        self.assertIn(SUPPRESSION_CHECK_SOURCE, item.detail)
        self.assertIn(sha256(VANILLA)[:12], item.detail)
        self.assertIn(sha256(b"an install one re-copy behind")[:12], item.detail)
        self.assertIn(str(self.fixture.gameparam), item.detail)

    def test_an_already_suppressed_install_also_warns_rather_than_failing(self):
        # The launch lane bypasses one comparison (manifest source vs the
        # installed file); both of this check's FAIL branches are that same
        # comparison, so both must downgrade together.
        self.fixture.gameparam.write_bytes(SUPPRESSED)
        self.assertEqual(FAIL, finding(run(self.fixture), "installed gameparam").status)
        item = finding(
            run(self.fixture, allow_suppression_mismatch=True), "installed gameparam"
        )
        self.assertEqual(WARN, item.status)
        self.assertIn(SUPPRESSION_OVERRIDE_KNOB, item.detail)

    def test_a_healthy_chain_under_the_knob_still_passes_without_a_warning(self):
        report = run(self.fixture, allow_suppression_mismatch=True)
        self.assertEqual(PASS, finding(report, "suppression binder and manifest").status)
        self.assertEqual(PASS, finding(report, "installed gameparam").status)
        self.assertNotIn(SUPPRESSION_OVERRIDE_KNOB, format_report(report))

    def test_the_knob_does_not_soften_a_corrupt_binder(self):
        self.fixture.binder.write_bytes(b"not what the manifest describes")
        item = finding(
            run(self.fixture, allow_suppression_mismatch=True),
            "suppression binder and manifest",
        )
        self.assertEqual(FAIL, item.status)
        self.assertIn("does not match its build manifest", item.detail)

    def test_the_cli_flag_is_off_unless_passed_and_is_never_read_from_settings(self):
        self.skew_the_plan()
        # A saved setup that tries to turn the override on is ignored: the knob
        # is per-invocation by construction, so it can never go sticky-silent.
        saved = self.fixture.settings_dict()
        saved["allow_suppression_mismatch"] = True
        self.fixture.settings_path.write_text(json.dumps(saved), encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli_main(["doctor", "--settings", str(self.fixture.settings_path)])
        self.assertEqual(1, code)
        self.assertIn("[FAIL] suppression binder and manifest", out.getvalue())

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli_main(
                [
                    "doctor",
                    "--settings",
                    str(self.fixture.settings_path),
                    SUPPRESSION_OVERRIDE_KNOB,
                ]
            )
        rendered = out.getvalue()
        self.assertIn("[WARN] suppression binder and manifest", rendered)
        self.assertIn(SUPPRESSION_OVERRIDE_KNOB, rendered)


if __name__ == "__main__":
    unittest.main()
