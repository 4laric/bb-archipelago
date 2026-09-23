import hashlib
import unittest
from collections import Counter
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import AMELIA_ARENA
from tools.bb_enemizer.boss_entrances import (
    ENTRANCE_POLICIES,
    skip_replacement_entrance,
)
from tools.bb_enemizer.laurence_donor import patch_laurence_donor
from tools.bb_enemizer.maria_contract import MARIA_EVENT_FILE
from tools.bb_enemizer.maria_donor import patch_maria_donor
from tools.bb_enemizer.maria_donor import MariaArenaAllocation


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


def source(policy):
    return read_blob(BUNDLE, "event/" + policy.event_file).decode("utf-8-sig")


class BossEntranceTests(unittest.TestCase):
    def test_census_pins_all_22_activation_events_and_12_cinematics(self):
        self.assertEqual(22, len(ENTRANCE_POLICIES))
        cinematic = {
            key for key, policy in ENTRANCE_POLICIES.items() if policy.has_cinematic
        }
        self.assertEqual(
            {
                "vicar-amelia", "lady-maria", "laurence", "ludwig",
                "orphan-of-kos", "martyr-logarius", "father-gascoigne",
                "mergos-wet-nurse", "micolash", "the-one-reborn",
                "gehrman", "moon-presence",
            },
            cinematic,
        )
        self.assertEqual(
            {"lady-maria", "laurence", "gehrman", "moon-presence"},
            {
                key for key, policy in ENTRANCE_POLICIES.items()
                if policy.relocation_regions
            },
        )
        for key, policy in ENTRANCE_POLICIES.items():
            with self.subTest(arena=key):
                blocks = event_blocks(source(policy))
                body = blocks[policy.event_id]
                self.assertEqual(
                    policy.source_sha256,
                    hashlib.sha256(body.encode("utf-8")).hexdigest(),
                )
                calls = [
                    line.strip() for line in body.splitlines()
                    if "PlayCutscene" in line
                ]
                expected = [
                    edit.instruction
                    for edit in policy.edits
                    for _ in range(edit.count)
                ]
                self.assertEqual(sorted(expected), sorted(calls))

    def test_policy_changes_only_exact_entrance_instructions_one_for_one(self):
        for key, policy in ENTRANCE_POLICIES.items():
            with self.subTest(arena=key):
                original = source(policy)
                before = event_blocks(original)
                result = skip_replacement_entrance(key, original, original)
                after = event_blocks(result)
                self.assertEqual(set(before), set(after))
                for event_id, block in before.items():
                    if event_id != policy.event_id:
                        self.assertEqual(block, after[event_id])
                expected = before[policy.event_id]
                for edit in policy.edits:
                    expected = expected.replace(edit.instruction, edit.replacement)
                self.assertEqual(expected, after[policy.event_id])
                self.assertNotIn("PlayCutscene", after[policy.event_id])
                if not policy.has_cinematic:
                    self.assertEqual(original, result)
                # Replacing one instruction with one instruction keeps relative
                # EMEVD SkipIf/label instruction counts stable.
                replacements = Counter()
                for edit in policy.edits:
                    replacements[edit.replacement] += edit.count
                for replacement, count in replacements.items():
                    self.assertEqual(
                        count,
                        after[policy.event_id].count(replacement)
                        - before[policy.event_id].count(replacement),
                    )
                self.assertEqual(
                    result,
                    skip_replacement_entrance(key, original, result),
                )

    def test_inferred_short_warps_use_original_msb_areas_and_record_runtime_gap(self):
        region_rows = read_blob(BUNDLE, "mined/msb_regions.tsv").decode(
            "utf-8-sig"
        ).splitlines()
        regions = {
            int(columns[3]): (columns[1], columns[4])
            for columns in (line.split("\t") for line in region_rows[1:])
            if len(columns) > 4 and columns[3]
        }
        for key in ("lady-maria", "laurence", "gehrman", "moon-presence"):
            with self.subTest(arena=key):
                policy = ENTRANCE_POLICIES[key]
                self.assertEqual(
                    "source-composed; runtime-unproven", policy.relocation_evidence
                )
                result = skip_replacement_entrance(key, source(policy), source(policy))
                activation = event_blocks(result)[policy.event_id]
                expected_map = policy.event_file[:12]
                for region in policy.relocation_regions:
                    self.assertEqual((expected_map, "Box"), regions[region])
                    self.assertIn(
                        "IssueShortWarpRequest(10000, TargetEntityType.Area, "
                        f"{region}, -1);",
                        activation,
                    )
        laurence = event_blocks(skip_replacement_entrance(
            "laurence",
            source(ENTRANCE_POLICIES["laurence"]),
            source(ENTRANCE_POLICIES["laurence"]),
        ))[13401851]
        self.assertEqual(2, laurence.count(
            "IssueShortWarpRequest(10000, TargetEntityType.Area, 3402856, -1);"
        ))
        self.assertIn(
            "} else {\n            WaitFixedTimeFrames(1);\n        }",
            laurence,
        )

    def test_combat_phase_and_post_defeat_cinematics_remain_byte_identical(self):
        excluded = {
            "vicar-amelia": (12401803,),
            "micolash": (12601854,),
            "rom": (13201803,),
            "ludwig": (13401800, 13404825),
            "orphan-of-kos": (13601803,),
        }
        for key, event_ids in excluded.items():
            with self.subTest(arena=key):
                policy = ENTRANCE_POLICIES[key]
                before = event_blocks(source(policy))
                after = event_blocks(skip_replacement_entrance(
                    key, source(policy), source(policy)
                ))
                for event_id in event_ids:
                    self.assertIn("PlayCutscene", before[event_id])
                    self.assertEqual(before[event_id], after[event_id])

    def test_runs_after_maria_and_laurence_amelia_adapters(self):
        original = source(ENTRANCE_POLICIES["vicar-amelia"])
        donors = (
            patch_maria_donor(
                AMELIA_ARENA,
                original,
                read_blob(BUNDLE, "event/" + MARIA_EVENT_FILE).decode("utf-8-sig"),
                MariaArenaAllocation(12994700, 12994701),
            ),
            patch_laurence_donor(
                AMELIA_ARENA,
                original,
                read_blob(
                    BUNDLE, "event/m34_00_00_00.emevd.dcx.js"
                ).decode("utf-8-sig"),
            ),
        )
        for patched in donors:
            with self.subTest(donor="maria" if "3500800" in patched else "laurence"):
                before = event_blocks(patched)
                result = skip_replacement_entrance(
                    "vicar-amelia", original, patched
                )
                after = event_blocks(result)
                self.assertNotIn("PlayCutscene", after[12401802])
                self.assertIn("IssueBossRoomEntryNotification(0)", after[12401802])
                self.assertIn("SetEventFlag(12404800, ON)", after[12401802])
                self.assertEqual(before[12401800], after[12401800])

    def test_rejects_unpinned_originals_and_partial_adapter_edits(self):
        policy = ENTRANCE_POLICIES["vicar-amelia"]
        original = source(policy)
        with self.assertRaisesRegex(ValueError, "unsupported original"):
            skip_replacement_entrance(
                "vicar-amelia", original.replace("SetEventFlag(9301, ON)",
                                                  "SetEventFlag(9302, ON)"),
                original,
            )
        partial = original.replace(policy.edits[0].instruction,
                                   policy.edits[0].replacement)
        with self.assertRaisesRegex(ValueError, "partially changed"):
            skip_replacement_entrance("vicar-amelia", original, partial)
        laurence_policy = ENTRANCE_POLICIES["laurence"]
        laurence_original = source(laurence_policy)
        adapted = skip_replacement_entrance(
            "laurence", laurence_original, laurence_original
        )
        short_warp = (
            "IssueShortWarpRequest(10000, TargetEntityType.Area, 3402856, -1);"
        )
        self.assertEqual(2, adapted.count(short_warp))
        with self.assertRaisesRegex(ValueError, "removed required player relocation"):
            skip_replacement_entrance(
                "laurence", laurence_original, adapted.replace(short_warp, "", 1)
            )
        with self.assertRaisesRegex(ValueError, "no entrance policy"):
            skip_replacement_entrance("unknown", original, original)


if __name__ == "__main__":
    unittest.main()
