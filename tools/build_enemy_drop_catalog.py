#!/usr/bin/env python3
"""Build the enemy-drop rewrite catalog from committed inputs.

The catalog carries everything the seed-side generator needs to *rewrite* an
enemy drop table rather than swap one vanilla table for another:

* the eligible NPC drop fields, including the ones whose vanilla lot is empty;
* each field's vanilla chance/quantity/luck cadence, so a rewrite can reuse it;
* the observed vanilla cadence profiles, so a field with no vanilla shape still
  gets a farm rate a real Bloodborne enemy already has;
* the item pools, with their `EquipParamGoods.maxNum` stack caps;
* the repeatable blood-gem recipe pool, tiered by the maps the archetype
  occupies.

Slot semantics (measured, `research/bb_inputs.db` CUSA03173 01.09): the eight
`lotItem*` slots of an `ItemLotParam` row are ONE weighted pick, not eight
independent rolls. Across the 329 distinct lots referenced by fixed-map NPC
drop fields, `lotItemBasePoint01..08` sums to 1000 in 267 rows and to 100 in 55
rows; the "nothing" outcome is an explicit slot with `lotItemCategory = -1`,
`lotItemId = 0` and a positive base point (163 such slots), while an unused
slot is category 0 / id 0 / base point 0 (1877 such slots). A slot's drop
chance is therefore `basePoint / sum(basePoint)`, and a rewritten row must
carry its own "nothing" slot or the enemy drops something on every kill.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bb_inputs import read_blob
from worlds.bloodborne.data import CONSUMABLE_ITEM_KEYS
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS

BUNDLE = ROOT / "research" / "bb_inputs.db"
OUTPUT = ROOT / "worlds" / "bloodborne" / "enemy_drop_catalog.json"

# Rewritten rows are written into a reserved ItemLotParam band; vanilla rows are
# never edited in place because fixed treasure and the vanilla suppression plan
# own many of them. The band sits above the category-8 award bands in
# `worlds/bloodborne/category8_awards.py` (98_000_000 generated, 98_100_000
# event awards). `LOT_STRIDE` repeats that module's finding: ItemLotParam ids
# are read as consecutive groups, so award ids must not be adjacent.
RESERVED_LOT_BASE = 99_000_000
RESERVED_LOT_STRIDE = 10

# Blood Vial and Quicksilver Bullets. Measured share of the field-weighted
# vanilla enemy drop pool: 35.0% and 20.9%, which is the whole reason this
# catalog exists (a permutation of vanilla tables only ever swapped one vial
# table for another). They stay common in a rewrite, they stop being dominant.
STAPLE_GOODS = (1000, 900)

# Repeatable upgrade materials, all three witnessed in vanilla enemy lots:
# Blood Stone Shard, Twin Blood Stone Shards, Blood Stone Chunk. Blood Rock
# (goods 3030) is deliberately absent: it is not a repeatable farm item.
MATERIAL_GOODS = (3000, 3010, 3020)

# Per-kind sampling weights. Uniform over kinds within a class; the classes
# exist only to keep the two staples common without letting them dominate, and
# to stop the 28-recipe gem pool from swamping the consumable kinds.
# Staple weight 8 against 2 for every other consumable kind puts Blood Vials
# and Quicksilver Bullets at 8/62 = 12.9% of balanced slot picks each: still the
# two commonest single kinds a player sees, and a long way from the 35%/21% that
# made a table permutation invisible.
CLASS_WEIGHTS = {
    "staple": 8,
    "consumable": 2,
    "material": 2,
    "coldblood": 1,
    "gem": 1,
}

FLAG_FIELDS = ("getItemFlagId", *(f"getItemFlagId{index:02}" for index in range(1, 9)))


def param_rows(name: str) -> list[dict[str, str]]:
    text = read_blob(BUNDLE, f"params/{name}.csv").decode("utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def is_safe_goods(row: dict[str, str] | None) -> bool:
    """The unchanged consumables-only policy."""
    return bool(
        row is not None
        and int(row["isDrop"]) == 1
        and int(row["isOnlyOne"]) == 0
        and int(row["isFixItem"]) == 0
        and int(row["maxNum"]) > 1
        and int(row["qwcId"]) < 0
    )


def read_slots(lot: dict[str, str]) -> list[dict[str, int]]:
    """Every slot with a positive base point, in slot order."""
    slots = []
    for index in range(1, 9):
        points = int(lot[f"lotItemBasePoint{index:02}"])
        if points <= 0:
            continue
        slots.append(
            {
                "slot": index,
                "category": int(lot[f"lotItemCategory{index:02}"]),
                "item_id": int(lot[f"lotItemId{index:02}"]),
                "quantity": int(lot[f"lotItemNum{index:02}"]),
                "points": points,
                "luck": int(lot[f"enableLuck{index:02}"]),
            }
        )
    return slots


def main() -> int:
    goods = {int(row["ID"]): row for row in param_rows("EquipParamGoods")}
    lots = {int(row["ID"]): row for row in param_rows("ItemLotParam")}
    npcs = {int(row["ID"]): row for row in param_rows("NpcParam")}

    maps_by_field: dict[tuple[int, str], set[str]] = defaultdict(set)
    with (ROOT / "research" / "joined" / "fixed_enemy_drop_sources.tsv").open(
        encoding="utf-8"
    ) as source:
        for row in csv.DictReader(source, delimiter="\t"):
            maps_by_field[(int(row["npc_param_id"]), row["drop_field"])].add(
                row["map_name"]
            )
    referenced = sorted(maps_by_field)

    # --- gem recipe pool -------------------------------------------------
    # A category-8 recipe is admitted only when a vanilla enemy already drops
    # it from a lot with no acquisition flag, and never from a flagged one. The
    # unflagged recipes all live in the 900xx band; the flagged ones (Caryll
    # runes, boss gems, 90230) are one-time rewards and stay excluded.
    gem_unflagged: dict[int, set[str]] = defaultdict(set)
    gem_flagged: set[int] = set()
    for npc_id, field in referenced:
        lot = lots.get(int(npcs[npc_id][field]))
        if lot is None:
            continue
        flagged = any(int(lot[name]) > 0 for name in FLAG_FIELDS)
        for slot in read_slots(lot):
            if slot["category"] != 8:
                continue
            if flagged:
                gem_flagged.add(slot["item_id"])
            else:
                gem_unflagged[slot["item_id"]].update(maps_by_field[(npc_id, field)])
    gem_recipes = {
        recipe: sorted(maps)
        for recipe, maps in sorted(gem_unflagged.items())
        if recipe not in gem_flagged
    }
    gems_by_map: dict[str, set[int]] = defaultdict(set)
    for recipe, recipe_maps in gem_recipes.items():
        for name in recipe_maps:
            gems_by_map[name].add(recipe)

    # --- goods pools -----------------------------------------------------
    coldblood_ids = {
        ITEM_BINDINGS[key].normalized_item_id & 0x0FFFFFFF
        for key in CONSUMABLE_ITEM_KEYS
        if "coldblood" in key and key in ITEM_BINDINGS
    }
    consumable_ids = {
        ITEM_BINDINGS[key].normalized_item_id & 0x0FFFFFFF
        for key in CONSUMABLE_ITEM_KEYS
        if "coldblood" not in key and key in ITEM_BINDINGS
    }
    # Blood Vial has no runtime item binding (it is not an AP-deliverable
    # item), but goods 1000 is the single most common vanilla enemy drop and
    # the pool would be absurd without it.
    consumable_ids.update(STAPLE_GOODS)
    consumable_ids.difference_update(MATERIAL_GOODS)

    def pool_entries(ids: set[int] | tuple[int, ...], item_class: str) -> list[dict]:
        entries = []
        for item_id in sorted(ids):
            row = goods.get(item_id)
            if not is_safe_goods(row):
                raise SystemExit(
                    f"goods {item_id} fails the consumables policy; refusing to pool it"
                )
            entries.append(
                {
                    "item_id": item_id,
                    "category": 4,
                    "max_num": int(row["maxNum"]),
                    "class": item_class,
                    "weight": CLASS_WEIGHTS[item_class],
                }
            )
        return entries

    staples = pool_entries(set(STAPLE_GOODS), "staple")
    consumables = staples + pool_entries(
        consumable_ids - set(STAPLE_GOODS), "consumable"
    )
    materials = pool_entries(MATERIAL_GOODS, "material")
    coldblood = pool_entries(coldblood_ids, "coldblood")
    gem_pool = [
        {
            "item_id": recipe,
            "category": 8,
            "max_num": 1,
            "class": "gem",
            "weight": CLASS_WEIGHTS["gem"],
            "maps": recipe_maps,
        }
        for recipe, recipe_maps in gem_recipes.items()
    ]

    # --- eligible fields -------------------------------------------------
    fields: list[dict] = []
    exclusions: Counter[str] = Counter()
    profiles: dict[str, list[dict]] = defaultdict(list)
    quantity_weights: Counter[int] = Counter()
    for npc_id, field in referenced:
        lot_id = int(npcs[npc_id][field])
        lot = lots.get(lot_id)
        if lot is None:
            exclusions["missing_lot"] += 1
            continue
        if any(int(lot[name]) > 0 for name in FLAG_FIELDS):
            exclusions["persistent_acquisition_flag"] += 1
            continue
        slots = read_slots(lot)
        # The "nothing" slot (category -1, id 0) and unused slots are fine; an
        # award slot must be a repeatable category-4 good. A vanilla gem, rune,
        # weapon or one-off good keeps the field vanilla in every mode, so a
        # rewrite can never delete one.
        reason = ""
        for slot in slots:
            if slot["category"] == -1 and slot["item_id"] == 0:
                continue
            if slot["category"] != 4:
                reason = "non_goods_or_unknown"
                break
            if not is_safe_goods(goods.get(slot["item_id"])):
                reason = "non_repeatable_goods"
                break
        if reason:
            exclusions[reason] += 1
            continue

        awards = [slot for slot in slots if slot["category"] == 4]
        empty_points = sum(
            slot["points"] for slot in slots if slot["category"] != 4
        )
        total_points = sum(slot["points"] for slot in slots)
        field_maps = sorted(maps_by_field[(npc_id, field)])
        # Gem tier: the recipes an enemy in this archetype's own earliest map
        # already drops. Map names sort in rough progression order (m22 Central
        # Yharnam through m36 Fishing Hamlet), so the earliest map is the
        # conservative cap for an archetype that appears in several. Maps with
        # no vanilla enemy gem at all (m24_02, m32) fall back to the union over
        # the archetype's maps, then to the whole repeatable pool.
        tier = sorted(gems_by_map.get(field_maps[0], set()))
        if not tier:
            tier = sorted(
                {
                    recipe
                    for name in field_maps
                    for recipe in gems_by_map.get(name, set())
                }
            )
        tier_source = "map" if tier else "global"
        if not tier:
            tier = sorted(gem_recipes)
        fields.append(
            {
                "npc_param_id": npc_id,
                "drop_field": field,
                "source_lot_id": lot_id,
                "maps": field_maps,
                "rarity": int(lot["lotItem_Rarity"]),
                "vanilla": {
                    "populated": bool(awards),
                    "total_points": total_points,
                    "empty_points": empty_points,
                    "slots": [
                        {
                            "points": slot["points"],
                            "quantity": slot["quantity"],
                            "luck": bool(slot["luck"]),
                        }
                        for slot in awards
                    ],
                },
                "gem_recipes": tier,
                "gem_tier_source": tier_source,
            }
        )
        if awards:
            quantity_weights.update(slot["quantity"] for slot in awards)
            profiles[str(len(awards))].append(
                {
                    "total_points": total_points,
                    "empty_points": empty_points,
                    "slots": [
                        {
                            "points": slot["points"],
                            "quantity": slot["quantity"],
                            "luck": bool(slot["luck"]),
                        }
                        for slot in awards
                    ],
                }
            )

    # Deduplicate the cadence profiles but keep their multiplicity as a weight,
    # so a rewrite draws a shape as often as vanilla uses it.
    cadence_profiles = {}
    for count, shapes in sorted(profiles.items(), key=lambda item: int(item[0])):
        counted = Counter(json.dumps(shape, sort_keys=True) for shape in shapes)
        cadence_profiles[count] = [
            {**json.loads(shape), "weight": weight}
            for shape, weight in sorted(counted.items())
        ]

    fields.sort(key=lambda row: (row["npc_param_id"], row["drop_field"]))
    for index, row in enumerate(fields):
        row["lot_id"] = RESERVED_LOT_BASE + RESERVED_LOT_STRIDE * index
    band_top = RESERVED_LOT_BASE + RESERVED_LOT_STRIDE * max(len(fields) - 1, 0)
    collisions = sorted(
        lot_id for lot_id in lots if RESERVED_LOT_BASE <= lot_id <= band_top
    )
    if collisions:
        raise SystemExit(f"reserved lot band collides with vanilla rows {collisions}")

    populated = sum(1 for row in fields if row["vanilla"]["populated"])
    payload = {
        "format": "bb-enemy-drop-catalog-v2",
        "policy": {
            "fixed_map_archetypes_only": True,
            "categories": [4, 8],
            "persistent_flags": False,
            "repeatable_goods_only": True,
            "rewrites_contents": True,
            "edits_vanilla_lot_rows": False,
            "gem_recipes": "unflagged vanilla enemy category-8 awards only",
            "slot_semantics": "one weighted pick over slots 01-08; explicit "
            "category -1 nothing slot; chance = basePoint / sum(basePoint)",
        },
        "reserved_lot_band": {
            "base": RESERVED_LOT_BASE,
            "stride": RESERVED_LOT_STRIDE,
            "count": len(fields),
            "top": band_top,
        },
        "class_weights": CLASS_WEIGHTS,
        "pools": {
            "consumables": consumables,
            "materials": materials,
            "coldblood": coldblood,
            "gems": gem_pool,
        },
        "cadence": {
            "profiles": cadence_profiles,
            "quantity_weights": {
                str(quantity): count
                for quantity, count in sorted(quantity_weights.items())
            },
            "slot_count_weights": {
                count: len(shapes) for count, shapes in sorted(
                    profiles.items(), key=lambda item: int(item[0])
                )
            },
        },
        "density": {
            "eligible_fields": len(fields),
            "vanilla_populated": populated,
            "vanilla_populated_fraction": round(populated / len(fields), 6),
        },
        "fields": fields,
        "summary": {
            "referenced_npc_fields": len(referenced),
            "eligible_fields": len(fields),
            "vanilla_populated_fields": populated,
            "vanilla_empty_fields": len(fields) - populated,
            "consumable_pool": len(consumables),
            "material_pool": len(materials),
            "coldblood_pool": len(coldblood),
            "gem_pool": len(gem_pool),
            "cadence_profiles": sum(len(rows) for rows in cadence_profiles.values()),
            "vanilla_lots_in_reserved_band": len(collisions),
            "exclusions": dict(sorted(exclusions.items())),
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
