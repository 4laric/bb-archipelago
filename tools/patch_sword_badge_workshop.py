#!/usr/bin/env python3
"""Gate Cathedral Ward's Healing Church Workshop door on Sword Hunter Badge."""

from __future__ import annotations

import hashlib


MAP = "m24_00_00_00"
EVENT = "12405710"
BADGE_GOODS = 4114
BSB_MIRROR_FLAG = 9453
SUPPORTED_SOURCE_SHA256 = "092fc23411eebb286df20401346b715d8110acbf3b7ca5b79ad494da65144d5c"
OLD = "    if (EventFlag(9453)) {"
NEW = "    if (PlayerHasItem(ItemType.Goods, 4114)) {"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_body(text: str) -> str:
    marker = f"$Event({EVENT},"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"event {EVENT} is absent")
    next_event = text.find("\n$Event(", start + len(marker))
    return text[start:] if next_event < 0 else text[start:next_event]


def patch(source: bytes, *, verify_source: bool = True) -> bytes:
    actual = sha256(source)
    if verify_source and actual != SUPPORTED_SOURCE_SHA256:
        raise ValueError(
            f"unsupported {MAP} source sha256 {actual}; expected {SUPPORTED_SOURCE_SHA256}"
        )
    text = source.decode("utf-8-sig")
    body = event_body(text)
    if body.count(OLD) != 1:
        raise ValueError(f"event {EVENT} does not contain exactly one expected BSB guard")
    if "ReproduceObjectAnimation(2401202, 1);" not in body:
        raise ValueError(f"event {EVENT} no longer controls the expected Workshop door")
    start = text.find(f"$Event({EVENT},")
    absolute = text.find(OLD, start)
    output = text[:absolute] + NEW + text[absolute + len(OLD):]
    changed = event_body(output)
    if f"EventFlag({BSB_MIRROR_FLAG})" in changed:
        raise ValueError(f"event {EVENT} still opens from the BSB mirror flag")
    if changed.count(f"PlayerHasItem(ItemType.Goods, {BADGE_GOODS})") != 1:
        raise ValueError(f"event {EVENT} does not have exactly one badge guard")
    return output.encode("utf-8")
