import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock


TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import weapon_probe_app as app


class FakeMemory:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class CapturePackageTests(unittest.TestCase):
    def capture(self, payload=None, failure=None):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        core = types.SimpleNamespace(
            verify_base=lambda _memory, _base: True,
            capture=(lambda _memory, _base: payload) if failure is None else mock.Mock(side_effect=failure),
        )
        patches = (
            mock.patch.object(app, "output_directory", return_value=Path(temp.name)),
            mock.patch.object(app.importlib, "import_module", return_value=core),
            mock.patch.object(app.windows, "find_shadps4_pid", return_value=123),
            mock.patch.object(app.windows, "ProcessMemory", return_value=FakeMemory()),
            mock.patch.object(app.windows, "resolve_base", return_value=0x500000),
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            path, success, message = app.capture_package("Tonitrus +6; Saw Cleaver +7", "shad_log.txt")
        with zipfile.ZipFile(path) as archive:
            self.assertEqual(["result.json"], archive.namelist())
            record = json.loads(archive.read("result.json"))
        return success, message, record

    def test_captured_payload_is_successful(self):
        success, message, record = self.capture({"status": "captured", "limitations": [], "weapons": []})
        self.assertTrue(success)
        self.assertEqual("Capture completed", message)
        self.assertEqual("captured", record["status"])
        self.assertEqual("pending_review", record["operator_control"]["review_status"])

    def test_incomplete_payload_is_not_reported_as_success(self):
        success, message, record = self.capture({"status": "incomplete", "limitations": ["review"], "weapons": []})
        self.assertFalse(success)
        self.assertIn("not a diagnosis", message)
        self.assertEqual("incomplete", record["status"])
        self.assertNotIn("error", record)

    def test_exception_is_packaged_as_error(self):
        success, message, record = self.capture(failure=ValueError("inventory unavailable"))
        self.assertFalse(success)
        self.assertEqual("inventory unavailable", message)
        self.assertEqual("error", record["status"])
        self.assertEqual("ValueError", record["error"]["type"])


if __name__ == "__main__":
    unittest.main()
