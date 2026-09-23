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
from .readiness import (
    format_client_health,
    format_readiness,
    gather_readiness,
    grants_watchdog_warning,
)
from .resources import application_root, resource_root
from .seed_request import (
    archive_player_name,
    archive_slots,
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
    ("ap_request", "Seed file", "file"),
    ("game_root", "Game folder", "directory"),
    ("suppression_binder", "Suppressed gameparam", "file"),
    ("suppression_manifest", "Suppression manifest", "file"),
    ("map_studio_source", "Source MapStudio", "directory"),
    ("enemy_inventory", "Enemy inventory", "file"),
    ("soulsformats_next", "SoulsFormatsNEXT", "directory"),
    ("process_plan", "Launch plan", "file"),
    ("shad_executable", "shadPS4", "file"),
    ("cache_root", "Seed cache", "directory"),
    ("state_root", "Launcher state", "directory"),
    ("shad_log", "shadPS4 log", "file"),
)
DEVELOPMENT_FIELDS = {"enemy_inventory", "soulsformats_next"}
# The empty-state line under the seed row names both shapes the field accepts.
SEED_PROMPT = "Choose a seed (.zip or .bbseed.json) to see its player and build."
PRIMARY_FIELDS = {"ap_request", "game_root", "shad_executable"}
ENEMY_FIELDS = {"map_studio_source", "enemy_inventory", "soulsformats_next"}

# The palette and every ttk style live in ``theme``; this module only lays
# widgets out.
from .theme import (  # noqa: E402
    Sidebar, apply_theme, autohide, field, option, page_header, scroll_page, section,
    text_well,
)
from .version import launcher_version  # noqa: E402


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


def repair_stale_packaged_suppression_paths(
    current: Mapping[str, str], derived: Mapping[str, str]
) -> dict[str, str]:
    """Replace a vanished saved suppression pair with this package's pair.

    Settings outlive extracted playtest directories. A saved binder/manifest
    path can therefore point into yesterday's deleted package even though the
    current package ships a verified replacement under ``work``. Keep valid
    operator-selected paths, but repair the pair atomically when either saved
    file has disappeared so binder and manifest can never come from different
    builds.
    """
    names = ("suppression_binder", "suppression_manifest")
    if not all(name in derived for name in names):
        return {}
    missing = any(
        not current.get(name, "").strip()
        or not Path(current[name]).expanduser().is_file()
        for name in names
    )
    return {name: derived[name] for name in names} if missing else {}


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
        from tkinter import filedialog, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        # A themed drop-in for tkinter.messagebox: same call shape, no
        # white OS-chrome popup flashing against the dark body.
        self.messagebox = Dialogs(tk, ttk, self.root)
        self.root = root
        self.repo_root = repo_root.resolve()
        self.settings_path = settings_path.expanduser().resolve()
        self.workflow = LauncherWorkflow(self.repo_root)
        self.packaged_toolchain = self.workflow.toolchain.is_bundled
        self.fields = {name: tk.StringVar() for name, _label, _kind in FIELD_DEFINITIONS}
        self.randomize_enemies = tk.BooleanVar(value=True)
        self.show_enemy_advanced = tk.BooleanVar(value=False)
        self.enemy_seed = tk.StringVar()
        self.ap_server = tk.StringVar()
        self.player_name = tk.StringVar()
        self.seed_summary = tk.StringVar(value=SEED_PROMPT)
        self.launch_hint = tk.StringVar(value="Choose a seed and shadPS4 to continue.")
        self.allow_tier_mixing = tk.BooleanVar(value=False)
        self.preserve_locomotion = tk.BooleanVar(value=False)
        self.normalize_scaling = tk.BooleanVar(value=False)
        self.boss_canary = tk.BooleanVar(value=False)
        self.boss_pool = tk.BooleanVar(value=False)
        # Operator override (bb-archipelago#183).  Deliberately absent from
        # _save_settings and _load_settings_if_present: it is per-session by
        # construction, so it can never be left on and forgotten.
        self.allow_suppression_mismatch = tk.BooleanVar(value=False)
        # Same per-session-only contract as allow_suppression_mismatch, for
        # the AP seed/slot identity check (bb-archipelago#347): a stale
        # saved server address must require a deliberate, un-persisted
        # override every time, never a setting left on and forgotten.
        self.allow_seed_mismatch = tk.BooleanVar(value=False)
        # Diagnostic probes are an explicit, per-session playtest aid.
        self.research_captures = tk.BooleanVar(value=False)
        self.show_session_details = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="")
        self.client_health = tk.StringVar(value="Client: not running (no live status)")
        self._health_monitoring = False
        self._enemy_widgets: list[Any] = []
        self._enemy_advanced_widgets: list[Any] = []
        self._busy = False

        root.title("Bloodborne Archipelago")
        root.minsize(960, 680)
        root.geometry("1080x760")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        self._apply_theme()
        self._build()
        self._show_player_choice(False)
        self._load_settings_if_present()
        self._apply_default_fields()
        remembered_seed = self.fields["ap_request"].get().strip()
        if remembered_seed:
            self._accept_ap_request(remembered_seed, show_error=False)
        self._last_path_field_values = {
            name: self.fields[name].get().strip() for name in PRIMARY_FIELDS
        }
        self._toggle_enemy_fields()
        self._toggle_enemy_advanced()
        self._refresh_launch_gate()
        self.root.after(0, self._refresh_status)

    def _apply_theme(self) -> None:
        """Every colour, font and ttk style comes from ``theme``; nothing is
        configured ad hoc here, so the pages cannot drift from the palette."""
        apply_theme(self.root, self.ttk)
        enable_dark_titlebar(self.root)

    def _apply_default_fields(self) -> None:
        """Fill derived fields and repair suppression paths from old packages."""
        derived = default_field_values(
            state_root=default_state_root(),
            package_roots=(application_root(), resource_root()),
            repo_root=self.repo_root,
            player_name=self.player_name.get(),
        )
        current = {name: variable.get() for name, variable in self.fields.items()}
        repairs = repair_stale_packaged_suppression_paths(current, derived)
        for name, value in derived.items():
            if name in repairs:
                self.fields[name].set(repairs[name])
                continue
            if not self.fields[name].get().strip():
                self.fields[name].set(value)

    def _build(self) -> None:
        tk, ttk = self.tk, self.ttk
        shell = ttk.Frame(self.root)
        shell.grid(row=0, column=0, sticky="nsew")
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        # The content column. The pages stretch and carry a floor
        # (bb-archipelago#190): a short display must never crush the page to
        # zero height. The details drawer (rows 1-2) only takes weight while it
        # is shown, so a collapsed drawer costs the pages nothing.
        outer = ttk.Frame(shell)
        outer.grid(row=0, column=1, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1, minsize=240)
        outer.rowconfigure(1, weight=0, minsize=0)

        notebook = ttk.Notebook(outer, style="Pages.TNotebook")
        notebook.grid(row=0, column=0, sticky="nsew")
        self.notebook = notebook

        # --- Play ---------------------------------------------------------
        setup = ttk.Frame(notebook)
        notebook.add(setup, text="Play")
        self.play_tab = setup
        play = scroll_page(tk, ttk, setup)
        play_row = page_header(ttk, play, "Play", "Choose your seed and your shadPS4 install, then launch.")
        play_row = section(ttk, play, play_row, "Seed", first=True)
        seed_row, play_row = play_row, play_row + 1
        name_row, play_row = play_row, play_row + 1
        server_row, play_row = play_row, play_row + 1
        summary_row, play_row = play_row, play_row + 1
        play_row = section(ttk, play, play_row, "Game")
        game_rows = {"game_root": play_row, "shad_executable": play_row + 1}
        primary_rows = {"ap_request": seed_row, **game_rows}

        # --- Enemies ------------------------------------------------------
        options_host = ttk.Frame(notebook)
        notebook.add(options_host, text="Enemies")
        options = scroll_page(tk, ttk, options_host)
        enemy_row = page_header(
            ttk, options, "Enemies", "Applied on the next build. Changing these rebuilds the seed.",
        )
        randomize, _randomize_row = option(
            ttk, options, enemy_row, "Randomize enemies", self.randomize_enemies,
            caption="Every enemy is redrawn from the seed. Off keeps vanilla placement.",
            command=self._toggle_enemy_fields,
        )
        enemy_row += 1
        advanced_toggle, _advanced_toggle_row = option(
            ttk, options, enemy_row, "Advanced enemy options", self.show_enemy_advanced,
            command=self._toggle_enemy_advanced,
        )
        enemy_row += 1
        # One frame holds everything the toggle discloses, so a caption can
        # never be left behind by its control.
        advanced = ttk.Frame(options)
        advanced.grid(row=enemy_row, column=0, columnspan=3, sticky="ew")
        advanced.columnconfigure(1, weight=1)
        self._enemy_advanced_widgets = [advanced]
        advanced_row = section(ttk, advanced, 0, "Seed")
        seed_label, seed_entry, _ = field(
            ttk, advanced, advanced_row, "Enemy seed", self.enemy_seed,
            trailing="from the AP seed when blank",
        )
        advanced_row = section(ttk, advanced, advanced_row + 1, "Experimental")
        tier, _tier_row = option(
            ttk, advanced, advanced_row, "Allow tier mixing", self.allow_tier_mixing,
            caption="Replacements may come from a different difficulty tier.",
        )
        locomotion, _locomotion_row = option(
            ttk, advanced, advanced_row + 1, "Preserve locomotion", self.preserve_locomotion,
            caption="Keep each slot's movement class. Tags are incomplete.",
        )
        scaling, _scaling_row = option(
            ttk, advanced, advanced_row + 2, "Normalize enemy stats", self.normalize_scaling,
            caption="Scale replacements to the slot they fill. Playtest only.",
        )
        boss, _boss_row = option(
            ttk, advanced, advanced_row + 3, "Boss playtest: BSB at Cleric Beast", self.boss_canary,
            caption="Only that swap, with scaling. Other enemies unchanged.",
        )
        pool, _pool_row = option(
            ttk, advanced, advanced_row + 4, "Boss shuffle (reviewed encounters)", self.boss_pool,
            caption="Gameplay untested.",
        )
        advanced_row = section(ttk, advanced, advanced_row + 5, "Build inputs")
        enemy_inputs = ttk.Frame(advanced)
        enemy_inputs.grid(row=advanced_row, column=0, columnspan=3, sticky="ew")
        enemy_inputs.columnconfigure(1, weight=1)

        # --- Create & host (inserts itself at index 1) --------------------
        from .local_session_ui import LocalSessionPanel
        self.local_session_panel = LocalSessionPanel(self, notebook)

        # --- Advanced -----------------------------------------------------
        advanced_host = ttk.Frame(notebook)
        notebook.add(advanced_host, text="Advanced")
        troubleshooting = scroll_page(tk, ttk, advanced_host)
        troubleshooting_row = page_header(
            ttk, troubleshooting, "Advanced",
            "Recovery tools, BBLauncher mode and operator paths. A normal launch needs none of this.",
        )
        troubleshooting_row = section(ttk, troubleshooting, troubleshooting_row, "Recovery", first=True)
        actions = ttk.Frame(troubleshooting)
        actions.grid(row=troubleshooting_row, column=0, columnspan=3, sticky="ew")
        troubleshooting_row += 1
        self.doctor_button = ttk.Button(actions, text="Check Setup", command=self._start_doctor)
        self.vanilla_button = ttk.Button(actions, text="Launch Vanilla", command=self._start_vanilla)
        self.restore_button = ttk.Button(actions, text="Undo Last Build", command=self._start_restore)
        self.rebuild_button = ttk.Button(actions, text="Rebuild", command=self._start_rebuild)
        self.diagnostics_button = ttk.Button(
            actions, text="Open Diagnostics", command=self._open_diagnostics
        )
        self.report_button = ttk.Button(
            actions, text="Report a Bad Enemy", command=self._start_enemy_report
        )
        for index, button in enumerate((
            self.doctor_button, self.vanilla_button, self.restore_button,
            self.rebuild_button, self.diagnostics_button, self.report_button,
        )):
            button.grid(row=index // 3, column=index % 3, sticky="ew",
                        padx=(0 if index % 3 == 0 else 8, 0), pady=(0, 8))
        for column in range(3):
            actions.columnconfigure(column, weight=1, uniform="recovery")
        ttk.Label(
            troubleshooting,
            text="Report a Bad Enemy writes a paste-ready list of every swap in the area "
                 "you were in, for a stuck, invisible or endlessly dying enemy.",
            style="Dim.TLabel", wraplength=640,
        ).grid(row=troubleshooting_row, column=0, columnspan=3, sticky="w")
        troubleshooting_row += 1

        troubleshooting_row = section(ttk, troubleshooting, troubleshooting_row, "BBLauncher mode")
        bblauncher = ttk.Frame(troubleshooting)
        bblauncher.grid(row=troubleshooting_row, column=0, columnspan=3, sticky="ew")
        troubleshooting_row += 1
        from .external_ui import BBLauncherPanel
        self.bblauncher_panel = BBLauncherPanel(self, bblauncher)

        # Session overrides (suppression-binder mismatch, seed/slot mismatch,
        # research captures) retired from the GUI: they were operator-only,
        # never-saved escape hatches that had outlived their usefulness here.
        # The vars stay permanently False now that nothing sets them; the CLI
        # doctor command (--allow-suppression-mismatch, --allow-seed-mismatch)
        # remains the way to invoke them when genuinely needed.
        troubleshooting_row = section(ttk, troubleshooting, troubleshooting_row, "Paths")
        paths = ttk.Frame(troubleshooting)
        paths.grid(row=troubleshooting_row, column=0, columnspan=3, sticky="ew")
        paths.columnconfigure(1, weight=1)

        # Player choices stay on Play, enemizer inputs live with their toggle,
        # and launcher-owned/operator paths sit under Advanced. Same variables
        # and browse commands; only their presentation changes.
        enemy_input_row = 0
        path_row = 0
        for name, label, kind in FIELD_DEFINITIONS:
            if self.packaged_toolchain and name in DEVELOPMENT_FIELDS:
                continue
            if name in ENEMY_FIELDS:
                parent, row = enemy_inputs, enemy_input_row
                enemy_input_row += 1
            elif name in PRIMARY_FIELDS:
                parent, row = play, primary_rows[name]
            else:
                parent, row = paths, path_row
                path_row += 1
            field_label, entry, button = field(
                ttk, parent, row, label, self.fields[name],
                browse=lambda key=name, selector=kind: self._browse(key, selector),
            )
            if name in PRIMARY_FIELDS:
                entry.bind(
                    "<FocusOut>",
                    lambda _event, key=name: self._path_field_changed(key),
                )
                entry.bind(
                    "<Return>",
                    lambda _event, key=name: self._path_field_changed(key, force=True),
                )
            if name in ENEMY_FIELDS:
                self._enemy_widgets.extend((entry, button))

        _server_label, server_entry, _ = field(
            ttk, play, server_row, "Server", self.ap_server, trailing=f"default {DEFAULT_SERVER}",
        )
        server_entry.bind("<FocusOut>", self._setup_changed)
        server_entry.bind("<Return>", self._setup_changed)
        self.player_label = ttk.Label(play, text="Player", style="Field.TLabel")
        self.player_label.grid(row=name_row, column=0, sticky="w", padx=(0, 14), pady=4)
        self.player_combo = ttk.Combobox(
            play, textvariable=self.player_name, state="readonly", values=()
        )
        self.player_combo.grid(row=name_row, column=1, sticky="ew", pady=4)
        self.player_combo.bind("<<ComboboxSelected>>", self._player_selected)
        self.player_help = ttk.Label(play, text="from the seed", style="Dim.TLabel")
        self.player_help.grid(row=name_row, column=2, sticky="w", padx=(10, 0))
        ttk.Label(play, textvariable=self.seed_summary, style="Muted.TLabel").grid(
            row=summary_row, column=0, columnspan=3, sticky="w", pady=(6, 0)
        )

        self._enemy_widgets.extend((seed_entry, tier, locomotion))
        self._enemy_widgets.extend((scaling, boss, pool))

        # --- Details drawer: launch progress and session status ------------
        # Outside the notebook so no page can hide it (bb-archipelago#190).
        log_frame = ttk.Frame(outer, padding=(28, 8, 28, 0))
        self.log_frame = log_frame
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)
        ttk.Label(log_frame, text="Progress", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.log = text_well(tk, log_frame, height=5)
        self.log.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.log.configure(yscrollcommand=autohide(scrollbar))

        status_frame = ttk.Frame(outer, padding=(28, 10, 28, 0))
        self.status_frame = status_frame
        status_frame.grid(row=2, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        ttk.Label(status_frame, text="Session status", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        refresh_button = ttk.Button(
            status_frame, text="Refresh", command=self._refresh_status, style="Link.TButton"
        )
        refresh_button.grid(row=0, column=1, columnspan=2, sticky="e")
        self.status_text = text_well(tk, status_frame, height=4)
        self.status_text.grid(row=1, column=0, columnspan=2, sticky="ew")
        status_scroll = ttk.Scrollbar(status_frame, orient="vertical", command=self.status_text.yview)
        status_scroll.grid(row=1, column=2, sticky="ns")
        self.status_text.configure(yscrollcommand=autohide(status_scroll))

        # --- Action bar -----------------------------------------------------
        controls = ttk.Frame(outer, padding=(28, 0, 28, 18))
        controls.grid(row=3, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        ttk.Frame(controls, height=1, style="Panel.TFrame").grid(
            row=0, column=0, columnspan=4, sticky="ew"
        )
        self.progress = ttk.Progressbar(controls, mode="indeterminate")
        self.progress.grid(row=1, column=0, columnspan=4, sticky="ew")
        self.progress.grid_remove()
        self.details_button = ttk.Button(
            controls, text="Show Details", command=self._toggle_session_details, style="Link.TButton"
        )
        self.details_button.grid(row=2, column=1, sticky="e", padx=(12, 12), pady=(14, 0))
        self.connect_button = ttk.Button(
            controls, text="Connect to running game", command=self._start_connect, style="Ghost.TButton",
        )
        self.connect_button.grid(row=2, column=2, sticky="e", padx=(0, 10), pady=(14, 0))
        self.launch_button = ttk.Button(
            controls,
            text="Randomize & Launch",
            command=self._start,
            style="Accent.TButton",
        )
        self.launch_button.grid(row=2, column=3, sticky="e", pady=(14, 0))
        # What the primary button is waiting for, then the last progress line
        # so a collapsed drawer still says what happened.
        hint = ttk.Label(controls, textvariable=self.launch_hint, style="Muted.TLabel", wraplength=600)
        hint.grid(row=3, column=0, columnspan=4, sticky="w", pady=(10, 0))
        status_line = ttk.Label(controls, textvariable=self.status, style="Dim.TLabel", wraplength=600)
        status_line.grid(row=4, column=0, columnspan=4, sticky="w", pady=(2, 0))

        def _fit_action_bar(event) -> None:
            for label in (hint, status_line):
                label.configure(wraplength=max(300, event.width - 56))
        controls.bind("<Configure>", _fit_action_bar, add="+")
        self._action_buttons = (
            self.connect_button,
            self.vanilla_button,
            self.restore_button,
            self.rebuild_button,
            self.diagnostics_button,
            self.doctor_button,
            self.report_button,
        )

        # --- Sidebar --------------------------------------------------------
        self.sidebar = Sidebar(
            tk, ttk, shell, notebook, brand="Bloodborne", product="Archipelago",
            version=launcher_version(),
        )
        self.sidebar.populate()
        self.client_health.trace_add(
            "write", lambda *_args: self.sidebar.set_health(self.client_health.get())
        )
        self.sidebar.set_health(self.client_health.get())
        self._set_session_details_visible(False)

    def _set_session_details_visible(self, visible: bool) -> None:
        """Keep routine launches compact; retain full evidence one click away."""
        self.show_session_details.set(visible)
        if visible:
            self.log_frame.grid()
            self.status_frame.grid()
            self.details_button.configure(text="Hide Details")
        else:
            self.log_frame.grid_remove()
            self.status_frame.grid_remove()
            self.details_button.configure(text="Show Details")
        self.log_frame.master.rowconfigure(1, weight=2 if visible else 0, minsize=120 if visible else 0)

    def _toggle_session_details(self) -> None:
        self._set_session_details_visible(not self.show_session_details.get())

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
        self._last_path_field_values[name] = selected.strip()
        if name == "shad_executable" and not self.fields["game_root"].get().strip():
            derived = derive_game_root_for_shad(selected)
            if derived is not None:
                self.fields["game_root"].set(str(derived))
        if name in {"shad_executable", "game_root"}:
            self._cascade_map_studio()
        if name == "ap_request":
            self._accept_ap_request(selected)
        self._refresh_status()
        self._refresh_launch_gate()

    def _accept_ap_request(self, selected: str, *, show_error: bool = True) -> None:
        """Resolve the chosen seed file and fill in what it tells us.

        A multiworld zip with exactly one Bloodborne slot also prefills the
        player-name field: the zip already knows whose slot it is, and an
        empty field is what makes the Doctor's slot-agreement check a warning.
        """
        chosen = Path(selected).expanduser()
        if looks_like_archive(chosen):
            try:
                names = tuple(sorted({name for _member, name in archive_slots(chosen)}))
            except LauncherError as exc:
                if show_error:
                    self.messagebox.showerror("Invalid AP seed file", str(exc), parent=self.root)
                return
        else:
            detected = _request_player_name(chosen)
            names = () if detected is None else (detected,)
        self.player_combo.configure(values=names)
        self._show_player_choice(len(names) > 1)
        if len(names) == 1:
            self.player_name.set(names[0])
        elif self.player_name.get().strip() not in names:
            self.player_name.set("")
        if len(names) > 1 and not self.player_name.get().strip():
            self.seed_summary.set("Choose which Bloodborne player you are.")
            self._refresh_launch_gate()
            return
        try:
            self.enemy_seed.set(
                request_enemy_seed(
                    chosen,
                    player_name=self.player_name.get().strip(),
                    state_root=self._state_root(),
                )
            )
            request = _request_identity(
                chosen,
                player_name=self.player_name.get().strip(),
                state_root=self._state_root(),
            )
            self.seed_summary.set(
                f"Player {request['slot']} · seed {request['seed']} · "
                f"runtime {request['runtime_build']}"
            )
        except LauncherError as exc:
            if show_error:
                self.messagebox.showerror("Invalid AP seed file", str(exc), parent=self.root)
        self._refresh_launch_gate()

    def _player_selected(self, _event: Any = None) -> None:
        selected = self.fields["ap_request"].get().strip()
        if selected:
            self._accept_ap_request(selected)
        self._refresh_status()
        self._refresh_launch_gate()

    def _setup_changed(self, _event: Any = None) -> None:
        self._refresh_status()
        self._refresh_launch_gate()

    def _path_field_changed(self, name: str, *, force: bool = False) -> None:
        """Apply the same derived setup updates after a path is pasted or typed."""
        selected = self.fields[name].get().strip()
        remembered = getattr(self, "_last_path_field_values", {})
        if not force and remembered.get(name) == selected:
            self._refresh_status()
            self._refresh_launch_gate()
            return
        remembered[name] = selected
        self._last_path_field_values = remembered
        if name == "ap_request":
            if selected:
                self._accept_ap_request(selected, show_error=False)
            else:
                self.player_combo.configure(values=())
                self._show_player_choice(False)
                self.player_name.set("")
                self.enemy_seed.set("")
                self.seed_summary.set(SEED_PROMPT)
            # _accept_ap_request can return early for an unreadable archive.
            # Passive focus changes still have to disable launch immediately.
            self._refresh_launch_gate()
            self._refresh_status()
            return
        if name == "shad_executable" and not self.fields["game_root"].get().strip():
            if selected:
                derived = derive_game_root_for_shad(selected)
                if derived is not None:
                    self.fields["game_root"].set(str(derived))
        if name in {"shad_executable", "game_root"}:
            self._cascade_map_studio()
        self._refresh_status()
        self._refresh_launch_gate()

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

    def _toggle_enemy_advanced(self) -> None:
        visible = self.show_enemy_advanced.get()
        for widget in self._enemy_advanced_widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _show_player_choice(self, visible: bool) -> None:
        for widget in (self.player_label, self.player_combo, self.player_help):
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _refresh_launch_gate(self) -> None:
        panel = getattr(self, "bblauncher_panel", None)
        if panel and panel.enabled.get():
            self.launch_hint.set("BBLauncher mode: use the BBLauncher tab to export, verify, and connect.")
            self.launch_button.configure(state="disabled")
            return
        required = (
            ("AP seed", self.fields["ap_request"].get().strip()),
            ("shadPS4", self.fields["shad_executable"].get().strip()),
            ("game folder", self.fields["game_root"].get().strip()),
        )
        missing = [label for label, value in required if not value]
        raw_seed = self.fields["ap_request"].get().strip()
        if raw_seed and looks_like_archive(raw_seed):
            try:
                if len(archive_slots(Path(raw_seed).expanduser())) > 1 and not self.player_name.get().strip():
                    missing.append("player")
            except LauncherError:
                missing.append("valid seed")
        if missing:
            self.launch_hint.set("Needed: " + ", ".join(missing) + ".")
            self.launch_button.configure(state="disabled")
        else:
            self.launch_hint.set("Ready to validate and launch.")
            if not self._busy:
                self.launch_button.configure(state="normal")

    def _state_root(self) -> Path:
        """The launcher-owned state directory, whether or not it is typed in."""
        raw = self.fields["state_root"].get().strip()
        return Path(raw).expanduser() if raw else default_state_root()

    def _settings(self) -> LauncherSettings:
        settings = settings_from_fields({name: variable.get() for name, variable in self.fields.items()})
        panel = getattr(self, "bblauncher_panel", None)
        return panel.settings(settings) if panel else settings

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
                "normalize_scaling": self.normalize_scaling.get(),
                "boss_canary": self.boss_canary.get(),
                "boss_pool": self.boss_pool.get(),
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
            panel = getattr(self, "bblauncher_panel", None)
            if panel:
                panel.load(value)
            self.randomize_enemies.set(bool(value.get("randomize_enemies", True)))
            self.enemy_seed.set(str(value.get("enemy_seed", "")))
            self.ap_server.set(str(value.get("ap_server", "")))
            self.player_name.set(str(value.get("player_name", "")))
            self.allow_tier_mixing.set(bool(value.get("allow_tier_mixing", False)))
            self.preserve_locomotion.set(bool(value.get("preserve_locomotion", False)))
            self.normalize_scaling.set(bool(value.get("normalize_scaling", False)))
            self.boss_canary.set(bool(value.get("boss_canary", False)))
            self.boss_pool.set(bool(value.get("boss_pool", False)))
        except (OSError, UnicodeError, json.JSONDecodeError, LauncherError) as exc:
            self.messagebox.showwarning("Saved setup ignored", str(exc), parent=self.root)

    def _generate_plan(self, *, show_error: bool = True) -> bool:
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
            self._append_log("Prepared the launch components automatically.")
            return True
        except (OSError, LauncherError) as exc:
            if show_error:
                self.messagebox.showerror(
                    "Could not prepare launch", str(exc), parent=self.root
                )
            return False

    def _append_log(self, message: str) -> None:
        if message.lstrip().upper().startswith(("REFUSED", "WARNING", "EARLY EXIT", "ERROR")):
            self._set_session_details_visible(True)
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status.set(message.rstrip())

    def _set_status_text(self, text: str) -> None:
        if text.startswith("Status unavailable:"):
            self._set_session_details_visible(True)
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
        panel = getattr(self, "bblauncher_panel", None)
        if panel and panel.enabled.get():
            panel.refresh_status(settings)
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
        self.client_health.set(format_client_health(readiness))

    def _refresh_live_health(self) -> None:
        """Refresh the heartbeat while a launched session may still be alive."""
        if not getattr(self, "_health_monitoring", False):
            return
        self._refresh_status()
        self.root.after(2000, lambda: LauncherApp._refresh_live_health(self))

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
        panel = getattr(self, "bblauncher_panel", None)
        if panel is not None:
            panel.update_setup()
        self.launch_button.configure(state="disabled" if busy else "normal")
        for button in self._action_buttons:
            button.configure(state="disabled" if busy else "normal")
        if busy:
            self.progress.grid()
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.grid_remove()
            self._refresh_launch_gate()

    def _start(self) -> None:
        if self._busy:
            return
        if not self._generate_plan():
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
                normalize_scaling=self.normalize_scaling.get(),
                boss_canary=self.boss_canary.get(),
                boss_pool="reviewed" if self.boss_pool.get() else None,
            )
            override = self.allow_suppression_mismatch.get()
            seed_mismatch_override = self.allow_seed_mismatch.get()
            research_captures = self.research_captures.get()
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
            args=(settings, options, override, research_captures, seed_mismatch_override),
            daemon=True,
            name="bloodborne-randomize-launch",
        ).start()

    def _start_connect(self) -> None:
        """Start only the AP client; the backend verifies the installed seed."""
        panel = getattr(self, "bblauncher_panel", None)
        if panel and panel.enabled.get():
            panel.start("connect")
            return
        if self._busy or not self._generate_plan():
            return
        try:
            settings = self._settings()
            player = self.player_name.get().strip()
            captures = self.research_captures.get()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._save_settings()
        self._set_busy(True)
        self._append_log("Connecting the AP client to the running game...")
        def connect():
            try:
                result = self.workflow.connect_to_running(
                    settings, player_name=player, research_captures=captures,
                    progress=self._progress_message,
                )
            except Exception as exc:
                self.root.after(0, self._action_failed, "Connect to running game", exc)
            else:
                self.root.after(0, lambda: self._finished(result, action="Client connection"))
        threading.Thread(target=connect, daemon=True, name="bloodborne-client-connect").start()

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
        if label == "Launch Vanilla" and not self._generate_plan():
            return None
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

    def _start_enemy_report(self) -> None:
        """Write a paste-ready bad-enemy report from the retained plan (bb-archipelago#321)."""
        if self._busy:
            return
        try:
            settings = self._settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        choice = self._ask_enemy_report_details()
        if choice is None:
            return
        area, echoes, note = choice
        self._set_busy(True)
        self._append_log("Writing the enemy report from the active seed's plan...")
        threading.Thread(
            target=self._run_enemy_report,
            args=(settings, area, echoes, note, self.player_name.get().strip()),
            daemon=True,
            name="bloodborne-enemy-report",
        ).start()

    def _ask_enemy_report_details(self) -> tuple[str | None, int | None, str] | None:
        """A small modal: which area, the echoes seen (optional), and a note."""
        from tkinter import ttk

        from .enemy_report import MAP_AREAS

        from .theme import THEME_BACKGROUND, THEME_BORDER, THEME_FOREGROUND, THEME_PANEL

        tk = self.tk
        dialog = tk.Toplevel(self.root)
        dialog.title("Report a Bad Enemy")
        dialog.transient(self.root)
        dialog.configure(bg=THEME_BACKGROUND)
        dialog.resizable(False, False)
        enable_dark_titlebar(dialog)
        frame = ttk.Frame(dialog, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Where were you?").grid(row=0, column=0, sticky="w", pady=4)
        labels = ["All areas"] + [f"{name} ({key})" for key, name in MAP_AREAS.items()]
        area_var = tk.StringVar(value=labels[0])
        ttk.Combobox(
            frame, textvariable=area_var, values=labels, state="readonly", width=38
        ).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text="Echoes awarded (if any)").grid(row=1, column=0, sticky="w", pady=4)
        echoes_var = tk.StringVar()
        ttk.Entry(frame, textvariable=echoes_var, width=12).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(frame, text="What did you see?").grid(row=2, column=0, sticky="nw", pady=4)
        note = tk.Text(
            frame, height=4, width=44, wrap="word", relief="flat", borderwidth=1,
            highlightthickness=1, highlightbackground=THEME_BORDER, highlightcolor=THEME_BORDER,
            bg=THEME_PANEL, fg=THEME_FOREGROUND, insertbackground=THEME_FOREGROUND,
        )
        note.grid(row=2, column=1, sticky="ew", pady=4)
        result: dict[str, Any] = {}

        def accept() -> None:
            raw = echoes_var.get().strip().replace(",", "")
            echoes = None
            if raw:
                if not raw.isdigit():
                    self.messagebox.showerror(
                        "Report a Bad Enemy", "Echoes must be a whole number.", parent=dialog
                    )
                    return
                echoes = int(raw)
            chosen = area_var.get()
            area = None
            if chosen != labels[0]:
                area = chosen.rsplit("(", 1)[1].rstrip(")")
            result["value"] = (area, echoes, note.get("1.0", "end").strip())
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(buttons, text="Write Report", command=accept, style="Accent.TButton").grid(
            row=0, column=1
        )
        dialog.grab_set()
        self.root.wait_window(dialog)
        return result.get("value")

    def _run_enemy_report(
        self,
        settings: LauncherSettings,
        area: str | None,
        echoes: int | None,
        note: str,
        player_name: str,
    ) -> None:
        from .enemy_report import format_report, load_context, write_report

        try:
            context = load_context(settings, player_name=player_name)
            text = format_report(context, area=area, echoes=echoes, note=note)
            path = write_report(settings.state_root or default_state_root(), text)
        except Exception as exc:
            self.root.after(0, self._action_failed, "Report a Bad Enemy", exc)
        else:
            self.root.after(0, self._enemy_report_finished, path, text)

    def _enemy_report_finished(self, path: Path, text: str) -> None:
        self._set_busy(False)
        self._append_log(f"Enemy report written: {path}")
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            copied = " It is on your clipboard too."
        except Exception:  # noqa: BLE001 - clipboard is a convenience, never a failure
            copied = ""
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            try:
                startfile(path)
            except OSError:
                pass
        self.messagebox.showinfo(
            "Report a Bad Enemy",
            f"Report saved to {path}.{copied}\n\nPaste it into a new GitHub issue or the "
            "playtest channel and add anything else you noticed.",
            parent=self.root,
        )

    def _start_doctor(self) -> None:
        """Preflight the whole chain (bb-archipelago#103) without launching."""
        if self._busy:
            return
        if not self._generate_plan():
            return
        try:
            settings = self._settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._set_busy(True)
        self._append_log("Checking the whole player chain...")
        threading.Thread(
            target=self._run_doctor,
            args=(
                settings,
                self.randomize_enemies.get(),
                self.ap_server.get().strip() or None,
                self.player_name.get().strip() or None,
                self.allow_suppression_mismatch.get(),
                self.allow_seed_mismatch.get(),
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
        allow_seed_mismatch: bool = False,
    ) -> None:
        try:
            report = run_doctor(
                settings,
                randomize_enemies=randomize_enemies,
                server=server,
                player_name=player_name,
                allow_suppression_mismatch=allow_suppression_mismatch,
                allow_seed_mismatch=allow_seed_mismatch,
            )
            text = format_report(report)
        except Exception as exc:
            self.root.after(0, self._action_failed, "Check Setup", exc)
        else:
            self.root.after(0, self._doctor_finished, text, report.ok)

    def _doctor_finished(self, text: str, ok: bool) -> None:
        self._set_busy(False)
        for line in text.splitlines():
            self._append_log(line)
        if not ok:
            self.messagebox.showwarning(
                "Setup problems found",
                text + "\n\nFix the FAIL lines above and run Check Setup again.",
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
        settings = self._setup_for_action("Undo Last Build")
        if settings is None:
            return
        threading.Thread(
            target=self._run_action,
            args=(
                "Undo Last Build",
                lambda: self.workflow.restore_previous(settings, progress=self._progress_message),
            ),
            daemon=True,
            name="bloodborne-restore-previous",
        ).start()

    def _start_rebuild(self) -> None:
        if self._busy:
            return
        if not self._generate_plan():
            return
        if not self.messagebox.askyesno(
            "Rebuild",
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
                normalize_scaling=self.normalize_scaling.get(),
                boss_canary=self.boss_canary.get(),
                boss_pool="reviewed" if self.boss_pool.get() else None,
            )
            override = self.allow_suppression_mismatch.get()
            seed_mismatch_override = self.allow_seed_mismatch.get()
            research_captures = self.research_captures.get()
            self._save_settings()
        except LauncherError as exc:
            self.messagebox.showerror("Setup incomplete", str(exc), parent=self.root)
            return
        self._set_busy(True)
        self._append_log("Starting Rebuild...")
        threading.Thread(
            target=self._run_rebuild,
            args=(settings, options, override, research_captures, seed_mismatch_override),
            daemon=True,
            name="bloodborne-rebuild-seed",
        ).start()

    def _run_rebuild(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        allow_suppression_mismatch: bool = False,
        research_captures: bool = False,
        allow_seed_mismatch: bool = False,
    ) -> None:
        try:
            result = self.workflow.randomize_and_launch(
                settings,
                options,
                force_rebuild=True,
                allow_suppression_mismatch=allow_suppression_mismatch,
                allow_seed_mismatch=allow_seed_mismatch,
                research_captures=research_captures,
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
        research_captures: bool = False,
        allow_seed_mismatch: bool = False,
    ) -> None:
        try:
            result = self.workflow.randomize_and_launch(
                settings,
                options,
                allow_suppression_mismatch=allow_suppression_mismatch,
                allow_seed_mismatch=allow_seed_mismatch,
                research_captures=research_captures,
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

    def _finished(self, result: Any, *, action: str = "Launch") -> None:
        self._set_busy(False)
        mode = "enemy randomization enabled" if result.enemizer_enabled else "enemies unchanged"
        self._append_log(f"{action} started ({mode}); cache {result.cache_key[:12]}.")
        self._append_log(f"Client runtime config: {result.client_config}")
        self._append_log(f"Receive ledger: {result.ledger}")
        client_log = getattr(result, "client_log", None)
        if client_log is not None:
            self._append_log(f"Client log: {client_log}")
        shad_log = getattr(result, "shad_process_log", None)
        if shad_log is not None:
            self._append_log(f"shadPS4 log: {shad_log}")
        self._refresh_status()
        if isinstance(self, LauncherApp) and not getattr(self, "_health_monitoring", False):
            self._health_monitoring = True
            self.root.after(2000, lambda: LauncherApp._refresh_live_health(self))
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
    parser.add_argument(
        "--self-check", type=Path, default=None, metavar="REPORT",
        help="write a packaging self-check report (JSON) and exit without opening a window",
    )
    args = parser.parse_args(argv)
    if args.self_check is not None:
        from .self_check import run_self_check

        return run_self_check(args.self_check)
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
