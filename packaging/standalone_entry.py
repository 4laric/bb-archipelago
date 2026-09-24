"""Console entry point for the self-contained standalone randomizer package."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="BloodborneRandomizer build",
        description="Build a verified local standalone Bloodborne randomizer overlay.",
    )
    parser.add_argument(
        "--game-root",
        type=Path,
        required=True,
        help="the installed game's dvdroot_ps4 directory",
    )
    parser.add_argument("--seed", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-dlc", action="store_true")
    parser.add_argument("--reduced-item-pool", action="store_true")
    parser.add_argument(
        "--goal",
        choices=("submit_to_gehrman", "refuse_gehrman", "moon_presence"),
        default="moon_presence",
    )
    parser.add_argument("--randomize-enemies", action="store_true")
    parser.add_argument("--enemy-seed")
    parser.add_argument("--preserve-locomotion", action="store_true")
    parser.add_argument("--normalize-enemy-scaling", action="store_true")
    parser.add_argument("--expanded-coverage", action="store_true")
    parser.add_argument("--maps", type=Path, help="development override for MapStudio")
    parser.add_argument(
        "--enemy-scripts", type=Path, help="development override for enemy AI scripts"
    )
    parser.add_argument(
        "--enemy-inventory", type=Path, help="development override for enemy inventory"
    )
    parser.add_argument("--wakeup-event", type=Path,
                        help="development override for the original wakeup event")
    parser.add_argument(
        "--item-writer", type=Path, help="development override for the item writer"
    )
    parser.add_argument(
        "--enemy-writer", type=Path, help="development override for the enemy writer"
    )
    parser.add_argument(
        "--dotnet", type=Path, help="development host for DLL writer overrides"
    )
    return parser


def build_arguments(args: argparse.Namespace, package_root: Path) -> list[str]:
    game = args.game_root.expanduser().resolve()
    tools = package_root / "tools"
    item_writer = args.item_writer or tools / "BBStandaloneItemWriter.exe"
    command = [
        "--seed",
        args.seed,
        "--gameparam",
        str(game / "param/gameparam/gameparam.parambnd.dcx"),
        "--paramdef",
        str(game / "paramdef/paramdef.paramdefbnd.dcx"),
        "--item-writer",
        str(item_writer),
        "--output",
        str(args.output.expanduser().resolve()),
        "--goal",
        args.goal,
        "--apply",
    ]
    for enabled, flag in (
        (args.include_dlc, "--include-dlc"),
        (args.reduced_item_pool, "--reduced-item-pool"),
    ):
        if enabled:
            command.append(flag)
    if args.dotnet is not None:
        command.extend(("--dotnet", str(args.dotnet.expanduser().resolve())))
    if not args.randomize_enemies:
        return command

    enemy_writer = args.enemy_writer or tools / "BBStandaloneEnemyWriter.exe"
    maps = args.maps or game / "map/MapStudio"
    scripts = args.enemy_scripts or game / "script"
    command.extend(
        (
            "--randomize-enemies",
            "--maps",
            str(maps.expanduser().resolve()),
            "--enemy-scripts",
            str(scripts.expanduser().resolve()),
            "--enemy-writer",
            str(enemy_writer),
        )
    )
    if args.enemy_seed:
        command.extend(("--enemy-seed", args.enemy_seed))
    if args.enemy_inventory is not None:
        command.extend(
            ("--enemy-inventory", str(args.enemy_inventory.expanduser().resolve()))
        )
    if args.expanded_coverage:
        event = args.wakeup_event or game / "event/m24_01_00_00.emevd.dcx"
        command.extend(("--wakeup-event", str(event.expanduser().resolve())))
    for enabled, flag in (
        (args.preserve_locomotion, "--preserve-locomotion"),
        (args.normalize_enemy_scaling, "--normalize-enemy-scaling"),
        (args.expanded_coverage, "--expanded-coverage"),
    ):
        if enabled:
            command.append(flag)
    return command


def _print_help() -> None:
    print(
        "BloodborneRandomizer commands:\n"
        "  build   Generate a verified standalone item/enemy overlay.\n"
        "  export  Export an overlay as an inactive BBLauncher directory or ZIP.\n"
        "  verify  Verify an exported directory or ZIP and its receipt.\n\n"
        "Run BloodborneRandomizer <command> --help for command options."
    )


def main(
    argv: Sequence[str] | None = None, *, package_root: Path | None = None
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments[:1] == ["--internal-enemy-planner"]:
        from tools.bb_enemizer.cli import main as planner_main

        return planner_main(arguments[1:])
    if not arguments or arguments[0] in ("-h", "--help"):
        _print_help()
        return 0
    if arguments[0] in ("export", "verify"):
        from tools.export_standalone_mod import main as export_main

        return export_main(arguments)
    if arguments[0] != "build":
        print(f"Unknown command: {arguments[0]}", file=sys.stderr)
        _print_help()
        return 2

    parsed = _build_parser().parse_args(arguments[1:])
    from tools.build_standalone_randomizer import main as build_main

    return build_main(build_arguments(parsed, package_root or application_root()))


def entrypoint(argv: Sequence[str] | None = None) -> int:
    try:
        return main(argv)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
