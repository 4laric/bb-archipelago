#!/usr/bin/env python3
"""Build a local, static Bloodborne item and optional enemy overlay.

This command is intentionally separate from the Archipelago launcher.  It
generates a native item plan, applies it to a staged parameter archive, and can
then run the existing ordinary-enemy planner and guarded native writer.  It
never installs the overlay or touches saves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bb_standalone import StandaloneOptions, generate_plan
from tools.bb_standalone.catalog import CATALOG_PATH
from tools.bb_standalone.schema import GAMEPARAM_PATH, PARAMDEF_PATH
from tools.bb_inputs import DEFAULT_BUNDLE, read_blob


BUILD_FORMAT = "bb-standalone-build-identity-v1"
RECEIPT_FORMAT = "bb-standalone-build-receipt-v1"
MAP_ROOT = Path("dvdroot_ps4/map/MapStudio")
SCRIPT_ROOT = Path("dvdroot_ps4/script")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
Runner = Callable[..., subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class EnemyOptions:
    enabled: bool = False
    seed: str | None = None
    allow_tier_mixing: bool = False
    preserve_locomotion: bool = False
    normalize_scaling: bool = False


@dataclass(frozen=True)
class BuildConfig:
    seed: str
    gameparam: Path
    paramdef: Path
    item_writer: Path
    output: Path
    dotnet: Path | None = None
    item_options: StandaloneOptions = StandaloneOptions()
    enemy_options: EnemyOptions = EnemyOptions()
    maps: Path | None = None
    scripts: Path | None = None
    enemy_writer: Path | None = None
    enemy_inventory: Path | None = None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read {label}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _regular_file(path: Path, label: str) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"{label} is not a regular file: {path}")


def _source_files(root: Path, suffixes: tuple[str, ...], label: str) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise ValueError(f"{label} is not a directory: {root}")
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name.lower().endswith(suffixes)
    )
    if not files:
        raise ValueError(f"{label} contains no supported source files: {root}")
    return files


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _native_command(dotnet: Path | None, writer: Path) -> list[str]:
    if writer.suffix.lower() == ".dll":
        if dotnet is None:
            raise ValueError(f"--dotnet is required for writer DLL: {writer}")
        return [str(dotnet), "--roll-forward", "Major", str(writer)]
    return [str(writer)]


def _run(
    command: Sequence[str], runner: Runner, *, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    return runner(
        list(command),
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )


def _parse_writer_receipt(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError:
        value = None
    if isinstance(value, dict):
        return value
    decoder = json.JSONDecoder()
    for offset, character in enumerate(stdout):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(stdout[offset:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("standalone item writer produced no JSON receipt")


def _snapshot(config: BuildConfig) -> tuple[dict[str, str], dict[Path, str]]:
    source_hashes = {
        GAMEPARAM_PATH: _hash_file(config.gameparam),
        PARAMDEF_PATH: _hash_file(config.paramdef),
    }
    physical = {
        config.gameparam: source_hashes[GAMEPARAM_PATH],
        config.paramdef: source_hashes[PARAMDEF_PATH],
    }
    if config.enemy_options.enabled:
        assert config.maps is not None and config.scripts is not None
        for path in _source_files(config.maps, (".msb", ".msb.dcx"), "MapStudio source"):
            relative = path.relative_to(config.maps).as_posix()
            logical = f"{MAP_ROOT.as_posix()}/{relative}"
            if logical in source_hashes:
                raise ValueError(f"duplicate source identity path: {logical}")
            source_hashes[logical] = physical[path] = _hash_file(path)
        for path in _source_files(config.scripts, (".luabnd", ".luabnd.dcx"), "enemy script source"):
            relative = path.relative_to(config.scripts).as_posix()
            logical = f"{SCRIPT_ROOT.as_posix()}/{relative}"
            if logical in source_hashes:
                raise ValueError(f"duplicate source identity path: {logical}")
            source_hashes[logical] = physical[path] = _hash_file(path)
        if config.enemy_inventory is not None:
            physical[config.enemy_inventory] = _hash_file(config.enemy_inventory)
    return source_hashes, physical


def _validate(config: BuildConfig) -> None:
    if not config.seed.strip():
        raise ValueError("standalone seed must be non-empty")
    for path, label in (
        (config.gameparam, "original gameparam"),
        (config.paramdef, "original paramdef"),
        (config.item_writer, "standalone item writer"),
        (CATALOG_PATH, "standalone award catalog"),
    ):
        _regular_file(path, label)
    if config.item_writer.suffix.lower() == ".dll":
        if config.dotnet is None:
            raise ValueError("--dotnet is required for an item-writer DLL")
        _regular_file(config.dotnet, "dotnet host")
    if config.output.exists() or config.output.is_symlink():
        raise ValueError(f"refusing to overwrite existing output: {config.output}")
    for source in (config.gameparam, config.paramdef):
        if config.output == source or _is_under(config.output, source.parent):
            raise ValueError(f"output must be outside original input directory: {source.parent}")
    enemy = config.enemy_options
    if enemy.enabled:
        if config.maps is None or config.scripts is None or config.enemy_writer is None:
            raise ValueError(
                "enemy randomization requires --maps, --enemy-scripts and --enemy-writer"
            )
        _regular_file(config.enemy_writer, "enemy writer")
        if config.enemy_inventory is not None:
            _regular_file(config.enemy_inventory, "enemy inventory")
        else:
            _regular_file(DEFAULT_BUNDLE, "bundled enemy inventory source")
        if config.enemy_writer.suffix.lower() == ".dll":
            if config.dotnet is None:
                raise ValueError("--dotnet is required for an enemy-writer DLL")
            _regular_file(config.dotnet, "dotnet host")
        _source_files(config.maps, (".msb", ".msb.dcx"), "MapStudio source")
        _source_files(config.scripts, (".luabnd", ".luabnd.dcx"), "enemy script source")
        for source_root in (config.maps, config.scripts):
            if _is_under(config.output, source_root):
                raise ValueError(f"output must be outside original input directory: {source_root}")


def _verify_item_receipt(
    receipt: Mapping[str, Any], plan_path: Path, source: Path, output: Path
) -> None:
    expected = {
        "format": "bb-standalone-item-receipt-v1",
        "plan_sha256": _hash_file(plan_path),
        "source_sha256": _hash_file(source),
        "output_sha256": _hash_file(output),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise ValueError(f"standalone item writer receipt has invalid {key}")


def _verify_enemy_plan(path: Path, seed: str) -> dict[str, Any]:
    plan = _read_object(path, "enemy plan")
    if (
        plan.get("format") != "bb-enemizer-plan-v2"
        or plan.get("dry_run") is not True
        or plan.get("seed") != seed
        or not isinstance(plan.get("swaps"), list)
        or not plan["swaps"]
    ):
        raise ValueError("ordinary enemy planner produced an invalid or empty plan")
    return plan


def _verify_ai(stage: Path, plan_path: Path) -> dict[str, Any]:
    script_root = stage / SCRIPT_ROOT
    report = _read_object(Path(str(script_root) + ".json"), "enemy AI receipt")
    if (
        report.get("format") != "bb-enemizer-ai-v1"
        or report.get("applied") is not True
        or report.get("plan_sha256") != _hash_file(plan_path)
        or not isinstance(report.get("maps"), list)
        or not report["maps"]
    ):
        raise ValueError("enemy AI writer produced an invalid receipt")
    expected: set[Path] = set()
    for row in report["maps"]:
        if not isinstance(row, dict) or int(row.get("missing_goals_after", -1)) != 0:
            raise ValueError("enemy AI receipt reports unresolved goals")
        name = str(row.get("map", ""))
        if Path(name).name != name:
            raise ValueError("enemy AI receipt contains an escaping path")
        output = script_root / name
        if (
            not output.is_file()
            or output.is_symlink()
            or row.get("output_sha256") != _hash_file(output)
        ):
            raise ValueError(f"enemy AI output verification failed: {name}")
        expected.add(output)
    actual = {path for path in script_root.iterdir() if path.is_file()}
    if actual != expected:
        raise ValueError("enemy AI output file set differs from its receipt")
    return report


def _verify_scaling(stage: Path, plan_path: Path, item_binder: Path) -> dict[str, Any]:
    report = _read_object(stage / "scaling-report.json", "enemy scaling receipt")
    output = stage / GAMEPARAM_PATH
    if (
        report.get("applied") is not True
        or report.get("source_plan_sha256") != _hash_file(plan_path)
        or report.get("source_gameparam_sha256") != _hash_file(item_binder)
        or report.get("output_gameparam_sha256") != _hash_file(output)
        or report.get("output_plan_sha256") != _hash_file(stage / "bb-enemizer-plan.json")
    ):
        raise ValueError("enemy scaling writer produced an invalid composition receipt")
    return report


def _assert_sources_unchanged(snapshot: Mapping[Path, str]) -> None:
    changed = [str(path) for path, digest in snapshot.items() if not path.is_file() or _hash_file(path) != digest]
    if changed:
        raise ValueError("original input changed during standalone build: " + ", ".join(changed))


def _file_records(root: Path) -> list[dict[str, Any]]:
    return [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _hash_file(path),
            "size": path.stat().st_size,
        }
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    ]


def build(
    config: BuildConfig,
    *,
    runner: Runner = subprocess.run,
    planner: Callable[[str, Mapping[str, str], StandaloneOptions], dict[str, Any]] = generate_plan,
) -> dict[str, Any]:
    """Build and atomically publish one verified standalone overlay."""
    _validate(config)
    source_hashes, physical_snapshot = _snapshot(config)
    config.output.parent.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex
    work = config.output.parent / f".bb-standalone-work-{nonce}"
    stage = config.output.parent / f".bb-standalone-build-{nonce}"
    if work.exists() or stage.exists():
        raise ValueError("refusing to reuse standalone staging paths")
    work.mkdir()
    try:
        item_plan = planner(
            config.seed,
            {
                GAMEPARAM_PATH: source_hashes[GAMEPARAM_PATH],
                PARAMDEF_PATH: source_hashes[PARAMDEF_PATH],
            },
            config.item_options,
        )
        item_plan_path = work / "standalone-item-plan.json"
        _write_json(item_plan_path, item_plan)
        item_binder = work / "gameparam.items.parambnd.dcx"
        item_command = _native_command(config.dotnet, config.item_writer) + [
            "--standalone-items",
            str(item_plan_path),
            str(CATALOG_PATH),
            str(config.gameparam),
            str(config.paramdef),
            str(item_binder),
            "--apply",
        ]
        completed = _run(item_command, runner, capture=True)
        if not item_binder.is_file():
            raise ValueError("standalone item writer produced no parameter archive")
        item_receipt = _parse_writer_receipt(completed.stdout or "")
        _verify_item_receipt(item_receipt, item_plan_path, config.gameparam, item_binder)

        enemy_plan: dict[str, Any] | None = None
        enemy_plan_path: Path | None = None
        enemy_receipt: dict[str, Any] | None = None
        enemy_inventory_path: Path | None = None
        enemy_inventory_sha256: str | None = None
        if config.enemy_options.enabled:
            enemy_seed = config.enemy_options.seed or config.seed
            if config.enemy_inventory is None:
                enemy_inventory_path = work / "msb_enemies.tsv"
                inventory_bytes = read_blob(DEFAULT_BUNDLE, "mined/msb_enemies.tsv")
                enemy_inventory_path.write_bytes(inventory_bytes)
                enemy_inventory_sha256 = hashlib.sha256(inventory_bytes).hexdigest()
            else:
                enemy_inventory_path = config.enemy_inventory
                enemy_inventory_sha256 = _hash_file(config.enemy_inventory)
            enemy_plan_path = work / "standalone-enemy-plan.json"
            planner_command = ([sys.executable, "--internal-enemy-planner"]
                               if getattr(sys, "frozen", False)
                               else [sys.executable, "-m", "tools.bb_enemizer.cli"]) + [
                "--seed",
                enemy_seed,
                "--inventory",
                str(enemy_inventory_path),
                "--tags",
                str(ROOT / "research/enemizer/enemy_tags.json"),
                "--slot-policy",
                str(ROOT / "research/enemizer/slot_policy.json"),
                "--facts",
                str(ROOT / "research/enemizer/archetype_facts.json"),
                "--output",
                str(enemy_plan_path),
            ]
            if config.enemy_options.allow_tier_mixing:
                planner_command.append("--allow-tier-mixing")
            if config.enemy_options.preserve_locomotion:
                planner_command.append("--preserve-locomotion")
            if config.enemy_options.normalize_scaling:
                planner_command.extend(
                    ["--normalize-scaling", "--bundle", str(ROOT / "research/bb_inputs.db")]
                )
            _run(planner_command, runner)
            enemy_plan = _verify_enemy_plan(enemy_plan_path, enemy_seed)
            assert config.maps is not None and config.scripts is not None
            assert config.enemy_writer is not None
            enemy_native = _native_command(config.dotnet, config.enemy_writer)
            if config.enemy_options.normalize_scaling:
                _run(
                    enemy_native
                    + [
                        "--scaled",
                        str(enemy_plan_path),
                        str(item_binder),
                        str(config.paramdef),
                        str(config.maps),
                        str(config.scripts),
                        str(stage),
                        "--apply",
                    ],
                    runner,
                )
                enemy_receipt = _verify_scaling(stage, enemy_plan_path, item_binder)
            else:
                stage.mkdir()
                final_binder = stage / GAMEPARAM_PATH
                final_binder.parent.mkdir(parents=True)
                shutil.copyfile(item_binder, final_binder)
                map_output = stage / MAP_ROOT
                _run(
                    enemy_native
                    + [str(enemy_plan_path), str(config.maps), str(map_output), "--apply"],
                    runner,
                )
                map_files = list(map_output.glob("*.msb.dcx")) if map_output.is_dir() else []
                if not map_files or any(path.is_symlink() for path in map_files):
                    raise ValueError("enemy writer produced no regular compressed map files")
                unexpected = [path for path in map_output.iterdir() if path.is_file() and path not in map_files]
                if unexpected:
                    raise ValueError("enemy writer produced unexpected map files")
                script_output = stage / SCRIPT_ROOT
                _run(
                    enemy_native
                    + [
                        "--ai",
                        str(enemy_plan_path),
                        str(final_binder),
                        str(config.paramdef),
                        str(config.scripts),
                        str(script_output),
                        "--apply",
                    ],
                    runner,
                )
                enemy_receipt = _verify_ai(stage, enemy_plan_path)
            # Native writers place their audit next to script/. Keep it in the
            # build records, outside the game payload consumed by BBLauncher.
            applied_plan = (stage / "bb-enemizer-plan.json"
                            if config.enemy_options.normalize_scaling else enemy_plan_path)
            _verify_ai(stage, applied_plan)
            (stage / "dvdroot_ps4/script.json").rename(stage / "enemy-ai-receipt.json")
        else:
            stage.mkdir()
            final_binder = stage / GAMEPARAM_PATH
            final_binder.parent.mkdir(parents=True)
            shutil.copyfile(item_binder, final_binder)

        if not (stage / GAMEPARAM_PATH).is_file():
            raise ValueError("standalone build produced no composed parameter archive")
        shutil.copyfile(item_plan_path, stage / "standalone-item-plan.json")
        if enemy_plan_path is not None:
            shutil.copyfile(enemy_plan_path, stage / "standalone-enemy-plan.json")
        _write_json(stage / "item-writer-receipt.json", item_receipt)

        tool_hashes = {
            "award_catalog": _hash_file(CATALOG_PATH),
            "item_writer": _hash_file(config.item_writer),
        }
        if config.enemy_options.enabled:
            assert config.enemy_writer is not None
            tool_hashes.update(
                {
                    "enemy_writer": _hash_file(config.enemy_writer),
                    "enemy_inventory": enemy_inventory_sha256,
                }
            )
            if config.enemy_inventory is None:
                tool_hashes["enemy_inventory_bundle"] = _hash_file(DEFAULT_BUNDLE)
        identity = {
            "format": BUILD_FORMAT,
            "seed": config.seed,
            "generator_build": item_plan.get("generator_build"),
            "options": {
                "items": asdict(config.item_options),
                "enemies": asdict(config.enemy_options),
            },
            "source_hashes": source_hashes,
            "tool_hashes": tool_hashes,
            "item_plan_sha256": _hash_file(stage / "standalone-item-plan.json"),
            "enemy_plan_sha256": (
                None
                if enemy_plan_path is None
                else _hash_file(stage / "standalone-enemy-plan.json")
            ),
        }
        _write_json(stage / "standalone-build-identity.json", identity)
        _assert_sources_unchanged(physical_snapshot)
        receipt = {
            "format": RECEIPT_FORMAT,
            "applied": True,
            "identity_sha256": _hash_file(stage / "standalone-build-identity.json"),
            "source_hashes": source_hashes,
            "composed_gameparam_sha256": _hash_file(stage / GAMEPARAM_PATH),
            "item_writer": item_receipt,
            "enemy_writer": enemy_receipt,
            "files": _file_records(stage),
        }
        _write_json(stage / "standalone-build-receipt.json", receipt)
        # A same-parent rename publishes either the complete build or nothing.
        stage.rename(config.output)
        return receipt
    except Exception:
        if stage.is_dir():
            shutil.rmtree(stage)
        raise
    finally:
        if work.is_dir():
            shutil.rmtree(work)


def _parse_args(argv: Sequence[str] | None) -> BuildConfig:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--gameparam", type=Path, required=True)
    parser.add_argument("--paramdef", type=Path, required=True)
    parser.add_argument("--item-writer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dotnet", type=Path)
    parser.add_argument("--include-dlc", action="store_true")
    parser.add_argument("--reduced-item-pool", action="store_true")
    parser.add_argument(
        "--goal",
        choices=("submit_to_gehrman", "refuse_gehrman", "moon_presence"),
        default="moon_presence",
    )
    parser.add_argument("--randomize-enemies", action="store_true")
    parser.add_argument("--enemy-seed")
    parser.add_argument("--maps", type=Path)
    parser.add_argument("--enemy-scripts", type=Path)
    parser.add_argument("--enemy-writer", type=Path)
    parser.add_argument(
        "--enemy-inventory", type=Path,
    )
    parser.add_argument("--allow-tier-mixing", action="store_true")
    parser.add_argument("--preserve-locomotion", action="store_true")
    parser.add_argument("--normalize-enemy-scaling", action="store_true")
    parser.add_argument(
        "--apply", action="store_true", help="write a new verified overlay directory"
    )
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("refusing to build without --apply")
    paths = {
        name: value.resolve()
        for name, value in vars(args).items()
        if isinstance(value, Path)
    }
    return BuildConfig(
        seed=args.seed,
        gameparam=paths["gameparam"],
        paramdef=paths["paramdef"],
        item_writer=paths["item_writer"],
        output=paths["output"],
        dotnet=paths.get("dotnet"),
        item_options=StandaloneOptions(
            include_dlc=args.include_dlc,
            full_item_pool=not args.reduced_item_pool,
            goal=args.goal,
        ),
        enemy_options=EnemyOptions(
            enabled=args.randomize_enemies,
            seed=args.enemy_seed,
            allow_tier_mixing=args.allow_tier_mixing,
            preserve_locomotion=args.preserve_locomotion,
            normalize_scaling=args.normalize_enemy_scaling,
        ),
        maps=paths.get("maps"),
        scripts=paths.get("enemy_scripts"),
        enemy_writer=paths.get("enemy_writer"),
        enemy_inventory=paths.get("enemy_inventory"),
    )


def main(argv: Sequence[str] | None = None) -> int:
    config = _parse_args(argv)
    receipt = build(config)
    print(f"Verified standalone overlay built: {config.output}")
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
