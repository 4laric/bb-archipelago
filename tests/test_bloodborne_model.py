import unittest

from worlds.bloodborne.data import MODEL
from worlds.bloodborne.model import Rule
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS
from worlds.bloodborne import ITEM_ID_BY_KEY, ITEM_NAME_TO_ID, LOCATION_ID_BY_KEY


class BloodborneModelTests(unittest.TestCase):
    def test_model_references_are_valid(self):
        self.assertEqual([], MODEL.validate())

    def test_rule_dnf(self):
        rule = Rule.any(("a", "b"), ("c",))
        self.assertTrue(rule.allows({"a", "b"}))
        self.assertTrue(rule.allows({"c"}))
        self.assertFalse(rule.allows({"a"}))

    def test_runtime_item_bindings_cover_shufflable_items(self):
        expected = {item.key for item in MODEL.items if item.kind.value != "event"}
        self.assertEqual(expected, set(ITEM_BINDINGS))

    def test_fixed_pickup_flags_cover_randomized_pickups(self):
        expected = {location.key for location in MODEL.locations if not location.locked_item}
        self.assertEqual(expected, set(LOCATION_BINDINGS))
        self.assertTrue(all(binding.event_flag for binding in LOCATION_BINDINGS.values()))

    def test_vertical_slice_ids_are_complete_and_disjoint(self):
        shufflable = {item.key for item in MODEL.items if item.kind.value != "event"}
        self.assertEqual(shufflable, set(ITEM_ID_BY_KEY))
        self.assertEqual({location.key for location in MODEL.locations}, set(LOCATION_ID_BY_KEY))
        self.assertEqual(len(ITEM_NAME_TO_ID), len(shufflable) + 1)  # Blood Vial filler
        self.assertFalse(set(ITEM_NAME_TO_ID.values()) & set(LOCATION_ID_BY_KEY.values()))

    def test_region_progression_graph_is_acyclic(self):
        edges = {}
        for entrance in MODEL.entrances:
            edges.setdefault(entrance.source, set()).add(entrance.target)
        visiting = set()
        visited = set()

        def visit(region):
            self.assertNotIn(region, visiting, f"progression cycle at {region}")
            if region in visited:
                return
            visiting.add(region)
            for target in edges.get(region, ()):
                visit(target)
            visiting.remove(region)
            visited.add(region)

        for region in MODEL.regions:
            visit(region)


if __name__ == "__main__":
    unittest.main()
