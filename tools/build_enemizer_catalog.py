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

EVENT_REASON = "entity ID referenced by area EMEVD"

# Boss model families that must never enter the ordinary enemy pool, even when
# one of their NpcParam rows passes the hostile-actor gate below. Lady Maria's
# c4520:452091 row reads as an ordinary elite (team 23, npcType 0) but her AI
# does not work outside her own fight.
NON_TARGET_MODELS = {
    "c4520": "Lady Maria: boss AI broken as an ordinary enemy",
}


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


def _write_release_records(args, slots, tags, slot_policy) -> None:
    """Emit per-tranche bb-enemizer-release-v1 records (opt-in, default policy untouched).

    Each record lists logical placements whose blanket exclusion is replaced
    by working compatibility handling (see tools/bb_enemizer/script_contracts.py
    and docs/ENEMIZER-EXPANSION.md). Tranches compose by union at plan time via
    the planner's --release-file. The Cathedral Ward Snatcher progression row
    is excluded from every tranche.
    """
    from collections import defaultdict as _defaultdict
    grouped = _defaultdict(list)
    for slot in slots:
        grouped[slot.logical_key].append(slot)

    census_by_logical: dict[str, list] = _defaultdict(list)
    if args.release_contracts:
        import tempfile as _tempfile
        from build_emevd_entity_usage import build_rows as _build_rows
        with _tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                          encoding="utf-8") as handle:
            json.dump(slot_policy, handle)
            policy_snapshot = Path(handle.name)
        try:
            census = _build_rows(args.inventory, policy_snapshot, args.events, args.lot_items)
        finally:
            policy_snapshot.unlink()
        for row in census:
            census_by_logical[row["logical_key"]].append(row)

    from bb_enemizer.script_contracts import classify_ops, placement_operations

    releases: dict[str, dict[str, dict]] = {"contracts": {}, "spawns": {}, "chara": {}}
    carrier_path = Path(__file__).resolve().parents[1] / "research" / "enemizer" / "quest_drop_carriers.json"
    carriers: set[str] = set()
    if carrier_path.is_file():
        carriers = set(json.loads(carrier_path.read_text(encoding="utf-8")).get("carriers", {}))
    for logical_key in sorted(grouped):
        if logical_key == "m24_00_00_00:c2020_0000":
            continue  # Hypogean Gaol progression contract; never released.
        if logical_key in carriers:
            continue  # Quest-drop carrier: its exact NpcParam row owns a
            # flagged or quest-goods lot the drop rewriter leaves vanilla.
        copies = grouped[logical_key]
        tag = tags.get(copies[0].archetype.key)
        if tag is None or not tag["target"]:
            continue  # Non-enemy or unapproved archetype: correctly out of scope.
        dummy = any(slot.dummy for slot in copies)
        talk = any(slot.talk_id > 0 for slot in copies)
        chara = any(slot.archetype.chara_init_id > 0 for slot in copies)
        broken_model = (
            not copies[0].archetype.model_name.startswith("c")
            or copies[0].archetype.npc_param_id <= 0
            or copies[0].archetype.think_param_id <= 0
        )
        ops: set[str] = set()
        for row in census_by_logical.get(logical_key, []):
            ops |= placement_operations(row["operations"])
        contract, hard, unreviewed = classify_ops(ops)
        detail = {
            "entity_ids": sorted({slot.entity_id for slot in copies}),
            "physical_copies": len(copies),
            "operations": sorted(ops),
            "contract_class": contract,
            "hard_operations": sorted(hard),
            "unreviewed_operations": sorted(unreviewed),
            "other_gates": sorted(
                name for name, present in
                (("dummy", dummy), ("talk", talk), ("chara_init", chara),
                 ("broken_model", broken_model))
                if present
            ),
        }
        override = slot_policy.get(logical_key, {})
        emevd_protected = EVENT_REASON in override.get("reason", "")
        if args.release_contracts and emevd_protected and contract == "supported":
            detail["reason"] = ("EMEVD-protected placement whose script contracts "
                                "are all supported operations")
            releases["contracts"][logical_key] = detail
        # A CharaInit-bound spawn Part also needs the chara tranche; the two
        # gates compose, so neither tranche alone releases it.
        if args.release_script_spawns and dummy and not talk and not broken_model:
            detail["reason"] = ("hostile script-spawn placement; entity ID, part name "
                                "and spawn triggers preserved; size gate bounds overflow")
            releases["spawns"][logical_key] = detail
        if args.release_chara_bound and chara and not talk and not broken_model:
            detail["reason"] = ("hostile CharaInit-bound placement; donor's own "
                                "CharaInit travels with the archetype tuple")
            releases["chara"][logical_key] = detail

    names = {"contracts": args.release_contracts, "spawns": args.release_script_spawns,
             "chara": args.release_chara_bound}
    for tranche, wanted in names.items():
        if not wanted:
            continue
        record = {
            "format": "bb-enemizer-release-v1",
            "tranche": tranche,
            "releases": releases[tranche],
        }
        (args.output / f"release_{tranche}.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"release tranche {tranche}: {len(releases[tranche])} logical placements")


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
    parser.add_argument("--lot-items", type=Path, default=Path("research/joined/lot_items.tsv"))
    parser.add_argument(
        "--relax-non-character-emevd", action="store_true",
        help=(
            "OPT-IN, OFF BY DEFAULT. Narrow EMEVD protection from 'entity id "
            "appears in area EMEVD' to 'entity id is the operand of a character "
            "operation' (see docs/ENEMIZER-COVERAGE.md). Fails closed: a slot is "
            "relaxed only when the reproducible census proves no character "
            "operation touches it, and only if it then still fails no other "
            "conservative gate. The default swap set is unchanged."))
    parser.add_argument(
        "--release-contracts", action="store_true",
        help=("Emit research/enemizer/release_contracts.json: EMEVD-protected "
              "placements whose script contracts are all supported operations "
              "(see tools/bb_enemizer/script_contracts.py). Consumed via the "
              "planner's --release-file; default policy unchanged."))
    parser.add_argument(
        "--release-script-spawns", action="store_true",
        help=("Emit research/enemizer/release_spawns.json: hostile "
              "script-spawn (dummy) placements with no talk binding. Entity "
              "ID, part name and spawn triggers are preserved by the writer; "
              "the size gate bounds spawn-closet overflow. Consumed via "
              "--release-file; default policy unchanged."))
    parser.add_argument(
        "--release-chara-bound", action="store_true",
        help=("Emit research/enemizer/release_chara.json: hostile "
              "CharaInit-bound placements with no talk binding. The donor's "
              "own CharaInit travels with the archetype tuple. Consumed via "
              "--release-file; default policy unchanged."))
    parser.add_argument(
        "--release-wakeup-fallbacks", action="store_true",
        help=("Emit the source-pinned Central Yharnam sleep-to-wake fallback "
              "record; consumed automatically with expanded release options."))
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
        approved = (team == 23 and npc_type == 0 and radius > 0 and height > 0
                    and archetype.model_name not in NON_TARGET_MODELS)
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

    relaxed_non_character = 0
    if args.relax_non_character_emevd:
        # Reproduce the committed EMEVD-usage census over the slot policy we
        # just derived, then drop protection only where NO alternate-state copy
        # of a logical placement is the operand of a character operation. This
        # is the sharper predicate argued in docs/ENEMIZER-COVERAGE.md; it never
        # relaxes a slot a character operation can witness, and the physical
        # gates in classify_slot still guard talk/dummy/hunter/unapproved slots.
        import tempfile as _tempfile
        from build_emevd_entity_usage import build_rows, has_character_operation
        with _tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                          encoding="utf-8") as handle:
            json.dump(slot_policy, handle)
            policy_snapshot = Path(handle.name)
        try:
            census = build_rows(args.inventory, policy_snapshot, args.events, args.lot_items)
        finally:
            policy_snapshot.unlink()
        character_logical = {
            row["logical_key"] for row in census
            if has_character_operation(row["usage_classes"])
        }
        for key in list(slot_policy):
            if (slot_policy[key].get("reason") == EVENT_REASON
                    and key not in character_logical):
                del slot_policy[key]
                relaxed_non_character += 1

    args.output.mkdir(parents=True, exist_ok=True)
    if args.release_contracts or args.release_script_spawns or args.release_chara_bound:
        _write_release_records(args, slots, tags, slot_policy)
    if args.release_wakeup_fallbacks:
        from bb_enemizer.wakeup_fallback import build_release
        wakeup = build_release(args.events)
        (args.output / "release_wakeup.json").write_text(
            json.dumps(wakeup, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n")
    (args.output / "enemy_tags.json").write_text(
        json.dumps(tags, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    (args.output / "slot_policy.json").write_text(
        json.dumps(slot_policy, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "physical_slots": len(slots),
        "archetypes": len(tags),
        "approved_archetypes": sum(tag["target"] for tag in tags.values()),
        "tiers": dict(Counter(tag["tier"] for tag in tags.values())),
        "sizes": dict(Counter(tag["size_class"] for tag in tags.values())),
        "scaling_hp_values": dict(sorted(Counter(
            str(tag.get("scaling_hp", 1.0)) for tag in tags.values()).items(), key=lambda x: float(x[0]))),
        "event_referenced_physical_sightings": event_referenced,
        "relax_non_character_emevd": bool(args.relax_non_character_emevd),
        "relaxed_non_character_logical_slots": relaxed_non_character,
        "protected_logical_slots": len(slot_policy),
        "emevd_covered_areas": sorted(covered_areas),
        "inventory_areas_without_emevd": sorted({
            slot.map_name.split("_", 1)[0] for slot in slots
        } - covered_areas),
        "unknown_npc_param_ids": sorted(set(unknown_npcs)),
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
