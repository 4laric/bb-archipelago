#!/usr/bin/env python3
"""Write the widest seed contract this apworld can emit, as slot_data JSON.

CI feeds it to the built client (`bb-ap-client --check-contract`) so a world
that publishes a binding the client cannot accept fails the release instead
of the first player's launch (clients#607 was exactly that).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def widest_slot_data() -> dict:
    from worlds.bloodborne import FULL_POOL_ITEM_KEYS, STARTING_TOOL_KEYS, build_runtime_slot_data
    from worlds.bloodborne.data import ATTIRE_ITEM_KEYS, UNCANNY_ITEM_KEYS

    return build_runtime_slot_data(
        FULL_POOL_ITEM_KEYS | UNCANNY_ITEM_KEYS | ATTIRE_ITEM_KEYS | STARTING_TOOL_KEYS
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    slot_data = widest_slot_data()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(slot_data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {args.output}: {len(slot_data['runtime_items'])} items, "
        f"{len(slot_data['runtime_locations'])} locations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
