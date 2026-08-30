"""Gates the model claims, checked against the gates the game has.

A too-permissive entrance rule never fails generation. The spoiler looks fine,
the seed is unwinnable in the game, and nothing in the tooling notices — so the
only guard available is writing the expected requirement down and comparing.

The Hemwick edge is why this file exists. It carried no rule at all, and the
fourteen-row "Wiki audit" table in docs/PROGRESSION-DAG.md does not list it —
the audit skipped exactly the edge that was wrong. The allow-list below is the
structural half of the fix: a new ungated entrance has to be added to it
deliberately, so the next omission is a diff rather than a silence.
"""

from __future__ import annotations

import unittest

from worlds.bloodborne.data import ENTRANCES, LOCATIONS
from worlds.bloodborne.model import ItemKind
from worlds.bloodborne.data import ITEMS

# entrance name -> the clauses that satisfy it, each a frozenset of item keys.
# Sourced from the game; see docs/PROGRESSION-DAG.md for the citations.
DOCUMENTED_GATES: dict[str, set[frozenset[str]]] = {
    # Two requirements. The door object 2411304 is the generic key door
    # (m24_01_00_00 event 12410110 slot 5, objParameterId 2410080), so the item
    # requirement is an ObjActParam property rather than an EMEVD condition;
    # and the door is physically behind Gascoigne's arena. Vanilla awarded the
    # key on his death, which hid the second requirement inside the first.
    "Tomb of Oedon gate": {frozenset({"oedon_tomb_key", "event_gascoigne_defeated"})},
    "Healing Church Workshop door": {frozenset({"event_blood_starved_beast_defeated"})},
    # The emblem opens the gate itself. The game's other way in is the Healing
    # Church Workshop route, which is its own entrance below rather than a
    # second clause here: folding it in made the emblem clause unreachable as a
    # requirement, because Blood-starved Beast is free from Cathedral Ward.
    "Cathedral Ward plaza gate": {frozenset({"hunter_chief_emblem"})},
    "Forbidden Woods password door": {frozenset({"event_forbidden_woods_password"})},
    "Path to Byrgenwerth": {frozenset({"event_shadows_defeated"})},
    "Lunarium door": {frozenset({"lunarium_key"})},
    "Blood Moon transition": {frozenset({"event_rom_defeated"})},
    "Advent Plaza mummy": {frozenset({"event_one_reborn_defeated"})},
    "Amygdala's grasp": {frozenset({"tonsil_stone"})},
    # The chapel side doors only open after Blood-starved Beast; the key alone
    # is not sufficient.
    "Upper Cathedral door": {
        frozenset({"upper_cathedral_key", "event_blood_starved_beast_defeated"})},
    "Cainhurst carriage": {
        frozenset({"cainhurst_summons", "event_witch_of_hemwick_defeated"})},
    "Amygdala's DLC grasp": {
        frozenset({"event_forbidden_woods_password", "eye_of_blood_drunk_hunter"})},
    "Ludwig's arena exit": {frozenset({"event_ludwig_defeated"})},
    "Surgery altar": {frozenset({"eye_pendant"})},
    "Astral Clocktower door": {
        frozenset({"event_living_failures_defeated", "astral_clocktower_key"})},
    "Astral clock": {frozenset({"event_lady_maria_defeated", "celestial_dial"})},
}

# Entrances that are genuinely free in the game. Anything not here must be
# documented above; the point is that "no rule" becomes a deliberate claim.
DOCUMENTED_FREE = {
    "Begin the Hunt",
    "Awaken in Central Yharnam",
    "Road into Old Yharnam",
    "Forbidden Woods clinic passage",
    # The workshop's own door already costs Blood-starved Beast; the walk from
    # it to the plaza costs nothing more.
    "Healing Church Workshop plaza route",
    # The road starts left of the Grand Cathedral entrance, so it is behind the
    # plaza. Its requirement is now the plaza edge itself, not a copy of it.
    "Road to Hemwick",
    "Lecture Hall giant door",
    "Lecture Building frontier door",
    "Research Hall summit",
    "Nightmare Grand Cathedral",
}


def clauses(rule) -> set[frozenset[str]]:
    return {frozenset(clause) for clause in rule.any_of}


class GateTests(unittest.TestCase):
    def test_documented_gates_match_the_model(self):
        by_name = {e.name: e for e in ENTRANCES}
        for name, expected in DOCUMENTED_GATES.items():
            with self.subTest(entrance=name):
                self.assertIn(name, by_name)
                self.assertEqual(clauses(by_name[name].rule), expected)

    def test_every_entrance_is_either_documented_or_declared_free(self):
        """No entrance gets to be ungated by accident."""
        described = set(DOCUMENTED_GATES) | DOCUMENTED_FREE
        for entrance in ENTRANCES:
            with self.subTest(entrance=entrance.name):
                self.assertIn(entrance.name, described,
                              "add it to DOCUMENTED_GATES or justify it in DOCUMENTED_FREE")

    def test_declared_free_entrances_really_have_no_rule(self):
        by_name = {e.name: e for e in ENTRANCES}
        for name in DOCUMENTED_FREE:
            with self.subTest(entrance=name):
                self.assertIn(name, by_name)
                self.assertEqual(clauses(by_name[name].rule), {frozenset()},
                                 "declared free but carries a requirement")

    def test_documented_gates_are_not_free(self):
        by_name = {e.name: e for e in ENTRANCES}
        for name in DOCUMENTED_GATES:
            with self.subTest(entrance=name):
                self.assertNotIn(frozenset(), clauses(by_name[name].rule),
                                 "a gate with an empty clause is satisfied by nothing at all")

    def test_no_entrance_appears_twice(self):
        names = [e.name for e in ENTRANCES]
        self.assertEqual(len(names), len(set(names)))

    def test_every_referenced_key_exists(self):
        known = {i.key for i in ITEMS}
        for name, expected in DOCUMENTED_GATES.items():
            for clause in expected:
                for key in clause:
                    with self.subTest(entrance=name, key=key):
                        self.assertIn(key, known)


class LocationRuleTests(unittest.TestCase):
    """Same principle for the location rules that carry one."""

    EXPECTED = {
        "interaction_laurences_skull": {frozenset({"event_amelia_defeated"})},
        "boss_mergos_wet_nurse": {frozenset({"event_micolash_defeated"})},
        "boss_gehrman": {frozenset({"event_mergos_wet_nurse_defeated"})},
        "boss_moon_presence": {
            frozenset({"event_gehrman_defeated", "third_umbilical_cord_1",
                       "third_umbilical_cord_2", "third_umbilical_cord_3"}),
            frozenset({"event_gehrman_defeated", "third_umbilical_cord_1",
                       "third_umbilical_cord_2", "third_umbilical_cord_4"}),
            frozenset({"event_gehrman_defeated", "third_umbilical_cord_1",
                       "third_umbilical_cord_3", "third_umbilical_cord_4"}),
            frozenset({"event_gehrman_defeated", "third_umbilical_cord_2",
                       "third_umbilical_cord_3", "third_umbilical_cord_4"}),
        },
        "pickup_eye_of_blood_drunk_hunter": {frozenset({"event_forbidden_woods_password"})},
        "boss_laurence": {frozenset({"laurences_skull"})},
        "treasure_cosmic_eye_watcher_badge": {frozenset({"orphanage_key"})},
    }

    def test_gated_locations_match(self):
        by_key = {l.key: l for l in LOCATIONS}
        for key, expected in self.EXPECTED.items():
            with self.subTest(location=key):
                self.assertEqual(clauses(by_key[key].rule), expected)

    def test_no_other_location_carries_a_rule(self):
        for location in LOCATIONS:
            if location.key in self.EXPECTED:
                continue
            with self.subTest(location=location.key):
                self.assertEqual(clauses(location.rule), {frozenset()},
                                 "undocumented location requirement")


class CathedralPlazaRouteTests(unittest.TestCase):
    """The plaza has its two distinct in-game routes.

    docs/PROGRESSION-DAG.md audits the plaza as "emblem OR the Healing Church
    Workshop route". Modelled as one two-clause rule it is vacuous: Old Yharnam
    is free from Cathedral Ward and the Blood-starved Beast is free inside it,
    so the second clause is always satisfiable and the emblem never decides
    anything. The Amelia slice keeps the two routes as two edges: the emblem
    is the direct shortcut, while defeating BSB opens the Workshop route.
    """

    def test_the_plaza_gate_is_emblem_only(self):
        gate = next(e for e in ENTRANCES if e.name == "Cathedral Ward plaza gate")
        self.assertEqual(clauses(gate.rule), {frozenset({"hunter_chief_emblem"})})

    def test_the_workshop_route_still_reaches_the_plaza(self):
        """Removing the disjunction must not remove the route it described."""
        edges = {(e.source, e.target) for e in ENTRANCES}
        self.assertIn(("Cathedral Ward", "Healing Church Workshop"), edges)
        self.assertIn(("Healing Church Workshop", "Grand Cathedral"), edges)

    def test_the_seeded_slice_contains_both_routes_to_the_plaza(self):
        from worlds.bloodborne.data import SLICE_ENTRANCES, SLICE_REGIONS
        into_plaza = [e for e in SLICE_ENTRANCES if e.target == "Grand Cathedral"]
        self.assertEqual(
            [e.name for e in into_plaza],
            ["Cathedral Ward plaza gate", "Healing Church Workshop plaza route"],
        )
        self.assertIn("Healing Church Workshop", SLICE_REGIONS)

    def test_both_routes_lead_to_seeded_checks(self):
        from worlds.bloodborne import NETWORK_LOCATIONS
        behind = [l for l in NETWORK_LOCATIONS if l.region == "Grand Cathedral"]
        self.assertGreaterEqual(len(behind), 2, [l.key for l in behind])

    def test_the_emblem_is_in_every_seeded_pool(self):
        """The direct route remains available as a useful shuffled shortcut."""
        from worlds.bloodborne import FULL_POOL_ITEM_KEYS
        from worlds.bloodborne.data import SLICE_ITEM_KEYS
        self.assertIn("hunter_chief_emblem", SLICE_ITEM_KEYS)
        self.assertIn("hunter_chief_emblem", FULL_POOL_ITEM_KEYS)


class EventItemTests(unittest.TestCase):
    def test_every_event_key_used_by_a_gate_is_granted_somewhere(self):
        """A gate on an event nothing awards is an unwinnable seed."""
        granted = {l.locked_item for l in LOCATIONS if l.locked_item}
        events = {i.key for i in ITEMS if i.kind is ItemKind.EVENT}
        used = set()
        for expected in DOCUMENTED_GATES.values():
            for clause in expected:
                used |= {k for k in clause if k in events}
        for key in sorted(used):
            with self.subTest(event=key):
                self.assertIn(key, granted, "gated on an event no location grants")


if __name__ == "__main__":
    unittest.main()
