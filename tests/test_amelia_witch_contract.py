import tempfile, unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.amelia_witch_contract import *


class AmeliaWitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.a = read_blob(BUNDLE, AMELIA_SOURCE).decode("utf-8-sig")
        c.w = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            c.slots = load_slots(p)
        c.npcs, c.effects = load_params(BUNDLE)

    def test_terminal_pair_and_progression_remain_destination_owned(self):
        b = event_blocks(self.w)
        o = event_blocks(patch_amelia_at_witch(self.w, self.a))
        self.assertEqual(b[12201800], o[12201800])
        self.assertIn("CharacterDead(2200800) && CharacterDead(2200801)", o[12201800])
        self.assertIn("HandleBossDefeat(2200800)", o[12201800])
        bridge = o[DEFAULT_IDS.bridge]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2200800));"),
            bridge.index("ForceCharacterDeath(2200801, false);"),
        )

    def test_amelia_activation_is_source_witnessed_and_independent_of_insight(self):
        source = event_blocks(self.a)[12401802]
        target = event_blocks(patch_amelia_at_witch(self.w, self.a))[12201802]
        self.assertNotIn("PlayerInsightAmount", target)
        self.assertNotIn("3011", target)
        for animation in (7000, 7001):
            self.assertIn(
                f"ForceAnimationPlayback(2400800, {animation}, false, false, false);",
                source,
            )
            self.assertIn(
                f"ForceAnimationPlayback(2200800, {animation}, false, false, false);",
                target,
            )
        self.assertLess(
            target.index("InArea(10000, 2202805)"),
            target.index("ForceAnimationPlayback"),
        )

    def test_full_amelia_combat_closure_and_witch_retirement(self):
        o = event_blocks(patch_amelia_at_witch(self.w, self.a))
        self.assertIn("DisplayBossHealthBar(Enabled, 2200800, 0, 502000)", o[12204802])
        self.assertIn("CreateNPCPart(2200800", o[DEFAULT_IDS.limbs])
        self.assertIn("CharacterHasSpEffect(2200800, 2150)", o[DEFAULT_IDS.heal])
        self.assertIn("SetLockcamSlotNumber(22, 0, 1)", o[12204804])
        self.assertIn("CharacterHasEventMessage(2200800, 100)", o[12204803])
        retire = o[DEFAULT_IDS.retire]
        self.assertIn("DeactivateGenerator(2205002, Disabled)", retire)
        self.assertIn("ChangeCharacterEnableState(2200812, Disabled)", retire)
        for e in (
            12204807,
            12204808,
            12204810,
            12204811,
            12204812,
            12204814,
            12204820,
            12204830,
            12204832,
            12204835,
            12204838,
            12204839,
            12204840,
            12204841,
            12204842,
            12204843,
        ):
            self.assertEqual("    EndEvent();", o[e].splitlines()[1])

    def test_plan_has_exact_primary_and_retained_terminal_second(self):
        p = native_plan_amelia_at_witch(
            self.slots, self.npcs, self.effects, "amelia-witch"
        )
        self.assertEqual(1, p["swap_count"])
        self.assertEqual("c5020", p["swaps"][0]["target"]["model_name"])
        h = p["boss_contract"]["retained_destination_helpers"][0]
        self.assertEqual(2200801, h["entity_id"])
        self.assertEqual("m22_00_00_00", h["map"])
        self.assertEqual("unobserved", p["boss_contract"]["runtime_status"])

    def test_collisions_and_source_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129928xx"):
            patch_amelia_at_witch(
                self.w, self.a, replace(DEFAULT_IDS, cloth=DEFAULT_IDS.phase_one)
            )
        with self.assertRaisesRegex(ValueError, "Amelia donor"):
            patch_amelia_at_witch(
                self.w, self.a.replace("CreateNPCPart(2400800", "CreateNPCPart(7")
            )


if __name__ == "__main__":
    unittest.main()
