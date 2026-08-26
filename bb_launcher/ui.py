"""Tk desktop surface for one-click Bloodborne enemy randomization and launch."""

from __future__ import annotations

import argparse
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable, Mapping

from .client_config import default_shad_log, default_state_root
from .core import (
    MAP_PREFIX,
    GameInstall,
    LauncherError,
    ValidationError,
    discover_game_install,
    elevation_risks,
    launcher_is_elevated,
)
from .doctor import _process_running, format_report, run_doctor
from .plan import DEFAULT_SERVER, generate_process_plan, write_process_plan
from .readiness import format_readiness, gather_readiness, grants_watchdog_warning
from .resources import application_root, resource_root
from .seed_request import (
    archive_player_name,
    looks_like_archive,
    resolve_request_source,
)
from .workflow import (
    REQUEST_FORMATS,
    SETTINGS_FORMAT,
    EnemizerOptions,
    LauncherSettings,
    LauncherWorkflow,
    _request_identity,
)


# One-shot post-launch check that the CE grant harness reported in. Four
# minutes covers slow CE start + both prompts; without this, a bridge that
# never arms is invisible until the player notices items never arrive
# (oz's 2026-08-23 session ran a full release with grants silently dead).
GRANT_WATCHDOG_MS = 240_000


FIELD_DEFINITIONS = (
    ("ap_request", "AP seed file (.zip or .bbseed.json)", "file"),
    ("game_root", "shadPS4 game folder", "directory"),
    ("suppression_binder", "Suppressed gameparam", "file"),
    ("suppression_manifest", "Suppression manifest", "file"),
    ("map_studio_source", "Source MapStudio", "directory"),
    ("enemy_inventory", "Enemy inventory", "file"),
    ("soulsformats_next", "SoulsFormatsNEXT", "directory"),
    ("process_plan", "Launch plan", "file"),
    ("shad_executable", "shadPS4.exe", "file"),
    ("cache_root", "Seed cache", "directory"),
    ("state_root", "Launcher state (optional)", "directory"),
    ("shad_log", "shadPS4 log (optional)", "file"),
)
DEVELOPMENT_FIELDS = {"enemy_inventory", "soulsformats_next"}

# Bloodborne palette: hunter's-dream night blues, bone parchment text,
# blood-red accents, lamp-light gold headers.
THEME_BACKGROUND = "#0d1117"
THEME_PANEL = "#161b24"
THEME_BORDER = "#2a3140"
THEME_FOREGROUND = "#d6d0bd"
THEME_MUTED = "#8590a0"
THEME_BLOOD = "#8f1d24"
THEME_BLOOD_ACTIVE = "#b3242c"
THEME_GOLD = "#c2a14d"


def default_field_values(
    *,
    state_root: Path,
    package_roots: Iterable[Path],
    repo_root: Path | None = None,
    player_name: str = "",
) -> dict[str, str]:
    """Values the launcher can derive for empty setup fields.

    Launcher-owned paths are always offered (seed cache, state root, shad log,
    the generated plan path); the suppression pair is offered only when
    `work/vanilla-suppression-build` actually exists beside the package or the
    checkout; Cheat Engine and the AP request are offered only when found on
    disk. Anything else stays for the player to choose.
    """
    values = {
        "cache_root": str(state_root / "seeds"),
        "state_root": str(state_root),
        "shad_log": str(default_shad_log()),
        "process_plan": str(state_root / "process-plan.json"),
    }
    if repo_root is not None:
        request = derive_ap_request((repo_root,), player_name)
        if request is not None:
            values["ap_request"] = str(request)
    for root in package_roots:
        build = root / "work" / "vanilla-suppression-build"
        binder = build / "gameparam.parambnd.dcx"
        manifest = build / "build-manifest.json"
        if binder.is_file():
            values.setdefault("suppression_binder", str(binder))
        if manifest.is_file():
            values.setdefault("suppression_manifest", str(manifest))
    return values


def _request_player_name(path: Path) -> str | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("format") not in REQUEST_FORMATS:
        return None
    name = value.get("player_name")
    return name.strip() if isinstance(name, str) and name.strip() else None


def _candidate_player_name(path: Path) -> str | None:
    """The slot a discovered candidate belongs to: loose file or whole zip.

    A zip with several Bloodborne slots names none of them on its own, so it
    stays a candidate only while no player name is known.
    """
    if looks_like_archive(path):
        return archive_player_name(path)
    return _request_player_name(path)


def derive_ap_request(roots: Iterable[Path], player_name: str = "") -> Path | None:
    """Newest seed request under each root's Archipelago output directory.

    Generation drops `<seed>_P<slot>_<name>.bbseed.json` (older seeds:
    `.bbenemizer.json`) beside the seed
    zip in `Archipelago/out` or `Archipelago/output`; the newest one is the
    best guess for what the player just generated. The `AP_<seed>.zip` itself
    counts too (bb-archipelago#194) -- the launcher takes either. A
    multi-Bloodborne multiworld drops one request per Bloodborne player, so
    when the player name is known, only that player's own requests are
    considered — picking another player's file connects the client as THEIR
    slot.
    """
    candidates: list[Path] = []
    for root in roots:
        for name in ("out", "output"):
            directory = root / "Archipelago" / name
            if directory.is_dir():
                candidates.extend(directory.rglob("*.bbseed.json"))
                candidates.extend(directory.rglob("*.bbenemizer.json"))
                candidates.extend(directory.rglob("AP_*.zip"))
    wanted = player_name.strip()
    if wanted:
        own = [path for path in candidates if _candidate_player_name(path) == wanted]
        if own:
            candidates = own
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def derive_map_studio_for_game_root(game_root: Path | str) -> Path | None:
    """Best-effort MapStudio source from a chosen game folder: patch wins."""
    try:
        install = GameInstall.from_root(game_root)
    except LauncherError:
        return None
    relative = Path(MAP_PREFIX)
    for _name, backend in install.content_backends():
        candidate = backend / relative
        if candidate.is_dir():
            return candidate
    return None


def derive_game_root_for_shad(shad_executable: Path | str) -> Path | None:
    """Best-effort game install discovery from a chosen shadPS4.exe.

    Looks in the executable's directory and its games/ sibling. Ambiguity and
    absence both yield None: a wrong guess is worse than an empty field.
    """
    parent = Path(shad_executable).expanduser().resolve().parent
    try:
        return discover_game_install([parent / "games", parent]).root
    except LauncherError:
        return None


def default_settings_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "BloodborneArchipelago" / "launcher-settings.json"


def request_enemy_seed(
    path: Path | str,
    *,
    player_name: str = "",
    state_root: Path | None = None,
) -> str:
    """The enemizer seed of the chosen seed file -- request or multiworld zip."""
    source = resolve_request_source(
        path, player_name=player_name, state_root=state_root
    ).path
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read AP seed file {source}: {exc}") from exc
    if not isinstance(value, dict) or value.get("format") not in REQUEST_FORMATS:
        raise ValidationError("selected AP seed file has the wrong format")
    seed = value.get("enemizer_seed")
    if not isinstance(seed, str) or not seed.strip():
        raise ValidationError("selected AP seed file has no enemizer_seed")
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
        self.ap_server = tk.StringVar()
        self.player_name = tk.StringVar()
        self.allow_tier_mixing = tk.BooleanVar(value=False)
        self.preserve_locomotion = tk.BooleanVar(value=False)
        # Operator override (bb-archipelago#183).  Deliberately absent from
        # _save_settings and _load_settings_if_present: it is per-session by
        # construction, so it can never be left on and forgotten.
        self.allow_suppression_mismatch = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Choose the AP seed and setup paths.")
        self._enemy_widgets: list[Any] = []
        self._busy = False

        root.title("Bloodborne AP Launcher")
        root.minsize(820, 620)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._apply_theme()
        self._build()
        self._load_settings_if_present()
        self._apply_default_fields()
        self._toggle_enemy_fields()
        self.root.after(0, self._refresh_status)

    def _apply_theme(self) -> None:
        ttk = self.ttk
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self.tk.TclError:
            pass
        self.root.configure(bg=THEME_BACKGROUND)
        style.configure(
            ".",
            background=THEME_BACKGROUND,
            foreground=THEME_FOREGROUND,
            fieldbackground=THEME_PANEL,
            bordercolor=THEME_BORDER,
            darkcolor=THEME_BACKGROUND,
            lightcolor=THEME_BACKGROUND,
        )
        style.configure("TFrame", background=THEME_BACKGROUND)
        style.configure("TLabel", background=THEME_BACKGROUND, foreground=THEME_FOREGROUND)
        style.configure(
            "Title.TLabel", background=THEME_BACKGROUND, foreground=THEME_GOLD
        )
        style.configure(
            "Muted.TLabel", background=THEME_BACKGROUND, foreground=THEME_MUTED
        )
        style.configure(
            "TLabelframe", background=THEME_BACKGROUND, foreground=THEME_GOLD,
            bordercolor=THEME_BORDER,
        )
        style.configure(
            "TLabelframe.Label", background=THEME_BACKGROUND, foreground=THEME_GOLD
        )
        style.configure(
            "TEntry", fieldbackground=THEME_PANEL, foreground=THEME_FOREGROUND,
            insertcolor=THEME_FOREGROUND, bordercolor=THEME_BORDER,
        )
        style.configure(
            "TButton", background=THEME_PANEL, foreground=THEME_FOREGROUND,
            bordercolor=THEME_BORDER, padding=(10, 4),
        )
        style.map(
            "TButton",
            background=[("active", "#1f2733"), ("disabled", THEME_BACKGROUND)],
            foreground=[("disabled", THEME_MUTED)],
        )
        style.configure("Accent.TButton", background=THEME_BLOOD, foreground="#f5f0e1")
        style.map(
            "Accent.TButton",
            background=[("active", THEME_BLOOD_ACTIVE), ("disabled", THEME_BACKGROUND)],
            foreground=[("disabled", THEME_MUTED)],
        )
        style.configure("TCheckbutton", background=THEME_BACKGROUND, foreground=THEME_FOREGROUND)
        style.map("TCheckbutton", background=[("active", THEME_BACKGROUND)])
        style.configure(
            "Horizontal.TProgressbar", background=THEME_BLOOD,
            troughcolor=THEME_PANEL, bordercolor=THEME_PANEL,
        )

    def _apply_default_fields(self) -> None:
        """Fill empty fields the launcher can derive; saved/user values win."""
        derived = default_field_values(
            state_root=default_state_root(),
            package_roots=(application_root(), resource_root()),
            repo_root=self.repo_root,
            player_name=self.player_name.get(),
        )
        for name, value in derived.items():
            if not self.fields[name].get().strip():
                self.fields[name].set(value)

    def _build(self) -> None:
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        # The notebook and the log both stretch, and both carry a floor
        # (bb-archipelago#190): the old single column stacked every panel in
        # one grid, so on a short display Tk crushed the only weighted row --
        # the enemy-randomization panel, toggle and progress log included --
        # to zero height and it vanished with no diagnostic at all.
        outer.rowconfigure(2, weight=1, minsize=240)
        outer.rowconfigure(3, weight=2, minsize=140)

        title = ttk.Label(
            outer, text="Bloodborne Archipelago",
            font=("Segoe UI", 18, "bold"), style="Title.TLabel",
        )
        title.grid(row=0, column=0, sticky="w")
        ttk.Label(
            outer,
            text="Build a seed-owned shadPS4 overlay, activate it safely, and launch every component.",
        ).grid(row=1, column=0, sticky="w", pady=(2, 12))

        notebook = ttk.Notebook(outer)
        notebook.grid(row=2, column=0, sticky="nsew")
        self.notebook = notebook

        setup = ttk.Frame(notebook, padding=10)
        setup.columnconfigure(1, weight=1)
        notebook.add(setup, text="Setup")

        options = ttk.Frame(notebook, padding=10)
        options.columnconfigure(1, weight=1)
        notebook.add(options, text="Enemy randomization")

        # The enemizer's own input paths live on the enemizer tab; everything
        # else stays on Setup. Same variables, same commands, same
        # _enemy_widgets group -- only the parent frame differs.
        enemy_fields = {"map_studio_source", "enemy_inventory", "soulsformats_next"}
        setup_row = 0
        enemy_row = 4
        for name, label, kind in FIELD_DEFINITIONS:
            if self.packaged_toolchain and name in DEVELOPMENT_FIELDS:
                continue
            if name in enemy_fields:
                parent, row = options, enemy_row
                enemy_row += 1
            else:
                parent, row = setup, setup_row
                setup_row += 1
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            entry = ttk.Entry(parent, textvariable=self.fields[name])
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            button = ttk.Button(
                parent,
                text="Browse...",
                command=lambda key=name, selector=kind: self._browse(key, selector),
            )
            button.grid(row=row, column=2, padx=(8, 0), pady=3)
            if name in enemy_fields:
                self._enemy_widgets.extend((entry, button))
        server_row = setup_row
        ttk.Label(setup, text="Archipelago server").grid(
            row=server_row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(setup, textvariable=self.ap_server).grid(row=server_row, column=1, sticky="ew", pady=3)
        ttk.Label(setup, text=f"default {DEFAULT_SERVER}").grid(
            row=server_row, column=2, sticky="w", padx=(8, 0), pady=3
        )
        name_row = server_row + 1
        ttk.Label(setup, text="Your AP player name").grid(
            row=name_row, column=0, sticky="w", padx=(0, 8), pady=3
        )
        ttk.Entry(setup, textvariable=self.player_name).grid(
            row=name_row, column=1, sticky="ew", pady=3
        )
        ttk.Label(setup, text="the slot name your host gave you").grid(
            row=name_row, column=2, sticky="w", padx=(8, 0), pady=3
        )
        # Outside the enemy-randomization widget group on purpose: it stays
        # usable with Randomize Enemies off, and it is never saved.
        ttk.Checkbutton(
            setup,
            text="Allow suppression binder mismatch (operators only, not saved)",
            variable=self.allow_suppression_mismatch,
        ).grid(row=name_row + 1, column=0, columnspan=3, sticky="w", pady=(8, 0))

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

        # Launch/build progress, not an enemizer concern: it lives outside the
        # notebook so no tab selection can hide it.
        log_frame = ttk.LabelFrame(outer, text="Progress", padding=10)
        log_frame.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = self.tk.Text(
            log_frame, height=8, wrap="word", state="disabled",
            bg=THEME_PANEL, fg=THEME_FOREGROUND, insertbackground=THEME_FOREGROUND,
            relief="flat",
        )
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        status_frame = ttk.LabelFrame(outer, text="Session status", padding=10)
        status_frame.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        status_frame.columnconfigure(0, weight=1)
        self.status_text = self.tk.Text(
            status_frame, height=6, wrap="word", state="disabled",
            bg=THEME_PANEL, fg=THEME_FOREGROUND, insertbackground=THEME_FOREGROUND,
            relief="flat",
        )
        self.status_text.grid(row=0, column=0, sticky="ew")
        status_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_text.yview)
        status_scroll.grid(row=0, column=1, sticky="ns")
        self.status_text.configure(yscrollcommand=status_scroll.set)
        refresh_button = ttk.Button(status_frame, text="Refresh", command=self._refresh_status)
        refresh_button.grid(row=0, column=2, sticky="ne", padx=(8, 0))

        controls = ttk.Frame(outer)
        controls.grid(row=5, column=0, sticky="ew", pady=(12, 0))
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

        actions = ttk.Frame(controls)
        actions.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.vanilla_button = ttk.Button(actions, text="Launch Vanilla", command=self._start_vanilla)
        self.vanilla_button.grid(row=0, column=0, padx=(0, 8))
        self.restore_button = ttk.Button(
            actions, text="Restore Previous", command=self._start_restore
        )
        self.restore_button.grid(row=0, column=1, padx=(0, 8))
        self.rebuild_button = ttk.Button(actions, text="Rebuild Seed", command=self._start_rebuild)
        self.rebuild_button.grid(row=0, column=2, padx=(0, 8))
        self.diagnostics_button = ttk.Button(
            actions, text="Open Diagnostics", command=self._open_diagnostics
        )
        self.diagnostics_button.grid(row=0, column=3)
        self.plan_button = ttk.Button(
            actions, text="Generate Launch Plan", command=self._generate_plan
        )
        self.plan_button.grid(row=0, column=4, padx=(8, 0))
        self.doctor_button = ttk.Button(actions, text="Doctor", command=self._start_doctor)
        self.doctor_button.grid(row=0, column=5, padx=(8, 0))
        self._action_buttons = (
            self.vanilla_button,
            self.restore_button,
            self.rebuild_button,
            self.diagnostics_button,
            self.doctor_button,
        )
        ttk.Label(outer, textvariable=self.status, style="Muted.TLabel").grid(
            row=6, column=0, sticky="w", pady=(8, 0)
        )

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
        if name == "shad_executable" and not self.fields["game_root"].get().strip():
            derived = derive_game_root_for_shad(selected)
            if derived is not None:
                self.fields["game_root"].set(str(derived))
        if name in {"shad_executable", "game_root"}:
            self._cascade_map_studio()
        if name == "ap_request":
            self._accept_ap_request(selected)

    def _accept_ap_request(self, selected: str) -> None:
        """Resolve the chosen seed file and fill in what it tells us.

        A multiworld zip with exactly one Bloodborne slot also prefills the
        player-name field: the zip already knows whose slot it is, and an
        empty field is what makes the Doctor's slot-agreement check a warning.
        """
        chosen = Path(selected).expanduser()
        if looks_like_archive(chosen) and not self.player_name.get().strip():
            only = archive_player_name(chosen)
            if only is not None:
                self.player_name.set(only)
        try:
            self.enemy_seed.set(
                request_enemy_seed(
                    chosen,
                    player_name=self.player_name.get().strip(),
                    state_root=self._state_root(),
                )
            )
        except LauncherError as exc:
            self.messagebox.showerror("Invalid AP seed file", str(exc), parent=self.root)

    def _cascade_map_studio(self) -> None:
        """Fill the MapStudio source from the game folder when unset."""
        if self.fields["map_studio_source"].get().strip():
            return
        raw = self.fields["game_root"].get().strip()
        if not raw:
            return
        derived = derive_map_studio_for_game_root(raw)
        if derived is not None:
            self.fields["map_studio_source"].set(str(derived))

    def _toggle_enemy_fields(self) -> None:
        state = "normal" if self.randomize_enemies.get() else "disabled"
        for widget in self._enemy_widgets:
            widget.configure(state=state)
        self.launch_button.configure(
            text="Randomize & Launch" if self.randomize_enemies.get() else "Build & Launch"
        )

    def _state_root(self) -> Path:
        """The launcher-owned state directory, whether or not it is typed in."""
        raw = self.fields["state_root"].get().strip()
        return Path(raw).expanduser() if raw else default_state_root()

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
                "ap_server": self.ap_server.get().strip(),
                "player_name": self.player_name.get().strip(),
                "shad_executable": self.fields["shad_executable"].get().strip(),
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
            self.ap_server.set(str(value.get("ap_server", "")))
            self.player_name.set(str(value.get("player_name", "")))
            self.allow_tier_mixing.set(bool(value.get("allow_tier_mixing", False)))
            self.preserve_locomotion.set(bool(value.get("preserve_locomotion", False)))
        except (OSError, UnicodeError, json.JSONDecodeError, LauncherError) as exc:
            self.messagebox.showwarning("Saved setup ignored", str(exc), parent=self.root)

    def _generate_plan(self) -> None:
        try:
            request_raw = self.fields["ap_request"].get().strip()
            if not request_raw:
                raise ValidationError("select the AP seed file first")
            request = _request_identity(
                Path(request_raw).expanduser(),
                player_name=self.player_name.get().strip(),
                state_root=self._state_root(),
            )
            shad_raw = self.fields["shad_executable"].get().strip()
            if not shad_raw:
                raise ValidationError("select the shadPS4 executable")
            client = application_root() / "tools" / "bb-ap-client.exe"
            if not client.is_file():
                raise ValidationError(
                    f"the packaged AP client is missing: {client} "
                    "(from a checkout, use: python -m bb_launcher plan --client ...)"
                )
            state_raw = self.fields["state_root"].get().strip()
            state_root = Path(state_raw).expanduser() if state_raw else default_state_root()
            output = state_root / "process-plan.json"
            document = generate_process_plan(
                shad_executable=shad_raw,
                client_executable=client,
                server=self.ap_server.get().strip() or DEFAULT_SERVER,
                slot=request["slot"],
                runtime_build=request["runtime_build"],
            )
            write_process_plan(output, document, force=True)
            self.fields["process_plan"].set(str(output))
            self.status.set(f"Launch plan generated at {output}")
        except (OSError, LauncherError) as exc:
            self.messagebox.showerror("Could not generate launch plan", str(exc), parent=self.root)

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message.rstrip())

    def _set_status_text(self, text: str) -> None:
        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("end", text.rstrip() + "\n")
        self.status_text.configure(state="disabled")

    def _refresh_status(self) -> None:
        try:
            settings = self._settings()
        except LauncherError:
            self._set_status_text("Finish the setup paths above to see session status.")
            return
        try:
            install = GameInstall.from_root(settings.game_root)
            request = _request_identity(
                settings.ap_request,
                player_name=self.player_name.get().strip(),
                state_root=settings.state_root or default_state_root(),
            )
            readiness = gather_readiness(
                install,
                settings.state_root or default_state_root(),
                seed=request["seed"],
                slot=request["slot"],
            )
        except LauncherError as exc:
            self._set_status_text(f"Status unavailable: {exc}")
            return
        self._set_status_text(format_readiness(readiness))

    def _check_grants_armed(self) -> None:
        """One-shot watchdog: did the CE grant harness ever report in?"""
        try:
            settings = self._settings()
            install = GameInstall.from_root(settings.game_root)
            request = _request_identity(
                settings.ap_request,
                player_name=self.player_name.get().strip(),
                state_root=settings.state_root or default_state_root(),
            )
            readiness = gather_readiness(
                install,
                settings.state_root or default_state_root(),
                seed=request["seed"],
                slot=request["slot"],
            )
        except LauncherError:
            return
        warning = grants_watchdog_warning(readiness, bridge_expected=True)
        if warning is None:
            self._append_log("Item grants armed: the Cheat Engine bridge has reported.")
            self._refresh_status()
            return
        # The popup can be dismissed and the remedy lost; the log keeps it.
        self._append_log("WARNING: item grants are NOT armed -- the CE table has not reported.")
        self._append_log(warning)
        self._refresh_status()
        self.messagebox.showwarning("Item grants not armed", warning, parent=self.root)

    def _progress_message(self, message: str) -> None:
        self.root.after(0, self._append_log, message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.launch_button.configure(state="disabled" if busy else "normal")
        self.save_button.configure(state="disabled" if busy else "normal")
        for button in self._action_buttons:
            button.configure(state="disabled" if busy else "normal")
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
                self.enemy_seed.set(
                    request_enemy_seed(
                        settings.ap_request,
                        player_name=self.player_name.get().strip(),
                        state_root=settings.state_root or default_state_root(),
                    )
                )
            options = EnemizerOptions(
                enabled=self.randomize_enemies.get(),
                seed=self.enemy_seed.get().strip() or None,
                allow_tier_mixing=self.allow_tier_mixing.get(),
                preserve_locomotion=self.preserve_locomotion.get(),
            )
            override = self.allow_suppression_mismatch.get()
            self._save_settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        if not self._confirm_elevation():
            return
        self._set_busy(True)
        self._append_log("Starting Randomize & Launch...")
        threading.Thread(
            target=self._run,
            args=(settings, options, override),
            daemon=True,
            name="bloodborne-randomize-launch",
        ).start()

    def _confirm_elevation(self) -> bool:
        """True to proceed. Nudges when shadPS4 may out-elevate the client."""
        if launcher_is_elevated():
            return True
        raw = self.fields["shad_executable"].get().strip()
        risks = elevation_risks(Path(raw) if raw else None, _process_running)
        if not risks:
            return True
        return self.messagebox.askyesno(
            "Run as administrator?",
            "shadPS4 may start elevated while this launcher is not:\n\n- "
            + "\n- ".join(risks)
            + "\n\nAn unelevated AP client cannot attach to an elevated shadPS4 "
            "and will wait for the game forever. Cancel, restart this launcher "
            "as administrator, and launch again (recommended) -- or continue "
            "anyway?",
            parent=self.root,
        )

    def _setup_for_action(self, label: str) -> LauncherSettings | None:
        try:
            settings = self._settings()
            self._save_settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return None
        self._set_busy(True)
        self._append_log(f"Starting {label}...")
        return settings

    def _run_action(self, label: str, action: Any) -> None:
        try:
            outcome = action()
        except Exception as exc:
            self.root.after(0, self._action_failed, label, exc)
        else:
            self.root.after(0, self._action_finished, label, outcome)

    def _action_failed(self, label: str, exc: Exception) -> None:
        self._set_busy(False)
        self._append_log(f"REFUSED: {exc}")
        self.messagebox.showerror(f"{label} refused", str(exc), parent=self.root)

    def _action_finished(self, label: str, outcome: Any) -> None:
        self._set_busy(False)
        detail = "" if outcome is None else f": {outcome}"
        self._append_log(f"{label} complete{detail}")
        self._refresh_status()

    def _start_doctor(self) -> None:
        """Preflight the whole chain (bb-archipelago#103) without launching."""
        if self._busy:
            return
        try:
            settings = self._settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._set_busy(True)
        self._append_log("Doctor: checking the whole player chain...")
        threading.Thread(
            target=self._run_doctor,
            args=(
                settings,
                self.randomize_enemies.get(),
                self.ap_server.get().strip() or None,
                self.player_name.get().strip() or None,
                self.allow_suppression_mismatch.get(),
            ),
            daemon=True,
            name="bloodborne-doctor",
        ).start()

    def _run_doctor(
        self,
        settings: LauncherSettings,
        randomize_enemies: bool,
        server: str | None,
        player_name: str | None = None,
        allow_suppression_mismatch: bool = False,
    ) -> None:
        try:
            report = run_doctor(
                settings,
                randomize_enemies=randomize_enemies,
                server=server,
                player_name=player_name,
                allow_suppression_mismatch=allow_suppression_mismatch,
            )
            text = format_report(report)
        except Exception as exc:
            self.root.after(0, self._action_failed, "Doctor", exc)
        else:
            self.root.after(0, self._doctor_finished, text, report.ok)

    def _doctor_finished(self, text: str, ok: bool) -> None:
        self._set_busy(False)
        for line in text.splitlines():
            self._append_log(line)
        if not ok:
            self.messagebox.showwarning(
                "Doctor found problems",
                text + "\n\nFix the FAIL lines above and run Doctor again.",
                parent=self.root,
            )

    def _start_vanilla(self) -> None:
        if self._busy:
            return
        settings = self._setup_for_action("Launch Vanilla")
        if settings is None:
            return
        threading.Thread(
            target=self._run_action,
            args=(
                "Launch Vanilla",
                lambda: self.workflow.launch_vanilla(settings, progress=self._progress_message),
            ),
            daemon=True,
            name="bloodborne-launch-vanilla",
        ).start()

    def _start_restore(self) -> None:
        if self._busy:
            return
        settings = self._setup_for_action("Restore Previous")
        if settings is None:
            return
        threading.Thread(
            target=self._run_action,
            args=(
                "Restore Previous",
                lambda: self.workflow.restore_previous(settings, progress=self._progress_message),
            ),
            daemon=True,
            name="bloodborne-restore-previous",
        ).start()

    def _start_rebuild(self) -> None:
        if self._busy:
            return
        if not self.messagebox.askyesno(
            "Rebuild Seed",
            "Evict the verified cache for this seed and build it again from the game files?",
            parent=self.root,
        ):
            return
        try:
            settings = self._settings()
            if not self.enemy_seed.get().strip():
                self.enemy_seed.set(
                    request_enemy_seed(
                        settings.ap_request,
                        player_name=self.player_name.get().strip(),
                        state_root=settings.state_root or default_state_root(),
                    )
                )
            options = EnemizerOptions(
                enabled=self.randomize_enemies.get(),
                seed=self.enemy_seed.get().strip() or None,
                allow_tier_mixing=self.allow_tier_mixing.get(),
                preserve_locomotion=self.preserve_locomotion.get(),
            )
            override = self.allow_suppression_mismatch.get()
            self._save_settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._set_busy(True)
        self._append_log("Starting Rebuild Seed...")
        threading.Thread(
            target=self._run_rebuild,
            args=(settings, options, override),
            daemon=True,
            name="bloodborne-rebuild-seed",
        ).start()

    def _run_rebuild(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        allow_suppression_mismatch: bool = False,
    ) -> None:
        try:
            result = self.workflow.randomize_and_launch(
                settings,
                options,
                force_rebuild=True,
                allow_suppression_mismatch=allow_suppression_mismatch,
                player_name=self.player_name.get().strip(),
                progress=self._progress_message,
            )
        except Exception as exc:
            self.root.after(0, self._failed, exc)
        else:
            self.root.after(0, self._finished, result)

    def _open_diagnostics(self) -> None:
        raw = self.fields["state_root"].get().strip()
        root = Path(raw).expanduser() if raw else default_state_root()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.messagebox.showerror("Could not open diagnostics", str(exc), parent=self.root)
            return
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(root)
        else:
            self.status.set(f"Diagnostics folder: {root}")

    def _run(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        allow_suppression_mismatch: bool = False,
    ) -> None:
        try:
            result = self.workflow.randomize_and_launch(
                settings,
                options,
                allow_suppression_mismatch=allow_suppression_mismatch,
                player_name=self.player_name.get().strip(),
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
        self._append_log(f"Client runtime config: {result.client_config}")
        self._append_log(f"Receive ledger: {result.ledger}")
        client_log = getattr(result, "client_log", None)
        if client_log is not None:
            self._append_log(f"Client log: {client_log}")
        shad_log = getattr(result, "shad_process_log", None)
        if shad_log is not None:
            self._append_log(f"shadPS4 log: {shad_log}")
        self._refresh_status()
        early_exit = getattr(result, "early_exit", None)
        if early_exit is not None:
            # The overlay is active but the component died at startup: report
            # what it said instead of the success popup (bb-archipelago#171).
            # The title names the component that actually died -- a hardcoded
            # client title blamed the client for a shadPS4 crash
            # (bb-archipelago#175).
            report = early_exit.describe()
            self._append_log(f"EARLY EXIT: {report}")
            self.messagebox.showerror(
                f"{early_exit.name} stopped",
                report,
                parent=self.root,
            )
            return
        if result.grants_bridge:
            self._append_log(
                "Item grants expected: watching for the Cheat Engine bridge to report..."
            )
            self.root.after(GRANT_WATCHDOG_MS, self._check_grants_armed)
        self.messagebox.showinfo(
            "Bloodborne AP started",
            f"Verified overlay {result.cache_key[:12]} is active.\n{mode.capitalize()}.\n"
            f"Client config: {result.client_config}",
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
