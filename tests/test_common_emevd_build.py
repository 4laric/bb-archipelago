"""The category-8 common.emevd round-trip check must tolerate compiler-dropped comments."""

import unittest

from tools.build_cathedral_emevd import event
from tools.build_common_emevd import instructions, verify_owned_events
from tools.patch_category8_awards import CATEGORY8_AWARDS, EVENT_ID, patch


VANILLA = "$Event(0, Default, function() {\n    $InitializeEvent(0, 1, 2);\n});\n"


class CommonEmevdRoundTripTest(unittest.TestCase):
    def test_patched_event_matches_its_comment_free_decompile(self):
        patched = patch(VANILLA.encode("utf-8-sig")).decode("utf-8-sig")
        expected = event(patched, str(EVENT_ID))
        self.assertIn("//", expected, "the fixture must carry a comment to be meaningful")
        # What DarkScript3 hands back: same instructions, no comments.
        decompiled = "\n".join(
            line for line in expected.splitlines() if not line.strip().startswith("//")
        )
        self.assertNotEqual(expected.rstrip(), decompiled.rstrip())
        self.assertEqual(instructions(expected), instructions(decompiled))

    def test_an_instruction_difference_is_still_detected(self):
        patched = patch(VANILLA.encode("utf-8-sig")).decode("utf-8-sig")
        expected = event(patched, str(EVENT_ID))
        mutated = expected.replace("AwardItemLot(itemLotId);", "AwardItemLot(0);")
        self.assertNotEqual(instructions(expected), instructions(mutated))

    def test_each_award_uses_an_isolated_event(self):
        patched = patch(VANILLA.encode("utf-8-sig")).decode("utf-8-sig")
        self.assertEqual(patched.count("$Event("), len(CATEGORY8_AWARDS) + 1)
        for index, row in enumerate(CATEGORY8_AWARDS):
            initializer = (
                f"$InitializeEvent(0, {EVENT_ID + index}, {row.token_goods_id}, "
                f"{row.item_lot_id}, {row.ack_flag});"
            )
            self.assertIn(initializer, patched)
            self.assertIn(f"$Event({EVENT_ID + index}, Restart", patched)

    def test_verifier_checks_nonpilot_event_body(self):
        patched = patch(VANILLA.encode()).decode('utf-8-sig')
        verify_owned_events(patched, patched)
        row15 = event(patched, str(EVENT_ID + 15))
        broken = patched.replace(row15, row15.replace('AwardItemLot(itemLotId)', 'AwardItemLot(0)'))
        with self.assertRaisesRegex(ValueError, '98000015'):
            verify_owned_events(patched, broken)


if __name__ == "__main__":
    unittest.main()
