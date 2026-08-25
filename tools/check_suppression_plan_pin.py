#!/usr/bin/env python3
"""Fail if a binder build's plan does not match the pin the world ships.

`worlds/bloodborne/__init__.py` pins `SUPPRESSION_PLAN_SHA256` and stamps it
into every seed's slot data; the launcher refuses to arm a binder whose
manifest `plan_sha256` disagrees with the seed. Until now nothing rebuilt the
binder from the repo, so the pin was asserted, not reproduced: a plan change
that forgot to move the pin (or a pin change with no plan behind it) shipped a
seed no binder could ever satisfy.

This script closes that gap. Given a `build-manifest.json` written by
`tools/build_vanilla_suppression.ps1`, it compares the manifest's
`plan_sha256` against the pin, read from the world source by parsing (never by
import -- the world only imports inside Archipelago).

A missing or malformed manifest is a failure, never a silent pass: an
unreadable build is not evidence of agreement.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORLD_SOURCE = REPO / "worlds" / "bloodborne" / "__init__.py"
MANIFEST_FORMAT = "bb-vanilla-suppression-build-v1"
_PIN_PATTERN = re.compile(
    r'^SUPPRESSION_PLAN_SHA256\s*=\s*"([0-9a-f]{64})"\s*$', re.MULTILINE
)


def read_pin(world_source: Path) -> str:
    text = world_source.read_text(encoding="utf-8")
    matches = _PIN_PATTERN.findall(text)
    if len(matches) != 1:
        raise SystemExit(
            f"ERROR: expected exactly one SUPPRESSION_PLAN_SHA256 assignment in "
            f"{world_source}, found {len(matches)}."
        )
    return matches[0]


def read_manifest(path: Path) -> dict:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(
            f"ERROR: no build manifest at {path}. This check fails closed: "
            "a binder that was not built is not a binder that matches."
        )
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: {path} is not valid JSON: {exc}")
    if manifest.get("format") != MANIFEST_FORMAT:
        raise SystemExit(
            f"ERROR: {path} format is {manifest.get('format')!r}, "
            f"expected {MANIFEST_FORMAT!r}."
        )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="build-manifest.json written by the binder build")
    parser.add_argument("--world-source", type=Path, default=WORLD_SOURCE,
                        help=argparse.SUPPRESS)  # test seam only
    args = parser.parse_args(argv)

    pin = read_pin(args.world_source)
    manifest = read_manifest(args.manifest)
    built = manifest.get("plan_sha256")
    if not isinstance(built, str) or not built:
        raise SystemExit(
            f"ERROR: {args.manifest} carries no plan_sha256; refusing to pass."
        )
    if built != pin:
        sys.stderr.write(
            "ERROR: the freshly built plan does not match the world's pin.\n"
            f"  built plan_sha256:          {built}\n"
            f"  SUPPRESSION_PLAN_SHA256:    {pin}\n"
            "Every seed stamps the pin into slot data and the launcher refuses\n"
            "a binder that disagrees, so one of these is wrong. If the plan\n"
            "changed on purpose, move the pin in the same commit; if not, the\n"
            "planner inputs or the planner itself regressed.\n"
        )
        return 1
    print(f"plan {built[:12]} matches SUPPRESSION_PLAN_SHA256")
    return 0


if __name__ == "__main__":
    sys.exit(main())
