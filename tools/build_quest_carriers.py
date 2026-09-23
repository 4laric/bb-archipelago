#!/usr/bin/env python3
"""Build the quest-drop carrier exclusion list from committed inputs.

A placement whose NpcParam drop lot carries a persistent acquisition flag
or a non-repeatable quest good (weapon, rune, one-off) keeps its exact
NpcParam row: swapping in a donor row would delete that lot from the game,
because the enemy-drop rewriter deliberately leaves such fields on their
vanilla lots and keys everything by npc_param_id. Category-8 blood-gem
recipes without flags are repeatable farm drops, not quest goods.

Output: research/enemizer/quest_drop_carriers.json
(bb-enemizer-quest-carriers-v1): logical key -> npc/lot/flag/goods evidence.
Reads research/bb_inputs.db only; no game dump required.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import tempfile
import zlib
from collections import defaultdict
from pathlib import Path

try:
    from .bb_enemizer.inventory import load_slots
except ImportError:
    from bb_enemizer.inventory import load_slots

FLAG_FIELDS = ("getItemFlagId",) + tuple(f"getItemFlagId{i:02}" for i in range(1, 9))
LOT_FIELDS = tuple(f"itemLotId_{i}" for i in range(1, 7)) + ("humanityLotId",)


def _csv_from_bundle(bundle: Path, name: str) -> dict[str, dict]:
    database = sqlite3.connect(bundle)
    try:
        blob = database.execute(
            "SELECT blob FROM files WHERE path=?", (f"params/{name}.csv",)).fetchone()[0]
    finally:
        database.close()
    tmp = Path(tempfile.mkdtemp()) / name
    tmp.write_bytes(zlib.decompress(blob))
    with tmp.open(encoding="utf-8-sig", newline="") as handle:
        return {row["ID"]: row for row in csv.DictReader(handle)}


def _quest_slots(lot: dict, goods: dict) -> list[list]:
    found = []
    for i in range(1, 9):
        suffix = f"{i:02}"
        points = int(lot.get(f"lotItemBasePoint{suffix}", 0) or 0)
        category = int(lot.get(f"lotItemCategory{suffix}", 0) or 0)
        item_id = int(lot.get(f"lotItemId{suffix}", 0) or 0)
        if points <= 0 or (category == -1 and item_id == 0) or category == 8:
            continue
        row = goods.get(str(item_id))
        if (category != 4 or row is None
                or not (int(row.get("isDrop", 0)) == 1 and int(row.get("isOnlyOne", 1)) == 0
                        and int(row.get("maxNum", 0)) > 1 and int(row.get("qwcId", 0)) < 0)):
            found.append([category, item_id])
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=Path("research/bb_inputs.db"))
    parser.add_argument("--inventory", type=Path)
    parser.add_argument("--output", type=Path,
                        default=Path("research/enemizer/quest_drop_carriers.json"))
    args = parser.parse_args(argv)
    temporary = tempfile.TemporaryDirectory() if not args.inventory else None
    try:
        if args.inventory:
            inventory = args.inventory
        else:
            database = sqlite3.connect(args.bundle)
            try:
                blob = database.execute(
                    "SELECT blob FROM files WHERE path='mined/msb_enemies.tsv'").fetchone()[0]
            finally:
                database.close()
            inventory = Path(temporary.name) / "msb_enemies.tsv"
            inventory.write_bytes(zlib.decompress(blob))
        slots = load_slots(inventory)
    finally:
        if temporary:
            temporary.cleanup()
    npcs = _csv_from_bundle(args.bundle, "NpcParam")
    lots = _csv_from_bundle(args.bundle, "ItemLotParam")
    goods = _csv_from_bundle(args.bundle, "EquipParamGoods")

    grouped: dict[str, list] = defaultdict(list)
    for slot in slots:
        grouped[slot.logical_key].append(slot)
    carriers = {}
    for logical_key in sorted(grouped):
        copies = grouped[logical_key]
        npc_id = str(copies[0].archetype.npc_param_id)
        row = npcs.get(npc_id)
        if row is None:
            continue
        for field in LOT_FIELDS:
            lot = lots.get(row.get(field, "-1"))
            if lot is None:
                continue
            flagged = any(int(lot.get(name, 0) or 0) > 0 for name in FLAG_FIELDS)
            quest = _quest_slots(lot, goods)
            if flagged or quest:
                carriers[logical_key] = {
                    "npc_param_id": int(npc_id),
                    "drop_field": field,
                    "item_lot_id": int(row[field]),
                    "persistent_acquisition_flag": flagged,
                    "quest_goods": quest,
                    "team_type": row.get("teamType"),
                    "npc_type": row.get("npcType"),
                }
                break
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(
        {"format": "bb-enemizer-quest-carriers-v1", "carriers": carriers},
        indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"quest-drop carriers: {len(carriers)} logical placements -> {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
