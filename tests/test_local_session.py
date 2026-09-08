from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from bb_launcher.core import ValidationError
from bb_launcher.local_session import (
    APTools,
    BloodborneWorldUnavailable,
    GenerationCancelled,
    bundled_apworld_path,
    discover_ap_tools,
    generate_seed,
    install_bloodborne_world,
    is_archipelago_root,
    start_server,
    validate_bloodborne_world,
)

WORLD_MANIFEST = {"game": "Bloodborne", "world_version": "0.1.0", "minimum_ap_version": "0.6.7"}


def make_apworld(path: Path, manifest: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("bloodborne/archipelago.json", json.dumps(manifest))


def make_ap_install(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "ArchipelagoGenerate.exe").touch()
    (root / "ArchipelagoServer.exe").touch()
    return root


class LocalSessionTests(unittest.TestCase):
    def test_packaged_tools_are_preferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ArchipelagoGenerate.exe").touch()
            (root / "ArchipelagoServer.exe").touch()
            tools = discover_ap_tools(root)
            self.assertEqual(tools.generate_command, (str(root / "ArchipelagoGenerate.exe"),))

    def test_source_checkout_uses_selected_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            python = root / "python.exe"
            for name in ("Generate.py", "MultiServer.py", "python.exe"):
                (root / name).touch()
            tools = discover_ap_tools(root, python)
            self.assertEqual(tools.server_command, (str(python), str(root / "MultiServer.py")))

    def test_world_manifest_must_match(self):
        expected = {"game": "Bloodborne", "world_version": "0.1.0", "minimum_ap_version": "0.6.7"}
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "custom_worlds" / "bloodborne.apworld"
            package.parent.mkdir()
            with zipfile.ZipFile(package, "w") as bundle:
                bundle.writestr("bloodborne/archipelago.json", json.dumps({**expected, "world_version": "0.0.9"}))
            with self.assertRaisesRegex(ValidationError, "0.0.9 installed; 0.1.0 required"):
                validate_bloodborne_world(tmp, expected_manifest=expected)

    def test_missing_and_mismatched_worlds_are_distinguishable_by_the_caller(self):
        # The UI offers "Install" or "Update ... to X"; prose alone cannot
        # choose between them.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(BloodborneWorldUnavailable) as missing:
                validate_bloodborne_world(root, expected_manifest=WORLD_MANIFEST)
            self.assertTrue(missing.exception.missing)
            self.assertFalse(missing.exception.mismatch)
            self.assertEqual("0.1.0", missing.exception.expected_version)

            make_apworld(root / "custom_worlds" / "bloodborne.apworld",
                         {**WORLD_MANIFEST, "world_version": "0.0.9"})
            with self.assertRaises(BloodborneWorldUnavailable) as stale:
                validate_bloodborne_world(root, expected_manifest=WORLD_MANIFEST)
            self.assertTrue(stale.exception.mismatch)
            self.assertEqual("0.0.9", stale.exception.installed_version)
            self.assertEqual("0.1.0", stale.exception.expected_version)

    def test_install_creates_custom_worlds_and_copies_the_bundled_apworld(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_ap_install(Path(tmp) / "Archipelago")
            source = Path(tmp) / "package" / "worlds" / "bloodborne.apworld"
            make_apworld(source, self.repo_manifest())
            self.assertFalse((root / "custom_worlds").exists(), "witness: nothing installed yet")
            with patch("bb_launcher.local_session.bundled_apworld_path", return_value=source):
                installed = install_bloodborne_world(root)
            self.assertEqual(root / "custom_worlds" / "bloodborne.apworld", installed)
            self.assertEqual(source.read_bytes(), installed.read_bytes())
            # No staging leftovers, and the world now validates for real.
            self.assertEqual(["bloodborne.apworld"],
                             sorted(path.name for path in (root / "custom_worlds").iterdir()))
            validate_bloodborne_world(root)

    def test_install_replaces_a_mismatched_world_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_ap_install(Path(tmp) / "Archipelago")
            destination = root / "custom_worlds" / "bloodborne.apworld"
            make_apworld(destination, {**WORLD_MANIFEST, "world_version": "0.0.9"})
            stale = destination.read_bytes()
            source = Path(tmp) / "package" / "worlds" / "bloodborne.apworld"
            make_apworld(source, self.repo_manifest())
            with patch("bb_launcher.local_session.bundled_apworld_path", return_value=source):
                installed = install_bloodborne_world(root)
            self.assertEqual(destination, installed)
            self.assertNotEqual(stale, destination.read_bytes())
            self.assertEqual(source.read_bytes(), destination.read_bytes())

    def test_install_refuses_a_source_world_checkout_instead_of_shadowing_it(self):
        for relative in ("worlds/bloodborne", "lib/worlds/bloodborne"):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                root = make_ap_install(Path(tmp) / "Archipelago")
                (root / relative).mkdir(parents=True)
                source = Path(tmp) / "package" / "worlds" / "bloodborne.apworld"
                make_apworld(source, self.repo_manifest())
                with patch("bb_launcher.local_session.bundled_apworld_path", return_value=source):
                    with self.assertRaisesRegex(ValidationError, "Update that checkout instead"):
                        install_bloodborne_world(root)
                self.assertFalse((root / "custom_worlds").exists(),
                                 "witness: the refusal wrote nothing")

    def test_install_without_a_bundled_apworld_names_the_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_ap_install(Path(tmp) / "Archipelago")
            absent = Path(tmp) / "package" / "worlds" / "bloodborne.apworld"
            with patch("bb_launcher.local_session.bundled_apworld_path", return_value=absent):
                with self.assertRaisesRegex(ValidationError, "does not carry a bloodborne.apworld"):
                    install_bloodborne_world(root)
            self.assertFalse((root / "custom_worlds").exists(),
                             "witness: the refusal wrote nothing")

    def test_install_refuses_a_folder_that_is_not_an_archipelago_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Downloads"
            root.mkdir()
            self.assertFalse(is_archipelago_root(root))
            with self.assertRaisesRegex(ValidationError, "is not an Archipelago installation"):
                install_bloodborne_world(root)
            self.assertEqual([], list(root.iterdir()), "witness: nothing was created")

    def test_bundled_apworld_prefers_the_package_and_falls_back_to_a_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "build" / "bloodborne.apworld").write_bytes(b"built")
            with patch("bb_launcher.local_session.application_root", return_value=root):
                self.assertEqual(root / "build" / "bloodborne.apworld", bundled_apworld_path())
                (root / "worlds").mkdir()
                (root / "worlds" / "bloodborne.apworld").write_bytes(b"packaged")
                self.assertEqual(root / "worlds" / "bloodborne.apworld", bundled_apworld_path())

    def repo_manifest(self) -> dict:
        path = Path(__file__).resolve().parents[1] / "worlds" / "bloodborne" / "archipelago.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_generation_streams_and_validates_one_hostable_zip(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            players = root / "players"; players.mkdir()
            output = root / "output"
            process = Mock(returncode=0)
            process.stdout = ["Generating\n"]
            process.poll.return_value = 0
            process.wait.return_value = 0
            popen.return_value = process

            def create_archive(command, **kwargs):
                run = Path(command[command.index("--outputpath") + 1])
                with zipfile.ZipFile(run / "AP_test.zip", "w") as bundle:
                    bundle.writestr("AP_test.archipelago", b"data")
                return process
            popen.side_effect = create_archive
            lines = []
            result = generate_seed(APTools(root, ("generate",), ("server",)), players, output, on_output=lines.append)
            self.assertEqual(result.archive.name, "AP_test.zip")
            self.assertEqual(result.log_path.read_text(encoding="utf-8"), "Generating\n")
            self.assertEqual(lines, ["Generating"])
            command = popen.call_args.args[0]
            self.assertEqual(command[:3], ["generate", "--player_files_path", str(players)])
            self.assertIs(popen.call_args.kwargs["stdin"], subprocess.DEVNULL)

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_generation_cancel_terminates_its_process(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); players = root / "players"; players.mkdir()
            process = Mock(returncode=-15)
            process.stdout = ["server listening on 127.0.0.1:38281\n"]
            process.poll.return_value = None
            process.wait.return_value = -15
            popen.return_value = process
            cancel = threading.Event(); cancel.set()
            with self.assertRaises(GenerationCancelled):
                generate_seed(APTools(root, ("generate",), ("server",)), players, root / "out", cancel=cancel)
            process.terminate.assert_called()

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_server_binds_localhost_and_handle_stops_owned_process(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "AP.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("seed.archipelago", b"data")
            process = Mock()
            process.stdout = ["server listening on 127.0.0.1:38281\n"]
            process.stdin = Mock()
            process.poll.return_value = None
            popen.return_value = process
            server = start_server(APTools(root, ("generate",), ("server",)), archive)
            server.stop()
            self.assertEqual(popen.call_args.args[0], ["server", str(archive), "--host", "127.0.0.1", "--port", "38281"])
            process.stdin.write.assert_called_once_with("/exit\n")
            process.terminate.assert_not_called()

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_server_reports_when_graceful_stop_times_out(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "AP.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("seed.archipelago", b"data")
            process = Mock()
            process.stdout = ["server listening on 127.0.0.1:38281\n"]
            process.stdin = Mock()
            process.poll.return_value = None
            process.wait.side_effect = [subprocess.TimeoutExpired("server", 0.01), 0]
            popen.return_value = process
            server = start_server(APTools(root, ("generate",), ("server",)), archive)
            with self.assertRaisesRegex(ValidationError, "forced closed"):
                server.stop(timeout=0.01)
            process.terminate.assert_called_once_with()

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_occupied_local_port_is_refused_before_spawn(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "AP.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("seed.archipelago", b"data")
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            try:
                port = listener.getsockname()[1]
                with self.assertRaisesRegex(ValidationError, "already in use"):
                    start_server(APTools(root, ("generate",), ("server",)), archive, port=port)
            finally:
                listener.close()
            popen.assert_not_called()

    @patch("bb_launcher.local_session.subprocess.Popen")
    def test_server_exit_before_listening_is_not_reported_ready(self, popen):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); archive = root / "AP.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("seed.archipelago", b"data")
            process = Mock()
            process.stdout = ["Hosting game at 127.0.0.1:38281\n"]
            process.poll.return_value = 7
            popen.return_value = process
            with self.assertRaisesRegex(ValidationError, "exited during startup with code 7"):
                start_server(APTools(root, ("generate",), ("server",)), archive)


if __name__ == "__main__":
    unittest.main()
