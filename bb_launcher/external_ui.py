"""BBLauncher companion controls, isolated from standalone activation actions."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import threading

from .core import LauncherError
from .workflow import EnemizerOptions


class BBLauncherPanel:
    def __init__(self, app, parent):
        """Build the companion controls inside ``parent`` (a frame on the
        Advanced page); the panel owns no page of its own."""
        from .theme import field, option
        self.app = app
        self.enabled = app.tk.BooleanVar(value=False)
        self.mods = app.tk.StringVar()
        self.executable = app.tk.StringVar()
        self.receipt = app.tk.StringVar()
        self.connected_receipt_id: str | None = None
        self.connected_fingerprint: str | None = None
        self.prepared = app.tk.StringVar(value="No mod prepared yet. Choose your seed in Play, then build it here.")
        self.guidance = app.tk.StringVar()
        frame = parent
        frame.columnconfigure(1, weight=1)
        self.tab = frame
        self._wrapping_labels = []
        def resize(event):
            for label in self._wrapping_labels:
                label.configure(wraplength=max(260, event.width - 40))
        frame.bind("<Configure>", resize, add="+")
        def label(text=None, variable=None, row=0, style="TLabel", pady=(2, 6)):
            widget = app.ttk.Label(frame, text=text, textvariable=variable, style=style, wraplength=640)
            widget.grid(row=row, column=0, columnspan=3, sticky="ew", pady=pady)
            self._wrapping_labels.append(widget)
            return widget
        def step(row, text):
            app.ttk.Label(frame, text=text, style="Section.TLabel").grid(
                row=row, column=0, columnspan=3, sticky="w", pady=(14, 4))
        option(app.ttk, frame, 0, "Use BBLauncher to manage and start Bloodborne", self.enabled,
               caption="Builds a data mod for BBLauncher instead of starting shadPS4 from here.",
               command=app._refresh_launch_gate)
        step(1, "1 \u00b7 Set up")
        field(app.ttk, frame, 2, "BBLauncher app", self.executable,
              browse=self.choose_executable, browse_text="Choose app\u2026")
        label(variable=self.guidance, row=3, style="Muted.TLabel")
        setup_actions = app.ttk.Frame(frame)
        setup_actions.grid(row=4, column=0, columnspan=3, sticky="w")
        app.ttk.Button(setup_actions, text="Advanced settings\u2026", command=self.advanced,
                       style="Link.TButton").pack(side="left")
        self.fix_folder = app.ttk.Button(setup_actions, text="Use detected mod folder",
                                         command=self.use_detected_folder, style="Ghost.TButton")
        self.fix_folder.pack(side="left", padx=(10, 0))
        step(5, "2 \u00b7 Prepare")
        label(variable=self.prepared, row=6)
        actions = app.ttk.Frame(frame)
        actions.grid(row=7, column=0, columnspan=3, sticky="w", pady=(0, 4))
        self.buttons = {}
        self.buttons["export"] = app.ttk.Button(actions, text="Build mod for BBLauncher", style="Accent.TButton",
                                                command=lambda: self.start("export"))
        self.buttons["export"].pack(side="left")
        app.ttk.Button(actions, text="Choose seed / player", style="Link.TButton",
                       command=lambda: app.notebook.select(app.play_tab)).pack(side="left", padx=(10, 0))
        step(8, "3 \u00b7 Activate, verify, connect")
        label("In BBLauncher's Mod Manager, deactivate any earlier Archipelago mod and activate the prepared one "
              "with the game stopped. On a file conflict, cancel and deactivate the other mod; never use Mod Merger.",
              row=9, style="Muted.TLabel")
        actions = app.ttk.Frame(frame)
        actions.grid(row=10, column=0, columnspan=3, sticky="w")
        for title, action in (("Verify activated mod", "verify"), ("Connect to game", "connect")):
            self.buttons[action] = app.ttk.Button(actions, text=title, command=lambda a=action: self.start(a))
            self.buttons[action].pack(side="left", padx=(0, 10))
        app.ttk.Button(actions, text="How to play without Archipelago", command=self.without_ap,
                       style="Link.TButton").pack(side="left")
        label("Verify with the game stopped, then start Bloodborne from BBLauncher and connect.",
              row=11, style="Dim.TLabel")
        self._suggested_mods = ""
        for variable in (self.executable, self.mods, self.receipt):
            variable.trace_add("write", self.update_setup)
        self.executable.trace_add("write", self._suggest_folder)
        for key in ("ap_request", "game_root", "shad_executable"):
            app.fields[key].trace_add("write", self.update_setup)
        self.update_setup()

    def _suggest_folder(self, *_):
        from .external_setup import suggest_mods_directory
        current = self.mods.get().strip()
        raw = self.executable.get().strip()
        if raw and (not current or current == self._suggested_mods):
            self._suggested_mods = str(suggest_mods_directory(Path(raw)))
            self.mods.set(self._suggested_mods)

    def use_detected_folder(self):
        from .external_setup import suggest_mods_directory
        if self.executable.get().strip():
            self._suggested_mods = str(suggest_mods_directory(Path(self.executable.get().strip())))
            self.mods.set(self._suggested_mods)

    def choose_executable(self):
        value = self.app.filedialog.askopenfilename(parent=self.app.root, title="Choose BBLauncher",
            filetypes=[("BBLauncher app", "*.exe"), ("All files", "*.*")])
        if value:
            self.executable.set(value)

    def advanced(self):
        app = self.app
        window = app.tk.Toplevel(app.root)
        window.title("BBLauncher advanced settings")
        window.transient(app.root)
        window.columnconfigure(1, weight=1)
        app.ttk.Label(window, text="Mod library folder (inactive mods)").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        app.ttk.Entry(window, textvariable=self.mods, width=60).grid(row=0, column=1, sticky="ew")
        app.ttk.Button(window, text="Choose folder...", command=lambda: self.browse(self.mods, True)).grid(row=0, column=2, padx=10)
        app.ttk.Button(window, text="Use launcher's default folder", command=self.use_detected_folder).grid(row=1, column=1, sticky="w")
        app.ttk.Label(window, textvariable=self.guidance, wraplength=680).grid(row=2, column=0, columnspan=3, sticky="ew", padx=10, pady=10)
        app.ttk.Label(window, text="Prepared mod details are saved automatically. To recover an earlier export, choose its saved JSON record.", wraplength=680).grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        app.ttk.Button(window, text="Recover a previous export...", command=lambda: self.browse(self.receipt, False)).grid(row=4, column=1, sticky="w")
        app.ttk.Button(window, text="Done", command=window.destroy).grid(row=5, column=2, padx=10, pady=10)

    def update_setup(self, *_):
        from .external_setup import setup_problem
        raw_exe = self.executable.get().strip()
        raw_mods = self.mods.get().strip()
        raw_game = self.app.fields["game_root"].get().strip()
        problem = setup_problem(Path(raw_exe) if raw_exe else None, Path(raw_mods) if raw_mods else None,
                                Path(raw_game) if raw_game else None)
        missing = [title for key, title in (("ap_request", "a seed"), ("game_root", "your game folder"), ("shad_executable", "shadPS4")) if not self.app.fields[key].get().strip()]
        if not problem and missing:
            problem = "In Play, choose " + ", ".join(missing) + ". Then return here to build your mod."
        self.guidance.set(problem or f"Mod library: {raw_mods}")
        from .external_setup import suggest_mods_directory
        if hasattr(self, "fix_folder"):
            if raw_exe and raw_mods != str(suggest_mods_directory(Path(raw_exe))):
                self.fix_folder.grid()
            else:
                self.fix_folder.grid_remove()
        record = self.receipt.get().strip()
        available = False
        if record:
            try:
                from .external import load_external_receipt
                saved = load_external_receipt(Path(record), allow_live_acceptance_candidate=True)
                available = True
                self.prepared.set(f"Prepared mod: {saved.package_name}")
            except (LauncherError, OSError, ValueError):
                self.prepared.set("Saved mod details are missing or unreadable. Build your mod again.")
        else:
            self.prepared.set("No mod prepared yet. Choose your seed in Play, then build it here.")
        busy = getattr(self.app, "_busy", False)
        for action, button in self.buttons.items():
            ready = not problem and (action == "export" or available)
            button.configure(state="normal" if ready and not busy else "disabled")

    def refresh_status(self, settings):
        import time
        from .external import load_external_receipt
        from .client_config import session_paths
        from .readiness import _client_health_status
        try:
            if settings.bblauncher_receipt is None:
                self.app.client_health.set("BBLauncher: no prepared mod selected.")
                self.app._set_status_text("BBLauncher: choose a seed in Play, then build your mod under Advanced.")
                return
            # f092023 is fully supported now; no per-session opt-in needed.
            receipt = load_external_receipt(settings.bblauncher_receipt,
                                            allow_live_acceptance_candidate=True)
            paths = session_paths(self.app._state_root(), seed=receipt.identity.seed, slot=receipt.identity.slot)
            notes = []
            health = _client_health_status(paths, notes, now=time.time())
            identity = f"Seed {receipt.identity.seed}; slot {receipt.identity.slot}"
            connection_verified = False
            if (self.connected_receipt_id == receipt.receipt_id
                    and self.connected_fingerprint is not None
                    and paths.config.is_file()):
                try:
                    runtime = json.loads(paths.config.read_text(encoding="utf-8-sig"))
                    contract = runtime.get("external_activation") if isinstance(runtime, dict) else None
                    connection_verified = (
                        isinstance(contract, dict)
                        and contract.get("activation_fingerprint") == self.connected_fingerprint
                        and contract.get("package_name") == receipt.package_name
                    )
                except (OSError, UnicodeError, json.JSONDecodeError):
                    connection_verified = False
            if not connection_verified:
                status = (
                    "Activation unverified in this companion session: verify the activated mod, "
                    "start the game in BBLauncher, and connect."
                )
            elif health is None or health.stale:
                status = "Disconnected: verify activation, start the game in BBLauncher, and connect."
            elif not health.process_alive:
                status = "Waiting for game: " + health.detail
            elif not health.ap_connected:
                status = "Disconnected from AP: " + health.detail
            elif health.delivery_armed:
                status = "Ready: " + health.detail
            else:
                status = "Delivery paused: " + health.detail
            self.app.client_health.set(status)
            self.app._set_status_text(identity + "\n" + status + ("\n" + "\n".join(notes) if notes else ""))
        except (LauncherError, OSError) as exc:
            self.app.client_health.set("BBLauncher: saved mod details could not be verified.")
            self.app._set_status_text(f"BBLauncher: {exc}")

    def browse(self, variable, directory):
        dialog = self.app.filedialog.askdirectory if directory else self.app.filedialog.askopenfilename
        value = dialog(parent=self.app.root)
        if value:
            variable.set(value)

    def settings(self, base):
        return replace(base, integration_mode="bblauncher" if self.enabled.get() else "standalone",
                       bblauncher_mods=Path(self.mods.get()) if self.mods.get().strip() else None,
                       bblauncher_executable=Path(self.executable.get()) if self.executable.get().strip() else None,
                       bblauncher_receipt=Path(self.receipt.get()) if self.receipt.get().strip() else None)

    def load(self, value):
        self.enabled.set(value.get("integration_mode") == "bblauncher")
        for variable, key in ((self.mods, "bblauncher_mods"), (self.executable, "bblauncher_executable"), (self.receipt, "bblauncher_receipt")):
            variable.set(value.get(key) or "")

    def without_ap(self):
        self.app.messagebox.showinfo("Launch without Archipelago",
            "Stop the AP client and shadPS4. Deactivate the Archipelago mod in BBLauncher, then start the game there. Other active BBLauncher mods remain active.", parent=self.app.root)

    def start(self, action, *, replace_existing=False):
        app = self.app
        if app._busy:
            return
        self.enabled.set(True)
        app._refresh_launch_gate()
        if action != "verify" and not app._generate_plan():
            return
        try:
            settings = app._settings()
            options = EnemizerOptions(enabled=app.randomize_enemies.get(), seed=app.enemy_seed.get().strip() or None,
                allow_tier_mixing=app.allow_tier_mixing.get(), preserve_locomotion=app.preserve_locomotion.get(),
                normalize_scaling=app.normalize_scaling.get(), boss_canary=app.boss_canary.get())
            player = app.player_name.get().strip()
            captures = app.research_captures.get()
        except LauncherError as exc:
            app.messagebox.showerror("Setup incomplete", str(exc), parent=app.root)
            return
        self.connected_receipt_id = None
        self.connected_fingerprint = None
        app.client_health.set("BBLauncher: " + {"export": "building mod", "verify": "checking activated mod", "connect": "connecting"}[action] + "...")
        app._save_settings()
        app._set_busy(True)
        def run():
            from .external_workflow import build_and_export, verify_before_boot, connect_external
            try:
                connection = None
                # f092023 is fully supported now; no per-session opt-in needed.
                kwargs = {"allow_live_acceptance_candidate": True}
                if action == "export":
                    result = build_and_export(app.workflow, settings, options, player_name=player,
                                              progress=app._progress_message,
                                              replace_existing=replace_existing, **kwargs)
                elif action == "verify":
                    result = verify_before_boot(
                        app.workflow, settings, player_name=player, **kwargs
                    )
                else:
                    result = connect_external(app.workflow, settings, player_name=player,
                                              research_captures=captures, progress=app._progress_message, **kwargs)
                    runtime = json.loads(result.client_config.read_text(encoding="utf-8-sig"))
                    contract = runtime.get("external_activation") if isinstance(runtime, dict) else None
                    if not isinstance(contract, dict) or not isinstance(
                            contract.get("activation_fingerprint"), str):
                        raise LauncherError("connected client config has no external activation fingerprint")
                    from .external import load_external_receipt
                    selected = load_external_receipt(
                        settings.bblauncher_receipt,
                        allow_live_acceptance_candidate=True,
                    )
                    connection = (selected.receipt_id, contract["activation_fingerprint"])
            except Exception as exc:
                app.root.after(0, self.failed, action, exc)
            else:
                app.root.after(
                    0, lambda r=result, c=connection: self.finished(action, r, c)
                )
        threading.Thread(target=run, name="bblauncher-companion", daemon=True).start()

    def failed(self, action, exc):
        from .external import ExternalPackageExists
        self.connected_receipt_id = None
        self.connected_fingerprint = None
        if action == "export" and isinstance(exc, ExternalPackageExists):
            self.offer_replacement(exc)
            return
        self.app.client_health.set("Not connected: the last BBLauncher action did not complete.")
        self.app._set_status_text(f"BBLauncher: {exc}")
        self.app._action_failed("BBLauncher " + action, exc)

    def offer_replacement(self, exc):
        """An earlier build of this seed is already in the Mods library.

        The package name is deterministic, so this is the normal outcome of
        pressing Build twice; a dead-end error would send players hunting
        through the Mods folder by hand.  Replacing only ever touches the
        inactive copy, and only after the player says so.
        """
        app = self.app
        app._set_busy(False)
        app._append_log(f"A prepared mod for this seed already exists: {exc.path}")
        replace = app.messagebox.askyesno(
            "Replace prepared mod?",
            f"{exc.path.name} is already in BBLauncher's Mods library from an earlier build "
            "of this seed.\n\nReplace it with a fresh build? If it is currently active, "
            "deactivate it in BBLauncher first.",
            parent=app.root,
        )
        if replace:
            self.start("export", replace_existing=True)
            return
        app.client_health.set("BBLauncher: kept the existing prepared mod.")
        app._set_status_text(f"Kept the existing prepared mod: {exc.path}")
        self.update_setup()

    def finished(self, action, result, connection=None):
        app = self.app
        if action == "connect":
            if connection is None:
                raise LauncherError("connected session has no activation fingerprint")
            if getattr(result, "early_exit", None) is None:
                self.connected_receipt_id, self.connected_fingerprint = connection
            app._finished(result, action="BBLauncher client connection")
            return
        app._set_busy(False)
        if action == "export":
            self.receipt.set(str(result.receipt_path))
            app._save_settings()
            message = f"Prepared {result.package_path.name}. In BBLauncher, activate this mod with the game stopped, then return here and select Verify activated mod."
        else:
            message = "Ready for a fresh boot. Start Bloodborne from BBLauncher, then select Connect to game."
        app._append_log(message)
        app._set_status_text(message)
        self.update_setup()
