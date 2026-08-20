"""Tk desktop surface for one-click Bloodborne enemy randomization and launch."""

from __future__ import annotations

import argparse
import json
import os
import threading
from pathlib import Path
from typing import Any, Mapping

from .core import LauncherError, ValidationError
from .resources import resource_root
from .workflow import (
    SETTINGS_FORMAT,
    EnemizerOptions,
    LauncherSettings,
    LauncherWorkflow,
)


FIELD_DEFINITIONS = (
    ("ap_request", "AP seed request", "file"),
    ("game_root", "shadPS4 game folder", "directory"),
    ("suppression_binder", "Suppressed gameparam", "file"),
    ("suppression_manifest", "Suppression manifest", "file"),
    ("map_studio_source", "Source MapStudio", "directory"),
    ("enemy_inventory", "Enemy inventory", "file"),
    ("soulsformats_next", "SoulsFormatsNEXT", "directory"),
    ("process_plan", "Launch plan", "file"),
    ("cache_root", "Seed cache", "directory"),
)
DEVELOPMENT_FIELDS = {"enemy_inventory", "soulsformats_next"}


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "BloodborneArchipelago" / "launcher-settings.json"


def request_enemy_seed(path: Path | str) -> str:
    source = Path(path).expanduser()
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read AP seed request {source}: {exc}") from exc
    if not isinstance(value, dict) or value.get("format") != "bb-enemizer-request-v1":
        raise ValidationError("selected AP seed request has the wrong format")
    seed = value.get("enemizer_seed")
    if not isinstance(seed, str) or not seed.strip():
        raise ValidationError("selected AP seed request has no enemizer_seed")
    return seed


def settings_from_fields(fields: Mapping[str, str]) -> LauncherSettings:
    value: dict[str, Any] = {"format": SETTINGS_FORMAT}
    for name, _label, _kind in FIELD_DEFINITIONS:
        value[name] = fields.get(name, "").strip() or None
    return LauncherSettings.from_dict(value)


class LauncherApp:
    def __init__(self, root: Any, *, repo_root: Path, settings_path: Path):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.root = root
        self.repo_root = repo_root.resolve()
        self.settings_path = settings_path.expanduser().resolve()
        self.workflow = LauncherWorkflow(self.repo_root)
        self.packaged_toolchain = self.workflow.toolchain.is_bundled
        self.fields = {name: tk.StringVar() for name, _label, _kind in FIELD_DEFINITIONS}
        self.randomize_enemies = tk.BooleanVar(value=True)
        self.enemy_seed = tk.StringVar()
        self.allow_tier_mixing = tk.BooleanVar(value=False)
        self.preserve_locomotion = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Choose the AP seed and setup paths.")
        self._enemy_widgets: list[Any] = []
        self._busy = False

        root.title("Bloodborne AP Launcher")
        root.minsize(820, 680)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._build()
        self._load_settings_if_present()
        self._toggle_enemy_fields()

    def _build(self) -> None:
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(3, weight=1)

        title = ttk.Label(outer, text="Bloodborne Archipelago", font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="Build a seed-owned shadPS4 overlay, activate it safely, and launch every component.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        setup = ttk.LabelFrame(outer, text="Setup", padding=10)
        setup.grid(row=2, column=0, sticky="ew")
        setup.columnconfigure(1, weight=1)
        for row, (name, label, kind) in enumerate(FIELD_DEFINITIONS):
            if self.packaged_toolchain and name in DEVELOPMENT_FIELDS:
                continue
            ttk.Label(setup, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            entry = ttk.Entry(setup, textvariable=self.fields[name])
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            button = ttk.Button(
                setup,
                text="Browse...",
                command=lambda key=name, selector=kind: self._browse(key, selector),
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=3)
            if name in {"map_studio_source", "enemy_inventory", "soulsformats_next"}:
                self._enemy_widgets.extend((entry, button))

        options = ttk.LabelFrame(outer, text="Enemy randomization", padding=10)
        options.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        options.columnconfigure(1, weight=1)
        options.rowconfigure(3, weight=1)
        ttk.Checkbutton(
            options,
            text="Randomize Enemies",
            variable=self.randomize_enemies,
            command=self._toggle_enemy_fields,
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(options, text="Enemy seed").grid(row=1, column=0, sticky="w", padx=(24, 8), pady=4)
        seed_entry = ttk.Entry(options, textvariable=self.enemy_seed)
        seed_entry.grid(row=1, column=1, sticky="ew", pady=4)
        tier = ttk.Checkbutton(
            options,
            text="Allow tier mixing (experimental)",
            variable=self.allow_tier_mixing,
        )
        tier.grid(row=2, column=0, sticky="w", padx=(24, 8))
        locomotion = ttk.Checkbutton(
            options,
            text="Preserve locomotion class",
            variable=self.preserve_locomotion,
        )
        locomotion.grid(row=2, column=1, sticky="w")
        self._enemy_widgets.extend((seed_entry, tier, locomotion))

        self.log = self.tk.Text(options, height=10, wrap="word", state="disabled")
        self.log.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        scrollbar = ttk.Scrollbar(options, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=3, column=2, sticky="ns", pady=(10, 0))
        self.log.configure(yscrollcommand=scrollbar.set)

        controls = ttk.Frame(outer)
        controls.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        controls.columnconfigure(1, weight=1)
        self.save_button = ttk.Button(controls, text="Save Setup", command=self._save_settings)
        self.save_button.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(controls, mode="indeterminate")
        self.progress.grid(row=0, column=1, sticky="ew", padx=12)
        self.launch_button = ttk.Button(
            controls,
            text="Randomize & Launch",
            command=self._start,
            style="Accent.TButton",
        )
        self.launch_button.grid(row=0, column=2, sticky="e")
        ttk.Label(outer, textvariable=self.status).grid(row=5, column=0, sticky="w", pady=(8, 0))

    def _browse(self, name: str, selector: str) -> None:
        current = self.fields[name].get().strip()
        initial = str(Path(current).expanduser().parent) if current else None
        if selector == "directory":
            selected = self.filedialog.askdirectory(initialdir=initial, mustexist=True)
        else:
            selected = self.filedialog.askopenfilename(initialdir=initial)
        if not selected:
            return
        self.fields[name].set(selected)
        if name == "ap_request":
            try:
                self.enemy_seed.set(request_enemy_seed(selected))
            except LauncherError as exc:
                self.messagebox.showerror("Invalid AP request", str(exc), parent=self.root)

    def _toggle_enemy_fields(self) -> None:
        state = "normal" if self.randomize_enemies.get() else "disabled"
        for widget in self._enemy_widgets:
            widget.configure(state=state)
        self.launch_button.configure(
            text="Randomize & Launch" if self.randomize_enemies.get() else "Build & Launch"
        )

    def _settings(self) -> LauncherSettings:
        return settings_from_fields({name: variable.get() for name, variable in self.fields.items()})

    def _save_settings(self) -> None:
        try:
            settings = self._settings()
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            value = {
                **settings.as_dict(),
                "randomize_enemies": self.randomize_enemies.get(),
                "enemy_seed": self.enemy_seed.get().strip(),
                "allow_tier_mixing": self.allow_tier_mixing.get(),
                "preserve_locomotion": self.preserve_locomotion.get(),
            }
            self.settings_path.write_text(
                json.dumps(value, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            self.status.set(f"Setup saved to {self.settings_path}")
        except (OSError, LauncherError) as exc:
            self.messagebox.showerror("Could not save setup", str(exc), parent=self.root)

    def _load_settings_if_present(self) -> None:
        if not self.settings_path.is_file():
            return
        try:
            value = json.loads(self.settings_path.read_text(encoding="utf-8-sig"))
            if not isinstance(value, dict) or value.get("format") != SETTINGS_FORMAT:
                raise ValidationError("saved launcher settings have the wrong format")
            for name in self.fields:
                raw = value.get(name)
                if isinstance(raw, str):
                    self.fields[name].set(raw)
            self.randomize_enemies.set(bool(value.get("randomize_enemies", True)))
            self.enemy_seed.set(str(value.get("enemy_seed", "")))
            self.allow_tier_mixing.set(bool(value.get("allow_tier_mixing", False)))
            self.preserve_locomotion.set(bool(value.get("preserve_locomotion", False)))
        except (OSError, UnicodeError, json.JSONDecodeError, LauncherError) as exc:
            self.messagebox.showwarning("Saved setup ignored", str(exc), parent=self.root)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message.rstrip())

    def _progress_message(self, message: str) -> None:
        self.root.after(0, self._append_log, message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.launch_button.configure(state="disabled" if busy else "normal")
        self.save_button.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _start(self) -> None:
        if self._busy:
            return
        try:
            settings = self._settings()
            if not self.enemy_seed.get().strip():
                self.enemy_seed.set(request_enemy_seed(settings.ap_request))
            options = EnemizerOptions(
                enabled=self.randomize_enemies.get(),
                seed=self.enemy_seed.get().strip() or None,
                allow_tier_mixing=self.allow_tier_mixing.get(),
                preserve_locomotion=self.preserve_locomotion.get(),
            )
            self._save_settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._set_busy(True)
        self._append_log("Starting Randomize & Launch...")
        threading.Thread(
            target=self._run,
            args=(settings, options),
            daemon=True,
            name="bloodborne-randomize-launch",
        ).start()

    def _run(self, settings: LauncherSettings, options: EnemizerOptions) -> None:
        try:
            result = self.workflow.randomize_and_launch(
                settings,
                options,
                progress=self._progress_message,
            )
        except Exception as exc:
            self.root.after(0, self._failed, exc)
        else:
            self.root.after(0, self._finished, result)

    def _failed(self, exc: Exception) -> None:
        self._set_busy(False)
        self._append_log(f"REFUSED: {exc}")
        self.messagebox.showerror("Randomize & Launch refused", str(exc), parent=self.root)

    def _finished(self, result: Any) -> None:
        self._set_busy(False)
        mode = "enemy randomization enabled" if result.enemizer_enabled else "enemies unchanged"
        self._append_log(f"Launch started ({mode}); cache {result.cache_key[:12]}.")
        self.messagebox.showinfo(
            "Bloodborne AP started",
            f"Verified overlay {result.cache_key[:12]} is active.\n{mode.capitalize()}.",
            parent=self.root,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=default_settings_path())
    args = parser.parse_args(argv)
    try:
        import tkinter as tk
    except ImportError as exc:
        raise SystemExit("This Python installation does not include Tkinter.") from exc
    root = tk.Tk()
    LauncherApp(
        root,
        repo_root=resource_root(),
        settings_path=args.settings,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
