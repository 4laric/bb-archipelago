import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.laurence_ludwig_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LaurenceLudwigIds,
    native_plan_laurence_at_ludwig,
    patch_laurence_at_ludwig,
)
from tools.bb_enemizer.scaling import load_params


class LaurenceLudwigContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )

    def test_preserves_both_terminals_and_all_original_laurence_combat(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_laurence_at_ludwig(self.source, self.source))
        changed = {
            0,
            13404802,
            13404803,
            13404804,
            13404820,
            13404821,
            13404822,
            13404823,
            13404824,
            13404825,
            13404830,
            13404835,
            13404840,
            13404841,
        }
        for event_id, body in before.items():
            if event_id not in changed:
                self.assertEqual(body, after[event_id], event_id)
        for event_id in (
            13401800,
            13401850,
            13404852,
            13404853,
            13404854,
            13404861,
            13404870,
            13404875,
        ):
            self.assertEqual(before[event_id], after[event_id])

    def test_uses_laurence_health_music_camera_and_full_limb_package(self):
        after = event_blocks(patch_laurence_at_ludwig(self.source, self.source))
        health = after[13404802]
        self.assertNotIn("CreateReferredDamagePair", health)
        self.assertNotIn("3400801", health)
        self.assertIn("EndIf(EventFlag(9471));", health)
        self.assertIn("SetSpEffect(3400800, 8040, false);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 3400800, 0, 450000)", health)
        self.assertIn("CharacterHasEventMessage(3400800, 400)", after[13404803])
        self.assertIn("EntityInRadiusOfEntity(10000, 3400800, 14)", after[13404804])
        self.assertIn("SetLockcamSlotNumber(34, 0, 1)", after[13404804])
        self.assertIn("CreateNPCPart(3400800", after[DEFAULT_IDS.limbs])
        self.assertIn("EndIf(EventFlag(13401800));", after[DEFAULT_IDS.limbs])
        self.assertIn(
            "ChangeCharacterHitmask(3400800, 10, ON)", after[DEFAULT_IDS.hitmask]
        )
        self.assertEqual(5, after[0].count(str(DEFAULT_IDS.limbs)))
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.hitmask)))
        self.assertEqual(1, after[0].count(str(DEFAULT_IDS.phase_two_cleanup)))
        for event_id in (
            13404820,
            13404821,
            13404822,
            13404823,
            13404824,
            13404825,
            13404830,
            13404835,
            13404840,
            13404841,
        ):
            self.assertIn("EndEvent();", after[event_id])

    def test_disables_phase_two_without_premature_kill(self):
        after = event_blocks(patch_laurence_at_ludwig(self.source, self.source))
        cleanup = after[DEFAULT_IDS.phase_two_cleanup]
        self.assertIn("ChangeCharacterEnableState(3400801, Disabled);", cleanup)
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(13401800));"),
            cleanup.index("ForceCharacterDeath(3400801, false);"),
        )
        self.assertNotIn(
            "ForceCharacterDeath(3400801",
            "\n".join(
                after[event_id]
                for event_id in (
                    0,
                    13404802,
                    13404820,
                    13404821,
                    13404822,
                    13404823,
                    13404824,
                    13404825,
                )
            ),
        )

    def test_rejects_project_id_collision_and_pins_source(self):
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_laurence_at_ludwig(
                self.source,
                self.source,
                LaurenceLudwigIds(13404870, 12991275, 12991276),
            )
        with self.assertRaisesRegex(
            ValueError, "unsupported original Laurence donor event 13404870"
        ):
            patch_laurence_at_ludwig(
                self.source,
                self.source.replace(
                    "SetNPCPartSEAndSFX(3400850, npcPartId2, 64, 64)",
                    "SetNPCPartSEAndSFX(3400850, npcPartId2, 1, 1)",
                ),
            )

    def test_native_plan_binds_true_laurence_part(self):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "enemies.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(inventory)
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_laurence_at_ludwig(slots, npcs, effects, "laurence-ludwig")
        self.assertEqual("c4500", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m34_00_00_00", binding["source_map"])
        self.assertEqual("c4500_0000", binding["source_part"])
        self.assertEqual("m34_00_00_00", binding["destination_map"])
        self.assertTrue(plan["scaling"]["enabled"])


if __name__ == "__main__":
    unittest.main()
