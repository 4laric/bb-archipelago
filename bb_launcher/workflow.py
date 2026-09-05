"""Player-facing build orchestration above the transactional launcher core."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .core import (
    CATHEDRAL_EVENT_PATH,
    COMMON_EVENT_PATH,
    STALE_BARE_SERIAL_REMEDY,
    SUPPRESSION_CHECK_PLAN,
    SUPPRESSION_CHECK_SOURCE,
    SUPPRESSION_OVERRIDE_KNOB,
    SUPPRESSION_PATH,
    EarlyExit,
    GameInstall,
    LauncherError,
    ProcessSpec,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    dead_path_warnings,
    deactivate_overlay,
    launch_processes,
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

        return cls(
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


@dataclass(frozen=True)
class EnemizerBuild:
    map_studio: Path
    manifest: Mapping[str, Any]
    manifest_sha256: str
    # The plan file the writer consumed; retained in the seed cache so a bad
    # swap can be named from a player's report (bb-archipelago#321).
    plan_path: Path | None = None


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

    def write_cathedral_event(
        self, *, source: Path, output: Path, manifest: Path,
        soulsformats_next: Path | None, progress: Progress,
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
        progress("Writing and verifying the Cathedral event overlay...")
        self.runner(command, self.repo_root, progress)
        if not output.is_file() or not manifest.is_file():
            raise ValidationError("event writer produced no Cathedral event overlay")

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
    if not isinstance(randomize_enemy_drops, bool):
        raise ValidationError("AP request has invalid randomize_enemy_drops")
    if randomize_enemy_drops:
        if enemy_drop_mode not in {"balanced", "dropsanity"}:
            raise ValidationError("AP request has invalid enemy drop mode")
        if not isinstance(enemy_drop_assignments, list) or not enemy_drop_assignments:
            raise ValidationError("AP request has no enemy drop assignments")
        seen_drop_fields: set[tuple[int, str]] = set()
        for assignment in enemy_drop_assignments:
            if not isinstance(assignment, dict):
                raise ValidationError("AP request has an invalid enemy drop assignment")
            npc_id = assignment.get("npc_param_id")
            field = assignment.get("drop_field")
            source_lot = assignment.get("source_lot_id")
            target_lot = assignment.get("target_lot_id")
            key = (npc_id, field)
            if (not isinstance(npc_id, int) or npc_id <= 0
                    or not isinstance(field, str) or field not in {
                        f"itemLotId_{index}" for index in range(1, 7)}
                    or not isinstance(source_lot, int) or source_lot <= 0
                    or not isinstance(target_lot, int) or target_lot <= 0
                    or source_lot == target_lot or key in seen_drop_fields):
                raise ValidationError("AP request has an invalid enemy drop assignment")
            seen_drop_fields.add(key)
    elif enemy_drop_assignments is not None or enemy_drop_mode is not None:
        raise ValidationError("AP request disables enemy drops but still supplies a plan")
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
        "category8_awards": category8_awards,
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


def _source_hashes(
    install: GameInstall, map_root: Path | None, *, cathedral: bool = False
) -> dict[str, str]:
    paths = (
        (SUPPRESSION_PATH, CATHEDRAL_EVENT_PATH, COMMON_EVENT_PATH)
        if cathedral
        else (SUPPRESSION_PATH,)
    )
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


class LauncherWorkflow:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        toolchain: EnemizerToolchain | None = None,
        process_launcher: Callable[[Sequence[ProcessSpec]], list[Any]] = launch_processes,
        process_running: Callable[[str], bool] = process_is_running_by_name,
        process_watcher: Callable[..., EarlyExit | None] = wait_for_early_exit,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.toolchain = toolchain or EnemizerToolchain(self.repo_root)
        self.process_launcher = process_launcher
        # Injectable so the early-exit report is testable without real timing.
        self.process_watcher = process_watcher
        # Injectable so the stray-Cheat-Engine refusal is testable off Windows.
        self.process_running = process_running

    def randomize_and_launch(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        *,
        force_rebuild: bool = False,
        allow_suppression_mismatch: bool = False,
        allow_seed_mismatch: bool = False,
        research_captures: bool = False,
        player_name: str = "",
        progress: Progress = lambda _message: None,
        process_is_running: Callable[[], bool] | None = None,
    ) -> WorkflowResult:
        progress("Validating CUSA03173 01.09 and launch components...")
        install = GameInstall.from_root(settings.game_root)
        request = _request_identity(
            settings.ap_request,
            player_name=player_name,
            state_root=settings.state_root,
        )
        effective_awards = _validate_category8_bridge_rows(request['category8_awards'])
        migrated_awards = effective_awards != request['category8_awards']
        request['category8_awards'] = effective_awards
        if migrated_awards:
            progress("Migrating legacy category-8 reward lots; token and acknowledgement identities are preserved.")
        plan = load_process_plan(settings.process_plan)
        validate_processes(plan.processes)
        # Before the overlay is touched: a stale bare-game-ID plan (#177) would
        # cost the player a full build only to die inside shadPS4.
        refuse_stale_plan(plan)
        # Before the overlay is touched: a bridge that cannot arm must not
        # cost the player a build (bb-archipelago#137).
        require_no_stray_cheat_engine(plan.processes, self.process_running)
        if plan.runtime_build != request["runtime_build"]:
            raise ValidationError(
                f"AP seed requires runtime {request['runtime_build']}, process plan supplies {plan.runtime_build}"
            )
        # Before the overlay is touched and no later than AP connection: a
        # stale saved server address must not silently inherit another
        # room's receive history onto this seed package (bb-archipelago#347).
        check_seed_slot_identity(
            settings.state_root or default_state_root(),
            server=_ap_client_server(plan),
            seed=request["seed"],
            slot=request["slot"],
            allow_mismatch=allow_seed_mismatch,
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
        map_root = settings.map_studio_source if options.enabled else None
        if options.enabled and map_root is None:
            relative_maps = Path("dvdroot_ps4") / "map" / "MapStudio"
            candidates = [
                candidate
                for _name, layer in install.content_backends()
                if (candidate := layer / relative_maps).is_dir()
            ]
            if candidates:
                def map_count(candidate: Path) -> int:
                    return sum(
                        path.is_file() and path.name.lower().endswith((".msb", ".msb.dcx"))
                        for path in candidate.iterdir()
                    )

                map_root = max(candidates, key=map_count)
        sources = _source_hashes(install, map_root, cathedral=True)
        identity = SeedIdentity(
            seed=request["seed"],
            slot=request["slot"],
            world_build=request["world_build"],
            runtime_build=request["runtime_build"],
            shad_build=plan.shad_build,
            source_hashes=sources,
            options={
                "enemy_randomizer": options.enabled,
                "allow_tier_mixing": options.allow_tier_mixing,
                "preserve_locomotion": options.preserve_locomotion,
                "starting_weapons": request["starting_weapons"],
                "weapon_requirement_families": request["weapon_requirement_families"],
                "shop_gate_permutation": request["shop_gate_permutation"],
                "enemy_drop_assignments": request["enemy_drop_assignments"],
                "category8_awards": request["category8_awards"],
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
            cathedral_output = None
            common_output = None
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
                    progress("Planning deterministic enemy swaps...")
                    enemizer = self.toolchain.build(
                        seed=enemy_seed,
                        inventory=settings.enemy_inventory,
                        map_studio_source=map_root,
                        soulsformats_next=settings.soulsformats_next,
                        output_root=temporary,
                        allow_tier_mixing=options.allow_tier_mixing,
                        preserve_locomotion=options.preserve_locomotion,
                        progress=progress,
                    )
                    map_output = enemizer.map_studio
                progress("Composing and verifying the seed cache...")
                result = cache.build(
                    identity, composed_binder, map_output, cathedral_output, common_output,
                    enemizer_plan=None if enemizer is None else enemizer.plan_path,
                    enemizer_options=None if enemizer is None else {
                        "allow_tier_mixing": options.allow_tier_mixing,
                        "preserve_locomotion": options.preserve_locomotion,
                    },
                )
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
        for line in dead_path_warnings(owner):
            progress(line)
        progress("Writing the native client runtime configuration...")
        client_manifest = settings.suppression_manifest.expanduser().resolve()
        # Same predicate as the recomposition above: whatever composed the
        # binder must also re-publish the witness the client hashes it against.
        if _composes_seed_binder(request):
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
            swaps = int(build.manifest.get("enemizer", {}).get("file_count", 0))
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
