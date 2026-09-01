#!/usr/bin/env python3
"""Build a canonical, English fixed-map location catalog for the Bloodborne MVP."""
from __future__ import annotations

import argparse
import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


FMG_BY_CATEGORY = {0: "weapon", 1: "armor", 4: "goods"}
# Curated exceptions whose English identity and progression role are independently
# confirmed by the validation pass. Keep this narrow: goodsType 1 alone still
# requires logic review for the rest of the catalog.
VALIDATED_PROGRESSION_GOODS = {4011: "hunter_chief_emblem_validation"}

# GemGenParam is a shared generator table: these fixed ids construct Caryll
# runes, not blood gems.  The English identities are corroborated by their
# native effects and fixed pickup locations.  They remain vanilla-only until
# category-8 rune delivery has its own proven runtime contract (#214).
CARYLL_RUNES_BY_GENERATOR_ID = {
    100001: "Moon (+10% Blood Echoes)",
    100002: "Moon (+20% Blood Echoes)",
    100201: "Eye (+50 Discovery)",
    100301: "Clockwise Metamorphosis (+5% HP)",
    100302: "Clockwise Metamorphosis (+10% HP)",
    100401: "Anti-Clockwise Metamorphosis (+10% Stamina)",
    100802: "Heir (+40% Visceral Blood Echoes)",
    101301: "Arcane Lake (+5% Arcane Reduction)",
    101302: "Arcane Lake (+7% Arcane Reduction)",
    101401: "Fading Lake (+5% Fire Reduction)",
    101601: "Dissipating Lake (+5% Bolt Reduction)",
    101701: "Lake (+3%)",
    101802: "Great Lake (+4%)",
    102001: "Clear Deep Sea (+100 Slow Poison RES)",
    102002: "Clear Deep Sea (+200 Slow Poison RES)",
    102102: "Stunning Deep Sea (+200 Rapid Poison RES)",
    102202: "Deep Sea (+200 Frenzy RES)",
    102302: "Great Deep Sea (+100 All RES)",
    102901: "Communion (+1 Blood Vial)",
    102902: "Communion (+2 Blood Vials)",
    102903: "Communion (+3 Blood Vials)",
    103104: "Formless Oedon (+4 Quicksilver Bullets)",
}


def read_tsv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh, delimiter="\t")


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh)


def read_fmg(path: Path) -> dict[int, str]:
    result = {}
    for node in ET.parse(path).getroot().findall("./entries/text"):
        if node.text and node.text != "%null%":
            result[int(node.attrib["id"])] = node.text
    return result


def write_tsv(path: Path, fields: list[str], rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        out = csv.DictWriter(fh, fields, delimiter="\t", lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("joined", type=Path)
    ap.add_argument("params", type=Path)
    ap.add_argument("goods_fmg", type=Path)
    ap.add_argument("weapon_fmg", type=Path)
    ap.add_argument("armor_fmg", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()

    names = {
        0: read_fmg(ns.weapon_fmg),
        1: read_fmg(ns.armor_fmg),
        4: read_fmg(ns.goods_fmg),
    }
    goods = {int(row["ID"]): row for row in read_csv(ns.params / "EquipParamGoods.csv")}
    items_by_lot = defaultdict(list)
    for row in read_tsv(ns.joined / "lot_items.tsv"):
        items_by_lot[row["item_lot_id"]].append(row)

    groups = defaultdict(list)
    unresolved = []
    for row in read_tsv(ns.joined / "fixed_treasure_lots.tsv"):
        flags = [f for f in re.split(r"[;|, ]+", row["acquisition_flags"]) if f]
        if not flags:
            unresolved.append(row)
            continue
        # BB fixed treasures use one row-level flag. Preserve an unusual multi-flag row separately.
        for flag in flags:
            groups[flag].append(row)

    item_rows = []
    catalog_rows = []
    for flag, placements in sorted(groups.items(), key=lambda pair: int(pair[0])):
        lots = sorted({row["item_lot_id"] for row in placements}, key=int)
        unique_items = {}
        for lot in lots:
            for item in items_by_lot.get(lot, ()):
                category = int(item["item_category"])
                item_id = int(item["item_id"])
                unique_items.setdefault((category, item_id, item["quantity"]), item)

        tiers = []
        display_items = []
        for (category, item_id, quantity), item in sorted(unique_items.items()):
            english_name = (
                CARYLL_RUNES_BY_GENERATOR_ID.get(item_id, "")
                if category == 8
                else names.get(category, {}).get(item_id, "")
            )
            if category == 4 and item_id in VALIDATED_PROGRESSION_GOODS:
                tier, reason = "key_or_badge", VALIDATED_PROGRESSION_GOODS[item_id]
            elif category == 4 and item_id in goods and goods[item_id].get("goodsType") == "1":
                tier, reason = "key_or_badge", "goods_type_1_requires_logic_review"
            elif category in (0, 1):
                tier, reason = "useful", FMG_BY_CATEGORY[category]
            elif category == 4 and item_id in goods and goods[item_id].get("isOnlyOne") == "1":
                tier, reason = "useful", "unique_goods_or_hunter_tool"
            elif category == 8 and item_id in CARYLL_RUNES_BY_GENERATOR_ID:
                tier, reason = "optional", "fixed_caryll_rune_vanilla_only"
            elif category == 8:
                tier, reason = "optional", "generated_blood_gem"
            elif category == 15:
                tier, reason = "excluded", "level_dependent_or_chalice_indirection"
            else:
                tier, reason = "filler", "consumable_or_material"
            tiers.append(tier)
            display_items.append(f"{english_name or 'unknown'} x{quantity}")
            item_rows.append({
                "location_flag": flag, "item_lot_id": item["item_lot_id"],
                "slot": item["slot"], "category": category,
                "category_name": FMG_BY_CATEGORY.get(
                    category,
                    (
                        "caryll_rune"
                        if item_id in CARYLL_RUNES_BY_GENERATOR_ID
                        else "gem"
                    ) if category == 8 else "unknown",
                ),
                "item_param_id": item_id, "english_name": english_name,
                "quantity": quantity, "normalized_runtime_id": item["normalized_runtime_id"],
                "classification": tier, "classification_reason": reason,
            })
        rank = {"key_or_badge": 0, "useful": 1, "optional": 2, "filler": 3, "excluded": 4}
        classification = min(tiers, key=rank.get) if tiers else "unresolved"
        maps = sorted({row["map_name"] for row in placements})
        event_names = sorted({row["event_name"] for row in placements})
        canonical_map = min(maps, key=lambda name: (name.endswith(("_01", "_11")), name))
        catalog_rows.append({
            "location_flag": flag,
            "canonical_map": canonical_map,
            "map_variants": ";".join(maps),
            "item_lot_ids": ";".join(lots),
            "display_items": "; ".join(display_items),
            "classification": classification,
            "mvp_candidate": classification in ("key_or_badge", "useful"),
            "placement_count": len(placements),
            "event_names": ";".join(event_names),
            "coordinates": ";".join(sorted({f"{r['x']},{r['y']},{r['z']}" for r in placements if r["x"]})),
        })

    write_tsv(ns.output / "fixed_location_catalog.tsv", list(catalog_rows[0]), catalog_rows)
    write_tsv(ns.output / "fixed_location_items.tsv", list(item_rows[0]), item_rows)
    write_tsv(ns.output / "unresolved_fixed_treasures.tsv",
              list(unresolved[0]) if unresolved else ["map_path"], unresolved)
    summary = {
        "canonical_locations": len(catalog_rows),
        "catalog_item_rows": len(item_rows),
        "unresolved_treasure_references": len(unresolved),
        "classifications": dict(sorted(Counter(r["classification"] for r in catalog_rows).items())),
        "mvp_candidates": sum(r["mvp_candidate"] for r in catalog_rows),
        "duplicate_or_revision_placements_collapsed": sum(len(v) for v in groups.values()) - len(groups),
    }
    (ns.output / "location_catalog_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
