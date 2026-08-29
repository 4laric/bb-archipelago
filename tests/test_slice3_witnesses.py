"""What the corpus can and cannot say about the slice-3 detection flags.

Issue #158. These are not witnesses -- a witness needs the game. They are the
half of the question the repository can answer, held so that it stops being
re-derived by hand: which slice-3 flag claims are complete from named sources,
which have a hole, and that the hole does not quietly widen.

Every assertion here names its population. `docs/EVENT-FLAG-RESEARCH.md`'s
requirements are universally quantified ("no flag is cleared", "no two checks
share one flag"), and a universal that ran over an empty set is not evidence,
so each of those tests asserts the size of the set it examined as well as the
property.
"""

from __future__ import annotations

import csv
import json
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.audit_slice3_witnesses import (  # noqa: E402
    AUDIT_JSON, AUDIT_TSV, FIELDS, SCRIPTED, SLICE3_REGIONS, load_events, off_ranges, render,
    audit,
)
from tools.bb_inputs import read_blob  # noqa: E402
from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS  # noqa: E402
from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS  # noqa: E402

BUNDLE = REPO / "research" / "bb_inputs.db"


def audited_rows() -> list[dict[str, str]]:
    with AUDIT_TSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class CommittedAuditTests(unittest.TestCase):
    def test_audit_matches_the_corpus_it_claims_to_read(self):
        rows, summary = audit()
        self.assertEqual(AUDIT_TSV.read_text(encoding="utf-8"), render(rows))
        self.assertEqual(
            json.loads(AUDIT_JSON.read_text(encoding="utf-8")), summary,
            "research/validation/slice3_witness_audit.tsv is stale; "
            "rerun tools/audit_slice3_witnesses.py")

    def test_audit_covers_every_slice3_detection_flag(self):
        rows = audited_rows()
        self.assertEqual(set(FIELDS), set(rows[0]))
        pickups = {row["flag"] for row in rows if row["kind"] == "pickup"}
        expected = {str(loc.event_flag) for loc in FIXED_LOCATIONS
                    if loc.region in SLICE3_REGIONS}
        self.assertEqual(expected, pickups)
        self.assertEqual(115, len(pickups), "slice 3 seeds 115 pickups in the two new regions")
        scripted = {row["key"] for row in rows if row["kind"] == "scripted"}
        self.assertEqual({key for key, *_ in SCRIPTED}, scripted)

    def test_nothing_in_the_audit_claims_a_live_observation(self):
        rows = audited_rows()
        self.assertEqual({"inferred"}, {row["evidence_label"] for row in rows})
        self.assertEqual(0, json.loads(AUDIT_JSON.read_text(encoding="utf-8"))["observed_live"])


class MonotonicityTests(unittest.TestCase):
    """`EVENT-FLAG-RESEARCH.md` requires a signal that does not clear in play."""

    def test_no_off_write_reaches_a_slice3_flag(self):
        events = load_events()
        ranges = off_ranges(events)
        unresolved = [r for r in ranges if r[2] == "unresolved"]
        self.assertEqual(
            (279, 0), (len(ranges), len(unresolved)),
            "an OFF range whose bounds could not be resolved is a hole, not a pass: "
            f"{unresolved}")
        rows = audited_rows()
        offending = [(row["key"], row["off_writers"]) for row in rows if row["off_writers"]]
        self.assertEqual((121, 0), (len(rows), len(offending)), f"cleared: {offending}")

    def test_the_resolver_can_actually_find_a_clearing_range(self):
        """A negative result is only worth something if a positive is reachable.

        `BatchSetEventFlags(1320, 1325, OFF)` really is in m23_00_00_00, so the
        same code path that reports "no slice-3 flag is cleared" does report a
        flag inside a cleared range.
        """
        from tools.audit_slice3_witnesses import flag_reaches
        ranges = off_ranges(load_events())
        self.assertNotEqual([], flag_reaches(1322, ranges))
        self.assertEqual(0, len(flag_reaches(12301800, ranges)))


class FlagSpecificityTests(unittest.TestCase):
    def test_each_slice3_pickup_flag_has_exactly_one_placed_lot(self):
        rows = [row for row in audited_rows() if row["kind"] == "pickup"]
        wrong = [row["key"] for row in rows if len(row["placed_lots"].split(";")) != 1]
        self.assertEqual((115, 0), (len(rows), len(wrong)),
                         f"not exactly one placed lot: {wrong}")
        shared = [row for row in rows if row["corroboration"]]
        self.assertEqual(
            5, len(shared),
            "five slice-3 flags sit on more than one ItemLotParam row; each keeps "
            "one MSB placement, so they are one check apiece, not two")


class SourceCitationTests(unittest.TestCase):
    def test_every_scripted_binding_cites_its_own_event_definition(self):
        """A citation that lands on a *reader* of the flag is not its source.

        `boss_cleric_beast` cited m24_01_00_00:1047 -- a `WaitFor(EventFlag(...))`
        inside event 12411899 -- rather than 1052, where 12411700 is defined.
        """
        checked = 0
        for key, binding in LOCATION_BINDINGS.items():
            if binding.source_kind not in ("boss_defeat", "interaction"):
                continue
            name, _, span = binding.source_ref.partition(":")
            text = read_blob(BUNDLE, f"event/{name}").decode("utf-8", "replace").splitlines()
            first = int(span.split("-")[0])
            self.assertTrue(
                text[first - 1].startswith(f"$Event({binding.event_flag},"),
                f"{key}: {binding.source_ref} is not the definition of "
                f"{binding.event_flag}; that line reads {text[first - 1]!r}")
            checked += 1
        self.assertEqual(18, checked, "every boss and interaction binding must be checked")

    def test_slice3_boss_bindings_say_their_write_is_not_cited(self):
        """The gap has to be visible where a reader will be, not only in a doc."""
        for key in ("boss_blood_starved_beast", "boss_vicar_amelia",
                    "interaction_laurences_skull"):
            self.assertIn("`inferred`", LOCATION_BINDINGS[key].evidence, key)

    def test_no_emevd_instruction_writes_a_scripted_slice3_flag(self):
        """The claim the owner checklist exists to close.

        If some map did set 12301800 explicitly, the flag would be corpus-
        complete and the live pass could be narrowed. Nothing does, so it is not.
        """
        events = load_events()
        population = sum(len(lines) for lines in events.values())
        self.assertGreater(population, 40000)
        for flag in (12301800, 12401800, 12401803, 12411700, 12411800):
            sites = [f"{name}:{index}"
                     for name, lines in events.items()
                     for index, line in enumerate(lines, 1)
                     if re.search(rf"SetEventFlag\(\s*{flag}\s*,", line.split("//", 1)[0])]
            self.assertEqual(0, len(sites), f"{flag} is written after all: {sites}")
        # and the same scan does find a real SetEventFlag, so it is not vacuous
        hits = [name for name, lines in events.items()
                if any(re.search(r"SetEventFlag\(\s*12401802\s*,", line) for line in lines)]
        self.assertEqual(["m24_00_00_00.emevd.dcx.js"], hits)


if __name__ == "__main__":
    unittest.main()
