"""The integrated standalone path exports inactive data with a late byte check."""

from __future__ import annotations

import shutil
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.integrated.backend import Backend
from bb_launcher.integrated.protocol import PROTOCOL_VERSION
from test_standalone_mod_export import make_overlay, write_json, file_record
from tools.export_standalone_mod import BUILD_IDENTITY_NAME, BUILD_RECEIPT_NAME
from tools.bb_standalone.schema import GAMEPARAM_PATH, PARAMDEF_PATH


def request(op: str, params: dict, seq: int = 0) -> dict:
    return {"protocol": PROTOCOL_VERSION, "op": op, "id": f"standalone-{seq}",
            "seq": seq, "params": params}


class FakeInstall:
    def __init__(self, root: Path):
        self.root = root

    def resolve_file(self, relative: str, *, include_mods: bool = True):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"original source")
        return "base", path

    def content_backends(self):
        return [("base", self.root)]


class IntegratedStandaloneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.mods = self.root / "BBLauncher" / "Mods"
        self.mods.mkdir(parents=True)
        self.tools = self.root / "app" / "tools"
        self.tools.mkdir(parents=True)
        (self.tools / "BBSuppressionWriter.exe").write_bytes(b"writer")
        self.backend = Backend(self.state)
        self.install = FakeInstall(self.root / "game")
        self.install_patcher = patch("bb_launcher.integrated.standalone.GameInstall.from_root",
                                     return_value=self.install)
        self.app_patcher = patch("bb_launcher.integrated.standalone.application_root",
                                 return_value=self.root / "app")
        self.install_patcher.start()
        self.app_patcher.start()
        self.params = {
            "seed": "Moonlight-101", "include_dlc": False,
            "randomize_enemies": False, "game_root": str(self.root / "game"),
            "mods_root": str(self.mods),
        }

    def tearDown(self):
        self.app_patcher.stop()
        self.install_patcher.stop()
        self.temp.cleanup()

    def _prepare(self):
        def fake_build(config):
            fixture = make_overlay(config.output.parent, seed=config.seed,
                                   enemies=config.enemy_options.enabled)
            identity_path = fixture / BUILD_IDENTITY_NAME
            receipt_path = fixture / BUILD_RECEIPT_NAME
            identity = json.loads(identity_path.read_text(encoding="utf-8"))
            identity["source_hashes"] = {
                GAMEPARAM_PATH: hashlib.sha256(config.gameparam.read_bytes()).hexdigest(),
                PARAMDEF_PATH: hashlib.sha256(config.paramdef.read_bytes()).hexdigest(),
            }
            if config.enemy_options.enabled:
                for source_root, logical_root in (
                    (config.maps, "dvdroot_ps4/map/MapStudio"),
                    (config.scripts, "dvdroot_ps4/script"),
                ):
                    for source in source_root.iterdir():
                        identity["source_hashes"][f"{logical_root}/{source.name}"] = (
                            hashlib.sha256(source.read_bytes()).hexdigest())
            identity["options"]["enemies"]["enabled"] = config.enemy_options.enabled
            write_json(identity_path, identity)
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["source_hashes"] = identity["source_hashes"]
            receipt["identity_sha256"] = hashlib.sha256(identity_path.read_bytes()).hexdigest()
            receipt["files"] = [
                file_record(fixture, row["path"]) for row in receipt["files"]
            ]
            write_json(receipt_path, receipt)
            fixture.rename(config.output)
            return {}

        with patch("tools.build_standalone_randomizer.build", side_effect=fake_build):
            return self.backend.handle(request("prepare_standalone", self.params))

    def _verify_params(self, prepared: dict) -> dict:
        return {
            **self.params,
            "package_path": prepared["package_path"],
            "receipt_path": prepared["receipt_path"],
            "receipt_id": prepared["receipt_id"],
            "package_name": prepared["package_name"],
        }

    def test_prepare_exports_inactive_payload_then_verifies_late_bytes(self):
        prepared = self._prepare()
        self.assertTrue(prepared["ok"], prepared)
        result = prepared["result"]
        package = Path(result["package_path"])
        receipt = Path(result["receipt_path"])
        self.assertEqual(self.mods, package.parent)
        self.assertEqual(self.state / "standalone" / "receipts", receipt.parent)
        self.assertEqual(["dvdroot_ps4"], [path.name for path in package.iterdir()])
        self.assertFalse((self.mods.parent / "Mods-Active (DO NOT DELETE)").exists())
        verified = self.backend.handle(request("verify_standalone",
                                               self._verify_params(result), 1))
        self.assertTrue(verified["ok"], verified)
        self.assertEqual(result["receipt_id"], verified["result"]["receipt_id"])
        self.assertEqual(result["package_name"], verified["result"]["package_name"])
        binder = package / "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"
        binder.write_bytes(b"tampered")
        rejected = self.backend.handle(request("verify_standalone",
                                               self._verify_params(result), 2))
        self.assertFalse(rejected["ok"])
        self.assertEqual("verification-failed", rejected["error"]["code"])

    def test_rejects_invalid_choices_and_foreign_receipt(self):
        bad = self.backend.handle(request("prepare_standalone", {
            **self.params, "include_dlc": "yes",
        }))
        self.assertFalse(bad["ok"])
        self.assertEqual("bad-request", bad["error"]["code"])
        prepared = self._prepare()["result"]
        foreign = self.root / "other" / "receipt.json"
        foreign.parent.mkdir()
        shutil.copyfile(prepared["receipt_path"], foreign)
        rejected = self.backend.handle(request("verify_standalone", {
            **self._verify_params(prepared), "receipt_path": str(foreign),
        }, 3))
        self.assertFalse(rejected["ok"])
        self.assertEqual("verification-failed", rejected["error"]["code"])

    def test_repeated_prepare_reuses_same_receipt_and_binds_selected_install(self):
        first = self._prepare()
        second = self._prepare()
        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertEqual(first["result"]["receipt_id"], second["result"]["receipt_id"])
        self.assertEqual(first["result"]["package_path"], second["result"]["package_path"])
        self.assertEqual(1, len(list(self.mods.iterdir())))
        wrong_game = self.backend.handle(request("verify_standalone", {
            **self._verify_params(second["result"]),
            "game_root": str(self.root / "different-game"),
        }, 4))
        self.assertFalse(wrong_game["ok"])
        self.assertEqual("verification-failed", wrong_game["error"]["code"])

    def test_selected_serial_directory_survives_install_root_normalization(self):
        self.params["game_root"] = str(self.root / "game" / "CUSA03173")
        prepared = self._prepare()
        self.assertTrue(prepared["ok"], prepared)
        verified = self.backend.handle(request(
            "verify_standalone", self._verify_params(prepared["result"]), 5))
        self.assertTrue(verified["ok"], verified)

    def test_original_game_source_drift_blocks_launch_verification(self):
        prepared = self._prepare()
        self.assertTrue(prepared["ok"], prepared)
        original = self.install.root / GAMEPARAM_PATH
        original.write_bytes(b"game updated after randomization")
        verified = self.backend.handle(request(
            "verify_standalone", self._verify_params(prepared["result"]), 6))
        self.assertFalse(verified["ok"])
        self.assertEqual("verification-failed", verified["error"]["code"])

    def test_enemy_script_source_drift_blocks_launch_verification(self):
        self.params["randomize_enemies"] = True
        (self.tools / "BBEnemizerWriter.exe").write_bytes(b"enemy writer")
        map_file = self.install.root / "dvdroot_ps4/map/MapStudio/m21_00_00_00.msb.dcx"
        script_file = self.install.root / "dvdroot_ps4/script/m21_00_00_00.luabnd.dcx"
        for path in (map_file, script_file):
            path.parent.mkdir(parents=True)
            path.write_bytes(b"original enemy source")
        prepared = self._prepare()
        self.assertTrue(prepared["ok"], prepared)
        first = self.backend.handle(request(
            "verify_standalone", self._verify_params(prepared["result"]), 7))
        self.assertTrue(first["ok"], first)
        script_file.write_bytes(b"game AI updated")
        changed = self.backend.handle(request(
            "verify_standalone", self._verify_params(prepared["result"]), 8))
        self.assertFalse(changed["ok"])
        self.assertEqual("verification-failed", changed["error"]["code"])


if __name__ == "__main__":
    unittest.main()
