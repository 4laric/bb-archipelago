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
            english_name = names.get(category, {}).get(item_id, "")
            if category == 4 and item_id in goods and goods[item_id].get("goodsType") == "1":
                tier, reason = "key_or_badge", "goods_type_1_requires_logic_review"
            elif category in (0, 1):
                tier, reason = "useful", FMG_BY_CATEGORY[category]
            elif category == 4 and item_id in goods and goods[item_id].get("isOnlyOne") == "1":
                tier, reason = "useful", "unique_goods_or_hunter_tool"
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
                "category_name": FMG_BY_CATEGORY.get(category, "gem" if category == 8 else "unknown"),
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
        json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
