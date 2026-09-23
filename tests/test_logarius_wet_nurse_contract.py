import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.logarius_wet_nurse_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LOGARIUS_SOURCE,
    WET_NURSE_SOURCE,
    native_plan_logarius_at_wet_nurse,
    patch_logarius_at_wet_nurse,
)
from tools.bb_enemizer.scaling import load_params


class LogariusWetNurseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logarius = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
        cls.nurse = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_direct_logarius_health_keeps_wet_proxy_as_terminal_operand(self):
        before = event_blocks(self.nurse)
        after = event_blocks(patch_logarius_at_wet_nurse(self.nurse, self.logarius))
        health = after[12604802]
        self.assertIn("DisplayBossHealthBar(Enabled, 2600800, 0, 232000);", health)
        self.assertIn("CreateBulletOwner(980501);", health)
        self.assertIn("SetCharacterImmortality(980500, Enabled);", health)
        self.assertNotIn("CreateReferredDamagePair", health)
        self.assertIn("ChangeCharacterEnableState(2600801, Disabled);", health)
        self.assertIn("SetCharacterAIState(2600802, Disabled);", health)
        for actor in (2600800, 2600801, 2600802, 980500):
            self.assertIn(
                f"SetNetworkUpdateAuthority({actor}, AuthorityLevel.Forced);", health
            )
        self.assertEqual(before[12601800], after[12601800])
        self.assertEqual(before[12604804], after[12604804])
        self.assertIn("HandleBossDefeat(2600803);", after[12601800])
        self.assertIn("!CharacterDead(2600803)", after[12604804])

    def test_sword_aura_and_proxy_bridge_keep_source_and_destination_roles_separate(
        self,
    ):
        after = event_blocks(patch_logarius_at_wet_nurse(self.nurse, self.logarius))
        self.assertIn(
            "WarpCharacterAndCopyFloor(980500, TargetEntityType.Character, 2600800",
            after[DEFAULT_IDS.sword_event],
        )
        self.assertIn("SpawnOneshotSFX", after[DEFAULT_IDS.sword_event])
        self.assertIn("623206", after[DEFAULT_IDS.sword_event])
        self.assertIn(
            "ShootBullet(980501, 2600800, 6, 223200590", after[DEFAULT_IDS.aura_event]
        )
        self.assertIn(
            "ForceAnimationPlayback(2600800, 2100",
            after[DEFAULT_IDS.phase_cleanup_event],
        )
        bridge = after[DEFAULT_IDS.proxy_bridge_event]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2600800));"),
            bridge.index("ForceCharacterDeath(2600802, false);"),
        )
        self.assertIn(
            "WaitFor(EventFlag(12601800));", after[DEFAULT_IDS.helper_cleanup_event]
        )
        self.assertIn(
            "ForceCharacterDeath(980500, false);",
            after[DEFAULT_IDS.helper_cleanup_event],
        )
        self.assertIn(
            "ForceCharacterDeath(980501, false);",
            after[DEFAULT_IDS.helper_cleanup_event],
        )
        self.assertIn("CharacterHasSpEffect(2600800, 5633)", after[12604803])
        for event in (12604810, 12604815, 12604820, 12604830, 12604840):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])

    def test_plan_binds_exact_three_actor_source_and_retained_wet_helpers(self):
        plan = native_plan_logarius_at_wet_nurse(
            self.slots, self.npcs, self.effects, "logarius-wet"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c2320", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {980500, 980501},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {2500801, 2500802},
            {row["source_entity_id"] for row in plan["boss_actor_additions"]},
        )
        contract = plan["boss_contract"]
        self.assertEqual("unobserved", contract["runtime_status"])
        self.assertIn("do not materialize", contract["opaque_actor_policy"])
        self.assertEqual(
            {2600801, 2600802},
            {row["entity_id"] for row in contract["retained_destination_helpers"]},
        )
        for helper in contract["retained_destination_helpers"]:
            self.assertEqual("m26_00_00_00", helper["map"])
            self.assertEqual(
                "bb-boss-actor-pin-v1", helper["source_provenance"]["format"]
            )
            self.assertEqual(
                {"talk_id", "unk_t18", "init_anim_id", "damage_anim_id"},
                set(helper["source_initialization"]),
            )
        self.assertTrue(plan["scaling"]["enabled"])
        requirement = plan["boss_emevd_ffx_requirements"][0]
        self.assertEqual(
            ("m25_00_00_00.emevd.dcx", 12504806),
            (requirement["source_event_file"], requirement["source_event_id"]),
        )
        self.assertEqual(
            ("m26_00_00_00.emevd.dcx", DEFAULT_IDS.sword_event, 623206),
            (
                requirement["destination_event_file"],
                requirement["destination_event_id"],
                requirement["effect_id"],
            ),
        )
        self.assertEqual(
            ("frpg_sfxbnd_m25.ffxbnd.dcx", "frpg_sfxbnd_m26.ffxbnd.dcx", [623206]),
            (
                plan["boss_ffx_merges"][0]["source_file"],
                plan["boss_ffx_merges"][0]["destination_file"],
                plan["boss_ffx_merges"][0]["required_effect_ids"],
            ),
        )

    def test_ids_and_pinned_source_or_destination_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129926xx"):
            patch_logarius_at_wet_nurse(
                self.nurse,
                self.logarius,
                replace(DEFAULT_IDS, aura_event=DEFAULT_IDS.sword_event),
            )
        with self.assertRaisesRegex(ValueError, "helper IDs"):
            patch_logarius_at_wet_nurse(
                self.nurse, self.logarius, replace(DEFAULT_IDS, sword_entity=2600800)
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Logarius donor"):
            patch_logarius_at_wet_nurse(
                self.nurse,
                self.logarius.replace("ShootBullet(2500802", "ShootBullet(7"),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Wet Nurse arena"):
            patch_logarius_at_wet_nurse(
                self.nurse.replace("HandleBossDefeat(2600803)", "HandleBossDefeat(7)"),
                self.logarius,
            )


if __name__ == "__main__":
    unittest.main()
