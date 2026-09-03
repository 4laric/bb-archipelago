"""Audited event-award bridge rows for category-8 AP items (#214)."""

from __future__ import annotations

from dataclasses import dataclass

from .fixed_locations import FIXED_LOCATIONS


@dataclass(frozen=True)
class Category8Award:
    item_key: str
    display_name: str
    token_goods_id: int
    item_lot_id: int
    gemgen_id: int
    ack_flag: int
    source_lot_id: int


# Keep the two live-proven pilot identities stable, then admit every other
# category-8 row in the reviewed fixed-location catalog.  A fixed-location key
# is used for generated identities because GemGenParam ids are recipes, not
# unique item identities (126000, for example, occurs at two checks).
_PILOTS = (
    Category8Award(
        "caryll_rune_communion_1", "Communion (+1 Blood Vial)",
        9_800, 98_000_000, 102_901, 12_400_990, 2_400_640,
    ),
    Category8Award(
        "blood_gem_old_yharnam_123000", "Old Yharnam Blood Gem (123000)",
        9_801, 98_000_001, 123_000, 12_400_991, 2_300_040,
    ),
)

_PILOT_SOURCE_LOTS = frozenset(row.source_lot_id for row in _PILOTS)
_REVIEWED_ROWS = tuple(
    row for row in FIXED_LOCATIONS
    if row.item_category == 8 and row.item_lot_id not in _PILOT_SOURCE_LOTS
)

CATEGORY8_AWARDS = _PILOTS + tuple(
    Category8Award(
        f"category8_{row.key.removeprefix('fixed_')}",
        row.name,
        9_800 + index,
        98_000_000 + index,
        row.item_id,
        12_400_900 + index - len(_PILOTS),
        row.item_lot_id,
    )
    for index, row in enumerate(_REVIEWED_ROWS, start=len(_PILOTS))
)
