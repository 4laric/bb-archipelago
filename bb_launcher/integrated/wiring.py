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
    if len(found) > 1:
        return {"game_running": True, "ambiguous": True,
                "pids": sorted(proc.pid for proc in found)}
    proc = found[0]
    executable = str(proc.executable) if proc.executable is not None else ""
    digest = ""
    if proc.executable is not None:
        try:
            digest = sha256_file(proc.executable)
        except (OSError, ValidationError):
            digest = ""
    return {
        "game_running": True,
        "pid": proc.pid,
        "executable": executable,
        "executable_sha256": digest,
        "creation_time": proc.creation_time,
        "alive": True,
    }


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
    from ..resources import application_root
    from ..workflow import EnemizerOptions, LauncherSettings, LauncherWorkflow
    from .policy import require_fork_provenance
    from .sessions import integrated_root

    game_root = Path(str(params["game_root"])).expanduser().resolve()
    state_root = Path(str(params.get("state_root", ""))).expanduser().resolve()
    mods_root = Path(str(params["mods_root"])).expanduser().resolve()
    seed_path = Path(str(params["seed_path"])).expanduser().resolve()
    fork = params.get("fork_build") or {}
    require_fork_provenance(str(fork.get("commit", "")), str(fork.get("executable_sha256", "")))

    settings = LauncherSettings(
        game_root=game_root,
        cache_root=Path(str(params.get("cache_root",
                                       state_root / "cache"))).expanduser().resolve(),
        ap_request=seed_path,
        suppression_binder=_suppression_file(params, state_root, "binder"),
        suppression_manifest=_suppression_file(params, state_root, "manifest"),
        process_plan=_process_plan(params, state_root),
        state_root=state_root,
    )
    workflow = LauncherWorkflow(application_root())
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
    from ..core import GameInstall, sha256_file, validate_processes
    from ..workflow import load_process_plan, resolve_process_plan
    from ..core import launch_processes

    game_root = Path(str(params["game_root"])).expanduser().resolve()
    state_root = Path(str(params.get("state_root", ""))).expanduser().resolve()
    install = GameInstall.from_root(game_root)
    manifest = install.mods / "build-manifest.json"
    paths = _write_runtime_config(
        state_root, seed=play.seed, slot=play.slot, installed=verified.installed_gameparam,
        suppression_manifest=manifest if manifest.is_file() else None,
        shad_log=default_shad_log(),
        external_activation={"receipt_id": play.receipt_id,
                             "fingerprint": verified.activation_fingerprint},
    )
    plan = resolve_process_plan(
        load_process_plan(_process_plan(params, state_root)), paths, game_path=install.base,
    )
    validate_processes(plan.processes)
    pids = launch_processes(plan.processes)
    shad = next((spec for spec in plan.processes if "shad" in spec.name.casefold()),
                plan.processes[0])
    return {
        "executable": str(shad.executable),
        "executable_sha256": sha256_file(shad.executable),
        "pid": int(pids[0]) if pids and pids[0] is not None else 0,
        "creation_time": None,
        "client_pid": int(pids[-1]) if pids and pids[-1] is not None else None,
    }
