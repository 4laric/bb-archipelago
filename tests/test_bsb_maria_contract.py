import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_maria_contract import (
    BUNDLE,
    DEFAULT_IDS,
    BsbMariaIds,
    native_plan_bsb_at_maria,
    patch_bsb_at_maria,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbMariaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(BUNDLE, "event/m35_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        cls.bsb = read_blob(BUNDLE, "event/m23_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )

    def test_preserves_maria_progression_cutscene_and_all_unrelated_m35_events(self):
        before = event_blocks(self.maria)
        after = event_blocks(patch_bsb_at_maria(self.maria, self.bsb))
        changed = {0, 13504802, 13504803, 13504804, 13504822}
        for event_id, body in before.items():
            if event_id not in changed:
                self.assertEqual(body, after[event_id], event_id)
        self.assertEqual(before[13501800], after[13501800])
        self.assertEqual(before[13501801], after[13501801])
        self.assertEqual(before[13501807], after[13501807])
        self.assertIn("PlayCutsceneAndWarpPlayer(35000010", after[13501801])
        self.assertIn("ChangeCharacterEnableState(3500800, Enabled);", after[13501807])

    def test_uses_bsb_health_phases_music_and_camera_without_maria_target(self):
        after = event_blocks(patch_bsb_at_maria(self.maria, self.bsb))
        health = after[13504802]
        self.assertIn("DisplayBossHealthBar(Enabled, 3500800, 0, 209000)", health)
        self.assertIn(
            "SetNetworkUpdateAuthority(3500800, AuthorityLevel.Normal)", health
        )
        self.assertIn("AdaptHpchangingSpEffectToNPCPartOfTarget(3500800)", health)
        self.assertNotIn("SetCharacterEventTarget(3500800, 3500801)", health)
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase_one})", after[13504803])
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase_two})", after[13504803])
        self.assertIn(
            "RequestCharacterAICommand(3500800, 100, 0)", after[DEFAULT_IDS.phase_one]
        )
        self.assertIn(
            "RequestCharacterAICommand(3500800, 101, 0)", after[DEFAULT_IDS.phase_two]
        )
        self.assertIn(
            f"EventFlag({DEFAULT_IDS.phase_one})", after[DEFAULT_IDS.phase_two]
        )
        self.assertIn("SetLockcamSlotNumber(35, 0, 1)", after[13504804])
        self.assertIn('EndIf(EventFlag(13501800));', after[13504804])
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.phase_one)))
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.phase_two)))
        self.assertEqual(
            "$Event(13504822, Default, function() {\n    EndEvent();\n});",
            after[13504822],
        )

    def test_rejects_tampered_donor_or_project_id_collision(self):
        with self.assertRaisesRegex(
            ValueError, "unsupported original BSB donor event 12304807"
        ):
            patch_bsb_at_maria(
                self.maria,
                self.bsb.replace("HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.7"),
            )
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_bsb_at_maria(self.maria, self.bsb, BsbMariaIds(13504822, 12991008))

    def test_native_plan_pins_true_bsb_source_and_reports_removed_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "enemies.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(inventory)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_bsb_at_maria(slots, npcs, effects, "bsb-maria")
        self.assertEqual("c2090", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual("c2090_0003", binding["source_part"])
        self.assertEqual("m35_00_00_00", binding["destination_map"])
        removed = plan["boss_contract"]["removed_destination_reference"]
        self.assertEqual(3500801, removed["literal"])
        self.assertTrue(plan["scaling"]["enabled"])


if __name__ == "__main__":
    unittest.main()
