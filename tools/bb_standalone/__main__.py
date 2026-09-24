"""Command-line entry point for standalone item plan generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generate import StandaloneOptions, generate_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--source-hashes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-dlc", action="store_true")
    parser.add_argument(
        "--goal",
        choices=("submit_to_gehrman", "refuse_gehrman", "moon_presence"),
        default="moon_presence",
    )
    parser.add_argument("--reduced-item-pool", action="store_true")
    args = parser.parse_args()
    hashes = json.loads(args.source_hashes.read_text(encoding="utf-8-sig"))
    plan = generate_plan(
        args.seed,
        hashes,
        StandaloneOptions(
            include_dlc=args.include_dlc,
            full_item_pool=not args.reduced_item_pool,
            goal=args.goal,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"placements={len(plan['placements'])} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
