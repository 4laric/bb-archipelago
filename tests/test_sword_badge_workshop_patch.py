from __future__ import annotations

import unittest

from tests.test_laurence_skull_patch import bundled_source
from tools.patch_sword_badge_workshop import EVENT, NEW, OLD, event_body, patch


class SwordBadgeWorkshopPatchTests(unittest.TestCase):
    def test_only_the_workshop_door_guard_changes(self):
        source = bundled_source()
        output = patch(source)
        before = source.decode("utf-8-sig")
        after = output.decode("utf-8")
        self.assertIn(OLD, event_body(before))
        self.assertNotIn(OLD, event_body(after))
        self.assertIn(NEW, event_body(after))
        start = before.index(f"$Event({EVENT},")
        position = before.index(OLD, start)
        self.assertEqual(before[:position] + NEW + before[position + len(OLD):], after)

    def test_refuses_a_changed_supported_shape(self):
        source = bundled_source().decode("utf-8-sig")
        start = source.index(f"$Event({EVENT},")
        position = source.index(OLD, start)
        changed = (source[:position] + "    if (EventFlag(9999)) {"
                   + source[position + len(OLD):]).encode()
        with self.assertRaisesRegex(ValueError, EVENT):
            patch(changed, verify_source=False)


if __name__ == "__main__":
    unittest.main()
