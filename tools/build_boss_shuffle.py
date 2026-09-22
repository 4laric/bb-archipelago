#!/usr/bin/env python3
"""Build the one hand-verified boss-shuffle canary from a reviewed draft plan.

This is a developer build path.  It deliberately accepts only the currently
registered ``bsb-at-cleric-v1`` adapter: a draft plan is evidence for that
adapter, not a generic native event recipe.  The draft is regenerated from the
committed inputs before any writer is launched, and the native overlay is
verified before it is published.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bb_enemizer.boss_canary import ADAPTER, DESTINATION_EVENT_FILE, plan_canary
from tools.bb_enemizer.boss_shuffle import plan_boss_shuffle
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_inputs import DEFAULT_BUNDLE, read_blob
from tools.build_boss_catalog import build as build_catalog
from tools.verify_boss_canary import verify


def _load_inventory(bundle: Path):
    """Load the bundled miner inventory without trusting a user-provided TSV."""
    with tempfile.TemporaryDirectory(prefix="bb-boss-shuffle-input-") as temporary:
        inventory = Path(temporary) / "msb_enemies.tsv"
        inventory.write_bytes(read_blob(bundle, "mined/msb_enemies.tsv"))
        return load_slots(inventory)


def regenerate_draft(bundle: Path, seed: str) -> tuple[dict, dict]:
    """Return independent draft and native plans from the pinned input bundle."""
    slots = _load_inventory(bundle)
    npcs, effects = load_params(bundle)
    draft = plan_boss_shuffle(seed, slots, npcs, effects, build_catalog(bundle))
    native = plan_canary(slots, npcs, effects)
    native["seed"] = seed
    return draft, native


def checked_native_plan(draft_path: Path, bundle: Path) -> dict:
    """Reject every draft except the exact canary plan regenerated from inputs."""
    try:
        submitted = json.loads(draft_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read draft boss shuffle plan: {error}") from error
    if not isinstance(submitted, dict):
        raise ValueError("draft boss shuffle plan must be a JSON object")
    if submitted.get("format") != "bb-enemizer-boss-shuffle-plan-v1":
        raise ValueError("unsupported draft boss shuffle plan format")
    seed = submitted.get("seed")
    if not isinstance(seed, str) or not seed:
        raise ValueError("draft boss shuffle plan requires a non-empty string seed")

    canonical, native = regenerate_draft(bundle, seed)
    if submitted != canonical:
        raise ValueError("draft boss shuffle plan differs from the canonical bundle result")
    templates = canonical.get("templates_planned", canonical.get("templates_applied"))
    if (canonical.get("status") not in (None, "planned")
            or templates != [ADAPTER]
            or canonical.get("template_failures")
            or canonical.get("swap_count") != 1
            or len(canonical.get("swaps", [])) != 1
            or canonical["swaps"][0].get("template") != ADAPTER):
        raise ValueError("draft does not select the supported native boss adapter")
    return native


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def check_output(output: Path, inputs: tuple[Path, ...]) -> None:
    if output.exists():
        raise ValueError("output must not exist")
    for item in inputs:
        parent = item if item.is_dir() else item.parent
        if _is_under(output, parent):
            raise ValueError("output must be outside input directories: " + str(parent))


def build(args) -> dict:
    """Write, verify, then atomically publish a native canary overlay."""
    native = checked_native_plan(args.plan, args.bundle)
    inputs = (args.plan, args.bundle, args.writer, args.gameparam, args.paramdef,
              args.maps, args.scripts, args.event)
    check_output(args.output, inputs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    stage = args.output.parent / (".bb-boss-shuffle-" + uuid.uuid4().hex)
    if stage.exists():  # UUID collision is fantastically unlikely, but never reuse output.
        raise ValueError("refusing to reuse build staging directory")
    try:
        with tempfile.TemporaryDirectory(prefix="bb-boss-shuffle-plan-") as temporary:
            native_path = Path(temporary) / "bb-enemizer-plan.json"
            native_path.write_text(json.dumps(native, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            command = ([str(args.dotnet)] if args.dotnet else []) + [
                str(args.writer), "--boss-native", str(native_path), str(args.gameparam),
                str(args.paramdef), str(args.maps), str(args.scripts), str(args.event),
                str(stage), "--apply",
            ]
            subprocess.run(command, check=True)
        result = verify(stage)
        # The final name is still absent (checked before any writes), and stage
        # shares its parent, so this is a single-filesystem publication step.
        stage.replace(args.output)
        return result
    except Exception:
        if stage.is_dir():
            shutil.rmtree(stage)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "writer", "gameparam", "paramdef", "maps", "scripts", "event", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--dotnet", type=Path, help="optional dotnet host for a writer DLL")
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--apply", action="store_true", help="write a verified developer overlay")
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error("refusing to build without --apply")
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    result = build(args)
    print("Verified experimental boss overlay built: " + str(args.output))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
