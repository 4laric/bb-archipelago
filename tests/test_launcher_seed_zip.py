"""bb-archipelago#194: the launcher takes the multiworld zip hosts actually send.

Archipelago generation emits one ``AP_<seed>.zip`` per multiworld and hosts
hand players that zip, not the per-slot file inside it. Every test here builds
its zip in memory in a tmpdir, so the fixtures are the exact shapes a real
generation produces: one Bloodborne slot, several, or none.
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bb_launcher.core import ValidationError
from bb_launcher.seed_request import (
    EXTRACTION_DIRECTORY,
    archive_player_name,
    archive_slots,
    resolve_request_source,
)
from bb_launcher.doctor import FAIL, PASS, format_report, run_doctor
from bb_launcher.ui import FIELD_DEFINITIONS, derive_ap_request, request_enemy_seed
from bb_launcher.workflow import REQUEST_FORMAT, LauncherSettings, _request_identity

from test_launcher_doctor import DoctorFixture, finding


def request_payload(player: int, name: str, seed: str = "AP_1:1") -> dict:
    return {
        "format": REQUEST_FORMAT,
        "player": player,
        "player_name": name,
        "runtime_build": "bb-0.1.0-r7",
        "world_version": "0.1.0",
        "enemizer_seed": seed,
        "seed_name": "AP_1",
        "suppression": {"plan_sha256": "0" * 64},
    }


def write_seed_zip(path: Path, members: dict[str, object]) -> Path:
    """An AP_<seed>.zip whose members are JSON documents (or raw bytes)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        for name, payload in members.items():
            raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
            bundle.writestr(name, raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())
    return path


def player_container(payload: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("archipelago.json", json.dumps({
            "compatible_version": 5,
            "version": 7,
            "server": "",
            "player": payload["player"],
            "player_name": payload["player_name"],
            "game": "Bloodborne",
            "patch_file_ending": ".apbb",
        }))
        bundle.writestr("seed.bbseed.json", json.dumps(payload))
    return buffer.getvalue()


class SingleSlotZipTests(unittest.TestCase):
    def test_downloaded_apbb_player_file_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = request_payload(1, "Tester")
            archive = root / "P1_Tester.apbb"
            archive.write_bytes(player_container(payload))

            resolved = resolve_request_source(archive, state_root=root / "state")

            self.assertEqual(resolved.member, "seed.bbseed.json")
            self.assertEqual(json.loads(resolved.path.read_text())["player_name"], "Tester")

    def test_multiworld_zip_resolves_nested_apbb_player_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = request_payload(1, "Tester")
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.apbb": player_container(payload)},
            )

            resolved = resolve_request_source(archive, state_root=root / "state")

            self.assertEqual(resolved.member, "AP_1_P1_Tester.apbb!seed.bbseed.json")
            self.assertEqual(json.loads(resolved.path.read_text())["player_name"], "Tester")

    def test_lone_bloodborne_slot_is_chosen_without_a_player_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester")},
            )
            resolved = resolve_request_source(archive, state_root=root / "state")
            self.assertEqual(resolved.member, "AP_1_P1_Tester.bbseed.json")
            self.assertEqual(resolved.player_name, "Tester")
            self.assertEqual(resolved.archive, archive)
            self.assertTrue(resolved.path.is_file())
            payload = json.loads(resolved.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["player_name"], "Tester")

    def test_lone_slot_names_itself_so_the_player_name_field_can_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P3_oz.bbseed.json": request_payload(3, "oz")},
            )
            self.assertEqual(archive_player_name(archive), "oz")

    def test_a_zip_resolves_to_the_same_identity_as_its_extracted_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = request_payload(1, "Tester")
            archive = write_seed_zip(root / "AP_1.zip", {"AP_1_P1_Tester.bbseed.json": payload})
            loose = root / "AP_1_P1_Tester.bbseed.json"
            loose.write_text(json.dumps(payload), encoding="utf-8")

            from_zip = _request_identity(archive, state_root=root / "state")
            from_file = _request_identity(loose)
            self.assertEqual(from_zip["slot"], "Tester")
            for identity in (from_zip, from_file):
                identity.pop("source"); identity.pop("path")
            self.assertEqual(from_zip, from_file)

    def test_legacy_bbenemizer_member_is_still_a_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbenemizer.json": request_payload(1, "Tester")},
            )
            resolved = resolve_request_source(archive, state_root=root / "state")
            self.assertEqual(resolved.member, "AP_1_P1_Tester.bbenemizer.json")

    def test_enemizer_seed_reads_straight_out_of_the_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester", seed="AP_1:7")},
            )
            self.assertEqual(
                request_enemy_seed(archive, state_root=root / "state"), "AP_1:7"
            )


class MultipleSlotZipTests(unittest.TestCase):
    def _archive(self, root: Path) -> Path:
        return write_seed_zip(
            root / "AP_1.zip",
            {
                "AP_1_P1_Bas.bbseed.json": request_payload(1, "Bas"),
                "AP_1_P2_oz.bbseed.json": request_payload(2, "oz"),
            },
        )

    def test_the_entered_player_name_picks_the_matching_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resolved = resolve_request_source(
                self._archive(root), player_name="oz", state_root=root / "state"
            )
            self.assertEqual(resolved.member, "AP_1_P2_oz.bbseed.json")
            self.assertEqual(resolved.player_name, "oz")

    def test_without_a_player_name_it_refuses_and_lists_the_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValidationError) as raised:
                resolve_request_source(self._archive(root), state_root=root / "state")
            message = str(raised.exception)
            self.assertIn("2 Bloodborne slots", message)
            self.assertIn("Bas", message)
            self.assertIn("oz", message)
            self.assertIn("AP player name", message)

    def test_an_unknown_player_name_is_refused_naming_what_the_zip_holds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ValidationError) as raised:
                resolve_request_source(
                    self._archive(root), player_name="Nobody", state_root=root / "state"
                )
            message = str(raised.exception)
            self.assertIn("Nobody", message)
            self.assertIn("Bas", message)

    def test_a_multi_slot_zip_names_no_one_so_it_cannot_prefill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertIsNone(archive_player_name(self._archive(root)))


class EmptyZipTests(unittest.TestCase):
    def test_a_zip_without_a_bloodborne_slot_says_exactly_that(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {
                    "AP_1_P1_Someone.apz3": b"another game's output",
                    "AP_1_Spoiler.txt": b"spoiler log",
                },
            )
            with self.assertRaises(ValidationError) as raised:
                resolve_request_source(archive, state_root=root / "state")
            self.assertIn("no Bloodborne slot", str(raised.exception))

    def test_a_bbseed_member_that_is_not_a_request_is_not_a_slot(self):
        # Name-shaped but payload-wrong: selection reads the payload, never
        # the filename, so this zip has nothing to offer.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": {"format": "something-else"}},
            )
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.namelist(), ["AP_1_P1_Tester.bbseed.json"])
            self.assertEqual(len(archive_slots(archive)), 0)
            with self.assertRaises(ValidationError) as raised:
                resolve_request_source(archive, state_root=root / "state")
            self.assertIn("no Bloodborne slot", str(raised.exception))


class ExtractionTests(unittest.TestCase):
    def test_the_extraction_is_launcher_owned_and_under_the_state_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester")},
            )
            resolved = resolve_request_source(archive, state_root=state)
            self.assertIn(EXTRACTION_DIRECTORY, resolved.path.parts)
            self.assertTrue(
                resolved.path.is_relative_to(state), f"{resolved.path} escaped {state}"
            )

    def test_reselecting_the_same_zip_reuses_the_same_extracted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            archive = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester")},
            )
            first = resolve_request_source(archive, state_root=state)
            stamp = first.path.stat().st_mtime_ns
            second = resolve_request_source(archive, state_root=state)
            self.assertEqual(first.path, second.path)
            self.assertEqual(second.path.stat().st_mtime_ns, stamp)
            self.assertEqual(
                len(list((state / EXTRACTION_DIRECTORY).iterdir())),
                1,
                "a second selection must not mint a second extraction directory",
            )

    def test_a_different_zip_extracts_somewhere_else(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            one = write_seed_zip(
                root / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester", seed="AP_1:1")},
            )
            two = write_seed_zip(
                root / "AP_2.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester", seed="AP_2:1")},
            )
            first = resolve_request_source(one, state_root=state)
            second = resolve_request_source(two, state_root=state)
            self.assertNotEqual(first.path, second.path)
            self.assertEqual(
                json.loads(second.path.read_text(encoding="utf-8"))["enemizer_seed"],
                "AP_2:1",
            )


class LooseRequestUnchangedTests(unittest.TestCase):
    """Control: the pre-#194 path must be byte-for-byte the same experience."""

    def test_a_loose_request_is_returned_untouched_and_never_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            loose = root / "AP_1_P1_Tester.bbseed.json"
            loose.write_text(json.dumps(request_payload(1, "Tester")), encoding="utf-8")
            resolved = resolve_request_source(loose, player_name="Tester", state_root=state)
            self.assertEqual(resolved.path, loose)
            self.assertIsNone(resolved.archive)
            self.assertFalse(resolved.from_archive)
            self.assertFalse(state.exists(), "a loose request must not touch the state root")

    def test_a_missing_zip_is_named_in_the_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "AP_gone.zip"
            with self.assertRaises(ValidationError) as raised:
                resolve_request_source(missing, state_root=Path(tmp) / "state")
            self.assertIn(str(missing), str(raised.exception))


class CandidateScanTests(unittest.TestCase):
    def test_the_output_scan_offers_the_multiworld_zip_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "Archipelago" / "output"
            archive = write_seed_zip(
                out / "AP_1.zip",
                {"AP_1_P1_Tester.bbseed.json": request_payload(1, "Tester")},
            )
            self.assertEqual(derive_ap_request((root,)), archive)

    def test_the_scan_prefers_the_zip_holding_the_named_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            out = root / "Archipelago" / "output"
            write_seed_zip(
                out / "AP_1.zip",
                {"AP_1_P1_Bas.bbseed.json": request_payload(1, "Bas")},
            )
            mine = write_seed_zip(
                out / "AP_2.zip",
                {"AP_2_P1_oz.bbseed.json": request_payload(1, "oz")},
            )
            self.assertEqual(derive_ap_request((root,), "oz"), mine)


class FieldLabelTests(unittest.TestCase):
    def test_the_field_names_both_shapes_it_accepts(self):
        labels = {name: label for name, label, _kind in FIELD_DEFINITIONS}
        label = labels["ap_request"]
        self.assertIn(".zip", label)
        self.assertIn(".bbseed.json", label)


class DoctorZipTests(unittest.TestCase):
    """The Doctor takes the zip and says which member it chose."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = DoctorFixture(self.root)
        self.payload = json.loads(self.fixture.request_path.read_text(encoding="utf-8"))

    def tearDown(self):
        self.temp.cleanup()

    def _settings_for(self, archive: Path) -> LauncherSettings:
        value = self.fixture.settings_dict()
        value["ap_request"] = str(archive)
        return LauncherSettings.from_dict(value, relative_to=self.root)

    def _run(self, archive: Path, player_name: str | None = None):
        return run_doctor(
            self._settings_for(archive),
            process_running=lambda _name: False,
            probe=lambda _host, _port: None,
            player_name=player_name,
        )

    def test_the_finding_names_both_the_zip_and_the_chosen_member(self):
        member = "AP_test_P1_Hunter.bbseed.json"
        archive = write_seed_zip(self.root / "AP_test.zip", {member: self.payload})
        result = finding(self._run(archive), "AP seed file")
        self.assertEqual(result.status, PASS, result.detail)
        self.assertIn(member, result.detail)
        self.assertIn(str(archive), result.detail)
        self.assertIn("Hunter", result.detail)

    def test_the_chain_downstream_of_the_zip_still_passes(self):
        archive = write_seed_zip(
            self.root / "AP_test.zip", {"AP_test_P1_Hunter.bbseed.json": self.payload}
        )
        report = self._run(archive, player_name="Hunter")
        self.assertTrue(report.ok, format_report(report))
        self.assertEqual(
            finding(report, "request slot agreement").status, PASS, format_report(report)
        )

    def test_an_ambiguous_zip_fails_the_request_check_instead_of_guessing(self):
        other = dict(self.payload, player=2, player_name="oz")
        archive = write_seed_zip(
            self.root / "AP_test.zip",
            {
                "AP_test_P1_Hunter.bbseed.json": self.payload,
                "AP_test_P2_oz.bbseed.json": other,
            },
        )
        result = finding(self._run(archive), "AP seed file")
        self.assertEqual(result.status, FAIL, result.detail)
        self.assertIn("2 Bloodborne slots", result.detail)
        self.assertIn("AP_<seed>.zip", result.remedy)

    def test_the_entered_name_disambiguates_the_same_zip(self):
        other = dict(self.payload, player=2, player_name="oz")
        archive = write_seed_zip(
            self.root / "AP_test.zip",
            {
                "AP_test_P1_Hunter.bbseed.json": self.payload,
                "AP_test_P2_oz.bbseed.json": other,
            },
        )
        result = finding(self._run(archive, player_name="Hunter"), "AP seed file")
        self.assertEqual(result.status, PASS, result.detail)
        self.assertIn("AP_test_P1_Hunter.bbseed.json", result.detail)
        self.assertNotIn("AP_test_P2_oz.bbseed.json", result.detail)


if __name__ == "__main__":
    unittest.main()
