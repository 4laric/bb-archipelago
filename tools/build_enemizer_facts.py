"""Derive the player-facing facts the enemizer report needs per NpcParam row.

The launcher never ships the research bundle, only two small enemizer tables.
When a player reports a bad enemy, the report has to name the actors involved
without a game dump on hand. This tool writes ``archetype_facts.json`` keyed by
NpcParam id with the designer's row name, the Blood Echo reward, and HP, all
read from ``research/bb_inputs.db``. The planner stamps these into every swap
it plans (``tools/bb_enemizer/planner.py``), so a retained plan is enough to
identify a swap after the fact (bb-archipelago#321).

The table is restricted to NpcParam ids that occur in the fixed-map inventory
so it stays small enough to bundle.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bb_inputs import read_blob  # noqa: E402


def build_facts(bundle: Path) -> dict[str, dict[str, object]]:
    inventory = csv.DictReader(
        io.StringIO(read_blob(bundle, "mined/msb_enemies.tsv").decode("utf-8")),
        delimiter="\t",
    )
    wanted = {row["npc_param_id"] for row in inventory if row["npc_param_id"]}
    npcs = csv.DictReader(io.StringIO(read_blob(bundle, "params/NpcParam.csv").decode("utf-8")))
    facts: dict[str, dict[str, object]] = {}
    for row in npcs:
        if row["ID"] not in wanted:
            continue
        facts[row["ID"]] = {
            "name": row.get("Name", "").strip(),
            "echoes": int(row.get("getSoul") or 0),
            "hp": int(row.get("hp") or 0),
        }
    return dict(sorted(facts.items(), key=lambda item: int(item[0])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", type=Path, default=REPO / "research" / "bb_inputs.db")
    parser.add_argument(
        "--output", type=Path, default=REPO / "research" / "enemizer" / "archetype_facts.json"
    )
    args = parser.parse_args(argv)
    facts = build_facts(args.bundle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(facts, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"npc_param_rows={len(facts)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
