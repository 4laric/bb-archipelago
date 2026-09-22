"""Report a native startup refusal as failure, not a successful connection."""
import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bb_launcher.cli import main
from bb_launcher.core import EarlyExit


class ExternalCliTests(unittest.TestCase):
    def test_verify_passes_selected_player_name(self):
        result = SimpleNamespace(activation_fingerprint="a" * 64)
        output = io.StringIO()
        with patch("bb_launcher.cli._json_file", return_value={}), \
             patch("bb_launcher.cli.LauncherSettings.from_dict"), \
             patch("bb_launcher.external_workflow.verify_before_boot",
                   return_value=result) as verify, \
             contextlib.redirect_stdout(output):
            status = main([
                "bblauncher-verify", "--settings", "settings.json",
                "--player-name", "Hunter Two",
            ])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue())["activation_fingerprint"], "a" * 64)
        self.assertEqual(verify.call_args.kwargs["player_name"], "Hunter Two")

    def test_native_early_exit_is_a_failed_command_with_diagnostic(self):
        result = SimpleNamespace(
            client_log=Path("client.log"), process_ids=(42,),
            early_exit=EarlyExit("AP client", 1, Path("client.log"),
                                 "External activation changed; restart the game"),
        )
        output = io.StringIO()
        with patch("bb_launcher.cli._json_file", return_value={}), \
             patch("bb_launcher.cli.LauncherSettings.from_dict"), \
             patch("bb_launcher.external_workflow.connect_external", return_value=result), \
             contextlib.redirect_stdout(output):
            status = main(["bblauncher-connect", "--settings", "settings.json"])
        self.assertEqual(status, 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report["status"], "client failed to start")
        self.assertIn("External activation changed", report["message"])


if __name__ == "__main__":
    unittest.main()
