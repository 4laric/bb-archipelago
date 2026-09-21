"""Validate the seed's pickup-name plan and select an explicit live canary."""

from __future__ import annotations

from typing import Any

from .core import ValidationError


def pickup_name_plan(value: Any, *, canary_location: str | None = None) -> dict | None:
    if value is None:
        if canary_location is not None:
            raise ValidationError("this seed has no pickup-name plan; generate a new seed")
        return None
    if (not isinstance(value, dict)
            or value.get("format") != "bb-toast-placeholder-plan-v1"
            or type(value.get("enabled")) is not bool
            or value.get("source_goods_id") != 1000
            or not isinstance(value.get("entries"), list)):
        raise ValidationError("invalid pickup-name plan")
    seen = {field: set() for field in ("goods_id", "item_lot_id", "location_id", "location_key")}
    for entry in value["entries"]:
        if not isinstance(entry, dict):
            raise ValidationError("invalid pickup-name entry")
        for field in ("goods_id", "item_lot_id", "location_id"):
            if type(entry.get(field)) is not int or entry[field] < 0:
                raise ValidationError(f"invalid pickup-name {field}")
        if not 900000 <= entry["goods_id"] <= 900999:
            raise ValidationError("pickup-name goods id is outside the reserved range")
        name = entry.get("display_name")
        if (not isinstance(name, str) or not name.strip() or "\x00" in name
                or len(name.encode("utf-16-le")) > 96):
            raise ValidationError("pickup name must contain 1..48 UTF-16 code units")
        if not isinstance(entry.get("location_key"), str) or not entry["location_key"]:
            raise ValidationError("invalid pickup-name location key")
        for field, values in seen.items():
            if entry[field] in values:
                raise ValidationError(f"duplicate pickup-name {field}")
            values.add(entry[field])
    if canary_location is not None:
        entries = [entry for entry in value["entries"]
                   if canary_location == "*" or entry["location_key"] == canary_location]
        if not entries:
            raise ValidationError(f"no named pickup at {canary_location!r}; choose a location from pickup-name-canary --list")
        # Testing is not a passing verdict. The writer has a distinct playtest
        # canary mode so an inert plan never masquerades as probe-confirmed.
        return {**value, "enabled": False, "entries": entries}
    # Older generators emitted this same plan behind an inert rollout flag.
    # The observed rendering path is now enabled for those seeds too, retaining
    # their existing goods allocation and the names they actually contain.
    return {**value, "enabled": True} if value["entries"] else None
