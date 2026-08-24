#!/usr/bin/env python3
"""Apply a suppression plan to ItemLotParam.csv.

Consumes `bb-vanilla-suppression-plan-v2` from `plan_vanilla_suppression.py` and
rewrites the planned rows so they award a placeholder instead of the key item
Archipelago is shuffling. The row id and the acquisition flag are left alone —
that is the entire point, because the flag is the check's detection target.

## Why this edits text rather than parsing CSV

`ItemLotParam.csv` has a header of 71 fields and data rows of 70: the header
carries a trailing comma that the rows do not. Round-tripping that through
`csv.DictWriter` emits 71 fields per row and silently shifts every column. There
are no quoted fields anywhere in the file, so splitting on commas and replacing
one field by index is both simpler and lossless.

`--check` proves that claim on the real file before any edit is trusted: it runs
the whole pipeline with zero edits applied and requires the output to be
byte-identical to the input. A writer that cannot reproduce its input has no
business modifying it.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN_FORMAT = "bb-vanilla-suppression-plan-v2"
ITEM_SLOTS = range(1, 9)
GOODS_CATEGORY = "4"


class SuppressionError(RuntimeError):
    pass


@dataclass
class Table:
    header: list[str]
    lines: list[str]          # raw data lines, no trailing newline
    index: dict[str, int]     # column name -> position
    row_by_id: dict[str, int]

    @classmethod
    def load(cls, text: str) -> "Table":
        if text.endswith("\n"):
            text = text[:-1]
        rows = text.split("\n")
        header = rows[0].split(",")
        index = {name: i for i, name in enumerate(header) if name}
        for required in (
            "ID", "getItemFlagId", "lotItemId01", "lotItemCategory01", "lotItemNum01"
        ):
            if required not in index:
                raise SuppressionError(f"ItemLotParam is missing the {required} column")
        lines = rows[1:]
        row_by_id: dict[str, int] = {}
        for position, line in enumerate(lines):
            if line:
                row_by_id[line.split(",", 1)[0]] = position
        return cls(header, lines, index, row_by_id)

    def dump(self) -> str:
        return "\n".join([",".join(self.header), *self.lines]) + "\n"

    def field(self, row: int, column: str) -> str:
        return self.lines[row].split(",")[self.index[column]]

    def set_field(self, row: int, column: str, value: str) -> None:
        fields = self.lines[row].split(",")
        fields[self.index[column]] = value
        self.lines[row] = ",".join(fields)


@dataclass
class Applied:
    item_key: str
    item_lot_id: str
    slot: str
    was: str
    now: str
    was_category: str
    now_category: str
    was_quantity: str
    now_quantity: str
    acquisition_flag: str
    # A handful of planned rows already award exactly the placeholder (the
    # Blood Vial x1 corpses in Old Yharnam and Cathedral Ward). Suppressing
    # them is a no-op on the bytes, which is correct but indistinguishable
    # from "the write did not happen" unless it is declared here.
    already_placeholder: bool = False


def apply_plan(table: Table, plan: dict, *, dry_run: bool = False) -> list[Applied]:
    if plan.get("format") != PLAN_FORMAT:
        raise SuppressionError(f"expected a {PLAN_FORMAT} plan, got {plan.get('format')!r}")
    placeholder = str(plan["placeholder"]["goods_id"])
    placeholder_quantity = str(plan["placeholder"].get("quantity", 1))
    if not placeholder.isdigit():
        raise SuppressionError(f"placeholder goods id must be numeric, got {placeholder!r}")
    if not placeholder_quantity.isdigit() or int(placeholder_quantity) < 1:
        raise SuppressionError(
            f"placeholder quantity must be a positive integer, got {placeholder_quantity!r}"
        )

    applied: list[Applied] = []
    for edit in plan["edits"]:
        lot = str(edit["item_lot_id"])
        goods = str(edit["goods_id"])
        category = str(edit["item_category"])
        row = table.row_by_id.get(lot)
        if row is None:
            raise SuppressionError(f"{edit['item_key']}: lot {lot} is not in ItemLotParam")

        # Find the slot holding this item. The planner refuses multi-item lots,
        # so exactly one slot must match; anything else means the plan and the
        # params disagree and the edit would be a guess.
        matches = [n for n in ITEM_SLOTS
                   if table.field(row, f"lotItemId{n:02d}") == goods
                   and table.field(row, f"lotItemCategory{n:02d}") == category]
        if len(matches) != 1:
            raise SuppressionError(
                f"{edit['item_key']}: lot {lot} has {len(matches)} slots awarding "
                f"category {category} item {goods}; "
                "the plan was built against different params")

        slot = f"{matches[0]:02d}"
        flag_before = table.field(row, "getItemFlagId")
        quantity_before = table.field(row, f"lotItemNum{slot}")
        if flag_before != str(edit["acquisition_flag"]):
            raise SuppressionError(
                f"{edit['item_key']}: lot {lot} flag is {flag_before}, plan says "
                f"{edit['acquisition_flag']}. The detection target moved; re-plan.")

        if not dry_run:
            table.set_field(row, f"lotItemId{slot}", placeholder)
            table.set_field(row, f"lotItemCategory{slot}", GOODS_CATEGORY)
            table.set_field(row, f"lotItemNum{slot}", placeholder_quantity)

        applied.append(Applied(edit["item_key"], lot, slot, goods,
                               goods if dry_run else placeholder, category,
                               category if dry_run else GOODS_CATEGORY, quantity_before,
                               quantity_before if dry_run else placeholder_quantity, flag_before,
                               already_placeholder=(goods == placeholder
                                                    and category == GOODS_CATEGORY
                                                    and quantity_before == placeholder_quantity)))
    return applied


def verify(before: Table, after: Table, applied: list[Applied]) -> None:
    """Prove the edit did what it said and nothing else.

    Reading the result back is the only thing that distinguishes "the write
    succeeded" from "the write did what was intended".
    """
    if len(before.lines) != len(after.lines):
        raise SuppressionError("row count changed")

    # Rows that already awarded the placeholder must be byte-identical after
    # the write; every other planned row must have moved.
    expected = {a.item_lot_id for a in applied if not a.already_placeholder}
    changed = {after.lines[i].split(",", 1)[0]
               for i in range(len(after.lines)) if before.lines[i] != after.lines[i]}
    if changed != expected:
        unexpected = sorted(changed - expected)
        missing = sorted(expected - changed)
        raise SuppressionError(
            f"edited rows do not match the plan; unexpected={unexpected} unchanged={missing}")

    for a in applied:
        row = after.row_by_id[a.item_lot_id]
        if after.field(row, "getItemFlagId") != a.acquisition_flag:
            raise SuppressionError(f"lot {a.item_lot_id}: the acquisition flag changed")
        if after.field(row, f"lotItemCategory{a.slot}") != a.now_category:
            raise SuppressionError(f"lot {a.item_lot_id}: the item category changed")
        if after.field(row, f"lotItemId{a.slot}") != a.now:
            raise SuppressionError(f"lot {a.item_lot_id}: the item was not replaced")
        if after.field(row, f"lotItemNum{a.slot}") != a.now_quantity:
            raise SuppressionError(f"lot {a.item_lot_id}: the quantity was not replaced")
        if after.field(row, "ID") != a.item_lot_id:
            raise SuppressionError(f"lot {a.item_lot_id}: the row id changed")


def read_params(source: Path) -> str:
    if source.is_dir():
        return (source / "ItemLotParam.csv").read_text(encoding="utf-8-sig")
    if source.suffix == ".db":
        sys.path.insert(0, str(REPO))
        import zlib
        from tools.bb_inputs import connect
        db = connect(source)
        row = db.execute("SELECT blob FROM files WHERE path='params/ItemLotParam.csv'").fetchone()
        db.close()
        if row is None:
            raise SuppressionError("the bundle does not carry params/ItemLotParam.csv")
        return zlib.decompress(row[0]).decode("utf-8-sig")
    return source.read_text(encoding="utf-8-sig")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--params", type=Path, default=REPO / "research" / "bb_inputs.db",
                        help="a params dir, an ItemLotParam.csv, or the inputs bundle")
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    parser.add_argument("--check", action="store_true",
                        help="apply nothing and require a byte-identical round trip")
    args = parser.parse_args(argv)

    text = read_params(args.params)

    if args.check:
        rebuilt = Table.load(text).dump()
        if rebuilt != text:
            print("ROUND TRIP FAILED: the writer cannot reproduce its own input, so it "
                  "must not be trusted to modify it.", file=sys.stderr)
            for i, (a, b) in enumerate(zip(text.split("\n"), rebuilt.split("\n"))):
                if a != b:
                    print(f"  first difference at line {i}:\n    in  {a[:120]}\n    out {b[:120]}",
                          file=sys.stderr)
                    break
            return 1
        print(f"round trip is byte-identical ({len(text)} bytes, "
              f"{len(Table.load(text).lines)} rows)")
        return 0

    if not args.plan:
        parser.error("--plan is required unless --check")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))

    before = Table.load(text)
    after = Table.load(text)
    try:
        applied = apply_plan(after, plan)
        verify(before, after, applied)
    except SuppressionError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    print(f"suppressed {len(applied)} vanilla award(s)")
    for a in applied:
        print(f"  lot {a.item_lot_id:<8} slot {a.slot}  "
              f"category:item {a.was_category}:{a.was} -> 4:{a.now}"
              f" quantity {a.was_quantity}->{a.now_quantity}"
              f"  flag {a.acquisition_flag} unchanged   {a.item_key}")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(after.dump(), encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({
            "format": "bb-vanilla-suppression-receipt-v1",
            "placeholder": plan["placeholder"],
            "applied": [a.__dict__ for a in applied],
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.receipt}")
    if not args.output:
        print("\n(no --output given, so nothing was written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
