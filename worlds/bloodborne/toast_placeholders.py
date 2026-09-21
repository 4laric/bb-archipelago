"""Seed-owned plan for truthful in-game pickup names.

Pickup-name rendering was observed on CUSA03173 01.09 on 2026-09-21.
The plan maps every physical check, including filler, to its seeded item name.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

TOAST_GOODS_START = 900_000
TOAST_GOODS_END = 900_999
TOAST_NAME_LIMIT = 48
TOAST_PLAN_FORMAT = "bb-toast-placeholder-plan-v1"


@dataclass(frozen=True)
class ToastPlacement:
    location_key: str
    location_id: int
    item_lot_id: int
    item_name: str
    recipient: str
    important: bool


@dataclass(frozen=True)
class ToastPlaceholder:
    location_key: str
    location_id: int
    item_lot_id: int
    goods_id: int
    display_name: str


def display_name(item_name: str, recipient: str) -> str:
    """Bound the FMG text while preserving the recipient whenever possible."""
    def bounded(text: str, units: int) -> str:
        return text.encode("utf-16-le")[:units * 2].decode("utf-16-le", errors="ignore")

    suffix = f" ({recipient.strip()})"
    clean = " ".join(item_name.split()) or "Archipelago Item"
    suffix_units = len(suffix.encode("utf-16-le")) // 2
    if suffix_units >= TOAST_NAME_LIMIT:
        return bounded(suffix, TOAST_NAME_LIMIT)
    return bounded(clean, TOAST_NAME_LIMIT - suffix_units).rstrip() + suffix


def build_toast_placeholder_plan(
    placements: Iterable[ToastPlacement],
) -> dict:
    """Allocate stable named goods for every supplied physical pickup, including filler."""
    eligible = sorted(
        placements,
        key=lambda placement: (placement.location_id, placement.location_key),
    )
    capacity = TOAST_GOODS_END - TOAST_GOODS_START + 1
    if len(eligible) > capacity:
        raise ValueError(
            f"toast goods range has {capacity} rows but the seed needs {len(eligible)}"
        )
    lot_ids = [placement.item_lot_id for placement in eligible]
    if len(lot_ids) != len(set(lot_ids)):
        raise ValueError("two toast placements claim the same ItemLotParam row")
    entries = [
        ToastPlaceholder(
            placement.location_key,
            placement.location_id,
            placement.item_lot_id,
            TOAST_GOODS_START + index,
            display_name(placement.item_name, placement.recipient),
        )
        for index, placement in enumerate(eligible)
    ]
    return {
        "format": TOAST_PLAN_FORMAT,
        "enabled": True,
        "evidence": "CUSA03173_01.09_pickup_name_observed_2026-09-21",
        "source_goods_id": 1000,
        "goods_range": [TOAST_GOODS_START, TOAST_GOODS_END],
        "name_limit": TOAST_NAME_LIMIT,
        "entries": [asdict(entry) for entry in entries],
    }
