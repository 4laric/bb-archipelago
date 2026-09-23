"""Report implementation gaps separately from boss-placement incompatibility.

The construction graph is a work inventory, not evidence that missing pairs
cannot work. Native receipts and gameplay evidence are separate dimensions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_enemizer.boss_pool import assign_donors


def coverage_report(compatible: Mapping[str, Sequence[str]]) -> dict:
    roster = sorted(compatible)
    if not roster:
        raise ValueError("boss roster is empty")
    graph = {arena: tuple(sorted(set(donors))) for arena, donors in compatible.items()}
    for arena, donors in graph.items():
        if set(donors) - set(roster):
            raise ValueError(f"unknown donor for {arena}")
    # A failed base assignment is a broken implementation graph, not 462
    # individual incompatibility findings.
    assign_donors("coverage", graph)
    pairs = []
    for arena in roster:
        for donor in roster:
            if arena == donor:
                continue
            implemented = donor in graph[arena]
            feasible = False
            if implemented:
                forced = dict(graph)
                forced[arena] = (donor,)
                try:
                    assign_donors("coverage", forced)
                    feasible = True
                except ValueError as exc:
                    if "no complete one-to-one assignment" not in str(exc):
                        raise
            pairs.append({
                "arena": arena,
                "donor": donor,
                "implementation": "implemented" if implemented else "unimplemented",
                "usable_in_full_assignment": feasible,
                "native_validation": "not_assessed_by_this_report",
                "gameplay_validation": "not_assessed_by_this_report",
            })
    implemented_count = sum(row["implementation"] == "implemented" for row in pairs)
    return {
        "format": "bb-boss-implementation-coverage-v1",
        "roster": roster,
        "assignment_policy": {"one_of_each_donor": True, "allow_self_placement": False},
        "candidate_pair_count": len(pairs),
        "implemented_pair_count": implemented_count,
        "unimplemented_pair_count": len(pairs) - implemented_count,
        "feasible_pair_count": sum(row["usable_in_full_assignment"] for row in pairs),
        "interpretation": (
            "Missing adapters are implementation gaps, not proven incompatibilities. "
            "Graph membership proves neither native construction nor gameplay. "
            "A pair can be implemented but blocked by the current one-to-one graph."
        ),
        "pairs": pairs,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    from tools.build_boss_encounters import reviewed_compatibility

    report = coverage_report(reviewed_compatibility())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"implemented={report['implemented_pair_count']}/{report['candidate_pair_count']} "
        f"unimplemented={report['unimplemented_pair_count']} "
        f"feasible={report['feasible_pair_count']} output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
