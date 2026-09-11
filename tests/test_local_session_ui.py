import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bb_launcher.core import ValidationError
from bb_launcher.local_session import BloodborneWorldUnavailable
from bb_launcher.local_session_ui import LocalSessionPanel, write_solo_player
from bb_launcher.workflow import check_seed_slot_identity, read_ap_identity_lock, WorkflowError


def install_panel(install_root=None):
    """A headless panel with just the world-install collaborators wired."""
    app = SimpleNamespace(_busy=False, _append_log=Mock(), messagebox=Mock(), root=Mock())
    panel = SimpleNamespace(
        app=app, status=Mock(), install_label=Mock(), install_button=Mock(),
        _install_root=install_root, _generate=Mock(), _error=Mock(),
    )
    # The real disarm, so "the button cannot install twice" is proven, not staged.
    panel._clear_world_install = lambda: LocalSessionPanel._clear_world_install(panel)
    return panel


class LocalSessionUiTests(unittest.TestCase):
    def test_new_local_host_rebinds_only_after_start_and_preserves_other_sessions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            address = "127.0.0.1:38281"
            check_seed_slot_identity(root, server=address, seed="old", slot="OldHunter")
            check_seed_slot_identity(root, server="remote:1234", seed="remote", slot="Other")
            ledger = root / "sessions" / "old" / "ledger.json"
            ledger.parent.mkdir(parents=True)
            ledger.write_text('old-delivery-history', encoding="utf-8")
            app = SimpleNamespace(_busy=False, fields={"ap_request": Mock(get=lambda: "new.zip")},
                _state_root=lambda: root, player_name=Mock(get=lambda: "NewHunter"),
                _set_busy=Mock(), _progress_message=Mock(), root=Mock())
            panel = SimpleNamespace(app=app, host=None, _tools=Mock(), port=Mock(get=lambda: "38281"),
                _save=Mock(), _error=Mock(), _host_failed=Mock(), _host_started=Mock())
            server = Mock()
            def start(*args, **kwargs):
                self.assertEqual(read_ap_identity_lock(root, address), {"seed":"old", "slot":"OldHunter"})
                return server
            with patch("bb_launcher.local_session_ui._request_identity", return_value={"seed":"new", "slot":"NewHunter"}), patch(
                "bb_launcher.local_session_ui.start_server", side_effect=start
            ), patch("bb_launcher.local_session_ui.threading.Thread", side_effect=lambda **kw: SimpleNamespace(start=kw["target"])):
                LocalSessionPanel._host_selected(panel)
            check_seed_slot_identity(root, server=address, seed="new", slot="NewHunter")
            with self.assertRaises(WorkflowError):
                check_seed_slot_identity(root, server=address, seed="old", slot="OldHunter")
            self.assertEqual(read_ap_identity_lock(root, "remote:1234"), {"seed":"remote", "slot":"Other"})
            self.assertEqual(ledger.read_text(), 'old-delivery-history')
            server.stop.assert_not_called()
            self.assertEqual(app.root.after.call_args.args, (0, panel._host_started, server, 38281))

    def test_failed_local_host_does_not_rebind_address(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            address = "127.0.0.1:38281"
            check_seed_slot_identity(root, server=address, seed="old", slot="Hunter")
            app = SimpleNamespace(_busy=False, fields={"ap_request": Mock(get=lambda: "new.zip")},
                _state_root=lambda: root, player_name=Mock(get=lambda: "Hunter"),
                _set_busy=Mock(), _progress_message=Mock(), root=Mock())
            panel = SimpleNamespace(app=app, host=None, _tools=Mock(), port=Mock(get=lambda: "38281"),
                _save=Mock(), _error=Mock(), _host_failed=Mock(), _host_started=Mock())
            with patch("bb_launcher.local_session_ui._request_identity", return_value={"seed":"new", "slot":"Hunter"}), patch(
                "bb_launcher.local_session_ui.start_server", side_effect=ValidationError("port occupied")
            ), patch("bb_launcher.local_session_ui.threading.Thread", side_effect=lambda **kw: SimpleNamespace(start=kw["target"])):
                LocalSessionPanel._host_selected(panel)
            self.assertEqual(read_ap_identity_lock(root, address), {"seed":"old", "slot":"Hunter"})
            self.assertEqual(app.root.after.call_args.args, (0, panel._host_failed, "port occupied"))

    def test_solo_yaml_preserves_name_and_dlc_choice(self):
        # write_solo_player emits YAML by hand (see its docstring comment) so the
        # launcher does not depend on PyYAML, which the frozen build may lack.
        # Parse it back the same minimal way rather than importing yaml here.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = write_solo_player(root, 'A: "Hunter"', False)
            text = (first / 'Bloodborne.yaml').read_text(encoding='utf-8')
            lines = text.splitlines()
            self.assertEqual('name: "A: \\"Hunter\\""', lines[0])
            name = json.loads(lines[0][len('name: '):])
            self.assertEqual('A: "Hunter"', name)
            self.assertEqual('game: Bloodborne', lines[1])
            self.assertEqual('Bloodborne:', lines[2])
            self.assertEqual('  include_dlc: false', lines[3])
            second = write_solo_player(root, 'Hunter', True)
            self.assertNotEqual(first, second)

    def test_invalid_player_name_creates_no_input(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sentinel = root / "sentinel.txt"
            sentinel.write_text("untouched", encoding="utf-8")
            for name in ('', 'x' * 17, 'Hunter\nOther'):
                with self.assertRaises(ValidationError):
                    write_solo_player(root, name, False)
            self.assertEqual([sentinel], list(root.iterdir()),
                              "witness: no player directory was created")

    def test_generated_seed_flows_into_play_without_manual_path_entry(self):
        app = SimpleNamespace(_set_busy=Mock(), _accept_ap_request=Mock(), fields={'ap_request': Mock()},
                              notebook=Mock(), play_tab='play')
        panel = SimpleNamespace(app=app, cancel_button=Mock(), status=Mock(), _host_selected=Mock())
        with patch('bb_launcher.local_session_ui.archive_slots', return_value=[('seed.bbseed.json', 'Hunter')]):
            LocalSessionPanel._generated(panel, Path('AP_seed.zip'), False)
        app.fields['ap_request'].set.assert_called_once_with('AP_seed.zip')
        app._accept_ap_request.assert_called_once_with('AP_seed.zip')
        app.notebook.select.assert_called_once_with('play')
        panel._host_selected.assert_not_called()

    def test_auto_host_occurs_after_seed_is_selected(self):
        events = []
        app = SimpleNamespace(_set_busy=Mock(), _accept_ap_request=lambda p: events.append(('seed', p)), fields={'ap_request': Mock()},
                              notebook=Mock(), play_tab='play')
        panel = SimpleNamespace(app=app, cancel_button=Mock(), status=Mock(),
                                _host_selected=lambda: events.append(('host', None)))
        with patch('bb_launcher.local_session_ui.archive_slots', return_value=[('seed.bbseed.json', 'Hunter')]):
            LocalSessionPanel._generated(panel, Path('AP_seed.zip'), True)
        self.assertEqual(events, [('seed', 'AP_seed.zip'), ('host', None)])

    def test_invalid_generated_zip_cannot_host_previously_selected_seed(self):
        app = SimpleNamespace(_set_busy=Mock(), _accept_ap_request=Mock(), fields={'ap_request': Mock()})
        panel = SimpleNamespace(app=app, cancel_button=Mock(), _error=Mock(), _host_selected=Mock())
        with patch('bb_launcher.local_session_ui.archive_slots', side_effect=ValidationError('no Bloodborne player')):
            LocalSessionPanel._generated(panel, Path('bad.zip'), True)
        panel._host_selected.assert_not_called()
        app.fields['ap_request'].set.assert_not_called()

    def test_missing_world_arms_an_install_button_and_installs_nothing_yet(self):
        panel = install_panel()
        error = BloodborneWorldUnavailable("no Bloodborne world.", reason="missing",
                                           expected_version="0.1.0")
        with patch("bb_launcher.local_session_ui.install_bloodborne_world") as install:
            LocalSessionPanel._offer_world_install(panel, Path("C:/Archipelago"), error)
        install.assert_not_called()
        panel.install_label.set.assert_called_once_with("Install Bloodborne world")
        panel.install_button.configure.assert_called_once_with(state="normal")
        self.assertEqual(Path("C:/Archipelago"), panel._install_root)
        message = panel.status.set.call_args.args[0]
        self.assertIn("no Bloodborne world.", message)
        self.assertIn("close and reopen it", message, "the restart warning is shown")

    def test_version_mismatch_offers_an_update_naming_the_version(self):
        panel = install_panel()
        error = BloodborneWorldUnavailable("wrong version.", reason="mismatch",
                                           expected_version="0.2.0", installed_version="0.1.0")
        LocalSessionPanel._offer_world_install(panel, Path("C:/Archipelago"), error)
        panel.install_label.set.assert_called_once_with("Update Bloodborne world to 0.2.0")

    def test_one_click_installs_once_and_re_runs_the_original_request(self):
        panel = install_panel(install_root=Path("C:/Archipelago"))
        installed = Path("C:/Archipelago/custom_worlds/bloodborne.apworld")
        with patch("bb_launcher.local_session_ui.install_bloodborne_world",
                   return_value=installed) as install:
            LocalSessionPanel._install_world(panel)
            install.assert_called_once_with(Path("C:/Archipelago"))
            panel._generate.assert_called_once_with()
            # The button is disarmed, so a second click cannot install again.
            panel.install_button.configure.assert_called_once_with(state="disabled")
            self.assertIsNone(panel._install_root)
            LocalSessionPanel._install_world(panel)
            install.assert_called_once_with(Path("C:/Archipelago"))
        self.assertIn("close and reopen it", panel.status.set.call_args.args[0])

    def test_a_failed_install_does_not_pretend_the_world_is_ready(self):
        panel = install_panel(install_root=Path("C:/Archipelago"))
        with patch("bb_launcher.local_session_ui.install_bloodborne_world",
                   side_effect=ValidationError("source install")):
            LocalSessionPanel._install_world(panel)
        panel._error.assert_called_once_with("source install")
        panel._generate.assert_not_called()
        self.assertEqual(Path("C:/Archipelago"), panel._install_root,
                         "witness: the button stays armed for a retry")

    def test_close_does_not_stop_server_without_user_choice(self):
        app = SimpleNamespace(_busy=False, messagebox=Mock(), root=Mock())
        app.messagebox.askyesno.return_value = False
        panel = SimpleNamespace(app=app, host=SimpleNamespace(running=True), _stop=Mock())
        LocalSessionPanel._close(panel)
        panel._stop.assert_not_called()
        app.root.destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
