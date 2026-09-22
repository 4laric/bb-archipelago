"""BBLauncher companion controls, isolated from standalone activation actions."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import threading

from .core import LauncherError
from .workflow import EnemizerOptions


class BBLauncherPanel:
    def __init__(self, app, notebook):
        self.app = app
        self.enabled = app.tk.BooleanVar(value=False)
        self.candidate = app.tk.BooleanVar(value=False)
        self.mods = app.tk.StringVar()
        self.executable = app.tk.StringVar()
        self.receipt = app.tk.StringVar()
        self.connected_receipt_id: str | None = None
        self.connected_fingerprint: str | None = None
        frame = app.ttk.Frame(notebook, padding=10)
        frame.columnconfigure(1, weight=1)
        notebook.add(frame, text="BBLauncher")
        app.ttk.Checkbutton(frame, text="BBLauncher mode", variable=self.enabled,
                            command=app._refresh_launch_gate).grid(row=0, column=0, columnspan=3, sticky="w")
        app.ttk.Label(frame, text="Build here; activate and start the game in BBLauncher; connect here.",
                      wraplength=680).grid(row=1, column=0, columnspan=3, sticky="w", pady=6)
        for row, (label, variable, directory) in enumerate((
            ("BBLauncher executable", self.executable, False),
            ("BBLauncher Mods directory", self.mods, True),
            ("Export receipt", self.receipt, False),
        ), 2):
            app.ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            app.ttk.Entry(frame, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=3)
            app.ttk.Button(frame, text="Browse...", command=lambda v=variable, d=directory: self.browse(v, d)).grid(row=row, column=2)
        app.ttk.Checkbutton(frame, text="Test the pinned BBLauncher build (live acceptance pending)",
                            variable=self.candidate).grid(row=5, column=0, columnspan=3, sticky="w", pady=5)
        buttons = app.ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=3, sticky="w", pady=8)
        for label, action in (("Build and export mod", "export"),
                              ("Verify activated mod", "verify"),
                              ("Connect to running game", "connect")):
            app.ttk.Button(buttons, text=label, command=lambda a=action: self.start(a)).pack(side="left", padx=3)
        app.ttk.Button(frame, text="Launch without Archipelago", command=self.without_ap).grid(row=7, column=0, columnspan=3, sticky="w")
        app.ttk.Label(frame, text="Deactivate the previous AP mod before activating another. Resolve AP file conflicts; do not accept an override or use Mod Merger. After activation, verify with the game stopped, then start it in BBLauncher.",
                      wraplength=700).grid(row=8, column=0, columnspan=3, sticky="w", pady=6)

    def refresh_status(self, settings):
        import time
        from .external import load_external_receipt
        from .client_config import session_paths
        from .readiness import _client_health_status
        try:
            if settings.bblauncher_receipt is None:
                self.app._set_status_text("BBLauncher: build and export a seed, then select its receipt.")
                return
            receipt = load_external_receipt(settings.bblauncher_receipt,
                                            allow_live_acceptance_candidate=self.candidate.get())
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

    def start(self, action):
        app = self.app
        if app._busy:
            return
        self.connected_receipt_id = None
        self.connected_fingerprint = None
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
            candidate = self.candidate.get()
            captures = app.research_captures.get()
        except LauncherError as exc:
            app.messagebox.showerror("Setup incomplete", str(exc), parent=app.root)
            return
        app._save_settings()
        app._set_busy(True)
        def run():
            from .external_workflow import build_and_export, verify_before_boot, connect_external
            try:
                connection = None
                kwargs = {"allow_live_acceptance_candidate": candidate}
                if action == "export":
                    result = build_and_export(app.workflow, settings, options, player_name=player,
                                              progress=app._progress_message, **kwargs)
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
                        allow_live_acceptance_candidate=candidate,
                    )
                    connection = (selected.receipt_id, contract["activation_fingerprint"])
            except Exception as exc:
                app.root.after(0, app._action_failed, "BBLauncher " + action, exc)
            else:
                app.root.after(
                    0, lambda r=result, c=connection: self.finished(action, r, c)
                )
        threading.Thread(target=run, name="bblauncher-companion", daemon=True).start()

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
            message = f"Exported {result.package_path}. Activate it in BBLauncher with the game stopped, then select Verify activated mod."
        else:
            message = "Ready for a fresh boot. Start Bloodborne from BBLauncher, then select Connect to running game."
        app._append_log(message)
        app._set_status_text(message)
