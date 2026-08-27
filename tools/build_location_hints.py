#!/usr/bin/env python3
"""Append landmark hints to the player-facing location names (issue #222).

docs/LOCATION-NAMING.md owns the convention; this tool is the mechanical half
of it. It appends ``(hint)`` to rows of
``worlds/bloodborne/location_names.tsv`` and records where the hint came from
in the row's ``basis``, from three sources in trust order:

1. the developers' own ``lot_name`` area tag, translated per map through
   ``docs/location_hint_vocabulary.tsv``;
2. MSB signals -- currently ``in_chest``, read from the inputs bundle's
   ``mined/msb_treasures.tsv`` when it is available;
3. ``docs/location_hint_overrides.tsv``, the hand-written hints, each with its
   own evidence note.

It never invents a hint, never overwrites one a row already carries, and never
touches the ``#N`` disambiguator: the ordinal stays exactly where it is so
tracker packs and player muscle memory do not churn when a hint would have
de-collided the name. Re-running is a no-op.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
NAMES = REPO / "worlds" / "bloodborne" / "location_names.tsv"
CATALOG = REPO / "research" / "catalog" / "fixed_location_catalog.tsv"
LOT_ITEMS = REPO / "research" / "joined" / "lot_items.tsv"
VOCAB = REPO / "docs" / "location_hint_vocabulary.tsv"
OVERRIDES = REPO / "docs" / "location_hint_overrides.tsv"

FLOOR = re.compile(r"(\d(?:\.\d)?)F")

# Rows this pass leaves alone. 52410295 is the NG+ replacement corpse retired
# by #221: no first playthrough can reach it, so it is not a spot a player
# hunts and a landmark for it would be noise.
EXEMPT = {"52410295"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        # QUOTE_NONE: the table has never quoted, and several `basis` cells
        # carry literal quotes from the #75 rename notes. Minimal quoting would
        # rewrite every one of them and bury the change in noise.
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
            quoting=csv.QUOTE_NONE,
            quotechar="",
        )
        writer.writeheader()
        writer.writerows(rows)


def lot_names_by_flag() -> dict[str, str]:
    """flag -> the first lot_name that awards it.

    The join is on the acquisition flag, never on the lot name.
    """
    out: dict[str, str] = {}
    for row in read_tsv(LOT_ITEMS):
        for flag in (row["all_acquisition_flags"] or "").split(";"):
            if flag:
                out.setdefault(flag, row["lot_name"])
    return out


def vocabulary() -> dict[str, list[tuple[str, str]]]:
    """map -> [(tag, hint)], longest tag first so a refinement wins."""
    out: dict[str, list[tuple[str, str]]] = {}
    for row in read_tsv(VOCAB):
        out.setdefault(row["canonical_map"], []).append((row["tag"], row["hint"]))
    for entries in out.values():
        entries.sort(key=lambda pair: len(pair[0]), reverse=True)
    return out


def has_hint(name: str) -> bool:
    """True if the name already ends in a place hint.

    A trailing ``(1)``/``(2)`` is part of an item name (``Coldblood Dew (1)``),
    not a hint, so a purely numeric parenthetical does not count.
    """
    if not name.endswith(")"):
        return False
    inner = name[name.rindex("(") + 1 : -1]
    return not inner.isdigit()


def tag_hint(
    lot_name: str, canonical_map: str, vocab: dict[str, list[tuple[str, str]]]
) -> tuple[str, str] | None:
    for tag, hint in vocab.get(canonical_map, ()):
        if tag in lot_name:
            if hint == "tower":
                floor = FLOOR.search(lot_name)
                if floor:
                    hint = f"tower {floor.group(1)}F"
            return hint, tag
    return None


def in_chest_lots(msb: Path | None) -> set[str]:
    if msb is None or not msb.exists():
        return set()
    lots: set[str] = set()
    for row in read_tsv(msb):
        if row["in_chest"] != "True":
            continue
        for column in ("item_lot_1", "item_lot_2", "item_lot_3"):
            value = row[column]
            if value and value != "-1":
                lots.add(value)
    return lots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--msb",
        type=Path,
        default=None,
        help="mined/msb_treasures.tsv from the inputs bundle; chest hints are "
        "skipped when it is absent",
    )
    parser.add_argument("--check", action="store_true", help="report, write nothing")
    args = parser.parse_args()

    names = read_tsv(NAMES)
    catalog = {row["location_flag"]: row for row in read_tsv(CATALOG)}
    lots = lot_names_by_flag()
    vocab = vocabulary()
    overrides = {row["location_flag"]: row for row in read_tsv(OVERRIDES)}
    chests = in_chest_lots(args.msb)

    hinted = 0
    for row in names:
        flag = row["location_flag"]
        if flag in EXEMPT or has_hint(row["name"]):
            continue

        override = overrides.get(flag)
        if override:
            row["name"] = f"{row['name']} ({override['hint']})"
            row["basis"] = f"{row['basis']}; hint hand-written: {override['note']}"
            hinted += 1
            continue

        entry = catalog.get(flag)
        if entry is None:
            continue
        parts: list[str] = []
        provenance: list[str] = []

        found = tag_hint(lots.get(flag, ""), entry["canonical_map"], vocab)
        if found:
            hint, tag = found
            parts.append(hint)
            provenance.append(f"hint from lot tag {tag} ({entry['canonical_map']})")

        if any(lot in chests for lot in entry["item_lot_ids"].split(";")):
            if not any("chest" in part for part in parts):
                parts.append("chest")
                provenance.append("hint from MSB in_chest")

        if not parts:
            continue
        row["name"] = f"{row['name']} ({' '.join(parts)})"
        row["basis"] = "; ".join([row["basis"], *provenance])
        hinted += 1

    bare = sum(1 for row in names if not has_hint(row["name"]))
    print(f"hinted {hinted}; {len(names) - bare} of {len(names)} rows now carry a hint")
    duplicates = len(names) - len({row["name"] for row in names})
    if duplicates:
        raise SystemExit(f"{duplicates} duplicate names after hinting")
    for row in names:
        if not row["name"].isascii():
            raise SystemExit(f"non-ASCII name: {row['name']!r}")
    if not args.check:
        write_tsv(NAMES, ["location_flag", "region", "name", "basis"], names)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
