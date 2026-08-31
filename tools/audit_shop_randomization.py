#!/usr/bin/env python3
"""Refuse shop randomization until every Bath gate has a randomized badge.

The gate identities are witnessed by representative ShopLineupParam rows.  The
badge ids are independently checked against the progression-item mine, and pool
membership is checked against the world model source.  This script deliberately
returns non-zero while the feature is unsafe.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPECTED_GATES = set(range(12101000, 12101010))


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def modeled_item_names(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r'Item\(\s*"[^"]+"\s*,\s*"([^"]+)"', text))


def audit(repo: Path = REPO) -> dict[str, object]:
    witnesses = read_tsv(repo / "research/validation/shop_gate_witnesses.tsv")
    progression = read_tsv(repo / "research/validation/progression_items.tsv")
    goods_by_name = {row["item_name"]: int(row["goods_param_id"])
                     for row in progression if row["goods_param_id"]}
    modeled = modeled_item_names(repo / "worlds/bloodborne/data.py")

    errors: list[str] = []
    gates = [int(row["qwc_id"]) for row in witnesses]
    goods = [int(row["goods_id"]) for row in witnesses]
    if set(gates) != EXPECTED_GATES or len(gates) != len(EXPECTED_GATES):
        errors.append("witness table must contain each ordinary Bath gate exactly once")
    if len(goods) != len(set(goods)):
        errors.append("badge goods ids must be unique")

    rows = []
    for row in witnesses:
        name = row["badge_name"]
        goods_id = int(row["goods_id"])
        mined_goods = goods_by_name.get(name)
        if mined_goods != goods_id:
            errors.append(
                f"{name}: witness goods {goods_id}, progression mine says {mined_goods}")
        in_pool = name in modeled
        rows.append({
            "qwc_id": int(row["qwc_id"]),
            "badge_name": name,
            "goods_id": goods_id,
            "representative_row": int(row["representative_row"]),
            "stock_witness": row["stock_witness"],
            "in_world_model": in_pool,
        })

    missing = [row["badge_name"] for row in rows if not row["in_world_model"]]
    if missing:
        errors.append("badges absent from AP world model: " + ", ".join(missing))
    return {
        "format": "bb-shop-randomization-audit-v1",
        "ready": not errors,
        "gate_count": len(rows),
        "modeled_badge_count": len(rows) - len(missing),
        "missing_badges": missing,
        "errors": errors,
        "gates": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true",
                        help="report an unsafe audit without returning failure")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for row in report["gates"]:
            state = "POOL" if row["in_world_model"] else "MISSING"
            print(f"{row['qwc_id']}  {row['badge_name']} ({row['goods_id']})  "
                  f"{state}  witness={row['representative_row']}:{row['stock_witness']}")
        print(f"ready={str(report['ready']).lower()} "
              f"modeled={report['modeled_badge_count']}/{report['gate_count']}")
        for error in report["errors"]:
            print(f"REFUSED: {error}")
    return 0 if report["ready"] or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
