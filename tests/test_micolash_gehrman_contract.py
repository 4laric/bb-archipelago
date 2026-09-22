import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_pool import compose_event_patches
from tools.bb_enemizer.final_boss_contracts import (
    FinalAttachmentIds,
    patch_gehrman_at_moon,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.micolash_gehrman_contract import (
    ARENA_SOURCE,
    BUNDLE,
    DONOR_SOURCE,
    DEFAULT_IDS,
    patch_micolash_at_gehrman,
    native_plan_micolash_at_gehrman,
)


class MicolashGehrmanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_only_combat_events_change_and_both_dream_terminals_survive(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_micolash_at_gehrman(self.arena, self.donor))
        self.assertEqual(
            {0, 12104802, 12104803, 12104807, 12104808},
            {e for e in before if before[e] != after[e]},
        )
        self.assertEqual({DEFAULT_IDS.phase_state}, set(after) - set(before))
        for event in (50, 12100800, 12101800, 12101802, 12101850, 12101852, 12104804):
            self.assertEqual(before[event], after[event])

    def test_health_preserves_entry_protection_and_releases_direct_combat(self):
        after = event_blocks(patch_micolash_at_gehrman(self.arena, self.donor))
        health = after[12104802]
        self.assertLess(
            health.index("SetCharacterInvincibility(2100800, Enabled)"),
            health.index("WaitFor(EventFlag(12104800))"),
        )
        self.assertIn("SetCharacterInvincibility(2100800, Disabled)", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 2100800, 0, 899000)", health)
        self.assertIn("RequestCharacterAICommand(2100800, -1, 0)", health)
        self.assertIn("StartTimeMeasurement(2100010, 80, Enabled)", health)
        self.assertIn("SetSpEffect(2100800, 7500, true)", health)
        self.assertIn("SetSpEffect(2100800, 7501, true)", health)
        self.assertNotIn("12604731", health)
        self.assertNotIn("SetCharacterEventTarget", health)
        self.assertIn("EventFlag(12994120)", after[12104803])
        self.assertIn("HPRatio(2100800) <= 0.5", after[DEFAULT_IDS.phase_state])

    def test_primary_keeps_original_micolash_init_pin_and_retires_dialogue(self):
        plan = native_plan_micolash_at_gehrman(
            self.slots, self.npcs, self.effects, "gehrman"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(1, len(plan["primary_init_source_bindings"]))
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(2600850, binding["source_entity_id"])
        self.assertEqual(2100800, binding["destination_entity_id"])
        self.assertEqual(210306, binding["destination_original_talk_id"])
        self.assertEqual(0, binding["destination_talk_id_override"])
        self.assertEqual(
            {
                "talk_id": 260311,
                "unk_t18": 6380,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            binding["source_initialization"],
        )
        self.assertEqual(
            "ab37480d123ba5807ace745e2238c7891782479dec1fc3222267f62040460d35",
            binding["source_provenance"]["part_sha256"],
        )

    def test_composes_with_gehrman_at_moon_from_the_same_pristine_map(self):
        first = patch_micolash_at_gehrman(self.arena, self.donor)
        second = patch_gehrman_at_moon(
            self.arena, FinalAttachmentIds(12104907, 12104908)
        )
        combined = event_blocks(
            compose_event_patches(self.arena, [first, second], [12101800, 12101850])
        )
        original = event_blocks(self.arena)
        self.assertEqual(original[12101800], combined[12101800])
        self.assertEqual(original[12101850], combined[12101850])
        self.assertIn("RequestCharacterAICommand(2100800, -1, 0)", combined[12104802])
        self.assertIn("2100810", combined[12104907])
        self.assertIn("$InitializeEvent(0, 12994100)", combined[0])
        self.assertIn("$InitializeEvent(0, 12104907)", combined[0])

    def test_source_drift_and_colliding_allocations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Micolash donor"):
            patch_micolash_at_gehrman(
                self.arena,
                self.donor.replace(
                    "RequestCharacterAICommand(2600850, 10, 0)",
                    "RequestCharacterAICommand(2600850, 11, 0)",
                ),
            )
        with self.assertRaisesRegex(ValueError, "Gehrman arena"):
            patch_micolash_at_gehrman(
                self.arena.replace("HandleBossDefeat(2100800)", "HandleBossDefeat(1)"),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "collision-free"):
            patch_micolash_at_gehrman(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, phase_marker=DEFAULT_IDS.phase_state),
            )


if __name__ == "__main__":
    unittest.main()
