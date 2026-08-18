#!/usr/bin/env python3
"""Join Bloodborne CSV parameter dumps to raw MSBB provenance tables.

This deliberately preserves numeric item categories and every nonzero flag field;
it does not guess category semantics, player-facing names, or AP regions.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


UNSET = {"", "0", "-1"}


def rows(path: Path, delimiter: str = ","):
    with path.open(encoding="utf-8-sig", newline="") as fh:
        yield from csv.DictReader(fh, delimiter=delimiter)


def write_tsv(path: Path, fieldnames: list[str], data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        wr.writeheader()
        wr.writerows(data)


def fixed_map(map_path: str) -> bool:
    return "/" not in map_path.replace("\\", "/") and not Path(map_path).name.startswith("m29_")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("params_dump", type=Path)
    ap.add_argument("msb_mined", type=Path)
    ap.add_argument("output", type=Path)
    ns = ap.parse_args()

    lot_path = ns.params_dump / "ItemLotParam.csv"
    npc_path = ns.params_dump / "NpcParam.csv"
    lots = {int(r["ID"]): r for r in rows(lot_path)}
    npcs = {int(r["ID"]): r for r in rows(npc_path)}
    goods = {int(r["ID"]): r for r in rows(ns.params_dump / "EquipParamGoods.csv")}

    lot_fields = next(iter(lots.values())).keys()
    item_id_cols = sorted(c for c in lot_fields if c.startswith("lotItemId"))
    category_cols = sorted(c for c in lot_fields if c.startswith("lotItemCategory"))
    quantity_cols = sorted(c for c in lot_fields if c.startswith("lotItemNum"))
    point_cols = sorted(c for c in lot_fields if c.startswith("lotItemBasePoint"))
    slot_flag_cols = sorted(c for c in lot_fields if c.startswith("getItemFlagId") and c != "getItemFlagId")

    lot_item_rows = []
    lots_with_flags = set()
    for lot_id, lot in sorted(lots.items()):
        generic_flag = lot.get("getItemFlagId", "")
        all_flags = sorted({lot.get(c, "") for c in ["getItemFlagId", *slot_flag_cols]} - UNSET,
                           key=int)
        if all_flags:
            lots_with_flags.add(lot_id)
        for i, item_col in enumerate(item_id_cols):
            item_id = lot.get(item_col, "")
            if item_id in UNSET:
                continue
            slot = item_col[-2:]
            flag_col = f"getItemFlagId{slot}"
            lot_item_rows.append({
                "item_lot_id": lot_id,
                "lot_name": lot.get("Name", ""),
                "slot": slot,
                "item_category": lot.get(f"lotItemCategory{slot}", ""),
                "item_id": item_id,
                "item_param_name": goods.get(int(item_id), {}).get("Name", "")
                    if lot.get(f"lotItemCategory{slot}", "") == "4" else "",
                "normalized_runtime_id": f"0x{(0x40000000 | int(item_id)):08X}"
                    if lot.get(f"lotItemCategory{slot}", "") == "4" and int(item_id) in goods else "",
                "raw_runtime_descriptor": f"0x{(0xB0000000 | int(item_id)):08X}"
                    if lot.get(f"lotItemCategory{slot}", "") == "4" and int(item_id) in goods else "",
                "quantity": lot.get(f"lotItemNum{slot}", ""),
                "base_points": lot.get(f"lotItemBasePoint{slot}", ""),
                "slot_acquisition_flag": lot.get(flag_col, ""),
                "generic_acquisition_flag": generic_flag,
                "all_acquisition_flags": ";".join(all_flags),
            })
    lot_item_fields = list(lot_item_rows[0])
    write_tsv(ns.output / "lot_items.tsv", lot_item_fields, lot_item_rows)

    goods_rows = [{
        "goods_param_id": goods_id,
        "param_name": row.get("Name", ""),
        "normalized_runtime_id": f"0x{(0x40000000 | goods_id):08X}",
        "raw_runtime_descriptor": f"0x{(0xB0000000 | goods_id):08X}",
        "max_num": row.get("maxNum", ""),
        "max_repository_num": row.get("maxRepositoryNum", ""),
        "is_only_one": row.get("isOnlyOne", ""),
        "is_auto_replenish": row.get("isAutoReplenish", ""),
        "mapping_evidence": "formula validated by Bullets, Vials, Pebble, and Augur",
    } for goods_id, row in sorted(goods.items())]
    write_tsv(ns.output / "goods_runtime_ids.tsv", list(goods_rows[0]), goods_rows)

    treasure_rows = []
    treasure_lot_refs = Counter()
    missing_treasure_lots = Counter()
    for t in rows(ns.msb_mined / "msb_treasures.tsv", "\t"):
        if not fixed_map(t["map_path"]):
            continue
        for lot_col in ("item_lot_1", "item_lot_2", "item_lot_3"):
            value = t.get(lot_col, "")
            if value in UNSET:
                continue
            lot_id = int(value)
            treasure_lot_refs[lot_id] += 1
            lot = lots.get(lot_id)
            if lot is None:
                missing_treasure_lots[lot_id] += 1
            flags = [] if lot is None else sorted(
                {lot.get(c, "") for c in ["getItemFlagId", *slot_flag_cols]} - UNSET, key=int)
            treasure_rows.append({
                "map_path": t["map_path"],
                "map_name": t["map_name"],
                "event_name": t["event_name"],
                "event_id": t["event_id"],
                "event_entity_id": t["event_entity_id"],
                "treasure_part_name": t["treasure_part_name"],
                "part_entity_id": t["part_entity_id"],
                "x": t["x"], "y": t["y"], "z": t["z"],
                "lot_field": lot_col,
                "item_lot_id": lot_id,
                "lot_name": "" if lot is None else lot.get("Name", ""),
                "acquisition_flags": ";".join(flags),
            })
    treasure_fields = list(treasure_rows[0])
    write_tsv(ns.output / "fixed_treasure_lots.tsv", treasure_fields, treasure_rows)

    npc_drop_fields = [c for c in next(iter(npcs.values())).keys() if c.startswith("itemLotId_")]
    npc_drop_rows = []
    npc_to_lots: dict[int, list[tuple[str, int]]] = {}
    for npc_id, npc in sorted(npcs.items()):
        for field in npc_drop_fields:
            value = npc.get(field, "")
            if value in UNSET:
                continue
            lot_id = int(value)
            npc_to_lots.setdefault(npc_id, []).append((field, lot_id))
            npc_drop_rows.append({
                "npc_param_id": npc_id,
                "npc_name": npc.get("Name", ""),
                "drop_field": field,
                "item_lot_id": lot_id,
                "lot_name": lots.get(lot_id, {}).get("Name", ""),
                "lot_present": lot_id in lots,
                "lot_acquisition_flags": ";".join(sorted(
                    {lots[lot_id].get(c, "") for c in ["getItemFlagId", *slot_flag_cols]} - UNSET,
                    key=int)) if lot_id in lots else "",
            })
    write_tsv(ns.output / "npc_drop_lots.tsv", list(npc_drop_rows[0]), npc_drop_rows)

    enemy_sources = []
    unknown_enemy_npcs = Counter()
    for e in rows(ns.msb_mined / "msb_enemies.tsv", "\t"):
        if not fixed_map(e["map_path"]):
            continue
        npc_id = int(e["npc_param_id"])
        if npc_id not in npcs:
            unknown_enemy_npcs[npc_id] += 1
        for field, lot_id in npc_to_lots.get(npc_id, []):
            enemy_sources.append({
                "map_path": e["map_path"], "map_name": e["map_name"],
                "part_name": e["part_name"], "part_entity_id": e["part_entity_id"],
                "npc_param_id": npc_id, "npc_name": npcs.get(npc_id, {}).get("Name", ""),
                "talk_id": e["talk_id"], "x": e["x"], "y": e["y"], "z": e["z"],
                "drop_field": field, "item_lot_id": lot_id,
                "lot_name": lots.get(lot_id, {}).get("Name", ""),
            })
    write_tsv(ns.output / "fixed_enemy_drop_sources.tsv",
              list(enemy_sources[0]) if enemy_sources else ["map_path"], enemy_sources)

    summary = {
        "item_lot_rows": len(lots),
        "equip_param_goods_rows": len(goods),
        "lot_item_rows": len(lot_item_rows),
        "lots_with_acquisition_flags": len(lots_with_flags),
        "fixed_treasure_lot_references": len(treasure_rows),
        "fixed_distinct_treasure_lots": len(treasure_lot_refs),
        "fixed_missing_treasure_lot_ids": dict(sorted(missing_treasure_lots.items())),
        "npc_param_rows": len(npcs),
        "npc_drop_lot_rows": len(npc_drop_rows),
        "fixed_enemy_drop_source_rows": len(enemy_sources),
        "fixed_unknown_enemy_npc_ids": dict(sorted(unknown_enemy_npcs.items())),
        "measured_item_category_counts": dict(sorted(Counter(r["item_category"] for r in lot_item_rows).items())),
    }
    (ns.output / "param_join_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
