from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bb_launcher.external import ACTIVE_MODS_DIR_NAME
from bb_launcher.external_setup import setup_problem, suggest_mods_directory


class ExternalSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.executable = self.root / "BB_Launcher.exe"
        self.executable.write_bytes(b"fixture launcher")
        self.inactive = self.root / "BBLauncher" / "Mods"
        self.inactive.mkdir(parents=True)
        self.game = self.root / "install" / "CUSA03173"
        self.game.mkdir(parents=True)
        self.overlay = self.game.with_name("CUSA03173-mods")
        self.overlay.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def snapshot(self):
        return tuple(sorted(
            (path.relative_to(self.root).as_posix(),
             "directory" if path.is_dir() else path.read_bytes())
            for path in self.root.rglob("*")
        ))

    def test_suggestion_matches_bblauncher_layout_without_creating_it(self):
        before = self.snapshot()
        suggestion = suggest_mods_directory(self.executable)
        self.assertEqual(suggestion, self.inactive)
        self.assertEqual(self.snapshot(), before)

    def test_default_and_explicit_custom_inactive_libraries_are_valid(self):
        custom = self.root / "custom-library"
        custom.mkdir()
        candidates = (self.inactive, custom)
        self.assertEqual(len(candidates), 2)
        for candidate in candidates:
            with self.subTest(candidate=candidate):
                self.assertIsNone(setup_problem(self.executable, candidate, self.game))

    def test_missing_app_and_library_have_actionable_guidance(self):
        without_app = setup_problem(None, None, self.game)
        self.assertIn("Choose BB_Launcher.exe first", without_app)
        missing_app = setup_problem(self.root / "missing.exe", self.inactive, self.game)
        self.assertIn("BBLauncher app was not found", missing_app)
        missing_library = setup_problem(
            self.executable, self.root / "missing-library", self.game
        )
        self.assertIn(str(self.inactive), missing_library)
        self.assertIn("start BBLauncher once", missing_library)

    def test_game_overlay_and_its_parent_are_rejected_as_live_output(self):
        selections = (self.overlay, self.overlay / "dvdroot_ps4", self.game.parent)
        self.assertEqual(len(selections), 3)
        for selection in selections:
            with self.subTest(selection=selection):
                problem = setup_problem(self.executable, selection, self.game)
                self.assertIn("game's live CUSA03173-mods overlay", problem)
                self.assertIn(str(self.inactive), problem)

    def test_active_directory_and_packages_are_rejected(self):
        active = self.root / "BBLauncher" / ACTIVE_MODS_DIR_NAME
        active.mkdir()
        selections = (active, active / "Some Package", active / "Some Package" / "Mods")
        self.assertEqual(len(selections), 3)
        for selection in selections:
            with self.subTest(selection=selection):
                problem = setup_problem(self.executable, selection, self.game)
                self.assertIn("active package area", problem)
                self.assertIn(str(self.inactive), problem)

    def test_malformed_paths_return_guidance_instead_of_raising(self):
        bad = Path("invalid\0path")
        app_problem = setup_problem(bad, self.inactive, self.game)
        mods_problem = setup_problem(self.executable, bad, self.game)
        self.assertIsInstance(app_problem, str)
        self.assertIn("BBLauncher app", app_problem)
        self.assertIsInstance(mods_problem, str)
        self.assertIn("inactive mod library", mods_problem)

    def test_validation_never_changes_bblauncher_or_game_files(self):
        settings = self.root / "BBLauncher" / "LauncherSettings.toml"
        settings.write_bytes(b'[Launcher]\ninstallPath = "fixture"\n')
        installed = self.overlay / "existing.bin"
        installed.write_bytes(b"game overlay")
        before = self.snapshot()
        self.assertIsNone(setup_problem(self.executable, self.inactive, self.game))
        self.assertIsNotNone(setup_problem(self.executable, self.overlay, self.game))
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
