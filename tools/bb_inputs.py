#!/usr/bin/env python3
"""Pack and query the extracted-game-data inputs the mining tools read.

The tools that build `research/joined/` and `research/catalog/` take a path to
an extracted game dump. That works on the machine holding the dump and nowhere
else, so nothing downstream of them can be regenerated, tested in CI, or checked
by anyone else.

This is the same answer `er-archipelago` uses: pack those inputs into one
committed sqlite bundle, so the derivation is reproducible from the repo alone.

    python tools/bb_inputs.py --build <dump-root>          # pack (needs the dump)
    python tools/bb_inputs.py --extract work/inputs        # unpack (needs the repo)
    python tools/bb_inputs.py --list                       # manifest
    python tools/bb_inputs.py --get params/ItemLotParam.csv | head
    python tools/bb_inputs.py --verify                     # re-check every sha256

The bundle is plain sqlite with zlib blobs, so it can also be read directly
without extracting anything — which is usually what you want when the question
is "what does row 4011 say".

## What goes in, and why that list

Only inputs a committed tool actually reads. `--check-coverage` asserts that
every `*.csv` named in `tools/` is present, so the bundle cannot silently drift
away from the code that consumes it. Adding a param to a tool reds that check
until the bundle is rebuilt.

🛑 This is extracted game data. It is committed here deliberately, to a private
repository, for reproducibility. See `docs/INPUTS-BUNDLE.md` before widening the
list or changing the repository's visibility.
"""

from __future__ import annotations

import argparse
import hashlib
import sqlite3
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BUNDLE = REPO / "research" / "bb_inputs.db"
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Source:
    """One group of files to pack, and where to find it under the dump root."""

    prefix: str            # path prefix inside the bundle
    relative: str          # directory under the dump root
    pattern: str
    required: bool = True
    note: str = ""


SOURCES: tuple[Source, ...] = (
    Source("params", "install/CUSA03173/dvdroot_ps4/params_dump", "*.csv", True,
           "param tables; the joins and the enemizer catalog read these"),
    Source("event", "bloodborne_artifacts/event", "*.emevd.dcx.js", True,
           "decompiled event scripts; the award and protection analyses read these"),
    Source("mined", "../research/mined", "*.tsv", False,
           "msbb_miner output. Derived rather than raw, but the MSBs themselves "
           "are not bundled, so without it the joins cannot be re-run."),
)

# Params are large and most are unused. Restrict to what tools reference, and
# let --check-coverage police the list.
PARAM_ALLOWLIST = {
    "ItemLotParam.csv", "NpcParam.csv", "EquipParamGoods.csv", "SpEffectParam.csv",
}


def connect(path: Path, *, create: bool = False) -> sqlite3.Connection:
    if not create and not path.exists():
        raise SystemExit(f"no bundle at {path}. Build one with --build <dump-root>, "
                         f"or ask for the committed one.")
    return sqlite3.connect(path)


def build(dump_root: Path, bundle: Path) -> int:
    bundle.parent.mkdir(parents=True, exist_ok=True)
    if bundle.exists():
        bundle.unlink()
    db = connect(bundle, create=True)
    db.executescript("""
        CREATE TABLE files (path TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                            size INTEGER NOT NULL, blob BLOB NOT NULL);
        CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)

    packed = 0
    raw_total = 0
    for source in SOURCES:
        directory = (dump_root / source.relative).resolve()
        if not directory.is_dir():
            if source.required:
                raise SystemExit(f"required source missing: {directory}")
            print(f"  skipping absent optional source {source.prefix} ({directory})")
            continue
        for path in sorted(directory.glob(source.pattern)):
            if source.prefix == "params" and path.name not in PARAM_ALLOWLIST:
                continue
            data = path.read_bytes()
            raw_total += len(data)
            db.execute("INSERT INTO files VALUES (?,?,?,?)",
                       (f"{source.prefix}/{path.name}", hashlib.sha256(data).hexdigest(),
                        len(data), zlib.compress(data, 9)))
            packed += 1
        print(f"  {source.prefix}: packed from {directory}")

    for key, value in (("schema_version", str(SCHEMA_VERSION)),
                       ("serial", "CUSA03173"), ("app_version", "01.09"),
                       ("file_count", str(packed)), ("raw_bytes", str(raw_total))):
        db.execute("INSERT INTO meta VALUES (?,?)", (key, value))
    db.commit()
    db.execute("VACUUM")
    db.close()
    print(f"packed {packed} files, {raw_total/1e6:.1f} MB raw -> "
          f"{bundle.stat().st_size/1e6:.1f} MB at {bundle}")
    return 0


def extract(bundle: Path, target: Path) -> int:
    db = connect(bundle)
    count = 0
    for path, sha, size, blob in db.execute("SELECT path, sha256, size, blob FROM files"):
        data = zlib.decompress(blob)
        if hashlib.sha256(data).hexdigest() != sha or len(data) != size:
            raise SystemExit(f"{path}: bundle content does not match its recorded digest")
        out = target / path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        count += 1
    db.close()
    print(f"extracted {count} files to {target}")
    return 0


def get(bundle: Path, path: str) -> int:
    db = connect(bundle)
    row = db.execute("SELECT blob FROM files WHERE path = ?", (path,)).fetchone()
    db.close()
    if row is None:
        raise SystemExit(f"{path} is not in the bundle; --list to see what is")
    sys.stdout.buffer.write(zlib.decompress(row[0]))
    return 0


def listing(bundle: Path) -> int:
    db = connect(bundle)
    for key, value in db.execute("SELECT key, value FROM meta ORDER BY key"):
        print(f"# {key}: {value}")
    for path, sha, size in db.execute("SELECT path, sha256, size FROM files ORDER BY path"):
        print(f"{sha[:12]}  {size:>10}  {path}")
    db.close()
    return 0


def verify(bundle: Path) -> int:
    db = connect(bundle)
    bad = 0
    for path, sha, size, blob in db.execute("SELECT path, sha256, size, blob FROM files"):
        data = zlib.decompress(blob)
        if hashlib.sha256(data).hexdigest() != sha or len(data) != size:
            print(f"CORRUPT {path}", file=sys.stderr)
            bad += 1
    db.close()
    print("bundle verified" if not bad else f"{bad} corrupt entries")
    return 1 if bad else 0


def referenced_csvs() -> set[str]:
    """Every `*.csv` named in tools/, which is what the bundle must cover."""
    import re
    names: set[str] = set()
    for path in sorted((REPO / "tools").rglob("*.py")):
        if path.name == Path(__file__).name:
            continue
        names |= set(re.findall(r"([A-Za-z_]+\.csv)", path.read_text(encoding="utf-8")))
    return names


def check_coverage(bundle: Path) -> int:
    db = connect(bundle)
    have = {path.split("/", 1)[1] for (path,) in db.execute("SELECT path FROM files")}
    db.close()
    missing = sorted(referenced_csvs() - have)
    if missing:
        print("GATE FAILED: tools read params the bundle does not carry: "
              + ", ".join(missing), file=sys.stderr)
        print("Add them to PARAM_ALLOWLIST and rebuild the bundle from the dump.",
              file=sys.stderr)
        return 1
    print(f"coverage ok: every referenced csv ({len(referenced_csvs())}) is in the bundle")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--build", type=Path, metavar="DUMP_ROOT")
    action.add_argument("--extract", type=Path, metavar="DIR")
    action.add_argument("--get", metavar="PATH")
    action.add_argument("--list", action="store_true")
    action.add_argument("--verify", action="store_true")
    action.add_argument("--check-coverage", action="store_true")
    args = parser.parse_args(argv)

    if args.build:
        return build(args.build, args.bundle)
    if args.extract:
        return extract(args.bundle, args.extract)
    if args.get:
        return get(args.bundle, args.get)
    if args.list:
        return listing(args.bundle)
    if args.verify:
        return verify(args.bundle)
    return check_coverage(args.bundle)


if __name__ == "__main__":
    raise SystemExit(main())
