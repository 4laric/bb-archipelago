#!/usr/bin/env python3
"""Refuse silent use of shadPS4 v0.17 absolute-address Cheat Engine tables."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
ROOT = PACKAGE_ROOT if (PACKAGE_ROOT / "tables").exists() else PACKAGE_ROOT.parent
MANIFEST = ROOT / "tables" / "legacy-v017.tsv"
ABSOLUTE = re.compile(r"(?i)(?<![0-9a-f])80[1-5][0-9a-f]{6,}")
RELOCATED_TEMPLATE = 'install=install:gsub(old,string.format("%X",address))'
CURRENT_RELOCATED_TABLE = "Bloodborne-native-item-grant-auto-v2.CT"


def tracked_tables(root: Path = ROOT) -> dict[str, Path]:
    output = subprocess.check_output(
        ["git", "ls-files", "tables/*.CT"], cwd=root, text=True,
    )
    return {Path(line).name: root / line for line in output.splitlines() if line}


def unresolved_tables(root: Path = ROOT) -> set[str]:
    result = set()
    for name, path in tracked_tables(root).items():
        text = path.read_text(encoding="utf-8")
        if ABSOLUTE.search(text) and RELOCATED_TEMPLATE not in text:
            result.add(name)
    return result


def manifest_rows(path: Path = MANIFEST) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def audit(root: Path = ROOT) -> list[str]:
    rows = manifest_rows(root / "tables" / MANIFEST.name)
    listed = {row["table"] for row in rows}
    detected = unresolved_tables(root)
    errors = []
    if listed != detected:
        for name in sorted(detected - listed):
            errors.append(f"untriaged fixed-address table: {name}")
        for name in sorted(listed - detected):
            errors.append(f"manifest entry is no longer fixed-address: {name}")
    for row in rows:
        if row["disposition"] not in {"archive", "retire"}:
            errors.append(f"invalid disposition for {row['table']}: {row['disposition']}")
        if not row["reason"].strip():
            errors.append(f"missing rationale for {row['table']}")
    current = root / "tables" / CURRENT_RELOCATED_TABLE
    current_text = current.read_text(encoding="utf-8")
    if "local function readEbootBase()" not in current_text or RELOCATED_TEMPLATE not in current_text:
        errors.append(f"current table lost launch-relative relocation: {CURRENT_RELOCATED_TABLE}")
    self_attach_markers = (
        'getProcessIDFromName("shadPS4.exe")',
        "bbNativeGrantStartTimer.OnTimer",
    )
    for marker in self_attach_markers:
        if marker not in current_text:
            errors.append(f"current table lost self-attach retry ({marker}): {CURRENT_RELOCATED_TABLE}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="return nonzero when the inventory diverges")
    args = parser.parse_args()
    errors = audit()
    if errors:
        print("\n".join(errors))
        return 1 if args.check else 0
    print(f"CE table inventory OK: {len(manifest_rows())} legacy tables are explicitly retired")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
