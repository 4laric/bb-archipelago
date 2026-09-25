from __future__ import annotations

import os
import unittest

from bb_launcher.integrated.path_identity import same_path


class ProcessPathIdentityTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows path semantics")
    def test_windows_slashes_case_and_dot_components(self):
        self.assertTrue(same_path(
            "C:/Games/./shadPS4.exe", "c:\\games\\shadPS4.exe"))
        self.assertFalse(same_path(
            "C:/Games/shadPS4.exe", "C:\\Other\\shadPS4.exe"))

    @unittest.skipIf(os.name == "nt", "POSIX path semantics")
    def test_posix_case_remains_significant(self):
        self.assertFalse(same_path("/games/shadPS4", "/Games/shadPS4"))


if __name__ == "__main__":
    unittest.main()
