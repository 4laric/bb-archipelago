"""Player-facing build orchestration above the transactional launcher core."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .core import (
    SUPPRESSION_PATH,
    GameInstall,
    LauncherError,
    ProcessSpec,
    SeedCache,
    SeedIdentity,
    ValidationError,
    activate_build,
    deactivate_overlay,
    launch_processes,
    process_is_running_by_name,
    require_no_stray_cheat_engine,
    restore_previous_build,
    sha256_file,
    validate_processes,
)
from .client_config import (
    ClientRuntimePaths,
    default_shad_log,
    default_state_root,
    substitute_plan_arguments,
    write_client_runtime_config,
)
from .resources import application_root


SETTINGS_FORMAT = "bb-launcher-ui-settings-v1"
PROCESS_PLAN_FORMAT = "bb-launcher-process-plan-v1"
REQUEST_FORMAT = "bb-enemizer-request-v1"
PLAN_FORMAT = "bb-enemizer-plan-v2"
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
        }


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


def resolve_process_plan(plan: ProcessPlan, paths: ClientRuntimePaths | None) -> ProcessPlan:
    """Return the plan with launch-time placeholders substituted throughout."""

    return ProcessPlan(
        shad_build=plan.shad_build,
        runtime_build=plan.runtime_build,
        processes=tuple(
            ProcessSpec(
                name=spec.name,
                executable=spec.executable,
                arguments=substitute_plan_arguments(spec.arguments, paths),
                working_directory=spec.working_directory,
                expected_sha256=spec.expected_sha256,
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
        return self.app_root / "tools" / "BBEnemizerPlanner.exe"

    @property
    def writer_executable(self) -> Path:
        return self.app_root / "tools" / "BBEnemizerWriter.exe"

    @property
    def miner_executable(self) -> Path:
        return self.app_root / "tools" / "MSBBMiner.exe"

    @property
    def is_bundled(self) -> bool:
        return all(
            path.is_file()
            for path in (self.planner_executable, self.writer_executable, self.miner_executable)
        )

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
        return EnemizerBuild(map_output, plan, sha256_file(plan_path))


def _request_identity(request_path: Path) -> dict[str, Any]:
    request = _read_object(request_path, "AP enemizer request")
    if request.get("format") != REQUEST_FORMAT:
        raise ValidationError(f"expected a {REQUEST_FORMAT} file")
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
    seed_name = request.get("seed_name")
    return {
        "request": request,
        "seed": str(seed_name or enemizer_seed),
        "slot": player_name,
        "runtime_build": runtime_build,
        "world_build": f"bloodborne-apworld-{world_version}",
        "enemizer_seed": enemizer_seed,
        "suppression_plan_sha256": suppression["plan_sha256"],
    }


def _validate_suppression(
    install: GameInstall,
    binder: Path,
    manifest_path: Path,
    expected_plan_hash: str,
) -> dict[str, Any]:
    if not binder.is_file() or binder.is_symlink():
        raise ValidationError(f"suppression binder does not exist: {binder}")
    manifest = _read_object(manifest_path, "suppression build manifest")
    if manifest.get("format") != "bb-vanilla-suppression-build-v1":
        raise ValidationError("suppression build manifest has the wrong format")
    if manifest.get("output_relative_path") != "param/gameparam/gameparam.parambnd.dcx":
        raise ValidationError("suppression manifest output path is not the gameparam binder")
    if manifest.get("plan_sha256") != expected_plan_hash:
        raise ValidationError("suppression build plan hash does not match the AP seed")
    source_path = install.resolve_file(SUPPRESSION_PATH, include_mods=False)[1]
    source_hash = sha256_file(source_path)
    if manifest.get("source_gameparam_sha256") != source_hash:
        raise ValidationError(
            f"suppression build source hash does not match the installed game: "
            f"{source_path} hashes to {source_hash[:12]}..., but the binder was built from "
            f"{str(manifest.get('source_gameparam_sha256'))[:12]}... -- rebuild the suppression "
            "binder against the installed gameparam (build.ps1 -Package -GameRoot ...), or "
            "restore a clean 01.09 installation if the game files were modified"
        )
    output_hash = sha256_file(binder)
    if manifest.get("output_gameparam_sha256") != output_hash:
        raise ValidationError("suppression binder hash does not match its build manifest")
    if output_hash == source_hash:
        raise ValidationError("suppression binder is byte-identical to vanilla; refusing an unsuppressed build")
    return manifest


def _source_hashes(install: GameInstall, map_root: Path | None) -> dict[str, str]:
    hashes = install.source_hashes((SUPPRESSION_PATH,))
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
    if len(hashes) == 1:
        raise ValidationError("source MapStudio directory contains no .msb/.msb.dcx files")
    return hashes


class LauncherWorkflow:
    def __init__(
        self,
        repo_root: Path | str,
        *,
        toolchain: EnemizerToolchain | None = None,
        process_launcher: Callable[[Sequence[ProcessSpec]], list[Any]] = launch_processes,
        process_running: Callable[[str], bool] = process_is_running_by_name,
    ):
        self.repo_root = Path(repo_root).expanduser().resolve()
        self.toolchain = toolchain or EnemizerToolchain(self.repo_root)
        self.process_launcher = process_launcher
        # Injectable so the stray-Cheat-Engine refusal is testable off Windows.
        self.process_running = process_running

    def randomize_and_launch(
        self,
        settings: LauncherSettings,
        options: EnemizerOptions,
        *,
        force_rebuild: bool = False,
        progress: Progress = lambda _message: None,
        process_is_running: Callable[[], bool] | None = None,
    ) -> WorkflowResult:
        progress("Validating CUSA03173 01.09 and launch components...")
        install = GameInstall.from_root(settings.game_root)
        request = _request_identity(settings.ap_request)
        plan = load_process_plan(settings.process_plan)
        validate_processes(plan.processes)
        # Before the overlay is touched: a bridge that cannot arm must not
        # cost the player a build (bb-archipelago#137).
        require_no_stray_cheat_engine(plan.processes, self.process_running)
        if plan.runtime_build != request["runtime_build"]:
            raise ValidationError(
                f"AP seed requires runtime {request['runtime_build']}, process plan supplies {plan.runtime_build}"
            )
        binder = settings.suppression_binder.expanduser().resolve()
        _validate_suppression(
            install,
            binder,
            settings.suppression_manifest.expanduser().resolve(),
            request["suppression_plan_sha256"],
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
        sources = _source_hashes(install, map_root)
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
            },
            enemizer_seed=enemy_seed if options.enabled else None,
            suppression_plan_sha256=request["suppression_plan_sha256"],
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
            completed = False
            try:
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
                    settings.cache_root.mkdir(parents=True, exist_ok=True)
                    temporary = Path(tempfile.mkdtemp(prefix=".enemizer-build-", dir=settings.cache_root))
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
                result = cache.build(identity, binder, map_output)
                build = result
                reused = result.reused
                completed = True
            finally:
                if temporary is not None and temporary.exists():
                    resolved_cache = settings.cache_root.expanduser().resolve()
                    resolved_temp = temporary.resolve()
                    if resolved_temp.parent != resolved_cache or not resolved_temp.name.startswith(".enemizer-build-"):
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
        )
        if owner["suppression"]["sha256"] != build.manifest["suppression"]["sha256"]:
            raise ValidationError("activated suppression witness does not match the seed build")
        progress("Writing the native client runtime configuration...")
        paths = write_client_runtime_config(
            settings.state_root or default_state_root(),
            seed=request["seed"],
            slot=request["slot"],
            install=install,
            owner=owner,
            suppression_manifest=settings.suppression_manifest.expanduser().resolve(),
            shad_log=settings.shad_log or default_shad_log(),
        )
        progress("Starting shadPS4, bridge, and AP client...")
        resolved = resolve_process_plan(plan, paths)
        # Re-checked at the spawn point: Cheat Engine may have been opened
        # while the seed was building.
        require_no_stray_cheat_engine(resolved.processes, self.process_running)
        started = self.process_launcher(resolved.processes)
        progress("Randomized Bloodborne launch started.")
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
        available) and launches the process plan under the vanilla rule: any
        client placeholder in the plan fails closed, because a vanilla launch
        has no client runtime configuration to substitute.
        """

        progress("Validating CUSA03173 01.09 and launch components...")
        install = GameInstall.from_root(settings.game_root)
        plan = load_process_plan(settings.process_plan)
        validate_processes(plan.processes)
        # Resolve before any mutation: a plan that still carries client
        # placeholders must fail closed with the overlay untouched.
        resolved = resolve_process_plan(plan, None)
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
