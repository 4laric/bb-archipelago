#!/usr/bin/env python3
"""Reproducible protection/exclusion audit census for the Bloodborne enemizer.

Reads only committed inputs (research/bb_inputs.db, research/enemizer/*) and
emits research/enemizer/protection_audit.json: per-logical-placement records
with EVERY applicable exclusion gate (not just the first-hit reason the
planner reports), per-map coverage tables, the Central Yharnam case-study
numbers, and the EMEVD-resolution breakdown from the committed census.

No game dump is required. This tool changes no policy; it reports.
"""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

try:
    from .bb_enemizer.inventory import (
        apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
    )
    from .bb_enemizer.model import canonical_map
    from .bb_enemizer.planner import EnemizerConfig, plan_swaps
    from .build_emevd_entity_usage import has_character_operation, materialize_bundle
except ImportError:  # Direct script execution.
    from bb_enemizer.inventory import (
        apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
    )
    from bb_enemizer.model import canonical_map
    from bb_enemizer.planner import EnemizerConfig, plan_swaps
    from build_emevd_entity_usage import has_character_operation, materialize_bundle

EVENT_REASON = "entity ID referenced by area EMEVD"
GATES = (
    "emevd_override", "dummy", "talk", "chara_init", "nonchar_model",
    "missing_npc_think", "unapproved_archetype", "variant_disagreement",
)


def all_gates(copies, overrides, tags) -> set[str]:
    """Every independently applicable exclusion gate for one logical placement."""
    gates: set[str] = set()
    for slot in copies:
        if EVENT_REASON in (overrides.get(slot.key) or overrides.get(slot.logical_key) or {}).get("reason", ""):
            gates.add("emevd_override")
        if slot.dummy:
            gates.add("dummy")
        if slot.talk_id > 0:
            gates.add("talk")
        if slot.archetype.chara_init_id > 0:
            gates.add("chara_init")
        if not slot.archetype.model_name.startswith("c"):
            gates.add("nonchar_model")
        if slot.archetype.npc_param_id <= 0 or slot.archetype.think_param_id <= 0:
            gates.add("missing_npc_think")
    tag = tags.get(copies[0].archetype.key)
    if tag is not None and not tag.target:
        gates.add("unapproved_archetype")
    if len({slot.archetype.key for slot in copies}) > 1:
        gates.add("variant_disagreement")
    return gates


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("research/bb_inputs.db"))
    parser.add_argument("--census", type=Path, default=Path("research/enemizer/emevd_entity_usage.tsv"))
    parser.add_argument("--slot-policy", type=Path, default=Path("research/enemizer/slot_policy.json"))
    parser.add_argument("--tags", type=Path, default=Path("research/enemizer/enemy_tags.json"))
    parser.add_argument("--seed", default="12345")
    parser.add_argument("--output", type=Path, default=Path("research/enemizer/protection_audit.json"))
    args = parser.parse_args(argv)

    temporary = tempfile.TemporaryDirectory()
    try:
        inventory, _events = materialize_bundle(args.bundle, Path(temporary.name))
        slots = load_slots(inventory)
    finally:
        temporary.cleanup()
    tags = load_tags(args.tags)
    overrides = load_slot_overrides(args.slot_policy)
    census = {
        row["logical_key"]: row for row in
        csv.DictReader(args.census.open(encoding="utf-8-sig", newline=""), delimiter="\t")
    }

    grouped: dict[str, list] = defaultdict(list)
    for slot in slots:
        grouped[slot.logical_key].append(slot)
    policies = {
        slot.key: apply_archetype_tag(classify_slot(slot, overrides), tags.get(slot.archetype.key))
        for slot in slots
    }
    swaps, rejections = plan_swaps(slots, policies, tags, EnemizerConfig(args.seed))
    swapped = {swap.logical_key for swap in swaps}
    first_hit = {row["logical_key"]: row["reason"] for row in rejections}

    placements = []
    for logical_key in sorted(grouped):
        copies = grouped[logical_key]
        gates = sorted(all_gates(copies, overrides, tags))
        placements.append({
            "logical_key": logical_key,
            "canonical_map": canonical_map(copies[0].map_name),
            "physical_copies": len(copies),
            "entity_ids": sorted({copy.entity_id for copy in copies}),
            "source_archetypes": sorted({copy.archetype.key for copy in copies}),
            "all_gates": gates,
            "first_hit_reason": first_hit.get(logical_key),
            "swapped": logical_key in swapped,
        })
    # Attach logical-level EMEVD rollups from the census (physical rows grouped).
    census_by_logical: dict[str, list] = defaultdict(list)
    for row in csv.DictReader(args.census.open(encoding="utf-8-sig", newline=""), delimiter="\t"):
        census_by_logical[row["logical_key"]].append(row)
    for placement in placements:
        rows = census_by_logical.get(placement["logical_key"], [])
        placement["emevd"] = {
            "protected_copies": len(rows),
            "any_character_operation": any(has_character_operation(r["usage_classes"]) for r in rows),
            "any_unresolved_reference": any("unresolved_event_reference:" in r["usage_classes"] for r in rows),
            "usage_classes": sorted({row["usage_classes"] for row in rows}),
        } if rows else None

    def per_map(key_fn):
        table = {}
        for placement in placements:
            table.setdefault(key_fn(placement), {"logical": 0, "swapped": 0, "gates": Counter()})
            entry = table[key_fn(placement)]
            entry["logical"] += 1
            entry["swapped"] += placement["swapped"]
            for gate in placement["all_gates"]:
                entry["gates"][gate] += 1
        return {name: {"logical": v["logical"], "swapped": v["swapped"],
                       "gate_hits": dict(sorted(v["gates"].items()))}
                for name, v in sorted(table.items())}

    central = [p for p in placements if p["canonical_map"] == "m24_01_00_00"]
    report = {
        "format": "bb-enemizer-protection-audit-v1",
        "seed": args.seed,
        "denominators": {
            "physical_slots": len(slots),
            "logical_placements": len(grouped),
            "logical_swaps": len(swapped),
            "logical_rejections": len(first_hit),
        },
        "gate_overlap": {"+".join(k) or "(eligible)": v for k, v in sorted(
            Counter(tuple(p["all_gates"]) for p in placements).items(), key=lambda kv: str(kv[0]))},
        "per_area": per_map(lambda p: p["canonical_map"].split("_")[0]),
        "per_canonical_map": per_map(lambda p: p["canonical_map"]),
        "central_yharnam_m24_01": {
            "logical": len(central),
            "swapped": sum(p["swapped"] for p in central),
            "first_hit": dict(sorted(Counter(
                p["first_hit_reason"] for p in central if not p["swapped"]).items())),
            "multi_gate_overlap": sum(
                1 for p in central if len(p["all_gates"]) > 1),
        },
        "placements": placements,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "placements"}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
