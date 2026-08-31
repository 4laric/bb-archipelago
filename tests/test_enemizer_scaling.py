import hashlib
import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools.bb_enemizer.cli import main as enemizer_main
from tools.bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
)
from tools.bb_enemizer.planner import EnemizerConfig, plan_swaps
from tools.bb_enemizer.scaling import (
    MAX_MULTIPLIER, MIN_MULTIPLIER, NPC_CLONE_END, NPC_CLONE_START,
    SPEFFECT_END, SPEFFECT_START, derive_ladder, free_effect_slot, load_params,
    plan_scaling, MAP_LEVELS,
)


ROOT = Path(__file__).resolve().parents[1]


class StaticScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.npcs, cls.effects = load_params(ROOT / "research/bb_inputs.db")
        cls.slots = load_slots(ROOT / "research/mined/msb_enemies.tsv")
        tags = load_tags(ROOT / "research/enemizer/enemy_tags.json")
        overrides = load_slot_overrides(ROOT / "research/enemizer/slot_policy.json")
        policies = {
            slot.key: apply_archetype_tag(
                classify_slot(slot, overrides), tags.get(slot.archetype.key)
            )
            for slot in cls.slots
        }
        cls.swaps, _ = plan_swaps(
            cls.slots, policies, tags, EnemizerConfig("scaling-fixture")
        )

    def test_native_ladder_is_regenerated_with_pinned_invariants(self):
        ladder = derive_ladder(self.effects)
        self.assertEqual(13, len(ladder))
        self.assertAlmostEqual(8.735, ladder[1].max_hp_rate)
        self.assertAlmostEqual(1.340, ladder[13].max_hp_rate)
        self.assertAlmostEqual(2.555, ladder[1].attack_rate)
        self.assertAlmostEqual(1.016, ladder[13].defense_rate)
        self.assertTrue(all("周回パワーアップ" in rung.source_name
                            for rung in ladder.values()))
        with (ROOT / "research/enemizer/scaling_ladder.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            committed = {int(row["level"]): row for row in csv.DictReader(handle, delimiter="\t")}
        self.assertEqual(set(ladder), set(committed))
        for level, rung in ladder.items():
            self.assertEqual(rung.source_id, int(committed[level]["sp_effect_id"]))
            self.assertAlmostEqual(rung.max_hp_rate, float(committed[level]["max_hp_rate"]))
            self.assertAlmostEqual(rung.attack_rate, float(committed[level]["physical_attack_rate"]))
            self.assertAlmostEqual(rung.defense_rate, float(committed[level]["physical_defense_rate"]))

    def test_committed_map_oracle_matches_code(self):
        with (ROOT / "research/enemizer/scaling_map_tiers.tsv").open(
            encoding="utf-8", newline=""
        ) as handle:
            committed = {row["map"]: int(row["level"])
                         for row in csv.DictReader(handle, delimiter="\t")}
        self.assertEqual(MAP_LEVELS, committed)

    def test_claimed_ranges_are_empty_in_the_bundle(self):
        self.assertFalse(set(self.npcs) & set(range(NPC_CLONE_START, NPC_CLONE_END + 1)))
        self.assertFalse(set(self.effects) & set(range(SPEFFECT_START, SPEFFECT_END + 1)))

    def test_exactly_58_npc_rows_have_no_free_effect_slot(self):
        blocked = [row for row in self.npcs.values() if free_effect_slot(row) is None]
        self.assertEqual(58, len(blocked))

    def test_scaling_plan_is_deterministic_and_order_independent(self):
        first, first_skips = plan_scaling(self.swaps, self.slots, self.npcs, self.effects)
        second, second_skips = plan_scaling(
            list(reversed(self.swaps)), list(reversed(self.slots)), self.npcs, self.effects
        )
        self.assertEqual(first, second)
        self.assertEqual(first_skips, second_skips)
        self.assertTrue(first)
        self.assertTrue(first_skips)
        fixture = json.loads(
            (ROOT / "research/enemizer/scaling_fixture.json").read_text(encoding="utf-8")
        )
        payload = {
            "enabled": True,
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(first),
            "skip_count": len(first_skips),
            "changes": [change.json() for change in first],
            "skips": first_skips,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        self.assertEqual(fixture["swap_count"], len(self.swaps))
        self.assertEqual(fixture["change_count"], len(first))
        self.assertEqual(fixture["skip_count"], len(first_skips))
        self.assertEqual(fixture["scaling_sha256"], digest)
        for change in first:
            self.assertEqual(1.0, change.have_soul_rate)
            self.assertGreaterEqual(change.hp_multiplier, MIN_MULTIPLIER)
            self.assertLessEqual(change.hp_multiplier, MAX_MULTIPLIER)
            self.assertGreaterEqual(change.attack_multiplier, MIN_MULTIPLIER)
            self.assertLessEqual(change.attack_multiplier, MAX_MULTIPLIER)
            self.assertGreaterEqual(change.defense_multiplier, MIN_MULTIPLIER)
            self.assertLessEqual(change.defense_multiplier, MAX_MULTIPLIER)

    def test_clone_contract_preserves_reward_fields_by_copying_the_source_row(self):
        changes, _ = plan_scaling(self.swaps, self.slots, self.npcs, self.effects)
        reward_fields = ("getSoul", "itemLotId_1", "itemLotId_2", "itemLotId_3",
                         "itemLotId_4", "itemLotId_5", "itemLotId_6",
                         "GameClearSpEffectID")
        for change in changes:
            source = self.npcs[change.source_npc_param_id]
            clone = dict(source)
            clone[change.sp_effect_slot] = str(change.minted_sp_effect_id)
            self.assertEqual(
                tuple(source[field] for field in reward_fields),
                tuple(clone[field] for field in reward_fields),
            )

    def test_cli_scaling_is_disabled_unless_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            default_path = Path(directory) / "default.json"
            enabled_path = Path(directory) / "enabled.json"
            self.assertEqual(0, enemizer_main([
                "--seed", "scaling-fixture", "--output", str(default_path),
            ]))
            self.assertEqual(0, enemizer_main([
                "--seed", "scaling-fixture", "--output", str(enabled_path),
                "--normalize-scaling",
            ]))
            default = json.loads(default_path.read_text(encoding="utf-8"))
            enabled = json.loads(enabled_path.read_text(encoding="utf-8"))
            self.assertFalse(default["scaling"]["enabled"])
            self.assertEqual([], default["scaling"]["changes"])
            self.assertTrue(enabled["scaling"]["enabled"])
            self.assertEqual(237, enabled["scaling"]["change_count"])


if __name__ == "__main__":
    unittest.main()
