import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.rom_ebrietas_contract import (
    BUNDLE,
    DEFAULT_IDS,
    EBRIETAS_SOURCE,
    ROM_SOURCE,
    SPIDER_ENTITIES,
    WARP_ENTITIES,
    native_plan_rom_at_ebrietas,
    patch_rom_at_ebrietas,
    rom_helper_scaling_parents,
)
from tools.bb_enemizer.scaling import load_params


class RomEbrietasContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig")
        cls.ebrietas = read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self):
        return event_blocks(patch_rom_at_ebrietas(self.ebrietas, self.rom))

    def test_destination_progression_fog_coop_and_music_cleanup_are_preserved(self):
        before = event_blocks(self.ebrietas)
        after = self.patched()
        for event_id in (12421800, 12421801, 12421803, 12424805, 12424810, 12424811):
            self.assertEqual(before[event_id], after[event_id])
        activation = after[12421802]
        self.assertIn(
            "IssueShortWarpRequest(2420800, TargetEntityType.Area, 2422800", activation
        )
        self.assertIn("HasDamageType(2420800, -1, DamageType.Unspecified)", activation)
        self.assertIn("$InitializeEvent(0, 9350, 3)", activation)
        self.assertNotIn("5647", activation)
        self.assertNotIn("ForceAnimationPlayback", activation)

    def test_health_music_camera_and_phase_use_ebrietas_arena_operands(self):
        after = self.patched()
        health = after[12424802]
        self.assertIn("SetCharacterImmortality(2420800, Enabled)", health)
        self.assertIn("EventFlag(12421802) && EventFlag(12424800)", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 2420800, 0, 510000)", health)
        self.assertIn("CreatePlaylog(104)", health)
        self.assertIn("StartTimeMeasurement(2420010, 40, Enabled)", health)
        self.assertIn("InArea(10000, 2422802)", after[12424803])
        self.assertIn("SetMapSoundState(2423802, Disabled)", after[12424803])
        self.assertEqual(2, after[12424804].count("SetLockcamSlotNumber(24, 2,"))
        phase = after[DEFAULT_IDS.phase]
        self.assertIn(f"TargetEntityType.Area, {WARP_ENTITIES[0]}, -1", phase)
        self.assertIn(f"TargetEntityType.Area, {WARP_ENTITIES[1]}, -1", phase)
        self.assertIn(f"SetEventFlag({DEFAULT_IDS.wave_two_flag}, ON)", phase)
        self.assertIn(f"SetEventFlag({DEFAULT_IDS.wave_three_flag}, ON)", phase)

    def test_limb_anomaly_is_preserved_but_foreign_replans_are_removed(self):
        after = self.patched()
        part2 = after[DEFAULT_IDS.limb_part2]
        part3 = after[DEFAULT_IDS.limb_part3]
        self.assertIn("NPCPartHP(2420800, 3) <= 0", part3)
        self.assertNotIn(
            "RequestCharacterAIReplan(2420800);\n    WaitFixedTimeFrames(10)", part2
        )
        self.assertNotIn(
            "RequestCharacterAIReplan(2420800);\n    WaitFixedTimeFrames(10)", part3
        )
        self.assertIn("RequestCharacterAIReplan(2420800)", part2)
        self.assertIn("RequestCharacterAIReplan(2420800)", part3)
        for body in (part2, part3):
            self.assertEqual(1, body.count("WaitFixedTimeFrames(10)"))

    def test_constructor_has_all_three_thirty_spider_controller_sets(self):
        constructor = self.patched()[0]
        expected = {
            DEFAULT_IDS.phase: 1,
            DEFAULT_IDS.limb_part2: 1,
            DEFAULT_IDS.limb_part3: 1,
            DEFAULT_IDS.limb_part1: 1,
            DEFAULT_IDS.wave_enable: 30,
            DEFAULT_IDS.wave_cleanup: 30,
            DEFAULT_IDS.spider_target: 30,
            DEFAULT_IDS.owner_cleanup: 1,
        }
        for event_id, count in expected.items():
            self.assertEqual(
                count,
                len(
                    re.findall(
                        r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                        constructor,
                    )
                ),
            )
        for entity in SPIDER_ENTITIES:
            self.assertEqual(
                3, len(re.findall(r"[, ]" + str(entity) + r"(?:,|\))", constructor))
            )

    def test_spiders_and_destination_owner_have_terminal_cleanup(self):
        after = self.patched()
        cleanup = after[DEFAULT_IDS.wave_cleanup]
        self.assertIn("EventFlag(12421800)", cleanup)
        self.assertIn("ForceCharacterDeath(chrEntityId, false)", cleanup)
        owner = after[DEFAULT_IDS.owner_cleanup]
        wait = owner.index("WaitFor(EventFlag(12421800));")
        self.assertIn("ChangeCharacterEnableState(2420801, Disabled)", owner[:wait])
        self.assertNotIn("ForceCharacterDeath", owner[:wait])
        self.assertIn("ForceCharacterDeath(2420801, false)", owner[wait:])
        self.assertNotIn("CreateBulletOwner(2420801)", after[0])
        for event_id in (12424870, 12424871, 12424980, 12424990):
            self.assertEqual("    EndEvent();", after[event_id].splitlines()[1])

    def test_native_plan_pins_full_two_state_roster_and_regions(self):
        plan = native_plan_rom_at_ebrietas(
            self.slots, self.npcs, self.effects, "rom-ebrietas"
        )
        self.assertEqual("c5100", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(60, len(plan["boss_actor_additions"]))
        self.assertEqual(4, len(plan["boss_region_additions"]))
        self.assertEqual(2, len(plan["primary_init_source_bindings"]))
        self.assertEqual(60, len(rom_helper_scaling_parents(plan)))
        self.assertEqual(
            set(SPIDER_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            set(WARP_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_region_additions"]},
        )
        for row in plan["boss_region_additions"]:
            self.assertEqual(
                "bb-boss-region-pin-v1", row["source_provenance"]["format"]
            )
            self.assertEqual(64, len(row["source_provenance"]["region_sha256"]))
            self.assertEqual(64, len(row["source_anchor_provenance"]["part_sha256"]))
            self.assertEqual(
                64, len(row["destination_anchor_provenance"]["part_sha256"])
            )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(2, len(retained))
        self.assertEqual(
            {("m24_02_00_00", 2420801), ("m24_02_00_01", 2420801)},
            {(row["map"], row["entity_id"]) for row in retained},
        )
        self.assertNotIn("boss_generator_additions", plan)
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_source_destination_id_and_roster_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129919xx"):
            patch_rom_at_ebrietas(
                self.ebrietas,
                self.rom,
                replace(DEFAULT_IDS, phase=DEFAULT_IDS.limb_part2),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Rom donor"):
            patch_rom_at_ebrietas(
                self.ebrietas,
                self.rom.replace(
                    "HPRatio(3200800) <= 0.75", "HPRatio(3200800) <= 0.74"
                ),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Ebrietas arena"):
            patch_rom_at_ebrietas(
                self.ebrietas.replace(
                    "HandleBossDefeat(2420800)", "HandleBossDefeat(9)"
                ),
                self.rom,
            )
        reduced = [slot for slot in self.slots if slot.entity_id != 3200229]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_rom_at_ebrietas(
                reduced, self.npcs, self.effects, "missing-spider"
            )


if __name__ == "__main__":
    unittest.main()
