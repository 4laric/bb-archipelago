import tempfile
import unittest
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.bsb_orphan_contract import (
    BUNDLE,
    BSB_SOURCE,
    ORPHAN_SOURCE,
    BsbOrphanIds,
    DEFAULT_IDS,
    native_plan_bsb_at_orphan,
    patch_bsb_at_orphan,
)
from tools.bb_enemizer.scaling import load_params


class BsbOrphanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.bsb = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
        cls.orphan = (
            read_blob(BUNDLE, ORPHAN_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        cls.installed_orphan = (
            cls.orphan.replace(
                "    $InitializeEvent(1, 13605900, 13605951, 13605961, 13605971, 3602910, 3602911, 0);\n"
                "    $InitializeEvent(2, 13605900, 13605952, 13605962, 13605972, 3602920, 0, 0);",
                "    $InitializeEvent(1, 13605900, 13605951, 13605961, 13605971, 3602910, 3602911, 6001);\n"
                "    $InitializeEvent(2, 13605900, 13605952, 13605962, 13605972, 3602920, 0, 6001);",
            )
            .replace(
                "    SetCharacterHPBarDisplay(3600802, Disabled);\n",
                "    SetCharacterHPBarDisplay(3600802, Disabled);\n    SetCharacterGravity(3600802, Disabled);\n",
            )
            .replace(
                "                && EntityInRadiusOfEntity(10000, 3600800, 24));\n",
                "                && (EntityInRadiusOfEntity(10000, 3600800, 24)\n"
                "                    || HasDamageType(3600800, -1, DamageType.Unspecified)));\n",
            )
            .replace(
                "        SetNetworkUpdateRate(3600801, true, CharacterUpdateFrequency.NoUpdate);",
                "        SetNetworkUpdateRate(3600801, true, CharacterUpdateFrequency.AlwaysUpdate);",
            )
        )

    def test_bsb_health_replaces_referred_pair_and_preserves_orphan_terminal_postfight(
        self,
    ):
        before = event_blocks(self.orphan)
        after = event_blocks(patch_bsb_at_orphan(self.orphan, self.bsb))
        health = after[13604802]
        self.assertIn("DisplayBossHealthBar(Enabled, 3600800, 0, 209000)", health)
        self.assertNotIn("CreateReferredDamagePair", health)
        self.assertIn("SetCharacterAIState(3600801, Disabled);", health)
        self.assertIn("SetCharacterAIState(3600803, Disabled);", health)
        self.assertNotIn("ForceCharacterDeath(3600801", health)
        self.assertIn("ChangeCharacterEnableState(3600801, Disabled);", health)
        self.assertIn("ChangeCharacterEnableState(3600803, Disabled);", health)
        self.assertIn("SetEventFlag(13604810, ON);", health)
        for event in (13601800, 13601801, 13601802, 13601803):
            self.assertEqual(before[event], after[event])
        self.assertIn("WaitFor(chr || chr2);", after[13601800])
        self.assertEqual(set(before) | set(DEFAULT_IDS.values()), set(after))

    def test_bsb_phase_camera_music_and_late_helper_cleanup_are_explicit(self):
        after = event_blocks(patch_bsb_at_orphan(self.orphan, self.bsb))
        self.assertIn("HPRatio(3600800) < 0.67", after[12991100])
        self.assertIn("HPRatio(3600800) < 0.33 && EventFlag(12991100)", after[12991101])
        self.assertIn("flagArea2 &= EventFlag(12991101);", after[13604803])
        self.assertIn("SetLockcamSlotNumber(36, 0, 1)", after[13604804])
        self.assertEqual(1, after[0].count("$InitializeEvent(0, 13604804);"))
        cleanup = after[12991102]
        self.assertIn("WaitFor(EventFlag(13601800));", cleanup)
        self.assertIn("ForceCharacterDeath(3600801, false);", cleanup)
        self.assertIn("ForceCharacterDeath(3600803, false);", cleanup)
        for event in (13604820, 13604830, 13604840, 13604850):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])

    def test_cutscene_fog_host_flow_stays_destination_owned(self):
        before = event_blocks(self.orphan)
        after = event_blocks(patch_bsb_at_orphan(self.orphan, self.bsb))
        for event in (13604800, 13604801, 13604805):
            self.assertEqual(before[event], after[event])
        self.assertIn("WaitFor(EventFlag(13604808));", after[13604802])
        self.assertIn("InArea(10000, 3602802)", after[13604803])
        copied = "\n".join(
            after[event] for event in (13604802, 13604803, 13604804, 12991100, 12991101)
        )
        for literal in (
            "2301800",
            "2302800",
            "2302805",
            "2303800",
            "12301802",
            "12304800",
        ):
            self.assertNotIn(literal, copied)

    def test_exact_installed_orphan_variant_is_preserved_and_other_drift_refuses(self):
        patched = event_blocks(patch_bsb_at_orphan(self.installed_orphan, self.bsb))
        self.assertIn("SetCharacterGravity(3600802, Disabled);", patched[13601802])
        self.assertIn(
            "DisplayBossHealthBar(Enabled, 3600800, 0, 209000)", patched[13604802]
        )
        with self.assertRaisesRegex(ValueError, "unsupported original Orphan arena"):
            patch_bsb_at_orphan(
                self.installed_orphan.replace(
                    "HandleBossDefeat(3600800)", "HandleBossDefeat(9)", 1
                ),
                self.bsb,
            )

    def test_native_plan_has_single_primary_swap_and_source_initialization_request(
        self,
    ):
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_bsb_at_orphan(self.slots, npcs, effects, "test")
        self.assertEqual("c2090", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            "m23_00_00_00", plan["primary_init_source_bindings"][0]["source_map"]
        )
        self.assertEqual(
            "m36_00_00_00", plan["primary_init_source_bindings"][0]["destination_map"]
        )
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_pins_and_project_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "original EMEVD literal"):
            patch_bsb_at_orphan(
                self.orphan, self.bsb, BsbOrphanIds(12991100, 12991100, 12991102)
            )
        with self.assertRaisesRegex(ValueError, "original EMEVD literal"):
            patch_bsb_at_orphan(
                self.orphan, self.bsb, BsbOrphanIds(12991099, 12991101, 12991102)
            )
        with self.assertRaisesRegex(ValueError, "unsupported original BSB donor"):
            patch_bsb_at_orphan(
                self.orphan,
                self.bsb.replace("HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5"),
                DEFAULT_IDS,
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Orphan arena"):
            patch_bsb_at_orphan(
                self.orphan.replace(
                    "HandleBossDefeat(3600800)", "HandleBossDefeat(99)", 1
                ),
                self.bsb,
            )


if __name__ == "__main__":
    unittest.main()
