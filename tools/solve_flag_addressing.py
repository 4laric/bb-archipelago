#!/usr/bin/env python3
"""Solve the flag-id to memory-address mapping from captured bit transitions.

The session captures which *bit* moved when a pickup was taken. We already know
which *flag id* that pickup sets, from the static ItemLotParam join. So the
session is not a search for "a flag" — it is two known points on an unknown
line, and this solves for the line.

    id = (byte_offset - base_byte) * 8 + bit_within_byte * bit_sign + constant

Elden Ring's, for reference, is `id = offset*8 + (7-bit) + 50000`, i.e. bits are
numbered high-to-low within the byte. Bloodborne's packing is unknown, so both
bit orders are tried and the one that fits every observation wins.

⭐ Two observations with widely separated ids over-determine the mapping, so a
single session can *solve* it rather than merely locate one bit. A third
observation is the check: it must be predicted, not fitted.

    python tools/solve_flag_addressing.py \\
        --observation 52410100=0x1A4C:3 \\
        --observation 50002200=0x0F20:6 \\
        --predict 52410140
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path


@dataclass(frozen=True)
class Observation:
    flag_id: int
    byte_offset: int
    bit: int

    @classmethod
    def parse(cls, text: str) -> "Observation":
        try:
            flag, position = text.split("=", 1)
            offset, bit = position.split(":", 1)
            return cls(int(flag), int(offset, 0), int(bit, 0))
        except ValueError as exc:
            raise SystemExit(f"bad observation {text!r}; expected FLAG=OFFSET:BIT") from exc


@dataclass(frozen=True)
class Mapping:
    """id = (byte_offset * 8) + bit_term + constant, bit_term per bit_order."""

    constant: int
    bit_order: str          # "msb0" (7-bit, Elden Ring's) or "lsb0" (bit)

    def bit_term(self, bit: int) -> int:
        return (7 - bit) if self.bit_order == "msb0" else bit

    def flag_for(self, byte_offset: int, bit: int) -> int:
        return byte_offset * 8 + self.bit_term(bit) + self.constant

    def address_for(self, flag_id: int) -> tuple[int, int]:
        delta = flag_id - self.constant
        byte_offset, bit_term = divmod(delta, 8)
        bit = (7 - bit_term) if self.bit_order == "msb0" else bit_term
        return byte_offset, bit

    def describe(self) -> str:
        sign = "+" if self.constant >= 0 else "-"
        term = "(7 - bit)" if self.bit_order == "msb0" else "bit"
        return f"id = byte_offset * 8 + {term} {sign} {abs(self.constant)}"


def solve(observations: list[Observation]) -> list[Mapping]:
    """Every mapping consistent with every observation. Usually zero or one."""
    fits: list[Mapping] = []
    for bit_order in ("msb0", "lsb0"):
        probe = Mapping(0, bit_order)
        constants = {o.flag_id - probe.flag_for(o.byte_offset, o.bit) for o in observations}
        if len(constants) == 1:
            fits.append(Mapping(constants.pop(), bit_order))
    return fits


def load_intersection(path: Path) -> list[tuple[int, int]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return [(int(row["ByteOffset"]), int(row["Bit"])) for row in csv.DictReader(handle)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--observation", action="append", default=[], metavar="FLAG=OFFSET:BIT",
                        help="a known flag id and where its bit moved")
    parser.add_argument("--predict", action="append", type=int, default=[], metavar="FLAG",
                        help="flag id to locate once the mapping is solved")
    parser.add_argument("--intersection", type=Path, default=None,
                        help="an intersection.csv, to check a solved mapping against it")
    args = parser.parse_args(argv)

    observations = [Observation.parse(text) for text in args.observation]
    if len(observations) < 2:
        print("Give at least two observations. One point does not determine a line, and a "
              "mapping fitted to a single pickup will 'work' on that pickup and nothing else.",
              file=sys.stderr)
        return 2

    fits = solve(observations)
    if not fits:
        print("No linear mapping fits these observations. Either a capture is wrong, the "
              "flags are not packed contiguously, or the region base moved between trials.",
              file=sys.stderr)
        for o in observations:
            print(f"  flag {o.flag_id} at byte 0x{o.byte_offset:X} bit {o.bit}", file=sys.stderr)
        return 1
    if len(fits) > 1:
        print("Ambiguous: more than one packing fits. Add an observation whose bit index "
              "is not symmetric (anything other than bit 3 or 4).", file=sys.stderr)

    for mapping in fits:
        print(f"SOLVED  {mapping.describe()}")
        print(f"        bit order {mapping.bit_order}, constant {mapping.constant}")
        for o in observations:
            got = mapping.flag_for(o.byte_offset, o.bit)
            print(f"          check flag {o.flag_id} -> {got} {'ok' if got == o.flag_id else 'MISMATCH'}")
        for flag in args.predict:
            byte_offset, bit = mapping.address_for(flag)
            print(f"        PREDICTS flag {flag} at byte 0x{byte_offset:X} bit {bit}")
            print(f"                 verify by taking that pickup; a prediction that holds is "
                  f"the evidence, a fit is not")
        if args.intersection:
            present = set(load_intersection(args.intersection))
            for flag in args.predict:
                position = mapping.address_for(flag)
                mark = "PRESENT" if position in present else "absent"
                print(f"        flag {flag} at 0x{position[0]:X}:{position[1]} is {mark} "
                      f"in {args.intersection.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
