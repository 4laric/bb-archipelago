#!/usr/bin/env python3
"""Patch Cathedral Ward's plaza gate source without creating a logic lie.

The committed inputs bundle contains DarkScript's decompiled source, not the
licensed EMEVD binary.  This tool therefore produces a deterministic, guarded
source patch and a manifest suitable for the eventual compile/install stage.
It deliberately does not alter world logic by itself.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FORMAT = "bb-emblem-chokepoint-source-patch-v1"
MAP = "m24_00_00_00"
EVENT = "12400760"
GOODS = 4011
FAR_SIDE_FLAG = 12400170
SUPPORTED_SOURCE_SHA256 = "092fc23411eebb286df20401346b715d8110acbf3b7ca5b79ad494da65144d5c"
OLD = "WaitFor(itemAct || itemAct2 || ObjActEventFlag(12400170));"
NEW = "WaitFor(itemAct || itemAct2);"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def event_body(text: str) -> str:
    marker = f"$Event({EVENT},"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"event {EVENT} is absent")
    next_event = text.find("\n$Event(", start + len(marker))
    return text[start:] if next_event < 0 else text[start:next_event]


def patch(source: bytes) -> bytes:
    actual = sha256(source)
    if actual != SUPPORTED_SOURCE_SHA256:
        raise ValueError(
            f"unsupported {MAP} source sha256 {actual}; expected {SUPPORTED_SOURCE_SHA256}"
        )
    text = source.decode("utf-8-sig")
    body = event_body(text)
    if body.count(OLD) != 1:
        raise ValueError(f"event {EVENT} does not contain exactly one expected far-side wait")
    if body.count("PlayerHasItem(ItemType.Goods, 4011)") != 2:
        raise ValueError(f"event {EVENT} goods-{GOODS} guard shape changed")
    output = text[:]
    absolute = text.find(OLD, text.find(f"$Event({EVENT},"))
    output = output[:absolute] + NEW + output[absolute + len(OLD):]
    if output.count(OLD) != text.count(OLD) - 1:
        raise ValueError("patch changed an unexpected number of far-side waits")
    if event_body(output).count(f"ObjActEventFlag({FAR_SIDE_FLAG})") != 0:
        raise ValueError(f"event {EVENT} still has a far-side success path")
    return output.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--apply", action="store_true")
    ns = parser.parse_args()
    if not ns.apply:
        parser.error("refusing to write without --apply")
    if ns.output.exists() or ns.manifest.exists():
        raise SystemExit("refusing to overwrite output or manifest")
    source = ns.source.read_bytes()
    output = patch(source)
    ns.output.parent.mkdir(parents=True, exist_ok=True)
    ns.output.write_bytes(output)
    manifest = {
        "format": FORMAT,
        "map": MAP,
        "event": EVENT,
        "goods_id": GOODS,
        "removed_success_condition": f"ObjActEventFlag({FAR_SIDE_FLAG})",
        "source_path": str(ns.source.resolve()),
        "source_sha256": sha256(source),
        "output_path": str(ns.output.resolve()),
        "output_sha256": sha256(output),
    }
    ns.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
