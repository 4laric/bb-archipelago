#!/usr/bin/env python3
"""Offline release gate for Bloodborne enemizer manifests."""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
)
from bb_enemizer.model import SIZE_CLASSES
from bb_enemizer.planner import EnemizerConfig, plan_swaps


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=25)
    ap.add_argument("--inventory", type=Path, default=Path("research/mined/msb_enemies.tsv"))
    ap.add_argument("--tags", type=Path, default=Path("research/enemizer/enemy_tags.json"))
    ap.add_argument("--slot-policy", type=Path, default=Path("research/enemizer/slot_policy.json"))
    ap.add_argument("--chr", type=Path, default=Path(
        "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE/install/CUSA03173/dvdroot_ps4/chr"))
    ap.add_argument("--output", type=Path, default=Path("research/enemizer/audit.json"))
    ns = ap.parse_args()

    slots = load_slots(ns.inventory)
    tags = load_tags(ns.tags)
    overrides = load_slot_overrides(ns.slot_policy)
    policies = {slot.key: apply_archetype_tag(
        classify_slot(slot, overrides), tags.get(slot.archetype.key)) for slot in slots}
    by_key = {slot.key: slot for slot in slots}

    approved_models = {slot.archetype.model_name for slot in slots
                       if tags.get(slot.archetype.key) and tags[slot.archetype.key].target}
    asset_missing = {}
    for model in sorted(approved_models):
        missing = []
        if not (ns.chr / f"{model}.chrbnd.dcx").is_file():
            missing.append(".chrbnd.dcx")
        # Bloodborne's cXXX1 model variants intentionally share the cXXX0
        # animation binder. Treat that explicit sibling as the only fallback;
        # broader prefix guessing would hide genuinely missing assets.
        animation = ns.chr / f"{model}.anibnd.dcx"
        shared_animation = ns.chr / f"{model[:-1]}0.anibnd.dcx"
        if not animation.is_file() and not shared_animation.is_file():
            missing.append(".anibnd.dcx")
        if missing:
            asset_missing[model] = missing

    failures = []
    swap_counts = []
    family_counts = Counter()
    large_by_map_peak = Counter()
    for seed_index in range(ns.seeds):
        seed = f"offline-audit-{seed_index}"
        config = EnemizerConfig(seed)
        swaps, _ = plan_swaps(slots, policies, tags, config)
        repeat, _ = plan_swaps(list(reversed(slots)), policies, tags, config)
        if [swap.json() for swap in swaps] != [swap.json() for swap in repeat]:
            failures.append(f"seed {seed}: non-deterministic plan")
        swap_counts.append(len(swaps))
        per_map_large = Counter()
        for swap in swaps:
            if swap.source.model_name == swap.target.model_name:
                failures.append(f"{seed}:{swap.logical_key}: same-model swap")
            tag = tags.get(swap.target.key)
            if tag is None or not tag.target:
                failures.append(f"{seed}:{swap.logical_key}: unapproved target")
                continue
            family_counts[swap.target.model_name] += 1
            if SIZE_CLASSES.index(tag.size_class) >= SIZE_CLASSES.index("L"):
                for destination in swap.destination_keys:
                    per_map_large[by_key[destination].map_name] += 1
        for map_name, count in per_map_large.items():
            large_by_map_peak[map_name] = max(large_by_map_peak[map_name], count)

    report = {
        "seeds": ns.seeds,
        "failures": failures,
        "asset_missing": asset_missing,
        "swap_count_range": [min(swap_counts), max(swap_counts)] if swap_counts else [0, 0],
        "distinct_target_families": len(family_counts),
        "target_family_counts": dict(family_counts.most_common()),
        "peak_large_physical_targets_by_map": dict(large_by_map_peak.most_common()),
    }
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("target_family_counts", "peak_large_physical_targets_by_map")},
                     indent=2, sort_keys=True))
    return 1 if failures or asset_missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
