#!/usr/bin/env python3
"""Build the deterministic fixed-pickup manifest for the playable slice.

The research catalog contains one row per acquisition flag and repeats the
same physical placements for the map's runtime variants.  The shipped manifest
uses the canonical map row for each map in ``SLICE_MAPS``, collapses the
NG-cycle replacement lots onto their first-playthrough physical locations, and
keeps the previously published stable keys.

``SLICE_MAPS`` is the whole scope statement.  Slice 1 was ``m24_01_00_00``
alone (Central Yharnam through Father Gascoigne).  Slice 3 adds
``m24_00_00_00`` (Cathedral Ward) and ``m23_00_00_00`` (Old Yharnam through
the Blood-starved Beast). Slice 4 adds ``m22_00_00_00`` (Hemwick) and
``m25_00_00_00`` (Cainhurst). Slice 5 adds ``m27_00_00_00`` (Forbidden
Woods); m32's reviewed fixed rows belong to the Lecture Building and remain
deferred even though Rom shares that archive. The queue-jumped optional
Nightmare Frontier slice adds ``m33_00_00_00``. The map ids are read off
``research/catalog/fixed_location_catalog.tsv``; none of them is guessed.

Player-facing names come from ``worlds/bloodborne/location_names.tsv``, the
single source defined by docs/LOCATION-NAMING.md; this tool never invents one.
The ``region`` column is the logic placement.  It defaults per map, and
``REGION_OVERRIDES`` places the rows whose real gate is not their map's
default (issue #124).  The default is cross-checked against the reviewed
``region`` column of the name table, so a disagreement is a build failure
rather than a silent mis-placement.

Evidence discipline: every emitted row is a *catalog* row.  ``source_kind`` is
``treasure`` because the flag/lot pair also appears in
``research/joined/fixed_location_event_refs.tsv`` (the MSB/EMEVD placement
join), and ``source_ref`` is the catalog's own ``map_variants`` string.  A row
that exists only in ``research/joined/lot_items.tsv`` is not a placement and
never reaches this manifest.
"""

from __future__ import annotations

import argparse
import csv
import io
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]

# The playable scope, in emission order. Appending a map appends rows; it never
# reorders or renumbers the rows already published.
SLICE_MAPS = (
    "m24_01_00_00", "m24_00_00_00", "m23_00_00_00",
    "m22_00_00_00", "m25_00_00_00",
    "m27_00_00_00",
    "m33_00_00_00",
)

# Per-map defaults for the two data-only columns a catalog row cannot supply.
MAP_DEFAULT_REGION = {
    "m24_01_00_00": "Central Yharnam",
    "m24_00_00_00": "Cathedral Ward",
    "m23_00_00_00": "Old Yharnam",
    "m22_00_00_00": "Hemwick Charnel Lane",
    "m25_00_00_00": "Castle Cainhurst",
    "m27_00_00_00": "Forbidden Woods",
    "m33_00_00_00": "Nightmare Frontier",
}
MAP_KEY_PREFIX = {
    "m24_01_00_00": "fixed_central_yharnam_lot_",
    "m24_00_00_00": "fixed_cathedral_ward_lot_",
    "m23_00_00_00": "fixed_old_yharnam_lot_",
    "m22_00_00_00": "fixed_hemwick_lot_",
    "m25_00_00_00": "fixed_cainhurst_lot_",
    "m27_00_00_00": "fixed_forbidden_woods_lot_",
    "m33_00_00_00": "fixed_nightmare_frontier_lot_",
}

OUTPUT = REPO / "worlds" / "bloodborne" / "fixed_locations.tsv"
NAMES = REPO / "worlds" / "bloodborne" / "location_names.tsv"

# These rows occupy the same physical chest as the first-cycle row they point
# at and are selected only when the unique first-cycle reward was already
# owned. The catalog's event name says so: each carries the same chest ordinal
# plus 差し替え ("replacement") or the replaced chest's number.
REPLACEMENT_FLAGS = {
    52410645: 52410640,   # Item 宝箱05（差し替え用）
    52411005: 52411000,   # Item 宝箱02（差し替え用）
    52400485: 52400480,   # Item 宝箱01（05 アイテム差し替え）
    52420645: 52420640,   # Item 宝箱03（差し替え用）
    52420695: 52420690,   # Item_宝箱04（差し替え用）
}

# Catalog rows inside a slice map that deliberately do not become manifest
# rows. Each needs a reason; "it looked wrong" is not one.
EXCLUDED_FLAGS = {
    52400480: (
        "already published by data.py as treasure_radiant_sword_hunter_badge "
        "with its own permanent network id and runtime binding"
    ),
    52420320: (
        "the acquisition flag is shared between an m24_00 dummy corpse and the "
        "real m24_02 placement; the reviewed name table places the real spot in "
        "Upper Cathedral Ward, outside this slice"
    ),
    52200360: (
        "already published by data.py as treasure_rune_workshop_tool with "
        "its own permanent network id and runtime binding"
    ),
    52500250: (
        "already published by data.py as treasure_executioners_gloves with "
        "its own permanent network id and runtime binding"
    ),
    53300330: (
        "already published by data.py as treasure_messengers_gift"
    ),
}

# Stable keys for rows the datapackage published before the name table
# existed. Keys are wire identifiers and never change; names live in the
# name table.
PUBLISHED_KEYS = {
    50002200: "fixed_white_messenger_ribbon",
    52410100: "fixed_saw_spear",
    52410290: "fixed_saw_hunter_badge",
    52410520: "fixed_torch",
    52410800: "fixed_iosefka_courtyard_bullets",
    52411000: "fixed_blood_gem_workshop_tool",
}

# Placements behind intra-map gates in m24_01 (issue #124, verified against
# the wiki, the catalog coordinates, and playtester reports):
# - 52410140 / 52410640: clinic back yard (`診療所外` anchor), unlocked only
#   via the Forbidden Woods cave passage.
# - 52410920: ledge above the Tomb of Oedon; the approach is through the
#   Gascoigne arena's post-fight exit.
# - 52411000: library chest between the Gascoigne arena and the Cathedral
#   Ward lamp, gated by event_gascoigne_defeated.
# The clinic front courtyard (52410800) stays in Central Yharnam: it is
# reachable at sphere 1 on the way out of the clinic.
REGION_OVERRIDES = {
    52410140: "Iosefka's Clinic",
    52410640: "Iosefka's Clinic",
    52410920: "Cathedral Ward",
    52411000: "Cathedral Ward",
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
    name_table = read_tsv(repo / "worlds" / "bloodborne" / "location_names.tsv")
    names_by_flag = {int(r["location_flag"]): r["name"] for r in name_table}
    regions_by_flag = {int(r["location_flag"]): r["region"] for r in name_table}
    event_refs = {
        (row["acquisition_flag"], row["item_lot_id"])
        for row in read_tsv(repo / "research" / "joined" / "fixed_location_event_refs.tsv")
    }
    items_by_flag: dict[int, list[dict[str, str]]] = {}
    for row in item_rows:
        items_by_flag.setdefault(int(row["location_flag"]), []).append(row)

    output: list[dict[str, str]] = []
    for canonical_map in SLICE_MAPS:
        for source in catalog:
            if source["canonical_map"] != canonical_map:
                continue
            flag = int(source["location_flag"])
            if flag in REPLACEMENT_FLAGS or flag in EXCLUDED_FLAGS:
                continue
            matches = items_by_flag.get(flag, [])
            if len(matches) != 1:
                raise ValueError(
                    f"flag {flag}: expected one catalog item row, found {len(matches)}")
            item = matches[0]
            lots = source["item_lot_ids"].split(";")
            if item["item_lot_id"] not in lots:
                raise ValueError(f"flag {flag}: item row lot is absent from the location catalog")
            if (str(flag), item["item_lot_id"]) not in event_refs:
                raise ValueError(
                    f"flag {flag}: no MSB/EMEVD placement reference for lot "
                    f"{item['item_lot_id']}; a lot_items row alone is not a placement")
            if flag not in names_by_flag:
                raise ValueError(f"flag {flag}: no name in {NAMES.relative_to(REPO)}")

            region = REGION_OVERRIDES.get(flag, MAP_DEFAULT_REGION[canonical_map])
            reviewed = regions_by_flag[flag]
            if flag not in REGION_OVERRIDES and reviewed != region:
                raise ValueError(
                    f"flag {flag}: the name table reviews this row as {reviewed!r} but "
                    f"{canonical_map} defaults to {region!r}; add a REGION_OVERRIDES or "
                    "EXCLUDED_FLAGS entry with a reason instead of shipping the disagreement")

            key = PUBLISHED_KEYS.get(flag, MAP_KEY_PREFIX[canonical_map] + item["item_lot_id"])
            output.append({
                "key": key,
                "name": names_by_flag[flag],
                "region": region,
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
