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
    GenerationCancelled,
    discover_ap_tools,
    generate_seed,
    start_server,
    validate_bloodborne_world,
)


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

    def test_missing_world_explains_that_installation_is_manual(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValidationError, "Install the bloodborne.apworld"):
                validate_bloodborne_world(tmp)

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
