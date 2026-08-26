"""The storage-routing probe (clients#445), everything testable without a game.

What these establish and what they cannot: the step list is well formed and
names only allowlisted descriptors, the step engine records the cells it claims
to record, resume reads the same journal the grant CLI writes, the report is
append-only, and — the part that decides whether the session was worth running —
the classifier turns recorded cells into the right verdict, including the
several ways a recording is not evidence at all.

They establish nothing about where the guest actually puts an item. That is the
operator's half, and it is the whole reason the probe exists.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from bb_native_delivery import cli, probe  # noqa: E402
from bb_native_delivery.descriptor import (  # noqa: E402
    describe_validated_descriptor,
    uses_persistent_source,
)
from bb_native_delivery.probe import (  # noqa: E402
    HELD,
    PROBE_STEPS,
    SPLIT,
    STORAGE,
    UNKNOWN,
    DeliveryResult,
    ProbeContext,
    ProbeError,
    ProbeStep,
)


def _record(step_id, hypothesis, observation, **overrides):
    """One report row, with only the cells a classifier reads spelled out."""
    record = {
        "step_id": step_id,
        "hypothesis": hypothesis,
        "observation": observation,
        "item": "Pebble",
        "lane": "in_frame",
        "held_before": 3,
        "held_after": 4,
        "native_result": 4,
        "save_id": "throwaway-a",
    }
    record.update(overrides)
    return record


# The two shapes clients#445 read live, written once so every H1 test agrees on
# what "the normal case" and "the overflow case" mean.
NORMAL_ADD = _record("a1-normal-add", "H1", HELD, held_before=3, held_after=4, native_result=4)
CAP_OVERFLOW = _record(
    "a3-cap-overflow", "H1", STORAGE, held_before=20, held_after=20, native_result=1
)


class StepListTests(unittest.TestCase):
    def test_every_step_names_a_descriptor_the_real_allowlist_accepts(self):
        derivations = [
            describe_validated_descriptor(*step.descriptor) for step in PROBE_STEPS
        ]
        self.assertEqual(len(PROBE_STEPS), len(derivations))
        self.assertEqual(
            sorted({"Pebble", "Blood Vial", "Saw Spear"}),
            sorted({step.item for step in PROBE_STEPS}),
            "the probe must not reach beyond the three validated canaries",
        )

    def test_a_step_naming_an_unallowlisted_item_is_refused(self):
        rogue = replace(PROBE_STEPS[0], step_id="rogue", item="Rifle Spear")
        with self.assertRaises(ProbeError) as caught:
            probe.validate_steps((rogue,))
        self.assertIn("Rifle Spear", str(caught.exception))
        self.assertIn("#146", str(caught.exception), "the refusal must cite the reproduction")

    def test_two_unique_inserts_in_one_pass_are_refused(self):
        unique = next(step for step in PROBE_STEPS if step.consumes_unique)
        twin = replace(unique, step_id=unique.step_id + "-again")
        with self.assertRaises(ProbeError) as caught:
            probe.validate_steps((unique, twin))
        self.assertIn("once per save", str(caught.exception))

    def test_duplicate_step_ids_are_refused_because_they_collide_journal_tags(self):
        first = PROBE_STEPS[0]
        with self.assertRaises(ProbeError) as caught:
            probe.validate_steps((first, replace(first, hypothesis="H4")))
        self.assertIn("duplicate", str(caught.exception))

    def test_the_shipped_step_list_validates(self):
        probe.validate_steps()
        self.assertEqual(10, len(PROBE_STEPS))

    def test_pass_a_spends_its_unique_insert_before_it_overflows_anything(self):
        """Ordering is evidence: an idle-unique step run after a deliberate
        overflow would be measuring H3, not H2."""
        pass_a = [step.step_id for step in probe.steps_for("a")]
        self.assertLess(
            pass_a.index("a2-unique-idle"), pass_a.index("a3-cap-overflow"),
            "H2 needs a state with no preceding overflow",
        )

    def test_each_pass_spends_the_unique_insert_at_most_once(self):
        for pass_name in probe.PROBE_PASSES:
            spent = [step.step_id for step in probe.steps_for(pass_name) if step.consumes_unique]
            self.assertEqual(1, len(spent), f"pass {pass_name}: {spent}")

    def test_the_two_unique_steps_live_in_different_passes(self):
        passes = {step.pass_name for step in PROBE_STEPS if step.consumes_unique}
        self.assertEqual({"a", "b"}, passes,
                         "a save accepts a unique item once, so H2 and H3 cannot share one")

    def test_the_lane_of_each_step_matches_the_descriptor_branch(self):
        lanes = {step.item: step.lane for step in PROBE_STEPS}
        self.assertEqual("persistent", lanes["Saw Spear"])
        self.assertEqual("in_frame", lanes["Pebble"])
        self.assertEqual("in_frame", lanes["Blood Vial"])
        self.assertTrue(uses_persistent_source(probe.PROBE_ITEMS["Saw Spear"][0]))

    def test_an_unknown_pass_is_refused_by_name(self):
        with self.assertRaises(ProbeError):
            probe.steps_for("c")

    def test_a_tag_is_scoped_to_the_save_it_was_recorded_on(self):
        step = PROBE_STEPS[0]
        self.assertNotEqual(step.tag("save-a"), step.tag("save-b"))
        self.assertIn(step.step_id, step.tag("save-a"))

    def test_the_runbook_names_every_step_and_ends_at_the_paste(self):
        text = probe.runbook()
        for step in PROBE_STEPS:
            self.assertIn(step.step_id, text)
            self.assertIn(step.setup, text)
        self.assertIn("THROWAWAY save", text)
        self.assertIn("clients#445", text)


class ObservationParsingTests(unittest.TestCase):
    def test_the_words_an_operator_actually_types_are_understood(self):
        self.assertEqual(HELD, probe.parse_observation("held"))
        self.assertEqual(HELD, probe.parse_observation(" H "))
        self.assertEqual(STORAGE, probe.parse_observation("Storage"))
        self.assertEqual(STORAGE, probe.parse_observation("box"))
        self.assertEqual(SPLIT, probe.parse_observation("both"))

    def test_an_unreadable_answer_is_unknown_not_a_guess(self):
        self.assertEqual(UNKNOWN, probe.parse_observation("no idea"))
        self.assertEqual(UNKNOWN, probe.parse_observation(""))

    def test_counts_parse_and_a_blank_means_not_checked(self):
        self.assertEqual(20, probe.parse_count(" 20 "))
        self.assertIsNone(probe.parse_count(""))
        self.assertIsNone(probe.parse_count("about twenty"))


class StepEngineTests(unittest.TestCase):
    def _context(self, answers, reads, result, save_id="throwaway-a"):
        self.asked = []

        def prompt(question):
            self.asked.append(question)
            return answers.pop(0)

        return ProbeContext(
            save_id=save_id,
            read_stack=lambda _normalized: reads.pop(0),
            deliver=lambda _step, _before: result,
            prompt=prompt,
            now=lambda: "2026-08-26T00:00:00+0000",
        )

    def test_a_step_records_both_read_backs_the_cells_and_the_observation(self):
        step = next(s for s in PROBE_STEPS if s.step_id == "a3-cap-overflow")
        context = self._context(
            answers=["storage", "20", "7", "surplus appeared in the box"],
            reads=[20, 20],
            result=DeliveryResult("failed", "expected_after=21 actual=20", 1, 20, 21),
        )
        record = probe.run_step(step, context)
        self.assertEqual(20, record["held_before"])
        self.assertEqual(20, record["held_after"])
        self.assertEqual(1, record["native_result"])
        self.assertEqual(21, record["expected_after"])
        self.assertEqual("failed", record["delivery_status"])
        self.assertEqual(STORAGE, record["observation"])
        self.assertEqual(7, record["operator_storage_count"])
        self.assertEqual("surplus appeared in the box", record["operator_notes"])
        self.assertEqual("in_frame", record["lane"])
        self.assertFalse(record["uses_persistent_source"])
        self.assertEqual(4, len(self.asked), "one question per recorded cell")

    def test_a_unique_step_records_the_persistent_lane_and_the_once_per_save_flag(self):
        step = next(s for s in PROBE_STEPS if s.step_id == "b3-unique-after-overflow")
        context = self._context(
            answers=["storage", "", "", ""],
            reads=[0, 0],
            result=DeliveryResult("completed", "native_result=91", 91, 0, 1),
        )
        record = probe.run_step(step, context)
        self.assertEqual("persistent", record["lane"])
        self.assertTrue(record["consumes_unique"])
        self.assertEqual("0x806c5660", record["raw_id"])
        self.assertIsNone(record["operator_held_count"])

    def test_an_unreadable_observation_is_recorded_as_unknown(self):
        context = self._context(
            answers=["dunno", "", "", ""], reads=[3, 4],
            result=DeliveryResult("completed", "", 4, 3, 4),
        )
        record = probe.run_step(PROBE_STEPS[0], context)
        self.assertEqual(UNKNOWN, record["observation"])


class ReportTests(unittest.TestCase):
    def test_records_append_and_survive_a_second_session(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "nested" / "probe.jsonl"
            probe.append_record(report, NORMAL_ADD)
            probe.append_record(report, CAP_OVERFLOW)
            records = probe.read_records(report)
            self.assertEqual(["a1-normal-add", "a3-cap-overflow"],
                             [record["step_id"] for record in records])

    def test_a_blank_or_corrupt_line_is_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "probe.jsonl"
            report.write_text(
                json.dumps(NORMAL_ADD) + "\n\nnot json\n" + json.dumps(CAP_OVERFLOW) + "\n",
                encoding="utf-8",
            )
            self.assertEqual(2, len(probe.read_records(report)))

    def test_a_missing_report_reads_as_no_records(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(0, len(probe.read_records(Path(directory) / "absent.jsonl")))

    def test_a_redone_step_supersedes_its_earlier_attempt(self):
        first = _record("a1-normal-add", "H1", UNKNOWN)
        redone = _record("a1-normal-add", "H1", HELD, native_result=4, held_after=4)
        verdict = probe.classify_return_semantics([first, redone, CAP_OVERFLOW])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)


class ResumeTests(unittest.TestCase):
    def test_a_recorded_step_is_skipped_and_the_rest_still_run(self):
        steps = probe.steps_for("a")
        journal = {steps[0].tag("save-a"): {"status": "completed", "probe_status": "recorded"}}
        todo, done = probe.pending_steps(steps, journal, "save-a")
        self.assertEqual([steps[0].step_id], [step.step_id for step in done])
        self.assertEqual([step.step_id for step in steps[1:]],
                         [step.step_id for step in todo])

    def test_a_skipped_step_is_also_terminal(self):
        steps = probe.steps_for("a")
        journal = {steps[1].tag("save-a"): {"status": "armed", "probe_status": "skipped"}}
        _todo, done = probe.pending_steps(steps, journal, "save-a")
        self.assertEqual([steps[1].step_id], [step.step_id for step in done])

    def test_an_interrupted_step_is_offered_again(self):
        steps = probe.steps_for("a")
        journal = {steps[0].tag("save-a"): {"status": "interrupted",
                                           "probe_status": "interrupted"}}
        todo, done = probe.pending_steps(steps, journal, "save-a")
        self.assertEqual(len(steps), len(todo), f"done: {[s.step_id for s in done]}")

    def test_resume_cannot_cross_saves(self):
        steps = probe.steps_for("a")
        journal = {steps[0].tag("save-a"): {"probe_status": "recorded"}}
        todo, _done = probe.pending_steps(steps, journal, "save-b")
        self.assertEqual(len(steps), len(todo),
                         "a different throwaway save has run nothing")

    def test_probe_state_rides_in_the_grant_journal_not_a_parallel_store(self):
        """#147's journal is the one store. A probe step is a grant with a tag,
        so its resume state has to be visible to the reused-tag gate."""
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "journal.json"
            step = PROBE_STEPS[0]
            cli._record_tag(journal, step.tag("save-a"), "completed", probe_status="recorded")
            written = json.loads(journal.read_text(encoding="utf-8"))
            entry = written[step.tag("save-a")]
            self.assertEqual("completed", entry["status"])
            self.assertEqual("recorded", entry["probe_status"])
            self.assertEqual(1, len(written), "exactly one store, keyed by grant tag")
            todo, done = probe.pending_steps((step,), cli._read_journal(journal), "save-a")
            self.assertEqual([step.step_id], [s.step_id for s in done])
            self.assertEqual(0, len(todo))


class ReturnSemanticsVerdictTests(unittest.TestCase):
    def test_the_hypothesis_is_supported_by_a_normal_add_and_an_overflow(self):
        verdict = probe.classify_return_semantics([NORMAL_ADD, CAP_OVERFLOW])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("a1-normal-add", verdict.witnesses)
        self.assertIn("a3-cap-overflow", verdict.witnesses)

    def test_an_overflow_returning_anything_but_one_refutes_it(self):
        verdict = probe.classify_return_semantics(
            [NORMAL_ADD, _record("a3-cap-overflow", "H1", STORAGE, native_result=20,
                                 held_before=20, held_after=20)]
        )
        self.assertEqual(probe.REFUTED, verdict.verdict)
        self.assertIn("not 1", verdict.reason)

    def test_a_normal_add_whose_result_is_not_the_final_count_refutes_it(self):
        verdict = probe.classify_return_semantics(
            [_record("a1-normal-add", "H1", HELD, native_result=79, held_after=4),
             CAP_OVERFLOW]
        )
        self.assertEqual(probe.REFUTED, verdict.verdict)
        self.assertIn("final held count", verdict.reason)

    def test_one_case_alone_is_unclear_because_the_claim_is_a_contrast(self):
        verdict = probe.classify_return_semantics([NORMAL_ADD])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("at-cap add", verdict.reason)

    def test_an_unreadable_held_count_cannot_confirm_a_normal_add(self):
        verdict = probe.classify_return_semantics(
            [_record("a1-normal-add", "H1", HELD, held_after=None, native_result=4),
             CAP_OVERFLOW]
        )
        self.assertEqual(probe.REFUTED, verdict.verdict)


class IdleUniqueVerdictTests(unittest.TestCase):
    def test_a_unique_landing_held_while_idle_supports_it(self):
        verdict = probe.classify_idle_unique(
            [_record("a2-unique-idle", "H2", HELD, item="Saw Spear", lane="persistent")]
        )
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("persistent", verdict.reason)

    def test_a_unique_landing_in_storage_while_idle_refutes_the_order_story(self):
        verdict = probe.classify_idle_unique(
            [_record("a2-unique-idle", "H2", STORAGE, item="Saw Spear", lane="persistent")]
        )
        self.assertEqual(probe.REFUTED, verdict.verdict)
        self.assertIn("Order/tempo cannot be the term", verdict.reason)

    def test_a_step_that_was_not_run_is_unclear(self):
        verdict = probe.classify_idle_unique([NORMAL_ADD])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("was not run", verdict.reason)


class StickyVerdictTests(unittest.TestCase):
    IDLE_HELD = _record("a2-unique-idle", "H2", HELD, item="Saw Spear", lane="persistent")
    OVERFLOW = _record("b2-vial-overflow", "H1", STORAGE, item="Blood Vial",
                       held_before=20, held_after=20, native_result=1)

    def test_a_unique_going_to_storage_right_after_an_overflow_supports_sticky(self):
        verdict = probe.classify_sticky([
            self.IDLE_HELD, self.OVERFLOW,
            _record("b3-unique-after-overflow", "H3", STORAGE, item="Saw Spear",
                    lane="persistent"),
        ])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("landed HELD when delivered idle", verdict.reason)

    def test_without_the_idle_control_the_support_says_so(self):
        verdict = probe.classify_sticky([
            _record("a2-unique-idle", "H2", UNKNOWN, item="Saw Spear", lane="persistent"),
            self.OVERFLOW,
            _record("b3-unique-after-overflow", "H3", STORAGE, item="Saw Spear",
                    lane="persistent"),
        ])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("cannot separate sticky from always-storage", verdict.reason)

    def test_a_unique_landing_held_after_an_overflow_refutes_sticky(self):
        verdict = probe.classify_sticky([
            self.OVERFLOW,
            _record("b3-unique-after-overflow", "H3", HELD, item="Saw Spear",
                    lane="persistent"),
        ])
        self.assertEqual(probe.REFUTED, verdict.verdict)

    def test_without_a_witnessed_overflow_the_sticky_window_was_never_armed(self):
        verdict = probe.classify_sticky([
            _record("b2-vial-overflow", "H1", HELD, item="Blood Vial"),
            _record("b3-unique-after-overflow", "H3", STORAGE, item="Saw Spear",
                    lane="persistent"),
        ])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("never armed", verdict.reason)

    def test_a_sub_cap_goods_add_also_stored_widens_the_scope(self):
        verdict = probe.classify_sticky([
            self.IDLE_HELD, self.OVERFLOW,
            _record("b3-unique-after-overflow", "H3", STORAGE, item="Saw Spear",
                    lane="persistent"),
            _record("b5-goods-after-overflow", "H3", STORAGE, held_before=3, held_after=3),
        ])
        self.assertIn("not specific to unique items", verdict.reason)

    def test_a_sub_cap_goods_add_landing_held_narrows_the_scope(self):
        verdict = probe.classify_sticky([
            self.IDLE_HELD, self.OVERFLOW,
            _record("b3-unique-after-overflow", "H3", STORAGE, item="Saw Spear",
                    lane="persistent"),
            _record("b5-goods-after-overflow", "H3", HELD),
        ])
        self.assertIn("specific to the unique insert", verdict.reason)


class StateVerdictTests(unittest.TestCase):
    POST_BOSS_STORED = _record("a4-post-boss", "H4", STORAGE, held_before=3, held_after=3)
    MENU_HELD = _record("a5-non-gameplay", "H4", HELD)

    def test_a_state_case_diverging_from_the_idle_baseline_supports_it(self):
        verdict = probe.classify_state([NORMAL_ADD, self.POST_BOSS_STORED, self.MENU_HELD])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("a4-post-boss", verdict.reason)
        self.assertIn("did NOT diverge", verdict.reason)

    def test_every_state_case_matching_the_baseline_refutes_it(self):
        verdict = probe.classify_state([
            NORMAL_ADD, _record("a4-post-boss", "H4", HELD), self.MENU_HELD,
        ])
        self.assertEqual(probe.REFUTED, verdict.verdict)

    def test_without_an_idle_baseline_a_state_case_has_nothing_to_differ_from(self):
        verdict = probe.classify_state([self.POST_BOSS_STORED])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("nothing to differ FROM", verdict.reason)

    def test_a_baseline_with_no_state_case_is_unclear(self):
        verdict = probe.classify_state([NORMAL_ADD])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("neither state case", verdict.reason)


class LaneVerdictTests(unittest.TestCase):
    def test_a_lane_producing_both_destinations_rules_the_lane_out(self):
        verdict = probe.classify_lane([
            NORMAL_ADD, CAP_OVERFLOW,
            _record("b3-unique-after-overflow", "H3", STORAGE, lane="persistent"),
        ])
        self.assertEqual(probe.REFUTED, verdict.verdict)
        self.assertIn("in_frame", verdict.reason)

    def test_a_clean_split_is_reported_as_a_correlation_and_labelled_one(self):
        verdict = probe.classify_lane([
            NORMAL_ADD,
            _record("b3-unique-after-overflow", "H3", STORAGE, lane="persistent"),
        ])
        self.assertEqual(probe.SUPPORTED, verdict.verdict)
        self.assertIn("CORRELATION ONLY", verdict.reason)

    def test_one_lane_alone_cannot_separate_anything(self):
        verdict = probe.classify_lane([NORMAL_ADD, _record("a5-non-gameplay", "H4", HELD)])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)
        self.assertIn("one lane cannot separate", verdict.reason)

    def test_no_readable_destination_is_unclear(self):
        verdict = probe.classify_lane([_record("a1-normal-add", "H1", UNKNOWN)])
        self.assertEqual(probe.UNCLEAR, verdict.verdict)


class SummaryRenderingTests(unittest.TestCase):
    def _summary(self):
        return probe.render_summary(
            [NORMAL_ADD, CAP_OVERFLOW,
             _record("a2-unique-idle", "H2", HELD, item="Saw Spear", lane="persistent")],
            save_ids=("throwaway-a",),
        )

    def test_every_recorded_step_gets_a_row_with_its_cells(self):
        text = self._summary()
        for step_id in ("a1-normal-add", "a3-cap-overflow", "a2-unique-idle"):
            self.assertIn(step_id, text)
        self.assertIn("| H1 |", text)
        self.assertIn("throwaway-a", text)

    def test_each_hypothesis_gets_a_verdict_line(self):
        text = self._summary()
        for hypothesis in ("H1", "H2", "H3", "H4", "lane"):
            self.assertIn(f"**{hypothesis} ", text)
        self.assertIn("SUPPORTED", text)
        self.assertIn("UNCLEAR", text)

    def test_the_summary_says_what_an_unclear_verdict_means(self):
        self.assertIn("not a weak result", self._summary())

    def test_the_summary_states_its_own_evidence_boundary(self):
        text = self._summary()
        self.assertIn("throwaway save", text)
        self.assertIn("CUSA03173 01.09", text)
        self.assertIn("guarded contract", text)


class ProbeCliTests(unittest.TestCase):
    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.build_parser().parse_args(argv).func(
                cli.build_parser().parse_args(argv))
        return code, buffer.getvalue()

    def test_the_runbook_needs_no_pid_and_touches_no_process(self):
        code, output = self._run(["probe-storage", "--runbook"])
        self.assertEqual(0, code)
        self.assertIn("a2-unique-idle", output)

    def test_arming_without_asserting_a_throwaway_save_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._run([
                "probe-storage", "--pid", "1", "--save-id", "s", "--arm",
                "--journal", str(Path(directory) / "j.json"),
                "--report", str(Path(directory) / "r.jsonl"),
            ])
        self.assertEqual(1, code)
        self.assertIn("--yes-throwaway-save", output)

    def test_a_run_without_a_save_id_is_refused_before_anything_attaches(self):
        code, output = self._run(["probe-storage", "--pid", "1"])
        self.assertEqual(1, code)
        self.assertIn("--save-id", output)

    def test_a_dry_run_rehearses_the_steps_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "j.json"
            report = Path(directory) / "r.jsonl"
            code, output = self._run([
                "probe-storage", "--pid", "1", "--save-id", "s", "--pass", "b",
                "--journal", str(journal), "--report", str(report),
            ])
            self.assertEqual(0, code)
            self.assertIn("b3-unique-after-overflow", output)
            self.assertIn("Dry run", output)
            self.assertFalse(journal.exists(), "a rehearsal must not journal a tag")
            self.assertFalse(report.exists(), "a rehearsal must not write a report")

    def test_an_unknown_step_id_is_refused(self):
        code, output = self._run([
            "probe-storage", "--pid", "1", "--save-id", "s", "--only", "a9-nope",
        ])
        self.assertEqual(1, code)
        self.assertIn("a9-nope", output)

    def test_a_summary_of_an_empty_report_is_a_red_not_an_empty_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._run([
                "probe-storage", "--summary", "--report", str(Path(directory) / "none.jsonl"),
            ])
        self.assertEqual(1, code)
        self.assertIn("Nothing to summarise", output)

    def test_a_summary_renders_the_recorded_report_and_names_the_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "r.jsonl"
            probe.append_record(report, NORMAL_ADD)
            probe.append_record(report, CAP_OVERFLOW)
            code, output = self._run(["probe-storage", "--summary", "--report", str(report)])
        self.assertEqual(0, code)
        self.assertIn("H1 SUPPORTED", output)
        self.assertIn("clients#445", output)

    def test_every_selected_step_already_recorded_ends_the_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "j.json"
            for step in probe.steps_for("b"):
                cli._record_tag(journal, step.tag("s"), "completed", probe_status="recorded")
            code, output = self._run([
                "probe-storage", "--pid", "1", "--save-id", "s", "--pass", "b",
                "--journal", str(journal), "--report", str(Path(directory) / "r.jsonl"),
            ])
        self.assertEqual(0, code)
        self.assertIn("already recorded", output)

    def test_the_probe_subcommand_offers_no_unvalidated_descriptor_escape_hatch(self):
        parser = cli.build_parser()
        options = {
            action.dest for action in parser._subparsers._group_actions[0]
            .choices["probe-storage"]._actions
        }
        self.assertNotIn("unvalidated_descriptor", options)
        self.assertNotIn("raw", options)
        self.assertIn("yes_throwaway_save", options)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
