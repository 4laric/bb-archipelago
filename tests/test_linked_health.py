"""Regression census for live referred-health bodies in transplanted encounters."""
import unittest
from pathlib import Path
from functools import cache
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.encounter_recipes import reusable_recipes
from tools.bb_enemizer.ludwig_orphan_contract import patch_ludwig_at_orphan
from tools.bb_enemizer.ludwig_shadows_contract import patch_ludwig_at_shadows
import re

@cache
def source(name):
    return read_blob(Path(__file__).resolve().parents[1] / "research/bb_inputs.db",
                     "event/" + name).decode("utf-8-sig")

class LinkedHealthTests(unittest.TestCase):
    def test_fourteen_routes_keep_linked_body_loaded_and_phase_transition_intact(self):
        routes = [(a, d, r.arena.event_file, r.donor.event_file, r.patch)
                  for (a, d), r in reusable_recipes().items()
                  if d in ("orphan-of-kos", "ludwig")]
        routes += [("orphan-of-kos", "ludwig", "m36_00_00_00.emevd.dcx.js",
                    "m34_00_00_00.emevd.dcx.js", patch_ludwig_at_orphan),
                   ("shadows-of-yharnam", "ludwig", "m27_00_00_00.emevd.dcx.js",
                    "m34_00_00_00.emevd.dcx.js", patch_ludwig_at_shadows)]
        self.assertEqual(14, len(routes))
        for arena, donor, dest, donorfile, patch in routes:
            with self.subTest(arena=arena, donor=donor):
                result = patch(source(dest), source(donorfile))
                healths = [b for b in event_blocks(result).values()
                           if "CreateReferredDamagePair(" in b and "DisplayBossHealthBar(" in b]
                # A shared map can retain another unrelated boss; select the
                # health body which the adapter explicitly keeps loaded.
                healths = [b for b in healths if "SetCharacterDefaultBackreadState(" in b]
                self.assertEqual(1, len(healths))
                health = healths[0]
                core, phase = re.search(r"CreateReferredDamagePair\((\d+), (\d+)\)", health).groups()
                self.assertIn(f"ChangeCharacterEnableState({phase}, Enabled);", health)
                self.assertNotIn(f"ChangeCharacterEnableState({phase}, Disabled);", health)
                self.assertIn(f"SetCharacterAIState({phase}, Disabled);", health)
                self.assertLess(health.index(f"WaitFor(CharacterBackreadStatus({phase}));"),
                                health.index("CreateReferredDamagePair("))
                self.assertIn(f"SetCharacterGravity({phase}, Disabled);", health)
                self.assertLess(health.index(f"SetCharacterGravity({phase}, Disabled);"),
                                health.index("CreateReferredDamagePair("))
                self.assertIn(f"SetCharacterGravity({phase}, Enabled);", result)
                self.assertIn(f"WarpCharacterAndCopyFloor({phase},", result)
                self.assertIn(f"SetCharacterAIState({phase}, Enabled);", result)
