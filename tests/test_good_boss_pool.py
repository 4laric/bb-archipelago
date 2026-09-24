"""Exact-family matching tests, including the directed planned-route boundary."""
from __future__ import annotations

import unittest

from tools.bb_enemizer.good_boss_pool import (
    GOOD_ARENAS, GOOD_FAMILIES, CoverageError, assign_good_bosses,
    coverage_report, donor_family,
)
from tools.build_boss_encounters import reviewed_compatibility
from tools.bb_enemizer.chalice_recipes import chalice_recipes


def reviewed_routes() -> set[tuple[str, str]]:
    return {(arena, donor)
            for arena, donors in reviewed_compatibility().items()
            for donor in donors} | set(chalice_recipes())


def planned_routes() -> set[tuple[str, str]]:
    """Proposed specialist routes, kept separate from implemented routes."""
    people = ("pthumerian-elder", "pthumerian-descendant", "keeper-of-old-lords")
    beasts = ("watchdog-of-the-old-lords", "abhorrent-beast", "beast-possessed-soul")
    specialists = {
        "lady-maria": people,
        "gehrman": beasts,
        "vicar-amelia": people,
        "ebrietas": ("keeper-of-old-lords",),
        "the-one-reborn": ("beast-possessed-soul",),
    }
    return reviewed_routes() | {(arena, donor)
                                for arena, donors in specialists.items()
                                for donor in donors}


class GoodBossPoolTests(unittest.TestCase):
    def test_current_implemented_graph_covers_all_families_but_reports_loran_absence(self):
        report = coverage_report(reviewed_routes())
        self.assertEqual(report["arenas_without_good_routes"], [])
        self.assertEqual(report["families_without_routes"], [])
        self.assertIn("loran-darkbeast", report["unavailable_variants"])
        assignment = assign_good_bosses("current", reviewed_routes())
        self.assertEqual(len(assignment.arena_to_donor), 22)
        self.assertEqual(assignment.self_pairs, ())

    def test_planned_specialist_routes_admit_complete_no_self_matching(self):
        assignment = assign_good_bosses("feasibility", planned_routes())
        self.assertEqual(len(assignment.arena_to_donor), 22)
        self.assertEqual(set(assignment.arena_to_donor), set(GOOD_ARENAS))
        self.assertEqual(set(assignment.arena_to_family.values()), set(GOOD_FAMILIES))
        self.assertEqual(assignment.self_pairs, ())
        self.assertEqual(assignment, assign_good_bosses("feasibility", planned_routes()))
        self.assertEqual(assignment.unavailable_variants, ("loran-darkbeast",))
        self.assertTrue(all((arena, donor) in planned_routes()
                            for arena, donor in assignment.arena_to_donor.items()))
        self.assertEqual({donor_family(d) for d in assignment.arena_to_donor.values()},
                         set(GOOD_FAMILIES))

    def test_variants_are_one_family_and_forced_missing_loran_is_error(self):
        routes = planned_routes()
        with self.assertRaisesRegex(CoverageError, "loran-darkbeast"):
            assign_good_bosses("forced", routes,
                               required_variants={"darkbeast-paarl": "loran-darkbeast"})
        self.assertTrue(any(assign_good_bosses(str(seed), routes).selected_variants[
                            "bloodletting-beast"] == "headless-bloodletting-beast"
                            for seed in range(20)))
        routes |= {(arena, "loran-darkbeast") for arena, donor in routes
                   if donor == "darkbeast-paarl"}
        assignment = assign_good_bosses(
            "forced", routes,
            required_variants={"darkbeast-paarl": "loran-darkbeast",
                               "bloodletting-beast": "headless-bloodletting-beast"})
        self.assertEqual(assignment.selected_variants["darkbeast-paarl"], "loran-darkbeast")
        self.assertEqual(assignment.selected_variants["bloodletting-beast"],
                         "headless-bloodletting-beast")
        self.assertEqual(assignment.unavailable_variants, ())
        self.assertEqual(len(set(assignment.arena_to_family.values())), 22)

    def test_hall_deficit_fails_even_with_each_family_individually_available(self):
        # Two arenas can only use the same family, while all 22 families appear.
        routes = {(GOOD_ARENAS[0], GOOD_FAMILIES[0]),
                  (GOOD_ARENAS[1], GOOD_FAMILIES[0])}
        routes |= {(arena, family)
                   for arena, family in zip(GOOD_ARENAS[2:], GOOD_FAMILIES[1:])}
        routes.add((GOOD_ARENAS[2], GOOD_FAMILIES[-1]))
        self.assertEqual(coverage_report(routes)["families_without_routes"], [])
        with self.assertRaises(CoverageError) as caught:
            assign_good_bosses("hall", routes)
        self.assertEqual(caught.exception.report["maximum_matching_size"], 21)

    def test_self_pair_is_explicit_when_only_supported_route(self):
        routes = {(arena, family)
                  for arena, family in zip(GOOD_ARENAS, GOOD_FAMILIES)}
        # A three-cycle keeps each family present while making Amygdala's only
        # edge a vanilla self pair.
        routes.remove((GOOD_ARENAS[0], GOOD_FAMILIES[0]))
        routes.remove((GOOD_ARENAS[1], GOOD_FAMILIES[1]))
        routes.remove((GOOD_ARENAS[11], GOOD_FAMILIES[11]))
        routes |= {("amygdala", "amygdala"),
                   (GOOD_ARENAS[1], GOOD_FAMILIES[0]),
                   (GOOD_ARENAS[11], GOOD_FAMILIES[1])}
        assignment = assign_good_bosses("self", routes)
        self.assertIn("amygdala", assignment.self_pairs)
        with self.assertRaises(CoverageError):
            assign_good_bosses("self", routes, allow_self=False)


if __name__ == "__main__":
    unittest.main()
