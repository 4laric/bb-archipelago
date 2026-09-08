"""Seed-owned, local enemy-drop rewrites (never AP locations).

Version 1 permuted whole vanilla loot tables. That did almost nothing: of the
73 eligible tables, 35.0% of the field-weighted contents were Blood Vials and
20.9% Quicksilver Bullets, so a permutation mostly swapped one vial table for
another ("the only difference is 5x vials and 3x bullets", player report,
2026-09-07).

Version 2 rewrites table *contents* instead. Every eligible NPC drop field,
including the 65 whose vanilla table is empty, gets a brand new ItemLotParam
row in a reserved band; `NpcParam.itemLotId_N` is repointed at it. Vanilla rows
are never edited, because fixed treasure and the vanilla suppression plan own
many of them.

Slot semantics, measured from the committed CUSA03173 01.09 params (see
`tools/build_enemy_drop_catalog.py`): the eight slots of an ItemLotParam row
are ONE weighted pick. `lotItemBasePoint01..08` sums to 1000 on 267 of the 329
distinct enemy lots, the "nothing" outcome is an explicit `lotItemCategory=-1`
slot, and a slot's drop chance is `basePoint / sum(basePoint)`. So a rewritten
row carries its own nothing slot and its base points come from a cadence shape
a real vanilla enemy already uses -- either the field's own, or one drawn from
the catalog's observed profiles. Farm rates therefore stay in vanilla range by
construction rather than by estimate.
"""
from __future__ import annotations

import json
from random import Random
from typing import Any

from .resource_data import read_resource_text

PLAN_FORMAT = "bb-enemy-drop-plan-v2"

#: Item classes each mode may draw from. `balanced` stays consumables-only, the
#: unchanged policy; `dropsanity` widens to repeatable upgrade materials,
#: Coldblood denominations, and the blood-gem recipes vanilla enemies already
#: drop. Everything else -- equipment, runes, keys, badges, flagged rewards --
#: stays excluded in both.
MODE_POOLS = {
    "balanced": ("consumables",),
    "dropsanity": ("consumables", "materials", "coldblood", "gems"),
}

#: At most one blood-gem slot per rewritten table, and it always lands in the
#: rarest slot of the cadence. Without this the 28-recipe gem pool would put a
#: gem in a third of every table's slots.
MAX_GEM_SLOTS = 1


def enemy_drop_catalog() -> dict[str, Any]:
    value = json.loads(read_resource_text("enemy_drop_catalog.json"))
    if value.get("format") != "bb-enemy-drop-catalog-v2":
        raise ValueError("unsupported enemy-drop catalog")
    return value


def _weighted_pick(random: Random, entries: list[dict[str, Any]]) -> dict[str, Any]:
    total = sum(int(entry["weight"]) for entry in entries)
    roll = random.randrange(total)
    for entry in entries:
        roll -= int(entry["weight"])
        if roll < 0:
            return entry
    return entries[-1]


def _weighted_sample(
    random: Random, entries: list[dict[str, Any]], count: int
) -> list[dict[str, Any]]:
    """Deterministic weighted draw of distinct kinds, uniform within a class."""
    remaining = list(entries)
    picked: list[dict[str, Any]] = []
    for _ in range(min(count, len(remaining))):
        choice = _weighted_pick(random, remaining)
        picked.append(choice)
        remaining = [entry for entry in remaining if entry is not choice]
    return picked


def _cadence_for(
    random: Random, catalog: dict[str, Any], field: dict[str, Any]
) -> dict[str, Any]:
    """Reuse the field's own vanilla chance/quantity shape when it has one."""
    vanilla = field["vanilla"]
    if vanilla["populated"]:
        return {
            "total_points": vanilla["total_points"],
            "empty_points": vanilla["empty_points"],
            "slots": vanilla["slots"],
        }
    counts = catalog["cadence"]["slot_count_weights"]
    buckets = [{"count": key, "weight": weight} for key, weight in sorted(counts.items())]
    bucket = _weighted_pick(random, buckets)["count"]
    return _weighted_pick(random, catalog["cadence"]["profiles"][bucket])


def build_enemy_drop_assignments(
    seed: str, mode: str = "balanced"
) -> list[dict[str, Any]]:
    """Rewrite every eligible enemy drop table for one seed and mode."""

    if mode not in MODE_POOLS:
        raise ValueError(f"unsupported enemy-drop mode: {mode}")

    catalog = enemy_drop_catalog()
    pools = catalog["pools"]
    gem_ids = {int(entry["item_id"]): entry for entry in pools["gems"]}
    goods_pool = [
        entry
        for name in MODE_POOLS[mode]
        if name != "gems"
        for entry in pools[name]
    ]
    density = float(catalog["density"]["vanilla_populated_fraction"])

    assignments: list[dict[str, Any]] = []
    for field in catalog["fields"]:
        npc_id = int(field["npc_param_id"])
        drop_field = str(field["drop_field"])
        random = Random(
            f"bloodborne-enemy-drops:v2:{mode}:{seed}:{npc_id}:{drop_field}"
        )
        vanilla_populated = bool(field["vanilla"]["populated"])
        # One roll per field at the vanilla populated share, so empty tables
        # gain drops at the same rate populated ones lose them and the total
        # drop density stays where vanilla put it.
        populated = random.random() < density
        if not populated and not vanilla_populated:
            continue

        slots: list[dict[str, Any]] = []
        if populated:
            cadence = _cadence_for(random, catalog, field)
            shape = list(cadence["slots"])
            # `gems` is a per-field pool: only the recipes an enemy in this
            # archetype's own map already drops (see the catalog's gem tier).
            pool = list(goods_pool)
            if "gems" in MODE_POOLS[mode]:
                pool += [
                    gem_ids[recipe]
                    for recipe in field["gem_recipes"]
                    if recipe in gem_ids
                ]
            kinds = _weighted_sample(random, pool, len(shape))
            gems = [entry for entry in kinds if entry["class"] == "gem"]
            if len(gems) > MAX_GEM_SLOTS:
                keep = gems[0]
                replacements = _weighted_sample(
                    random,
                    [entry for entry in goods_pool if entry not in kinds],
                    len(gems) - MAX_GEM_SLOTS,
                )
                kinds = [
                    entry for entry in kinds if entry["class"] != "gem" or entry is keep
                ] + replacements
            # The rarest slot of the cadence carries the gem, if one was drawn.
            order = sorted(range(len(shape)), key=lambda index: shape[index]["points"])
            gem_slot = order[0] if any(e["class"] == "gem" for e in kinds) else None
            gem_kind = next((e for e in kinds if e["class"] == "gem"), None)
            others = [entry for entry in kinds if entry["class"] != "gem"]
            layout: list[dict[str, Any]] = []
            for index in range(len(shape)):
                layout.append(gem_kind if index == gem_slot else others.pop(0))

            empty_points = int(cadence["empty_points"])
            next_slot = 1
            if empty_points > 0:
                slots.append(
                    {
                        "slot": next_slot,
                        "category": -1,
                        "item_id": 0,
                        "quantity": 0,
                        "base_point": empty_points,
                        "luck": False,
                    }
                )
                next_slot += 1
            for entry, spec in zip(layout, shape):
                quantity = 1 if entry["class"] == "gem" else max(
                    1, min(int(spec["quantity"]), int(entry["max_num"]))
                )
                slots.append(
                    {
                        "slot": next_slot,
                        "category": int(entry["category"]),
                        "item_id": int(entry["item_id"]),
                        "quantity": quantity,
                        "base_point": int(spec["points"]),
                        "luck": bool(spec["luck"]),
                    }
                )
                next_slot += 1
        else:
            # A vanilla-populated table that rolled empty: an explicit nothing
            # slot at the field's own total, never a zero-weight row.
            slots.append(
                {
                    "slot": 1,
                    "category": -1,
                    "item_id": 0,
                    "quantity": 0,
                    "base_point": int(field["vanilla"]["total_points"]),
                    "luck": False,
                }
            )

        assignments.append(
            {
                "npc_param_id": npc_id,
                "drop_field": drop_field,
                "source_lot_id": int(field["source_lot_id"]),
                "lot": {
                    "id": int(field["lot_id"]),
                    "rarity": int(field["rarity"]),
                    "slots": slots,
                },
            }
        )
    return assignments
