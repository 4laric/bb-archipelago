import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_shuffle import (
    REGISTRY,
    event_blocks,
    patch_template_swap,
    plan_boss_shuffle,
    plan_template_swap,
    profile_catalog,
    validate_registry,
    validate_template,
    verify_swap_invariants,
)
from tools.bb_enemizer.boss_canary import CHANGED_EVENTS, COMPLETION_EVENT
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.build_boss_catalog import build as build_catalog

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class BossShuffleRegressionTests(unittest.TestCase):
    """The generalized engine, run against the one registered template,
    must reproduce boss_canary.py's own hand-verified behavior exactly."""

    @classmethod
    def setUpClass(cls):
        files = read_prefix(BUNDLE, "event/")
        cls.destination = next(v.decode("utf-8-sig") for k, v in files.items() if k.endswith("m24_01_00_00.emevd.dcx.js"))
        cls.donor = next(v.decode("utf-8-sig") for k, v in files.items() if k.endswith("m23_00_00_00.emevd.dcx.js"))
        cls.template = REGISTRY[0]

    def test_generalized_patch_matches_canary_invariants(self):
        before = event_blocks(self.destination)
        after = event_blocks(patch_template_swap(self.template, self.destination, self.donor))
        self.assertEqual(set(before), set(after))
        self.assertEqual(CHANGED_EVENTS, sorted(k for k in before if before[k] != after[k]))
        self.assertEqual(before[COMPLETION_EVENT], after[COMPLETION_EVENT])

    def test_generalized_verifier_rejects_identity_and_progression_breaks(self):
        original = event_blocks(self.destination)
        mutated_identity = dict(original)
        del mutated_identity[COMPLETION_EVENT]
        with self.assertRaisesRegex(ValueError, "changed event identity set"):
            verify_swap_invariants(original, mutated_identity, self.template)

        # COMPLETION_EVENT is not itself in changed_events, so tampering with
        # it is caught by the generic "touched unrelated event" guard before
        # the dedicated progression-event check ever runs; both guards exist
        # to preserve the same invariant boss_canary.py names explicitly.
        mutated_progression = dict(original)
        mutated_progression[COMPLETION_EVENT] = mutated_progression[COMPLETION_EVENT] + "\n// tampered"
        with self.assertRaisesRegex(ValueError, f"touched unrelated event {COMPLETION_EVENT}"):
            verify_swap_invariants(original, mutated_progression, self.template)
        # If a hypothetical future template DID list the completion event as
        # one of its own changed_events, the dedicated check still fires.
        mutated_template = self.template.__class__(**{**self.template.__dict__, "changed_events": self.template.changed_events + (COMPLETION_EVENT,)})
        with self.assertRaisesRegex(ValueError, "changed destination progression event"):
            verify_swap_invariants(original, mutated_progression, mutated_template)

        mutated_unrelated = dict(original)
        untouched_event = next(k for k in original if k not in self.template.changed_events and k != COMPLETION_EVENT)
        mutated_unrelated[untouched_event] = mutated_unrelated[untouched_event] + "\n// tampered"
        with self.assertRaisesRegex(ValueError, "touched unrelated event"):
            verify_swap_invariants(original, mutated_unrelated, self.template)

    def test_source_drift_is_refused_through_the_generalized_wrapper(self):
        with self.assertRaisesRegex(ValueError, "unsupported original"):
            patch_template_swap(self.template, self.destination.replace("3028", "3029"), self.donor)

    def test_wrapper_enforces_pins_when_a_future_callback_does_not(self):
        unguarded = replace(self.template, patch=lambda destination, donor: destination)
        with self.assertRaisesRegex(ValueError, "unsupported original donor"):
            patch_template_swap(unguarded, self.destination, self.donor.replace("7010", "7012"))

    def test_template_cannot_claim_a_changed_event_without_a_destination_pin(self):
        unhashed = replace(self.template, destination_expected={})
        with self.assertRaisesRegex(ValueError, "no destination event hash pins"):
            validate_template(unhashed)

    def test_template_swap_reproduces_canary_provenance_plan(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        plan = plan_template_swap(self.template, slots, npcs, effects)
        self.assertEqual(self.template.name, plan["template"])
        self.assertEqual(3, len(plan["swap"]["destination_keys"]))
        with self.assertRaisesRegex(ValueError, "provenance"):
            plan_template_swap(self.template, [s for s in slots if s.map_name != "m24_01_00_01"], npcs, effects)


class BossShuffleCatalogCoverageTests(unittest.TestCase):
    """Every boss the mined catalog knows about must be accounted for: either
    covered by a registered SwapTemplate, or reported unsupported with a
    specific, non-generic reason. None may be silently dropped."""

    @classmethod
    def setUpClass(cls):
        cls.catalog = build_catalog(BUNDLE)

    def test_all_22_ap_bosses_are_covered_or_explained(self):
        covered, unsupported = profile_catalog(self.catalog)
        self.assertEqual(22, len(covered) + len(unsupported))
        covered_keys = {record["key"] for record in covered}
        self.assertIn("m24_01_00_00:12411700", covered_keys)  # Cleric Beast (destination)
        self.assertNotIn("m23_00_00_00:12301800", covered_keys)  # donor is not its own destination
        self.assertEqual(21, len(unsupported))
        for record in unsupported:
            self.assertTrue(record["reason"])
            self.assertNotEqual("", record["reason"].strip())

    def test_multi_actor_bosses_get_the_ambiguous_remap_reason(self):
        _, unsupported = profile_catalog(self.catalog)
        by_key = {record["key"]: record for record in unsupported}
        witch = by_key["m22_00_00_00:12201800"]
        self.assertIn("distinct actors", witch["reason"])
        self.assertEqual("multiple_actors", witch["actor_shape"])

    def test_single_actor_non_registered_bosses_get_a_specific_unsafe_derivation_reason(self):
        _, unsupported = profile_catalog(self.catalog)
        by_key = {record["key"]: record for record in unsupported}
        rom = by_key["m32_00_00_00:13201800"]
        self.assertEqual("single_actor", rom["actor_shape"])
        self.assertIn("no hand-verified SwapTemplate registered", rom["reason"])

    def test_registered_donor_remains_explicitly_unsupported_as_a_destination(self):
        _, unsupported = profile_catalog(self.catalog)
        by_key = {record["key"]: record for record in unsupported}
        self.assertIn("registered only as a donor", by_key["m23_00_00_00:12301800"]["reason"])

    def test_unsupported_reasons_are_not_silently_generic(self):
        _, unsupported = profile_catalog(self.catalog)
        reasons = {record["reason"] for record in unsupported}
        # At least two distinct reason shapes must appear (multi-actor vs.
        # single-actor-without-template); a single boilerplate string would
        # indicate the reasons were not actually derived per boss.
        self.assertGreaterEqual(len(reasons), 2)


class BossShuffleCliPlanTests(unittest.TestCase):
    def test_full_shuffle_plan_is_planned_not_written_and_reports_unsupported(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(path)
        npcs, effects = load_params(BUNDLE)
        catalog = build_catalog(BUNDLE)
        plan = plan_boss_shuffle("999", slots, npcs, effects, catalog)
        self.assertEqual("bb-enemizer-boss-shuffle-plan-v1", plan["format"])
        self.assertEqual("planned", plan["status"])
        self.assertEqual("not_written", plan["writer_status"])
        self.assertEqual("partial", plan["coverage_status"])
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(["bsb-at-cleric-v1"], plan["templates_planned"])
        self.assertFalse(plan["template_failures"])
        self.assertEqual(21, plan["unsupported_count"])
        self.assertEqual(json.loads(json.dumps(plan)), plan)  # fully JSON-serializable

    def test_failed_template_is_not_reported_as_planned(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = [slot for slot in load_slots(path) if slot.map_name != "m24_01_00_01"]
        npcs, effects = load_params(BUNDLE)
        plan = plan_boss_shuffle("999", slots, npcs, effects, build_catalog(BUNDLE))
        self.assertEqual("failed", plan["status"])
        self.assertEqual("not_written", plan["writer_status"])
        self.assertEqual(0, plan["swap_count"])
        self.assertFalse(plan["templates_planned"])
        self.assertEqual("bsb-at-cleric-v1", plan["template_failures"][0]["template"])
        self.assertIn("provenance", plan["template_failures"][0]["reason"])

    def test_registry_rejects_two_templates_that_would_write_one_event_file(self):
        duplicate = replace(REGISTRY[0], name="other-bsb-at-cleric")
        with self.assertRaisesRegex(ValueError, "colliding destination event file"):
            validate_registry((REGISTRY[0], duplicate))

    def test_cli_rejects_combining_the_two_boss_modes(self):
        from tools.bb_enemizer.cli import parser
        with self.assertRaises(SystemExit):
            parser().parse_args(["--seed", "999", "--output", "plan.json", "--boss-canary", "--boss-shuffle"])


if __name__ == "__main__":
    unittest.main()
