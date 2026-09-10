#!/usr/bin/env python3
"""Regenerate original fixed-map boss encounter contracts; no protection changes."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.bosses import build_boss_catalog
from tools.bb_enemizer.inventory import load_slots
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS


def build(bundle: Path) -> dict:
    scripts = {name: data.decode("utf-8-sig") for name, data in read_prefix(bundle, "event/").items()}
    with tempfile.TemporaryDirectory(prefix="bb-boss-census-") as temp:
        inventory = Path(temp) / "inventory.tsv"
        inventory.write_bytes(read_blob(bundle, "mined/msb_enemies.tsv"))
        slots = load_slots(inventory)
    bindings = {key: binding.event_flag for key, binding in LOCATION_BINDINGS.items() if binding.source_kind == "boss_defeat"}
    return build_boss_catalog(scripts, slots, bindings)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=ROOT / "research/bb_inputs.db")
    parser.add_argument("--output", type=Path, default=ROOT / "research/enemizer/boss_catalog.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    catalog = build(args.bundle)
    content = json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != content:
            raise SystemExit("boss catalog is stale; run tools/build_boss_catalog.py")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(json.dumps(catalog["summary"], sort_keys=True))
    if catalog["unmatched_ap_bindings"]:
        raise SystemExit("boss AP bindings have no encounter witness: " + ", ".join(catalog["unmatched_ap_bindings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
