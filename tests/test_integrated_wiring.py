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


if __name__ == "__main__":
    unittest.main()
