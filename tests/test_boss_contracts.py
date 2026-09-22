import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer import boss_canary, boss_contracts
from tools.bb_enemizer.boss_contracts import (
    AMELIA_ARENA,
    AMELIA_PACKAGE,
    AMYGDALA_ARENA,
    AMYGDALA_PACKAGE,
    actor_addition_requirements,
    BSB_ARENA,
    BSB_PACKAGE,
    CLERIC_ARENA,
    CLERIC_PACKAGE,
    EBRIETAS_ARENA,
    EBRIETAS_PACKAGE,
    COMPATIBILITY,
    PACKAGES,
    PAARL_ARENA,
    PAARL_PACKAGE,
    event_blocks,
    patch_contract_swap,
    plan_contract_shuffle,
    plan_contract_swap,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.boss_pool import assign_donors
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
        cls.amelia = next(value.decode("utf-8-sig") for name, value in files.items()
                              if name.endswith(AMELIA_PACKAGE.event_file))
        cls.amygdala = next(value.decode("utf-8-sig") for name, value in files.items()
                                if name.endswith(AMYGDALA_PACKAGE.event_file))
        cls.ebrietas = next(value.decode("utf-8-sig") for name, value in files.items()
                                if name.endswith(EBRIETAS_PACKAGE.event_file))

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

    def test_cleric_at_bsb_attaches_all_source_routines_without_changing_completion(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(BSB_ARENA, CLERIC_PACKAGE, self.old_yharnam, self.cleric))
        self.assertEqual([12304907, 12304908, 12304910, 12304920],
                         sorted(set(after) - set(before)))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12301802, 12304802, 12304803, 12304804, 12304807, 12304808}, changed)
        self.assertEqual(before[12301800], after[12301800])
        self.assertIn("ForceAnimationPlayback(2300800, 3028", after[12301802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2300800, 0, 500000)", after[12304802])
        self.assertIn("CharacterHasEventMessage(2300800, 100)", after[12304803])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304804])
        self.assertIn("HPRatio(2300800) < 0.7", after[12304907])
        self.assertIn("ChangeCharactersCloth(2300800, 15, 2)", after[12304908])
        self.assertEqual(5, after[0].count("12304910"))
        self.assertEqual(5, after[0].count("12304920"))
        self.assertEqual("$Event(12304808, Default, function() {\n    EndEvent();\n});", after[12304808])

    def test_cleric_at_paarl_uses_disjoint_attachment_ids_and_keeps_paarl_completion(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(PAARL_ARENA, CLERIC_PACKAGE, self.old_yharnam, self.cleric))
        self.assertEqual([12304917, 12304918, 12304919, 12304921],
                         sorted(set(after) - set(before)))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12301702, 12304702, 12304703, 12304704, 12304707, 12304715}, changed)
        self.assertEqual(before[12301700], after[12301700])
        self.assertIn("ForceAnimationPlayback(2300810, 3028", after[12301702])
        self.assertNotIn("SetCharacterInvincibility(2300810", after[12301702])
        self.assertIn("CharacterHasEventMessage(2300810, 100)", after[12304703])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304704])
        self.assertIn("CreateNPCPart(2300810", after[12304919])
        self.assertEqual(5, after[0].count("12304919"))
        self.assertEqual(5, after[0].count("12304921"))

    def test_cleric_attachment_rejects_an_id_used_as_an_original_flag_operand(self):
        drifted = self.old_yharnam.replace(
            "    $InitializeEvent(0, 12304808);",
            "    $InitializeEvent(0, 12304808);\n    SetEventFlag(12304907, OFF);",
            1,
        )
        expected = dict(BSB_ARENA.expected)
        expected[0] = hashlib.sha256(event_blocks(drifted)[0].encode("utf-8")).hexdigest()
        with self.assertRaisesRegex(ValueError, "12304907 collides with original arena literal"):
            patch_contract_swap(replace(BSB_ARENA, expected=expected), CLERIC_PACKAGE, drifted, self.cleric)

    def test_attachment_can_append_witnessed_initializers_when_an_arena_declares_no_anchor(self):
        append_only = replace(BSB_ARENA, attachment_anchor_slot=None, attachment_anchor_event=None)
        after = event_blocks(patch_contract_swap(append_only, CLERIC_PACKAGE,
                                                 self.old_yharnam, self.cleric))
        self.assertIn("    $InitializeEvent(0, 12304808);", after[0])
        self.assertEqual(5, after[0].count("12304910"))
        self.assertEqual(5, after[0].count("12304920"))
        self.assertTrue(after[0].endswith("    $InitializeEvent(4, 12304920, 484, 494, 9, 14);\n});"))

    def test_ebrietas_virtual_bullet_owner_is_witnessed_and_remapped_only_in_attached_events(self):
        donor_blocks = event_blocks(self.ebrietas)
        targets = boss_contracts._attachment_targets(BSB_ARENA, EBRIETAS_PACKAGE, self.old_yharnam)
        virtual = boss_contracts._virtual_entity_targets(BSB_ARENA, EBRIETAS_PACKAGE, self.old_yharnam)
        constructor = boss_contracts._attach_initializers(
            event_blocks(self.old_yharnam)[0], BSB_ARENA, EBRIETAS_PACKAGE,
            targets, virtual, donor_blocks[0])
        attached = event_blocks(boss_contracts._append_attachment_events(
            self.old_yharnam, donor_blocks, EBRIETAS_PACKAGE, BSB_ARENA, targets, virtual))
        self.assertIn("CreateBulletOwner(2300890);", constructor)
        self.assertNotIn("CreateBulletOwner(2420801);", constructor)
        bullet_event = attached[targets[12424990]]
        self.assertIn("ShootBullet(2300890, 2300800, 6, 225100310", bullet_event)
        self.assertNotIn("2420801", bullet_event)
        # The phase event's source start flag is remapped explicitly, rather
        # than through a broad m24->m23 numeric replacement.
        self.assertIn("EventFlag(12304800)", attached[targets[12424980]])

    def test_ebrietas_at_paarl_requires_and_uses_a_pinned_helper_actor_addition(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(
            PAARL_ARENA, EBRIETAS_PACKAGE, self.old_yharnam, self.ebrietas,
            allow_materialized_actor_additions=True))
        self.assertEqual([12304917, 12304918, 12304919, 12304921],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[12301700], after[12301700])
        self.assertIn("ForceAnimationPlayback(2300810, 7001, true", after[12301702])
        self.assertIn("SetCharacterImmortality(2300810, Enabled)", after[12301702])
        self.assertIn("SetSpEffect(2300810, 5647, false)", after[12301702])
        self.assertIn("ForceAnimationPlayback(2300810, 7000, false, true", after[12301702])
        self.assertIn("CreateBulletOwner(2300891);", after[0])
        self.assertIn("ShootBullet(2300891, 2300810, 6, 225100310", after[12304918])
        self.assertIn("EventFlag(12304700)", after[12304917])

    def test_amelia_uses_the_reusable_attachment_path_with_its_heal_choreography(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(BSB_ARENA, AMELIA_PACKAGE, self.old_yharnam, self.amelia))
        self.assertEqual([12304907, 12304908, 12304910, 12304920, 12304930],
                         sorted(set(after) - set(before)))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12304802, 12304803, 12304804, 12304807, 12304808}, changed)
        self.assertEqual(before[12301800], after[12301800])
        self.assertIn("DisplayBossHealthBar(Enabled, 2300800, 0, 502000)", after[12304802])
        self.assertIn("CharacterHasEventMessage(2300800, 100)", after[12304803])
        self.assertIn("SetLockcamSlotNumber(23, 0, 1)", after[12304804])
        self.assertIn("HPRatio(2300800) < 0.5", after[12304907])
        self.assertIn("WaitFor(CharacterHasSpEffect(2300800, 2150)", after[12304930])
        self.assertEqual(5, after[0].count("12304910"))
        self.assertEqual(5, after[0].count("12304920"))

    def test_amelia_at_paarl_has_a_disjoint_five_event_attachment_set(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(PAARL_ARENA, AMELIA_PACKAGE, self.old_yharnam, self.amelia))
        self.assertEqual([12304917, 12304918, 12304919, 12304921, 12304922],
                         sorted(set(after) - set(before)))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12301702, 12304702, 12304703, 12304704, 12304707, 12304715}, changed)
        self.assertEqual(before[12301700], after[12301700])
        self.assertNotIn("SetCharacterInvincibility(2300810", after[12301702])
        self.assertIn("CreateNPCPart(2300810", after[12304919])
        self.assertIn("ForceAnimationPlayback(2300810, 3035", after[12304922])

    def test_cleric_at_amelia_keeps_amelia_cutscene_terminal_and_attaches_four_routines(self):
        before = event_blocks(self.amelia)
        after = event_blocks(patch_contract_swap(AMELIA_ARENA, CLERIC_PACKAGE, self.amelia, self.cleric))
        self.assertEqual([12404907, 12404908, 12404910, 12404920],
                         sorted(set(after) - set(before)))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({0, 12401802, 12404802, 12404807, 12404808, 12404810, 12404820}, changed)
        self.assertEqual(before[12401800], after[12401800])
        self.assertEqual(before[12401803], after[12401803])
        self.assertIn("ForceAnimationPlayback(2400800, 3028", after[12401802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2400800, 0, 500000)", after[12404802])
        self.assertIn("SetLockcamSlotNumber(24, 0, 1)", after[12404804])
        self.assertIn("CreateNPCPart(2400800", after[12404910])
        self.assertEqual(5, after[0].count("12404910"))
        self.assertEqual(5, after[0].count("12404920"))

    def test_amygdala_at_paarl_copies_all_ten_limb_initializers_and_native_entry_sequence(self):
        before = event_blocks(self.old_yharnam)
        after = event_blocks(patch_contract_swap(PAARL_ARENA, AMYGDALA_PACKAGE,
                                                 self.old_yharnam, self.amygdala))
        self.assertEqual([12304917, 12304918, 12304919, 12304921, 12304922],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[12301700], after[12301700])
        self.assertIn("ForceAnimationPlayback(2300810, 7003, true", after[12301702])
        self.assertIn("ForceAnimationPlayback(2300810, 7006, false", after[12301702])
        self.assertIn("ForceAnimationPlayback(2300810, 7002, false", after[12301702])
        self.assertIn("WaitFixedTimeFrames(160)", after[12301702])
        self.assertIn("DisplayBossHealthBar(Enabled, 2300810, 0, 512000)", after[12304702])
        self.assertIn("CharacterHasEventMessage(2300810, 10)", after[12304703])
        self.assertIn("EventFlag(12304917)", after[12304918])
        self.assertEqual(10, after[0].count("12304921"))
        self.assertEqual(2, after[0].count("12304919"))

    def test_amelia_at_amygdala_preserves_amygdala_terminal_and_replaces_only_entry_model_actions(self):
        before = event_blocks(self.amygdala)
        after = event_blocks(patch_contract_swap(AMYGDALA_ARENA, AMELIA_PACKAGE,
                                                 self.amygdala, self.amelia))
        self.assertEqual([13304907, 13304908, 13304920, 13304930, 13304940],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[13301800], after[13301800])
        self.assertIn("InArea(10000, 3302805)", after[13301802])
        self.assertIn("ForceAnimationPlayback(3300800, 7001", after[13301802])
        self.assertNotIn("ForceAnimationPlayback(3300800, 7003", after[13301802])
        self.assertIn("DisplayBossHealthBar(Enabled, 3300800, 0, 502000)", after[13304802])
        self.assertIn("CharacterHasEventMessage(3300800, 100)", after[13304803])
        self.assertIn("SetLockcamSlotNumber(33, 0, 1)", after[13304804])
        self.assertEqual(5, after[0].count("13304930"))

    def test_cleric_at_amygdala_uses_the_generic_attachment_adapter_without_touching_terminal(self):
        before = event_blocks(self.amygdala)
        after = event_blocks(patch_contract_swap(AMYGDALA_ARENA, CLERIC_PACKAGE,
                                                 self.amygdala, self.cleric))
        self.assertEqual([13304907, 13304908, 13304920, 13304930],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[13301800], after[13301800])
        self.assertIn("InArea(10000, 3302805)", after[13301802])
        self.assertIn("ForceAnimationPlayback(3300800, 3028", after[13301802])
        self.assertNotIn("ForceAnimationPlayback(3300800, 7003", after[13301802])
        self.assertIn("DisplayBossHealthBar(Enabled, 3300800, 0, 500000)", after[13304802])
        self.assertIn("CharacterHasEventMessage(3300800, 100)", after[13304803])
        self.assertIn("SetLockcamSlotNumber(33, 0, 1)", after[13304804])
        self.assertIn("HPRatio(3300800) < 0.7", after[13304907])
        self.assertEqual(5, after[0].count("13304930"))
        self.assertEqual(5, after[0].count("13304920"))

    def test_amygdala_at_ebrietas_preserves_ebrietas_terminal_and_damage_trigger(self):
        before = event_blocks(self.ebrietas)
        after = event_blocks(patch_contract_swap(EBRIETAS_ARENA, AMYGDALA_PACKAGE,
                                                 self.ebrietas, self.amygdala))
        self.assertEqual([12424907, 12424908, 12424920, 12424930, 12424940],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[12421800], after[12421800])
        self.assertIn("HasDamageType(2420800, 10000, DamageType.Unspecified)", after[12421802])
        self.assertIn("ForceAnimationPlayback(2420800, 7003, true", after[12421802])
        self.assertIn("ForceAnimationPlayback(2420800, 7006, false", after[12421802])
        self.assertIn("ForceAnimationPlayback(2420800, 7002, false", after[12421802])
        self.assertNotIn("SetCharacterImmortality(2420800", after[12421802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2420800, 0, 512000)", after[12424802])
        self.assertIn("CharacterHasEventMessage(2420800, 10)", after[12424803])
        self.assertIn("SetLockcamSlotNumber(24, 2, 1)", after[12424804])
        self.assertIn("HPRatio(2420800) < 0.7", after[12424907])
        self.assertEqual(10, after[0].count("12424930"))
        self.assertEqual(2, after[0].count("12424920"))

    def test_cleric_at_ebrietas_preserves_damage_entry_and_replaces_only_ebrietas_state(self):
        before = event_blocks(self.ebrietas)
        after = event_blocks(patch_contract_swap(EBRIETAS_ARENA, CLERIC_PACKAGE,
                                                 self.ebrietas, self.cleric))
        self.assertEqual([12424907, 12424908, 12424920, 12424930],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[12421800], after[12421800])
        self.assertIn("HasDamageType(2420800, 10000, DamageType.Unspecified)", after[12421802])
        self.assertIn("ForceAnimationPlayback(2420800, 3028", after[12421802])
        self.assertNotIn("SetCharacterImmortality(2420800", after[12421802])
        self.assertNotIn("SetSpEffect(2420800, 5647", after[12421802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2420800, 0, 500000)", after[12424802])
        self.assertIn("SetLockcamSlotNumber(24, 2, 1)", after[12424804])
        self.assertEqual(5, after[0].count("12424930"))
        self.assertEqual(5, after[0].count("12424920"))

    def test_bsb_at_ebrietas_reuses_two_declared_phase_slots_and_keeps_ebrietas_fog_camera(self):
        before = event_blocks(self.ebrietas)
        after = event_blocks(patch_contract_swap(EBRIETAS_ARENA, BSB_PACKAGE,
                                                 self.ebrietas, self.old_yharnam))
        changed = {event_id for event_id in before if before[event_id] != after[event_id]}
        self.assertEqual({12421802, 12424802, 12424803, 12424870, 12424871, 12424980, 12424990},
                         changed)
        self.assertEqual(before[12421800], after[12421800])
        self.assertIn("HasDamageType(2420800, 10000, DamageType.Unspecified)", after[12421802])
        self.assertIn("ForceAnimationPlayback(2420800, 7001, false", after[12421802])
        self.assertNotIn("SetCharacterImmortality(2420800", after[12421802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2420800, 0, 209000)", after[12424802])
        self.assertIn("CharacterHasEventMessage(2420800, 20)", after[12424803])
        self.assertIn("SetLockcamSlotNumber(24, 2, 1)", after[12424804])
        self.assertIn("SetLockcamSlotNumber(24, 2, 0)", after[12424804])
        self.assertIn("HPRatio(2420800) < 0.67", after[12424980])
        self.assertIn("HPRatio(2420800) < 0.33 && EventFlag(12424980)", after[12424990])
        self.assertNotIn("ShootBullet", after[12424990])
        self.assertIn("function(unused_npcPartId, unused_npcPartId2", after[12424870])
        self.assertIn("function(unused_npcPartId, unused_npcPartId2", after[12424871])

    def test_amygdala_at_amelia_retains_cutscene_and_uses_native_wake_up_sequence(self):
        before = event_blocks(self.amelia)
        after = event_blocks(patch_contract_swap(AMELIA_ARENA, AMYGDALA_PACKAGE,
                                                 self.amelia, self.amygdala))
        self.assertEqual([12404907, 12404908, 12404910, 12404920, 12404930],
                         sorted(set(after) - set(before)))
        self.assertEqual(before[12401800], after[12401800])
        self.assertIn("PlayCutsceneToPlayer(24000060", after[12401802])
        self.assertIn("ForceAnimationPlayback(2400800, 7003, true", after[12401802])
        self.assertIn("ForceAnimationPlayback(2400800, 7006, false", after[12401802])
        self.assertIn("ForceAnimationPlayback(2400800, 7002, false", after[12401802])
        self.assertNotIn("ForceAnimationPlayback(2400800, 7000", after[12401802])
        self.assertIn("DisplayBossHealthBar(Enabled, 2400800, 0, 512000)", after[12404802])
        self.assertIn("CharacterHasEventMessage(2400800, 10)", after[12404803])
        self.assertIn("SetLockcamSlotNumber(24, 0, 1)", after[12404804])
        self.assertEqual(10, after[0].count("12404920"))
        self.assertEqual(2, after[0].count("12404910"))
        self.assertEqual(1, after[0].count("12404930"))


class ContractPlanningTests(unittest.TestCase):
    def test_seeded_selection_is_independent_and_metadata_names_only_typed_remaps(self):
        first = plan_contract_shuffle("archipelago", packages=(PAARL_PACKAGE,))
        second = plan_contract_shuffle("archipelago", packages=(PAARL_PACKAGE,))
        self.assertEqual(first, second)
        self.assertEqual("darkbeast-paarl", first["donor"])
        self.assertEqual("planned", first["status"])
        self.assertEqual("not_written", first["writer_status"])
        self.assertEqual({"actor", "completion_event", "encounter_start_flag", "phase_events", "co_op_entry_event", "part_routine", "added_events", "virtual_entities"},
                         set(first["remap"]))
        self.assertEqual(508000, first["health_bar"]["label"])
        self.assertEqual(5, len(first["part_initializers"]))

    def test_reviewed_registry_exposes_the_six_package_compatible_pool(self):
        self.assertEqual({"blood-starved-beast", "darkbeast-paarl", "cleric-beast", "vicar-amelia", "amygdala", "ebrietas"},
                         {package.key for package in PACKAGES})
        self.assertEqual(("darkbeast-paarl", "cleric-beast", "vicar-amelia"),
                         COMPATIBILITY[BSB_ARENA.key])
        self.assertEqual(("blood-starved-beast", "cleric-beast", "vicar-amelia", "amygdala", "ebrietas"),
                         COMPATIBILITY[PAARL_ARENA.key])
        self.assertEqual(("cleric-beast", "amygdala"), COMPATIBILITY[AMELIA_ARENA.key])
        self.assertEqual(("vicar-amelia", "cleric-beast"), COMPATIBILITY[AMYGDALA_ARENA.key])
        self.assertEqual(("amygdala", "cleric-beast", "blood-starved-beast"),
                         COMPATIBILITY[EBRIETAS_ARENA.key])

    def test_attached_plan_maps_only_declared_source_events(self):
        plan = plan_contract_shuffle("cleric", BSB_ARENA, (CLERIC_PACKAGE,))
        self.assertEqual("cleric-beast", plan["donor"])
        self.assertEqual({"12414707": 12304907, "12414708": 12304908,
                          "12414710": 12304910, "12414720": 12304920},
                         plan["remap"]["added_events"])
        self.assertEqual({"12414707": 12304907, "12414708": 12304908},
                         plan["remap"]["phase_events"])
        self.assertEqual(4, len(plan["attachments"]))

    def test_amelia_plan_declares_the_extra_heal_choreography_event(self):
        plan = plan_contract_shuffle("amelia", BSB_ARENA, (AMELIA_PACKAGE,))
        self.assertEqual({"12404807": 12304907, "12404808": 12304908,
                          "12404810": 12304910, "12404820": 12304920,
                          "12404830": 12304930}, plan["remap"]["added_events"])
        self.assertEqual(5, len(plan["attachments"]))

    def test_ebrietas_plan_declares_the_virtual_bullet_owner_without_registering_an_unsafe_pair(self):
        plan = plan_contract_shuffle("ebrietas", BSB_ARENA, (EBRIETAS_PACKAGE,))
        self.assertEqual({"2420801": 2300890}, plan["remap"]["virtual_entities"])
        self.assertEqual([{"source_entity": 2420801, "destination_entity": 2300890,
                           "initializer": "CreateBulletOwner", "requires_actor_addition": True}],
                         plan["virtual_entities"])
        self.assertNotIn("ebrietas", COMPATIBILITY[BSB_ARENA.key])
        files = read_prefix(BUNDLE, "event/")
        old_yharnam = next(value.decode("utf-8-sig") for name, value in files.items()
                           if name.endswith(BSB_ARENA.event_file))
        ebrietas = next(value.decode("utf-8-sig") for name, value in files.items()
                        if name.endswith(EBRIETAS_PACKAGE.event_file))
        with self.assertRaisesRegex(ValueError, "requires a materialized actor addition"):
            patch_contract_swap(BSB_ARENA, EBRIETAS_PACKAGE, old_yharnam, ebrietas)

    def test_ebrietas_actor_requirements_pair_exact_source_and_destination_map_states(self):
        with tempfile.TemporaryDirectory() as temp:
            inventory = Path(temp) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            slots = load_slots(inventory)
        requirements = actor_addition_requirements(PAARL_ARENA, EBRIETAS_PACKAGE, slots)
        self.assertEqual(2, len(requirements))
        self.assertEqual({"m24_02_00_00", "m24_02_00_01"},
                         {row["source_map"] for row in requirements})
        self.assertEqual({"m23_00_00_00", "m23_00_00_01"},
                         {row["destination_map"] for row in requirements})
        for row in requirements:
            self.assertEqual("c9010_0003", row["source_part"])
            self.assertEqual("c2510_0000", row["source_anchor_part"])
            self.assertEqual({"model_name": "c9010", "npc_param_id": 251001,
                              "think_param_id": 1, "chara_init_id": 0}, row["source_archetype"])
            self.assertEqual("c5080_0000", row["destination_anchor_part"])
            self.assertEqual("ap_ebrietas_bullet_owner", row["destination_part"])
            self.assertEqual(2300891, row["destination_entity_id"])
        npcs, effects = load_params(BUNDLE)
        plan = plan_contract_swap(PAARL_ARENA, EBRIETAS_PACKAGE, slots, npcs, effects, "ebrietas")
        self.assertNotIn("boss_actor_additions", plan)
        self.assertEqual(requirements, plan["boss_actor_addition_requirements"])
        self.assertEqual({"2420801": 2300891}, plan["boss_contract"]["remap"]["virtual_entities"])

    def test_six_package_registry_is_closed_and_seeds_select_two_reviewed_matchings(self):
        first = assign_donors("seed-0", COMPATIBILITY)
        second = assign_donors("seed-1", COMPATIBILITY)
        for assignment in (first, second):
            self.assertEqual(set(COMPATIBILITY), set(assignment))
            self.assertEqual(set(COMPATIBILITY), set(assignment.values()))
        self.assertNotEqual(first, second)
        self.assertEqual("blood-starved-beast", first[EBRIETAS_ARENA.key])
        self.assertEqual("cleric-beast", second[EBRIETAS_ARENA.key])
        self.assertEqual("amygdala", first[AMELIA_ARENA.key])
        self.assertEqual("amygdala", second[AMELIA_ARENA.key])

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
