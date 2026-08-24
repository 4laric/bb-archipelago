"""Compare the CE-assembled cave bytes against bb_native_delivery's frozen payload.

Owner validation checklist item 1 (docs/SPEC-client-without-cheat-engine.md):
with the grant table loaded and armed by Cheat Engine as usual, read back the
two caves from the live process and diff them against the prototype's
relocated blobs. Agreement promotes the payload encoding from `inferred` to
`validated`; disagreement means the CE table is right and the prototype is
wrong.

Read-only: opens the process without write access and never patches anything.

Usage (repo root, launcher chain already running and bridge armed):
    python -m tools.compare_ce_payload --pid <shadPS4 pid> [--base 0x...]

Without --base the eboot base comes from the shadPS4 log, then is verified
against the image the same way `verify` does.
"""

from __future__ import annotations

import argparse
import sys

from tools.bb_native_delivery.payload import consume_cave, heartbeat_cave
from tools.bb_native_delivery.process import (
    ProcessMemory,
    default_shad_log,
    logged_eboot_base,
    verify_base,
)


def _hexdiff(name: str, expected: bytes, actual: bytes) -> int:
    diffs = [i for i, (e, a) in enumerate(zip(expected, actual)) if e != a]
    if not diffs:
        print(f"[PASS] {name}: {len(expected)} bytes identical")
        return 0
    print(f"[FAIL] {name}: {len(diffs)} of {len(expected)} bytes differ; first at +0x{diffs[0]:X}")
    for off in diffs[:8]:
        lo, hi = max(0, off - 4), min(len(expected), off + 5)
        print(f"       +0x{off:03X} expected {expected[lo:hi].hex(' ')}")
        print(f"               actual   {actual[lo:hi].hex(' ')}")
    if len(diffs) > 8:
        print(f"       ... {len(diffs) - 8} more differing offsets")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--base", type=lambda v: int(v, 0), default=None)
    parser.add_argument("--shad-log", default=None)
    parser.add_argument(
        "--armed",
        action="store_true",
        help=(
            "the CE table is already installed: the hook sites now hold E9 "
            "detours, so the original-bytes image check cannot pass. Trust "
            "--base (from the table's AUTO V5 READY line) and confirm a detour "
            "is present at each hook instead."
        ),
    )
    args = parser.parse_args()

    with ProcessMemory(args.pid, writable=False) as memory:
        base = args.base
        if base is None:
            log_path = args.shad_log or default_shad_log()
            text = open(log_path, "r", errors="replace").read()
            base = logged_eboot_base(text)
            if base is None:
                print(f"no eboot base found in {log_path}; pass --base", file=sys.stderr)
                return 2
        if args.armed:
            if args.base is None:
                print("--armed requires --base (from the AUTO V5 READY line)", file=sys.stderr)
                return 2
            for name, rva in (("consume_hook", 0x14D9575), ("heartbeat_hook", 0x1BFE882)):
                first = memory.read(base + rva, 1)
                if first != b"\xE9":
                    print(
                        f"eboot base 0x{base:X}: no E9 detour at {name}+0x{rva:X} "
                        f"(found 0x{first.hex().upper()}) -- wrong base, or the table is not armed",
                        file=sys.stderr,
                    )
                    return 2
            print(f"eboot base 0x{base:X} confirmed armed (E9 detours present at both hooks)")
        elif not verify_base(memory, base):
            print(
                f"eboot base 0x{base:X} failed image verification. If the CE table is "
                f"already loaded, the hook originals are overwritten -- rerun with --armed.",
                file=sys.stderr,
            )
            return 2
        else:
            print(f"eboot base 0x{base:X} verified (unarmed image)")

        failures = 0
        for blob in (consume_cave(), heartbeat_cave()):
            expected = blob.relocated(base)
            actual = memory.read(base + blob.rva, len(expected))
            if actual == expected and all(b == 0 for b in actual):
                print(f"[FAIL] {blob.name}: cave is all zeroes -- CE table not loaded/armed?")
                failures += 1
                continue
            failures += _hexdiff(f"{blob.name} (eboot+0x{blob.rva:X})", expected, actual)

    if failures:
        print("\nRESULT: MISMATCH -- the CE table is the reference; the prototype encoding is wrong.")
        return 1
    print("\nRESULT: MATCH -- payload encoding is confirmed against CE's assembled bytes.")
    print("Record this run; it promotes the payload label from `inferred` to `validated`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
