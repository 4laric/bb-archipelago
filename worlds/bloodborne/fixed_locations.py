"""Generated fixed-location slice shipped by the Bloodborne world.

The TSV is intentionally data-only and contains no process addresses.  Every
row must be reproducible from the research catalog; tests enforce that
contract.  Adding a region is therefore an append-only data review, not a
Python edit.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

from .resource_data import read_resource_text


@dataclass(frozen=True)
class FixedLocation:
    key: str
    name: str
    region: str
    event_flag: int
    item_lot_id: int
    item_category: int
    item_id: int
    classification: str
    source_kind: str
    source_ref: str
    vanilla_award_suppressed: bool


# Exact GemGenParam ids proven to be fixed Caryll runes by playtest.32 and the
# committed parameter/location audit.  Their native awards remain enabled,
# but they are not AP checks until rune delivery is safe (#214).
VANILLA_ONLY_CARYLL_RUNE_PARAMS = frozenset({
    100001, 100002, 100201, 100301, 100302, 100401, 100802,
    101301, 101302, 101401, 101601, 101701, 101802,
    102001, 102002, 102102, 102202, 102302,
    102901, 102902, 102903, 103104,
})


def _load() -> tuple[FixedLocation, ...]:
    text = read_resource_text("fixed_locations.tsv")
    handle = io.StringIO(text, newline="")
    rows = csv.DictReader(handle, delimiter="\t")
    return tuple(
        FixedLocation(
            key=row["key"],
            name=row["name"],
            region=row["region"],
            event_flag=int(row["location_flag"]),
            item_lot_id=int(row["item_lot_id"]),
            item_category=int(row["item_category"]),
            item_id=int(row["item_id"]),
            classification=row["classification"],
            source_kind=row["source_kind"],
            source_ref=row["source_ref"],
            # Category 8 rows are generated blood-gem recipes, not stable item
            # identities. They remain AP checks but keep their native award so
            # the player receives a valid game-constructed gem.
            vanilla_award_suppressed=(
                row["vanilla_award_suppressed"] == "True"
                and int(row["item_category"]) != 8
            ),
        )
        for row in rows
    )


FIXED_LOCATIONS = _load()
