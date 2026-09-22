import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.wet_nurse_bsb_contract import (
    BSB_SOURCE,
    BUNDLE,
    DEFAULT_IDS,
    WET_NURSE_SOURCE,
    native_plan_wet_nurse_at_bsb,
    patch_wet_nurse_at_bsb,
)


class WetNurseBsbContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
        cls.nurse = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_source_health_graph_replaces_bsb_health_without_inventing_opaque_actor(
        self,
    ):
        before = event_blocks(self.bsb)
        after = event_blocks(patch_wet_nurse_at_bsb(self.bsb, self.nurse))
        health = after[12304802]
        self.assertIn("SetCharacterImmortality(2300800, Enabled);", health)
        self.assertIn("SetCharacterImmortality(980200, Enabled);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 980201, 0, 551000);", health)
        self.assertIn("CreateReferredDamagePair(2300800, 980201);", health)
        self.assertIn("CreateReferredDamagePair(980200, 980201);", health)
        for actor in (2300800, 980200, 980201):
            self.assertIn(
                f"SetNetworkUpdateAuthority({actor}, AuthorityLevel.Forced);", health
            )
        self.assertNotIn("2600803", health)
        self.assertEqual(before[12301800], after[12301800])
        self.assertEqual(before[12304804], after[12304804])
        self.assertIn("HandleBossDefeat(2300800);", after[12301800])

    def test_source_visibility_lifecycle_and_map_ambience_policy_are_explicit(self):
        after = event_blocks(patch_wet_nurse_at_bsb(self.bsb, self.nurse))
        entry = after[12301802]
        self.assertLess(
            entry.index("ChangeCharacterEnableState(2300800, Disabled);"),
            entry.index("WaitFor("),
        )
        self.assertLess(
            entry.index("WaitFor("),
            entry.index("ChangeCharacterEnableState(2300800, Enabled);"),
        )
        self.assertNotIn("ForceAnimationPlayback(2300800, 7001", entry)
        self.assertIn("ChangeCharacterEnableState(2300800, Enabled);", after[12301803])
        self.assertEqual(event_blocks(self.bsb)[12304803], after[12304803])
        self.assertNotIn("260000003", "\n".join(after.values()))

    def test_source_support_object_warp_and_bsb_terminal_bridge_are_explicit(self):
        after = event_blocks(patch_wet_nurse_at_bsb(self.bsb, self.nurse))
        emergence = after[DEFAULT_IDS.support_emergence]
        self.assertIn("WarpObjectToCharacter(980208, 10000, 245);", emergence)
        for model_point in (4, 104, 10, 110):
            self.assertIn(
                f"IssueShortWarpRequest(980200, TargetEntityType.Object, 980208, {model_point});",
                emergence,
            )
        route = after[DEFAULT_IDS.core_warp]
        self.assertIn(
            "WarpCharacterAndSetFloor(chrEntityId, TargetEntityType.Area", route
        )
        self.assertNotRegex(route, r"(?<!\\d)260283[0-5](?!\\d)")
        bridge = after[DEFAULT_IDS.proxy_death_bridge]
        self.assertLess(
            bridge.index("WaitFor(HPRatio(980201) <= 0);"),
            bridge.index(
                "RequestCharacterAnimationReset(2300800, Interpolation.Uninterpolated);"
            ),
        )
        self.assertLess(
            bridge.index(
                "RequestCharacterAnimationReset(980200, Interpolation.Uninterpolated);"
            ),
            bridge.index("ForceCharacterDeath(980200, false);"),
        )
        self.assertLess(
            bridge.index("ForceCharacterDeath(2300800, false);"),
            bridge.index("ClearSpEffect(10000, 5630);"),
        )
        cleanup = after[DEFAULT_IDS.helper_cleanup]
        self.assertNotIn("EndIf(ThisEvent());", cleanup)
        self.assertIn("WaitFor(EventFlag(12301800));", cleanup)
        self.assertIn("ChangeCharacterEnableState(980200, Disabled);", cleanup)
        self.assertIn("ChangeCharacterEnableState(980201, Disabled);", cleanup)
        self.assertEqual("    EndEvent();", after[12304807].splitlines()[1])
        phase = after[12304808]
        self.assertIn("WaitFor(HPRatio(980201) < 0.7);", phase)
        self.assertNotIn("RequestCharacterAICommand", phase)
        self.assertNotIn("EndEvent();", phase)

    def test_plan_requires_three_actors_six_regions_and_model_point_object_per_bsb_state(
        self,
    ):
        plan = native_plan_wet_nurse_at_bsb(
            self.slots, self.npcs, self.effects, "wet-nurse-bsb"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5510", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(4, len(plan["boss_actor_additions"]))
        self.assertEqual(
            {980200, 980201},
            {
                addition["destination_entity_id"]
                for addition in plan["boss_actor_additions"]
            },
        )
        self.assertEqual(12, len(plan["boss_region_additions"]))
        self.assertEqual(
            set(range(980202, 980208)),
            {
                addition["destination_entity_id"]
                for addition in plan["boss_region_additions"]
            },
        )
        self.assertEqual(2, len(plan["boss_object_additions"]))
        self.assertEqual(
            {980208},
            {
                addition["destination_entity_id"]
                for addition in plan["boss_object_additions"]
            },
        )
        contract = plan["boss_contract"]
        self.assertEqual("unobserved", contract["runtime_status"])
        self.assertIn("not materialized", contract["opaque_actor_policy"])
        changed = contract["event_patch"]["changed_events"]
        self.assertEqual(
            12604802,
            next(
                row["source_event_id"]
                for row in changed
                if row["destination_event_id"] == 12304802
            ),
        )
        self.assertNotIn(
            12304802,
            {
                row["destination_event_id"]
                for row in contract["event_patch"]["added_events"]
            },
        )
        ambience = contract["source_map_ambience_not_transplanted"]
        self.assertEqual(12604815, ambience["event_id"])
        self.assertEqual(260000003, ambience["sound_id"])
        self.assertEqual("sprj_m26.fev", ambience["bank"])
        self.assertEqual("destination_owned_environmental_audio", ambience["policy"])

    def test_id_collision_and_pinned_source_or_destination_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129921xx"):
            patch_wet_nurse_at_bsb(
                self.bsb,
                self.nurse,
                replace(DEFAULT_IDS, health_entered_flag=DEFAULT_IDS.warp_flag_first),
            )
        with self.assertRaisesRegex(ValueError, "helper IDs"):
            patch_wet_nurse_at_bsb(
                self.bsb,
                self.nurse,
                replace(DEFAULT_IDS, support_entity=2300800),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original BSB arena"):
            patch_wet_nurse_at_bsb(
                self.bsb.replace("HandleBossDefeat(2300800)", "HandleBossDefeat(7)"),
                self.nurse,
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Wet Nurse donor"):
            patch_wet_nurse_at_bsb(
                self.bsb,
                self.nurse.replace(
                    "CreateReferredDamagePair(2600800, 2600802)",
                    "CreateReferredDamagePair(2600800, 1)",
                ),
            )


if __name__ == "__main__":
    unittest.main()
