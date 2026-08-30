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

It also pins the binder's LINEAGE (#200). The release bundle once shipped a
binder built from a re-extracted gameparam that was byte-different from the
patch layer real installs carry, so every zip binder failed the installed-
gameparam check and manually built binders were couriered around it. Bytes,
not content, are the identity (#104), so three more pins hold here:

* the bundle's ``parambnd/gameparam.parambnd.dcx`` must hash to the installed
  patch layer (``EXPECTED_SOURCE_SHA256``);
* the manifest's ``source_gameparam_sha256`` must equal that same pin;
* the manifest's ``output_gameparam_sha256`` must equal the known-good manual
  binder (``EXPECTED_OUTPUT_SHA256``) that playtesters live-validated.

Moving either constant is a deliberate act in the same commit as the bytes
that justify it.
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
BUNDLE_PATH = REPO / "research" / "bb_inputs.db"
BUNDLE_MEMBER = "parambnd/gameparam.parambnd.dcx"
# The installed CUSA03173 01.09 patch-layer gameparam, byte-for-byte -- the
# bytes the launcher validates on every player machine (#104, #200).
EXPECTED_SOURCE_SHA256 = "581e28302a231a10ad333806dfc90f41425db4f9f146799dca625f8d83c760c3"
# The binder output CI reproduces from the pinned source + plan + the pinned
# SoulsFormatsNEXT (7cef52a7). The operator's hand-built binder (195eb7cf...,
# live-validated) used a different SFN checkout and differs in bytes only:
# the writer's byte-faithful round-trip verification guards content, and the
# client checks a binder against its OWN manifest, so this value is playable
# by construction. Owed: one live session on a CI-built binder (#200).
EXPECTED_OUTPUT_SHA256 = "69ccf70b2986a1c22b246169e2e18e5ca40e51112288a869daa3b26c4bf82d1c"


def read_bundle_source_sha(bundle: Path) -> str:
    import sqlite3
    if not bundle.exists():
        raise SystemExit(f"ERROR: no inputs bundle at {bundle}; refusing to pass.")
    row = sqlite3.connect(bundle).execute(
        "SELECT sha256 FROM files WHERE path = ?", (BUNDLE_MEMBER,)
    ).fetchone()
    if row is None:
        raise SystemExit(f"ERROR: {bundle} has no {BUNDLE_MEMBER}; refusing to pass.")
    return row[0]
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
    parser.add_argument("--bundle", type=Path, default=BUNDLE_PATH,
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
    bundle_sha = read_bundle_source_sha(args.bundle)
    if bundle_sha != EXPECTED_SOURCE_SHA256:
        sys.stderr.write(
            "ERROR: the inputs bundle's gameparam is not the installed patch layer.\n"
            f"  bundle {BUNDLE_MEMBER}:  {bundle_sha}\n"
            f"  EXPECTED_SOURCE_SHA256:  {EXPECTED_SOURCE_SHA256}\n"
            "A binder built from these bytes will fail the installed-gameparam\n"
            "check on every player machine (#200). Repack the bundle from the\n"
            "installed CUSA03173-patch gameparam, or move the pin deliberately\n"
            "in the same commit as the bytes that justify it.\n"
        )
        return 1
    source = manifest.get("source_gameparam_sha256")
    if source != EXPECTED_SOURCE_SHA256:
        sys.stderr.write(
            "ERROR: the binder was not built from the installed patch layer.\n"
            f"  manifest source_gameparam_sha256: {source}\n"
            f"  EXPECTED_SOURCE_SHA256:           {EXPECTED_SOURCE_SHA256}\n"
        )
        return 1
    output = manifest.get("output_gameparam_sha256")
    if output != EXPECTED_OUTPUT_SHA256:
        sys.stderr.write(
            "ERROR: the binder output differs from the known-good manual binder.\n"
            f"  manifest output_gameparam_sha256: {output}\n"
            f"  EXPECTED_OUTPUT_SHA256:           {EXPECTED_OUTPUT_SHA256}\n"
            "Same plan + same source bytes must reproduce the binder the\n"
            "playtesters validated; if the writer or plan changed on purpose,\n"
            "move the pin in the same commit.\n"
        )
        return 1
    print(f"plan {built[:12]} matches SUPPRESSION_PLAN_SHA256; "
          f"source {source[:12]} and output {output[:12]} match the #200 pins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
