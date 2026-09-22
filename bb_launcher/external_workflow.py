"""BBLauncher orchestration; never invokes the standalone overlay transaction."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import time

from .core import (GameInstall, SeedCache, ValidationError, SUPPRESSION_PATH,
                   SEED_MANIFEST_NAME, sha256_file, _write_json_atomic,
                   validate_processes, require_no_stray_cheat_engine)
from .client_config import default_state_root, default_shad_log, session_key, session_paths, _write_runtime_config
from .workflow import (LauncherSettings, LauncherWorkflow, EnemizerOptions, WorkflowResult,
                       CLIENT_PROCESS_NAME, SHAD_PROCESS_NAME, ProcessPlan, _read_object,
                       _request_identity, _validate_category8_bridge_rows, load_process_plan,
                       refuse_stale_plan, _shad_game_argument, _ap_client_server,
                       _validate_suppression, validate_selected_build, check_seed_slot_identity,
                       _composes_seed_binder, _write_seed_suppression_manifest, resolve_process_plan)

BOOT_FORMAT = "bb-external-boot-observation-v1"
FILETIME_EPOCH = 116444736000000000
LOCAL_CANDIDATE_SHA = "a990d5507f22d8b0590d8b9426519c98de6fe86042a61a32e679e4a1a66b2d0a"
LOCAL_COPY_SHA = "2cfa43cf05a16e0c0ebaf87275d295961afff32c91ea57962e83c474358881f0"
LOCAL_CANDIDATE_COMMIT = "f092023f6cdf36a83ce735f7124b7835e9cf03b0"


def _state(settings):
    return (settings.state_root or default_state_root()).expanduser().resolve()


def _paths(settings):
    if settings.integration_mode != "bblauncher":
        raise ValidationError("Select BBLauncher mode for this action")
    if settings.bblauncher_mods is None or settings.bblauncher_executable is None:
        raise ValidationError("Select the BBLauncher executable and Mods directory")
    install = GameInstall.from_root(settings.game_root)
    protected = [install.base, install.mods, install.user_mods]
    if install.patch:
        protected.append(install.patch)
    destinations = [settings.cache_root, _state(settings), settings.bblauncher_mods]
    for destination in destinations:
        resolved = destination.expanduser().resolve()
        for tree in protected:
            if resolved == tree or resolved.is_relative_to(tree) or tree.is_relative_to(resolved):
                raise ValidationError(f"BBLauncher export state/cache/mods must be outside game trees: {resolved}")
    mods = settings.bblauncher_mods.expanduser().resolve()
    managed_root = mods.parent
    for label, raw in (("state root", _state(settings)), ("cache root", settings.cache_root)):
        resolved = raw.expanduser().resolve()
        if (resolved == managed_root or resolved.is_relative_to(managed_root)
                or managed_root.is_relative_to(resolved)):
            raise ValidationError(
                f"BBLauncher {label} must stay outside its managed Mods/config/backup root: "
                f"{resolved} and {managed_root}"
            )
    return install


def _pin(settings, *, candidate):
    from .external import BBLauncherBuildPin
    if sys.platform != "win32":
        raise ValidationError("BBLauncher integration currently requires Windows and a directory install")
    executable = settings.bblauncher_executable
    if executable is None or not executable.is_file() or executable.is_symlink():
        raise ValidationError("Select a regular BBLauncher executable")
    digest = sha256_file(executable)
    if digest not in (LOCAL_CANDIDATE_SHA, LOCAL_COPY_SHA) or not candidate:
        raise ValidationError("This BBLauncher build has not completed live acceptance. Use an explicitly pinned acceptance candidate for development testing.")
    return BBLauncherBuildPin(build="2026-08-09-f092023" + ("-noUAC" if digest == LOCAL_COPY_SHA else ""), commit=LOCAL_CANDIDATE_COMMIT,
                              executable_sha256=digest, live_acceptance_candidate=True)


def build_and_export(workflow: LauncherWorkflow, settings: LauncherSettings, options: EnemizerOptions,
                     *, player_name="", progress=lambda _: None, allow_live_acceptance_candidate=False):
    from .external import export_external_package, ExternalNamespace
    install = _paths(settings)
    pin = _pin(settings, candidate=allow_live_acceptance_candidate)
    prepared = workflow.prepare_seed(settings, options, player_name=player_name, progress=progress)
    client = next((p for p in prepared.plan.processes if p.name == CLIENT_PROCESS_NAME), None)
    if client is None:
        raise ValidationError("Process plan has no AP client")
    progress("Exporting the generated mod into BBLauncher's inactive Mods directory...")
    result = export_external_package(
        prepared.build, identity=prepared.identity, mods_root=settings.bblauncher_mods,
        state_root=_state(settings), install=install, bblauncher=pin,
        client_version="sha256:" + sha256_file(client.executable),
        suppression_manifest_sha256=sha256_file(settings.suppression_manifest),
        namespace=ExternalNamespace(prepared.build.cache_key, session_key(prepared.identity.seed, prepared.identity.slot)),
        allow_live_acceptance_candidate=allow_live_acceptance_candidate,
    )
    progress(f"Exported {result.package_path}. Seed {prepared.identity.seed}; slot {prepared.identity.slot}. Activate with BBLauncher while the game is stopped, then verify before booting.")
    return result


def _receipt(settings, *, candidate):
    from .external import load_external_receipt
    install = _paths(settings)
    pin = _pin(settings, candidate=candidate)
    if settings.bblauncher_receipt is None:
        raise ValidationError("Select the exported AP mod receipt")
    receipt = load_external_receipt(settings.bblauncher_receipt, allow_live_acceptance_candidate=candidate)
    if receipt.bblauncher != pin:
        raise ValidationError("Export receipt belongs to a different BBLauncher build")
    return install, receipt


def _verify(settings, *, candidate):
    from .external import verify_external_activation
    install, receipt = _receipt(settings, candidate=candidate)
    verified = verify_external_activation(receipt, install=install, mods_root=settings.bblauncher_mods,
                                          allow_live_acceptance_candidate=candidate)
    return install, receipt, verified


def _observation_path(settings):
    if settings.bblauncher_receipt is None:
        raise ValidationError("Select the exported AP mod receipt")
    digest = sha256_file(settings.bblauncher_receipt)
    return _state(settings) / "external-boot-observations" / (digest + ".json")


def verify_before_boot(workflow, settings, *, player_name="",
                       allow_live_acceptance_candidate=False):
    if workflow.shad_processes():
        raise ValidationError("Stop shadPS4, verify the activated mod, then start a fresh game from BBLauncher")
    install, receipt, verified = _verify(settings, candidate=allow_live_acceptance_candidate)
    request = _request_identity(
        settings.ap_request, player_name=player_name, state_root=settings.state_root
    )
    if (request["seed"], request["slot"]) != (
            receipt.identity.seed, receipt.identity.slot):
        raise ValidationError(
            "Selected AP seed/slot does not match the export receipt; select the matching "
            "receipt before verifying and booting"
        )
    observation = {
        "format": BOOT_FORMAT,
        "receipt_sha256": sha256_file(settings.bblauncher_receipt),
        "activation_fingerprint": verified.activation_fingerprint,
        "observed_filetime": FILETIME_EPOCH + time.time_ns() // 100,
    }
    if workflow.shad_processes():
        raise ValidationError("shadPS4 started during verification; stop it and verify again")
    _write_json_atomic(_observation_path(settings), observation)
    return verified


def connect_external(workflow, settings, *, player_name="", research_captures=False,
                     progress=lambda _: None, allow_live_acceptance_candidate=False):
    install, receipt, verified = _verify(settings, candidate=allow_live_acceptance_candidate)
    observation_path = _observation_path(settings)
    if not observation_path.is_file():
        raise ValidationError("Stop the game and select Verify activated mod, then start a fresh game from BBLauncher")
    observation = _read_object(observation_path, "activation verification before boot")
    if (observation.get("format") != BOOT_FORMAT
            or observation.get("receipt_sha256") != sha256_file(settings.bblauncher_receipt)
            or observation.get("activation_fingerprint") != verified.activation_fingerprint):
        raise ValidationError("AP-owned files or activation changed. Stop the game, verify the activated mod, and restart from BBLauncher")
    request = _request_identity(settings.ap_request, player_name=player_name, state_root=settings.state_root)
    request["category8_awards"] = _validate_category8_bridge_rows(request["category8_awards"])
    plan = load_process_plan(settings.process_plan)
    refuse_stale_plan(plan)
    shads = [p for p in plan.processes if p.name == SHAD_PROCESS_NAME]
    clients = [p for p in plan.processes if p.name == CLIENT_PROCESS_NAME]
    if len(shads) != 1 or len(clients) != 1:
        raise ValidationError("Connect requires exactly one shadPS4 and one AP client in the process plan")
    shad, client = shads[0], clients[0]
    validate_processes((shad, client))
    # receipt.client_version is export provenance, not a permanent executable
    # lock: compatible client fixes must not require rebuilding immutable game
    # data.  The runtime build, current process-plan hash, and mandatory
    # external-activation arguments form the connection compatibility gate.
    require_no_stray_cheat_engine(plan.processes, workflow.process_running)
    running = tuple(workflow.shad_processes())
    if not running:
        raise ValidationError("Waiting for game: start Bloodborne from BBLauncher")
    if len(running) != 1:
        raise ValidationError("Incompatible process: close additional shadPS4 instances")
    target = running[0]
    if target.executable is None or target.arguments is None or target.creation_time is None:
        raise ValidationError("Cannot verify process identity; run the companion and shadPS4 at the same privilege level")
    if target.executable.resolve() != shad.executable.resolve() or _shad_game_argument(target.arguments) != install.base:
        raise ValidationError("Incompatible process: running shadPS4 executable/game differs from the selected installation")
    observed = observation.get("observed_filetime")
    if not isinstance(observed, int) or target.creation_time <= observed:
        raise ValidationError("A fresh game boot is required after activation verification; restart from BBLauncher")
    if workflow.process_running(client.executable.name):
        raise ValidationError("The AP client is already running")
    identity = receipt.identity.as_dict()
    names = validate_selected_build(identity, request, plan, settings)
    build = SeedCache(settings.cache_root).verify(SeedCache(settings.cache_root).path_for(receipt.cache_key), expected_key=receipt.cache_key)
    if sha256_file(build.path / SEED_MANIFEST_NAME) != receipt.build_manifest_sha256:
        raise ValidationError("Export receipt and cached build manifest differ")
    _validate_suppression(install, settings.suppression_binder, settings.suppression_manifest,
                                       request["suppression_plan_sha256"])
    if receipt.suppression_manifest_sha256 is not None and sha256_file(settings.suppression_manifest) != receipt.suppression_manifest_sha256:
        raise ValidationError("Suppression manifest differs from the exported seed receipt")
    _, _, late = _verify(settings, candidate=allow_live_acceptance_candidate)
    if (late.activation_fingerprint != verified.activation_fingerprint
            or tuple(workflow.shad_processes()) != running):
        raise ValidationError("Activation/process changed during connection; verify and restart")
    server = _ap_client_server(plan)
    if not server or server.startswith("-") or "{" in server or "}" in server:
        raise ValidationError("AP client has no valid server address")
    check_seed_slot_identity(_state(settings), server=server, seed=request["seed"], slot=request["slot"])
    manifest = settings.suppression_manifest
    if _composes_seed_binder(request) or names is not None:
        manifest = _write_seed_suppression_manifest(
            manifest, state_root=_state(settings), cache_key=build.cache_key,
            output_hash=build.manifest["suppression"]["sha256"],
            weapon_edits={k: request.get(k) for k in ("starting_weapons", "weapon_requirement_families", "shop_gate_permutation", "enemy_drop_assignments", "insight_armor_suppression", "toast_placeholders")},
        )
    contract = {
        "format": "bb-external-activation-v1", "pid": target.pid,
        "process_creation_time": target.creation_time,
        "executable": {"path": str(target.executable), "sha256": sha256_file(target.executable)},
        "game_path": str(install.base), "overlay_root": str(install.mods),
        "active_root": str(verified.active_root),
        "package_name": receipt.package_name, "files": [{"path": f.path, "sha256": f.sha256} for f in receipt.files],
        "activation_fingerprint": verified.activation_fingerprint,
        "invalidation_marker": str(session_paths(_state(settings), seed=request["seed"],
                                                slot=request["slot"]).session / "external-invalidation.json"),
    }
    installed = verified.installed_gameparam
    paths = _write_runtime_config(
        _state(settings), seed=request["seed"], slot=request["slot"], installed=installed,
        suppression_manifest=manifest, shad_log=settings.shad_log or default_shad_log(),
        auto_upgrade=request["auto_upgrade"], auto_equip=request["auto_equip"],
        research_captures=research_captures, external_activation=contract,
    )
    # Older clients accept one unknown argument as a password. Two copies
    # make those clients fail argument parsing before any attachment/network use.
    client = replace(client, arguments=(*client.arguments,
                     "--require-external-activation-v1", "--require-external-activation-v1"))
    resolved = resolve_process_plan(ProcessPlan(plan.shad_build, plan.runtime_build, (client,)), paths, game_path=install.base)
    _, _, final = _verify(settings, candidate=allow_live_acceptance_candidate)
    if final.activation_fingerprint != verified.activation_fingerprint or tuple(workflow.shad_processes()) != running:
        raise ValidationError("Activation/process changed during connection; verify and restart")
    if workflow.process_running(client.executable.name):
        raise ValidationError("The AP client started during verification")
    require_no_stray_cheat_engine(plan.processes, workflow.process_running)
    progress(f"Ready: seed {request['seed']}, slot {request['slot']}; starting only the AP client")
    started = workflow.process_launcher(resolved.processes)
    early = workflow.process_watcher(started, resolved.processes)
    return WorkflowResult(build.cache_key, build.path, True,
                          bool(build.manifest.get("enemizer", {}).get("enabled")),
                          int(build.manifest.get("enemizer", {}).get("file_count", 0)),
                          tuple(getattr(p, "pid", None) for p in started), paths.config, paths.ledger,
                          False, client_log=paths.client_log, early_exit=early)
