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
    recover_activation,
    restore_previous_build,
    validate_processes,
)
from .workflow import load_process_plan


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
                    "patch": str(install.patch),
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
                    "patch": str(install.patch),
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
                activate_build(install, args.build)
            started = launch_processes(processes)
            _print(
                {
                    "mode": "vanilla" if args.vanilla else "randomized",
                    "started": [
                        {"name": spec.name, "pid": getattr(process, "pid", None)}
                        for spec, process in zip(processes, started)
                    ],
                }
            )
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
