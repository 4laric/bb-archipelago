from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bb_launcher.core import GameInstall, ValidationError
from bb_launcher.workflow import _validate_suppression

from test_launcher_doctor import PLAN_HASH, DoctorFixture


class LauncherWorkflowTests(unittest.TestCase):
    def test_source_hash_mismatch_names_the_installed_path(self):
        # bb-archipelago#104: the opaque "does not match the installed game"
        # cost a full build cycle; the error must name the file it hashed.
        with tempfile.TemporaryDirectory() as tmp:
            fixture = DoctorFixture(Path(tmp))
            fixture.gameparam.write_bytes(b"modified after the binder was built")
            install = GameInstall.from_root(fixture.root / "game")
            with self.assertRaises(ValidationError) as raised:
                _validate_suppression(
                    install, fixture.binder, fixture.manifest_path, PLAN_HASH
                )
            message = str(raised.exception)
            self.assertIn(str(fixture.gameparam), message)
            self.assertIn("build.ps1 -Package -GameRoot", message)


if __name__ == "__main__":
    unittest.main()
