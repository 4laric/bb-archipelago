"""All production DarkScript calls must use locale-independent numbers."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_boss_canary import compile_events
from tools.build_cathedral_emevd import run_compiler


class DarkScriptLocaleTests(unittest.TestCase):
    def test_both_wrappers_override_child_culture_without_changing_parent(self):
        inherited = {
            "DOTNET_SYSTEM_GLOBALIZATION_INVARIANT": "0",
            "DOTNET_SYSTEM_GLOBALIZATION_PREDEFINED_CULTURES_ONLY": "1",
            "PATH": "preserve-this-path",
        }
        with patch.dict(os.environ, inherited), tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "source", root / "output"
            output.mkdir()
            expected = "m33_00_00_00.emevd.dcx.js"
            (output / expected).write_text("compiled witness", encoding="utf-8")
            for wrapper in ("cathedral", "boss"):
                for mode in ("decompile", "compile"):
                    with self.subTest(wrapper=wrapper, mode=mode), patch(
                        "subprocess.run",
                        return_value=subprocess.CompletedProcess([], 0, b"", b""),
                    ) as run:
                        if wrapper == "cathedral":
                            run_compiler(Path("DarkScript3.exe"), mode, source, output)
                        else:
                            compile_events(Path("DarkScript3.exe"), mode, source, output, expected)
                        run.assert_called_once()
                        child = run.call_args.kwargs["env"]
                        self.assertEqual("1", child["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"])
                        self.assertEqual("0", child["DOTNET_SYSTEM_GLOBALIZATION_PREDEFINED_CULTURES_ONLY"])
                        self.assertEqual(inherited["PATH"], child["PATH"])
                        self.assertIn("-" + mode, run.call_args.args[0])
                        self.assertEqual(inherited, {key: os.environ[key] for key in inherited})
