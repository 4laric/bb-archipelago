import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tools.audit_enemizer_seeds import main


class SeedAuditTests(unittest.TestCase):
    def test_failed_writer_and_bad_output_hash_are_retained_and_fail_batch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = []
            for name in ("dotnet", "writer", "inventory", "gameparam", "paramdef", "scripts"):
                source = root / name
                source.write_bytes(b"fixture")
                args += [f"--{name}", str(source)]
            output = root / "audit"
            args += ["--output", str(output), "--count", "2"]

            def make_plan(arguments):
                Path(arguments[-1]).write_text(json.dumps({"swaps": [{
                    "destination_keys": ["m24_01_00_00:c1000", "m24_01_00_11:c1000"],
                    "target": {"think_param_id": 42},
                }]}), encoding="utf-8")
                return 0

            def writer(command, **kwargs):
                destination = Path(command[-2])
                if destination.name == "scripts-0":
                    return SimpleNamespace(returncode=1, stdout="", stderr="missing dependency")
                destination.mkdir()
                (destination / "map.luabnd.dcx").write_bytes(b"changed")
                Path(str(destination) + ".json").write_text(json.dumps({"maps": [{
                    "map": "map.luabnd.dcx", "output_sha256": "incorrect",
                    "missing_goals_after": 0, "scripts_added": [],
                }]}), encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="written", stderr="")

            with patch("tools.audit_enemizer_seeds.plan", side_effect=make_plan), patch(
                "tools.audit_enemizer_seeds.subprocess.run", side_effect=writer
            ) as run:
                self.assertEqual(main(args), 1)
                self.assertEqual(run.call_count, 2)
                with self.assertRaises(FileExistsError):
                    main(args)
            summary = json.loads((output / "summary.json").read_text())
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["map_think_pairs"], 1)
            self.assertEqual([s["passed"] for s in summary["seeds"]], [False, False])
            self.assertIn("missing dependency", (output / "writer-0.log").read_text())
