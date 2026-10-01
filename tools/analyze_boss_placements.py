"""Count current matcher placements in both pools, before asset preflight."""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.build_boss_encounters import good_boss_routes, reviewed_compatibility
from tools.bb_enemizer.boss_pool import assign_donors
from tools.bb_enemizer.good_boss_pool import assign_good_bosses


def distribution(seed_count):
    if seed_count <= 0:
        raise ValueError("seed count must be positive")
    graph, routes = reviewed_compatibility(), good_boss_routes()
    matchers = {
        "reviewed": lambda seed: assign_donors(seed, graph),
        "good": lambda seed: assign_good_bosses(seed, routes, allow_self=False).arena_to_donor,
    }
    result = {}
    for pool, matcher in matchers.items():
        counts = {arena: Counter() for arena in graph}
        for seed in range(seed_count):
            for arena, donor in matcher(str(seed)).items():
                counts[arena][donor] += 1
        result[pool] = {arena: dict(sorted(count.items())) for arena, count in counts.items()}
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(distribution(args.seeds), indent=2) + "\n", encoding="utf-8")
