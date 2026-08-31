"""Seed-owned plan for truthful in-game pickup names.

The plan is intentionally inert until the item.msgbnd runtime-read probe has
passed.  Generating it now makes the ID allocation, naming policy, and exact
lot-to-name join reviewable without claiming that the game consumes the files.
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
    suffix = f" ({recipient.strip()})"
    clean = " ".join(item_name.split()) or "Archipelago Item"
    if len(suffix) >= TOAST_NAME_LIMIT:
        return suffix[:TOAST_NAME_LIMIT]
    return clean[:TOAST_NAME_LIMIT - len(suffix)].rstrip() + suffix


def build_toast_placeholder_plan(
    placements: Iterable[ToastPlacement],
) -> dict:
    """Allocate stable dummy goods only for useful/progression physical lots.

    Filler keeps the ordinary Blood Vial placeholder.  This is the bounded
    clutter ruling from the toast spec: the in-game name is reserved for the
    placements where knowing the item materially affects routing.
    """
    eligible = sorted(
        (placement for placement in placements if placement.important),
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
        "enabled": False,
        "activation_gate": "item_msgbnd_runtime_read_and_popup_not_modal_probe",
        "source_goods_id": 1000,
        "goods_range": [TOAST_GOODS_START, TOAST_GOODS_END],
        "name_limit": TOAST_NAME_LIMIT,
        "entries": [asdict(entry) for entry in entries],
    }
