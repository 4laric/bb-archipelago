"""Strict, writer-facing schema for standalone item placement plans."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

PLAN_FORMAT = "bb-standalone-item-plan-v1"
GAMEPARAM_PATH = "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"
PARAMDEF_PATH = "dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx"
TARGET_ROLES = frozenset({"delivery", "alternative", "retire"})
_SHA256 = re.compile(r"[0-9a-f]{64}")


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class SourceReward:
    item_category: int
    item_id: int
    quantity: int
    acquisition_flag: int

    def as_dict(self) -> dict[str, int]:
        return {
            "item_category": self.item_category,
            "item_id": self.item_id,
            "quantity": self.quantity,
            "acquisition_flag": self.acquisition_flag,
        }


@dataclass(frozen=True)
class AwardTarget:
    item_lot_id: int
    slot: int
    role: str
    source: SourceReward

    def __post_init__(self) -> None:
        if self.item_lot_id < 0 or not 1 <= self.slot <= 8:
            raise ValueError("award target requires a nonnegative lot and slot 1..8")
        if self.role not in TARGET_ROLES:
            raise ValueError(f"unsupported award target role: {self.role}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "item_lot_id": self.item_lot_id,
            "slot": self.slot,
            "role": self.role,
            "source": self.source.as_dict(),
        }


@dataclass(frozen=True)
class Reward:
    item_category: int
    item_id: int
    quantity: int

    def __post_init__(self) -> None:
        if self.item_category == 255:
            raise ValueError("AP-only event-flag effects cannot be standalone rewards")
        if self.item_category not in {0, 1, 4, 8}:
            raise ValueError(f"unsupported ItemLot category: {self.item_category}")
        if self.item_id < 0 or self.quantity <= 0:
            raise ValueError("reward item id and quantity must be positive")

    def as_dict(self) -> dict[str, int]:
        return {
            "item_category": self.item_category,
            "item_id": self.item_id,
            "quantity": self.quantity,
        }


def validate_source_hashes(source_hashes: Mapping[str, str]) -> dict[str, str]:
    normalized = {str(key): str(value).lower() for key, value in source_hashes.items()}
    missing = [
        path for path in (GAMEPARAM_PATH, PARAMDEF_PATH) if path not in normalized
    ]
    if missing:
        raise ValueError(f"source_hashes must pin {', '.join(missing)}")
    for path, value in normalized.items():
        if not path or _SHA256.fullmatch(value) is None:
            raise ValueError(f"invalid source SHA-256 for {path!r}")
    return dict(sorted(normalized.items()))
