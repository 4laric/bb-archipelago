import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bb_launcher.core import ValidationError
from bb_launcher.local_session import BloodborneWorldUnavailable
from bb_launcher.local_session_ui import LocalSessionPanel, write_solo_player


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


class PlayerFolderPickerTests(unittest.TestCase):
    """The picker opens where Archipelago actually keeps player YAML files."""

    def panel(self, ap_root, players=""):
        return SimpleNamespace(
            app=SimpleNamespace(filedialog=Mock()),
            ap_root=SimpleNamespace(get=lambda: str(ap_root)),
            players=Mock(get=Mock(return_value=players)),
            use_folder=Mock(get=Mock(return_value=True)),
        )

    def bind(self, panel):
        panel._players_directory = lambda: LocalSessionPanel._players_directory(panel)
        panel._players_initialdir = lambda: LocalSessionPanel._players_initialdir(panel)
        return panel

    def test_the_picker_opens_in_the_installs_players_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Archipelago capitalises this folder by convention only.
            (root / "players" / "Templates").mkdir(parents=True)
            panel = self.bind(self.panel(root))
            panel.app.filedialog.askdirectory.return_value = ""
            LocalSessionPanel._browse_players(panel)
            self.assertEqual(str(root / "players"),
                             panel.app.filedialog.askdirectory.call_args.kwargs["initialdir"])

    def test_without_a_players_folder_the_picker_falls_back(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            panel = self.bind(self.panel(root, players=str(root / "elsewhere")))
            panel.app.filedialog.askdirectory.return_value = ""
            LocalSessionPanel._browse_players(panel)
            self.assertEqual(str(root / "elsewhere"),
                             panel.app.filedialog.askdirectory.call_args.kwargs["initialdir"])
            # With nothing typed in the field either, the install root itself.
            panel.players.get.return_value = ""
            LocalSessionPanel._browse_players(panel)
            self.assertEqual(str(root),
                             panel.app.filedialog.askdirectory.call_args.kwargs["initialdir"])

    def test_ticking_the_box_prefills_the_players_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Players").mkdir()
            panel = self.bind(self.panel(root))
            panel._prefill_players = lambda: LocalSessionPanel._prefill_players(panel)
            panel._prefill_players()
            panel.players.set.assert_called_once_with(str(root / "Players"))
            # A folder the player already chose is never overwritten.
            panel.players.set.reset_mock()
            panel.players.get.return_value = str(root / "mine")
            panel._prefill_players()
            panel.players.set.assert_not_called()

    def test_no_prefill_without_an_install_or_a_players_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            panel = self.bind(self.panel(Path(temporary)))
            panel._prefill_players = lambda: LocalSessionPanel._prefill_players(panel)
            panel._prefill_players()
            panel.players.set.assert_not_called()

    def test_settings_round_trip_still_carries_the_chosen_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "local-session-settings.json"
            panel = SimpleNamespace(
                config_path=config,
                **{key: Mock(get=Mock(return_value=key.upper())) for key in
                   ("ap_root", "python", "name", "players", "port")})
            LocalSessionPanel._save(panel)
            self.assertEqual("PLAYERS", json.loads(config.read_text(encoding="utf-8"))["players"])
            LocalSessionPanel._load(panel)
            panel.players.set.assert_called_once_with("PLAYERS")


class PlayerFolderValidationTests(unittest.TestCase):
    """A bad folder is refused with words, not with Archipelago's traceback."""

    def manifest_root(self, near):
        """A stand-in resource root holding the bundled world manifest."""
        root = near / "resources"
        world = root / "worlds" / "bloodborne"
        world.mkdir(parents=True, exist_ok=True)
        (world / "archipelago.json").write_text('{"game": "Bloodborne"}', encoding="utf-8")
        return root

    def generating_panel(self, players):
        app = SimpleNamespace(
            _busy=False, _append_log=Mock(), _state_root=Mock(return_value=Path("state")),
            _progress_message=Mock(), _set_busy=Mock(), root=Mock())
        return SimpleNamespace(
            app=app, host=None, status=Mock(), cancel=Mock(), cancel_button=Mock(),
            players=Mock(get=Mock(return_value=str(players))),
            use_folder=Mock(get=Mock(return_value=True)),
            auto_host=Mock(get=Mock(return_value=False)),
            _tools=Mock(return_value=SimpleNamespace(root=Path("C:/Archipelago"))),
            _save=Mock(), _error=Mock(), _clear_world_install=Mock(), _offer_world_install=Mock(),
        )

    def test_generation_is_refused_before_archipelago_ever_runs(self):
        with tempfile.TemporaryDirectory() as temporary:
            players = Path(temporary)
            (players / "Player-EldenRing.yaml").write_text("name: Tarnished\n", encoding="utf-8")
            panel = self.generating_panel(players)
            with patch("bb_launcher.local_session_ui.validate_bloodborne_world"), \
                 patch("bb_launcher.local_session_ui.resource_root",
                       return_value=self.manifest_root(players)), \
                 patch("bb_launcher.local_session_ui.generate_seed") as generate:
                LocalSessionPanel._generate(panel)
            generate.assert_not_called()
            panel._error.assert_called_once()
            self.assertIn('no top-level "game" key', panel._error.call_args.args[0])

    def test_a_folder_with_no_bloodborne_player_warns_but_generates(self):
        with tempfile.TemporaryDirectory() as temporary:
            players = Path(temporary)
            (players / "Other.yaml").write_text("name: T\ngame: Elden Ring\n", encoding="utf-8")
            panel = self.generating_panel(players)
            with patch("bb_launcher.local_session_ui.validate_bloodborne_world"), \
                 patch("bb_launcher.local_session_ui.resource_root",
                       return_value=self.manifest_root(players)), \
                 patch("bb_launcher.local_session_ui.threading.Thread") as thread:
                LocalSessionPanel._generate(panel)
            panel._error.assert_not_called()
            thread.assert_called_once()
            self.assertIn("no player YAML", panel.app._append_log.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
