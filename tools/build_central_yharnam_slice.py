#!/usr/bin/env python3
"""Build the deterministic Central Yharnam fixed-pickup manifest.

The research catalog contains one row per acquisition flag and repeats the
same physical placements for the map's runtime variants.  The shipped slice
uses the canonical ``m24_01_00_00`` rows, collapses the two NG-cycle
replacement lots onto their first-playthrough physical locations, and keeps
the six previously published stable keys.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CANONICAL_MAP = "m24_01_00_00"
OUTPUT = REPO / "worlds" / "bloodborne" / "fixed_locations.tsv"

# These rows occupy the same physical chest as the preceding first-cycle row
# and are selected only when the unique first-cycle reward was already owned.
REPLACEMENT_FLAGS = {
    52410645: 52410640,
    52411005: 52411000,
}

PUBLISHED = {
    50002200: ("fixed_white_messenger_ribbon", "Central Yharnam - White Messenger Ribbon"),
    52410100: ("fixed_saw_spear", "Central Yharnam - Saw Spear"),
    52410290: ("fixed_saw_hunter_badge", "Central Yharnam - Saw Hunter Badge"),
    52410520: ("fixed_torch", "Central Yharnam - Torch"),
    52410800: (
        "fixed_iosefka_courtyard_bullets",
        "Central Yharnam - Iosefka Courtyard Quicksilver Bullets x10",
    ),
    52411000: (
        "fixed_blood_gem_workshop_tool",
        "Central Yharnam - Blood Gem Workshop Tool",
    ),
}

DISPLAY_OVERRIDES = {
    # The placement points at the first row of a four-row acquisition-flag
    # group (hat/garb/gloves/trousers), not a hat-only pickup.
    52410610: "Hunter Set",
    # Category 8 is generated blood-gem data and has no fixed FMG name.
    52410640: "Generated Blood Gem",
}

FIELDS = (
    "key",
    "name",
    "region",
    "location_flag",
    "item_lot_id",
    "item_category",
    "item_id",
    "classification",
    "source_kind",
    "source_ref",
    "vanilla_award_suppressed",
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def build_rows(repo: Path = REPO) -> list[dict[str, str]]:
    catalog = read_tsv(repo / "research" / "catalog" / "fixed_location_catalog.tsv")
    item_rows = read_tsv(repo / "research" / "catalog" / "fixed_location_items.tsv")
    items_by_flag: dict[int, list[dict[str, str]]] = {}
    for row in item_rows:
        items_by_flag.setdefault(int(row["location_flag"]), []).append(row)

    output: list[dict[str, str]] = []
    for source in catalog:
        if source["canonical_map"] != CANONICAL_MAP:
            continue
        flag = int(source["location_flag"])
        if flag in REPLACEMENT_FLAGS:
            continue
        matches = items_by_flag.get(flag, [])
        if len(matches) != 1:
            raise ValueError(f"flag {flag}: expected one catalog item row, found {len(matches)}")
        item = matches[0]
        lots = source["item_lot_ids"].split(";")
        if item["item_lot_id"] not in lots:
            raise ValueError(f"flag {flag}: item row lot is absent from the location catalog")

        if flag in PUBLISHED:
            key, name = PUBLISHED[flag]
        else:
            lot = item["item_lot_id"]
            key = f"fixed_central_yharnam_lot_{lot}"
            display = DISPLAY_OVERRIDES.get(flag, source["display_items"])
            name = f"Central Yharnam - {display} (Lot {lot})"
        output.append({
            "key": key,
            "name": name,
            "region": "Central Yharnam",
            "location_flag": str(flag),
            "item_lot_id": item["item_lot_id"],
            "item_category": item["category"],
            "item_id": item["item_param_id"],
            "classification": source["classification"],
            "source_kind": "treasure",
            "source_ref": source["map_variants"],
            "vanilla_award_suppressed": "True",
        })
    return output


def render(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=FIELDS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help=f"replace {OUTPUT.relative_to(REPO)}")
    args = parser.parse_args(argv)
    expected = render(build_rows())
    if args.write:
        OUTPUT.write_text(expected, encoding="utf-8", newline="")
        print(f"wrote {OUTPUT} ({expected.count(chr(10)) - 1} locations)")
        return 0
    actual = OUTPUT.read_text(encoding="utf-8")
    if actual != expected:
        print(f"{OUTPUT} is stale; run this command with --write")
        return 1
    print(f"{OUTPUT} matches the catalog ({len(build_rows())} locations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
