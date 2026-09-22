import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_actor_scaling import allocate_actor_scaling
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.logarius_contract import (
    BUNDLE,
    BSB_EVENT_SOURCE,
    DEFAULT_IDS,
    LOGARIUS_CORE,
    LOGARIUS_EFFECT_OWNER,
    LOGARIUS_SWORD,
    PROJECT_EFFECT_OWNER_ENTITY,
    PROJECT_SWORD_ENTITY,
    helper_scaling_parents,
    native_plan_logarius_at_bsb,
    patch_logarius_at_bsb,
)
from tools.bb_enemizer.scaling import load_params


class LogariusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = read_blob(BUNDLE, BSB_EVENT_SOURCE).decode("utf-8-sig")
        cls.logarius = read_blob(BUNDLE, "event/m25_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_patch_preserves_bsb_completion_and_ports_sword_combat_closure(self):
        before = event_blocks(self.bsb)
        after = event_blocks(patch_logarius_at_bsb(self.bsb, self.logarius))
        self.assertEqual(before[12301800], after[12301800])
        self.assertIn("HandleBossDefeat(2300800)", after[12301800])
        self.assertIn(
            "DisplayBossHealthBar(Enabled, 2300800, 0, 232000)", after[12304802]
        )
        self.assertIn("CreateBulletOwner(980006)", after[12304802])
        self.assertIn(
            "WarpCharacterAndCopyFloor(980005", after[DEFAULT_IDS.sword_event_id]
        )
        self.assertIn(
            "ShootBullet(980006, 2300800, 6, 223200590",
            after[DEFAULT_IDS.aura_event_id],
        )
        self.assertIn(
            "ForceAnimationPlayback(2300800, 2100", after[DEFAULT_IDS.cleanup_event_id]
        )
        self.assertIn(
            "WaitFor(EventFlag(12301800))", after[DEFAULT_IDS.lifecycle_event_id]
        )
        self.assertIn(
            "ForceCharacterDeath(980005, false)", after[DEFAULT_IDS.lifecycle_event_id]
        )
        self.assertIn(
            "ForceCharacterDeath(980006, false)", after[DEFAULT_IDS.lifecycle_event_id]
        )
        self.assertEqual(
            2, after[0].count(f"$InitializeEvent(0, {DEFAULT_IDS.sword_event_id});")
        )
        self.assertEqual(set(before) | set(DEFAULT_IDS.event_ids()), set(after))

    def test_patch_keeps_destination_entry_and_music_objects_with_typed_adaptations(
        self,
    ):
        after = event_blocks(patch_logarius_at_bsb(self.bsb, self.logarius))
        self.assertIn("InArea(10000, 2302805)", after[12301802])
        self.assertIn("ForceAnimationPlayback(2300800, 7000", after[12301802])
        self.assertIn("SetMapSoundState(2303802, Disabled)", after[12304803])
        self.assertIn("CharacterHasSpEffect(2300800, 5633)", after[12304803])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304804])
        for event_id in (12304807, 12304808):
            self.assertEqual("    EndEvent();", after[event_id].splitlines()[1])
        copied = "\n".join(
            after[event] for event in (12304802, 12304804, *DEFAULT_IDS.event_ids())
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:125|250)\d+(?!\d)")

    def test_native_plan_binds_exact_three_actor_roster_and_native_pins(self):
        plan = native_plan_logarius_at_bsb(
            self.slots, self.npcs, self.effects, "logarius-bsb"
        )
        self.assertEqual("c2320", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {"m23_00_00_00", "m23_00_00_01"},
            {row["destination_map"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {LOGARIUS_SWORD, LOGARIUS_EFFECT_OWNER},
            {row["source_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {PROJECT_SWORD_ENTITY, PROJECT_EFFECT_OWNER_ENTITY},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {"c2320_0000"},
            {row["source_anchor_part"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {
                "fc114097901492ce96524c9265c04a6c2606b3b825336723adb52c9064475b1d",
                "7bd8e95bd08d4bfe30801d088983025c6c1593885dfc97cabff3ecc89c5c4984",
            },
            {
                row["source_provenance"]["part_sha256"]
                for row in plan["boss_actor_additions"]
            },
        )
        self.assertEqual(
            {LOGARIUS_CORE},
            {row["source_entity_id"] for row in plan["primary_init_source_bindings"]},
        )
        self.assertEqual(
            "original_native_part_pinned_runtime_unobserved",
            plan["boss_contract"]["effect_owner_adapter"]["evidence_status"],
        )
        self.assertTrue(plan["scaling"]["enabled"])

    def test_helper_scaling_is_declared_for_post_combination_allocation(self):
        plan = native_plan_logarius_at_bsb(
            self.slots, self.npcs, self.effects, "logarius-scaling"
        )
        parents = helper_scaling_parents(plan)
        self.assertEqual(4, len(parents))
        self.assertEqual(
            {"ap_logarius_sword", "ap_logarius_effect_owner"},
            {part for _, part in parents},
        )
        self.assertEqual(
            {232000, 232100},
            {
                row["source_npc_param_id"]
                for row in plan["boss_actor_scaling_requirements"]
            },
        )
        self.assertEqual(
            {9}, {row["source_level"] for row in plan["scaling"]["changes"]}
        )
        scaling = allocate_actor_scaling(plan, self.npcs, parents)
        self.assertEqual(4, len(scaling))
        by_part = {}
        for row in scaling:
            by_part.setdefault(row["destination_part"], set()).add(
                row["cloned_npc_param_id"]
            )
        self.assertEqual(1, len(by_part["ap_logarius_sword"]))
        self.assertEqual(1, len(by_part["ap_logarius_effect_owner"]))
        self.assertNotEqual(
            by_part["ap_logarius_sword"], by_part["ap_logarius_effect_owner"]
        )

    def test_collisions_source_drift_and_missing_roster_refuse(self):
        with self.assertRaisesRegex(ValueError, "reviewed project actor ID"):
            native_plan_logarius_at_bsb(
                self.slots,
                self.npcs,
                self.effects,
                "bad",
                replace(DEFAULT_IDS, sword_entity_id=LOGARIUS_SWORD),
            )
        with self.assertRaisesRegex(ValueError, "129909xx"):
            patch_logarius_at_bsb(
                self.bsb, self.logarius, replace(DEFAULT_IDS, cleanup_event_id=12990899)
            )
        with patch(
            "tools.bb_enemizer.logarius_contract._globally_used_numbers",
            return_value=({DEFAULT_IDS.sword_event_id}, {PROJECT_SWORD_ENTITY}),
        ):
            with self.assertRaisesRegex(ValueError, "project actor ID collides"):
                patch_logarius_at_bsb(self.bsb, self.logarius)
        with self.assertRaisesRegex(ValueError, "unsupported original Logarius donor"):
            patch_logarius_at_bsb(self.bsb, "broken")
        without_effect_owner = [
            slot for slot in self.slots if slot.entity_id != LOGARIUS_EFFECT_OWNER
        ]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_logarius_at_bsb(
                without_effect_owner, self.npcs, self.effects, "missing"
            )


if __name__ == "__main__":
    unittest.main()
