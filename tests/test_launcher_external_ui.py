from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bb_launcher.external_ui import BBLauncherPanel


class Value:
    def __init__(self, value=""):
        self.value = value
    def get(self):
        return self.value
    def set(self, value):
        self.value = value


class Button:
    def configure(self, **kwargs):
        self.state = kwargs["state"]


class CompanionPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name) / "record.json"
        self.record.write_text(json.dumps({"package_name": "Archipelago-Alice-example"}))
        self.panel = BBLauncherPanel.__new__(BBLauncherPanel)
        self.panel.app = SimpleNamespace(_busy=False, fields={key: Value("configured") for key in
            ("ap_request", "game_root", "shad_executable")})
        for key in ("executable", "mods", "receipt", "guidance", "prepared"):
            setattr(self.panel, key, Value())
        self.panel.buttons = {action: Button() for action in ("export", "verify", "connect")}
        self.validation = patch("bb_launcher.external_setup.setup_problem", return_value=None)
        self.validation.start()
        self.addCleanup(self.validation.stop)

    def test_first_run_offers_build_but_no_unusable_followup_actions(self):
        self.panel.update_setup()
        self.assertEqual(self.panel.buttons["export"].state, "normal")
        self.assertEqual(self.panel.buttons["verify"].state, "disabled")
        self.assertEqual(self.panel.buttons["connect"].state, "disabled")
        self.assertIn("No mod prepared", self.panel.prepared.get())

    def test_remembered_mod_shows_name_and_busy_disables_all_actions(self):
        self.panel.receipt.set(str(self.record))
        with patch("bb_launcher.external.load_external_receipt", return_value=SimpleNamespace(package_name="Archipelago-Alice-example")):
            self.panel.update_setup()
        self.assertIn("Archipelago-Alice-example", self.panel.prepared.get())
        self.assertEqual(self.panel.buttons["verify"].state, "normal")
        self.panel.app._busy = True
        self.panel.update_setup()
        self.assertEqual({key: button.state for key, button in self.panel.buttons.items()},
                         {"export": "disabled", "verify": "disabled", "connect": "disabled"})

    def test_missing_record_offers_rebuild(self):
        self.panel.receipt.set(str(self.record.with_name("gone.json")))
        self.panel.update_setup()
        self.assertIn("Build your mod again", self.panel.prepared.get())
        self.assertEqual(self.panel.buttons["verify"].state, "disabled")
        self.assertEqual(self.panel.buttons["export"].state, "normal")

    def test_missing_seed_directs_player_to_play_tab(self):
        self.panel.app.fields["ap_request"].set("")
        self.panel.update_setup()
        self.assertIn("In Play, choose a seed", self.panel.guidance.get())
        self.assertEqual(self.panel.buttons["export"].state, "disabled")

    def test_failed_action_clears_old_ready_status(self):
        self.panel.connected_receipt_id = "old"
        self.panel.connected_fingerprint = "old"
        self.panel.app.client_health = Value("Ready")
        status = Value("Ready")
        self.panel.app._set_status_text = status.set
        failures = []
        self.panel.app._action_failed = lambda action, exc: failures.append(action)
        self.panel.failed("verify", RuntimeError("mod changed"))
        self.assertIsNone(self.panel.connected_receipt_id)
        self.assertIsNone(self.panel.connected_fingerprint)
        self.assertIn("Not connected", self.panel.app.client_health.get())
        self.assertIn("mod changed", status.get())
        self.assertEqual(failures, ["BBLauncher verify"])

    def test_json_name_alone_does_not_enable_verify(self):
        self.panel.receipt.set(str(self.record))
        self.panel.update_setup()
        self.assertEqual(self.panel.buttons["verify"].state, "disabled")
        self.assertIn("Build your mod again", self.panel.prepared.get())

    def test_existing_export_offers_replacement_instead_of_a_dead_end(self):
        from bb_launcher.external import ExternalPackageExists
        app = self.panel.app
        app.messagebox = SimpleNamespace(askyesno=lambda *a, **k: True)
        app.root = None
        app.client_health = Value()
        logged, shown, busy = [], [], []
        app._append_log = logged.append
        app._set_status_text = shown.append
        app._set_busy = busy.append
        app._action_failed = lambda *a: self.fail("a replaceable export must not be reported as a failure")
        started = []
        self.panel.start = lambda action, **kw: started.append((action, kw))
        self.panel.failed("export", ExternalPackageExists(Path("Mods/Archipelago-Alice-abc")))
        self.assertEqual(busy, [False])
        self.assertEqual(started, [("export", {"replace_existing": True})])
        self.assertIn("already exists", logged[0])

    def test_declining_replacement_keeps_the_existing_export(self):
        from bb_launcher.external import ExternalPackageExists
        app = self.panel.app
        app.messagebox = SimpleNamespace(askyesno=lambda *a, **k: False)
        app.root = None
        app.client_health = Value()
        shown, busy = [], []
        app._append_log = lambda _m: None
        app._set_status_text = shown.append
        app._set_busy = busy.append
        self.panel.start = lambda *a, **k: self.fail("declining must not rebuild")
        self.panel.failed("export", ExternalPackageExists(Path("Mods/Archipelago-Alice-abc")))
        self.assertIn("Kept the existing", shown[0])
        self.assertIn("kept", app.client_health.get())

    def test_verify_step_is_named_consistently_everywhere(self):
        """The workflow's refusals tell the player which button to press; the
        button must exist under that exact name (it was 'Check activated mod')."""
        root = Path(__file__).resolve().parents[1]
        ui = (root / "bb_launcher" / "external_ui.py").read_text(encoding="utf-8")
        workflow = (root / "bb_launcher" / "external_workflow.py").read_text(encoding="utf-8")
        doc = (root / "docs" / "BBLAUNCHER.md").read_text(encoding="utf-8")
        self.assertIn('"Verify activated mod"', ui)
        self.assertIn("Verify activated mod", workflow)
        self.assertIn("**Verify activated mod**", doc)
        for text in (ui, workflow, doc):
            self.assertNotIn("Check activated mod", text)

    def test_no_record_clears_stale_ready_label(self):
        self.panel.app.client_health = Value("Ready")
        self.panel.app._set_status_text = lambda message: None
        self.panel.refresh_status(SimpleNamespace(bblauncher_receipt=None))
        self.assertEqual(self.panel.app.client_health.get(), "BBLauncher: no prepared mod selected.")
