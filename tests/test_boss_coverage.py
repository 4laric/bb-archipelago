import unittest

from tools.build_boss_coverage import coverage_report


class BossCoverageTests(unittest.TestCase):
    def test_missing_reverse_routes_are_gaps_not_incompatibility_findings(self):
        report = coverage_report({"a": ("b",), "b": ("c",), "c": ("a",)})
        self.assertEqual(6, report["candidate_pair_count"])
        self.assertEqual(3, report["implemented_pair_count"])
        self.assertEqual(3, report["unimplemented_pair_count"])
        self.assertEqual(3, report["feasible_pair_count"])
        rows = {(row["arena"], row["donor"]): row for row in report["pairs"]}
        self.assertEqual("unimplemented", rows["b", "a"]["implementation"])
        self.assertEqual("implemented", rows["a", "b"]["implementation"])
        self.assertEqual("not_assessed_by_this_report", rows["a", "b"]["gameplay_validation"])

    def test_individually_implemented_route_can_be_globally_unusable(self):
        report = coverage_report({"a": ("b", "c"), "b": ("c",), "c": ("a",)})
        self.assertEqual(4, report["implemented_pair_count"])
        self.assertEqual(3, report["feasible_pair_count"])
        edge = next(row for row in report["pairs"] if (row["arena"], row["donor"]) == ("a", "c"))
        self.assertEqual("implemented", edge["implementation"])
        self.assertFalse(edge["usable_in_full_assignment"])

    def test_self_placement_is_an_explicit_policy_not_a_missing_adapter(self):
        report = coverage_report({"a": ("a", "b"), "b": ("a", "b")})
        self.assertEqual(2, len(report["pairs"]))
        self.assertEqual(2, report["implemented_pair_count"])
        self.assertFalse(report["assignment_policy"]["allow_self_placement"])
        self.assertEqual({("a", "b"), ("b", "a")},
                         {(row["arena"], row["donor"]) for row in report["pairs"]})

    def test_invalid_graph_is_not_reported_as_a_set_of_incompatibilities(self):
        for graph in ({}, {"a": ("unknown",)}, {"a": ("b",), "b": ()}):
            with self.subTest(graph=graph), self.assertRaises(ValueError):
                coverage_report(graph)

    def test_equivalent_graph_order_and_duplicate_entries_have_identical_reports(self):
        first = coverage_report({"a": ("b", "c"), "b": ("c", "a"), "c": ("a", "b")})
        second = coverage_report({"c": ("b", "a", "b"), "b": ("a", "c"), "a": ("c", "b")})
        self.assertEqual(first, second)
        self.assertEqual(6, first["feasible_pair_count"])
