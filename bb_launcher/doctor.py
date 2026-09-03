"""One-shot preflight of the whole player chain (bb-archipelago#103).

The first end-to-end player run failed serially, one error per attempt,
across nine distinct root causes -- each knowable up front, each costing a
full build/launch cycle to discover. This module checks every link in the
chain in one pass and renders a single PASS/WARN/FAIL list with a remedy per
failure, so the player is no longer the integration test.

Like readiness.py this module never writes anything; unlike readiness.py it
is a gate, not a status panel: it reports FAIL for anything that would
refuse or mis-build a launch. Every external probe (process scan, server
socket) is injectable so the tests stay dependency-free.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .core import (
    CE_BRIDGE_PROCESS_NAME,
    CHEAT_ENGINE_PROCESSES,
    DVDROOT_PREFIX,
    MAP_PREFIX,
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    SUPPRESSION_PATH,
    USER_MODS_DIR_NAME,
    GameInstall,
    LauncherError,
    ProcessSpec,
    ValidationError,
    STALE_BARE_SERIAL_REMEDY,
    dead_path_remedy,
    dead_path_wrappers,
    elevation_risks,
    launcher_is_elevated,
    collect_user_mod_files,
    plan_user_merge,
    process_is_running_by_name,
    sha256_file,
    stale_bare_serial_process,
    stray_cheat_engine_names,
    suppression_override_line,
    validate_processes,
)
from .client_config import default_state_root
from .readiness import gather_readiness
from .workflow import (
    SHAD_PROCESS_NAME,
    LauncherSettings,
    ProcessPlan,
    _read_object,
    _request_identity,
    load_process_plan,
)

PASS = "pass"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"

SUPPRESSION_MANIFEST_FORMAT = "bb-vanilla-suppression-build-v1"
SUPPRESSION_OUTPUT_RELATIVE = "param/gameparam/gameparam.parambnd.dcx"

# shadPS4 blocks overlay activation outright; the other two are the processes
# that held files or the wrong privilege token during the first player run.
BLOCKING_PROCESS = "shadps4.exe"
_BBLAUNCHER_REMEDY = (
    "the third-party BBLauncher spawns shadPS4 elevated; if you use it, "
    "this launcher and the AP client must also run as administrator or the "
    "client cannot attach"
)

_STRAY_CE_REMEDY = (
    "close every Cheat Engine window and relaunch: Windows hands the grant "
    "table to the instance that is already open, and that instance does not "
    "arm the grant bridge, so no items can be delivered (bb-archipelago#137)"
)

WARNING_PROCESSES = (
    ("bblauncher.exe", _BBLAUNCHER_REMEDY),
    ("bb-launcher.exe", _BBLAUNCHER_REMEDY),  # alternate spelling of the same tool
)

_BBLAUNCHER_LAYOUT_REMEDY = (
    "deactivate BB_Launcher mods while playing Archipelago; copy mods you still "
    f"want into {USER_MODS_DIR_NAME} with dvdroot_ps4 at the top, then rebuild "
    "the seed overlay; deletion mods are not compatible"
)


@dataclass(frozen=True)
class DoctorFinding:
    status: str
    name: str
    detail: str
    remedy: str | None = None


@dataclass(frozen=True)
class DoctorReport:
    findings: tuple[DoctorFinding, ...]

    def count(self, status: str) -> int:
        return sum(finding.status == status for finding in self.findings)

    @property
    def ok(self) -> bool:
        return self.count(FAIL) == 0

    @property
    def summary(self) -> str:
        return (
            f"{self.count(PASS)} passed, {self.count(WARN)} warning(s), "
            f"{self.count(FAIL)} failed, {self.count(SKIP)} skipped"
        )


@dataclass
class _Chain:
    """Validated intermediate state later checks build on."""

    install: GameInstall | None = None
    request: dict[str, Any] | None = None
    plan: ProcessPlan | None = None
    processes: list[ProcessSpec] | None = None


# The one process probe lives in core; doctor keeps the historical name so
# the UI and the tests import a single implementation.
_process_running = process_is_running_by_name


def _probe_server(host: str, port: int) -> None:
    with socket.create_connection((host, port), timeout=2.0):
        pass


def _check_install(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    try:
        chain.install = GameInstall.from_root(settings.game_root)
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "game installation",
            str(exc),
            "point the shadPS4 game folder at the directory holding CUSA03173, "
            "either with its CUSA03173-patch (01.09) update directory or as a "
            "merged 01.09 dump on its own",
        )
    return DoctorFinding(
        PASS,
        "game installation",
        f"CUSA03173 01.09 at {chain.install.root}",
    )


def _check_request(
    settings: LauncherSettings, chain: _Chain, player_name: str | None = None
) -> DoctorFinding:
    try:
        chain.request = _request_identity(
            settings.ap_request.expanduser().resolve(),
            player_name=(player_name or "").strip(),
            state_root=settings.state_root,
        )
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "AP seed file",
            str(exc),
            "select the *.apbb or AP_<seed>.zip your host sent you, or the "
            "*.bbseed.json (older seeds: *.bbenemizer.json) the generator "
            "dropped beside it; if the seed predates world-version tagging, "
            "regenerate it",
        )
    request = chain.request
    detail = (
        f"slot {request['slot']}, runtime {request['runtime_build']}, "
        f"world {request['world_build']}"
    )
    source = request["source"]
    if source.from_archive:
        # Name both halves: which zip, and which member inside it was chosen.
        detail = f"{detail} (member {source.member} of {source.archive})"
    return DoctorFinding(PASS, "AP seed file", detail)


def _check_plan(settings: LauncherSettings, chain: _Chain) -> DoctorFinding:
    try:
        chain.plan = load_process_plan(settings.process_plan)
        chain.processes = validate_processes(chain.plan.processes)
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "launch plan",
            str(exc),
            "use Generate Launch Plan (or python -m bb_launcher plan) against "
            "the current executables; a hash mismatch means a component was "
            "updated after the plan was pinned",
        )
    names = ", ".join(spec.name for spec in chain.processes)
    return DoctorFinding(
        PASS,
        "launch plan",
        f"{len(chain.processes)} process(es) pinned and present: {names}",
    )


def _check_bblauncher_layout(chain: _Chain) -> DoctorFinding:
    """Name BB_Launcher's on-disk convention instead of reporting mystery files.

    BB_Launcher stores its managed set below a ``dvdroot_ps4/MODS`` directory.
    It has been observed both in the game content tree and in the active mods
    overlay, depending on launcher/version.  Presence is not proof that every
    contained mod is active, so this is a warning; AP's ownership checks remain
    the authoritative fail-closed gate for an actual collision.
    """

    if chain.install is None:
        return DoctorFinding(SKIP, "BB_Launcher mods", "upstream check failed")
    candidates = [
        chain.install.mods / "dvdroot_ps4" / "MODS",
        chain.install.base / "dvdroot_ps4" / "MODS",
    ]
    if chain.install.patch is not None:
        candidates.append(chain.install.patch / "dvdroot_ps4" / "MODS")
    found = [path for path in candidates if path.is_dir()]
    if not found:
        return DoctorFinding(PASS, "BB_Launcher mods", "no managed MODS layout detected")
    rendered = ", ".join(str(path) for path in found)
    return DoctorFinding(
        WARN,
        "BB_Launcher mods",
        f"detected third-party managed MODS layout at {rendered}",
        _BBLAUNCHER_LAYOUT_REMEDY,
    )


def _check_plan_game_argument(chain: _Chain) -> DoctorFinding:
    """The plan must name the game by path, not by bare game ID.

    bb-archipelago#177: shadPS4 resolves a bare ``CUSA03173`` only against its
    own ``install_dirs`` config, which is empty on a fresh emulator copy, so a
    player whose launcher game-folder field was perfectly correct still hit
    "Game ID or file path not found".  A plan pinned before that fix carries the
    old argument and has to be regenerated; nothing at launch can repair it,
    because the plan is the document the player may have hand-edited.
    """

    if chain.plan is None:
        return DoctorFinding(SKIP, "launch plan game argument", "upstream check failed")
    stale = stale_bare_serial_process(chain.plan.processes)
    if stale is not None:
        return DoctorFinding(
            FAIL,
            "launch plan game argument",
            f"{stale.name} is invoked with the bare game ID; shadPS4 can only "
            "resolve that against its own library config, which is empty on an "
            "emulator copy that has never been opened and configured",
            STALE_BARE_SERIAL_REMEDY,
        )
    if chain.install is None:
        return DoctorFinding(
            SKIP, "launch plan game argument", "game installation check failed"
        )
    return DoctorFinding(
        PASS,
        "launch plan game argument",
        f"the game is launched by path: {chain.install.base}",
    )


def _read_windows_file_version(path: Path) -> str | None:
    """Read an executable's file-version resource, or None where there isn't one.

    Windows-only by construction: everywhere else this returns None and the
    version gate reports SKIP rather than inventing a verdict.
    """

    import sys

    if sys.platform != "win32":  # pragma: no cover - platform-specific
        return None
    try:  # pragma: no cover - exercised only on Windows
        import ctypes
        from ctypes import wintypes

        version_dll = ctypes.WinDLL("version")
        size = version_dll.GetFileVersionInfoSizeW(ctypes.c_wchar_p(str(path)), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version_dll.GetFileVersionInfoW(
            ctypes.c_wchar_p(str(path)), 0, size, buffer
        ):
            return None
        value = ctypes.c_void_p()
        length = wintypes.UINT()
        if not version_dll.VerQueryValueW(
            buffer, ctypes.c_wchar_p("\\"), ctypes.byref(value), ctypes.byref(length)
        ):
            return None

        class _FixedFileInfo(ctypes.Structure):
            _fields_ = [
                ("dwSignature", ctypes.c_uint32),
                ("dwStrucVersion", ctypes.c_uint32),
                ("dwFileVersionMS", ctypes.c_uint32),
                ("dwFileVersionLS", ctypes.c_uint32),
                ("dwProductVersionMS", ctypes.c_uint32),
                ("dwProductVersionLS", ctypes.c_uint32),
            ]

        info = ctypes.cast(value, ctypes.POINTER(_FixedFileInfo)).contents
        return (
            f"{info.dwFileVersionMS >> 16}.{info.dwFileVersionMS & 0xFFFF}."
            f"{info.dwFileVersionLS >> 16}.{info.dwFileVersionLS & 0xFFFF}"
        )
    except Exception:  # noqa: BLE001 - a missing resource is not a doctor crash
        return None


def _version_triple(raw: str) -> tuple[str, ...]:
    """The first three dotted components, so 0.18.0.0 and 0.18.0 compare equal."""

    parts = [part for part in raw.strip().lstrip("vV.").split(".") if part != ""]
    return tuple(parts[:3])


def _check_shad_version(
    chain: _Chain,
    read_version: Callable[[Path], str | None],
) -> DoctorFinding:
    """Refuse a shadPS4 build the native delivery RVAs were not validated against.

    bb-archipelago#177 point 1: the Doctor used to accept any file named
    shadPS4.exe, so a playtester passed every gate with the 0.16.0 copy bundled
    inside the third-party BBLauncher and only found out at runtime.
    """

    if chain.plan is None or chain.processes is None:
        return DoctorFinding(SKIP, "shadPS4 version", "upstream check failed")
    specs = [spec for spec in chain.processes if spec.name == SHAD_PROCESS_NAME]
    if not specs:
        return DoctorFinding(
            SKIP, "shadPS4 version", f"the plan pins no {SHAD_PROCESS_NAME} process"
        )
    executable = Path(specs[0].executable)
    found = read_version(executable)
    if found is None:
        return DoctorFinding(
            SKIP,
            "shadPS4 version",
            f"could not read a version resource from {executable}",
        )
    expected = chain.plan.shad_build
    if _version_triple(found) != _version_triple(expected):
        return DoctorFinding(
            FAIL,
            "shadPS4 version",
            f"{executable} reports version {found}, but this seed needs "
            f"shadPS4 {expected}",
            f"select a standalone shadPS4 {expected} build: native item delivery "
            f"is validated against {expected} only, and the client hard-fails on "
            "another build even after a successful boot. Beware the copy bundled "
            "inside the third-party BBLauncher tree -- it has shipped older "
            "builds, and picking it has cost a playtester a session before",
        )
    return DoctorFinding(PASS, "shadPS4 version", f"{executable} is shadPS4 {found}")


def _check_slot_agreement(chain: _Chain, player_name: str | None) -> DoctorFinding:
    if chain.request is None:
        return DoctorFinding(SKIP, "request slot agreement", "upstream check failed")
    slot = chain.request["slot"]
    entered = (player_name or "").strip()
    if not entered:
        return DoctorFinding(
            WARN,
            "request slot agreement",
            f"the AP seed file is for slot {slot!r}; no player name entered to verify against",
            "enter your AP player name so the Doctor can confirm the request is "
            "yours; in a multi-Bloodborne multiworld the launcher can auto-pick "
            "another player's request file",
        )
    if entered != slot:
        return DoctorFinding(
            FAIL,
            "request slot agreement",
            f"the AP seed file is for slot {slot!r} but you entered {entered!r}",
            "select YOUR own slot: with the AP_<seed>.zip, put your AP player "
            "name in the player-name field so the launcher picks your member; "
            "with a loose file, pick your own "
            "<seed>_P<number>_<name>.bbseed.json. Launching with another "
            "player's request connects you as their slot and steals their "
            "checks",
        )
    return DoctorFinding(
        PASS, "request slot agreement", f"slot {slot!r} matches the entered player name"
    )


def _check_runtime_agreement(chain: _Chain) -> DoctorFinding:
    if chain.request is None or chain.plan is None:
        return DoctorFinding(SKIP, "runtime build agreement", "upstream check failed")
    wanted = chain.request["runtime_build"]
    found = chain.plan.runtime_build
    if wanted != found:
        return DoctorFinding(
            FAIL,
            "runtime build agreement",
            f"the AP seed requires runtime {wanted}, the launch plan supplies {found}",
            "regenerate the launch plan against the current AP seed file",
        )
    return DoctorFinding(PASS, "runtime build agreement", wanted)


_REPACK_REMEDY = (
    "the usual cause is a pre-modded repack -- installs named like "
    '"Bloodborne (feat. shadPS4)" ship an already-modified patch gameparam; '
    "restore a clean 01.09 patch layer (re-dump or re-copy the untouched "
    "gameparam.parambnd.dcx) before building or launching. "
    f"The operator override {SUPPRESSION_OVERRIDE_KNOB} exists, but launching "
    "under it reverts whatever the repack's param edits did"
)


_OVERRIDE_REMEDY = (
    f"this is skew, not corruption; rebuild the binder for this seed and this "
    f"installation, or relaunch with {SUPPRESSION_OVERRIDE_KNOB} if you are the "
    "operator and you know exactly what drifted -- players should never use it"
)


def _check_suppression_chain(
    settings: LauncherSettings, chain: _Chain, *, allow_mismatch: bool = False
) -> DoctorFinding:
    if chain.request is None:
        return DoctorFinding(SKIP, "suppression binder and manifest", "upstream check failed")
    binder = settings.suppression_binder.expanduser().resolve()
    manifest_path = settings.suppression_manifest.expanduser().resolve()
    if not binder.is_file() or binder.is_symlink():
        return DoctorFinding(
            FAIL,
            "suppression binder and manifest",
            f"suppression binder is not a regular file: {binder}",
            "build it with tools/build_vanilla_suppression.ps1 or select the "
            "packaged gameparam.parambnd.dcx",
        )
    overridden: list[str] = []
    try:
        manifest = _read_object(manifest_path, "suppression build manifest")
        if manifest.get("format") != SUPPRESSION_MANIFEST_FORMAT:
            raise ValidationError("suppression build manifest has the wrong format")
        if manifest.get("output_relative_path") != SUPPRESSION_OUTPUT_RELATIVE:
            raise ValidationError("suppression manifest output path is not the gameparam binder")
        expected_plan = chain.request["suppression_plan_sha256"]
        if manifest.get("plan_sha256") != expected_plan:
            # WARN-with-the-knob-named, never a silent PASS: the operator still
            # has to read a line saying which hash disagreed (#183).
            if not allow_mismatch:
                raise ValidationError("suppression build plan hash does not match the AP seed")
            overridden.append(
                suppression_override_line(
                    SUPPRESSION_CHECK_PLAN,
                    expected_plan,
                    manifest.get("plan_sha256"),
                    "binder plan vs the seed's suppression_plan_sha256",
                )
            )
        output_hash = sha256_file(binder)
        if manifest.get("output_gameparam_sha256") != output_hash:
            raise ValidationError("suppression binder hash does not match its build manifest")
        if manifest.get("source_gameparam_sha256") == output_hash:
            raise ValidationError(
                "suppression binder is byte-identical to vanilla; refusing an unsuppressed build"
            )
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "suppression binder and manifest",
            str(exc),
            "binder and manifest must come from the same suppression build; "
            "if the seed was regenerated, rebuild the binder for its plan hash",
        )
    if overridden:
        return DoctorFinding(
            WARN,
            "suppression binder and manifest",
            "; ".join(overridden),
            _OVERRIDE_REMEDY,
        )
    return DoctorFinding(
        PASS,
        "suppression binder and manifest",
        f"binder {output_hash[:12]} matches manifest, plan {expected_plan[:12]} matches the seed",
    )


def _check_installed_gameparam(
    settings: LauncherSettings, chain: _Chain, *, allow_mismatch: bool = False
) -> DoctorFinding:
    if chain.install is None:
        return DoctorFinding(SKIP, "installed gameparam", "upstream check failed")
    try:
        manifest = _read_object(
            settings.suppression_manifest.expanduser().resolve(), "suppression build manifest"
        )
        source_expected = manifest.get("source_gameparam_sha256")
        output_expected = manifest.get("output_gameparam_sha256")
        if not isinstance(source_expected, str) or not isinstance(output_expected, str):
            raise ValidationError("suppression manifest is missing its source/output hashes")
        backend, source_path = chain.install.resolve_file(SUPPRESSION_PATH, include_mods=False)
    except LauncherError as exc:
        return DoctorFinding(
            SKIP,
            "installed gameparam",
            f"not checked: {exc}",
        )
    actual = sha256_file(source_path)
    if actual == source_expected:
        return DoctorFinding(
            PASS,
            "installed gameparam",
            f"{backend}-layer {source_path} is the vanilla source the suppression build was made from",
        )
    # Both branches below are the same comparison the launch path bypasses
    # (manifest source vs installed gameparam), so both downgrade together --
    # an override that fires in one lane and refuses in the other is worse
    # than no override at all (bb-archipelago#183).
    if allow_mismatch:
        return DoctorFinding(
            WARN,
            "installed gameparam",
            suppression_override_line(
                SUPPRESSION_CHECK_SOURCE,
                source_expected,
                actual,
                f"binder source vs the installed {backend}-layer {source_path}",
            ),
            _OVERRIDE_REMEDY,
        )
    if actual == output_expected:
        return DoctorFinding(
            FAIL,
            "installed gameparam",
            f"the {backend}-layer {source_path} IS the suppressed binder -- this "
            "installation was already modified outside the launcher",
            _REPACK_REMEDY,
        )
    return DoctorFinding(
        FAIL,
        "installed gameparam",
        f"the {backend}-layer {source_path} matches neither the vanilla source "
        f"nor the suppressed build (found {actual[:12]})",
        "something outside this toolchain modified the game files; "
        + _REPACK_REMEDY,
    )


def _check_user_mods(chain: _Chain, *, randomize_enemies: bool) -> DoctorFinding:
    """Report what the player's own mods directory will contribute, and what won't.

    The launcher owns CUSA03173-mods outright, so this is the only place a user
    file can come from -- and the only place a silent drop could hide.
    """

    if chain.install is None:
        return DoctorFinding(SKIP, "user mods", "upstream check failed")
    directory = chain.install.user_mods
    try:
        sources = collect_user_mod_files(directory)
    except LauncherError as exc:
        return DoctorFinding(
            FAIL,
            "user mods",
            str(exc),
            f"make {directory} an ordinary directory containing only real files",
        )
    if not sources:
        return DoctorFinding(
            PASS,
            "user mods",
            f"no files in {USER_MODS_DIR_NAME}; the overlay is Archipelago content only",
        )
    # The suppression binder is owned on every seed; MapStudio maps only when
    # the enemizer is emitting them, so name that case rather than guess it.
    owned = [SUPPRESSION_PATH]
    merge = plan_user_merge({relative: sha256_file(path) for relative, path in sources.items()}, owned)
    map_files = sorted(
        relative
        for relative in merge.merged
        if relative.casefold().startswith(MAP_PREFIX.casefold())
        and relative.casefold().endswith(".msb.dcx")
    )
    detail = f"{len(merge.merged)} file(s) from {USER_MODS_DIR_NAME} will merge into the overlay"
    # Dead paths first: they are the only exclusion that means a mod the player
    # believes is installed does nothing at all (bb-archipelago#173).
    wrappers = dead_path_wrappers(merge.excluded)
    if wrappers:
        dead = sum(count for _, count in wrappers)
        shown = wrappers[:5]
        listed = "; ".join(f"{wrapper} ({count} file(s))" for wrapper, count in shown)
        if len(wrappers) > len(shown):
            listed += f", and {len(wrappers) - len(shown)} more"
        return DoctorFinding(
            WARN,
            "user mods",
            f"{detail}; {dead} file(s) can never load because their paths do "
            f"not start with {DVDROOT_PREFIX} -- these are NOT merged and the "
            f"mod will do nothing: {listed}",
            "; ".join(dead_path_remedy(wrapper) for wrapper, _ in shown),
        )
    if merge.excluded:
        shown = ", ".join(f"{item.path} ({item.reason})" for item in merge.excluded[:3])
        extra = "" if len(merge.excluded) <= 3 else f", and {len(merge.excluded) - 3} more"
        return DoctorFinding(
            WARN,
            "user mods",
            f"{detail}; excluded: {shown}{extra}",
            "Archipelago-owned files always win; remove the colliding file from "
            "your mod, or accept that the Archipelago version is the one loaded",
        )
    if randomize_enemies and map_files:
        return DoctorFinding(
            WARN,
            "user mods",
            f"{detail}, including {len(map_files)} MapStudio map(s) that the "
            "enemy randomizer may also own on this seed",
            "if a seed generates one of these maps the Archipelago version wins "
            "and yours is reported as excluded; turn enemy randomization off to "
            "keep your map mod whole",
        )
    return DoctorFinding(PASS, "user mods", detail)


def _check_map_studio(
    settings: LauncherSettings, chain: _Chain, *, randomize_enemies: bool
) -> DoctorFinding:
    if not randomize_enemies:
        return DoctorFinding(SKIP, "MapStudio source", "enemy randomization is off")
    candidate = settings.map_studio_source
    if candidate is None and chain.install is not None:
        relative = Path("dvdroot_ps4") / "map" / "MapStudio"
        for _name, backend in chain.install.content_backends():
            found = backend / relative
            if found.is_dir():
                candidate = found
                break
    if candidate is None or not candidate.is_dir():
        return DoctorFinding(
            FAIL,
            "MapStudio source",
            "no source MapStudio selected and none found in the game installation",
            "select the installed map\\MapStudio directory (the patch layer's "
            "compressed *.msb.dcx set) or turn enemy randomization off",
        )
    maps = [
        path
        for path in candidate.iterdir()
        if path.is_file() and path.name.lower().endswith((".msb", ".msb.dcx"))
    ]
    if not maps:
        return DoctorFinding(
            FAIL,
            "MapStudio source",
            f"{candidate} contains no .msb/.msb.dcx files",
            "select the installed compressed MapStudio set, not a miner output directory",
        )
    return DoctorFinding(
        PASS, "MapStudio source", f"{len(maps)} map(s) under {candidate}"
    )


def _check_server(
    chain: _Chain,
    server: str | None,
    probe: Callable[[str, int], None],
) -> DoctorFinding:
    address = server
    if not address and chain.processes:
        for spec in chain.processes:
            if spec.name == "AP client" and spec.arguments:
                address = spec.arguments[0]
                break
    if not address:
        return DoctorFinding(
            SKIP, "AP server", "no server address in the launch plan and none supplied"
        )
    host, separator, raw_port = address.rpartition(":")
    if not separator or not host or not raw_port.isdigit():
        return DoctorFinding(
            FAIL,
            "AP server",
            f"cannot parse server address {address!r}",
            "use host:port, e.g. localhost:38281",
        )
    try:
        probe(host, int(raw_port))
    except (ConnectionRefusedError, OSError) as exc:
        if isinstance(exc, (socket.timeout, TimeoutError, socket.gaierror)):
            return DoctorFinding(
                WARN,
                "AP server",
                f"no answer from {address} within the probe timeout ({exc})",
                "a firewall may block the probe; the client connect is the real test",
            )
        return DoctorFinding(
            FAIL,
            "AP server",
            f"nothing is listening on {address} ({exc})",
            "start MultiServer with the seed zip first, and check the port: the "
            "client reports a wrong port only as 'a full error is available "
            "elsewhere'",
        )
    return DoctorFinding(PASS, "AP server", f"{address} accepted a connection")


def _bridge_reported(settings: LauncherSettings, chain: _Chain) -> bool | None:
    """Has the grant harness ever written bridge state for this session?

    None when the answer cannot be read (no install, no request, no state
    root) -- an unknown is not a negative.
    """

    if chain.install is None or chain.request is None:
        return None
    try:
        readiness = gather_readiness(
            chain.install,
            settings.state_root or default_state_root(),
            seed=chain.request["seed"],
            slot=chain.request["slot"],
        )
    except LauncherError:
        return None
    return readiness.bridge is not None


def _check_item_grants(
    settings: LauncherSettings, chain: _Chain, process_running: Callable[[str], bool]
) -> DoctorFinding:
    names = {spec.name for spec in chain.processes or ()}
    if CE_BRIDGE_PROCESS_NAME in names:
        stray = stray_cheat_engine_names(process_running)
        if stray:
            return DoctorFinding(
                FAIL,
                "item grants",
                "Cheat Engine bridge pinned, but Cheat Engine is already running "
                f"({', '.join(stray)}): launching now would not arm the bridge",
                _STRAY_CE_REMEDY,
            )
        reported = _bridge_reported(settings, chain)
        if reported is True:
            return DoctorFinding(
                PASS,
                "item grants",
                "Cheat Engine bridge pinned and the grant harness has reported: "
                "items can be delivered",
            )
        detail = "Cheat Engine bridge pinned: items can be delivered"
        if reported is False:
            detail += (
                " once the table arms (the harness has not reported yet this "
                "session; the launcher warns if it never does)"
            )
        return DoctorFinding(PASS, "item grants", detail)
    return DoctorFinding(
        WARN,
        "item grants",
        "no Cheat Engine bridge in the launch plan",
        "regenerate the launch plan with Cheat Engine and the grant table "
        "(Generate Launch Plan): without it your checks still reach the "
        "server, but no items can be delivered into your game",
    )


def _check_elevation(chain: _Chain, process_running: Callable[[str], bool]) -> DoctorFinding:
    if launcher_is_elevated():
        return DoctorFinding(
            PASS,
            "elevation",
            "launcher is running as administrator and can attach to an elevated shadPS4",
        )
    shad = None
    for spec in chain.processes or ():
        if spec.name == "shadPS4":
            shad = spec.executable
    risks = elevation_risks(shad, process_running)
    if risks:
        return DoctorFinding(
            WARN,
            "elevation",
            "; ".join(risks),
            "restart this launcher as administrator: an unelevated AP client "
            "cannot attach to an elevated shadPS4 and will wait forever",
        )
    return DoctorFinding(PASS, "elevation", "no elevated shadPS4 launch path detected")


def _check_processes(
    process_running: Callable[[str], bool], chain: _Chain
) -> list[DoctorFinding]:
    findings: list[DoctorFinding] = []
    if process_running(BLOCKING_PROCESS):
        findings.append(
            DoctorFinding(
                FAIL,
                "blocking processes",
                "shadPS4 is already running",
                "close it before launching: overlay activation refuses to touch "
                "the installation while the game runs, and a client started "
                "against the wrong boot state cannot verify the save",
            )
        )
    else:
        findings.append(
            DoctorFinding(PASS, "blocking processes", "shadPS4 is not running")
        )
    bridge_pinned = any(
        spec.name == CE_BRIDGE_PROCESS_NAME for spec in chain.processes or ()
    )
    for name in CHEAT_ENGINE_PROCESSES:
        if not process_running(name):
            continue
        # A pinned bridge turns the old warning into a refusal: the launch
        # would proceed into a degraded state where checks report but nothing
        # is delivered (bb-archipelago#137).
        findings.append(
            DoctorFinding(
                FAIL if bridge_pinned else WARN,
                f"running process {name}",
                f"{name} is running",
                _STRAY_CE_REMEDY
                if bridge_pinned
                else "a stray Cheat Engine instance can hold the grant table or "
                "stale bridge state; close any CE window you did not just open "
                "for this session",
            )
        )
    for name, remedy in WARNING_PROCESSES:
        if process_running(name):
            findings.append(
                DoctorFinding(WARN, f"running process {name}", f"{name} is running", remedy)
            )
    return findings


def _safely(check: Callable[[], DoctorFinding]) -> DoctorFinding:
    """A doctor that crashes on the ninth failure mode has learned nothing."""

    try:
        return check()
    except Exception as exc:  # noqa: BLE001 -- the report must survive anything
        return DoctorFinding(FAIL, "doctor internal", f"{type(exc).__name__}: {exc}")


def run_doctor(
    settings: LauncherSettings,
    *,
    randomize_enemies: bool = True,
    server: str | None = None,
    player_name: str | None = None,
    allow_suppression_mismatch: bool = False,
    process_running: Callable[[str], bool] | None = None,
    probe: Callable[[str, int], None] | None = None,
    read_shad_version: Callable[[Path], str | None] | None = None,
) -> DoctorReport:
    """Check every link in the player chain. Never raises for bad state."""

    process_running = process_running or _process_running
    probe = probe or _probe_server
    read_shad_version = read_shad_version or _read_windows_file_version
    chain = _Chain()
    findings = [
        _safely(lambda: _check_install(settings, chain)),
        _safely(lambda: _check_bblauncher_layout(chain)),
        _safely(lambda: _check_request(settings, chain, player_name)),
        _safely(lambda: _check_slot_agreement(chain, player_name)),
        _safely(lambda: _check_plan(settings, chain)),
        _safely(lambda: _check_plan_game_argument(chain)),
        _safely(lambda: _check_shad_version(chain, read_shad_version)),
        _safely(lambda: _check_item_grants(settings, chain, process_running)),
        _safely(lambda: _check_runtime_agreement(chain)),
        _safely(
            lambda: _check_suppression_chain(
                settings, chain, allow_mismatch=allow_suppression_mismatch
            )
        ),
        _safely(
            lambda: _check_installed_gameparam(
                settings, chain, allow_mismatch=allow_suppression_mismatch
            )
        ),
        _safely(lambda: _check_map_studio(settings, chain, randomize_enemies=randomize_enemies)),
        _safely(lambda: _check_user_mods(chain, randomize_enemies=randomize_enemies)),
        _safely(lambda: _check_server(chain, server, probe)),
        _safely(lambda: _check_elevation(chain, process_running)),
    ]
    try:
        findings.extend(_check_processes(process_running, chain))
    except Exception as exc:  # noqa: BLE001
        findings.append(DoctorFinding(FAIL, "blocking processes", f"{type(exc).__name__}: {exc}"))
    return DoctorReport(tuple(findings))


_MARKERS = {PASS: "PASS", WARN: "WARN", FAIL: "FAIL", SKIP: "SKIP"}


def format_report(report: DoctorReport) -> str:
    """Render the findings as one line each, ASCII-safe for any console."""

    lines: list[str] = []
    for finding in report.findings:
        lines.append(f"[{_MARKERS[finding.status]}] {finding.name}: {finding.detail}")
        if finding.remedy:
            lines.append(f"       -> {finding.remedy}")
    lines.append(f"Doctor: {report.summary}")
    return "\n".join(lines)
