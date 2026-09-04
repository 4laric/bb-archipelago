from __future__ import annotations

import argparse
import json
from pathlib import Path

from .inventory import (
    apply_archetype_tag,
    classify_slot,
    inventory_summary,
    load_facts,
    load_slot_overrides,
    load_slots,
    load_tags,
)
from .planner import EnemizerConfig, StressProfile, plan_swaps
from .scaling import load_params, plan_scaling


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
    result.add_argument("--facts", default="research/enemizer/archetype_facts.json",
                        help="per-NpcParam name/echo/HP facts stamped into every swap "
                             "for the player-facing enemy report (default: generated table)")
    result.add_argument("--output", required=True, help="manifest JSON path")
    result.add_argument("--allow-tier-mixing", action="store_true")
    result.add_argument("--preserve-locomotion", action="store_true")
    result.add_argument(
        "--normalize-scaling", action="store_true",
        help="emit inferred static-scaling clones (experimental; off by default)",
    )
    result.add_argument("--bundle", default="research/bb_inputs.db")
    return result


def _stress_matched(stress: StressProfile, swap) -> bool:
    if stress.kind == "family":
        return swap.target.model_name == stress.argument
    if stress.kind == "locomotion":
        return swap.source_tag.get("locomotion") != swap.target_tag.get("locomotion")
    if stress.kind == "size-up":
        return any(note.startswith("size-up") for note in swap.warnings)
    if stress.kind == "size-down":
        return swap.source_tag.get("size_class") != swap.target_tag.get("size_class")
    if stress.kind == "tier-up":
        return swap.source_tag.get("tier") != swap.target_tag.get("tier")
    if stress.kind == "echoes":
        return swap.target_facts.get("echoes", 0) > swap.source_facts.get("echoes", 0)
    return False


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
    try:
        stress = StressProfile.parse(args.seed)
    except ValueError as exc:
        raise SystemExit(str(exc))
    slots = load_slots(args.inventory)
    facts = load_facts(args.facts if Path(args.facts).is_file() else None)
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
    swaps, rejections = plan_swaps(slots, policies, tags, config, facts)
    scaling, scaling_skips = [], []
    if args.normalize_scaling:
        npcs, effects = load_params(Path(args.bundle))
        scaling, scaling_skips = plan_scaling(swaps, slots, npcs, effects)
    payload = {
        "format": "bb-enemizer-plan-v2",
        "seed": args.seed,
        "dry_run": True,
        "inventory": inventory_summary(slots, policies),
        "options": {
            "allow_tier_mixing": bool(args.allow_tier_mixing),
            "preserve_locomotion": bool(args.preserve_locomotion),
        },
        "stress": None if stress is None else {
            **stress.json(),
            # How many swaps actually embody the profile, so a tester can see
            # at a glance that e.g. a family was never compatible in the focus.
            "matched": sum(1 for swap in swaps if _stress_matched(stress, swap)),
        },
        "swap_count": len(swaps),
        "rejection_count": len(rejections),
        "swaps": [swap.json() for swap in swaps],
        "rejections": rejections,
        "scaling": {
            "enabled": bool(args.normalize_scaling),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(scaling),
            "skip_count": len(scaling_skips),
            "changes": [change.json() for change in scaling],
            "skips": scaling_skips,
        },
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
