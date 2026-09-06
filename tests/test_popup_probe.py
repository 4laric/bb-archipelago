"""The native-item-popup probe (issue #330), everything testable without a game.

Mirrors tests/test_storage_probe.py in shape: step-list validity, observation
parsing, the step engine against a fake context, resume against the shared
grant journal, and the classifiers -- including the one property this probe
adds that the storage probe does not have, a positive control whose failure
must stop the session rather than produce a verdict.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from bb_native_delivery import cli, popup_probe  # noqa: E402
from bb_native_delivery.popup_probe import (  # noqa: E402
    DEFERRED,
    MODAL,
    NONE_OBS,
    POPUP,
    POPUP_STEPS,
    PROBE_DEFECT,
    REFUTED,
    SUPPORTED,
    UNCLEAR,
    UNKNOWN,
    DeliveryResult,
    PopupProbeContext,
    PopupProbeError,
    PopupStep,
)


def _record(step_id, hypothesis, observation, **overrides):
    record = {
        "step_id": step_id,
        "hypothesis": hypothesis,
        "observation": observation,
        "lane": "event_award",
        "item": "Communion",
        "save_id": "throwaway-a",
    }
    record.update(overrides)
    return record


CONTROL_OK = _record("control-vanilla-pickup", "control", POPUP, lane="vanilla", item="(no delivery)")
CONTROL_FAILED = _record("control-vanilla-pickup", "control", NONE_OBS, lane="vanilla", item="(no delivery)")


class StepListTests(unittest.TestCase):
    def test_the_shipped_step_list_validates(self):
        popup_probe.validate_steps()
        self.assertEqual(5, len(POPUP_STEPS))

    def test_the_control_step_is_first_and_delivers_nothing(self):
        self.assertEqual("control-vanilla-pickup", POPUP_STEPS[0].step_id)
        self.assertEqual(0, POPUP_STEPS[0].quantity)

    def test_every_delivering_step_names_a_popup_probe_item(self):
        for step in POPUP_STEPS:
            if step.quantity > 0:
                self.assertIn(step.item, popup_probe.POPUP_ITEMS)

    def test_a_step_naming_an_unknown_lane_is_refused(self):
        with self.assertRaises(PopupProbeError):
            PopupStep(
                step_id="rogue", hypothesis="x", lane="teleport", item="Pebble",
                quantity=1, setup="", observe="", expected=POPUP, rationale="",
            )

    def test_a_delivering_step_naming_an_unknown_item_is_refused(self):
        with self.assertRaises(PopupProbeError):
            PopupStep(
                step_id="rogue", hypothesis="x", lane="itemgrant", item="Rifle Spear",
                quantity=1, setup="", observe="", expected=POPUP, rationale="",
            )

    def test_an_extra_question_needs_its_key_and_vice_versa(self):
        with self.assertRaises(PopupProbeError):
            PopupStep(
                step_id="rogue", hypothesis="x", lane="vanilla", item="(no delivery)",
                quantity=0, setup="", observe="", expected=POPUP, rationale="",
                extra_question="huh?",
            )

    def test_duplicate_step_ids_are_refused(self):
        first = POPUP_STEPS[0]
        with self.assertRaises(PopupProbeError):
            popup_probe.validate_steps((first, first))

    def test_the_communion_token_descriptor_is_the_category4_goods_formula(self):
        raw, normalized = popup_probe.POPUP_ITEMS["Communion"]
        self.assertEqual(0xB0000000 | popup_probe.COMMUNION_TOKEN_GOODS_ID, raw)
        self.assertEqual(0x40000000 | popup_probe.COMMUNION_TOKEN_GOODS_ID, normalized)

    def test_the_runbook_names_every_step_and_the_mark_command(self):
        text = popup_probe.runbook()
        for step in POPUP_STEPS:
            self.assertIn(step.step_id, text)
            self.assertIn(f"mark {step.step_id}", text)
        self.assertIn("issue #330", text)
        self.assertIn("probe defect", text.lower())


class ObservationParsingTests(unittest.TestCase):
    def test_the_words_an_operator_actually_types_are_understood(self):
        self.assertEqual(POPUP, popup_probe.parse_observation("popup"))
        self.assertEqual(POPUP, popup_probe.parse_observation(" P "))
        self.assertEqual(MODAL, popup_probe.parse_observation("Modal"))
        self.assertEqual(NONE_OBS, popup_probe.parse_observation("none"))
        self.assertEqual(DEFERRED, popup_probe.parse_observation("deferred"))

    def test_an_unreadable_answer_is_unknown_not_a_guess(self):
        self.assertEqual(UNKNOWN, popup_probe.parse_observation("no idea"))
        self.assertEqual(UNKNOWN, popup_probe.parse_observation(""))

    def test_yes_no_parsing(self):
        self.assertEqual("y", popup_probe.parse_yes_no("Y"))
        self.assertEqual("n", popup_probe.parse_yes_no("no"))
        self.assertEqual(UNKNOWN, popup_probe.parse_yes_no("maybe"))


class StepEngineTests(unittest.TestCase):
    def _context(self, answers, result=None, save_id="throwaway-a"):
        self.asked = []

        def prompt(question):
            self.asked.append(question)
            return answers.pop(0)

        return PopupProbeContext(
            save_id=save_id,
            deliver=lambda _step: result or DeliveryResult(),
            prompt=prompt,
            now=lambda: "2026-09-06T00:00:00+0000",
        )

    def test_the_control_step_asks_only_the_popup_question_and_notes(self):
        step = POPUP_STEPS[0]
        context = self._context(answers=["popup", "looked fine"])
        record = popup_probe.run_step(step, context)
        self.assertEqual(POPUP, record["observation"])
        self.assertEqual("looked fine", record["operator_notes"])
        self.assertEqual(2, len(self.asked))
        self.assertNotIn("nonblocking", record)

    def test_a_delivering_step_calls_deliver_and_records_the_result(self):
        step = next(s for s in POPUP_STEPS if s.step_id == "itemgrant-pebble")
        context = self._context(
            answers=["none", ""],
            result=DeliveryResult(status="completed", detail="ok", native_result=4),
        )
        record = popup_probe.run_step(step, context)
        self.assertEqual("completed", record["delivery_status"])
        self.assertEqual(4, record["native_result"])
        self.assertEqual(NONE_OBS, record["observation"])

    def test_a_step_with_an_extra_question_records_it_under_its_key(self):
        step = next(s for s in POPUP_STEPS if s.step_id == "award-while-menu-open")
        context = self._context(answers=["deferred", "y", ""])
        record = popup_probe.run_step(step, context)
        self.assertEqual("y", record["nonblocking"])
        self.assertEqual(DEFERRED, record["observation"])

    def test_a_no_delivery_step_never_calls_deliver(self):
        step = next(s for s in POPUP_STEPS if s.step_id == "award-after-reload")

        def boom(_step):
            raise AssertionError("a no-delivery step must not call deliver")

        answers = iter(["popup", "y", ""])
        context = PopupProbeContext(
            save_id="s", deliver=boom,
            prompt=lambda _question: next(answers),
            now=lambda: "2026-09-06T00:00:00+0000",
        )
        record = popup_probe.run_step(step, context)
        self.assertEqual("y", record["persisted"])


class ReportTests(unittest.TestCase):
    def test_records_append_and_read_back(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "nested" / "popup.jsonl"
            popup_probe.append_record(report, CONTROL_OK)
            records = popup_probe.read_records(report)
            self.assertEqual(["control-vanilla-pickup"], [r["step_id"] for r in records])


class ResumeTests(unittest.TestCase):
    def test_a_recorded_step_is_skipped_and_the_rest_still_run(self):
        journal = {POPUP_STEPS[0].tag("save-a"): {"probe_status": "recorded"}}
        todo, done = popup_probe.pending_steps(POPUP_STEPS, journal, "save-a")
        self.assertEqual([POPUP_STEPS[0].step_id], [s.step_id for s in done])
        self.assertEqual([s.step_id for s in POPUP_STEPS[1:]], [s.step_id for s in todo])

    def test_resume_cannot_cross_saves(self):
        journal = {POPUP_STEPS[0].tag("save-a"): {"probe_status": "recorded"}}
        todo, _done = popup_probe.pending_steps(POPUP_STEPS, journal, "save-b")
        self.assertEqual(len(POPUP_STEPS), len(todo))


class ControlVerdictTests(unittest.TestCase):
    def test_a_passing_control_is_supported(self):
        verdict = popup_probe.classify_control([CONTROL_OK])
        self.assertEqual(SUPPORTED, verdict.verdict)

    def test_a_failing_control_is_a_probe_defect(self):
        verdict = popup_probe.classify_control([CONTROL_FAILED])
        self.assertEqual(PROBE_DEFECT, verdict.verdict)

    def test_a_control_never_run_is_unclear(self):
        verdict = popup_probe.classify_control([])
        self.assertEqual(UNCLEAR, verdict.verdict)


class ItemgrantVerdictTests(unittest.TestCase):
    def test_no_popup_refutes_the_hypothesis(self):
        record = _record("itemgrant-pebble", "itemgrant_presents_popup", NONE_OBS, item="Pebble")
        verdict = popup_probe.classify_itemgrant([record])
        self.assertEqual(REFUTED, verdict.verdict)

    def test_a_popup_supports_the_hypothesis(self):
        record = _record("itemgrant-pebble", "itemgrant_presents_popup", POPUP, item="Pebble")
        verdict = popup_probe.classify_itemgrant([record])
        self.assertEqual(SUPPORTED, verdict.verdict)

    def test_a_modal_refutes_and_is_flagged_a_permanent_closure(self):
        record = _record("itemgrant-pebble", "itemgrant_presents_popup", MODAL, item="Pebble")
        verdict = popup_probe.classify_itemgrant([record])
        self.assertEqual(REFUTED, verdict.verdict)
        self.assertIn("permanently closes", verdict.reason)

    def test_not_run_is_unclear(self):
        verdict = popup_probe.classify_itemgrant([])
        self.assertEqual(UNCLEAR, verdict.verdict)


class AwardPresentsVerdictTests(unittest.TestCase):
    def test_a_popup_supports_the_mechanism_prediction(self):
        record = _record("award-rune-token", "award_presents_popup", POPUP)
        verdict = popup_probe.classify_award_presents([record])
        self.assertEqual(SUPPORTED, verdict.verdict)

    def test_none_refutes_it(self):
        record = _record("award-rune-token", "award_presents_popup", NONE_OBS)
        verdict = popup_probe.classify_award_presents([record])
        self.assertEqual(REFUTED, verdict.verdict)

    def test_modal_refutes_it(self):
        record = _record("award-rune-token", "award_presents_popup", MODAL)
        verdict = popup_probe.classify_award_presents([record])
        self.assertEqual(REFUTED, verdict.verdict)


class AwardNonblockingVerdictTests(unittest.TestCase):
    def test_deferred_and_input_free_supports_it(self):
        record = _record("award-while-menu-open", "award_nonblocking", DEFERRED, nonblocking="y")
        verdict = popup_probe.classify_award_nonblocking([record])
        self.assertEqual(SUPPORTED, verdict.verdict)

    def test_modal_refutes_it(self):
        record = _record("award-while-menu-open", "award_nonblocking", MODAL, nonblocking="y")
        verdict = popup_probe.classify_award_nonblocking([record])
        self.assertEqual(REFUTED, verdict.verdict)

    def test_input_captured_refutes_it_even_with_a_popup(self):
        record = _record("award-while-menu-open", "award_nonblocking", POPUP, nonblocking="n")
        verdict = popup_probe.classify_award_nonblocking([record])
        self.assertEqual(REFUTED, verdict.verdict)


class AwardPersistsVerdictTests(unittest.TestCase):
    def test_present_after_reload_supports_it(self):
        record = _record("award-after-reload", "award_persists", UNKNOWN, persisted="y")
        verdict = popup_probe.classify_award_persists([record])
        self.assertEqual(SUPPORTED, verdict.verdict)

    def test_absent_after_reload_refutes_it(self):
        record = _record("award-after-reload", "award_persists", UNKNOWN, persisted="n")
        verdict = popup_probe.classify_award_persists([record])
        self.assertEqual(REFUTED, verdict.verdict)

    def test_not_run_is_unclear(self):
        verdict = popup_probe.classify_award_persists([])
        self.assertEqual(UNCLEAR, verdict.verdict)


class SummaryRenderingTests(unittest.TestCase):
    def test_a_failed_control_is_called_out_in_the_summary(self):
        text = popup_probe.render_summary([CONTROL_FAILED])
        self.assertIn("PROBE_DEFECT", text.upper())
        self.assertIn("FAILED", text)

    def test_marks_are_merged_into_the_summary(self):
        text = popup_probe.render_summary(
            [CONTROL_OK], marks=[{"at": "2026-09-06T00:00:00+00:00", "label": "control"}]
        )
        self.assertIn("control", text)
        self.assertIn("Console marks", text)


class PopupCliTests(unittest.TestCase):
    def _run(self, argv):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = cli.build_parser().parse_args(argv).func(
                cli.build_parser().parse_args(argv))
        return code, buffer.getvalue()

    def test_the_runbook_needs_no_pid_and_touches_no_process(self):
        code, output = self._run(["probe-popup", "--runbook"])
        self.assertEqual(0, code)
        self.assertIn("control-vanilla-pickup", output)

    def test_a_run_without_a_save_id_is_refused_before_anything_attaches(self):
        code, output = self._run(["probe-popup", "--pid", "1"])
        self.assertEqual(1, code)
        self.assertIn("--save-id", output)

    def test_arming_without_asserting_a_throwaway_save_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._run([
                "probe-popup", "--pid", "1", "--save-id", "s", "--arm",
                "--journal", str(Path(directory) / "j.json"),
                "--report", str(Path(directory) / "r.jsonl"),
            ])
        self.assertEqual(1, code)
        self.assertIn("--yes-throwaway-save", output)

    def test_a_dry_run_rehearses_the_steps_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Path(directory) / "j.json"
            report = Path(directory) / "r.jsonl"
            code, output = self._run([
                "probe-popup", "--pid", "1", "--save-id", "s",
                "--journal", str(journal), "--report", str(report),
            ])
            self.assertEqual(0, code)
            self.assertIn("award-rune-token", output)
            self.assertIn("Dry run", output)
            self.assertFalse(journal.exists())
            self.assertFalse(report.exists())

    def test_an_unknown_step_id_is_refused(self):
        code, output = self._run([
            "probe-popup", "--pid", "1", "--save-id", "s", "--only", "nope",
        ])
        self.assertEqual(1, code)
        self.assertIn("nope", output)

    def test_a_summary_of_an_empty_report_is_a_red_not_an_empty_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            code, output = self._run([
                "probe-popup", "--summary", "--report", str(Path(directory) / "none.jsonl"),
                "--marks", str(Path(directory) / "none-marks.jsonl"),
            ])
        self.assertEqual(1, code)
        self.assertIn("Nothing to summarise", output)

    def test_a_summary_renders_the_recorded_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "r.jsonl"
            popup_probe.append_record(report, CONTROL_OK)
            code, output = self._run([
                "probe-popup", "--summary", "--report", str(report),
                "--marks", str(Path(directory) / "none-marks.jsonl"),
            ])
        self.assertEqual(0, code)
        self.assertIn("issue #330", output)
        self.assertIn("SUPPORTED", output)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
