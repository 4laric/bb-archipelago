import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer import boss_canary
from tools.bb_enemizer.boss_contracts import (
    BSB_ARENA,
    BSB_PACKAGE,
    CLERIC_ARENA,
    PAARL_ARENA,
    PAARL_PACKAGE,
    event_blocks,
    patch_contract_swap,
    plan_contract_shuffle,
    plan_contract_swap,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class ClericArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        files = read_prefix(BUNDLE, "event/")
        cls.cleric = next(value.decode("utf-8-sig") for name, value in files.items()
                          if name.endswith(CLERIC_ARENA.event_file))
        cls.old_yharnam = next(value.decode("utf-8-sig") for name, value in files.items()
                              if name.endswith(PAARL_PACKAGE.event_file))

    def test_bsb_contract_is_byte_for_byte_the_existing_canary(self):
        expected = boss_canary.patch_event_source(self.cleric, self.old_yharnam)
        actual = patch_contract_swap(CLERIC_ARENA, BSB_PACKAGE, self.cleric, self.old_yharnam)
        self.assertEqual(expected, actual)

    def test_paarl_transplants_all_five_declared_part_initializers_and_routine(self):
        before = event_blocks(self.cleric)
        after = event_blocks(patch_contract_swap(CLERIC_ARENA, PAARL_PACKAGE, self.cleric, self.old_yharnam))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual(
            {0, 12411701, 12411702, 12414702, 12414703, 12414704, 12414707, 12414708, 12414710, 12414720},
            changed,
        )
        self.assertEqual(before[CLERIC_ARENA.completion_event], after[CLERIC_ARENA.completion_event])
        self.assertEqual(5, after[0].count("12414710"))
        for binding in PAARL_PACKAGE.part_bindings:
            call = "    $InitializeEvent(" + ", ".join(
                (str(binding.slot), str(CLERIC_ARENA.part_routine_event), *binding.arguments)) + ");"
            self.assertIn(call, after[0])
        # The five Cleric cloth calls remain present in Event(0), while the
        # callee is explicitly disabled for Paarl rather than silently lost.
        self.assertEqual(5, after[0].count("12414720"))
        self.assertIn("function(npcPartId, npcPartId2, npcPartGroupIdx, spEffectId", after[12414710])
        self.assertIn("CreateNPCPart(2410800", after[12414710])
        self.assertNotIn("2300810", after[12414710])
        self.assertIn("HPRatio(2410800) < 0.67", after[12414707])
        self.assertIn("CharacterHasSpEffect(2410800, 5402)", after[12414707])
        self.assertIn("SetCharacterInvincibility(2410800, Enabled)", after[12411702])
        self.assertIn("ForceAnimationPlayback(2410800, 7000, true, false, false)", after[12411702])
        self.assertIn("ForceAnimationPlayback(2410800, 7001, false, false, false)", after[12411702])
        self.assertIn("WaitFixedTimeFrames(70)", after[12411702])
        self.assertIn("SetCharacterInvincibility(2410800, Disabled)", after[12411702])
        self.assertIn("DisplayBossHealthBar(Enabled, 2410800, 0, 508000)", after[12414702])
        self.assertIn("CharacterHasEventMessage(2410800, 20)", after[12414703])
        self.assertIn("SetLockcamSlotNumber(24, 1, 1)", after[12414704])
        self.assertIn("SetLockcamSlotNumber(24, 1, 0)", after[12414704])
        self.assertNotIn("SetLockcamSlotNumber(23, 0,", after[12414704])
        self.assertIn("EventFlag(12414700)", after[12414708])
        self.assertIn("SetEventFlag(12411702, ON)", after[12414708])
        self.assertIn("EndEvent();", after[12414720])
        self.assertIn("function(unused_spEffectId, unused_spEffectId2, unused_bitNumber, unused_bitNumber2)",
                      after[12414720])

    def test_paarl_patch_refuses_source_drift_before_any_rewrite(self):
        with self.assertRaisesRegex(ValueError, "unsupported original donor event 12304715"):
            patch_contract_swap(
                CLERIC_ARENA, PAARL_PACKAGE, self.cleric,
                self.old_yharnam.replace("CreateNPCPart(2300810", "CreateNPCPart(2300811", 1),
            )

    def test_paarl_patch_refuses_arena_constructor_drift(self):
        with self.assertRaisesRegex(ValueError, "unsupported original arena event 0"):
            patch_contract_swap(
                CLERIC_ARENA, PAARL_PACKAGE,
                self.cleric.replace("$InitializeEvent(0, 12414710", "$InitializeEvent(9, 12414710", 1),
                self.old_yharnam,
            )

    def test_paarl_at_bsb_uses_bsb_progression_and_replaces_its_single_limb_constructor(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(BSB_ARENA, PAARL_PACKAGE, self.old_yharnam, self.old_yharnam))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12301802, 12301803, 12304802, 12304803, 12304804, 12304807, 12304808}, changed)
        self.assertEqual(before[12301800], after[12301800])
        self.assertEqual(5, after[0].count("12304808"))
        self.assertIn("SetCharacterInvincibility(2300800, Enabled)", after[12301802])
        self.assertIn("ForceAnimationPlayback(2300800, 7000, true, false, false)", after[12301802])
        self.assertIn("WaitFixedTimeFrames(70)", after[12301802])
        self.assertIn("EventFlag(12304800)", after[12301803])
        self.assertIn("SetEventFlag(12301802, ON)", after[12301803])
        self.assertIn("DisplayBossHealthBar(Enabled, 2300800, 0, 508000)", after[12304802])
        self.assertIn("CharacterHasEventMessage(2300800, 20)", after[12304803])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304804])
        self.assertIn("HPRatio(2300800) < 0.67", after[12304807])
        self.assertIn("function(npcPartId, npcPartId2, npcPartGroupIdx, spEffectId", after[12304808])

    def test_bsb_at_paarl_preserves_paarl_progression_and_restores_one_phase_two_initializer(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(PAARL_ARENA, BSB_PACKAGE, self.old_yharnam, self.old_yharnam))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12301702, 12301703, 12304702, 12304703, 12304704, 12304707, 12304715}, changed)
        self.assertEqual(before[12301700], after[12301700])
        self.assertEqual(1, after[0].count("$InitializeEvent(0, 12304715);"))
        self.assertNotIn("SetCharacterInvincibility(2300810", after[12301702])
        self.assertNotIn("ForceAnimationPlayback(2300810, 7000", after[12301702])
        self.assertIn("ForceAnimationPlayback(2300810, 7001", after[12301702])
        self.assertIn("DisplayBossHealthBar(Enabled, 2300810, 0, 209000)", after[12304702])
        self.assertIn("EventFlag(12304715)", after[12304703])
        self.assertIn("EventFlag(12304700)", after[12301703])
        self.assertIn("SetEventFlag(12301702, ON)", after[12301703])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304704])
        self.assertIn("HPRatio(2300810) < 0.67", after[12304707])
        self.assertIn("HPRatio(2300810) < 0.33 && EventFlag(12304707)", after[12304715])


class ContractPlanningTests(unittest.TestCase):
    def test_seeded_selection_is_independent_and_metadata_names_only_typed_remaps(self):
        first = plan_contract_shuffle("archipelago", packages=(PAARL_PACKAGE,))
        second = plan_contract_shuffle("archipelago", packages=(PAARL_PACKAGE,))
        self.assertEqual(first, second)
        self.assertEqual("darkbeast-paarl", first["donor"])
        self.assertEqual("planned", first["status"])
        self.assertEqual("not_written", first["writer_status"])
        self.assertEqual({"actor", "completion_event", "encounter_start_flag", "phase_events", "co_op_entry_event", "part_routine"},
                         set(first["remap"]))
        self.assertEqual(508000, first["health_bar"]["label"])
        self.assertEqual(5, len(first["part_initializers"]))

    def test_paarl_contract_emits_the_existing_native_map_and_scaling_plan_shape(self):
        with tempfile.TemporaryDirectory() as temp:
            inventory = Path(temp) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(inventory)
        npcs, effects = load_params(BUNDLE)
        plan = plan_contract_swap(CLERIC_ARENA, PAARL_PACKAGE, slots, npcs, effects, "archipelago")
        self.assertEqual("bb-enemizer-plan-v2", plan["format"])
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5080", plan["swaps"][0]["target"]["model_name"])
        self.assertFalse(plan["scaling"]["enabled"])
        self.assertEqual(1, plan["scaling"]["skip_count"])
        self.assertIn("unknown source or destination tier", plan["scaling"]["skips"][0]["reason"])
        self.assertEqual("darkbeast-paarl", plan["boss_contract"]["donor"])


if __name__ == "__main__":
    unittest.main()
