#!/usr/bin/env python3
"""Plan the suppression of vanilla item awards.

Archipelago shuffles Bloodborne's key items, but nothing stops the game handing
you the original one where it has always been. So every gate in the logic model
is satisfiable by the vanilla copy and the shuffle currently decides nothing.

## Why this suppresses at the LOT and not at the placement

The obvious move is to edit the MSB treasure that holds the item. It is the
wrong one, for two measured reasons.

1. **The acquisition flag is a property of the lot, not of the placement.**
   Across all 8,888 rows of `lot_items.tsv`, the number of lots carrying more
   than one distinct acquisition flag is **zero**. Repointing a placement at a
   different lot therefore moves the flag, and those flags are exactly the
   detection targets recorded in `runtime_bindings.py`. Editing the lot in place
   changes what you receive and leaves the flag alone.

2. **A lot is reached by several different mechanisms.** MSB treasures, NpcParam
   drop tables and EMEVD `AwardItemLot` calls all end at the same row. Editing
   the row covers every route at once; editing placements would need three
   separate tools, and of the six pickups randomized today only one is an MSB
   treasure at all.

So: rewrite the `ItemLotParam` row to award a placeholder, keep the row id, keep
the flag. The pickup still exists, the player still interacts with it, the flag
still fires for the check, and the item that comes out is junk instead of the
key.

## What this tool does and does not do

It plans. It reads the committed research corpus, resolves each randomized item
to the row that awards it, and refuses to emit a plan for anything ambiguous.
It does not open a param file — writing needs the game dump and belongs in a
separate step that consumes this plan.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GOODS_CATEGORY = "4"


@dataclass
class LotFacts:
    item_lot_id: str
    lot_name: str
    acquisition_flags: list[str]
    item_rows: int
    placements: int
    other_lots_with_same_item: list[str]


@dataclass
class PlannedEdit:
    item_key: str
    goods_id: str
    item_lot_id: str
    lot_name: str
    acquisition_flag: str
    placements: int
    reason: str = "randomized by Archipelago; vanilla award must not satisfy its own gate"


@dataclass
class Refusal:
    item_key: str
    goods_id: str
    problem: str
    detail: str


@dataclass
class Plan:
    placeholder: dict[str, str]
    edits: list[PlannedEdit] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refusals


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def collect_lot_facts(research: Path) -> dict[str, LotFacts]:
    items = read_tsv(research / "joined" / "lot_items.tsv")

    flags: dict[str, set[str]] = defaultdict(set)
    item_rows: dict[str, int] = defaultdict(int)
    lots_by_item: dict[tuple[str, str], set[str]] = defaultdict(set)
    names: dict[str, str] = {}
    for row in items:
        lot = row["item_lot_id"]
        names.setdefault(lot, row["lot_name"])
        item_rows[lot] += 1
        for field_name in ("slot_acquisition_flag", "generic_acquisition_flag"):
            value = (row.get(field_name) or "").strip()
            # 0 and -1 both mean "no flag" in these params. Treating -1 as a real
            # flag would emit a plan claiming to preserve a detection target that
            # does not exist.
            if value and value not in {"0", "-1"}:
                flags[lot].add(value)
        if row.get("item_id"):
            lots_by_item[(row["item_category"], row["item_id"])].add(lot)

    placements: dict[str, int] = defaultdict(int)
    for name in ("fixed_treasure_lots.tsv", "fixed_enemy_drop_sources.tsv"):
        for row in read_tsv(research / "joined" / name):
            if row.get("item_lot_id"):
                placements[row["item_lot_id"]] += 1

    facts: dict[str, LotFacts] = {}
    for lot in item_rows:
        siblings: set[str] = set()
        for (_, _), lots in lots_by_item.items():
            if lot in lots and len(lots) > 1:
                siblings |= lots - {lot}
        facts[lot] = LotFacts(lot, names.get(lot, ""), sorted(flags.get(lot, ())),
                              item_rows[lot], placements.get(lot, 0), sorted(siblings))
    return facts


def lots_awarding(research: Path, goods_id: str) -> list[str]:
    return sorted({
        row["item_lot_id"] for row in read_tsv(research / "joined" / "lot_items.tsv")
        if row["item_category"] == GOODS_CATEGORY and row["item_id"] == goods_id
    })


def build_plan(item_goods: dict[str, str], research: Path,
               placeholder: dict[str, str]) -> Plan:
    """Resolve each randomized item to the one row that awards it.

    Every branch that gives up is deliberate. A plan that guesses which of two
    lots to edit is worse than no plan: the wrong guess leaves the vanilla item
    reachable and looks like it worked.
    """
    facts = collect_lot_facts(research)
    items = read_tsv(research / "joined" / "lot_items.tsv")
    by_goods: dict[str, list[str]] = defaultdict(list)
    for row in items:
        if row["item_category"] == GOODS_CATEGORY and row["item_id"]:
            by_goods[row["item_id"]].append(row["item_lot_id"])

    plan = Plan(placeholder=placeholder)
    for key, goods_id in sorted(item_goods.items()):
        lots = sorted(set(by_goods.get(goods_id, ())))
        if not lots:
            plan.refusals.append(Refusal(key, goods_id, "no_lot",
                "no ItemLotParam row awards this item. It may be shop-sourced, "
                "granted by a covenant or engine side effect, or absent from the "
                "extracted corpus. Suppressing it needs a different mechanism."))
            continue
        if len(lots) > 1:
            plan.refusals.append(Refusal(key, goods_id, "multiple_lots",
                f"awarded by {len(lots)} rows ({', '.join(lots)}). Editing one "
                "leaves the others reachable, so the vanilla item still satisfies "
                "its own gate. Decide which are in scope before planning."))
            continue
        lot = lots[0]
        fact = facts[lot]
        if not fact.acquisition_flags:
            plan.refusals.append(Refusal(key, goods_id, "no_acquisition_flag",
                f"lot {lot} ({fact.lot_name}) has no acquisition flag. Suppressing it "
                "is possible, but the location can never be detected, so it cannot be "
                "a check until a different signal is found for it."))
            continue
        if len(fact.acquisition_flags) > 1:
            plan.refusals.append(Refusal(key, goods_id, "flag_not_unique",
                f"lot {lot} carries {len(fact.acquisition_flags)} acquisition flags "
                f"({fact.acquisition_flags}). The flag is the detection target; an "
                "edit must not make it ambiguous."))
            continue
        if fact.item_rows > 1:
            plan.refusals.append(Refusal(key, goods_id, "multi_item_lot",
                f"lot {lot} awards {fact.item_rows} item rows. Replacing the whole "
                "row would also suppress the others; the edit has to be per-slot."))
            continue
        plan.edits.append(PlannedEdit(key, goods_id, lot, fact.lot_name,
                                      fact.acquisition_flags[0], fact.placements))
    return plan


def load_item_goods() -> dict[str, str]:
    """Map each randomized item key to its goods id, from the world's own bindings."""
    sys.path.insert(0, str(REPO))
    from worlds.bloodborne import SHUFFLABLE_ITEMS
    from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS

    out: dict[str, str] = {}
    for item in SHUFFLABLE_ITEMS:
        binding = ITEM_BINDINGS.get(item.key)
        if binding is None or binding.normalized_item_id is None:
            continue
        out[item.key] = str(binding.normalized_item_id & 0x0FFFFFFF)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--research", type=Path, default=REPO / "research")
    parser.add_argument("--output", type=Path, default=None)
    # Goods 1000 is the Blood Vial: 0x400003E8, which DELIVERY_FIXTURES already
    # records as granted live, with maxNum 20 and isOnlyOne 0. Worthless,
    # stackable, safe to receive repeatedly, and already this world's filler.
    parser.add_argument("--placeholder-goods", default="1000",
                        help="goods id to award instead of the suppressed item")
    parser.add_argument("--placeholder-name", default="Blood Vial",
                        help="human label for the substitute, for the plan only")
    parser.add_argument("--allow-refusals", action="store_true",
                        help="emit a partial plan instead of failing")
    args = parser.parse_args(argv)

    plan = build_plan(load_item_goods(), args.research,
                      {"goods_id": args.placeholder_goods, "name": args.placeholder_name})

    print(f"planned {len(plan.edits)} lot edit(s), refused {len(plan.refusals)}")
    for edit in plan.edits:
        shared = f"  [{edit.placements} placements]" if edit.placements > 1 else ""
        print(f"  {edit.item_key:<32} lot {edit.item_lot_id:<8} flag {edit.acquisition_flag:<9}"
              f" {edit.lot_name}{shared}")
    for refusal in plan.refusals:
        print(f"  REFUSED {refusal.item_key:<24} [{refusal.problem}] {refusal.detail}",
              file=sys.stderr)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({
            "format": "bb-vanilla-suppression-plan-v1",
            "placeholder": plan.placeholder,
            "edits": [asdict(e) for e in plan.edits],
            "refusals": [asdict(r) for r in plan.refusals],
        }, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.output}")

    if plan.refusals and not args.allow_refusals:
        print("\nrefusing to emit a plan with unresolved items; pass --allow-refusals "
              "to record what is known and what is not.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
