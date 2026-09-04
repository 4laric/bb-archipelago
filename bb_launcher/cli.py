"""UI-independent command line surface for the launcher core."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .core import (
    OWNER_NAME,
    ConflictError,
    GameInstall,
    LauncherError,
    SeedCache,
    SeedIdentity,
    ValidationError,
    _load_owner,
    activate_build,
    deactivate_overlay,
    discover_game_install,
    discover_shad_executable,
    launch_processes,
    require_no_stray_cheat_engine,
    recover_activation,
    restore_previous_build,
    validate_processes,
    wait_for_early_exit,
)
from .client_config import default_shad_log, default_state_root, write_client_runtime_config
from .doctor import format_report, run_doctor
from .plan import DEFAULT_SERVER, DEFAULT_SHAD_BUILD, generate_process_plan, write_process_plan
from .workflow import LauncherSettings, _request_identity, load_process_plan, resolve_process_plan


def _json_file(path: str | Path, label: str) -> dict[str, Any]:
    source = Path(path)
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"could not read {label} {source}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object: {source}")
    return value


def _install(path: str) -> GameInstall:
    return GameInstall.from_root(path)


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bb_launcher",
        description="Bloodborne AP seed cache and shadPS4 overlay launcher core.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    discover = commands.add_parser("discover", help="find and validate game/shad setup")
    discover.add_argument("--game-root", action="append", required=True, dest="game_roots")
    discover.add_argument("--shad-root", action="append", required=True, dest="shad_roots")

    validate = commands.add_parser("validate-game", help="validate CUSA03173 AppVer 01.09")
    validate.add_argument("--game-root", required=True)

    resolve = commands.add_parser("resolve", help="show the shad backend selected for one file")
    resolve.add_argument("--game-root", required=True)
    resolve.add_argument("--path", required=True)
    resolve.add_argument("--source-only", action="store_true")

    build = commands.add_parser("build", help="compose a verified hash-addressed seed cache")
    build.add_argument("--cache-root", required=True)
    build.add_argument("--game-root", required=True)
    build.add_argument("--identity", required=True, help="SeedIdentity JSON file")
    build.add_argument("--suppression-binder", required=True)
    build.add_argument("--map-studio")

    verify = commands.add_parser("verify-build", help="verify every cached output hash and path")
    verify.add_argument("--build", required=True)

    activate = commands.add_parser("activate", help="transactionally activate a cached build")
    activate.add_argument("--game-root", required=True)
    activate.add_argument("--build", required=True)

    recover = commands.add_parser("recover", help="finish or roll back an interrupted transaction")
    recover.add_argument("--game-root", required=True)

    vanilla = commands.add_parser("vanilla", help="disable only a verified launcher-owned overlay")
    vanilla.add_argument("--game-root", required=True)

    restore = commands.add_parser("restore-previous", help="reactivate the previous cached seed")
    restore.add_argument("--game-root", required=True)
    restore.add_argument("--cache-root", required=True)

    status = commands.add_parser("status", help="report installation and active overlay identity")
    status.add_argument("--game-root", required=True)

    run = commands.add_parser("run", help="activate or bypass an overlay, then start all components")
    run.add_argument("--game-root", required=True)
    mode = run.add_mutually_exclusive_group(required=True)
    mode.add_argument("--build")
    mode.add_argument("--vanilla", action="store_true")
    run.add_argument("--process-plan", required=True)
    run.add_argument(
        "--state-root",
        help="launcher state root for the generated client runtime config and per-session ledgers",
    )
    run.add_argument(
        "--suppression-manifest",
        help="build-manifest.json of the seed's suppression binder (recorded in the client config)",
    )
    run.add_argument("--shad-log", help="shadPS4 log path recorded in the client config")

    plan = commands.add_parser("plan", help="generate a hash-pinned process plan (#65)")
    plan.add_argument("--output", required=True, help="where to write the process plan JSON")
    plan.add_argument("--shad", required=True, help="shadPS4 executable to pin")
    plan.add_argument("--client", required=True, help="AP client executable to pin")
    plan.add_argument("--server", default=DEFAULT_SERVER, help="Archipelago server address")
    plan.add_argument("--shad-build", default=DEFAULT_SHAD_BUILD, help="shadPS4 build string")
    plan.add_argument("--slot", help="AP slot name (defaults to the AP request's player_name)")
    plan.add_argument("--runtime-build", help="runtime build string (defaults to the AP request's)")
    plan.add_argument(
        "--ap-request",
        help=(
            "AP seed file to derive the slot and runtime build from: the "
            "AP_<seed>.zip, or an extracted *.bbseed.json"
        ),
    )
    plan.add_argument("--force", action="store_true", help="overwrite an existing plan")

    doctor = commands.add_parser(
        "doctor", help="preflight the whole player chain in one pass (#103)"
    )
    doctor.add_argument("--settings", required=True, help="launcher settings JSON (the UI saves one)")
    doctor.add_argument("--server", help="override the AP server probe target")
    doctor.add_argument(
        "--player-name", help="override the AP player name the request slot is verified against"
    )
    doctor.add_argument(
        "--no-enemizer", action="store_true", help="skip the enemy-randomization checks"
    )
    doctor.add_argument(
        "--allow-suppression-mismatch",
        action="store_true",
        help="OPERATORS ONLY: report suppression binder/seed/install hash skew as a "
        "named WARN instead of a FAIL (bb-archipelago#183)",
    )

    report = commands.add_parser(
        "enemy-report",
        help="write a paste-ready report of the active seed's enemy swaps (bb-archipelago#321)",
    )
    report.add_argument("--settings", required=True, help="launcher settings JSON (the UI saves one)")
    report.add_argument("--area", help="only this map prefix, e.g. m24_01 for Central Yharnam")
    report.add_argument(
        "--echoes", type=int, help="Blood Echoes you saw awarded; ranks the closest enemies first"
    )
    report.add_argument("--note", default="", help="what you saw, in your own words")
    report.add_argument("--player-name", help="override the AP player name the seed is resolved for")
    report.add_argument("--output", help="write here instead of the launcher state root")

    ui = commands.add_parser("ui", help="open the Bloodborne AP desktop launcher")
    ui.add_argument("--settings")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "discover":
            install = discover_game_install(args.game_roots)
            shad = discover_shad_executable(args.shad_roots)
            _print(
                {
                    "game_root": str(install.root),
                    "base": str(install.base),
                    "patch": str(install.patch) if install.patch is not None else None,
                    "mods": str(install.mods),
                    "serial": install.serial,
                    "app_version": install.app_version,
                    "shad_executable": str(shad),
                }
            )
        elif args.command == "validate-game":
            install = _install(args.game_root)
            _print(
                {
                    "game_root": str(install.root),
                    "serial": install.serial,
                    "app_version": install.app_version,
                    "base": str(install.base),
                    "patch": str(install.patch) if install.patch is not None else None,
                }
            )
        elif args.command == "resolve":
            backend, path = _install(args.game_root).resolve_file(
                args.path, include_mods=not args.source_only
            )
            _print({"backend": backend, "path": str(path)})
        elif args.command == "build":
            identity = SeedIdentity.from_dict(_json_file(args.identity, "seed identity"))
            _install(args.game_root).verify_source_hashes(identity.source_hashes)
            result = SeedCache(args.cache_root).build(
                identity,
                args.suppression_binder,
                args.map_studio,
            )
            _print(
                {
                    "path": str(result.path),
                    "cache_key": result.cache_key,
                    "reused": result.reused,
                    "files": result.manifest["files"],
                }
            )
        elif args.command == "verify-build":
            build_path = Path(args.build).expanduser().resolve()
            result = SeedCache(build_path.parent).verify(build_path)
            _print(
                {
                    "path": str(result.path),
                    "cache_key": result.cache_key,
                    "identity": result.manifest["identity"],
                }
            )
        elif args.command == "activate":
            owner = activate_build(_install(args.game_root), args.build)
            _print(owner)
        elif args.command == "recover":
            result = recover_activation(_install(args.game_root))
            _print({"recovery": result})
        elif args.command == "vanilla":
            disabled = deactivate_overlay(_install(args.game_root))
            _print({"disabled_overlay": None if disabled is None else str(disabled)})
        elif args.command == "restore-previous":
            owner = restore_previous_build(
                _install(args.game_root), SeedCache(args.cache_root)
            )
            _print(owner)
        elif args.command == "status":
            install = _install(args.game_root)
            recovery = recover_activation(install)
            status_value: dict[str, Any] = {
                "game_root": str(install.root),
                "serial": install.serial,
                "app_version": install.app_version,
                "recovery": recovery,
                "overlay": None,
            }
            if install.mods.exists():
                try:
                    owner = _load_owner(install.mods)
                    status_value["overlay"] = {
                        "ownership": OWNER_NAME,
                        "cache_key": owner["cache_key"],
                        "previous_cache_key": owner.get("previous_cache_key"),
                        "identity": owner["identity"],
                        "suppression": owner["suppression"],
                        "enemizer": owner["enemizer"],
                    }
                except ConflictError as exc:
                    status_value["overlay"] = {"conflict": str(exc)}
            _print(status_value)
        elif args.command == "run":
            install = _install(args.game_root)
            process_plan = load_process_plan(args.process_plan)
            processes = process_plan.processes
            validate_processes(processes)
            paths = None
            if args.vanilla:
                deactivate_overlay(install)
            else:
                build_path = Path(args.build).expanduser().resolve()
                build = SeedCache(build_path.parent).verify(build_path)
                build_identity = build.manifest["identity"]
                if build_identity["shad_build"] != process_plan.shad_build:
                    raise ValidationError(
                        f"seed requires shadPS4 {build_identity['shad_build']}, "
                        f"process plan supplies {process_plan.shad_build}"
                    )
                if build_identity["runtime_build"] != process_plan.runtime_build:
                    raise ValidationError(
                        f"seed requires runtime {build_identity['runtime_build']}, "
                        f"process plan supplies {process_plan.runtime_build}"
                    )
                owner = activate_build(install, args.build)
                paths = write_client_runtime_config(
                    args.state_root or default_state_root(),
                    seed=build_identity["seed"],
                    slot=build_identity["slot"],
                    install=install,
                    owner=owner,
                    suppression_manifest=args.suppression_manifest,
                    shad_log=args.shad_log or default_shad_log(),
                )
            resolved = resolve_process_plan(
                process_plan, paths, game_path=install.base
            ).processes
            require_no_stray_cheat_engine(resolved)
            started = launch_processes(resolved)
            early_exit = wait_for_early_exit(started, resolved)
            _print(
                {
                    "mode": "vanilla" if args.vanilla else "randomized",
                    "client_config": None if paths is None else str(paths.config),
                    "ledger": None if paths is None else str(paths.ledger),
                    "client_log": None if paths is None else str(paths.client_log),
                    "shad_process_log": (
                        None if paths is None else str(paths.shad_process_log)
                    ),
                    "early_exit": (
                        None
                        if early_exit is None
                        else {
                            "name": early_exit.name,
                            "returncode": early_exit.returncode,
                            "log_path": (
                                None
                                if early_exit.log_path is None
                                else str(early_exit.log_path)
                            ),
                            "log_tail": early_exit.log_tail,
                            "message": early_exit.describe(),
                        }
                    ),
                    "started": [
                        {"name": spec.name, "pid": getattr(process, "pid", None)}
                        for spec, process in zip(processes, started)
                    ],
                }
            )
        elif args.command == "plan":
            slot = args.slot
            runtime_build = args.runtime_build
            if args.ap_request is not None:
                request = _request_identity(
                    Path(args.ap_request).expanduser().resolve(),
                    player_name=(args.slot or ""),
                )
                if slot is not None and slot != request["slot"]:
                    raise ValidationError(
                        f"--slot {slot!r} disagrees with the AP request "
                        f"({request['slot']!r})"
                    )
                if runtime_build is not None and runtime_build != request["runtime_build"]:
                    raise ValidationError(
                        f"--runtime-build {runtime_build!r} disagrees with the AP request "
                        f"({request['runtime_build']!r})"
                    )
                slot = slot or request["slot"]
                runtime_build = runtime_build or request["runtime_build"]
            if slot is None:
                raise ValidationError("plan requires --slot or --ap-request")
            if runtime_build is None:
                raise ValidationError("plan requires --runtime-build or --ap-request")
            document = generate_process_plan(
                shad_executable=args.shad,
                client_executable=args.client,
                server=args.server,
                shad_build=args.shad_build,
                slot=slot,
                runtime_build=runtime_build,
            )
            destination = write_process_plan(args.output, document, force=args.force)
            _print(
                {
                    "path": str(destination),
                    "processes": [record["name"] for record in document["processes"]],
                }
            )
        elif args.command == "doctor":
            settings_path = Path(args.settings).expanduser().resolve()
            raw = _json_file(settings_path, "launcher settings")
            settings = LauncherSettings.from_dict(raw, relative_to=settings_path.parent)
            server = args.server
            player_name = args.player_name
            randomize = not args.no_enemizer
            # The UI saves these alongside the settings fields; honor them
            # unless an explicit flag overrides.
            if server is None and isinstance(raw.get("ap_server"), str):
                server = raw["ap_server"].strip() or None
            if player_name is None and isinstance(raw.get("player_name"), str):
                player_name = raw["player_name"].strip() or None
            if not args.no_enemizer and raw.get("randomize_enemies") is False:
                randomize = False
            # Deliberately not read from the saved settings: the override is
            # per-invocation, so a saved setup can never silently keep it on.
            report = run_doctor(
                settings,
                randomize_enemies=randomize,
                server=server,
                player_name=player_name,
                allow_suppression_mismatch=args.allow_suppression_mismatch,
            )
            print(format_report(report))
            return 0 if report.ok else 1
        elif args.command == "enemy-report":
            from .enemy_report import format_report as format_enemy_report
            from .enemy_report import load_context, write_report

            settings_path = Path(args.settings).expanduser().resolve()
            raw = _json_file(settings_path, "launcher settings")
            settings = LauncherSettings.from_dict(raw, relative_to=settings_path.parent)
            player_name = args.player_name
            if player_name is None and isinstance(raw.get("player_name"), str):
                player_name = raw["player_name"].strip()
            context = load_context(settings, player_name=player_name or "")
            text = format_enemy_report(
                context, area=args.area, echoes=args.echoes, note=args.note
            )
            if args.output:
                destination = Path(args.output).expanduser().resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(text, encoding="utf-8", newline="\n")
            else:
                destination = write_report(settings.state_root or default_state_root(), text)
            print(text)
            print(f"Saved to {destination}", file=sys.stderr)
        elif args.command == "ui":
            from .ui import main as ui_main

            ui_arguments = [] if args.settings is None else ["--settings", args.settings]
            return ui_main(ui_arguments)
        else:
            parser.error(f"unknown command {args.command}")
        return 0
    except LauncherError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
