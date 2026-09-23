"""Protection-audit regression tests: multi-gate overlaps, EMEVD resolver
witnesses, denominator hygiene, and the Central Yharnam case-study numbers.

All inputs come from the committed bundle plus committed research tables; no
game dump is required. See docs/ENEMIZER-PROTECTION-AUDIT.md.
"""
import csv
import json
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path

from tools.build_emevd_entity_usage import (
    build_rows, has_character_operation, materialize_bundle,
)
from tools.bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, inventory_summary, load_slot_overrides,
    load_slots, load_tags,
)
from tools.bb_enemizer.model import canonical_map
from tools.bb_enemizer.planner import EnemizerConfig, plan_swaps

ROOT = Path(__file__).resolve().parents[1]
CENSUS = ROOT / "research/enemizer/emevd_entity_usage.tsv"
AUDIT_JSON = ROOT / "research/enemizer/protection_audit.json"
EVENT_REASON = "entity ID referenced by area EMEVD"


def _census_rows():
    with CENSUS.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class DenominatorTests(unittest.TestCase):
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

    def test_physical_logical_swap_denominators(self):
        self.assertEqual(4186, len(self.slots))
        logical = {slot.logical_key for slot in self.slots}
        self.assertEqual(2646, len(logical))
        policies = {
            slot.key: apply_archetype_tag(
                classify_slot(slot, self.overrides), self.tags.get(slot.archetype.key))
            for slot in self.slots
        }
        swaps, rejections = plan_swaps(self.slots, policies, self.tags, EnemizerConfig("12345"))
        self.assertEqual(308, len(swaps))
        self.assertEqual(2338, len(rejections))
        self.assertEqual(308 + 2338, len(logical))
        # 545 is the whole-plan eligible-physical fan-out, not Central Yharnam.
        summary = inventory_summary(self.slots, policies)
        self.assertEqual(545, summary["eligible_physical_slots"])

    def test_chalice_templates_are_outside_the_inventory(self):
        # The fixed-map filter is what keeps ~664k Chalice rows out of every
        # denominator; dropping it must explode the population.
        all_slots = load_slots(
            Path(self._tmp.name) / "mined/msb_enemies.tsv", fixed_maps_only=False)
        self.assertGreater(len(all_slots), 100000)


class MultiGateTests(unittest.TestCase):
    """First-hit planner reasons hide overlapping independent gates."""

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

    def _gates(self, copies):
        gates = set()
        for slot in copies:
            reason = (self.overrides.get(slot.key) or self.overrides.get(slot.logical_key) or {}).get(
                "reason", "")
            if EVENT_REASON in reason:
                gates.add("emevd")
            if slot.dummy:
                gates.add("dummy")
            if slot.talk_id > 0:
                gates.add("talk")
            if slot.archetype.chara_init_id > 0:
                gates.add("chara_init")
            if not slot.archetype.model_name.startswith("c"):
                gates.add("nonchar")
            if slot.archetype.npc_param_id <= 0 or slot.archetype.think_param_id <= 0:
                gates.add("missing")
        tag = self.tags.get(copies[0].archetype.key)
        if tag is not None and not tag.target:
            gates.add("unapproved")
        return gates

    def test_central_yharnam_first_hit_and_overlap(self):
        grouped = defaultdict(list)
        for slot in self.slots:
            grouped[slot.logical_key].append(slot)
        central = {key: copies for key, copies in grouped.items()
                   if key.startswith("m24_01_00_00:")}
        self.assertEqual(277, len(central))
        policies = {
            slot.key: apply_archetype_tag(
                classify_slot(slot, self.overrides), self.tags.get(slot.archetype.key))
            for slot in self.slots
        }
        swaps, rejections = plan_swaps(self.slots, policies, self.tags, EnemizerConfig("12345"))
        central_swapped = {swap.logical_key for swap in swaps if swap.logical_key in central}
        self.assertEqual(49, len(central_swapped))
        central_rejected = [row for row in rejections if row["logical_key"] in central]
        self.assertEqual(228, len(central_rejected))
        first_hit = Counter(row["reason"] for row in central_rejected)
        self.assertEqual(131, first_hit["protected copy: entity ID referenced by area EMEVD"])
        self.assertEqual(79, first_hit["protected copy: dummy/script-spawn Part"])
        self.assertEqual(10, first_hit["protected copy: character-init-bound NPC or hunter"])
        self.assertEqual(7, first_hit["protected copy: talk-bound character"])
        self.assertEqual(1, first_hit["protected copy: archetype not approved as a target/source"])
        # Overlapping causes: EMEVD plus at least one independent gate.
        emevd_and_other = sum(
            1 for key, copies in central.items()
            if key not in central_swapped
            and "emevd" in self._gates(copies) and len(self._gates(copies)) > 1)
        self.assertEqual(48, emevd_and_other)

    def test_overrides_bypass_physical_gates(self):
        # An EMEVD override reports the EMEVD reason even when the slot is
        # also a dummy/talk/CharaInit placement: first-hit is not exhaustive.
        grouped = defaultdict(list)
        for slot in self.slots:
            grouped[slot.logical_key].append(slot)
        both = [key for key, copies in grouped.items()
                if "emevd" in self._gates(copies) and len(self._gates(copies)) > 1]
        self.assertGreater(len(both), 400)


class EmevdResolverTests(unittest.TestCase):
    """Shared-event resolution, namespace, and lexical-predicate witnesses."""

    def test_common_event_actor_carries_character_operation(self):
        # Witness: m22 c1051 entity 2200710 is passed as chrEntityId into
        # common events 9220/9240/9260/9280 (SetCharacterAIState,
        # ForceAnimationPlayback, CharacterDead, ...). The pre-audit census
        # recorded event_argument only; the corrected census must show a
        # character operation, keeping every c1051 out of the relaxable set.
        rows = [row for row in _census_rows() if row["entity_id"] == "2200710"]
        self.assertGreaterEqual(len(rows), 1)
        for row in rows:
            self.assertTrue(
                has_character_operation(row["usage_classes"]),
                f"common-event character op missing for {row['logical_key']}")
        grouped = defaultdict(list)
        for row in _census_rows():
            grouped[row["logical_key"]].append(row)
        relaxable = {key for key, items in grouped.items()
                     if not any(has_character_operation(item["usage_classes"]) for item in items)}
        self.assertEqual(39, len(relaxable))
        # Witnessed per-key form: relaxable is proven non-empty above, and
        # each member is checked individually (a bare assertFalse(any(...))
        # would trip the witnessless-assertion ratchet).
        for key in sorted(relaxable):
            self.assertNotIn(":c1051_", key)

    def test_no_comment_only_or_cross_canonical_protections(self):
        rows = _census_rows()
        self.assertEqual(0, sum(int(row["comment_lines"]) for row in rows))
        for row in rows:
            own = row["map_name"] + ".emevd.dcx.js"
            canon = canonical_map(row["map_name"]) + ".emevd.dcx.js"
            sources = {entry.split(":")[0] for entry in row["source_lines"].split(";") if entry}
            self.assertTrue(
                own in sources or canon in sources,
                f"broad-area-only protection: {row['logical_key']}")

    def test_snatcher_progression_row_stays_in_census(self):
        rows = [row for row in _census_rows()
                if row["logical_key"] == "m24_00_00_00:c2020_0000"]
        self.assertEqual(2, len(rows))

    def test_unresolved_references_are_zero_and_explicit(self):
        rows = _census_rows()
        unresolved = [row for row in rows if "unresolved_event_reference:" in row["usage_classes"]]
        self.assertEqual(0, len(unresolved))
        summary = json.loads((ROOT / "research/enemizer/emevd_entity_usage_summary.json").read_text(
            encoding="utf-8"))
        self.assertEqual(0, summary["slots_with_unresolved_event_references"])
        self.assertEqual(67, summary["slots_without_character_operations_and_fully_resolved"])

    def test_namespace_collisions_mostly_spurious(self):
        rows = _census_rows()
        colliding = [row for row in rows if row["collides_item_lot_id"] == "True"]
        self.assertEqual(308, len(colliding))
        without_char = [row for row in colliding
                        if not has_character_operation(row["usage_classes"])]
        self.assertEqual(10, len(without_char))


class CommittedAuditArtifactTests(unittest.TestCase):
    def test_protection_audit_json_matches_planner(self):
        report = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        self.assertEqual("bb-enemizer-protection-audit-v1", report["format"])
        self.assertEqual(4186, report["denominators"]["physical_slots"])
        self.assertEqual(2646, report["denominators"]["logical_placements"])
        self.assertEqual(308, report["denominators"]["logical_swaps"])
        central = report["central_yharnam_m24_01"]
        self.assertEqual(277, central["logical"])
        self.assertEqual(49, central["swapped"])
        self.assertEqual(131, central["first_hit"][
            "protected copy: entity ID referenced by area EMEVD"])


if __name__ == "__main__":
    unittest.main()
