from __future__ import annotations

import unittest

from tests.test_laurence_skull_patch import bundled_source
from tools.build_cathedral_emevd import (
    DARKSCRIPT_SHA256,
    DARKSCRIPT_VERSION,
    OUTPUT_RELATIVE_PATH,
    event,
    unrelated_events,
)
from tools.patch_emblem_chokepoint import NEW as EMBLEM_NEW, patch as patch_emblem
from tools.patch_laurence_skull import patch as patch_laurence
from tools.patch_sword_badge_workshop import NEW as WORKSHOP_NEW, patch as patch_workshop


class CathedralEmevdBuildTests(unittest.TestCase):
    def test_owned_transforms_compose_from_one_pinned_source(self):
        source = bundled_source()
        patched = patch_workshop(
            patch_laurence(patch_emblem(source), verify_source=False), verify_source=False
        )
        text = patched.decode("utf-8")
        self.assertIn(EMBLEM_NEW, event(text, "12400760"))
        skull = event(text, "12401803")
        self.assertIn("SetEventFlag(12401898, ON);", skull)
        self.assertNotIn("EndIf(ThisEvent());", skull)
        self.assertIn("WaitFor(!EventFlag(12401898));", skull)
        self.assertIn("WaitFor(!HasMultiplayerState(MultiplayerState.Client));", skull)
        self.assertEqual(
            unrelated_events(source.decode("utf-8-sig")), unrelated_events(text)
        )
        self.assertIn(WORKSHOP_NEW, event(text, "12405710"))

    def test_compiler_and_overlay_contract_are_pinned(self):
        self.assertEqual(DARKSCRIPT_VERSION, "3.6.3")
        self.assertEqual(len(DARKSCRIPT_SHA256), 64)
        self.assertEqual(
            OUTPUT_RELATIVE_PATH,
            "dvdroot_ps4/event/m24_00_00_00.emevd.dcx",
        )


if __name__ == "__main__":
    unittest.main()
