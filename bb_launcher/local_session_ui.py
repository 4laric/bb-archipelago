"""Guided seed generation and launcher-owned local hosting."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from .core import ValidationError
from .local_session import (
    RESTART_NOTICE,
    BloodborneWorldUnavailable,
    discover_ap_tools,
    generate_seed,
    install_bloodborne_world,
    start_server,
    validate_bloodborne_world,
)
from .resources import resource_root
from .seed_request import archive_slots
from .workflow import _request_identity, check_seed_slot_identity


def write_solo_player(root: Path, name: str, include_dlc: bool) -> Path:
    name = name.strip()
    if not name or len(name) > 16 or any(ord(char) < 32 for char in name):
        raise ValidationError("Choose a player name of 1–16 characters, without line breaks.")
    folder = root / "player-inputs" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    # JSON strings are valid YAML scalars, including quotes and colons in names.
    (folder / "Bloodborne.yaml").write_text(
        f"name: {json.dumps(name)}\ngame: Bloodborne\nBloodborne:\n"
        f"  include_dlc: {str(include_dlc).lower()}\n", encoding="utf-8",
    )
    return folder


class LocalSessionPanel:
    def __init__(self, app, notebook):
        self.app = app
        tk, ttk = app.tk, app.ttk
        self.host = None
        self.cancel = threading.Event()
        self.generating = False
        self.config_path = app.settings_path.parent / "local-session-settings.json"
        self.ap_root = tk.StringVar(value=str(Path.home() / "Archipelago"))
        self.python = tk.StringVar()
        self.name = tk.StringVar(value="Hunter")
        self.players = tk.StringVar()
        self.use_folder = tk.BooleanVar(value=False)
        self.include_dlc = tk.BooleanVar(value=False)
        self.auto_host = tk.BooleanVar(value=True)
        self.port = tk.StringVar(value="38281")
        self.status = tk.StringVar(value="Create a solo seed, or use a folder of player YAML files.")
        # Installing the world is never automatic: the button appears only
        # after a validation failure names it, and one click does exactly one
        # install and then re-validates.
        self.install_label = tk.StringVar(value="Install Bloodborne world")
        self._install_root = None
        self._load()
        from .theme import field, option, page_header, scroll_page, section
        host_frame = ttk.Frame(notebook)
        notebook.insert(1, host_frame, text="Create & host")
        frame = scroll_page(tk, ttk, host_frame)
        row = page_header(ttk, frame, "Create & host", "Generate a seed on this PC and host it for yourself.")
        row = section(ttk, frame, row, "Your game", first=True)
        field(ttk, frame, row, "Player name", self.name)
        option(ttk, frame, row + 1, "Include The Old Hunters DLC", self.include_dlc)
        row = section(ttk, frame, row + 2, "Multiworld")
        option(ttk, frame, row, "Use existing player YAML files", self.use_folder,
               caption="Bring your own player files instead of a solo seed.")
        field(ttk, frame, row + 1, "YAML folder", self.players, browse=self._browse_players)
        row = section(ttk, frame, row + 2, "Local server")
        option(ttk, frame, row, "Start the server after generation", self.auto_host)
        field(ttk, frame, row + 1, "Port", self.port, trailing="this PC only")
        row = section(ttk, frame, row + 2, "Archipelago install")
        field(ttk, frame, row, "Archipelago folder", self.ap_root, browse=self._browse_root)
        field(ttk, frame, row + 1, "Python", self.python, browse=self._browse_python)
        ttk.Label(frame, text="Only for a source checkout of Archipelago.", style="Dim.TLabel").grid(
            row=row + 2, column=1, sticky="w", pady=(0, 4))
        actions = ttk.Frame(frame)
        actions.grid(row=row + 3, column=0, columnspan=3, sticky="ew", pady=(18, 6))
        self.create = ttk.Button(actions, text="Create seed", command=self._generate, style="Accent.TButton")
        self.create.pack(side="left")
        self.host_button = ttk.Button(actions, text="Host selected seed", command=self._host_selected)
        self.host_button.pack(side="left", padx=(10, 0))
        self.stop_button = ttk.Button(actions, text="Stop server", command=self._stop, state="disabled",
                                      style="Ghost.TButton")
        self.stop_button.pack(side="left", padx=(10, 0))
        # Cancel and Install appear only while they can do something; a row of
        # five buttons, three of them dead, overflowed a narrow window.
        self.cancel_button = ttk.Button(actions, text="Cancel generation", command=self.cancel.set,
                                        state="disabled", style="Ghost.TButton")
        self.install_button = ttk.Button(
            actions, textvariable=self.install_label, command=self._install_world, state="disabled")
        status = ttk.Label(frame, textvariable=self.status, style="Muted.TLabel", wraplength=640)
        status.grid(row=row + 4, column=0, columnspan=3, sticky="w")
        frame.bind("<Configure>", lambda e: status.configure(wraplength=max(300, e.width - 60)), add="+")
        app.root.protocol("WM_DELETE_WINDOW", self._close)
        app.root.after(1000, self._poll)

    def _browse_root(self):
        value = self.app.filedialog.askdirectory(title="Archipelago installation")
        if value:
            self.ap_root.set(value)

    def _browse_python(self):
        value = self.app.filedialog.askopenfilename(title="Python interpreter for Archipelago")
        if value:
            self.python.set(value)

    def _browse_players(self):
        value = self.app.filedialog.askdirectory(title="Folder containing player YAML files")
        if value:
            self.players.set(value)
            self.use_folder.set(True)

    def _load(self):
        try:
            values = json.loads(self.config_path.read_text(encoding="utf-8"))
            if not isinstance(values, dict):
                return
            for key in ("ap_root", "python", "name", "players", "port"):
                if isinstance(values.get(key), str):
                    getattr(self, key).set(values[key])
        except (OSError, ValueError, TypeError):
            pass

    def _save(self):
        values = {key: getattr(self, key).get() for key in ("ap_root", "python", "name", "players", "port")}
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(values, indent=2), encoding="utf-8")

    def _tools(self):
        return discover_ap_tools(Path(self.ap_root.get().strip()), self.python.get().strip() or None)

    def _generate(self):
        if self.app._busy:
            return
        if self.host and self.host.running:
            self._error("Stop the local server before creating a different seed.")
            return
        try:
            tools = self._tools()
            manifest = resource_root() / "worlds" / "bloodborne" / "archipelago.json"
            expected = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception as exc:
            self._error(str(exc))
            return
        try:
            validate_bloodborne_world(tools.root, expected_manifest=expected)
        except BloodborneWorldUnavailable as exc:
            self._offer_world_install(tools.root, exc)
            return
        except Exception as exc:
            self._error(str(exc))
            return
        self._clear_world_install()
        try:
            state = self.app._state_root()
            if self.use_folder.get():
                if not self.players.get().strip():
                    raise ValidationError("Choose the folder containing your player YAML files.")
                players = Path(self.players.get().strip())
            else:
                players = write_solo_player(state, self.name.get(), self.include_dlc.get())
            self._save()
            auto_host = self.auto_host.get()
        except Exception as exc:
            self._error(str(exc))
            return
        self.cancel.clear()
        self.generating = True
        self.app._set_busy(True)
        self.cancel_button.configure(state="normal")
        self.cancel_button.pack(side="left", padx=(10, 0))
        self.status.set("Generating seed… Progress appears below.")
        def run():
            try:
                result = generate_seed(tools, players, state / "generated", on_output=self.app._progress_message, cancel=self.cancel)
            except Exception as exc:
                self.app.root.after(0, self._generation_failed, str(exc))
            else:
                self.app.root.after(0, self._generated, result.archive, auto_host)
        threading.Thread(target=run, daemon=True, name="ap-generate").start()

    def _offer_world_install(self, root, error):
        """Name the problem and arm the one button that fixes it.

        Nothing is installed here. The player sees what is wrong, where the
        world would go, and a button whose label says which of the two things
        it will do.
        """
        self._install_root = root
        if error.mismatch and error.expected_version:
            label = f"Update Bloodborne world to {error.expected_version}"
        elif error.mismatch:
            label = "Update Bloodborne world"
        else:
            label = "Install Bloodborne world"
        self.install_label.set(label)
        self.install_button.configure(state="normal")
        self.install_button.pack(side="left", padx=(10, 0))
        self.status.set(f"{error} Choose “{label}” to install it into {root}. {RESTART_NOTICE}")
        self.app._append_log(f"ERROR: {error}")

    def _clear_world_install(self):
        self._install_root = None
        self.install_button.configure(state="disabled")
        self.install_button.pack_forget()

    def _install_world(self):
        if self.app._busy or self._install_root is None:
            return
        root = self._install_root
        try:
            installed = install_bloodborne_world(root)
        except Exception as exc:
            self._error(str(exc))
            return
        self._clear_world_install()
        self.status.set(f"Installed {installed}. {RESTART_NOTICE}")
        self.app._append_log(f"Installed the Bloodborne world: {installed}. {RESTART_NOTICE}")
        # Re-validate and carry on with what the player originally asked for.
        self._generate()

    def _generation_failed(self, message):
        self.generating = False
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack_forget()
        self.app._set_busy(False)
        self._error(message)

    def _generated(self, archive, auto_host):
        self.generating = False
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack_forget()
        self.app._set_busy(False)
        try:
            archive_slots(archive)
        except Exception as exc:
            self._error(f"Generated seed cannot be used for Bloodborne: {exc}")
            return
        self.app.fields["ap_request"].set(str(archive))
        self.app._accept_ap_request(str(archive))
        self.status.set(f"Seed created: {archive.name}. Select your player on Play.")
        if auto_host:
            self._host_selected()
        else:
            self.app.notebook.select(self.app.play_tab)

    def _host_selected(self):
        if self.app._busy:
            return
        if self.host and self.host.running:
            self._error("This launcher already hosts a seed. Stop it before hosting another.")
            return
        try:
            tools = self._tools()
            archive = Path(self.app.fields["ap_request"].get().strip())
            port = int(self.port.get())
            state_root = self.app._state_root()
            identity = _request_identity(
                archive, player_name=self.app.player_name.get().strip(), state_root=state_root
            )
            self._save()
        except Exception as exc:
            self._error(str(exc))
            return
        self.app._set_busy(True)
        def run():
            try:
                server = start_server(tools, archive, host="127.0.0.1", port=port, on_output=self.app._progress_message)
                try:
                    # This launcher just started this archive on a previously
                    # free port. Its verified identity replaces address history;
                    # ordinary remote connections retain the mismatch guard.
                    check_seed_slot_identity(
                        state_root, server=f"127.0.0.1:{port}",
                        seed=identity["seed"], slot=identity["slot"], allow_mismatch=True,
                    )
                except Exception:
                    server.stop()
                    raise
            except Exception as exc:
                self.app.root.after(0, self._host_failed, str(exc))
            else:
                self.app.root.after(0, self._host_started, server, port)
        threading.Thread(target=run, daemon=True, name="ap-local-host").start()

    def _host_failed(self, message):
        self.app._set_busy(False)
        self._error(message)

    def _host_started(self, server, port):
        self.host = server
        self.app._set_busy(False)
        self.app.ap_server.set(f"127.0.0.1:{port}")
        self.status.set(f"Local server started on 127.0.0.1:{port}. Keep this launcher open while playing.")
        self.app.notebook.select(self.app.play_tab)
        self.app._setup_changed()

    def _stop(self, close_after=False):
        if self.app._busy:
            return
        if not self.host or not self.host.running:
            if close_after:
                self.app.root.destroy()
            return
        self.app._set_busy(True)
        server = self.host
        self.status.set("Saving and stopping the local server…")
        def run():
            try:
                server.stop()
            except Exception as exc:
                self.app.root.after(0, self._host_failed, str(exc))
            else:
                self.app.root.after(0, self._stopped, close_after)
        threading.Thread(target=run, daemon=True, name="ap-host-stop").start()

    def _stopped(self, close_after):
        self.host = None
        self.app._set_busy(False)
        self.status.set("Local server stopped. The generated seed remains available on Play.")
        if close_after:
            self.app.root.destroy()

    def _close(self):
        if self.app._busy:
            self.app.messagebox.showinfo("Operation in progress", "Wait for the operation to finish, or cancel seed generation first.", parent=self.app.root)
            return
        if self.host and self.host.running:
            if self.app.messagebox.askyesno("Stop local server?", "Closing will save and stop the local server hosted by this launcher. Continue?", parent=self.app.root):
                self._stop(close_after=True)
        else:
            self.app.root.destroy()

    def _poll(self):
        active = bool(self.host and self.host.running)
        if self.host and not active:
            self.host = None
            self.status.set("Local server exited. See Progress for details; restart with Host selected seed.")
        self.create.configure(state="disabled" if self.app._busy or active else "normal")
        self.host_button.configure(state="disabled" if self.app._busy or active else "normal")
        self.stop_button.configure(state="normal" if active and not self.app._busy else "disabled")
        self.app.root.after(1000, self._poll)

    def _error(self, message):
        self.status.set(message)
        self.app._append_log(f"ERROR: {message}")
        self.app.messagebox.showerror("Create & host", message, parent=self.app.root)
