from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inventory import (
    apply_archetype_tag,
    classify_slot,
    inventory_summary,
    load_slot_overrides,
    load_slots,
    load_tags,
)
from .planner import EnemizerConfig, plan_swaps


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Build a deterministic Bloodborne enemy swap manifest (no game files are written)."
    )
    result.add_argument("--inventory", default="research/mined/msb_enemies.tsv")
    seed = result.add_mutually_exclusive_group(required=True)
    seed.add_argument("--seed")
    seed.add_argument("--ap-request",
                      help="bb-seed-request-v1 (or legacy bb-enemizer-request-v1) emitted by the Bloodborne apworld")
    result.add_argument("--tags", default="research/enemizer/enemy_tags.json",
                        help="archetype-tag JSON (default: generated research catalog)")
    result.add_argument("--slot-policy", default="research/enemizer/slot_policy.json",
                        help="per-slot policy JSON (default: generated research catalog)")
    result.add_argument("--output", required=True, help="manifest JSON path")
    result.add_argument("--allow-tier-mixing", action="store_true")
    result.add_argument("--preserve-locomotion", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.ap_request:
        request = json.loads(Path(args.ap_request).read_text(encoding="utf-8"))
        if request.get("format") not in ("bb-seed-request-v1", "bb-enemizer-request-v1"):
            raise SystemExit("invalid AP seed request format")
        # Whether enemies are randomized is a launch-time decision
        # (bb-archipelago#150): the request seeds the planner, it does not
        # authorize it. Legacy requests still carry an `enemizer` flag; it is
        # deliberately ignored.
        args.seed = str(request["enemizer_seed"])
    slots = load_slots(args.inventory)
    tags_path = args.tags if Path(args.tags).is_file() else None
    policy_path = args.slot_policy if Path(args.slot_policy).is_file() else None
    tags = load_tags(tags_path)
    overrides = load_slot_overrides(policy_path)
    policies = {
        slot.key: apply_archetype_tag(
            classify_slot(slot, overrides), tags.get(slot.archetype.key)
        )
        for slot in slots
    }
    config = EnemizerConfig(
        seed=args.seed,
        preserve_tier=not args.allow_tier_mixing,
        preserve_locomotion=args.preserve_locomotion,
    )
    swaps, rejections = plan_swaps(slots, policies, tags, config)
    payload = {
        "format": "bb-enemizer-plan-v2",
        "seed": args.seed,
        "dry_run": True,
        "inventory": inventory_summary(slots, policies),
        "swap_count": len(swaps),
        "rejection_count": len(rejections),
        "swaps": [swap.json() for swap in swaps],
        "rejections": rejections,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"slots={len(slots)} logical={payload['inventory']['logical_slots']} "
        f"swaps={len(swaps)} protected_or_rejected={len(rejections)} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
