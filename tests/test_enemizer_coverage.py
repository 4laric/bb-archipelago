"""Evidence for docs/ENEMIZER-COVERAGE.md: the sharper EMEVD predicate and the
coverage delta it would unlock. These tests reproduce the analysis from the
committed census plus the bundled inventory, so they need no game dump.

They also pin the opt-in wider mode's own determinism (336 swaps), kept
separate from the default determinism pin (308) in research/enemizer/audit.json.
"""
import csv
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from tools.build_emevd_entity_usage import (
    build_rows, has_character_operation, materialize_bundle,
)
from tools.bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
)
from tools.bb_enemizer.planner import EnemizerConfig, plan_swaps

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "research/enemizer/emevd_entity_usage.tsv"
EVENT_REASON = "entity ID referenced by area EMEVD"


def _census_rows():
    with CENSUS.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _by_logical(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["logical_key"]].append(row)
    return grouped


class PredicateTests(unittest.TestCase):
    def test_predicate_reads_the_folded_usage_class_column(self):
        self.assertTrue(has_character_operation("character_operation:38;other_operation:6"))
        self.assertFalse(has_character_operation("event_argument:4"))
        self.assertFalse(has_character_operation("item_lot_operand:2"))
        # A substring must not masquerade as the class name.
        self.assertFalse(has_character_operation("non_character_operationish:1"))
        self.assertFalse(has_character_operation(""))


class CensusDecompositionTests(unittest.TestCase):
    """The precise decomposition of the 2,399 EMEVD-protected slots."""

    def test_protected_slot_total(self):
        self.assertEqual(2399, len(_census_rows()))

    def test_slots_without_a_character_operation(self):
        rows = _census_rows()
        no_char = [r for r in rows if not has_character_operation(r["usage_classes"])]
        self.assertEqual(145, len(no_char))
        self.assertEqual(2254, len(rows) - len(no_char))

    def test_item_lot_collisions_without_a_character_operation(self):
        rows = _census_rows()
        item_lot_only = [
            r for r in rows
            if r["collides_item_lot_id"] == "True"
            and not has_character_operation(r["usage_classes"])
        ]
        self.assertEqual(20, len(item_lot_only))

    def test_logical_keys_fully_free_of_character_operations(self):
        grouped = _by_logical(_census_rows())
        relaxable = [
            key for key, rows in grouped.items()
            if not any(has_character_operation(r["usage_classes"]) for r in rows)
        ]
        # 86 logical placements have no character operation on any copy.
        self.assertEqual(86, len(relaxable))


class CoverageDeltaTests(unittest.TestCase):
    """Run the planner against the real inventory to measure the delta the
    sharper predicate would earn. Inventory comes from the committed bundle."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        inventory, _events = materialize_bundle(
            ROOT / "research/bb_inputs.db", Path(cls._tmp.name))
        cls.slots = load_slots(inventory)
        cls.tags = load_tags(ROOT / "research/enemizer/enemy_tags.json")
        cls.overrides = load_slot_overrides(ROOT / "research/enemizer/slot_policy.json")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _count(self, overrides, seed="12345"):
        policies = {
            s.key: apply_archetype_tag(classify_slot(s, overrides), self.tags.get(s.archetype.key))
            for s in self.slots
        }
        swaps, _ = plan_swaps(self.slots, policies, self.tags, EnemizerConfig(seed))
        return swaps

    def _relaxed_overrides(self):
        grouped = _by_logical(_census_rows())
        relaxable = {
            key for key, rows in grouped.items()
            if not any(has_character_operation(r["usage_classes"]) for r in rows)
        }
        return {
            key: value for key, value in self.overrides.items()
            if not (key in relaxable and value.get("reason") == EVENT_REASON)
        }

    def test_default_swap_set_is_the_pinned_308(self):
        self.assertEqual(308, len(self._count(self.overrides)))

    def test_relaxed_predicate_adds_twenty_eight_swaps(self):
        relaxed = self._relaxed_overrides()
        self.assertEqual(336, len(self._count(relaxed)))

    def test_relaxed_new_swaps_are_all_low_tier(self):
        base = {s.logical_key for s in self._count(self.overrides)}
        relaxed = self._relaxed_overrides()
        policies = {
            s.key: apply_archetype_tag(classify_slot(s, relaxed), self.tags.get(s.archetype.key))
            for s in self.slots
        }
        added = [s for s in self._count(relaxed) if s.logical_key not in base]
        self.assertEqual(28, len(added))
        from collections import Counter
        tiers = Counter(policies[s.destination_keys[0]].tier for s in added)
        # Every newly freed slot is common/elite - no boss tier is relaxed.
        self.assertEqual(0, tiers.get("boss", 0))
        self.assertEqual(28, tiers.get("common", 0) + tiers.get("elite", 0))

    def test_opt_in_mode_has_its_own_determinism_pin(self):
        relaxed = self._relaxed_overrides()
        policies = {
            s.key: apply_archetype_tag(classify_slot(s, relaxed), self.tags.get(s.archetype.key))
            for s in self.slots
        }
        counts = set()
        for index in range(6):
            forward, _ = plan_swaps(self.slots, policies, self.tags, EnemizerConfig(f"wide-{index}"))
            reverse, _ = plan_swaps(list(reversed(self.slots)), policies, self.tags,
                                    EnemizerConfig(f"wide-{index}"))
            self.assertEqual([s.json() for s in forward], [s.json() for s in reverse])
            counts.add(len(forward))
        self.assertEqual({336}, counts)


class CatalogBuilderOptInTests(unittest.TestCase):
    def test_flag_is_off_by_default_and_relaxation_is_wired(self):
        source = (ROOT / "tools/build_enemizer_catalog.py").read_text(encoding="utf-8")
        self.assertIn("--relax-non-character-emevd", source)
        self.assertIn("relaxed_non_character_logical_slots", source)
        # The default remains the blunt rule; relaxation is gated on the flag.
        self.assertIn("if args.relax_non_character_emevd:", source)


if __name__ == "__main__":
    unittest.main()
