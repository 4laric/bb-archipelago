from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bb_launcher.integrated.path_identity import same_path


class ProcessPathIdentityTests(unittest.TestCase):
    @patch("bb_launcher.integrated.path_identity.os", SimpleNamespace(name="nt"))
    def test_windows_slashes_case_and_dot_components(self):
        self.assertTrue(same_path(
            "C:/Games/./shadPS4.exe", "c:\\games\\shadPS4.exe"))
        self.assertFalse(same_path(
            "C:/Games/shadPS4.exe", "C:\\Other\\shadPS4.exe"))

    @patch("bb_launcher.integrated.path_identity.os", SimpleNamespace(name="posix"))
    def test_posix_case_remains_significant(self):
        self.assertFalse(same_path("/games/shadPS4", "/Games/shadPS4"))


if __name__ == "__main__":
    unittest.main()
