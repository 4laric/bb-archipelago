#!/usr/bin/env python3
"""Build the conservative enemy-drop shuffle catalog from committed inputs."""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.bb_inputs import read_blob

BUNDLE = ROOT / "research" / "bb_inputs.db"
OUTPUT = ROOT / "worlds" / "bloodborne" / "enemy_drop_catalog.json"


def param_rows(name: str) -> list[dict[str, str]]:
    text = read_blob(BUNDLE, f"params/{name}.csv").decode("utf-8-sig")
    return list(csv.DictReader(text.splitlines()))


def main() -> int:
    goods = {int(row["ID"]): row for row in param_rows("EquipParamGoods")}
    lots = {int(row["ID"]): row for row in param_rows("ItemLotParam")}
    npcs = {int(row["ID"]): row for row in param_rows("NpcParam")}
    with (ROOT / "research" / "joined" / "fixed_enemy_drop_sources.tsv").open(
        encoding="utf-8"
    ) as source:
        referenced = {
            (int(row["npc_param_id"]), row["drop_field"])
            for row in csv.DictReader(source, delimiter="\t")
        }

    groups: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    exclusions: dict[str, int] = defaultdict(int)
    for npc_id, field in sorted(referenced):
        lot_id = int(npcs[npc_id][field])
        lot = lots.get(lot_id)
        reason = ""
        active: list[tuple[int, int, int]] = []
        if lot is None:
            reason = "missing_lot"
        elif any(
            int(lot[name]) > 0
            for name in ("getItemFlagId", *(f"getItemFlagId{i:02}" for i in range(1, 9)))
        ):
            reason = "persistent_acquisition_flag"
        else:
            for slot in range(1, 9):
                item_id = int(lot[f"lotItemId{slot:02}"])
                points = int(lot[f"lotItemBasePoint{slot:02}"])
                if item_id <= 0 or points <= 0:
                    continue
                category = int(lot[f"lotItemCategory{slot:02}"])
                item = goods.get(item_id) if category == 4 else None
                if item is None:
                    reason = "non_goods_or_unknown"
                    break
                safe = (
                    int(item["isDrop"]) == 1
                    and int(item["isOnlyOne"]) == 0
                    and int(item["isFixItem"]) == 0
                    and int(item["maxNum"]) > 1
                    and int(item["qwcId"]) < 0
                )
                if not safe:
                    reason = "non_repeatable_goods"
                    break
                active.append(
                    (
                        points,
                        int(lot[f"lotItemNum{slot:02}"]),
                        int(lot[f"enableLuck{slot:02}"]),
                    )
                )
            if not reason and not active:
                reason = "empty_lot"
        if reason:
            exclusions[reason] += 1
            continue
        signature = (field, int(lot["lotItem_Rarity"]), tuple(active))
        groups[signature].append(
            {
                "npc_param_id": npc_id,
                "drop_field": field,
                "source_lot_id": lot_id,
            }
        )

    emitted = []
    for index, (signature, entries) in enumerate(sorted(groups.items(), key=lambda item: repr(item[0]))):
        if len({int(entry["source_lot_id"]) for entry in entries}) < 2:
            continue
        field, rarity, cadence = signature
        emitted.append(
            {
                "group": f"g{index:03}",
                "drop_field": field,
                "rarity": rarity,
                "cadence": [
                    {"points": points, "quantity": quantity, "luck": bool(luck)}
                    for points, quantity, luck in cadence
                ],
                "entries": entries,
            }
        )

    payload = {
        "format": "bb-enemy-drop-catalog-v1",
        "policy": {
            "fixed_map_archetypes_only": True,
            "categories": [4],
            "persistent_flags": False,
            "repeatable_goods_only": True,
            "group_key": ["drop_field", "lotItem_Rarity", "chance_quantity_luck_cadence"],
        },
        "groups": emitted,
        "summary": {
            "referenced_npc_fields": len(referenced),
            "groups": len(emitted),
            "assignments": sum(len(group["entries"]) for group in emitted),
            "distinct_lots": sum(
                len({entry["source_lot_id"] for entry in group["entries"]})
                for group in emitted
            ),
            "exclusions": dict(sorted(exclusions.items())),
        },
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
