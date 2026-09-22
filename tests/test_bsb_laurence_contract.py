import tempfile, unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_laurence_contract import (
    BUNDLE,
    DEFAULT_IDS,
    BsbLaurenceIds,
    patch_bsb_at_laurence,
    native_plan_bsb_at_laurence,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbLaurenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(c):
        c.a = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        c.d = read_blob(BUNDLE, "event/m23_00_00_00.emevd.dcx.js").decode("utf-8-sig")

    def test_preserves_shared_progression_and_laurence_entry(self):
        b = event_blocks(self.a)
        x = event_blocks(patch_bsb_at_laurence(self.a, self.d))
        self.assertEqual(b[13401800], x[13401800])
        self.assertEqual(b[13401850], x[13401850])
        self.assertIn("PlayerHasItem(ItemType.Goods, 4014)", x[13401851])
        self.assertIn("PlayCutsceneAndWarpPlayer(34000010", x[13401851])
        self.assertIn("ForceAnimationPlayback(3400850, 7001", x[13401851])
        self.assertNotIn("7002", x[13404861])

    def test_maps_bsb_health_phase_poison_ai_and_camera(self):
        x = event_blocks(patch_bsb_at_laurence(self.a, self.d))
        self.assertIn("DisplayBossHealthBar(Enabled, 3400850, 0, 209000)", x[13404852])
        self.assertIn("EventFlag(12990801)", x[13404853])
        self.assertIn(
            "RequestCharacterAICommand(3400850, 100, 0)", x[DEFAULT_IDS.phase_one]
        )
        self.assertIn("EventFlag(12990800)", x[DEFAULT_IDS.phase_two])
        self.assertIn("SetLockcamSlotNumber(34, 0, 1)", x[DEFAULT_IDS.camera])
        self.assertEqual(1, x[0].count("12990800"))
        self.assertEqual(1, x[0].count("12990801"))
        self.assertEqual(1, x[0].count("12990802"))
        self.assertIn("EndEvent();", x[13404870])

    def test_preserves_all_shared_ludwig_combat(self):
        before = event_blocks(self.a)
        after = event_blocks(patch_bsb_at_laurence(self.a, self.d))
        for event_id in range(13404820, 13404826):
            self.assertEqual(before[event_id], after[event_id])

    def test_rejects_colliding_project_id(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_bsb_at_laurence(
                self.a, self.d, BsbLaurenceIds(13404824, 12990801, 12990802)
            )

    def test_native_plan_uses_true_bsb_part_and_ai_source(self):
        with tempfile.TemporaryDirectory() as q:
            p = Path(q) / "i"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(p)
        n, e = load_params(BUNDLE)
        plan = native_plan_bsb_at_laurence(slots, n, e, "bsb-laurence")
        self.assertEqual("c2090", plan["swaps"][0]["target"]["model_name"])
        b = plan["primary_init_source_bindings"][0]
        self.assertEqual("c2090_0003", b["source_part"])
        self.assertEqual("m23_00_00_00", b["source_map"])
        self.assertTrue(plan["scaling"]["enabled"])


if __name__ == "__main__":
    unittest.main()
