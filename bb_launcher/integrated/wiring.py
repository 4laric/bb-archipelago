"""Production wiring: real prepare/verify/spawn behind the coordinator.

These functions reuse the existing seed preparation, cache, receipt,
verifier, runtime-config and native-client code.  They run against the
real game trees and BBLauncher directories, so they are validated in
live acceptance (phase 4), not in this environment.  The coordinator,
protocol, sessions, journal, locks, policy and supervisor code around
them is exercised by fixture/fault-injection tests with injected fakes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from ..client_config import _write_runtime_config, default_shad_log, session_key
from ..core import GameInstall, ValidationError


def production_process_check() -> dict[str, Any]:
    """Live shadPS4 enumeration for preflight and connection checks.

    Reports at most one process: zero running, exactly one live entry, or
    an ambiguous flag the coordinator resolves with its claimed identity.
    """

    from ..core import sha256_file
    from ..workflow import running_shad_processes

    try:
        found = running_shad_processes()
    except ValidationError:
        return {"game_running": False, "reason": "process-query-refused"}
    if not found:
        return {"game_running": False}
    records = []
    for proc in found:
        executable = str(proc.executable) if proc.executable is not None else ""
        digest = ""
        if proc.executable is not None:
            try:
                digest = sha256_file(proc.executable)
            except (OSError, ValidationError):
                digest = ""
        records.append({
            "pid": proc.pid, "executable": executable,
            "executable_sha256": digest, "creation_time": proc.creation_time,
            "alive": True,
        })
    if len(records) > 1:
        return {"game_running": True, "ambiguous": True, "processes": records,
                "pids": sorted(proc.pid for proc in found)}
    return {"game_running": True, **records[0]}


def _suppression_file(params: Mapping[str, Any], state_root: Path, kind: str) -> Path:
    """Suppression inputs ship in the fork bundle; explicit paths win."""

    direct = params.get(f"suppression_{kind}")
    if direct:
        candidate = Path(str(direct)).expanduser().resolve()
        if not candidate.is_file() or candidate.is_symlink():
            raise ValidationError(f"suppression {kind} is not a regular file: {candidate}")
        return candidate
    names = {"binder": "gameparam.parambnd.dcx", "manifest": "build-manifest.json"}
    bundle = params.get("suppression_dir")
    if bundle:
        candidate = Path(str(bundle)).expanduser().resolve() / names[kind]
        if candidate.is_file() and not candidate.is_symlink():
            return candidate
    raise ValidationError(
        f"suppression {kind} is missing: pass suppression_{kind} or a bundle "
        f"suppression_dir holding {names[kind]}"
    )


def _process_plan(params: Mapping[str, Any], state_root: Path) -> Path:
    """Reuse an explicit plan, else generate a hash-pinned one from the
    fork-reported executables and the seed request identity -- the same
    inputs the manual plan command takes, so the file is identical
    either way. Plans stay portable (placeholders resolve at spawn) and
    are keyed by every input that shapes them, so reuse is exact."""

    direct = params.get("process_plan")
    if direct:
        candidate = Path(str(direct)).expanduser().resolve()
        if not candidate.is_file() or candidate.is_symlink():
            raise ValidationError(f"process plan is not a regular file: {candidate}")
        return candidate
    import hashlib

    from ..core import canonical_json
    from ..plan import DEFAULT_SHAD_BUILD, generate_process_plan, write_process_plan
    from ..workflow import _request_identity

    for key in ("shad_executable", "ap_client", "server", "seed_path"):
        if not str(params.get(key, "")).strip():
            raise ValidationError(
                f"process plan generation requires {key} (or an explicit process_plan)"
            )
    seed_path = Path(str(params["seed_path"])).expanduser().resolve()
    request = _request_identity(seed_path, player_name=str(params.get("player_name", "")),
                                state_root=state_root)["request"]
    slot = str(params.get("player_name") or request.get("player_name", ""))
    material = {
        "shad_executable": str(Path(str(params["shad_executable"])).expanduser().resolve()),
        "ap_client": str(Path(str(params["ap_client"])).expanduser().resolve()),
        "server": str(params["server"]),
        "slot": slot,
        "runtime_build": str(request.get("runtime_build", "")),
        "shad_build": DEFAULT_SHAD_BUILD,
    }
    key = hashlib.sha256(canonical_json(material)).hexdigest()[:16]
    directory = state_root / "integrated" / "plans"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"plan-{key}.json"
    if path.is_file() and not path.is_symlink():
        return path
    document = generate_process_plan(
        shad_executable=material["shad_executable"],
        runtime_build=material["runtime_build"],
        slot=slot,
        client_executable=material["ap_client"],
        shad_build=material["shad_build"],
        server=material["server"],
    )
    return write_process_plan(path, document)


def production_prepare(params: Mapping[str, Any], op_id: str) -> Mapping[str, Any]:
    from ..external import ExternalNamespace, export_external_package
    from ..resources import application_root, resource_root
    from ..workflow import EnemizerOptions, EnemizerToolchain, LauncherSettings, LauncherWorkflow
    from .policy import fork_build_warning

    game_root = Path(str(params["game_root"])).expanduser().resolve()
    state_root = Path(str(params.get("state_root", ""))).expanduser().resolve()
    mods_root = Path(str(params["mods_root"])).expanduser().resolve()
    seed_path = Path(str(params["seed_path"])).expanduser().resolve()
    fork = params.get("fork_build") or {}
    plan_path = _process_plan(params, state_root)

    settings = LauncherSettings(
        game_root=game_root,
        cache_root=Path(str(params.get("cache_root",
                                       state_root / "cache"))).expanduser().resolve(),
        ap_request=seed_path,
        suppression_binder=_suppression_file(params, state_root, "binder"),
        suppression_manifest=_suppression_file(params, state_root, "manifest"),
        process_plan=plan_path,
        state_root=state_root,
    )
    workflow = LauncherWorkflow(
        resource_root(),
        toolchain=EnemizerToolchain(resource_root(), app_root=application_root()),
    )
    prepared = workflow.prepare_seed(
        settings, EnemizerOptions(enabled=False),
        player_name=str(params.get("player_name", "")), progress=lambda _: None,
    )
    install = GameInstall.from_root(game_root)
    from ..core import sha256_file
    from ..external import BBLauncherBuildPin

    client = next((p for p in prepared.plan.processes if p.name == "AP client"), None)
    if client is None:
        raise ValidationError("process plan has no AP client")
    pin = BBLauncherBuildPin(
        build=str(fork.get("build", "fork")),
        commit=str(fork["commit"]),
        executable_sha256=str(fork["executable_sha256"]),
    )
    export = export_external_package(
        prepared.build, identity=prepared.identity, mods_root=mods_root,
        state_root=state_root, install=install, bblauncher=pin,
        client_version="sha256:" + sha256_file(client.executable),
        suppression_manifest_sha256=sha256_file(settings.suppression_manifest),
        namespace=ExternalNamespace(
            prepared.build.cache_key,
            session_key(prepared.identity.seed, prepared.identity.slot)),
    )
    import hashlib

    from ..core import canonical_json

    receipt_payload = dict(export.receipt.as_dict())
    receipt_payload.pop("receipt_id")
    return {
        "receipt_id": export.receipt.receipt_id,
        "receipt_digest": hashlib.sha256(canonical_json(receipt_payload)).hexdigest(),
        "seed": export.receipt.identity.seed,
        "slot": export.receipt.identity.slot,
        "cache_key": export.receipt.cache_key,
        "package_name": export.receipt.package_name,
        "server": str(params.get("server", "")),
        "title": f"{export.receipt.identity.seed} ({export.receipt.identity.slot})",
        "build_warning": fork_build_warning(
            str(fork.get("commit", "")), str(fork.get("executable_sha256", ""))),
        # Persist non-secret settings alongside the opaque play handle so the
        # connect request need only carry arm/process identity. Passwords stay
        # in the backend's process memory and never enter this JSON record.
        "launch_config": {
            "game_root": str(game_root),
            "state_root": str(state_root),
            "mods_root": str(mods_root),
            "process_plan": str(plan_path),
            "seed_path": str(seed_path),
            "server": str(params.get("server", "")),
            "player_name": str(params.get("player_name", "")),
            "shad_executable": str(params.get("shad_executable", "")),
            "ap_client": str(params.get("ap_client", "")),
            "cache_root": str(settings.cache_root),
            "suppression_binder": str(settings.suppression_binder),
            "suppression_manifest": str(settings.suppression_manifest),
        },
    }


def production_verify(play: Any, params: Mapping[str, Any]) -> Any:
    from ..core import GameInstall
    from ..external import load_external_receipt, verify_external_activation

    game_root = Path(str(params["game_root"])).expanduser().resolve()
    state_root = Path(str(params.get("state_root", ""))).expanduser().resolve()
    receipt_path = (state_root / "external" / "receipts" / f"{play.receipt_id}.json")
    receipt = load_external_receipt(receipt_path)
    if receipt.receipt_id != play.receipt_id:
        raise ValidationError("play receipt identity does not match its stored receipt")
    install = GameInstall.from_root(game_root)
    return verify_external_activation(
        receipt, install=install, mods_root=Path(str(params["mods_root"])),
    )


def production_spawn(play: Any, arm: Any, params: Mapping[str, Any], verified: Any) -> Mapping[str, Any]:
    import os
    import subprocess
    import sys
    from dataclasses import replace

    from ..client_config import session_paths
    from ..core import GameInstall, SeedCache, sha256_file, validate_processes
    from ..external import load_external_receipt
    from ..external_workflow import _write_seed_suppression_manifest
    from ..workflow import (
        ProcessPlan, _composes_seed_binder, _request_identity, load_process_plan,
        resolve_process_plan,
    )
    from ..workflow import process_creation_time

    def stop_child(child: Any) -> None:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        else:
            child.wait()

    game_root = Path(str(params["game_root"])).expanduser().resolve()
    state_root = Path(str(params.get("state_root", ""))).expanduser().resolve()
    install = GameInstall.from_root(game_root)
    game = params.get("process_identity") or params.get("process") or {}
    required_identity = ("pid", "creation_time", "executable", "executable_sha256")
    if not isinstance(game, Mapping) or any(key not in game for key in required_identity):
        raise ValidationError("the started emulator process identity is incomplete")
    raw_pid = int(game["pid"])
    if raw_pid <= 0:
        raise ValidationError("the started emulator process identity has an invalid PID")
    seed_path = Path(str(params["seed_path"])).expanduser().resolve()
    request = _request_identity(
        seed_path, player_name=str(params.get("player_name", "")), state_root=state_root)
    cache = SeedCache(Path(str(params.get("cache_root", state_root / "cache"))))
    build = cache.verify(cache.path_for(play.cache_key), expected_key=play.cache_key)
    suppression_manifest = _suppression_file(params, state_root, "manifest")
    if _composes_seed_binder(request) or request.get("toast_placeholders") is not None:
        suppression_manifest = _write_seed_suppression_manifest(
            suppression_manifest, state_root=state_root, cache_key=build.cache_key,
            output_hash=build.manifest["suppression"]["sha256"],
            weapon_edits={key: request.get(key) for key in (
                "starting_weapons", "weapon_requirement_families", "shop_gate_permutation",
                "enemy_drop_assignments", "insight_armor_suppression", "toast_placeholders",
            )},
        )
    receipt = load_external_receipt(
        state_root / "external" / "receipts" / f"{play.receipt_id}.json")
    session = session_paths(state_root, seed=play.seed, slot=play.slot)
    activation_contract = {
        "format": "bb-external-activation-v1",
        "pid": raw_pid,
        "process_creation_time": int(game["creation_time"]),
        "executable": {"path": str(game["executable"]),
                       "sha256": str(game["executable_sha256"])},
        "game_path": str(install.base),
        "overlay_root": str(verified.overlay_root),
        "active_root": str(verified.active_root),
        "package_name": play.package_name,
        "files": [{"path": item.path, "sha256": item.sha256} for item in receipt.files],
        "activation_fingerprint": verified.activation_fingerprint,
        "invalidation_marker": str(session.session / "external-invalidation.json"),
    }
    paths = _write_runtime_config(
        state_root, seed=play.seed, slot=play.slot, installed=verified.installed_gameparam,
        suppression_manifest=suppression_manifest,
        shad_log=default_shad_log(),
        external_activation=activation_contract,
    )
    source_plan = load_process_plan(_process_plan(params, state_root))
    validate_processes(source_plan.processes)
    client = next((spec for spec in source_plan.processes
                   if spec.name.casefold() == "ap client"), None)
    if client is None:
        raise ValidationError("process plan has no AP client")
    client = replace(client, arguments=(*client.arguments,
                     "--require-external-activation-v1", "--require-external-activation-v1"))
    client_plan = ProcessPlan(source_plan.shad_build, source_plan.runtime_build, (client,))
    plan = resolve_process_plan(client_plan, paths, game_path=install.base)
    validate_processes(plan.processes)
    client = plan.processes[0]
    # Qt's EmulatorService has already started shadPS4 after arming. Starting
    # the full plan here would open a second game; this boundary starts only
    # the AP client. Keep its output off backend stdout, which is JSON-lines.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    environment = os.environ.copy()
    password = params.get("password")
    if password:
        # The native client consumes this private environment handoff. Never
        # put credentials in a process argument or backend log.
        environment["BB_AP_PASSWORD"] = str(password)
    child = subprocess.Popen(
        [str(client.executable), *client.arguments],
        cwd=str(client.working_directory) if client.working_directory else None,
        stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=subprocess.STDOUT,
        creationflags=flags, env=environment,
    )
    game_executable = str(game.get("executable", ""))
    if not game_executable:
        stop_child(child)
        raise ValidationError("the started emulator executable path is unavailable")
    try:
        client_birth = process_creation_time(int(child.pid)) if os.name == "nt" else None
    except Exception:
        stop_child(child)
        raise
    return {
        "executable": game_executable,
        "executable_sha256": str(game.get("executable_sha256", "")),
        "pid": int(game["pid"]),
        "creation_time": int(game["creation_time"]) if game.get("creation_time") is not None else None,
        "client_pid": int(child.pid),
        "client_creation_time": client_birth,
        "client_executable": str(client.executable),
        "client_executable_sha256": sha256_file(client.executable),
        "_process": child,
    }
