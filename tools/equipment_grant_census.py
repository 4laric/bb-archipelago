#!/usr/bin/env python3
"""Force-grant census for every weapon and attire binding (issue #330, phase 2).

Two subcommands, one live session on a throwaway save:

    python tools/equipment_grant_census.py script  > census-script.txt
    python tools/equipment_grant_census.py verdict  <delivery-diagnostics.jsonl> [--ui ui.tsv]

`script` prints, in a fixed order, one `give INDEX CONFIRM` console command per
category-0 (weapon) and category-1 (attire) binding, with the item name, the
runtime id the readback must show, and the evidence class the binding ships
with. The operator pastes them one at a time and records what the equipment
menu shows.

`verdict` reads the client's `delivery-diagnostics.jsonl` back and prints one
row per grant: whether the client completed it on a **verified slot readback**
or only on **execution evidence** (the Rifle Spear/Torch failure shape), the
inferred destination, and, if a UI sheet is given, whether the item was seen.
The script never talks to the game; it only reads the files the client wrote.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CATEGORY_NAMES = {0: "weapon", 1: "attire"}


def census_rows() -> list[dict[str, object]]:
    from worlds.bloodborne import ITEM_ID_BY_KEY, SHUFFLABLE_ITEMS
    from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS

    names = {item.key: item.name for item in SHUFFLABLE_ITEMS}
    rows = []
    for key, binding in ITEM_BINDINGS.items():
        if binding.item_category not in CATEGORY_NAMES or key not in ITEM_ID_BY_KEY:
            continue
        rows.append({
            "key": key,
            "name": names.get(key, key),
            "ap_item_id": ITEM_ID_BY_KEY[key],
            "category": CATEGORY_NAMES[binding.item_category],
            "normalized_item_id": binding.normalized_item_id,
            "raw_descriptor": binding.raw_descriptor,
            "descriptor_evidence": binding.descriptor_evidence,
        })
    # Weapons first, then attire; stable by key inside each group so two
    # operators produce the same order.
    rows.sort(key=lambda row: (row["category"] != "weapon", row["key"]))
    return rows


def print_script(rows: list[dict[str, object]]) -> None:
    print("# Equipment grant census. One command per line; wait for the AUDIT line")
    print("# and check the equipment menu before the next. Throwaway save only.")
    print("# columns: command | name | category | readback normalized id | evidence")
    for row in rows:
        print(
            f"give {row['ap_item_id']} CONFIRM\t{row['name']}\t{row['category']}\t"
            f"0x{row['normalized_item_id']:08X}\t{row['descriptor_evidence']}"
        )
    print(f"# {len(rows)} grants", file=sys.stderr)


def classify(record: dict[str, object]) -> str:
    """The completion branch the client took for one grant."""
    status = str(record.get("terminal_status", ""))
    detail = str(record.get("terminal_detail", ""))
    if status != "completed":
        return status or "unknown"
    if "instance insert verified at slot" in detail:
        return "verified_slot"
    if "completed on execution evidence" in detail:
        return "execution_evidence_only"
    if record.get("execution_evidence") and not any(
        value is not None for value in record.get("readbacks", [])
    ):
        return "execution_evidence_only"
    return "completed"


def verdict(diagnostics: Path, ui_sheet: Path | None) -> int:
    rows = {row["ap_item_id"]: row for row in census_rows()}
    seen: dict[int, str] = {}
    if ui_sheet is not None:
        with ui_sheet.open(encoding="utf-8", newline="") as handle:
            for line in csv.DictReader(handle, delimiter="\t"):
                seen[int(line["ap_item_id"])] = line["seen"].strip().lower()
    print("ap_item_id\tname\tcategory\tevidence\tbranch\tdestination\tnative_result\tui_seen")
    counts: dict[str, int] = {}
    with diagnostics.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            tag = str(record.get("tag", ""))
            if not tag.startswith("operator_grant_"):
                continue
            ap_item_id = int(tag.removeprefix("operator_grant_"))
            row = rows.get(ap_item_id)
            if row is None:
                continue
            branch = classify(record)
            counts[branch] = counts.get(branch, 0) + 1
            print(
                f"{ap_item_id}\t{row['name']}\t{row['category']}\t{row['descriptor_evidence']}\t"
                f"{branch}\t{record.get('inferred_destination', '')}\t"
                f"{record.get('native_result', '')}\t{seen.get(ap_item_id, '')}"
            )
    print(f"# branches: {counts}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("script", help="print the give commands")
    v = sub.add_parser("verdict", help="read delivery-diagnostics.jsonl back")
    v.add_argument("diagnostics", type=Path)
    v.add_argument("--ui", type=Path, default=None,
                   help="TSV with columns ap_item_id, seen (yes/no/storage)")
    args = parser.parse_args(argv)
    if args.command == "script":
        print_script(census_rows())
        return 0
    return verdict(args.diagnostics, args.ui)


if __name__ == "__main__":
    raise SystemExit(main())
