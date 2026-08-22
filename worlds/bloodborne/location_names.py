"""Loader for the location-name table owned by docs/LOCATION-NAMING.md.

The TSV is the single source for player-facing location names: fixed
treasures keyed by their catalog acquisition flag, and scripted checks
(boss defeats, EMEVD awards) keyed by their committed event flag. Design
data, read once at import; the naming contract's tests own the ratchets.
"""

from __future__ import annotations

import csv
import io

from .resource_data import read_resource_text


def _load() -> dict[int, str]:
    text = read_resource_text("location_names.tsv")
    handle = io.StringIO(text, newline="")
    return {int(row["location_flag"]): row["name"] for row in csv.DictReader(handle, delimiter="\t")}


NAMES_BY_FLAG = _load()


def location_name(flag: int) -> str:
    """The contract name for a check, or a loud failure if the table lacks it."""
    try:
        return NAMES_BY_FLAG[flag]
    except KeyError:
        raise KeyError(f"flag {flag} has no row in location_names.tsv") from None
