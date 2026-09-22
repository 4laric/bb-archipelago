import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer import witch_one_reborn_contract as contract
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class WitchOneRebornContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(contract.BUNDLE, contract.ARENA_SOURCE).decode(
            "utf-8-sig"
        )
        cls.donor = read_blob(contract.BUNDLE, contract.WITCH_SOURCE).decode(
            "utf-8-sig"
        )
        cls.original = event_blocks(cls.arena)
        cls.source = event_blocks(cls.donor)
        cls.patched = event_blocks(
            contract.patch_witch_at_one_reborn(cls.arena, cls.donor)
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(contract.BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(contract.BUNDLE)

    def plan(self, slots=None):
        return contract.native_plan_witch_at_one_reborn(
            self.slots if slots is None else slots,
            self.npcs,
            self.effects,
            "witch-one-test",
        )

    def test_original_terminal_is_exact_and_bridge_waits_for_both_witches(self):
        terminal = self.original[12801800]
        self.assertEqual(terminal, self.patched[12801800])
        self.assertIn("WaitFor(HPRatio(2800803) <= 0);", terminal)
        self.assertIn("AwardItemLot(50700000);", terminal)
        bridge = self.patched[contract.DEFAULT_IDS.terminal_bridge]
        death_wait = "WaitFor(CharacterDead(2800800) && CharacterDead(982200));"
        self.assertIn(death_wait, bridge)
        self.assertLess(
            bridge.index("SetCharacterGravity(2800803, Disabled);"),
            bridge.index(death_wait),
        )
        self.assertLess(
            bridge.index("SetCharacterInvincibility(2800803, Enabled);"),
            bridge.index(death_wait),
        )
        self.assertLess(
            bridge.index(death_wait), bridge.index("ForceCharacterDeath(2800803")
        )
        self.assertLess(
            bridge.index(death_wait),
            bridge.index("SetCharacterInvincibility(2800803, Disabled);"),
        )
        self.assertLess(
            bridge.index("SetCharacterInvincibility(2800803, Disabled);"),
            bridge.index("ForceCharacterDeath(2800803"),
        )
        self.assertEqual(1, bridge.count("ForceCharacterDeath(2800803"))
        self.assertIn("if (EventFlag(12801800))", bridge)
        for entity in contract.one.RETAINED:
            self.assertLess(
                bridge.index(f"ChangeCharacterEnableState({entity}, Disabled);"),
                bridge.index(death_wait),
            )

    def test_full_source_pair_minion_and_counter_closure_is_imported(self):
        ids = contract.DEFAULT_IDS
        constructor = self.patched[0]
        for source_event, destination_event, count in contract._copied_events(ids):
            source_calls = [
                line
                for line in self.source[0].splitlines()
                if f", {source_event}," in line or f", {source_event});" in line
            ]
            self.assertEqual(count, len(source_calls))
            expected = [
                contract.witch._remap(line, contract._mapping(ids))
                for line in source_calls
            ]
            for line in expected:
                self.assertIn(line, constructor)
            self.assertIn(destination_event, self.patched)
        revival = self.patched[ids.revival]
        self.assertIn("SetCharacterImmortality(chrEntityId, Enabled);", revival)
        self.assertIn("ForceCharacterDeath(chrEntityId2, false);", revival)
        self.assertIn("IssueShortWarpRequest", revival)
        manager = self.patched[ids.generator_manager]
        self.assertIn("EventValue(12994580, 10)", manager)
        self.assertNotIn("12994540, 10", manager)
        for event in (ids.minion_setup, ids.insight):
            self.assertEqual(
                "    EndIf(EventFlag(12801800));",
                self.patched[event].splitlines()[1],
            )
        self.assertTrue(
            set(range(ids.minion_count_flag, ids.minion_count_flag + 10)).isdisjoint(
                set(ids.events())
                | set(range(ids.visibility_flag_first, ids.insight_flag + 1))
            )
        )

    def test_one_reborn_entry_fog_shared_events_and_retirement_stay_destination_owned(
        self,
    ):
        for event in (12801802, 12801803):
            self.assertIn(
                "ChangeCharacterEnableState(2800800, Enabled);", self.patched[event]
            )
            self.assertNotIn(
                "ChangeCharacterEnableState(2800801, Enabled);", self.patched[event]
            )
        self.assertIn("PlayCutsceneToPlayer(28000000", self.patched[12801802])
        for event in contract.one.RETIRED_EVENTS:
            self.assertEqual("    EndEvent();", self.patched[event].splitlines()[1])
        for event in (12801801, 12804805, 12804880, 12804881, 12804882, 12804883):
            self.assertEqual(self.original[event], self.patched[event])
        self.assertIn("SetMapSoundState(2803802, Disabled);", self.patched[12804803])
        self.assertIn("SetLockcamSlotNumber(28, 0, 1);", self.patched[12804804])

    def test_live_bridge_cancels_pending_minion_reactivation(self):
        ids = contract.DEFAULT_IDS
        guard = f"EndIf(EventFlag({ids.shutdown_flag}));"
        guarded = 0
        activation_operands = (
            *(
                f"ChangeCharacterEnableState({ids.minion_first_entity + offset}, Enabled);"
                for offset in range(3)
            ),
            *(
                f"DeactivateGenerator({ids.generator_entity_first + offset}, Enabled);"
                for offset in range(3)
            ),
        )
        for event in ids.events():
            lines = self.patched[event].splitlines()
            for index, line in enumerate(lines):
                if any(operand in line for operand in activation_operands):
                    self.assertEqual(guard, lines[index - 1].strip())
                    guarded += 1
        self.assertEqual(9, guarded)

        bridge = self.patched[ids.terminal_bridge]
        shutdown = bridge.index(f"SetEventFlag({ids.shutdown_flag}, ON);")
        self.assertGreater(shutdown, bridge.index("WaitFor(CharacterDead(2800800)"))
        for offset in range(3):
            entity = ids.minion_first_entity + offset
            self.assertLess(
                shutdown,
                bridge.index(f"ForceCharacterDeath({entity}, false);", shutdown),
            )
            self.assertIn(f"SetCharacterImmortality({entity}, Disabled);", bridge)
        self.assertLess(shutdown, bridge.index("ForceCharacterDeath(2800803, false);"))

    def test_native_plan_has_two_complete_pinned_geometry_states(self):
        plan = self.plan()
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(2, len(plan["swaps"][0]["destination_keys"]))
        self.assertEqual(8, len(plan["boss_actor_additions"]))
        self.assertEqual(40, len(plan["boss_region_additions"]))
        self.assertEqual(6, len(plan["boss_generator_additions"]))
        self.assertEqual(8, len(plan["boss_actor_scaling_requirements"]))
        self.assertEqual(18, len(plan["boss_contract"]["retained_destination_helpers"]))
        for state in contract.STATES:
            actors = [
                row
                for row in plan["boss_actor_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(
                {982200, 982201, 982202, 982203},
                {row["destination_entity_id"] for row in actors},
            )
            regions = [
                row
                for row in plan["boss_region_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(20, len(regions))
            target_pin = contract.one.ACTOR_WITNESSES[state][contract.PRIMARY]["sha256"]
            self.assertEqual(
                {target_pin},
                {
                    row["destination_anchor_provenance"]["part_sha256"]
                    for row in regions
                },
            )
            generators = [
                row
                for row in plan["boss_generator_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(
                {"h000100"}, {row["destination_part_name"] for row in generators}
            )
            for index, row in enumerate(generators):
                self.assertEqual(
                    {
                        f"ap_witch_one_spawn_{4 * index + offset:02d}"
                        for offset in range(4)
                    },
                    set(row["spawn_point_map"].values()),
                )

    def test_runtime_boundary_and_geometry_policy_are_explicit(self):
        plan = self.plan()
        boss = plan["boss_contract"]
        self.assertEqual("unobserved", boss["runtime_status"])
        self.assertIn("anchor-relative", boss["geometry_policy"])
        self.assertIn("both source-controlled Witches", boss["terminal_policy"])
        self.assertEqual(
            {
                "actor_additions",
                "region_additions",
                "generator_additions",
                "generator_collision",
                "destination_anchors",
            },
            set(boss["native_requirements"]),
        )

    def test_allocation_source_and_destination_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129945xx"):
            contract.patch_witch_at_one_reborn(
                self.arena,
                self.donor,
                replace(
                    contract.DEFAULT_IDS,
                    minion_count_flag=contract.DEFAULT_IDS.visibility_flag_first,
                ),
            )
        with self.assertRaisesRegex(ValueError, "9822xx"):
            contract.patch_witch_at_one_reborn(
                self.arena,
                self.donor,
                replace(
                    contract.DEFAULT_IDS,
                    second_entity=contract.DEFAULT_IDS.warp_first_entity,
                ),
            )
        with self.assertRaisesRegex(ValueError, "129945xx"):
            contract.patch_witch_at_one_reborn(
                self.arena,
                self.donor,
                replace(
                    contract.DEFAULT_IDS,
                    shutdown_flag=contract.DEFAULT_IDS.insight_flag,
                ),
            )
        with self.assertRaisesRegex(ValueError, "One Reborn arena"):
            contract.patch_witch_at_one_reborn(
                self.arena.replace("AwardItemLot(50700000);", "AwardItemLot(1);"),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "Witch donor"):
            contract.patch_witch_at_one_reborn(
                self.arena,
                self.donor.replace(
                    "WaitFor(HPRatio(2200800) <= 0.5);",
                    "WaitFor(HPRatio(1) <= 0.5);",
                ),
            )

    def test_incomplete_destination_state_or_helper_archetype_refuses(self):
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
                if row.entity_id == contract.witch.MINIONS[0]
                else row
            )
            for row in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "source actor"):
            self.plan(changed)


if __name__ == "__main__":
    unittest.main()
