import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.shadows_orphan_contract import (
    ACTOR_PINS,
    BUNDLE,
    DEFAULT_IDS,
    HELPER_ENTITIES,
    ORPHAN_SOURCE,
    REGION_PINS,
    SHADOWS_SOURCE,
    native_plan_shadows_at_orphan,
    patch_shadows_at_orphan,
    shadows_helper_scaling_parents,
)


class ShadowsOrphanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ORPHAN_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_three_body_bridge_preserves_orphan_rewards_and_postboss_flow(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_shadows_at_orphan(self.arena, self.donor))
        terminal = after[13601800]
        self.assertEqual(before[13601800], terminal)
        bridge = after[DEFAULT_IDS.bridge]
        self.assertIn(
            "CharacterDead(981310) && CharacterDead(981300) && CharacterDead(981301)",
            bridge,
        )
        self.assertIn("SetCharacterInvincibility(3600800, Disabled);", bridge)
        self.assertIn("ForceCharacterDeath(3600800, false);", bridge)
        for event in (13601801, 13601802, 13601803, 13601804):
            self.assertEqual(before[event], after[event])
        for literal in (
            "AwardAchievement(35);",
            "AwardItemLot(3601800);",
            "SetEventFlag(3600, ON);",
        ):
            self.assertIn(literal, terminal)

    def test_source_constructor_closure_keeps_exact_started_slot_counts(self):
        after = event_blocks(patch_shadows_at_orphan(self.arena, self.donor))
        constructor = after[0]
        expected = {
            DEFAULT_IDS.group_phase: 1,
            DEFAULT_IDS.summon: 3,
            DEFAULT_IDS.body_phase: 3,
            DEFAULT_IDS.attachment: 4,
            DEFAULT_IDS.effect: 2,
            DEFAULT_IDS.summon_cleanup: 3,
        }
        for event, count in expected.items():
            self.assertEqual(
                count,
                constructor.count(f", {event},") + constructor.count(f", {event});"),
            )
        self.assertNotIn(f", {DEFAULT_IDS.distance_pair}", constructor)
        self.assertNotIn(f", {DEFAULT_IDS.distance_all}", constructor)
        copied = (
            constructor
            + "\n"
            + "\n".join(after[event] for event in DEFAULT_IDS.event_map().values())
        )
        for entity in HELPER_ENTITIES:
            self.assertIn(str(entity), copied)
        for original in (
            2700800,
            2700801,
            2700802,
            2700803,
            2700804,
            2700805,
            2700810,
            2700811,
            2700813,
            2700814,
            2705001,
            2705002,
            2705003,
        ):
            self.assertNotIn(str(original), copied)

    def test_destination_helpers_stay_inert_then_all_imported_helpers_clean_up(self):
        after = event_blocks(patch_shadows_at_orphan(self.arena, self.donor))
        entry = after[DEFAULT_IDS.helper_entry]
        self.assertIn("ChangeCharacterEnableState(3600800, Disabled);", entry)
        self.assertIn("SetCharacterInvincibility(3600800, Enabled);", entry)
        self.assertIn("ChangeCharacterEnableState(981310, Disabled);", entry)
        self.assertIn("ChangeCharacterEnableState(981310, Enabled);", entry)
        self.assertLess(
            entry.index("ChangeCharacterEnableState(981300, Disabled);"),
            entry.index("WaitFor(EventFlag(13604808));"),
        )
        cleanup = after[DEFAULT_IDS.destination_cleanup]
        self.assertLess(
            cleanup.index("ChangeCharacterEnableState(3600801, Disabled);"),
            cleanup.index("WaitFor(EventFlag(13601800));"),
        )
        for entity in (*HELPER_ENTITIES, 3600801, 3600803):
            self.assertIn(f"ForceCharacterDeath({entity}, false);", cleanup)
        for generator in (981330, 981331, 981332):
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", cleanup)
        self.assertIn("SetEventFlag(12704808, OFF);", cleanup)
        for event in (13604820, 13604830, 13604840, 13604850):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])

    def test_native_plan_pins_complete_actor_generator_and_region_graph(self):
        plan = native_plan_shadows_at_orphan(
            self.slots, self.npcs, self.effects, "shadows-orphan"
        )
        self.assertEqual(
            set(HELPER_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {"c2120_0001"},
            {row["source_anchor_part"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {ACTOR_PINS[2700801]},
            {
                row["source_provenance"]["anchor_sha256"]
                for row in plan["boss_actor_additions"]
            },
        )
        self.assertEqual(12, len(plan["boss_region_additions"]))
        self.assertEqual(
            set(range(981340, 981352)),
            {row["destination_entity_id"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(
            {fingerprint for _, _, fingerprint in REGION_PINS},
            {
                row["source_provenance"]["region_sha256"]
                for row in plan["boss_region_additions"]
            },
        )
        self.assertEqual(
            {("c2120_0001", "c4540_0000")},
            {
                (row["source_anchor_part"], row["destination_anchor_part"])
                for row in plan["boss_region_additions"]
            },
        )
        self.assertEqual(
            {ACTOR_PINS[2700801]},
            {
                row["source_anchor_provenance"]["part_sha256"]
                for row in plan["boss_region_additions"]
            },
        )
        self.assertEqual(3, len(plan["boss_generator_additions"]))
        for index, generator in enumerate(plan["boss_generator_additions"]):
            self.assertEqual("h000600_0000", generator["destination_part_name"])
            self.assertEqual(
                {
                    f"ap_shadows_snake_spawn_{index * 4 + offset:02d}"
                    for offset in range(4)
                },
                set(generator["spawn_point_map"].values()),
            )
            self.assertEqual(1, len(generator["spawn_part_map"]))
        self.assertEqual(10, len(plan["boss_actor_scaling_requirements"]))
        self.assertEqual(10, len(shadows_helper_scaling_parents(plan)))
        self.assertEqual(
            3600800, plan["boss_contract"]["inert_terminal_proxy"]["entity_id"]
        )
        self.assertEqual(
            2700801,
            plan["boss_contract"]["placement_anchor_policy"]["source_anchor_entity"],
        )
        self.assertEqual(
            {3600801, 3600803},
            {
                row["entity_id"]
                for row in plan["boss_contract"]["retained_destination_helpers"]
            },
        )

    def test_source_drift_and_allocated_id_collisions_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Shadows donor"):
            patch_shadows_at_orphan(
                self.arena,
                self.donor.replace(
                    "DisplayBossHealthBar(Enabled, 2700800, 2, 212010);",
                    "DisplayBossHealthBar(Enabled, 2700800, 2, 1);",
                ),
            )
        with self.assertRaisesRegex(ValueError, "129935xx"):
            patch_shadows_at_orphan(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, bridge=DEFAULT_IDS.group_phase),
            )
        with self.assertRaisesRegex(ValueError, "helper IDs"):
            patch_shadows_at_orphan(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, generator_entity_first=HELPER_ENTITIES[0]),
            )

    def test_installed_quest_constructor_alternate_keeps_boss_patch_identical(self):
        installed = self.donor.replace(
            "    $InitializeEvent(0, 12700907);",
            "    $InitializeEvent(0, 12700910);",
        )
        self.assertNotEqual(self.donor, installed)
        self.assertEqual(
            patch_shadows_at_orphan(self.arena, self.donor),
            patch_shadows_at_orphan(self.arena, installed),
        )


if __name__ == "__main__":
    unittest.main()
