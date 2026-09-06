#!/usr/bin/env python3
"""Guard the two sides of the Cathedral Ward--Hemwick boundary fog."""

from __future__ import annotations

import hashlib
import argparse
from pathlib import Path

ACCESS_FLAG = 12201898
GATE_EVENT = {"m22_00_00_00": 12209990, "m24_00_00_00": 12409990}
BOUNDARY = {
    "m22_00_00_00": (0, 2201999, 2203999),
    "m24_00_00_00": (24, 2401995, 2403995),
}
SUPPORTED_SOURCE_SHA256 = {
    "m22_00_00_00": "ebba03cdcbb9783ae2f6bb72f5681ab97c4a3dd0082c8f9af82e2ea12bb83cdb",
    "m24_00_00_00": "092fc23411eebb286df20401346b715d8110acbf3b7ca5b79ad494da65144d5c",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch(source: bytes, map_name: str, *, verify_source: bool = True) -> bytes:
    if map_name not in BOUNDARY:
        raise ValueError(f"unsupported Hemwick boundary map {map_name}")
    if verify_source and sha256(source) != SUPPORTED_SOURCE_SHA256[map_name]:
        raise ValueError(f"unsupported {map_name} source sha256 {sha256(source)}")
    slot, obj, sfx = BOUNDARY[map_name]
    old = f"    $InitializeEvent({slot}, 7600, {obj}, {sfx});"
    new = f"    $InitializeEvent(0, {GATE_EVENT[map_name]});"
    text = source.decode("utf-8-sig")
    if text.count(old) != 1:
        raise ValueError(f"{map_name} does not contain exactly one boundary initializer")
    text = text.replace(old, new, 1)
    event = f"""

// AP Hemwick access gate. The wall remains active while either the AP item is
// absent or multiplayer confinement is active, and recomputes after each edge.
$Event({GATE_EVENT[map_name]}, Restart, function() {{
    SetNetworkSyncState(Disabled);
    DeactivateObject({obj}, Disabled);
    DeleteMapSFX({sfx}, true);
    WaitFor(
        !EventFlag({ACCESS_FLAG})
            || HasMultiplayerState(MultiplayerState.ConnectingtoMultiplayer)
            || HasMultiplayerState(MultiplayerState.Multiplayer));
    DeactivateObject({obj}, Enabled);
    SpawnMapSFX({sfx});
    WaitFor(
        EventFlag({ACCESS_FLAG})
            && !HasMultiplayerState(MultiplayerState.ConnectingtoMultiplayer)
            && !HasMultiplayerState(MultiplayerState.Multiplayer));
    RestartEvent();
}});
"""
    return (text.rstrip() + event).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("map_name", choices=sorted(BOUNDARY))
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.apply:
        parser.error("refusing to write without --apply")
    if args.output.exists():
        raise FileExistsError(f"refusing to overwrite {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patch(args.source.read_bytes(), args.map_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
