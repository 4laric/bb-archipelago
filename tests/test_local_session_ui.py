import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bb_launcher.core import ValidationError
from bb_launcher.local_session_ui import LocalSessionPanel, write_solo_player


class LocalSessionUiTests(unittest.TestCase):
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

    def test_close_does_not_stop_server_without_user_choice(self):
        app = SimpleNamespace(_busy=False, messagebox=Mock(), root=Mock())
        app.messagebox.askyesno.return_value = False
        panel = SimpleNamespace(app=app, host=SimpleNamespace(running=True), _stop=Mock())
        LocalSessionPanel._close(panel)
        panel._stop.assert_not_called()
        app.root.destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
