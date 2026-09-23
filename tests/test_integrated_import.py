"""Import, seed inspection and install detection for the integrated backend."""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bb_launcher.core import ValidationError
from bb_launcher.integrated.backend import Backend
from bb_launcher.integrated.import_state import detect_installations, import_companion_state
from bb_launcher.integrated.protocol import PROTOCOL_VERSION


def request(op: str, params: dict | None = None, seq: int = 0, op_id: str = "op-1") -> dict:
    return {"protocol": PROTOCOL_VERSION, "op": op, "id": op_id, "seq": seq,
            "params": params or {}}


class InstallDetectionTests(unittest.TestCase):
    def test_no_install_reports_missing_prerequisite(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = Backend(Path(state))
            response = backend.handle(
                request("inspect_install", {"candidates": [str(Path(state) / "nope")]}))
            self.assertFalse(response["ok"])
            self.assertEqual(response["error"]["code"], "missing-prerequisite")

    def test_ambiguity_is_reported_not_guessed(self) -> None:
        report = None
        with patch("bb_launcher.core.GameInstall.from_root") as fake:
            fake.side_effect = [
                type("I", (), {"serial": "CUSA03173", "app_version": "01.09"})(),
                type("I", (), {"serial": "CUSA03173", "app_version": "01.09"})(),
            ]
            report = detect_installations([Path("a"), Path("b")])
        assert report is not None
        self.assertEqual(report["status"], "ambiguous")
        self.assertIsNone(report["selected"])
        self.assertEqual(len(report["installs"]), 2)


class SeedInspectionTests(unittest.TestCase):
    def _seed_file(self, directory: str, payload: dict) -> str:
        path = Path(directory) / "seed.bbseed.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)

    def test_single_slot_seed_needs_no_player_question(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = Backend(Path(state))
            seed = self._seed_file(state, {
                "format": "bb-seed-request-v1", "seed": "Evening hunt",
                "player": 1, "player_name": "Alaric", "runtime_build": "r",
                "world_version": "w", "server": "archipelago.gg:9",
            })
            response = backend.handle(request("inspect_seed", {"seed_path": seed}))
            self.assertTrue(response["ok"], response)
            self.assertFalse(response["result"]["needs_choice"])
            self.assertEqual(response["result"]["selected"], "Alaric")

    def test_multi_slot_seed_without_choice_returns_available_slots(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            backend = Backend(Path(state))
            seed = self._seed_file(state, {
                "format": "bb-seed-request-v1", "seed": "Hunt", "player": 1,
                "player_name": "A", "runtime_build": "r", "world_version": "w",
                "slots": ["A", "B"],
            })
            missing = backend.handle(request("inspect_seed", {"seed_path": seed}))
            self.assertTrue(missing["ok"], missing)
            self.assertTrue(missing["result"]["needs_choice"])
            self.assertIsNone(missing["result"]["selected"])
            self.assertEqual(missing["result"]["slots"], ["A", "B"])
            chosen = backend.handle(
                request("inspect_seed", {"seed_path": seed, "player_name": "B"}))
            self.assertTrue(chosen["ok"], chosen)
            self.assertEqual(chosen["result"]["selected"], "B")

    def test_multi_slot_zip_returns_slots_before_extracting_a_member(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            archive = Path(state) / "AP_seed.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                for slot in ("A", "B"):
                    bundle.writestr(f"{slot}.bbseed.json", json.dumps({
                        "format": "bb-seed-request-v1", "seed": "Hunt",
                        "player": 1, "player_name": slot, "runtime_build": "r",
                        "world_version": "w", "server": "archipelago.gg:9",
                    }))
            backend = Backend(Path(state))
            response = backend.handle(request("inspect_seed", {"seed_path": str(archive)}))
            self.assertTrue(response["ok"], response)
            self.assertEqual(response["result"]["slots"], ["A", "B"])
            self.assertTrue(response["result"]["needs_choice"])
            self.assertFalse((Path(state) / "seed-requests").exists())


class CompanionImportTests(unittest.TestCase):
    def test_import_references_without_moving_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            root = Path(state)
            receipts = root / "external" / "receipts"
            receipts.mkdir(parents=True)
            (receipts / "abc.json").write_text("{}", encoding="utf-8")
            sessions = root / "sessions"
            sessions.mkdir()
            (sessions / "ledger.json").write_text("{}", encoding="utf-8")
            record = import_companion_state(state_root=state, game_root=str(root / "game"))
            kinds = {item["kind"] for item in record["adopted"]}
            self.assertIn("external/receipts", kinds)
            self.assertIn("sessions", kinds)
            # Originals untouched: still where the companion left them.
            self.assertTrue((receipts / "abc.json").is_file())
            self.assertIn("restore", record)

    def test_standalone_owner_requires_explicit_transition(self) -> None:
        with tempfile.TemporaryDirectory() as state:
            root = Path(state)
            overlay = root / "game" / "CUSA03173-mods"
            overlay.mkdir(parents=True)
            (overlay / ".bb-ap-owner.json").write_text("{}", encoding="utf-8")
            record = import_companion_state(state_root=state, game_root=str(root / "game"))
            self.assertTrue(record["requires_standalone_transition"])


if __name__ == "__main__":
    unittest.main()
