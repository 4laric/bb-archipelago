import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer import rom_one_reborn_contract as contract
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class RomOneRebornTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(contract.BUNDLE, contract.ARENA_SOURCE).decode(
            "utf-8-sig"
        )
        cls.donor = read_blob(contract.BUNDLE, contract.rom.ROM_SOURCE).decode(
            "utf-8-sig"
        )
        cls.original = event_blocks(cls.arena)
        cls.source = event_blocks(cls.donor)
        cls.patched = event_blocks(
            contract.patch_rom_at_one_reborn(cls.arena, cls.donor)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(contract.BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(contract.BUNDLE)

    def plan(self, slots=None):
        return contract.native_plan_rom_at_one_reborn(
            self.slots if slots is None else slots,
            self.npcs,
            self.effects,
            "rom-one-test",
        )

    def test_original_proxy_terminal_and_rewards_follow_rom_death(self):
        terminal = self.original[12801800]
        self.assertEqual(terminal, self.patched[12801800])
        self.assertIn("WaitFor(HPRatio(2800803) <= 0);", terminal)
        self.assertIn("AwardItemLot(50700000);", terminal)
        bridge = self.patched[contract.BRIDGE]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2800800));"),
            bridge.index("ForceCharacterDeath(2800803, false);"),
        )
        for entity in contract.RETAINED:
            self.assertLess(
                bridge.index(f"ChangeCharacterEnableState({entity}, Disabled);"),
                bridge.index("EndIf(EventFlag(12801800));"),
            )

    def test_displaced_combat_is_retired_but_local_entry_and_fog_survive(self):
        for event in contract.RETIRED_EVENTS:
            self.assertIn("EndEvent();", self.patched[event])
            self.assertNotIn("RequestCharacterAICommand", self.patched[event])
            self.assertNotIn("WarpCharacter", self.patched[event])
        for event in (12801802, 12801803):
            self.assertIn(
                "ChangeCharacterEnableState(2800800, Enabled);", self.patched[event]
            )
            self.assertNotIn(
                "ChangeCharacterEnableState(2800801, Enabled);", self.patched[event]
            )
        self.assertIn("PlayCutsceneToPlayer(28000000", self.patched[12801802])
        for event in (12801801, 12804805, 12804880, 12804881, 12804882, 12804883):
            self.assertEqual(self.original[event], self.patched[event])

    def test_all_rom_phase_limb_and_thirty_spider_initializers_are_preserved(self):
        for event, count in (
            (13204807, 1),
            (13204808, 1),
            (13204809, 1),
            (13204810, 1),
            (13204000, 30),
            (13204050, 30),
            (13204730, 30),
        ):
            source_calls = [
                line
                for line in self.source[0].splitlines()
                if f", {event}," in line or f", {event});" in line
            ]
            self.assertEqual(count, len(source_calls))
            for line in source_calls:
                expected = contract.rom._remap(line, contract._mapping())
                self.assertIn(expected, self.patched[0])
        phase = self.patched[contract.EVENT_MAP[13204807]]
        for entity in contract.WARPS:
            self.assertIn(str(entity), phase)
        self.assertIn("CharacterHasEventMessage(3200800, 10)", self.source[13204803])
        self.assertIn("CharacterHasEventMessage(2800800, 10)", self.patched[12804803])

    def test_completed_load_also_cleans_up_every_spider_wave(self):
        cleanup = self.patched[contract.EVENT_MAP[13204050]]
        self.assertIn("|| EventFlag(12801800)", cleanup)
        self.assertIn("ForceCharacterDeath", cleanup)
        self.assertIn("CharacterDead(2800800)", cleanup)

    def test_native_plan_carries_both_states_and_complete_pinned_helper_rosters(self):
        plan = self.plan()
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(2, len(plan["swaps"][0]["destination_keys"]))
        self.assertEqual(60, len(plan["boss_actor_additions"]))
        self.assertEqual(4, len(plan["boss_region_additions"]))
        self.assertEqual(60, len(plan["boss_actor_scaling_requirements"]))
        self.assertEqual(18, len(plan["boss_contract"]["retained_destination_helpers"]))
        for state in contract.STATES:
            helpers = [
                row
                for row in plan["boss_actor_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(
                set(contract.SPIDERS), {row["destination_entity_id"] for row in helpers}
            )
            source_state = contract.rom.ROM_STATES[contract.STATES.index(state)]
            self.assertEqual(
                [contract.rom.ROM_CORE_PINS[source_state]] * 30,
                [row["source_provenance"]["anchor_sha256"] for row in helpers],
            )
            regions = [
                row
                for row in plan["boss_region_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(
                set(contract.WARPS), {row["destination_entity_id"] for row in regions}
            )
            self.assertEqual(
                [contract.ACTOR_WITNESSES[state][contract.PRIMARY]["sha256"]] * 2,
                [
                    row["destination_anchor_provenance"]["part_sha256"]
                    for row in regions
                ],
            )

    def test_original_event_drift_and_allocated_id_collision_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "original One Reborn"):
            contract.patch_rom_at_one_reborn(
                self.arena.replace("AwardItemLot(50700000);", "AwardItemLot(1);"),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "original Rom"):
            contract.patch_rom_at_one_reborn(
                self.arena,
                self.donor.replace("CreatePlaylog(124);", "CreatePlaylog(1);"),
            )
        with self.assertRaisesRegex(ValueError, "collides with destination"):
            contract.patch_rom_at_one_reborn(
                self.arena + "\n// reserved 981100\n", self.donor
            )

    def test_incomplete_destination_or_changed_spider_archetype_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "both destination map states"):
            self.plan(
                [
                    row
                    for row in self.slots
                    if not (
                        row.entity_id == contract.PRIMARY
                        and row.map_name == contract.STATES[1]
                    )
                ]
            )
        changed = [
            (
                replace(row, archetype=replace(row.archetype, npc_param_id=1))
                if row.entity_id == 3200200
                else row
            )
            for row in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "spider roster drift"):
            self.plan(changed)


if __name__ == "__main__":
    unittest.main()
