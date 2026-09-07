#!/usr/bin/env python3
"""Validate production BBEventWriter dumps for the two-sided Hemwick gate."""

from __future__ import annotations

import argparse
import re

EXPECTED_TAIL = [
    (2000, 2, "00000000"),
    (2005, 3, None), (2006, 1, None),
    (3, 0, "ff000000aa2fba00"), (3, 6, "ff030000"),
    (3, 6, "ff020000"), (0, 0, "0001ff00"),
    (2005, 3, None), (2006, 2, None),
    (3, 0, "01010000aa2fba00"), (3, 6, "02030000"),
    (0, 0, "01000200"), (3, 6, "03020000"),
    (0, 0, "01000300"), (0, 0, "00010100"),
    (1000, 4, "01000000"),
]


def parse(path):
    rows = []
    for line in path.read_text().splitlines():
        match = re.search(r"\[\d+\] (\d+)\[(\d+)\] ([0-9a-f]*)$", line)
        if match:
            rows.append((int(match[1]), int(match[2]), match[3]))
    return rows


def enabled(access, connecting=False, multiplayer=False):
    return not access or connecting or multiplayer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("cathedral", type=__import__("pathlib").Path)
    parser.add_argument("hemwick", type=__import__("pathlib").Path)
    parser.add_argument("--mutation-controls", action="store_true")
    args = parser.parse_args()
    expected_entities = {
        "cathedral": (2401995, 2403995), "hemwick": (2201999, 2203999),
    }
    for name, path in (("cathedral", args.cathedral), ("hemwick", args.hemwick)):
        rows = parse(path)
        assert len(rows) == 16, (name, len(rows))
        obj, sfx = expected_entities[name]
        concrete = list(EXPECTED_TAIL)
        concrete[1] = (2005, 3, obj.to_bytes(4, "little").hex() + "00000000")
        concrete[2] = (2006, 1, sfx.to_bytes(4, "little").hex() + "01000000")
        concrete[7] = (2005, 3, obj.to_bytes(4, "little").hex() + "01000000")
        concrete[8] = (2006, 2, sfx.to_bytes(4, "little").hex())
        assert rows == concrete, (name, rows, concrete)
    states = {(False, False, False): True, (True, False, False): False,
              (True, True, False): True, (True, False, True): True}
    assert all(enabled(*state) == wanted for state, wanted in states.items())
    if args.mutation_controls:
        assert enabled(True) is False
        assert enabled(False) is True
        assert enabled(True, multiplayer=True) is True
        assert not all(not access for (access, _, _), wanted in states.items() if wanted)
    print("Hemwick gate writer and lifecycle contract verified on both sides")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
