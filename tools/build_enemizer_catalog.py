#!/usr/bin/env python3
"""Derive conservative Bloodborne enemizer metadata from params and events."""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from bb_enemizer.inventory import load_slots


NUMBER = re.compile(r"(?<!\d)\d{6,9}(?!\d)")


def rows(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def size_class(radius: float, height: float) -> str:
    # Collider-derived, intentionally asymmetric with the planner's size gate.
    # Use the larger of radius and height buckets so tall/thin enemies do not
    # masquerade as small merely because their capsule is narrow.
    radius_limits = (0.15, 0.3, 0.5, 0.8, 1.2, 2.0)
    height_limits = (0.6, 1.2, 2.0, 3.0, 4.5, 6.0)
    labels = ("XS", "S", "M", "L", "XL", "XXL", "GIGA")
    rb = next((i for i, limit in enumerate(radius_limits) if radius <= limit), 6)
    hb = next((i for i, limit in enumerate(height_limits) if height <= limit), 6)
    return labels[max(rb, hb)]


def tier(row: dict, radius: float) -> str:
    hp = int(row.get("hp") or 0)
    souls = int(row.get("getSoul") or 0)
    no_respawn = row.get("disableRespawn") == "1"
    if no_respawn and (hp >= 1000 or souls >= 10000 or radius >= 1.2):
        return "boss"
    if no_respawn or hp >= 700 or souls >= 3000 or radius >= 1.0:
        return "elite"
    return "common"


def event_numbers(event_root: Path) -> tuple[dict[str, set[int]], set[str]]:
    by_area: dict[str, set[int]] = defaultdict(set)
    covered: set[str] = set()
    # Fixed-map scripts live at the event root. Recursive traversal descends
    # into thousands of Chalice-template scripts, which are out of scope for
    # the fixed-map catalog and turn a sub-second evidence pass into minutes.
    for path in event_root.glob("*.emevd.dcx.js"):
        name = path.name.split(".", 1)[0]
        if not name.startswith("m"):
            continue
        area = name.split("_", 1)[0]
        covered.add(area)
        text = path.read_text(encoding="utf-8", errors="replace")
        by_area[area].update(map(int, NUMBER.findall(text)))
    return by_area, covered


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=Path("research/mined/msb_enemies.tsv"))
    parser.add_argument("--npc-param", type=Path, default=Path(
        "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE/install/CUSA03173/"
        "dvdroot_ps4/params_dump/NpcParam.csv"))
    parser.add_argument("--speffect-param", type=Path, default=Path(
        "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE/install/CUSA03173/"
        "dvdroot_ps4/params_dump/SpEffectParam.csv"))
    parser.add_argument("--events", type=Path, default=Path(
        "Bloodborne.Game.of.the.Year.Edition.PS4-PRELUDE/bloodborne_artifacts/event"))
    parser.add_argument("--output", type=Path, default=Path("research/enemizer"))
    args = parser.parse_args()

    slots = load_slots(args.inventory)
    npcs = {int(row["ID"]): row for row in rows(args.npc_param)}
    effects = {int(row["ID"]): row for row in rows(args.speffect_param)}
    archetypes = {slot.archetype.key: slot.archetype for slot in slots}
    placements_by_archetype = Counter(slot.archetype.key for slot in slots)
    tags = {}
    unknown_npcs = []
    for key, archetype in sorted(archetypes.items()):
        row = npcs.get(archetype.npc_param_id)
        if row is None:
            unknown_npcs.append(archetype.npc_param_id)
            tags[key] = {
                "size_class": "unknown", "tier": "common", "locomotion": "unknown",
                "target": False, "notes": "NPCParam row missing",
            }
            continue
        radius = float(row.get("hitRadius") or 0)
        height = float(row.get("hitHeight") or 0)
        team = int(row.get("teamType") or 0)
        npc_type = int(row.get("npcType") or 0)
        approved = team == 23 and npc_type == 0 and radius > 0 and height > 0
        scaling_rows = []
        for index in range(8):
            effect_id = int(row.get(f"spEffectID{index}") or 0)
            effect = effects.get(effect_id)
            if effect is None or not 7000 <= effect_id < 7300:
                continue
            if (effect.get("spCategory") == "0"
                    and float(effect.get("effectEndurance") or 0) == -1
                    and float(effect.get("physicsAttackRate") or 0) == 1):
                scaling_rows.append((float(effect.get("maxHpRate") or 1), effect_id))
        scaling_hp, scaling_id = max(scaling_rows, default=(1.0, 0))
        tags[key] = {
            "size_class": size_class(radius, height),
            "tier": tier(row, radius),
            "locomotion": f"move_type_{row.get('moveType') or 'unknown'}",
            "scaling_hp": scaling_hp,
            "target": approved,
            "notes": (
                f"NpcParam {archetype.npc_param_id}; hp={row.get('hp')}; "
                f"radius={radius:g}; height={height:g}; team={team}; npcType={npc_type}; "
                f"disableRespawn={row.get('disableRespawn')}; scalingEffect={scaling_id}; "
                f"scalingHp={scaling_hp:g}; placements={placements_by_archetype[key]}"
            ),
        }

    numbers_by_area, covered_areas = event_numbers(args.events)
    slot_policy = {}
    event_referenced = 0
    for slot in slots:
        area = slot.map_name.split("_", 1)[0]
        if area not in covered_areas:
            slot_policy[slot.logical_key] = {
                "randomize": False,
                "reason": "no fixed-map EMEVD coverage for area",
            }
            continue
        if slot.entity_id <= 0:
            continue
        if slot.entity_id in numbers_by_area.get(area, set()):
            slot_policy[slot.logical_key] = {
                "randomize": False,
                "reason": "entity ID referenced by area EMEVD",
            }
            event_referenced += 1

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "enemy_tags.json").write_text(
        json.dumps(tags, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.output / "slot_policy.json").write_text(
        json.dumps(slot_policy, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = {
        "physical_slots": len(slots),
        "archetypes": len(tags),
        "approved_archetypes": sum(tag["target"] for tag in tags.values()),
        "tiers": dict(Counter(tag["tier"] for tag in tags.values())),
        "sizes": dict(Counter(tag["size_class"] for tag in tags.values())),
        "scaling_hp_values": dict(sorted(Counter(
            str(tag.get("scaling_hp", 1.0)) for tag in tags.values()).items(), key=lambda x: float(x[0]))),
        "event_referenced_physical_sightings": event_referenced,
        "protected_logical_slots": len(slot_policy),
        "emevd_covered_areas": sorted(covered_areas),
        "inventory_areas_without_emevd": sorted({
            slot.map_name.split("_", 1)[0] for slot in slots
        } - covered_areas),
        "unknown_npc_param_ids": sorted(set(unknown_npcs)),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
