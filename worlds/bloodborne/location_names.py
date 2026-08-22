"""Loader for the location-name table owned by docs/LOCATION-NAMING.md.

The TSV is the single source for player-facing location names: fixed
treasures keyed by their catalog acquisition flag, and scripted checks
(boss defeats, EMEVD awards) keyed by their committed event flag. Design
data, read once at import; the naming contract's tests own the ratchets.
"""

from __future__ import annotations

import csv
from pathlib import Path


def _load() -> dict[int, str]:
    path = Path(__file__).with_name("location_names.tsv")
    with path.open(encoding="utf-8", newline="") as handle:
        return {int(row["location_flag"]): row["name"] for row in csv.DictReader(handle, delimiter="\t")}


NAMES_BY_FLAG = _load()


def location_name(flag: int) -> str:
    """The contract name for a check, or a loud failure if the table lacks it."""
    try:
        return NAMES_BY_FLAG[flag]
    except KeyError:
        raise KeyError(f"flag {flag} has no row in location_names.tsv") from None
