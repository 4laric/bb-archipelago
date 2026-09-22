import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.orphan_contract import (
    BUNDLE, CLERIC_EVENT_SOURCE, ORPHAN_EVENT_SOURCE, NativeActorPin, OrphanIds, ORPHAN_CORE,
    ORPHAN_PHASE, ORPHAN_SUPPORT, PROJECT_PHASE_ENTITY, PROJECT_SUPPORT_ENTITY,
    construction_request, native_plan_orphan_at_cleric, patch_orphan_at_cleric,
)
from tools.bb_enemizer.scaling import load_params


class OrphanContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.cleric = read_blob(BUNDLE, CLERIC_EVENT_SOURCE).decode("utf-8-sig")
        cls.orphan = read_blob(BUNDLE, ORPHAN_EVENT_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        cls.installed_orphan = cls.orphan.replace(
            "    $InitializeEvent(1, 13605900, 13605951, 13605961, 13605971, 3602910, 3602911, 0);\n"
            "    $InitializeEvent(2, 13605900, 13605952, 13605962, 13605972, 3602920, 0, 0);",
            "    $InitializeEvent(1, 13605900, 13605951, 13605961, 13605971, 3602910, 3602911, 6001);\n"
            "    $InitializeEvent(2, 13605900, 13605952, 13605962, 13605972, 3602920, 0, 6001);").replace(
            "                && EntityInRadiusOfEntity(10000, 3600800, 24));\n",
            "                && (EntityInRadiusOfEntity(10000, 3600800, 24)\n"
            "                    || HasDamageType(3600800, -1, DamageType.Unspecified)));\n").replace(
            "        SetNetworkUpdateRate(3600801, true, CharacterUpdateFrequency.NoUpdate);",
            "        SetNetworkUpdateRate(3600801, true, CharacterUpdateFrequency.AlwaysUpdate);")

    def ids(self, **changes):
        values = dict(phase_entity_id=PROJECT_PHASE_ENTITY, support_entity_id=PROJECT_SUPPORT_ENTITY,
                      combat_ready_flag=12990600, phase_event_id=12990601, support_event_id=12990602,
                      player_effect_event_id=12990603, phase_camera_event_id=12990604,
                      terminal_bridge_event_id=12990605,
                      phase_destination_part="ap_orphan_phase", support_destination_part="ap_orphan_support",
                      evidence="test-owned project IDs checked against the bundled corpus")
        values.update(changes)
        return OrphanIds(**values)

    def pins(self, **changes):
        values = dict(part_sha256="a" * 64, anchor_sha256="b" * 64,
                      talk_id=0, unk_t18=0, init_anim_id=0, damage_anim_id=0)
        values.update(changes)
        pin = NativeActorPin(**values)
        return {"core": pin, "phase": pin, "support": pin}

    def test_request_binds_exact_three_actor_roster_and_destination_states(self):
        request = construction_request(self.slots, self.ids(), self.pins())
        self.assertEqual(6, len(request.actor_additions))
        self.assertEqual({"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"},
                         {row["destination_map"] for row in request.actor_additions})
        self.assertEqual({ORPHAN_PHASE, ORPHAN_SUPPORT}, {row["source_entity_id"] for row in request.actor_additions})
        self.assertEqual({"c4540_0000"}, {row["source_anchor_part"] for row in request.actor_additions})
        self.assertEqual({PROJECT_PHASE_ENTITY, PROJECT_SUPPORT_ENTITY},
                         {row["destination_entity_id"] for row in request.actor_additions})
        self.assertEqual({13604802, 13604803, 13604804},
                         {row["source_event_id"] for row in request.changed_events})
        self.assertEqual({13604820, 13604830, 13604840, 13604850},
                         {row["source_event_id"] for row in request.added_events if row["source_event_id"] is not None})
        self.assertEqual({ORPHAN_CORE}, {row["source_entity_id"] for row in request.primary_initialization})
        primary_provenance = request.primary_initialization[0]["source_provenance"]
        self.assertEqual(
            {"format": "bb-boss-actor-pin-v1", "part_sha256": "a" * 64},
            primary_provenance,
        )
        for addition in request.actor_additions:
            self.assertEqual("b" * 64, addition["source_provenance"]["anchor_sha256"])
            self.assertEqual("enemy", addition["source_part_kind"])

    def test_patch_preserves_destination_terminal_except_for_reviewed_bridge_wait(self):
        before = event_blocks(self.cleric)
        ids = self.ids()
        after = event_blocks(patch_orphan_at_cleric(self.cleric, self.orphan, ids))
        restored = after[12411700].replace("WaitFor(EventFlag(12990605));", "WaitFor(CharacterDead(2410800));")
        self.assertEqual(before[12411700], restored)
        self.assertIn("WaitFor(EventFlag(12990600));", after[12990605])
        self.assertIn("WaitFor(coreDead || phaseDead);", after[12990605])
        self.assertIn("ForceCharacterDeath(2410800, false);", after[12990605])
        self.assertIn("ForceCharacterDeath(980004, false);", after[12990605])
        self.assertIn("CreateReferredDamagePair(2410800, 980003);", after[12414702])
        self.assertIn("WaitFor(EventFlag(12414700) || EventFlag(12415400));", after[12414702])
        self.assertIn("WaitFor(HPRatio(2410800) < 0.5);", after[12990601])
        self.assertIn("RequestCharacterAICommand(980004, 10, 0);", after[12990602])
        self.assertIn("CharacterHasSpEffect(10000, 8055)", after[12990603])
        self.assertIn("CharacterHasSpEffect(980003, 5036)", after[12990604])
        self.assertIn("$InitializeEvent(0, 12990601);", after[0])
        self.assertEqual(set(before) | {12990601, 12990602, 12990603, 12990604, 12990605}, set(after))

    def test_known_installed_source_variant_is_retained_but_other_drift_refuses(self):
        patched = event_blocks(patch_orphan_at_cleric(self.cleric, self.installed_orphan, self.ids()))
        self.assertIn("HasDamageType(2410800, -1, DamageType.Unspecified)", patched[12414702])
        self.assertIn("SetNetworkUpdateRate(980003, true, CharacterUpdateFrequency.AlwaysUpdate)", patched[12414702])
        with self.assertRaisesRegex(ValueError, "unsupported original Orphan donor"):
            patch_orphan_at_cleric(self.cleric,
                                   self.installed_orphan.replace("HPRatio(3600800) < 0.5", "HPRatio(3600800) < 0.6"),
                                   self.ids())

    def test_patch_removes_unmapped_source_arena_lifecycle_and_noops_cleric_only_routines(self):
        after = event_blocks(patch_orphan_at_cleric(self.cleric, self.orphan, self.ids()))
        copied = "\n".join(after[event] for event in (12414702, 12414703, 12414704, 12990601, 12990602))
        for literal in ("36000000", "3601800", "3602800", "3602801", "3602805", "13604808", "13604810"):
            self.assertNotIn(literal, copied)
        self.assertNotRegex(copied, r"(?<!\d)(?:360|136)\d+",
                            "copied combat bodies must not retain donor-map operands")
        self.assertIn("InArea(10000, 2412802)", after[12414703])
        self.assertIn("SetLockcamSlotNumber(24, 1, 1)", after[12414704])
        for event in (12414707, 12414708, 12414710, 12414720):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])

    def test_native_plan_only_swaps_core_and_records_unobserved_status(self):
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_orphan_at_cleric(self.slots, npcs, effects, self.ids(), self.pins(), "test")
        self.assertEqual("c4540", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(6, len(plan["boss_actor_additions"]))
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])
        self.assertIn("scaling", plan)

    def test_bad_ids_pins_and_pinned_source_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "reviewed project actor IDs"):
            construction_request(self.slots, self.ids(phase_entity_id=ORPHAN_PHASE), self.pins())
        with self.assertRaisesRegex(ValueError, "129906xx"):
            construction_request(self.slots, self.ids(phase_event_id=12990599), self.pins())
        with self.assertRaisesRegex(ValueError, "unique project-owned"):
            construction_request(self.slots, self.ids(support_event_id=12990601), self.pins())
        with patch("tools.bb_enemizer.orphan_contract._globally_used_numbers",
                   return_value=({12990601}, {PROJECT_PHASE_ENTITY})):
            with self.assertRaisesRegex(ValueError, "project actor ID collides"):
                construction_request(self.slots, self.ids(), self.pins())
        with self.assertRaisesRegex(ValueError, "lowercase SHA256"):
            construction_request(self.slots, self.ids(), self.pins(part_sha256="A" * 64))
        with self.assertRaisesRegex(ValueError, "exact core, phase and support"):
            construction_request(self.slots, self.ids(), {"core": next(iter(self.pins().values()))})
        with self.assertRaisesRegex(ValueError, "unsupported original Orphan donor"):
            patch_orphan_at_cleric(self.cleric, self.orphan.replace("HPRatio(3600800) < 0.5", "HPRatio(3600800) < 0.6"), self.ids())
        with self.assertRaisesRegex(ValueError, "unsupported original Cleric arena"):
            patch_orphan_at_cleric(self.cleric.replace("HandleBossDefeat(2410800)", "HandleBossDefeat(999)", 1), self.orphan, self.ids())


if __name__ == "__main__":
    unittest.main()
