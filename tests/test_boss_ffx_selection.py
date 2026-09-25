import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tools.build_boss_encounters import build, FfxCompatibilityError, ffx_conflict_combinations


def merge(source, destination="dst"):
    return {"source_file": source, "destination_file": destination}


def conflict(left, right):
    return {"destination_file": "dst", "left_file": left, "right_file": right,
            "entry": "effect/f000620900.fxr"}


class BossFfxSelectionTests(unittest.TestCase):
    def test_shared_bank_conflict_excludes_combination_not_each_route(self):
        routes = [("arena-a", "donor-a"), ("arena-b", "donor-b")]
        plans = [{"boss_ffx_merges": [merge("src-a")]},
                 {"boss_ffx_merges": [merge("src-b")]}]
        result = ffx_conflict_combinations([conflict("src-a", "src-b")], routes, plans)
        self.assertEqual(result, {frozenset(routes)})
        self.assertEqual({len(row) for row in result}, {2})

    def test_native_destination_conflict_excludes_only_contributing_route(self):
        routes = [("arena-a", "donor-a"), ("arena-b", "donor-b")]
        plans = [{"boss_ffx_merges": [merge("src-a")]},
                 {"boss_ffx_merges": [merge("src-b")]}]
        result = ffx_conflict_combinations([conflict("dst", "src-a")], routes, plans)
        self.assertEqual(result, {frozenset([routes[0]])})
        with self.assertRaisesRegex(ValueError, "no contributing route"):
            ffx_conflict_combinations([conflict("dst", "unknown")], routes, plans)

    def test_retry_keeps_seed_and_ordinary_plan_and_records_conflict(self):
        args = SimpleNamespace(pool="reviewed", seed="same", ordinary_plan="ordinary.json")
        bad = frozenset([("arena-a", "donor-a"), ("arena-b", "donor-b")])
        seen = []
        def run(current):
            seen.append((current.seed, current.ordinary_plan, set(current._ffx_forbidden_combinations)))
            if len(seen) == 1:
                raise FfxCompatibilityError([conflict("src-a", "src-b")], {bad})
            return {"files": ["receipt"], "selection": current._ffx_selection}
        with patch("tools.build_boss_encounters._build_once", side_effect=run):
            result = build(args)
        self.assertEqual(len(seen), 2)
        self.assertEqual({row[:2] for row in seen}, {("same", "ordinary.json")})
        self.assertEqual(seen[1][2], {bad})
        self.assertEqual(result["selection"]["attempt"], 2)
        self.assertEqual(result["selection"]["conflicts_avoided"], [conflict("src-a", "src-b")])

    def test_direct_route_and_unrelated_failures_do_not_retry(self):
        failure = FfxCompatibilityError([conflict("dst", "src")], {frozenset([("a", "b")])})
        with patch("tools.build_boss_encounters._build_once", side_effect=failure) as run:
            with self.assertRaises(FfxCompatibilityError):
                build(SimpleNamespace(pool=None))
            self.assertEqual(run.call_count, 1)
        with patch("tools.build_boss_encounters._build_once", side_effect=ValueError("source drift")) as run:
            with self.assertRaisesRegex(ValueError, "source drift"):
                build(SimpleNamespace(pool="good"))
            self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
