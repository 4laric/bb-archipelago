"""Player-facing build orchestration above the transactional launcher core."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .core import (
    BuildResult,
    AI_PREFIX,
    AI_FILE_PATTERN,
    DVDROOT_PREFIX,
    CATHEDRAL_EVENT_PATH,
    HEMWICK_EVENT_PATH,
    ITEM_NAMES_PATH,
    ITEM_NAMES_PATHS,
    COMMON_EVENT_PATH,
    BOSS_EVENT_PATH,
    STALE_BARE_SERIAL_REMEDY,
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    SUPPRESSION_PATH,
    SEED_MANIFEST_NAME,
    EarlyExit,
    GameInstall,
    LauncherError,
    ProcessSpec,
    REBUILD_OVERLAY_HINT,
    SeedCache,
    SeedIdentity,
    ValidationError,
    _load_owner,
    activate_build,
    dead_path_warnings,
    deactivate_overlay,
    launch_processes,
    overlay_heal_line,
    process_is_running_by_name,
    require_no_stray_cheat_engine,
    restore_previous_build,
    sha256_file,
    stale_bare_serial_process,
    suppression_override_line,
    validate_processes,
    wait_for_early_exit,
    _write_json_atomic,
)
from .client_config import (
    CLIENT_LOG_FLAG,
    CLIENT_PLACEHOLDERS,
    ClientRuntimePaths,
    default_shad_log,
    default_state_root,
    substitute_plan_arguments,
    write_client_runtime_config,
)
from .resources import application_root
from .pickup_names import pickup_name_plan
from .seed_request import ResolvedRequest, resolve_request_source


SETTINGS_FORMAT = "bb-launcher-ui-settings-v1"
PROCESS_PLAN_FORMAT = "bb-launcher-process-plan-v1"
# The plan entry whose output is captured and watched (bb-archipelago#171).
CLIENT_PROCESS_NAME = "AP client"
SHAD_PROCESS_NAME = "shadPS4"
REQUEST_FORMAT = "bb-seed-request-v1"
# Seeds generated before the request became the seed identity document (#149)
# carry the old format name; the payload is compatible.
LEGACY_REQUEST_FORMAT = "bb-enemizer-request-v1"
REQUEST_FORMATS = (REQUEST_FORMAT, LEGACY_REQUEST_FORMAT)
# Records which AP seed/slot a server address was last used to connect
# delivery for, so a stale saved address cannot silently replay another
# room's receive history onto a freshly selected seed package
# (bb-archipelago#347).
AP_IDENTITY_LOCK_FORMAT = "bb-ap-identity-lock-v1"
PLAN_FORMAT = "bb-enemizer-plan-v2"
PARAMDEF_PATH = "dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx"
Progress = Callable[[str], None]
CommandRunner = Callable[[Sequence[str], Path, Progress], None]


@dataclass(frozen=True)
class RunningProcess:
    pid: int
    executable: Path | None
    arguments: tuple[str, ...] | None
    creation_time: int | None = None


def _windows_command_line_args(command: str) -> tuple[str, ...]:
    """Parse a Windows command line with the same rules as the target process."""

    import ctypes
    from ctypes import wintypes

    count = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    command_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
    pointer = command_line_to_argv(command, ctypes.byref(count))
    if not pointer:
        raise ValidationError("Windows could not parse the shadPS4 command line")
    try:
        return tuple(pointer[index] for index in range(count.value))
    finally:
        local_free = ctypes.windll.kernel32.LocalFree
        local_free.argtypes = (wintypes.HLOCAL,)
        local_free.restype = wintypes.HLOCAL
        local_free(pointer)


def process_creation_time(pid: int) -> int:
    """Read the Windows process birth identity; a reused PID is a different process."""
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        raise ValidationError(f"Cannot verify shadPS4 process {pid}: Windows error {ctypes.get_last_error()}; run both programs at the same privilege level")
    try:
        created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel_time), ctypes.byref(user_time)):
            raise ValidationError(f"Cannot read shadPS4 process creation time: Windows error {ctypes.get_last_error()}")
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def running_shad_processes() -> tuple[RunningProcess, ...]:
    """Enumerate shadPS4 processes with enough identity to attach safely."""

    if sys.platform == "win32":
        script = (
            "$ErrorActionPreference='Stop'; "
            "@(Get-CimInstance Win32_Process -Filter \"Name='shadPS4.exe'\" | "
            "Select-Object ProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                check=False, capture_output=True, text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as exc:
            raise ValidationError(
                "could not inspect running shadPS4 processes; run the launcher with "
                "permission to query process paths and command lines"
            ) from exc
        if result.returncode != 0:
            raise ValidationError(
                "could not inspect running shadPS4 process identity; Windows denied or "
                "failed the process query. Run the launcher at the same privilege level as shadPS4"
            )
        try:
            raw = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ValidationError("Windows returned invalid shadPS4 process identity data") from exc
        records = raw if isinstance(raw, list) else ([] if raw is None else [raw])
        found = []
        for record in records:
            command = record.get("CommandLine") if isinstance(record, dict) else None
            arguments = None
            if isinstance(command, str) and command.strip():
                arguments = _windows_command_line_args(command)
            executable = record.get("ExecutablePath") if isinstance(record, dict) else None
            found.append(RunningProcess(
                int(record.get("ProcessId", 0)),
                Path(executable).resolve() if isinstance(executable, str) and executable else None,
                arguments,
                process_creation_time(int(record.get("ProcessId", 0))),
            ))
        return tuple(found)
    found = []
    for comm in Path("/proc").glob("[0-9]*/comm"):
        try:
            if comm.read_text(encoding="utf-8").strip().casefold() != "shadps4.exe":
                continue
            process_root = comm.parent
            executable = Path(os.readlink(process_root / "exe")).resolve()
            argv = tuple(
                part.decode(errors="replace")
                for part in (process_root / "cmdline").read_bytes().split(b"\0") if part
            )
            found.append(RunningProcess(int(process_root.name), executable, argv))
        except OSError:
            found.append(RunningProcess(int(comm.parent.name), None, None))
    return tuple(found)


def _shad_game_argument(arguments: Sequence[str]) -> Path | None:
    values = tuple(arguments[1:]) if arguments else ()
    for index, value in enumerate(values):
        lowered = value.casefold()
        if lowered in {"-g", "--game"}:
            game = Path(values[index + 1]).expanduser().resolve() if index + 1 < len(values) else None
            return game.parent if game is not None and game.name.casefold() == "eboot.bin" else game
        if lowered.startswith("--game=") or lowered.startswith("-g="):
            game = Path(value.split("=", 1)[1]).expanduser().resolve()
            return game.parent if game.name.casefold() == "eboot.bin" else game
    index = 0
    while index < len(values):
        value = values[index]
        if value.casefold() in {"-f", "--fullscreen"}:
            index += 2
            continue
        if value.startswith("-"):
            index += 1
            continue
        game = Path(value).expanduser().resolve()
        return game.parent if game.name.casefold() == "eboot.bin" else game
    return None


class WorkflowError(LauncherError):
    """One-click build orchestration failed before a safe launch."""


@dataclass(frozen=True)
class ProcessPlan:
    shad_build: str
    runtime_build: str
    processes: tuple[ProcessSpec, ...]


@dataclass(frozen=True)
class LauncherSettings:
    game_root: Path
    cache_root: Path
    ap_request: Path
    suppression_binder: Path
    suppression_manifest: Path
    process_plan: Path
    map_studio_source: Path | None = None
    enemy_inventory: Path | None = None
    soulsformats_next: Path | None = None
    state_root: Path | None = None
    shad_log: Path | None = None
    # Retained so settings files written by earlier builds still load. The
    # event overlays are written by the bundled BBEventWriter; no compiler is
    # consulted.
    darkscript: Path | None = None
    integration_mode: str = "standalone"
    bblauncher_mods: Path | None = None
    bblauncher_executable: Path | None = None
    bblauncher_receipt: Path | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any], *, relative_to: Path | None = None) -> "LauncherSettings":
        if value.get("format") != SETTINGS_FORMAT:
            raise ValidationError("unsupported launcher settings format")
        base = (relative_to or Path.cwd()).resolve()

        def required(name: str) -> Path:
            raw = value.get(name)
            if not isinstance(raw, str) or not raw.strip():
                raise ValidationError(f"launcher settings require {name}")
            path = Path(raw).expanduser()
            return (base / path).resolve() if not path.is_absolute() else path.resolve()

        def optional(name: str) -> Path | None:
            raw = value.get(name)
            if raw in (None, ""):
                return None
            if not isinstance(raw, str):
                raise ValidationError(f"launcher setting {name} must be a path string")
            path = Path(raw).expanduser()
            return (base / path).resolve() if not path.is_absolute() else path.resolve()

        mode = value.get("integration_mode", "standalone")
        if mode not in ("standalone", "bblauncher"):
            raise ValidationError("integration_mode must be standalone or bblauncher")
        return cls(
            integration_mode=mode,
            bblauncher_mods=optional("bblauncher_mods"),
            bblauncher_executable=optional("bblauncher_executable"),
            bblauncher_receipt=optional("bblauncher_receipt"),
            game_root=required("game_root"),
            cache_root=required("cache_root"),
            ap_request=required("ap_request"),
            suppression_binder=required("suppression_binder"),
            suppression_manifest=required("suppression_manifest"),
            process_plan=required("process_plan"),
            map_studio_source=optional("map_studio_source"),
            enemy_inventory=optional("enemy_inventory"),
            soulsformats_next=optional("soulsformats_next"),
            state_root=optional("state_root"),
            shad_log=optional("shad_log"),
            darkscript=optional("darkscript"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "format": SETTINGS_FORMAT,
            "integration_mode": self.integration_mode,
            "bblauncher_mods": None if self.bblauncher_mods is None else str(self.bblauncher_mods),
            "bblauncher_executable": None if self.bblauncher_executable is None else str(self.bblauncher_executable),
            "bblauncher_receipt": None if self.bblauncher_receipt is None else str(self.bblauncher_receipt),
            "game_root": str(self.game_root),
            "cache_root": str(self.cache_root),
            "ap_request": str(self.ap_request),
            "suppression_binder": str(self.suppression_binder),
            "suppression_manifest": str(self.suppression_manifest),
            "process_plan": str(self.process_plan),
            "map_studio_source": None if self.map_studio_source is None else str(self.map_studio_source),
            "enemy_inventory": None if self.enemy_inventory is None else str(self.enemy_inventory),
            "soulsformats_next": None if self.soulsformats_next is None else str(self.soulsformats_next),
            "state_root": None if self.state_root is None else str(self.state_root),
            "shad_log": None if self.shad_log is None else str(self.shad_log),
            "darkscript": None if self.darkscript is None else str(self.darkscript),
        }


@dataclass(frozen=True)
class SuppressionValidation:
    """The verified suppression manifest plus whatever the operator waved past."""

    manifest: Mapping[str, Any]
    bypassed: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnemizerOptions:
    enabled: bool = True
    seed: str | None = None
    allow_tier_mixing: bool = False
    preserve_locomotion: bool = False
    normalize_scaling: bool = False
    boss_canary: bool = False
    # Reviewed encounter packages are an explicit experimental opt-in.  Keep
    # this separate from the legacy single canary so their receipts cannot be
    # confused in a seed cache.
    boss_pool: str | None = None
    # Release tranches replace one blanket exclusion each with reviewed
    # compatibility handling (docs/ENEMIZER-EXPANSION.md). All default off;
    # the conservative 308-swap policy is unchanged unless opted in.
    release_contracts: bool = False
    release_spawns: bool = False
    release_chara: bool = False


@dataclass(frozen=True)
class EnemizerBuild:
    map_studio: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    # The plan file the writer consumed; retained in the seed cache so a bad
    # swap can be named from a player's report (bb-archipelago#321).
    plan_path: Path | None = None
    overlay: Path | None = None


@dataclass(frozen=True)
class PreparedSeed:
    install: GameInstall
    request: Mapping[str, Any]
    plan: ProcessPlan
    identity: SeedIdentity
    suppression: SuppressionValidation
    build: BuildResult
    reused: bool
    enemizer: EnemizerBuild | None


@dataclass(frozen=True)
class WorkflowResult:
    cache_key: str
    build_path: Path
    reused: bool
    enemizer_enabled: bool
    enemizer_swaps: int
    process_ids: tuple[int | None, ...]
    client_config: Path
    ledger: Path
    # True when the launch plan pinned a CE bridge, so the UI knows item
    # grants are expected and can watch for the harness reporting in.
    grants_bridge: bool
    # The captured AP client output for this session, and the first component
    # observed to die inside the post-launch watch window (bb-archipelago#171).
    client_log: Path | None = None
    # shadPS4's captured output for this session (bb-archipelago#175).
    shad_process_log: Path | None = None
    early_exit: EarlyExit | None = None


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} is not a JSON object: {path}")
    return value


def _resolve_from(path: Path, raw: str) -> Path:
    value = Path(raw).expanduser()
    return (path.parent / value).resolve() if not value.is_absolute() else value.resolve()


def load_process_plan(path: Path | str) -> ProcessPlan:
    source = Path(path).expanduser().resolve()
    value = _read_object(source, "process plan")
    if value.get("format") != PROCESS_PLAN_FORMAT:
        raise ValidationError(f"unsupported process plan format in {source}")
    shad_build = value.get("shad_build")
    runtime_build = value.get("runtime_build")
    if not isinstance(shad_build, str) or not shad_build.strip():
        raise ValidationError("process plan requires a non-empty shad_build")
    if not isinstance(runtime_build, str) or not runtime_build.strip():
        raise ValidationError("process plan requires a non-empty runtime_build")
    records = value.get("processes")
    if not isinstance(records, list) or not records:
        raise ValidationError("process plan must carry a non-empty processes list")
    processes: list[ProcessSpec] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValidationError(f"process plan record {index} is not an object")
        name = record.get("name")
        executable = record.get("executable")
        arguments = record.get("arguments", [])
        expected_hash = record.get("sha256")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError(f"process plan record {index} has no name")
        if not isinstance(executable, str) or not executable.strip():
            raise ValidationError(f"process plan record {index} has no executable")
        if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
            raise ValidationError(f"process plan {name} arguments must be strings")
        if not isinstance(expected_hash, str) or not expected_hash:
            raise ValidationError(f"process plan {name} requires a sha256")
        raw_working = record.get("working_directory")
        working = None
        if raw_working is not None:
            if not isinstance(raw_working, str) or not raw_working:
                raise ValidationError(f"process plan {name} has an invalid working_directory")
            working = _resolve_from(source, raw_working)
        processes.append(
            ProcessSpec(
                name=name,
                executable=_resolve_from(source, executable),
                arguments=tuple(arguments),
                working_directory=working,
                expected_sha256=expected_hash,
            )
        )
    return ProcessPlan(shad_build, runtime_build, tuple(processes))


def captured_process_logs(
    paths: ClientRuntimePaths | None,
) -> dict[str, Path]:
    """Session log destinations keyed by process name.

    Only the two children a generated plan emits are captured; a host-authored
    entry such as the CE bridge keeps whatever logging it brought.  The plan
    file format is untouched -- these are attached at resolve time.
    """

    if paths is None:
        return {}
    return {
        CLIENT_PROCESS_NAME: paths.client_log,
        SHAD_PROCESS_NAME: paths.shad_process_log,
    }


def refuse_stale_plan(plan: ProcessPlan) -> None:
    """Refuse a plan pinned before bb-archipelago#177.

    Called before any mutation on every launch path, and again from
    :func:`resolve_process_plan` as the backstop, so no caller can route around
    it. Regenerating is the player's move -- the launcher does not silently
    rewrite a plan file a player may have hand-validated.
    """

    stale = stale_bare_serial_process(plan.processes)
    if stale is not None:
        raise ValidationError(
            f"{stale.name} still launches the game by bare game ID; "
            + STALE_BARE_SERIAL_REMEDY
        )


def _without_client_processes(plan: ProcessPlan) -> ProcessPlan:
    """Drop every entry that only a randomized session can satisfy.

    An entry naming any client placeholder consumes files the client runtime
    configuration writer produces, so it has nothing to run against on a
    vanilla launch (bb-archipelago review W3).
    """

    kept = tuple(
        spec
        for spec in plan.processes
        if not any(
            "{" + name + "}" in argument
            for argument in spec.arguments
            for name in CLIENT_PLACEHOLDERS
        )
    )
    return ProcessPlan(
        shad_build=plan.shad_build, runtime_build=plan.runtime_build, processes=kept
    )


def resolve_process_plan(
    plan: ProcessPlan,
    paths: ClientRuntimePaths | None,
    *,
    game_path: Path | None = None,
) -> ProcessPlan:
    """Return the plan with launch-time placeholders substituted throughout.

    ``game_path`` is the game directory shadPS4 should boot -- the installation's
    own ``CUSA03173`` folder, which is what the ``{game_path}`` placeholder in a
    generated plan resolves to (bb-archipelago#177).

    Both children get a session ``log_path``, because that names the file the
    early-exit dialog reads.  Who *writes* it is decided by the entry's own
    arguments: one that carries ``--log-file`` tees console and file itself
    (clients#425) and is marked ``self_logging``, so the launcher leaves its
    output alone; anything else keeps the launcher's tee.  A generated plan
    passes the flag to the AP client and not to shadPS4, and a plan pinned
    before bb-archipelago#181 passes it to nobody -- which is the right answer
    for a stale plan paired with any client build.
    """

    refuse_stale_plan(plan)
    logs = captured_process_logs(paths)
    return ProcessPlan(
        shad_build=plan.shad_build,
        runtime_build=plan.runtime_build,
        processes=tuple(
            ProcessSpec(
                name=spec.name,
                executable=spec.executable,
                arguments=substitute_plan_arguments(
                    spec.arguments, paths, game_path=game_path
                ),
                working_directory=spec.working_directory,
                expected_sha256=spec.expected_sha256,
                log_path=logs.get(spec.name, spec.log_path),
                # Read from the arguments, not from the process name: an entry
                # that was told --log-file writes its own session log
                # (clients#425) and must keep the console it inherited, because
                # piping it would take away the very console its tee exists to
                # preserve. An entry that was NOT told keeps the launcher's own
                # tee (bb-archipelago#179) -- which is exactly what a plan
                # pinned before bb-archipelago#181 needs, so a stale plan keeps
                # a populated client.log instead of silently losing it.
                self_logging=(CLIENT_LOG_FLAG in spec.arguments),
            )
            for spec in plan.processes
        ),
    )


def run_command(command: Sequence[str], working_directory: Path, progress: Progress) -> None:
    """Run one tool without opening a console and stream bounded diagnostics."""

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        process = subprocess.Popen(
            [str(argument) for argument in command],
            cwd=str(working_directory),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=flags,
        )
    except OSError as exc:
        raise WorkflowError(f"could not start build tool {command[0]}: {exc}") from exc
    assert process.stdout is not None
    tail: list[str] = []
    for raw in process.stdout:
        line = raw.rstrip()
        if line:
            progress(line)
            tail.append(line)
            tail = tail[-20:]
    code = process.wait()
    if code != 0:
        detail = "\n".join(tail)
        raise WorkflowError(
            f"build tool exited with code {code}: {' '.join(map(str, command[:4]))}"
            + (f"\n{detail}" if detail else "")
        )


class EnemizerToolchain:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        runner: CommandRunner = run_command,
        python: str | Path = sys.executable,
        dotnet: str | Path = "dotnet",
        app_root: Path | str | None = None,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.app_root = Path(app_root or application_root()).expanduser().resolve()
        self.runner = runner
        self.python = str(python)
        self.dotnet = str(dotnet)

    @property
    def planner_executable(self) -> Path:
        return self.app_root / "tools" / "BBEnemizerPlanner" / "BBEnemizerPlanner.exe"

    @property
    def writer_executable(self) -> Path:
        return self.app_root / "tools" / "BBEnemizerWriter.exe"

    @property
    def parameter_writer_executable(self) -> Path:
        return self.app_root / "tools" / "BBSuppressionWriter.exe"

    @property
    def event_writer_executable(self) -> Path:
        return self.app_root / "tools" / "BBEventWriter.exe"

    @property
    def miner_executable(self) -> Path:
        return self.app_root / "tools" / "MSBBMiner.exe"

    @property
    def boss_encounter_builder_executable(self) -> Path:
        return (self.app_root / "tools" / "BBBossEncounterBuilder"
                / "BBBossEncounterBuilder.exe")

    @property
    def is_bundled(self) -> bool:
        return all(
            path.is_file()
            for path in (self.planner_executable, self.writer_executable, self.miner_executable)
        )

    def write_seed_weapons(
        self, *, request_path: Path, input_binder: Path, paramdef: Path,
        output_binder: Path, soulsformats_next: Path | None, progress: Progress,
    ) -> None:
        if self.parameter_writer_executable.is_file():
            command = [str(self.parameter_writer_executable)]
        else:
            if soulsformats_next is None or not soulsformats_next.is_dir():
                raise ValidationError(
                    "SoulsFormatsNEXT is required when the packaged parameter writer is unavailable"
                )
            command = [
                self.dotnet, "run", "--project",
                str(self.repo_root / "tools" / "bb_suppression_writer" / "BBSuppressionWriter.csproj"),
                "-c", "Release", f"-p:SoulsFormatsNextRoot={soulsformats_next}", "--",
            ]
        command.extend([
            "--seed-weapons", str(request_path), str(input_binder), str(paramdef),
            str(output_binder), "--apply",
        ])
        progress("Writing seed-specific weapon and shop parameters...")
        self.runner(command, self.repo_root, progress)
        if not output_binder.is_file():
            raise ValidationError("parameter writer produced no starting-weapon binder")

    def _event_writer_command(self, soulsformats_next: Path | None) -> list[str]:
        if self.event_writer_executable.is_file():
            return [str(self.event_writer_executable)]
        if soulsformats_next is None or not soulsformats_next.is_dir():
            raise ValidationError(
                "SoulsFormatsNEXT is required when the packaged event writer is unavailable"
            )
        return [
            self.dotnet, "run", "--project",
            str(self.repo_root / "tools" / "bb_event_writer" / "BBEventWriter.csproj"),
            "-c", "Release", f"-p:SoulsFormatsNextRoot={soulsformats_next}", "--",
        ]

    def write_pickup_names(
        self, *, plan: Mapping[str, Any], input_binder: Path, paramdef: Path,
        input_names: Path, output_binder: Path, output_names: Path,
        soulsformats_next: Path | None, progress: Progress, canary: bool = False,
    ) -> None:
        executable = self.app_root / "tools" / "BBToastWriter.exe"
        if executable.is_file():
            command = [str(executable)]
        else:
            if soulsformats_next is None or not soulsformats_next.is_dir():
                raise ValidationError("SoulsFormatsNEXT is required when the packaged pickup-name writer is unavailable")
            command = [self.dotnet, "run", "--project",
                       str(self.repo_root / "tools/bb_toast_writer/BBToastWriter.csproj"),
                       "-c", "Release", f"-p:SoulsFormatsNextRoot={soulsformats_next}", "--"]
        plan_path = output_binder.with_suffix(".toast-plan.json")
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        command.extend([str(plan_path), str(input_binder), str(paramdef), str(input_names),
                        str(output_binder), str(output_names),
                        "--canary" if canary else "--probe-confirmed", "--apply"])
        progress("Writing and verifying randomized pickup names...")
        self.runner(command, self.repo_root, progress)
        if not output_binder.is_file() or not output_names.is_file():
            raise ValidationError("pickup-name writer did not produce both archives")

    def write_cathedral_event(
        self, *, source: Path, output: Path, manifest: Path,
        soulsformats_next: Path | None, progress: Progress, access_flag: int | None = None,
    ) -> None:
        """Write the Laurence's Skull / Hunter Chief Emblem overlay for m24_00_00_00.

        The writer edits the licensed event file in place with SoulsFormats and
        refuses the result unless every unrelated event is byte-identical to
        the source; see docs/EVENT-WRITER.md.
        """
        command = self._event_writer_command(soulsformats_next)
        command.extend([
            "cathedral", "--source", str(source), "--output", str(output),
            "--manifest", str(manifest),
        ])
        if access_flag is not None:
            command.extend(["--access-flag", str(access_flag)])
        progress("Writing and verifying the Cathedral event overlay...")
        self.runner(command, self.repo_root, progress)
        if not output.is_file() or not manifest.is_file():
            raise ValidationError("event writer produced no Cathedral event overlay")

    def write_hemwick_event(
        self, *, source: Path, output: Path, manifest: Path, access_flag: int,
        soulsformats_next: Path | None, progress: Progress,
    ) -> None:
        command = self._event_writer_command(soulsformats_next)
        command.extend(["hemwick", "--source", str(source), "--output", str(output),
                        "--manifest", str(manifest), "--access-flag", str(access_flag)])
        progress("Writing and verifying the Hemwick access gate overlay...")
        self.runner(command, self.repo_root, progress)
        if not output.is_file() or not manifest.is_file():
            raise ValidationError("event writer produced no Hemwick event overlay")

    def write_common_event(
        self, *, request_path: Path, source: Path, output: Path, manifest: Path,
        soulsformats_next: Path | None, progress: Progress,
    ) -> None:
        """Write the category-8 award bridge (event 98000000) into common.emevd."""
        command = self._event_writer_command(soulsformats_next)
        command.extend([
            "common", "--source", str(source), "--request", str(request_path),
            "--output", str(output), "--manifest", str(manifest),
        ])
        progress("Writing and verifying the category-8 common event overlay...")
        self.runner(command, self.repo_root, progress)
        if not output.is_file() or not manifest.is_file():
            raise ValidationError("event writer produced no common event overlay")

    def write_enemy_ai(
        self, *, manifest: Mapping[str, Any], install: GameInstall,
        output_root: Path, soulsformats_next: Path | None, progress: Progress,
    ) -> Path:
        sources = enemy_ai_sources(install)
        stage = output_root / "ai-input"
        stage.mkdir()
        for relative, source in sources.items():
            destination = stage / Path(relative).name
            shutil.copyfile(source, destination)
            if sha256_file(source) != sha256_file(destination):
                raise ValidationError(f"enemy AI source copy failed: {relative}")
        plan_path = output_root / "enemy-ai-plan.json"
        plan_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        output = output_root / "script"
        if self.writer_executable.is_file():
            command = [str(self.writer_executable)]
        else:
            if soulsformats_next is None:
                raise ValidationError("SoulsFormatsNEXT is required for the enemy AI writer")
            command = [self.dotnet, "run", "--project",
                       str(self.repo_root / "tools/bb_enemizer_writer/BBEnemizerWriter.csproj"),
                       "-c", "Release", f"-p:SoulsFormatsNextRoot={soulsformats_next}", "--"]
        command.extend(["--ai", str(plan_path),
                        str(install.resolve_file(SUPPRESSION_PATH, include_mods=False)[1]),
                        str(install.resolve_file(PARAMDEF_PATH, include_mods=False)[1]),
                        str(stage), str(output), "--apply"])
        progress("Transplanting and verifying enemy AI scripts...")
        self.runner(command, self.repo_root, progress)
        report = _read_object(output_root / "script.json", "enemy AI report")
        if (report.get("format") != "bb-enemizer-ai-v1" or report.get("applied") is not True
                or report.get("plan_sha256") != sha256_file(plan_path)):
            raise ValidationError("enemy AI writer produced an invalid report")
        records = report.get("maps")
        if not isinstance(records, list) or not records:
            raise ValidationError("enemy AI writer produced no map records")
        paths = []
        for record in records:
            name = str(record.get("map", ""))
            if re.fullmatch(AI_FILE_PATTERN, name) is None or record.get("missing_goals_after") != 0:
                raise ValidationError("enemy AI report contains an invalid map or missing goals")
            path = output / name
            if not path.is_file() or path.is_symlink() or sha256_file(path) != record.get("output_sha256"):
                raise ValidationError(f"enemy AI output verification failed: {name}")
            paths.append(path)
        if len(set(paths)) != len(paths) or set(output.iterdir()) != set(paths):
            raise ValidationError("enemy AI output file set differs from its report")
        return output

    def build(
        self,
        *,
        seed: str,
        inventory: Path | None,
        map_studio_source: Path,
        soulsformats_next: Path | None,
        output_root: Path,
        allow_tier_mixing: bool,
        preserve_locomotion: bool,
        progress: Progress,
        normalize_scaling: bool = False,
        boss_canary: bool = False,
        plan_only: bool = False,
        release_contracts: bool = False,
        release_spawns: bool = False,
        release_chara: bool = False,
        release_wakeup: bool = True,
    ) -> EnemizerBuild:
        for path, label, kind in ((map_studio_source, "source MapStudio", "directory"),):
            exists = path.is_file() if kind == "file" else path.is_dir()
            if not exists:
                raise ValidationError(f"{label} {kind} does not exist: {path}")
        if not seed.strip():
            raise ValidationError("enemy randomization requires a non-empty seed")
        # The workflow hands us a directory tempfile.mkdtemp already created;
        # creating it again is a bare WinError 183 on Windows.
        output_root.mkdir(parents=True, exist_ok=True)
        plan_path = output_root / "bb-enemizer-plan.json"
        map_output = output_root / "MapStudio"
        if inventory is None:
            if not self.miner_executable.is_file():
                raise ValidationError(
                    "enemy inventory is required when the packaged MSBB miner is unavailable"
                )
            mined = output_root / "mined"
            progress("Reading enemy slots from the installed maps...")
            self.runner(
                [self.miner_executable, map_studio_source, mined, "--fixed-maps-only"],
                self.repo_root,
                progress,
            )
            inventory = mined / "msb_enemies.tsv"
        if not inventory.is_file():
            raise ValidationError(f"enemy inventory file does not exist: {inventory}")
        planner = (
            [str(self.planner_executable)]
            if self.planner_executable.is_file()
            else [self.python, "-m", "tools.bb_enemizer.cli"]
        ) + [
            "--seed",
            seed,
            "--inventory",
            str(inventory),
            "--tags",
            str(self.repo_root / "research" / "enemizer" / "enemy_tags.json"),
            "--slot-policy",
            str(self.repo_root / "research" / "enemizer" / "slot_policy.json"),
            "--facts",
            str(self.repo_root / "research" / "enemizer" / "archetype_facts.json"),
            "--output",
            str(plan_path),
        ]
        if allow_tier_mixing:
            planner.append("--allow-tier-mixing")
        if preserve_locomotion:
            planner.append("--preserve-locomotion")
        for enabled, name in ((release_contracts, "contracts"),
                              (release_spawns, "spawns"),
                              (release_chara, "chara")):
            if not enabled:
                continue
            record = self.repo_root / "research" / "enemizer" / f"release_{name}.json"
            if not record.is_file():
                raise ValidationError(
                    f"enemy release tranche {name!r} requested but {record} is not packaged")
            planner.extend(["--release-file", str(record)])
        if release_wakeup and (release_contracts or release_spawns or release_chara):
            wakeup_record = self.repo_root / "research" / "enemizer" / "release_wakeup.json"
            if not wakeup_record.is_file():
                raise ValidationError(
                    f"enemy release tranche 'wakeup' requested but {wakeup_record} is not packaged")
            planner.extend(["--release-file", str(wakeup_record)])
        if normalize_scaling:
            planner.append("--normalize-scaling")
        if boss_canary:
            planner.append("--boss-canary")
        if normalize_scaling or boss_canary:
            planner.extend(['--bundle', str(self.repo_root / 'research/bb_inputs.db')])
        progress("Planning deterministic enemy swaps...")
        self.runner(planner, self.repo_root, progress)
        plan = _read_object(plan_path, "enemizer plan")
        if plan.get("format") != PLAN_FORMAT or plan.get("dry_run") is not True:
            raise ValidationError("planner produced an unsupported or non-dry-run manifest")
        if str(plan.get("seed")) != seed:
            raise ValidationError("planner output seed does not match the requested enemy seed")
        swaps = plan.get("swaps")
        if not isinstance(swaps, list) or not swaps:
            raise ValidationError("enemy randomization produced zero safe swaps")
        if plan_only:
            return EnemizerBuild(map_output, plan, sha256_file(plan_path), plan_path)
        if self.writer_executable.is_file():
            writer = [
                str(self.writer_executable),
                str(plan_path),
                str(map_studio_source),
                str(map_output),
                "--apply",
            ]
        else:
            if soulsformats_next is None or not soulsformats_next.is_dir():
                raise ValidationError(
                    "SoulsFormatsNEXT is required when the packaged enemizer writer is unavailable"
                )
            writer_project = self.repo_root / "tools" / "bb_enemizer_writer" / "BBEnemizerWriter.csproj"
            writer = [
                self.dotnet,
                "run",
                "--project",
                str(writer_project),
                "-c",
                "Release",
                f"-p:SoulsFormatsNextRoot={soulsformats_next}",
                "--",
                str(plan_path),
                str(map_studio_source),
                str(map_output),
                "--apply",
            ]
        progress(f"Writing and reopening {len(swaps)} planned enemy swaps...")
        self.runner(writer, self.repo_root, progress)
        outputs = sorted(map_output.glob("*.msb.dcx")) if map_output.is_dir() else []
        other = sorted(
            path.name for path in map_output.iterdir() if path.is_file() and path not in outputs
        ) if map_output.is_dir() else []
        if not outputs:
            raise ValidationError(
                "enemizer writer produced no compressed *.msb.dcx maps; select the installed compressed MapStudio source"
            )
        if other:
            raise ValidationError("enemizer writer produced unexpected files: " + ", ".join(other))
        progress(f"Verified {len(outputs)} randomized map file(s).")
        return EnemizerBuild(map_output, plan, sha256_file(plan_path), plan_path)

    def write_wakeup_fallback(
        self, *, plan_path: Path, source_event: Path, output_event: Path,
        report_path: Path, expected_fallbacks: Sequence[Mapping[str, Any]],
        soulsformats_next: Path | None,
        progress: Progress = lambda _message: None,
    ) -> Mapping[str, Any]:
        """Apply only the planner-recorded sleep fallbacks to m24_01's event."""

        for path, label in ((plan_path, "wakeup fallback plan"),
                            (source_event, "wakeup fallback source event")):
            if not path.is_file() or path.is_symlink():
                raise ValidationError(f"{label} is not a regular file: {path}")
        output_event.parent.mkdir(parents=True, exist_ok=True)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        if self.writer_executable.is_file():
            command = [str(self.writer_executable)]
        else:
            if soulsformats_next is None:
                raise ValidationError("SoulsFormatsNEXT is required for the wakeup fallback writer")
            command = [self.dotnet, "run", "--project",
                       str(self.repo_root / "tools/bb_enemizer_writer/BBEnemizerWriter.csproj"),
                       "-c", "Release", f"-p:SoulsFormatsNextRoot={soulsformats_next}", "--"]
        command.extend(["--wakeup-fallback", str(plan_path), str(source_event),
                        str(output_event), str(report_path)])
        self.runner(
            command,
            self.repo_root, progress,
        )
        report = _read_object(report_path, "wakeup fallback report")
        if (report.get("format") != "bb-enemizer-wakeup-fallback-v1"
                or report.get("applied") is not True
                or report.get("plan_sha256") != sha256_file(plan_path)
                or report.get("source_event_sha256") != sha256_file(source_event)
                or report.get("wakeup_fallbacks") != list(expected_fallbacks)
                or not output_event.is_file() or output_event.is_symlink()
                or report.get("output_event_sha256") != sha256_file(output_event)):
            raise ValidationError("wakeup fallback writer produced an invalid report or event")
        return report

    def build_experimental(self, *, options: EnemizerOptions, install: GameInstall,
                           input_binder: Path, **kwargs) -> EnemizerBuild:
        from tools.verify_boss_canary import verify as verify_boss
        planned = self.build(**kwargs, normalize_scaling=True,
                             boss_canary=options.boss_canary, plan_only=True)
        root = kwargs['output_root']
        inputs = root / 'experimental-input'
        stage = inputs / 'ai'
        stage.mkdir(parents=True)
        staged_plan = inputs / 'plan.json'
        staged_binder = inputs / 'gameparam.parambnd.dcx'
        shutil.copyfile(planned.plan_path, staged_plan)
        shutil.copyfile(input_binder, staged_binder)
        if sha256_file(staged_plan) != planned.manifest_sha256 or sha256_file(staged_binder) != sha256_file(input_binder):
            raise ValidationError('experimental plan/parameter input copy failed')
        for relative, source in enemy_ai_sources(install).items():
            destination = stage / Path(relative).name
            shutil.copyfile(source, destination)
            if sha256_file(source) != sha256_file(destination):
                raise ValidationError('enemy AI input copy failed')
        output = root / 'experimental-overlay'
        sf = kwargs['soulsformats_next']
        if self.writer_executable.is_file():
            command = [str(self.writer_executable)]
        else:
            if sf is None:
                raise ValidationError('SoulsFormatsNEXT is required for experimental enemy builds')
            command = [self.dotnet, 'run', '--project', str(self.repo_root / 'tools/bb_enemizer_writer'),
                       '-c', 'Release', f'-p:SoulsFormatsNextRoot={sf}', '--']
        command += ['--boss-native' if options.boss_canary else '--scaled', str(staged_plan),
                    str(staged_binder), str(install.resolve_file(PARAMDEF_PATH, include_mods=False)[1]),
                    str(kwargs['map_studio_source']), str(stage)]
        if options.boss_canary:
            command.append(str(install.resolve_file(BOSS_EVENT_PATH, include_mods=False)[1]))
        command += [str(output), '--apply']
        kwargs['progress']('Building experimental enemy normalization' + (' and BSB boss encounter...' if options.boss_canary else '...'))
        self.runner(command, self.repo_root, kwargs['progress'])
        if options.boss_canary:
            verify_boss(output)
        adjusted = output / 'bb-enemizer-plan.json'
        plan = _read_object(adjusted, 'adjusted enemy plan')
        receipt = _read_object(output / 'scaling-report.json', 'scaling receipt')
        if (receipt.get('applied') is not True or receipt.get('output_plan_sha256') != sha256_file(adjusted)
                or receipt.get('source_plan_sha256') != planned.manifest_sha256
                or receipt.get('source_gameparam_sha256') != sha256_file(input_binder)
                or receipt.get('output_gameparam_sha256') != sha256_file(output / SUPPRESSION_PATH)):
            raise ValidationError('experimental scaling provenance mismatch')
        return EnemizerBuild(output / 'dvdroot_ps4/map/MapStudio', plan, sha256_file(adjusted), adjusted, output)

    def build_boss_encounters(
        self, *, options: EnemizerOptions, install: GameInstall, input_binder: Path,
        darkscript: Path, event_overrides: Mapping[str, Path], **kwargs,
    ) -> EnemizerBuild:
        """Compose one ordinary normalized plan and the reviewed boss pool.

        The Python builder is deliberately the only component that combines
        ordinary and boss allocations.  It receives complete, effective game
        inputs, including AP event rewrites, and publishes its own audited
        overlay rather than allowing launcher-side file splicing.
        """
        if options.boss_pool != "reviewed":
            raise ValidationError("unsupported reviewed boss pool")
        if not darkscript.is_file():
            raise ValidationError(f"reviewed boss encounters require DarkScript3: {darkscript}")
        planned = self.build(**kwargs, normalize_scaling=True, plan_only=True)
        root = kwargs["output_root"]
        inputs = root / "boss-encounter-input"
        maps = inputs / "MapStudio"
        scripts = inputs / "script"
        events = inputs / "event"
        sfx = inputs / "sfx"
        overrides = inputs / "event-overrides"
        for directory in (maps, scripts, events, sfx, overrides):
            directory.mkdir(parents=True)
        for source in kwargs["map_studio_source"].iterdir():
            if source.is_file() and source.name.lower().endswith((".msb", ".msb.dcx")):
                target = maps / source.name
                shutil.copyfile(source, target)
                if sha256_file(source) != sha256_file(target):
                    raise ValidationError(f"boss map input copy failed: {source.name}")
        for relative, source in enemy_ai_sources(install).items():
            target = scripts / Path(relative).name
            shutil.copyfile(source, target)
            if sha256_file(source) != sha256_file(target):
                raise ValidationError(f"boss AI input copy failed: {relative}")
        for relative, source in encounter_event_sources(install).items():
            target = events / Path(relative).name
            shutil.copyfile(source, target)
            if sha256_file(source) != sha256_file(target):
                raise ValidationError(f"boss event input copy failed: {relative}")
        for relative, source in encounter_sfx_sources(install).items():
            target = sfx / Path(relative).name
            shutil.copyfile(source, target)
            if sha256_file(source) != sha256_file(target):
                raise ValidationError(f"boss SFX input copy failed: {relative}")
        for relative, source in event_overrides.items():
            if relative not in encounter_event_sources(install):
                raise ValidationError(f"unsupported AP event override for reviewed boss pool: {relative}")
            if not source.is_file() or source.is_symlink():
                raise ValidationError(f"AP event override is not a regular file: {source}")
            target = overrides / Path(relative).name
            shutil.copyfile(source, target)
            if sha256_file(source) != sha256_file(target):
                raise ValidationError(f"boss AP event override copy failed: {relative}")
        if not self.boss_encounter_builder_executable.is_file():
            raise ValidationError(
                "reviewed boss encounters require the packaged BBBossEncounterBuilder tool"
            )
        if not self.writer_executable.is_file():
            raise ValidationError(
                "reviewed boss encounters require the packaged BBEnemizerWriter tool"
            )
        staged_binder = inputs / "gameparam.parambnd.dcx"
        shutil.copyfile(input_binder, staged_binder)
        if sha256_file(staged_binder) != sha256_file(input_binder):
            raise ValidationError("boss parameter input copy failed")
        output = root / "boss-encounter-overlay"
        command = [
            str(self.boss_encounter_builder_executable),
            "--darkscript", str(darkscript), "--writer", str(self.writer_executable),
            "--gameparam", str(staged_binder),
            "--paramdef", str(install.resolve_file(PARAMDEF_PATH, include_mods=False)[1]),
            "--maps", str(maps), "--scripts", str(scripts), "--events", str(events),
            "--sfx", str(sfx),
            "--event-overrides", str(overrides),
            "--ordinary-plan", str(planned.plan_path), "--pool", "reviewed",
            "--bundle", str(self.repo_root / "research" / "bb_inputs.db"),
            "--seed", kwargs["seed"], "--output", str(output), "--apply",
        ]
        kwargs["progress"]("Building experimental reviewed boss encounters...")
        self.runner(command, self.repo_root, kwargs["progress"])
        receipt = _read_object(output / "boss-encounters-report.json", "boss encounter receipt")
        adjusted = output / "bb-enemizer-plan.json"
        if (receipt.get("format") != "bb-boss-encounters-v1" or receipt.get("applied") is not True
                or not isinstance(receipt.get("files"), list) or not receipt["files"]
                or not adjusted.is_file()):
            raise ValidationError("reviewed boss builder produced an invalid receipt")
        return EnemizerBuild(output / "dvdroot_ps4/map/MapStudio", _read_object(adjusted, "combined enemy plan"),
                             sha256_file(adjusted), adjusted, output)

    def boss_encounter_identity_inputs(self, inventory: Path | None) -> dict[str, Path]:
        """Every executable and data input that can alter a reviewed build."""
        paths = {
            "launcher-tools/boss-inputs.db": self.repo_root / "research" / "bb_inputs.db",
            "launcher-tools/boss-builder.exe": self.boss_encounter_builder_executable,
            "launcher-tools/boss-writer.exe": self.writer_executable,
            "launcher-tools/boss-planner.exe": self.planner_executable,
            "launcher-tools/boss-event-writer.exe": self.event_writer_executable,
        }
        if inventory is None:
            paths["launcher-tools/boss-miner.exe"] = self.miner_executable
        else:
            paths["launcher-input/enemy-inventory.tsv"] = inventory.expanduser().resolve()
        for label, path in paths.items():
            if not path.is_file() or path.is_symlink():
                raise ValidationError(f"reviewed boss encounters require {path} ({label})")
        return paths


def _request_identity(
    request_path: Path,
    *,
    player_name: str = "",
    state_root: Path | None = None,
) -> dict[str, Any]:
    """Identity of the seed request the player chose.

    ``request_path`` is either a request document or the Archipelago
    multiworld zip (bb-archipelago#194); a zip is resolved to its Bloodborne
    member first, and the resolution rides along in the returned identity so
    the Doctor can name both halves.
    """
    resolved = resolve_request_source(
        request_path, player_name=player_name, state_root=state_root
    )
    request = _read_object(resolved.path, "AP seed file")
    if request.get("format") not in REQUEST_FORMATS:
        raise ValidationError(
            f"expected a {REQUEST_FORMAT} file (or legacy {LEGACY_REQUEST_FORMAT})"
        )
    player = request.get("player")
    player_name = request.get("player_name")
    runtime_build = request.get("runtime_build")
    world_version = request.get("world_version")
    enemizer_seed = request.get("enemizer_seed")
    suppression = request.get("suppression")
    if not isinstance(player, int) or player < 1:
        raise ValidationError("AP request has no valid player number")
    if not isinstance(player_name, str) or not player_name.strip():
        raise ValidationError("AP request has no player_name")
    if not isinstance(runtime_build, str) or not runtime_build.strip():
        raise ValidationError("AP request has no runtime_build")
    if not isinstance(world_version, str) or not world_version.strip():
        raise ValidationError("AP request has no world_version")
    if not isinstance(enemizer_seed, str) or not enemizer_seed.strip():
        raise ValidationError("AP request has no enemizer_seed")
    if not isinstance(suppression, dict) or not isinstance(suppression.get("plan_sha256"), str):
        raise ValidationError("AP request has no suppression plan hash")
    auto_upgrade = request.get("auto_upgrade", False)
    auto_equip = request.get("auto_equip", False)
    if not isinstance(auto_upgrade, bool):
        raise ValidationError("AP request has invalid auto_upgrade")
    if not isinstance(auto_equip, bool):
        raise ValidationError("AP request has invalid auto_equip")
    randomize_starting = request.get("randomize_starting_weapons", False)
    starting_weapons = request.get("starting_weapons")
    if not isinstance(randomize_starting, bool):
        raise ValidationError("AP request has invalid randomize_starting_weapons")
    if randomize_starting:
        if not isinstance(starting_weapons, dict):
            raise ValidationError("AP request has no starting weapon choices")
        for hand, count in (("right_hand", 3), ("left_hand", 2)):
            values = starting_weapons.get(hand)
            if (not isinstance(values, list) or len(values) != count
                    or any(not isinstance(value, int) or value <= 0 for value in values)
                    or len(set(values)) != count):
                raise ValidationError(f"AP request has invalid {hand} starting weapon choices")
    elif starting_weapons is not None:
        raise ValidationError("AP request disables starting weapons but still supplies choices")
    remove_requirements = request.get("remove_weapon_requirements", False)
    requirement_families = request.get("weapon_requirement_families")
    if not isinstance(remove_requirements, bool):
        raise ValidationError("AP request has invalid remove_weapon_requirements")
    if remove_requirements:
        if (not isinstance(requirement_families, list) or not requirement_families
                or any(not isinstance(value, int) or value <= 0 for value in requirement_families)
                or len(set(requirement_families)) != len(requirement_families)):
            raise ValidationError("AP request has invalid weapon requirement families")
    elif requirement_families is not None:
        raise ValidationError("AP request keeps weapon requirements but still supplies families")
    randomize_shops = request.get("randomize_shops", False)
    shop_gate_permutation = request.get("shop_gate_permutation")
    if not isinstance(randomize_shops, bool):
        raise ValidationError("AP request has invalid randomize_shops")
    expected_shop_gates = {str(value) for value in range(12101000, 12101010)}
    if randomize_shops:
        if (not isinstance(shop_gate_permutation, dict)
                or set(shop_gate_permutation) != expected_shop_gates
                or any(not isinstance(value, int) for value in shop_gate_permutation.values())
                or set(shop_gate_permutation.values()) != {int(value) for value in expected_shop_gates}):
            raise ValidationError("AP request has invalid Bath shop gate permutation")
    elif shop_gate_permutation is not None:
        raise ValidationError("AP request disables shop randomization but still supplies a permutation")
    randomize_enemy_drops = request.get("randomize_enemy_drops", False)
    # Requests emitted by the first implementation predate the named mode;
    # enabled legacy requests mean the original balanced behavior.
    enemy_drop_mode = request.get(
        "enemy_drop_mode", "balanced" if randomize_enemy_drops else None)
    enemy_drop_assignments = request.get("enemy_drop_assignments")
    # v2 rewrites table contents into new ItemLotParam rows; v1 permuted whole
    # vanilla tables. Old seeds already in flight carry no marker, so the plan
    # shape is chosen by the marker and never guessed from the payload.
    enemy_drop_plan_format = request.get("enemy_drop_plan_format")
    from worlds.bloodborne.enemy_drops import PLAN_FORMAT as ENEMY_DROP_PLAN_FORMAT
    if not isinstance(randomize_enemy_drops, bool):
        raise ValidationError("AP request has invalid randomize_enemy_drops")
    if randomize_enemy_drops:
        if enemy_drop_mode not in {"balanced", "dropsanity"}:
            raise ValidationError("AP request has invalid enemy drop mode")
        if enemy_drop_plan_format not in {None, ENEMY_DROP_PLAN_FORMAT}:
            raise ValidationError("AP request has an unsupported enemy drop plan format")
        if not isinstance(enemy_drop_assignments, list) or not enemy_drop_assignments:
            raise ValidationError("AP request has no enemy drop assignments")
        seen_drop_fields: set[tuple[int, str]] = set()
        seen_lot_ids: set[int] = set()
        for assignment in enemy_drop_assignments:
            if not isinstance(assignment, dict):
                raise ValidationError("AP request has an invalid enemy drop assignment")
            npc_id = assignment.get("npc_param_id")
            field = assignment.get("drop_field")
            source_lot = assignment.get("source_lot_id")
            key = (npc_id, field)
            if (not isinstance(npc_id, int) or npc_id <= 0
                    or not isinstance(field, str) or field not in {
                        f"itemLotId_{index}" for index in range(1, 7)}
                    or not isinstance(source_lot, int) or source_lot <= 0
                    or key in seen_drop_fields):
                raise ValidationError("AP request has an invalid enemy drop assignment")
            seen_drop_fields.add(key)
            if enemy_drop_plan_format is None:
                target_lot = assignment.get("target_lot_id")
                if (not isinstance(target_lot, int) or target_lot <= 0
                        or target_lot == source_lot):
                    raise ValidationError("AP request has an invalid enemy drop assignment")
                continue
            lot = assignment.get("lot")
            if not isinstance(lot, dict):
                raise ValidationError("AP request has an invalid enemy drop lot")
            lot_id = lot.get("id")
            slots = lot.get("slots")
            if (not isinstance(lot_id, int) or lot_id <= 0
                    or lot_id in seen_lot_ids
                    or not isinstance(slots, list) or not 1 <= len(slots) <= 8):
                raise ValidationError("AP request has an invalid enemy drop lot")
            seen_lot_ids.add(lot_id)
            seen_slots: set[int] = set()
            for slot in slots:
                if not isinstance(slot, dict):
                    raise ValidationError("AP request has an invalid enemy drop slot")
                index = slot.get("slot")
                category = slot.get("category")
                item_id = slot.get("item_id")
                quantity = slot.get("quantity")
                base_point = slot.get("base_point")
                if (not isinstance(index, int) or not 1 <= index <= 8
                        or index in seen_slots
                        or category not in {-1, 4, 8}
                        or not isinstance(item_id, int) or item_id < 0
                        or not isinstance(quantity, int) or quantity < 0
                        or not isinstance(base_point, int) or base_point <= 0
                        or not isinstance(slot.get("luck"), bool)
                        or (category == -1 and (item_id != 0 or quantity != 0))
                        or (category != -1 and (item_id <= 0 or quantity < 1))):
                    raise ValidationError("AP request has an invalid enemy drop slot")
                seen_slots.add(index)
    elif enemy_drop_assignments is not None or enemy_drop_mode is not None:
        raise ValidationError("AP request disables enemy drops but still supplies a plan")
    from worlds.bloodborne.insight_armor import build_insight_armor_suppression
    from worlds.bloodborne.attire import ATTIRE_CATALOG
    insight_rows = request.get("insight_armor_suppression", [])
    allowed_insight = build_insight_armor_suppression({p.item_key for p in ATTIRE_CATALOG})
    if (not isinstance(insight_rows, list)
            or any(row not in allowed_insight for row in insight_rows)
            or len({row["row_id"] for row in insight_rows}) != len(insight_rows)):
        raise ValidationError("AP request has an invalid Insight armor suppression plan")
    raw_category8_awards = request.get("category8_awards", {})
    if (not isinstance(raw_category8_awards, dict)
            or any(not isinstance(key, str) or not key.isdecimal()
                   or not isinstance(row, dict)
                   for key, row in raw_category8_awards.items())):
        raise ValidationError("AP request has an invalid category-8 award table")
    category8_awards = list(raw_category8_awards.values())
    required_award_fields = {
        "item_key", "token_goods_id", "item_lot_id", "gemgen_id", "ack_flag",
        "source_lot_id",
    }
    for row in category8_awards:
        if (set(row) != required_award_fields
                or not isinstance(row["item_key"], str)
                or any(not isinstance(row[field], int) or row[field] <= 0
                       for field in required_award_fields - {"item_key"})):
            raise ValidationError("AP request has an invalid category-8 award row")
    for field in ("token_goods_id", "item_lot_id", "ack_flag"):
        values = [row[field] for row in category8_awards]
        if len(values) != len(set(values)):
            raise ValidationError(f"category-8 award table repeats {field}")
    if any(not 12_400_900 <= row["ack_flag"] <= 12_400_999
           for row in category8_awards):
        raise ValidationError(
            "category-8 award acknowledgement flag is outside 12400900..12400999"
        )
    hemwick_gate = request.get("hemwick_gate")
    expected_hemwick_gate = {
        "enabled": True, "access_flag": 12201898,
        "cathedral_object": 2401995, "cathedral_sfx": 2403995,
        "hemwick_object": 2201999, "hemwick_sfx": 2203999,
    }
    if hemwick_gate is not None and hemwick_gate != expected_hemwick_gate:
        raise ValidationError("AP request has an unsupported Hemwick gate contract")
    if hemwick_gate is not None:
        runtime_items = request.get("runtime_items")
        access_binding = (
            runtime_items.get("12255783") if isinstance(runtime_items, dict) else None
        )
        if (not isinstance(access_binding, dict)
                or access_binding.get("normalized_item_id") != 12201898
                or access_binding.get("raw_descriptor") != 12201898
                or access_binding.get("item_category") != 255
                or access_binding.get("descriptor_evidence") != "event_flag_effect"):
            raise ValidationError(
                "AP request has no supported Hemwick Access runtime binding"
            )
    seed_name = request.get("seed_name")
    return {
        "request": request,
        "source": resolved,
        "path": resolved.path,
        "seed": str(seed_name or enemizer_seed),
        "slot": player_name,
        "runtime_build": runtime_build,
        "world_build": f"bloodborne-apworld-{world_version}",
        "enemizer_seed": enemizer_seed,
        "suppression_plan_sha256": suppression["plan_sha256"],
        "auto_upgrade": auto_upgrade,
        "auto_equip": auto_equip,
        "starting_weapons": starting_weapons if randomize_starting else None,
        "weapon_requirement_families": requirement_families if remove_requirements else None,
        "shop_gate_permutation": shop_gate_permutation if randomize_shops else None,
        "enemy_drop_assignments": (
            enemy_drop_assignments if randomize_enemy_drops else None),
        "enemy_drop_mode": enemy_drop_mode if randomize_enemy_drops else None,
        "enemy_drop_plan_format": (
            enemy_drop_plan_format if randomize_enemy_drops else None),
        "category8_awards": category8_awards,
        "hemwick_gate": hemwick_gate,
        "insight_armor_suppression": insight_rows,
        "toast_placeholders": pickup_name_plan(request.get("toast_placeholders")),
    }


def _ap_identity_lock_path(state_root: Path | str, server: str) -> Path:
    root = Path(state_root).expanduser().resolve()
    key = hashlib.sha256(server.strip().encode("utf-8")).hexdigest()
    return root / "ap-identity" / f"{key}.json"


def read_ap_identity_lock(state_root: Path | str, server: str) -> dict[str, str] | None:
    """The seed/slot last connected through ``server``, or None if unknown.

    Read-only and tolerant of a missing or corrupt lock file: an unknown
    prior identity is not a mismatch, only an absence of evidence.
    """
    path = _ap_identity_lock_path(state_root, server)
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("format") != AP_IDENTITY_LOCK_FORMAT:
        return None
    seed = value.get("seed")
    slot = value.get("slot")
    if not isinstance(seed, str) or not isinstance(slot, str) or not seed or not slot:
        return None
    return {"seed": seed, "slot": slot}


def _write_ap_identity_lock(state_root: Path | str, server: str, *, seed: str, slot: str) -> None:
    path = _ap_identity_lock_path(state_root, server)
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(
        path,
        {"format": AP_IDENTITY_LOCK_FORMAT, "server": server.strip(), "seed": seed, "slot": slot},
    )


def check_seed_slot_identity(
    state_root: Path | str,
    *,
    server: str | None,
    seed: str,
    slot: str,
    allow_mismatch: bool = False,
) -> None:
    """Refuse an AP connection that would replay another room's history.

    bb-archipelago#347: the AP server address is player-editable and easily
    left pointed at a previous room. If ``server`` was last used to connect
    delivery for a different seed or slot than the one the player just
    selected, that is exactly the setup that silently inherits the old
    room's receive ledger onto a fresh seed package -- so this refuses
    before delivery arms unless the player explicitly overrides it. A fresh
    Bloodborne save/character slot is not part of this comparison at all,
    so switching save slots alone can never resolve a real mismatch.
    """
    if server is None or not server.strip():
        return
    recorded = read_ap_identity_lock(state_root, server)
    if recorded is not None and (recorded["seed"] != seed or recorded["slot"] != slot):
        if not allow_mismatch:
            raise WorkflowError(
                "AP server/slot does not match the selected seed package -- delivery "
                "stays disarmed. Selected seed package expects "
                f"seed {seed!r} slot {slot!r}; server {server!r} was last connected "
                f"as seed {recorded['seed']!r} slot {recorded['slot']!r}. Fix the AP "
                "server field to the room for this seed package (or select the seed "
                "package for that room) -- a different Bloodborne save slot does not "
                "resolve this. If you intend to reuse this server for a different "
                "seed on purpose, enable the explicit seed/slot mismatch override."
            )
    _write_ap_identity_lock(state_root, server, seed=seed, slot=slot)


def _ap_client_server(plan: ProcessPlan) -> str | None:
    for spec in plan.processes:
        if spec.name == CLIENT_PROCESS_NAME and spec.arguments:
            return spec.arguments[0]
    return None


def _validate_suppression(
    install: GameInstall,
    binder: Path,
    manifest_path: Path,
    expected_plan_hash: str,
    *,
    allow_mismatch: bool = False,
    progress: Progress = lambda _message: None,
) -> "SuppressionValidation":
    """Check the binder against the seed and the install.

    With ``allow_mismatch`` false -- the default, and the only thing a player
    ever gets -- every refusal below is exactly the one this function has
    always raised, word for word.  With it true (bb-archipelago#183) the two
    *skew* comparisons emit a loud line each instead of raising, and the names
    of the checks that were bypassed come back for the launch record.  The
    binder-vs-manifest hash and the byte-identical-to-vanilla refusal are never
    bypassable: those mean the binder itself is wrong.
    """

    if not binder.is_file() or binder.is_symlink():
        raise ValidationError(f"suppression binder does not exist: {binder}")
    manifest = _read_object(manifest_path, "suppression build manifest")
    if manifest.get("format") != "bb-vanilla-suppression-build-v1":
        raise ValidationError("suppression build manifest has the wrong format")
    if manifest.get("output_relative_path") != "param/gameparam/gameparam.parambnd.dcx":
        raise ValidationError("suppression manifest output path is not the gameparam binder")
    bypassed: list[str] = []
    if manifest.get("plan_sha256") != expected_plan_hash:
        if not allow_mismatch:
            raise ValidationError("suppression build plan hash does not match the AP seed")
        bypassed.append(SUPPRESSION_CHECK_PLAN)
        progress(
            suppression_override_line(
                SUPPRESSION_CHECK_PLAN,
                expected_plan_hash,
                manifest.get("plan_sha256"),
                "binder plan vs the seed's suppression_plan_sha256",
            )
        )
    source_path = install.resolve_file(SUPPRESSION_PATH, include_mods=False)[1]
    source_hash = sha256_file(source_path)
    if manifest.get("source_gameparam_sha256") != source_hash:
        if not allow_mismatch:
            raise ValidationError(
                f"suppression build source hash does not match the installed game: "
                f"{source_path} hashes to {source_hash[:12]}..., but the binder was built from "
                f"{str(manifest.get('source_gameparam_sha256'))[:12]}... -- rebuild the suppression "
                "binder against the installed gameparam (build.ps1 -Package -GameRoot ...), or "
                "restore a clean 01.09 installation if the game files were modified"
            )
        bypassed.append(SUPPRESSION_CHECK_SOURCE)
        progress(
            suppression_override_line(
                SUPPRESSION_CHECK_SOURCE,
                manifest.get("source_gameparam_sha256"),
                source_hash,
                f"binder source vs the installed {source_path}",
            )
        )
    output_hash = sha256_file(binder)
    if manifest.get("output_gameparam_sha256") != output_hash:
        raise ValidationError("suppression binder hash does not match its build manifest")
    if output_hash == source_hash:
        raise ValidationError("suppression binder is byte-identical to vanilla; refusing an unsuppressed build")
    return SuppressionValidation(manifest, tuple(bypassed))


def _composes_seed_binder(request: Mapping[str, Any]) -> bool:
    """Does this seed get a freshly composed gameparam binder?

    One predicate, two call sites, because they must never disagree
    (bb-archipelago review W2). The category-8 award table is a param edit like
    any other -- the C# writer adds an ItemLot row and a Goods row per award --
    so a seed whose *only* edit is that table still composes a binder. When the
    recomposition condition counted it and the manifest condition did not, such
    a seed shipped a composed binder to the overlay while the client was handed
    the bundled build-manifest.json naming the un-composed one: the client's
    hash check failed and nothing was ever delivered, behind a success dialog.
    """

    return (
        request["starting_weapons"] is not None
        or request["weapon_requirement_families"] is not None
        or request["shop_gate_permutation"] is not None
        or request["enemy_drop_assignments"] is not None
        or bool(request["category8_awards"])
        or bool(request.get("insight_armor_suppression"))
    )


def _write_seed_suppression_manifest(
    source_manifest: Path, *, state_root: Path, cache_key: str, output_hash: str,
    weapon_edits: Mapping[str, Any],
) -> Path:
    """Publish the client witness for a suppression binder composed per seed."""
    manifest = _read_object(source_manifest, "suppression build manifest")
    manifest["output_gameparam_sha256"] = output_hash
    manifest["seed_weapon_edits"] = dict(weapon_edits)
    directory = state_root.expanduser().resolve() / "seed-manifests"
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / f"{cache_key}.json"
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def enemy_ai_sources(install: GameInstall) -> dict[str, Path]:
    """Resolve each licensed AI binder independently, honoring update precedence."""
    names = {path.name for _name, layer in install.content_backends()
             for path in (layer / AI_PREFIX).glob("*.luabnd.dcx")
             if path.name == "aicommon.luabnd.dcx" or re.fullmatch(AI_FILE_PATTERN, path.name)}
    if "aicommon.luabnd.dcx" not in names or len(names) < 2:
        raise ValidationError("Randomize Enemies requires the game's common and map AI binders")
    return {AI_PREFIX + name: install.resolve_file(AI_PREFIX + name, include_mods=False)[1]
            for name in sorted(names)}


def enemy_map_sources(install: GameInstall, selected: Path | None) -> dict[str, Path]:
    """Resolve installed maps per file, with update overrides and base fallbacks.

    Saved UI settings may point at either installed layer. Neither layer alone
    represents the complete game. Explicit external map folders stay standalone.
    """
    installed = [root / "dvdroot_ps4" / "map" / "MapStudio"
                 for _, root in install.content_backends()]
    roots = installed
    if selected is not None:
        selected = selected.expanduser().resolve()
        if not selected.is_dir():
            raise ValidationError(f"source MapStudio directory does not exist: {selected}")
        if selected not in [root.resolve() for root in installed]:
            roots = [selected]
    maps: dict[str, Path] = {}
    for root in roots:
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if path.is_file() and path.name.lower().endswith((".msb", ".msb.dcx")):
                    maps.setdefault(path.name.lower(), path)
    if not maps:
        raise ValidationError("source MapStudio directory contains no .msb/.msb.dcx files")
    return maps


def encounter_event_sources(install: GameInstall) -> dict[str, Path]:
    """Resolve complete map/common EMEVD input set with update precedence."""
    prefix = f"{DVDROOT_PREFIX}event/"
    names = {
        path.name for _name, layer in install.content_backends()
        for path in (layer / "dvdroot_ps4" / "event").glob("*.emevd.dcx")
        if path.name == "common.emevd.dcx" or re.fullmatch(r"m\d{2}_\d{2}_\d{2}_\d{2}\.emevd\.dcx", path.name)
    }
    if not names:
        raise ValidationError("reviewed boss encounters require installed map EMEVD files")
    return {prefix + name: install.resolve_file(prefix + name, include_mods=False)[1]
            for name in sorted(names)}


def encounter_sfx_sources(install: GameInstall) -> dict[str, Path]:
    """Resolve original map effect banks per file, including base-only banks."""
    prefix = f"{DVDROOT_PREFIX}sfx/"
    names = {
        path.name for _name, layer in install.content_backends()
        for path in (layer / "dvdroot_ps4" / "sfx").glob("*.ffxbnd.dcx")
        if re.fullmatch(r"frpg_sfxbnd_m\d{2}\.ffxbnd\.dcx", path.name)
    }
    return {prefix + name: install.resolve_file(prefix + name, include_mods=False)[1]
            for name in sorted(names)}


def _source_hashes(
    install: GameInstall, map_root: Path | None, *, cathedral: bool = False,
    hemwick: bool = False,
) -> dict[str, str]:
    paths = [SUPPRESSION_PATH]
    if cathedral:
        paths.extend((CATHEDRAL_EVENT_PATH, COMMON_EVENT_PATH))
    if hemwick:
        paths.append(HEMWICK_EVENT_PATH)
    hashes = install.source_hashes(paths)
    if map_root is None:
        return hashes
    if not map_root.is_dir():
        raise ValidationError(f"source MapStudio directory does not exist: {map_root}")
    map_files = sorted(path for path in map_root.iterdir() if path.is_file())
    if not map_files:
        raise ValidationError("source MapStudio directory contains no files")
    for path in map_files:
        if not path.name.lower().endswith((".msb.dcx", ".msb")):
            continue
        hashes[f"dvdroot_ps4/map/MapStudio/{path.name}"] = sha256_file(path)
    if len(hashes) == len(paths):
        raise ValidationError("source MapStudio directory contains no .msb/.msb.dcx files")
    return hashes


def _validate_category8_bridge_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate stable identities, migrating only the known legacy internal lot IDs.

    Token, ack, recipe and AP identity stay unchanged. Only the launcher's private
    lot address changes, in both the parameter writer and common event catalog.
    """
    from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

    catalog = {row.item_key: row for row in CATEGORY8_AWARDS}
    legacy_lots = {row.item_key: 98_000_000 + index
                   for index, row in enumerate(CATEGORY8_AWARDS)}
    effective = []
    fields = ('token_goods_id', 'item_lot_id', 'gemgen_id', 'ack_flag', 'source_lot_id')
    for row in rows:
        canonical = catalog.get(row['item_key'])
        if canonical is None:
            raise ValidationError(
                f"category-8 seed row {row['item_key']} is not in this launcher's bridge catalog; "
                "use a matching world/launcher version before launching"
            )
        for name in fields:
            expected = getattr(canonical, name)
            if row[name] != expected:
                if name == 'item_lot_id' and row[name] == legacy_lots[row['item_key']]:
                    continue
                raise ValidationError(
                    f"category-8 seed/bridge mismatch for {row['item_key']}: "
                    f"seed {name}={row[name]}, bundled bridge expects {expected}. "
                    "This seed needs a compatible migration or a new seed generated with "
                    "the matching world. Do not repair an existing save by reissuing "
                    "the held token or editing the ledger."
                )
        effective.append({**row, 'item_lot_id': canonical.item_lot_id})
    return effective


def validate_selected_build(identity: Mapping[str, Any], request: Mapping[str, Any],
                            plan: ProcessPlan, settings: LauncherSettings):
    """Both activation modes enforce the same selected seed, options and runtime."""
    active_options = identity.get("options")
    if not isinstance(active_options, dict):
        raise ValidationError("active cached build has no options identity")
    active_canary = active_options.get("pickup_name_canary")
    selected_names = pickup_name_plan(
        request["request"].get("toast_placeholders"), canary_location=active_canary)
    request_options = {
        "starting_weapons": request["starting_weapons"],
        "weapon_requirement_families": request["weapon_requirement_families"],
        "shop_gate_permutation": request["shop_gate_permutation"],
        "enemy_drop_assignments": request["enemy_drop_assignments"],
        "enemy_drop_plan_format": request["enemy_drop_plan_format"],
        "category8_awards": request["category8_awards"],
        "toast_placeholders": selected_names,
    }
    expected_fields = {
        "seed": request["seed"],
        "slot": request["slot"],
        "world_build": request["world_build"],
        "runtime_build": request["runtime_build"],
        "shad_build": plan.shad_build,
        "suppression_plan_sha256": request["suppression_plan_sha256"],
        "suppression_binder_sha256": sha256_file(settings.suppression_binder.expanduser().resolve()),
    }
    mismatched = [name for name, value in expected_fields.items() if identity.get(name) != value]
    mismatched.extend(
        f"options.{name}"
        for name, value in request_options.items()
        if active_options.get(name) != value
    )
    if mismatched:
        raise ValidationError(
            "active overlay does not match the selected seed/options/runtime: "
            + ", ".join(mismatched)
        )
    return selected_names


class LauncherWorkflow:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        toolchain: EnemizerToolchain | None = None,
        process_launcher: Callable[[Sequence[ProcessSpec]], list[Any]] = launch_processes,
        process_running: Callable[[str], bool] = process_is_running_by_name,
        process_watcher: Callable[..., EarlyExit | None] = wait_for_early_exit,
        shad_processes: Callable[[], Sequence[RunningProcess]] = running_shad_processes,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.toolchain = toolchain or EnemizerToolchain(self.repo_root)
        self.process_launcher = process_launcher
        # Injectable so the early-exit report is testable without real timing.
        self.process_watcher = process_watcher
        # Injectable so the stray-Cheat-Engine refusal is testable off Windows.
        self.process_running = process_running
        self.shad_processes = shad_processes

    def connect_to_running(
        self,
        settings: LauncherSettings,
        *,
        allow_suppression_mismatch: bool = False,
        allow_seed_mismatch: bool = False,
        research_captures: bool = False,
        player_name: str = "",
        progress: Progress = lambda _message: None,
    ) -> WorkflowResult:
        """Start only the native AP client for an already-running shadPS4.

        This mode is deliberately limited to an overlay previously activated
        by this launcher.  It neither builds nor activates content, and it does
        not implement the separate BBLauncher/external-overlay mode (#192).
        """

        if settings.integration_mode == "bblauncher":
            raise ValidationError("Use BBLauncher Connect with the selected export receipt")
        progress("Validating the active seed and running shadPS4...")
        install = GameInstall.from_root(settings.game_root)
        request = _request_identity(
            settings.ap_request,
            player_name=player_name,
            state_root=settings.state_root,
        )
        request["category8_awards"] = _validate_category8_bridge_rows(
            request["category8_awards"]
        )
        plan = load_process_plan(settings.process_plan)
        refuse_stale_plan(plan)
        if plan.runtime_build != request["runtime_build"]:
            raise ValidationError(
                f"AP seed requires runtime {request['runtime_build']}, "
                f"process plan supplies {plan.runtime_build}"
            )
        shad_specs = tuple(spec for spec in plan.processes if spec.name == SHAD_PROCESS_NAME)
        client_specs = tuple(spec for spec in plan.processes if spec.name == CLIENT_PROCESS_NAME)
        if len(shad_specs) != 1 or len(client_specs) != 1:
            raise ValidationError("connect requires exactly one shadPS4 and one AP client process")
        shad_spec, client_spec = shad_specs[0], client_specs[0]
        validate_processes((shad_spec, client_spec))
        require_no_stray_cheat_engine(plan.processes, self.process_running)
        running = tuple(self.shad_processes())
        if not running:
            raise ValidationError("connect requires shadPS4 to already be running")
        if len(running) != 1:
            raise ValidationError(
                f"connect found {len(running)} shadPS4 processes; close all but the selected instance"
            )
        target = running[0]
        if target.executable is None or target.arguments is None:
            raise ValidationError(
                "could not verify the running shadPS4 executable and game path; run the launcher "
                "at the same privilege level as shadPS4"
            )
        if target.executable.resolve() != shad_spec.executable.resolve():
            raise ValidationError(
                f"running shadPS4 executable is {target.executable}, expected {shad_spec.executable}"
            )
        running_game = _shad_game_argument(target.arguments)
        if running_game is None or running_game.resolve() != install.base.resolve():
            raise ValidationError(
                f"running shadPS4 game is {running_game or 'unknown'}, expected {install.base}"
            )
        if self.process_running(client_spec.executable.name):
            raise ValidationError("the AP client is already running")
        server = _ap_client_server(plan)
        if (server is None or not server.strip() or server.startswith("-")
                or "{" in server or "}" in server):
            raise ValidationError("AP client process has no valid server address")

        binder = settings.suppression_binder.expanduser().resolve()
        suppression = _validate_suppression(
            install,
            binder,
            settings.suppression_manifest.expanduser().resolve(),
            request["suppression_plan_sha256"],
            allow_mismatch=allow_suppression_mismatch,
            progress=progress,
        )
        # Launch time never heals: this check guards what shadPS4 is about to
        # load.  It only says which button rebuilds the overlay
        # (bb-archipelago#408).
        try:
            owner = _load_owner(install.mods)
        except LauncherError as exc:
            raise type(exc)(f"{exc}{REBUILD_OVERLAY_HINT}") from exc
        cache_key = str(owner["cache_key"])
        build = SeedCache(settings.cache_root).verify(
            SeedCache(settings.cache_root).path_for(cache_key), expected_key=cache_key
        )
        if owner.get("build_manifest_sha256") != sha256_file(build.path / SEED_MANIFEST_NAME):
            raise ValidationError("active overlay does not match its cached build manifest")
        if owner.get("identity") != build.manifest.get("identity"):
            raise ValidationError("active overlay identity does not match its cached build")

        identity = build.manifest["identity"]
        selected_names = validate_selected_build(identity, request, plan, settings)
        validation = owner.get("suppression_validation")
        active_bypasses = (
            tuple(validation.get("bypassed", ())) if isinstance(validation, dict) else ()
        )
        if active_bypasses != suppression.bypassed:
            raise ValidationError("active overlay suppression override does not match this launch")

        check_seed_slot_identity(
            settings.state_root or default_state_root(),
            server=server, seed=request["seed"], slot=request["slot"],
            allow_mismatch=allow_seed_mismatch,
        )
        client_manifest = settings.suppression_manifest.expanduser().resolve()
        if _composes_seed_binder(request) or selected_names is not None:
            client_manifest = (
                (settings.state_root or default_state_root()).expanduser().resolve()
                / "seed-manifests" / f"{cache_key}.json"
            )
        paths = write_client_runtime_config(
            settings.state_root or default_state_root(),
            seed=request["seed"], slot=request["slot"], install=install, owner=owner,
            suppression_manifest=client_manifest,
            shad_log=settings.shad_log or default_shad_log(),
            auto_upgrade=request["auto_upgrade"], auto_equip=request["auto_equip"],
            research_captures=research_captures,
        )
        resolved = resolve_process_plan(
            ProcessPlan(plan.shad_build, plan.runtime_build, (client_spec,)),
            paths,
            game_path=install.base,
        )
        # Recheck immediately before spawn; the client owns its normal attach
        # retry while shadPS4 finishes becoming ready.
        late = tuple(self.shad_processes())
        if len(late) != 1 or late[0] != target:
            raise ValidationError("shadPS4 stopped before the AP client could start")
        if self.process_running(client_spec.executable.name):
            raise ValidationError("the AP client is already running")
        require_no_stray_cheat_engine(plan.processes, self.process_running)
        progress("Starting the AP client and attaching to the running shadPS4...")
        started = self.process_launcher(resolved.processes)
        early_exit = self.process_watcher(started, resolved.processes)
        return WorkflowResult(
            cache_key=cache_key, build_path=build.path, reused=True,
            enemizer_enabled=bool(build.manifest.get("enemizer", {}).get("enabled")),
            enemizer_swaps=int(build.manifest.get("enemizer", {}).get("file_count", 0)),
            process_ids=tuple(getattr(process, "pid", None) for process in started),
            client_config=paths.config, ledger=paths.ledger,
            client_log=paths.client_log, shad_process_log=None,
            early_exit=early_exit, grants_bridge=False,
        )

    def prepare_seed(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        *,
        force_rebuild: bool = False,
        allow_suppression_mismatch: bool = False,
        pickup_name_canary: str | None = None,
        pickup_name_language: str | None = None,
        player_name: str = "",
        progress: Progress = lambda _message: None,
    ) -> PreparedSeed:
        progress("Validating CUSA03173 01.09 and launch components...")
        if pickup_name_language not in (None, "engus", "enggb"):
            raise ValidationError("pickup-name language must be engus or enggb")
        install = GameInstall.from_root(settings.game_root)
        request = _request_identity(
            settings.ap_request,
            player_name=player_name,
            state_root=settings.state_root,
        )
        if pickup_name_canary is not None:
            request["toast_placeholders"] = pickup_name_plan(
                request["request"].get("toast_placeholders"), canary_location=pickup_name_canary)
            progress(f"Pickup-name playtest: {len(request['toast_placeholders']['entries'])} named pickups enabled.")
        effective_awards = _validate_category8_bridge_rows(request['category8_awards'])
        migrated_awards = effective_awards != request['category8_awards']
        request['category8_awards'] = effective_awards
        if migrated_awards:
            progress("Migrating legacy category-8 reward lots; token and acknowledgement identities are preserved.")
        if options.boss_pool not in (None, "reviewed"):
            raise ValidationError("the only available experimental boss pool is reviewed")
        if options.boss_pool is not None and not options.enabled:
            raise ValidationError("reviewed boss encounters require Randomize Enemies")
        if options.boss_pool is not None and options.boss_canary:
            raise ValidationError("reviewed boss encounters cannot be combined with the legacy boss canary")
        plan = load_process_plan(settings.process_plan)
        validate_processes(plan.processes)
        # Before the overlay is touched: a stale bare-game-ID plan (#177) would
        # cost the player a full build only to die inside shadPS4.
        refuse_stale_plan(plan)
        if plan.runtime_build != request["runtime_build"]:
            raise ValidationError(
                f"AP seed requires runtime {request['runtime_build']}, process plan supplies {plan.runtime_build}"
            )
        binder = settings.suppression_binder.expanduser().resolve()
        # Operator override (bb-archipelago#183): off by default, and when on
        # it emits one loud line per bypassed check through this same progress
        # sink, so the launch log carries what was waved past.
        suppression = _validate_suppression(
            install,
            binder,
            settings.suppression_manifest.expanduser().resolve(),
            request["suppression_plan_sha256"],
            allow_mismatch=allow_suppression_mismatch,
            progress=progress,
        )

        enemy_seed = options.seed.strip() if options.seed else request["enemizer_seed"]
        map_sources = enemy_map_sources(install, settings.map_studio_source) if options.enabled else {}
        map_root = next(iter(map_sources.values())).parent if map_sources else None
        sources = _source_hashes(
            install, None, cathedral=True,
            hemwick=request["hemwick_gate"] is not None,
        )
        sources.update({f"dvdroot_ps4/map/MapStudio/{name}": sha256_file(path)
                        for name, path in map_sources.items()})
        names_paths: list[str] = []
        if request["toast_placeholders"] is not None:
            names_paths = ([f"dvdroot_ps4/msg/{pickup_name_language}/item.msgbnd.dcx"]
                           if pickup_name_language else sorted(
                               path for path in ITEM_NAMES_PATHS
                               if any((root / path).is_file() for _, root in install.content_backends())))
            if not names_paths:
                raise ValidationError("pickup names require an installed engus or enggb item.msgbnd.dcx")
            sources.update(install.source_hashes([*names_paths, PARAMDEF_PATH]))
        boss_darkscript: Path | None = None
        if options.enabled:
            sources.update({relative: sha256_file(path) for relative, path in enemy_ai_sources(install).items()})
            sources.update(install.source_hashes([PARAMDEF_PATH]))
            if options.boss_canary:
                sources.update(install.source_hashes([BOSS_EVENT_PATH]))
            if options.boss_pool:
                # DarkScript is downloaded from its official release only for
                # this explicit experimental path; the helper pins both the
                # archive and unpacked compiler before returning it.
                from .boss_compiler import ensure_boss_compiler
                boss_darkscript = ensure_boss_compiler(
                    settings.state_root or default_state_root(), progress
                )
                sources.update({relative: sha256_file(path)
                                for relative, path in encounter_event_sources(install).items()})
                sources.update({relative: sha256_file(path)
                                for relative, path in encounter_sfx_sources(install).items()})
                identity_inputs = getattr(self.toolchain, "boss_encounter_identity_inputs", None)
                if not callable(identity_inputs):
                    raise ValidationError("reviewed boss toolchain cannot report its pinned build inputs")
                sources.update({label: sha256_file(source)
                                for label, source in identity_inputs(settings.enemy_inventory).items()})
                sources["launcher-tools/DarkScript3.exe"] = sha256_file(boss_darkscript)
        expanded_enemy_release = bool(options.enabled and (
            options.release_contracts or options.release_spawns or options.release_chara))
        wakeup_source_event: Path | None = None
        if expanded_enemy_release and not (options.boss_canary or options.boss_pool):
            try:
                wakeup_source_event = install.resolve_file(
                    BOSS_EVENT_PATH, include_mods=False)[1]
            except ValidationError:
                wakeup_source_event = None
            if wakeup_source_event is not None:
                sources[BOSS_EVENT_PATH] = sha256_file(wakeup_source_event)
        identity = SeedIdentity(
            seed=request["seed"],
            slot=request["slot"],
            world_build=request["world_build"],
            runtime_build=request["runtime_build"],
            shad_build=plan.shad_build,
            source_hashes=sources,
            options={
                "enemy_randomizer": options.enabled,
                "enemy_ai_version": 3 if options.enabled else None,
                "allow_tier_mixing": options.allow_tier_mixing,
                "preserve_locomotion": options.preserve_locomotion,
                "release_tranches": sorted(
                    name for name, enabled in
                    (("contracts", options.release_contracts),
                     ("spawns", options.release_spawns),
                     ("chara", options.release_chara))
                    if enabled) + (["wakeup"] if expanded_enemy_release else [])
                    if options.enabled else [],
                "wakeup_fallback_version": 1 if expanded_enemy_release else None,
                "normalize_scaling": bool(options.enabled and (options.normalize_scaling or options.boss_canary or options.boss_pool)),
                "boss_canary": bool(options.enabled and options.boss_canary),
                "boss_pool": options.boss_pool if options.enabled else None,
                "boss_encounters": bool(options.enabled and options.boss_pool),
                "experimental_enemy_version": 1 if options.enabled and (options.normalize_scaling or options.boss_canary or options.boss_pool) else None,
                "starting_weapons": request["starting_weapons"],
                "weapon_requirement_families": request["weapon_requirement_families"],
                "shop_gate_permutation": request["shop_gate_permutation"],
                "enemy_drop_assignments": request["enemy_drop_assignments"],
                "enemy_drop_plan_format": request["enemy_drop_plan_format"],
                "category8_awards": request["category8_awards"],
                "hemwick_gate": request["hemwick_gate"],
                "insight_armor_suppression": request.get("insight_armor_suppression", []),
                "toast_placeholders": request["toast_placeholders"],
                "pickup_name_canary": pickup_name_canary,
                "item_names_paths": names_paths,
            },
            enemizer_seed=enemy_seed if options.enabled else None,
            suppression_plan_sha256=request["suppression_plan_sha256"],
            suppression_binder_sha256=sha256_file(binder),
        )
        cache = SeedCache(settings.cache_root)
        existing = cache.path_for(identity.cache_key)
        if force_rebuild and existing.exists():
            # Rebuild Seed evicts only the exact hash-addressed directory for
            # this identity: it must sit directly beneath the cache root and
            # be named by the key, the same guard shape as temp-build cleanup.
            resolved_existing = existing.resolve()
            if (
                resolved_existing.parent != cache.root
                or resolved_existing.name != identity.cache_key
            ):
                raise WorkflowError(f"refusing to evict unexpected cache path: {resolved_existing}")
            progress("Rebuilding: evicting the verified cache for this seed...")
            shutil.rmtree(resolved_existing)
        enemizer: EnemizerBuild | None = None
        temporary: Path | None = None
        if existing.exists():
            progress("Reusing verified seed cache...")
            build = cache.verify(existing, expected_key=identity.cache_key)
            reused = True
        else:
            map_output = None
            composed_binder = binder
            names_output = None
            cathedral_output = None
            common_output = None
            hemwick_output = None
            script_output = None
            enemy_event_output: Path | None = None
            enemy_event_report: Mapping[str, Any] | None = None
            boss_output = None
            boss_report = None
            scaling_report = None
            ai_report = None
            boss_encounter_overlay = None
            completed = False
            try:
                if (options.enabled or request["starting_weapons"] is not None
                        or request["weapon_requirement_families"] is not None
                        or request["shop_gate_permutation"] is not None
                        or request["enemy_drop_assignments"] is not None):
                    settings.cache_root.mkdir(parents=True, exist_ok=True)
                    temporary = Path(tempfile.mkdtemp(prefix=".seed-build-", dir=settings.cache_root))
                if temporary is None:
                    settings.cache_root.mkdir(parents=True, exist_ok=True)
                    temporary = Path(tempfile.mkdtemp(prefix=".seed-build-", dir=settings.cache_root))
                cathedral_output = temporary / CATHEDRAL_EVENT_PATH
                cathedral_manifest = temporary / "cathedral-event-manifest.json"
                source_event = install.resolve_file(
                    CATHEDRAL_EVENT_PATH, include_mods=False
                )[1]
                self.toolchain.write_cathedral_event(
                    source=source_event, output=cathedral_output,
                    manifest=cathedral_manifest,
                    soulsformats_next=settings.soulsformats_next, progress=progress,
                    access_flag=(request["hemwick_gate"] or {}).get("access_flag"),
                )
                if request["hemwick_gate"] is not None:
                    hemwick_output = temporary / HEMWICK_EVENT_PATH
                    hemwick_manifest = temporary / "hemwick-event-manifest.json"
                    source_hemwick = install.resolve_file(
                        HEMWICK_EVENT_PATH, include_mods=False
                    )[1]
                    self.toolchain.write_hemwick_event(
                        source=source_hemwick, output=hemwick_output,
                        manifest=hemwick_manifest,
                        access_flag=request["hemwick_gate"]["access_flag"],
                        soulsformats_next=settings.soulsformats_next, progress=progress,
                    )
                # The bridge carries the complete reviewed category-8 table, not
                # only this seed's rows, exactly as the compiled overlay did:
                # an initializer for an unshuffled row is inert because its
                # token is never granted.
                from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
                common_output = temporary / COMMON_EVENT_PATH
                common_manifest = temporary / "common-event-manifest.json"
                common_rows = temporary / "category8-award-rows.json"
                common_rows.write_text(json.dumps({
                    "category8_awards": [row.__dict__ for row in CATEGORY8_AWARDS],
                    "toast_placeholders": (
                        request["toast_placeholders"]["entries"]
                        if request["toast_placeholders"] is not None else []
                    ),
                }, indent=2) + "\n", encoding="utf-8")
                source_common = install.resolve_file(COMMON_EVENT_PATH, include_mods=False)[1]
                self.toolchain.write_common_event(
                    request_path=common_rows, source=source_common,
                    output=common_output, manifest=common_manifest,
                    soulsformats_next=settings.soulsformats_next, progress=progress,
                )
                if _composes_seed_binder(request):
                    assert temporary is not None
                    composed_binder = temporary / "gameparam.parambnd.dcx"
                    paramdef = install.resolve_file(PARAMDEF_PATH, include_mods=False)[1]
                    parameter_request = request['path']
                    if migrated_awards:
                        parameter_request = temporary / 'compatible-seed-params.json'
                        parameter_request.write_text(json.dumps({
                            **request['request'], 'category8_awards': effective_awards,
                        }, indent=2) + '\n', encoding='utf-8')
                    self.toolchain.write_seed_weapons(
                        request_path=parameter_request, input_binder=binder, paramdef=paramdef,
                        output_binder=composed_binder,
                        soulsformats_next=settings.soulsformats_next, progress=progress,
                    )
                if request["toast_placeholders"] is not None:
                    names_output = {}
                    binder_hash = None
                    # Each language starts from the same composed parameters;
                    # cloning twice into the previous output would collide.
                    for index, names_path in enumerate(names_paths):
                        named_binder = temporary / f"gameparam.named-{index}.parambnd.dcx"
                        names_output[names_path] = temporary / names_path
                        self.toolchain.write_pickup_names(
                            plan=request["toast_placeholders"], input_binder=composed_binder,
                            paramdef=install.resolve_file(PARAMDEF_PATH, include_mods=False)[1],
                            input_names=install.resolve_file(names_path, include_mods=False)[1],
                            output_binder=named_binder, output_names=names_output[names_path],
                            soulsformats_next=settings.soulsformats_next, progress=progress,
                            canary=pickup_name_canary is not None,
                        )
                        current_hash = sha256_file(named_binder)
                        if binder_hash is not None and binder_hash != current_hash:
                            raise ValidationError("pickup-name language writers produced different parameter binders")
                        binder_hash = current_hash
                    composed_binder = named_binder
                if options.enabled:
                    if map_root is None:
                        raise ValidationError(
                            "Randomize Enemies could not find MapStudio in the game; select it explicitly"
                        )
                    if not getattr(self.toolchain, "is_bundled", False):
                        for path, label in (
                            (settings.enemy_inventory, "enemy inventory"),
                            (settings.soulsformats_next, "SoulsFormatsNEXT"),
                        ):
                            if path is None:
                                raise ValidationError(f"Randomize Enemies requires {label}")
                    assert temporary is not None
                    if len({path.parent for path in map_sources.values()}) > 1:
                        map_root = temporary / "map-input"
                        map_root.mkdir()
                        for name, source in map_sources.items():
                            destination = map_root / name
                            shutil.copyfile(source, destination)
                            if sha256_file(destination) != sources[f"dvdroot_ps4/map/MapStudio/{name}"]:
                                raise ValidationError(f"enemy map source copy failed: {name}")
                    progress(f"Planning deterministic enemy swaps from {len(map_sources)} maps...")
                    build_args = dict(
                        seed=enemy_seed,
                        inventory=settings.enemy_inventory,
                        map_studio_source=map_root,
                        soulsformats_next=settings.soulsformats_next,
                        output_root=temporary,
                        allow_tier_mixing=options.allow_tier_mixing,
                        preserve_locomotion=options.preserve_locomotion,
                        release_contracts=options.release_contracts,
                        release_spawns=options.release_spawns,
                        release_chara=options.release_chara,
                        release_wakeup=not (options.boss_canary or options.boss_pool),
                        progress=progress,
                    )
                    if options.boss_pool:
                        assert boss_darkscript is not None
                        overrides = {
                            relative: event for relative, event in (
                                (CATHEDRAL_EVENT_PATH, cathedral_output),
                                (COMMON_EVENT_PATH, common_output),
                                (HEMWICK_EVENT_PATH, hemwick_output),
                            ) if event is not None
                        }
                        enemizer = self.toolchain.build_boss_encounters(
                            options=options, install=install, input_binder=composed_binder,
                            darkscript=boss_darkscript, event_overrides=overrides, **build_args,
                        )
                        overlay = enemizer.overlay
                        if overlay is None:
                            raise ValidationError("reviewed boss builder produced no overlay")
                        boss_encounter_overlay = overlay
                        # Keep the original AP event arguments.  SeedCache
                        # checks their hashes against the retained generic
                        # plan, then substitutes the receipt-pinned final
                        # event, so the output is still staged exactly once.
                    elif options.normalize_scaling or options.boss_canary:
                        enemizer = self.toolchain.build_experimental(options=options, install=install,
                            input_binder=composed_binder, **build_args)
                        overlay = enemizer.overlay
                        assert overlay is not None
                        composed_binder = overlay / SUPPRESSION_PATH
                        script_output = overlay / 'dvdroot_ps4/script'
                        ai_report = _read_object(overlay / 'dvdroot_ps4/script.json', 'enemy AI report')
                        scaling_report = _read_object(overlay / 'scaling-report.json', 'scaling report')
                        if options.boss_canary:
                            boss_output = overlay / BOSS_EVENT_PATH
                            boss_report = _read_object(overlay / 'boss-adapter-report.json', 'boss report')
                    else:
                        enemizer = self.toolchain.build(**build_args)
                        script_output = self.toolchain.write_enemy_ai(
                            manifest=enemizer.manifest, install=install, output_root=temporary,
                            soulsformats_next=settings.soulsformats_next, progress=progress,
                        )
                        ai_report = _read_object(temporary / 'script.json', 'enemy AI report')
                    if boss_encounter_overlay is None:
                        map_output = enemizer.map_studio
                    planned_wakeup = enemizer.manifest.get("wakeup_fallbacks", [])
                    if not isinstance(planned_wakeup, list):
                        raise ValidationError("enemizer plan wakeup_fallbacks must be a list")
                    if planned_wakeup:
                        if (not expanded_enemy_release or wakeup_source_event is None
                                or options.boss_canary or options.boss_pool
                                or enemizer.plan_path is None):
                            raise ValidationError(
                                "enemizer planned wakeup fallbacks without a compatible source event")
                        assert temporary is not None
                        enemy_event_output = temporary / "wakeup-fallback" / Path(BOSS_EVENT_PATH).name
                        report_path = temporary / "wakeup-fallback" / "wakeup-fallback-report.json"
                        enemy_event_report = self.toolchain.write_wakeup_fallback(
                            plan_path=enemizer.plan_path, source_event=wakeup_source_event,
                            output_event=enemy_event_output, report_path=report_path,
                            expected_fallbacks=planned_wakeup,
                            soulsformats_next=settings.soulsformats_next, progress=progress,
                        )
                progress("Composing and verifying the seed cache...")
                result = cache.build(
                    identity, composed_binder, map_output, cathedral_output, common_output,
                    hemwick_output,
                    enemizer_plan=None if enemizer is None or boss_encounter_overlay is not None else enemizer.plan_path,
                    enemizer_options=None if enemizer is None or boss_encounter_overlay is not None else {
                        "allow_tier_mixing": options.allow_tier_mixing,
                        "preserve_locomotion": options.preserve_locomotion,
                        "normalize_scaling": options.normalize_scaling or options.boss_canary,
                        "boss_canary": options.boss_canary,
                        "release_tranches": sorted(
                            name for name, enabled in
                            (("contracts", options.release_contracts),
                             ("spawns", options.release_spawns),
                             ("chara", options.release_chara))
                            if enabled),
                    },
                    enemy_scripts=script_output,
                    enemy_ai_report=ai_report, boss_event=boss_output, boss_report=boss_report,
                    scaling_report=scaling_report, boss_encounter_overlay=boss_encounter_overlay,
                    item_names=names_output,
                    enemy_events=(None if enemy_event_output is None else
                                  {BOSS_EVENT_PATH: enemy_event_output}),
                    enemy_event_report=enemy_event_report)
                build = result
                reused = result.reused
                completed = True
            finally:
                if temporary is not None and temporary.exists():
                    resolved_cache = settings.cache_root.expanduser().resolve()
                    resolved_temp = temporary.resolve()
                    if resolved_temp.parent != resolved_cache or not resolved_temp.name.startswith(".seed-build-"):
                        raise WorkflowError(f"refusing to clean unexpected build path: {resolved_temp}")
                    if completed:
                        shutil.rmtree(resolved_temp)
                    else:
                        progress(f"Preserved failed enemizer build diagnostics at {resolved_temp}")
        return PreparedSeed(install, request, plan, identity, suppression, build, reused, enemizer)

    def randomize_and_launch(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        *,
        force_rebuild: bool = False,
        allow_suppression_mismatch: bool = False,
        allow_seed_mismatch: bool = False,
        research_captures: bool = False,
        pickup_name_canary: str | None = None,
        pickup_name_language: str | None = None,
        player_name: str = "",
        progress: Progress = lambda _message: None,
        process_is_running: Callable[[], bool] | None = None,
    ) -> WorkflowResult:
        if settings.integration_mode == "bblauncher":
            raise ValidationError("BBLauncher owns activation and deactivation in this mode. Use BBLauncher to change mods; standalone activation/restore is unavailable.")
        # Validate the seed's bridge contract before reading a launch plan,
        # touching the cache, inspecting processes, or activating anything.
        # Besides keeping mismatch refusal side-effect free, this preserves the
        # category-8 migration that prepare_seed applies to the same request.
        request = _request_identity(settings.ap_request, player_name=player_name, state_root=settings.state_root)
        request["category8_awards"] = _validate_category8_bridge_rows(
            request["category8_awards"]
        )
        plan = load_process_plan(settings.process_plan)
        require_no_stray_cheat_engine(plan.processes, self.process_running)
        check_seed_slot_identity(
            settings.state_root or default_state_root(), server=_ap_client_server(plan),
            seed=request["seed"], slot=request["slot"], allow_mismatch=allow_seed_mismatch,
        )
        prepared = self.prepare_seed(
            settings, options, force_rebuild=force_rebuild,
            allow_suppression_mismatch=allow_suppression_mismatch,
            pickup_name_canary=pickup_name_canary, pickup_name_language=pickup_name_language,
            player_name=player_name, progress=progress,
        )
        if (prepared.plan != plan
                or prepared.request.get("request") != request.get("request")
                or prepared.request.get("seed") != request.get("seed")
                or prepared.request.get("slot") != request.get("slot")):
            raise ValidationError(
                "AP request or process plan changed during seed preparation; retry the launch"
            )
        install, request, plan = prepared.install, prepared.request, prepared.plan
        identity, suppression, build = prepared.identity, prepared.suppression, prepared.build
        reused, enemizer = prepared.reused, prepared.enemizer
        progress("Activating verified shadPS4 overlay...")
        owner = activate_build(
            install,
            build.path,
            process_is_running=process_is_running,
            suppression_override=suppression.bypassed,
            identity=identity,
        )
        if owner["suppression"]["sha256"] != build.manifest["suppression"]["sha256"]:
            raise ValidationError("activated suppression witness does not match the seed build")
        cathedral = build.manifest.get("cathedral_event")
        if not isinstance(cathedral, dict) or cathedral.get("path") != CATHEDRAL_EVENT_PATH:
            raise ValidationError(
                "activated seed is missing the required Cathedral event overlay"
            )
        common = build.manifest.get("common_event")
        if not isinstance(common, dict) or common.get("path") != COMMON_EVENT_PATH:
            raise ValidationError("activated seed is missing the category-8 common event overlay")
        for note in owner.get("healed_from", ()):
            progress(overlay_heal_line(note))
        for line in dead_path_warnings(owner):
            progress(line)
        progress("Writing the native client runtime configuration...")
        client_manifest = settings.suppression_manifest.expanduser().resolve()
        # Include either writer: the client must hash the final composed binder.
        if _composes_seed_binder(request) or request["toast_placeholders"] is not None:
            client_manifest = _write_seed_suppression_manifest(
                client_manifest,
                state_root=settings.state_root or default_state_root(),
                cache_key=build.cache_key,
                output_hash=build.manifest["suppression"]["sha256"],
                weapon_edits={
                    "choices": request["starting_weapons"],
                    "requirement_families": request["weapon_requirement_families"],
                    "shop_gate_permutation": request["shop_gate_permutation"],
                    "enemy_drop_assignments": request["enemy_drop_assignments"],
                    "insight_armor_suppression": request.get("insight_armor_suppression", []),
                    "toast_placeholders": request["toast_placeholders"],
                },
            )
        paths = write_client_runtime_config(
            settings.state_root or default_state_root(),
            seed=request["seed"],
            slot=request["slot"],
            install=install,
            owner=owner,
            suppression_manifest=client_manifest,
            shad_log=settings.shad_log or default_shad_log(),
            auto_upgrade=request["auto_upgrade"],
            auto_equip=request["auto_equip"],
            research_captures=research_captures,
        )
        progress("Starting shadPS4, bridge, and AP client...")
        resolved = resolve_process_plan(plan, paths, game_path=install.base)
        # Re-checked at the spawn point: Cheat Engine may have been opened
        # while the seed was building.
        require_no_stray_cheat_engine(resolved.processes, self.process_running)
        started = self.process_launcher(resolved.processes)
        progress("Watching the launched components for an early exit...")
        early_exit = self.process_watcher(started, resolved.processes)
        if early_exit is None:
            progress("Randomized Bloodborne launch started.")
        else:
            progress(
                f"{early_exit.name} exited immediately; see "
                f"{early_exit.log_path or paths.session}"
            )
        swaps = 0
        if enemizer is not None:
            swaps = len(enemizer.manifest["swaps"])
        elif options.enabled:
            cached_enemizer = build.manifest.get("enemizer", {})
            cached_plan = cached_enemizer.get("plan") or {}
            swaps = int(cached_plan.get("swap_count", cached_enemizer.get("file_count", 0)))
        return WorkflowResult(
            cache_key=build.cache_key,
            build_path=build.path,
            reused=reused,
            enemizer_enabled=options.enabled,
            enemizer_swaps=swaps,
            process_ids=tuple(getattr(process, "pid", None) for process in started),
            client_config=paths.config,
            ledger=paths.ledger,
            client_log=paths.client_log,
            shad_process_log=paths.shad_process_log,
            early_exit=early_exit,
            grants_bridge=any(spec.name == "CE bridge" for spec in resolved.processes),
        )

    def launch_vanilla(
        self,
        settings: LauncherSettings,
        *,
        progress: Progress = lambda _message: None,
        process_is_running: Callable[[], bool] | None = None,
    ) -> tuple[int | None, ...]:
        """Bypass the overlay and launch the plan without any AP component.

        Deactivates only a verified launcher-owned overlay (cached builds stay
        available) and launches the plan with every AP component dropped: an
        entry whose arguments name a client placeholder is a component of the
        randomized session, and a vanilla launch has no client runtime
        configuration to give it.

        Dropping rather than refusing (bb-archipelago review W3): every plan a
        packaged player has is a generated one, and `generate_process_plan`
        always pins the AP client with `{runtime_config}`, `{ledger}` and
        `{client_log}`, so failing closed on those placeholders made the
        button refuse on every healthy setup, leaving the overlay active and
        the game unlaunched.
        """

        if settings.integration_mode == "bblauncher":
            raise ValidationError("BBLauncher owns activation and deactivation in this mode. Use BBLauncher to change mods; standalone activation/restore is unavailable.")

        progress("Validating CUSA03173 01.09 and launch components...")
        install = GameInstall.from_root(settings.game_root)
        plan = load_process_plan(settings.process_plan)
        validate_processes(plan.processes)
        vanilla = _without_client_processes(plan)
        if not vanilla.processes:
            raise ValidationError(
                "this launch plan has no non-Archipelago process to launch vanilla; "
                "regenerate it (Generate Launch Plan) so it pins shadPS4"
            )
        for spec in plan.processes:
            if spec not in vanilla.processes:
                progress(f"Vanilla launch: leaving out the Archipelago component {spec.name}")
        # Resolve before any mutation: a plan that still fails to resolve must
        # do so with the overlay untouched.
        resolved = resolve_process_plan(vanilla, None, game_path=install.base)
        require_no_stray_cheat_engine(resolved.processes, self.process_running)
        progress("Moving the launcher-owned overlay out of the search path...")
        disabled = deactivate_overlay(install, process_is_running=process_is_running)
        if disabled is None:
            progress("No launcher-owned overlay was active; launching vanilla.")
        else:
            progress(f"Overlay preserved at {disabled}")
        progress("Starting configured processes...")
        started = self.process_launcher(resolved.processes)
        progress("Vanilla Bloodborne launch started.")
        return tuple(getattr(process, "pid", None) for process in started)

    def restore_previous(
        self,
        settings: LauncherSettings,
        *,
        progress: Progress = lambda _message: None,
        process_is_running: Callable[[], bool] | None = None,
    ) -> str:
        """Reactivate the previous cached seed through a full transaction."""

        if settings.integration_mode == "bblauncher":
            raise ValidationError("BBLauncher owns activation and deactivation in this mode. Use BBLauncher to change mods; standalone activation/restore is unavailable.")

        progress("Validating CUSA03173 01.09...")
        install = GameInstall.from_root(settings.game_root)
        owner = restore_previous_build(
            install,
            SeedCache(settings.cache_root),
            process_is_running=process_is_running,
        )
        key = str(owner["cache_key"])
        progress(f"Previous seed {key[:12]} is active again.")
        return key
