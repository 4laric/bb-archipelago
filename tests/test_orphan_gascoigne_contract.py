import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.orphan_gascoigne_contract import (
    BUNDLE,
    DEFAULT_IDS,
    GASCOIGNE_SOURCE,
    ORPHAN_SOURCE,
    OrphanGascoigneIds,
    native_plan_orphan_at_gascoigne,
    patch_orphan_at_gascoigne,
)
from tools.bb_enemizer.scaling import load_params


class OrphanGascoigneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orphan = (
            read_blob(BUNDLE, ORPHAN_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        cls.gascoigne = (
            read_blob(BUNDLE, GASCOIGNE_SOURCE)
            .decode("utf-8-sig")
            .replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)

    def test_preserves_gascoigne_terminal_cutscene_and_or_death_predicate(self):
        before = event_blocks(self.gascoigne)
        after = event_blocks(patch_orphan_at_gascoigne(self.gascoigne, self.orphan))
        for event in (12411800, 12411801, 12411802):
            self.assertEqual(before[event], after[event])
        self.assertIn("WaitFor(chr || chr2);", after[12411800])
        self.assertEqual(set(before).union(DEFAULT_IDS.added_events()), set(after))

    def test_health_uses_independent_ready_flag_and_never_kills_phase_early(self):
        after = event_blocks(patch_orphan_at_gascoigne(self.gascoigne, self.orphan))
        health = after[12414802]
        self.assertIn("SetEventFlag(12991700, ON);", health)
        self.assertIn("CreateReferredDamagePair(2410810, 2410811);", health)
        self.assertIn("ChangeCharacterEnableState(2410811, Disabled);", health)
        self.assertNotIn("ForceCharacterDeath", health)
        self.assertIn("EventFlag(12991700)", after[12414803])
        cleanup = after[DEFAULT_IDS.cleanup_event]
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(12411800));"),
            cleanup.index("ForceCharacterDeath(2410811, false);"),
        )

    def test_phase_support_and_cameras_use_declared_destination_bindings(self):
        after = event_blocks(patch_orphan_at_gascoigne(self.gascoigne, self.orphan))
        phase, support = after[12991720], after[12991730]
        self.assertIn("ChangeCharacterEnableState(2410811, Enabled);", phase)
        self.assertIn("ChangeCharacterEnableState(980007, Enabled);", support)
        self.assertIn("SetCharacterAIState(980007, Enabled);", support)
        self.assertIn("SetLockcamSlotNumber(24, 1, 1)", after[12414804])
        self.assertIn("SetLockcamSlotNumber(24, 1, 0)", after[12414804])
        self.assertNotIn("SetLockcamSlotNumber(34,", after[12414804])
        for event in (12414807, 12414808, 12414809):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])

    def test_full_added_graph_is_initialized_and_pinned_ids_fail_closed(self):
        after = event_blocks(patch_orphan_at_gascoigne(self.gascoigne, self.orphan))
        for event in DEFAULT_IDS.added_events():
            self.assertEqual(1, after[0].count(f"$InitializeEvent(0, {event});"))
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_orphan_at_gascoigne(
                self.gascoigne,
                self.orphan,
                replace(DEFAULT_IDS, support_entity=2410811),
            )
        with self.assertRaisesRegex(ValueError, "Orphan donor"):
            patch_orphan_at_gascoigne(
                self.gascoigne,
                self.orphan.replace(
                    "HPRatio(3600800) < 0.5", "HPRatio(3600800) < 0.4", 1
                ),
            )

    def test_native_plan_has_two_primaries_three_support_requirements_and_complete_scaling(
        self,
    ):
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_orphan_at_gascoigne(
            self.slots, npcs, effects, "orphan-gascoigne"
        )
        self.assertEqual(2, plan["swap_count"])
        self.assertEqual(
            [454000, 454100], [swap["target"]["npc_param_id"] for swap in plan["swaps"]]
        )
        self.assertEqual(
            6, sum(len(swap["destination_keys"]) for swap in plan["swaps"])
        )
        self.assertEqual(6, len(plan["primary_init_source_bindings"]))
        self.assertEqual(3, len(plan["boss_actor_additions"]))
        self.assertEqual(
            {980007},
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            {"c4543_0000"}, {row["source_part"] for row in plan["boss_actor_additions"]}
        )
        accounted = plan["scaling"]["changes"] + plan["scaling"]["skips"]
        self.assertEqual(
            {swap["logical_key"] for swap in plan["swaps"]},
            {row["logical_key"] for row in accounted},
        )


if __name__ == "__main__":
    unittest.main()
