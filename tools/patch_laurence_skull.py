#!/usr/bin/env python3
"""Build the guarded DarkScript source patch for Laurence's Skull.

The repository may redistribute the decompiled source census, but not a game
EMEVD binary.  This module therefore owns the deterministic source transform
and its manifest; the managed-overlay compiler/install step remains separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


FORMAT = "bb-laurence-skull-source-patch-v1"
MAP = "m24_00_00_00"
EVENT = "12401803"
WITNESS_FLAG = 12401898
PASSWORD_FLAG = 12401803
SUPPORTED_SOURCE_SHA256 = "092fc23411eebb286df20401346b715d8110acbf3b7ca5b79ad494da65144d5c"
OLD_GUARD = "    EndIf(ThisEvent());"
NEW_GUARD = f"    EndIf(EventFlag({WITNESS_FLAG}));"
OLD_TAIL = "    SetEventFlag(9180, OFF);\n});"
NEW_TAIL = (
    "    SetEventFlag(9180, OFF);\n"
    f"    SetEventFlag({WITNESS_FLAG}, ON);\n"
    "    RestartEvent();\n"
    "});"
)


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
    text = source.decode("utf-8-sig").replace("\r\n", "\n")
    body = event_body(text)
    if body.count(OLD_GUARD) != 1 or body.count(OLD_TAIL) != 1:
        raise ValueError(f"event {EVENT} does not have the supported interaction shape")

    patched_body = body.replace(OLD_GUARD, NEW_GUARD, 1).replace(OLD_TAIL, NEW_TAIL, 1)
    if f"SetEventFlag({PASSWORD_FLAG}, ON)" in patched_body:
        raise ValueError("altar patch must not write the shuffled password flag")
    if patched_body.count(f"SetEventFlag({WITNESS_FLAG}, ON)") != 1:
        raise ValueError("altar patch must write exactly one synthetic witness")
    if patched_body.count("RestartEvent();") != body.count("RestartEvent();") + 1:
        raise ValueError("altar patch must restart instead of completing its own event flag")

    start = text.index(f"$Event({EVENT},")
    return (text[:start] + patched_body + text[start + len(body) :]).encode("utf-8")


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
    ns.manifest.write_text(
        json.dumps(
            {
                "format": FORMAT,
                "map": MAP,
                "event": EVENT,
                "synthetic_witness_flag": WITNESS_FLAG,
                "suppressed_vanilla_completion_flag": PASSWORD_FLAG,
                "source_path": str(ns.source.resolve()),
                "source_sha256": sha256(source),
                "output_path": str(ns.output.resolve()),
                "output_sha256": sha256(output),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
