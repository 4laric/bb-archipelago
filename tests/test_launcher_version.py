import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bb_launcher.version import launcher_version


class LauncherVersionTests(unittest.TestCase):
    def test_packaged_release_preserves_prerelease_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "version-metadata.json").write_text(json.dumps({
                "product_version": "0.1.0-enemizer-ai.1",
                "file_version": "0.1.0.0",
            }), encoding="utf-8")
            with patch("sys.frozen", True, create=True), patch(
                "bb_launcher.version.resource_root", return_value=root
            ):
                self.assertEqual(launcher_version(), "0.1.0-enemizer-ai.1")
                (root / "version-metadata.json").write_text("broken", encoding="utf-8")
                self.assertEqual(launcher_version(), "packaged (release metadata unavailable)")

    def test_source_checkout_is_explicit(self):
        with patch("sys.frozen", False, create=True):
            self.assertEqual(launcher_version(), "source checkout")
