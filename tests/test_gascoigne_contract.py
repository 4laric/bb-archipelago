import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.gascoigne_contract import (
    BUNDLE, GASCOIGNE_BEAST, PHASE_EVENTS, NativeActorPin, ProjectOwnedIds,
    construction_request, native_plan_gascoigne_at_cleric, patch_gascoigne_at_cleric, plan_gascoigne_at_cleric,
)
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.inventory import load_slots


class GascoigneContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)

    def allocation(self, **changes):
        values = dict(beast_entity_id=980001, phase_event_ids={12414807: 12990001, 12414808: 12990002, 12414809: 12990003}, terminal_bridge_event_id=12990004,
                      destination_part="ap_gascoigne_beast", evidence="test-owned explicit IDs; checked against bundled m24_01 corpus")
        values.update(changes)
        return ProjectOwnedIds(**values)

    def native_pin(self, **changes):
        values = dict(part_sha256="a" * 64, anchor_sha256="b" * 64,
                      talk_id=0, unk_t18=0, init_anim_id=0, damage_anim_id=0)
        values.update(changes)
        return NativeActorPin(**values)

    def native_pins(self, **changes):
        return {name: self.native_pin(**changes) for name in
                ("m24_01_00_00", "m24_01_00_01", "m24_01_00_11")}

    def test_phase_pair_is_explicit_and_native_addition_is_anchored(self):
        request = construction_request(self.slots, self.allocation(), self.native_pins())
        self.assertEqual(2410800, request.human_entity_id)
        self.assertEqual(980001, request.beast_entity_id)
        self.assertEqual(3, len(request.actor_additions))
        self.assertEqual({"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"},
                         {item["destination_map"] for item in request.actor_additions})
        for addition in request.actor_additions:
            self.assertEqual("c2720_0000", addition["source_part"])
            self.assertEqual("c2710_0000", addition["source_anchor_part"])
            self.assertEqual("c5000_0000", addition["destination_anchor_part"])
            self.assertEqual("destination-anchor", addition["placement_policy"])
            self.assertEqual(GASCOIGNE_BEAST, addition["source_entity_id"])
            self.assertEqual("enemy", addition["source_part_kind"])
            self.assertEqual("bb-boss-actor-pin-v1", addition["source_provenance"]["format"])
        self.assertEqual(set(PHASE_EVENTS), {item["source_event_id"] for item in request.added_events if item["source_event_id"] is not None})
        self.assertEqual({12414702, 12414703, 12414704},
                         {item["destination_event_id"] for item in request.changed_events})
        self.assertEqual({12411700}, {item["literal_remap"][12411800] for item in request.added_events if "literal_remap" in item})
        self.assertTrue(request.completion_adapter["required"])

    def test_source_patch_uses_a_bridge_and_preserves_terminal_progression_body(self):
        original = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")
        patched = patch_gascoigne_at_cleric(original, self.allocation())
        before, after = event_blocks(original), event_blocks(patched)
        self.assertEqual(before[12411700].replace("    WaitFor(CharacterDead(2410800));\n",
                                                   "    WaitFor(EventFlag(12990004));\n"), after[12411700])
        self.assertIn("WaitFor(humanDead || (beastPhase && beastDead));", after[12990004])
        self.assertIn("beastPhase = EventFlag(12990001);", after[12990004])
        self.assertIn("ChangeCharacterEnableState(980001, Disabled);", after[12990004])
        self.assertIn("CreateReferredDamagePair(2410800, 980001);", after[12414702])
        link = after[12414702].index("CreateReferredDamagePair(2410800, 980001);")
        self.assertLess(after[12414702].index(
            "SetCharacterInvincibility(980001, Disabled);"
        ), link)
        self.assertIn("WaitFor(EventFlag(12414700) || EventFlag(12415400));", after[12414702])
        self.assertIn("IssueBossRoomEntryNotification(0);", after[12414702])
        self.assertNotIn("12414223", after[12414702])
        self.assertIn("WarpCharacterAndCopyFloor(980001", after[12990001])
        self.assertNotIn("9350", after[12990001])
        self.assertNotIn("9337", after[12990001])
        self.assertIn("$InitializeEvent(0, 12990004);", after[0])
        self.assertEqual(set(before) | {12990001, 12990002, 12990003, 12990004}, set(after))

    def test_beast_is_isolated_until_post_warp_phase_activation_and_restored_on_reload(self):
        original = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")
        phase = event_blocks(patch_gascoigne_at_cleric(original, self.allocation()))[12990001]
        pre_phase = (
            "    ChangeCharacterEnableState(980001, Disabled);\n"
            "    SetCharacterInvincibility(980001, Enabled);\n"
            "    SetCharacterAIState(980001, Disabled);\n"
            "    SetCharacterHPBarDisplay(980001, Disabled);\n"
            "    SetCharacterGravity(980001, Disabled);"
        )
        self.assertIn(pre_phase, phase)
        warp = phase.index("WarpCharacterAndCopyFloor(980001")
        enabled = phase.index("ChangeCharacterEnableState(980001, Enabled);", warp)
        vulnerable = phase.index("SetCharacterInvincibility(980001, Disabled);", enabled)
        gravity = phase.index("SetCharacterGravity(980001, Enabled);", vulnerable)
        combat = phase.index("SetCharacterAIState(980001, Enabled);", gravity)
        self.assertLess(warp, enabled)
        self.assertLess(enabled, vulnerable)
        self.assertLess(vulnerable, gravity)
        self.assertLess(gravity, combat)
        completed = phase.split("L0:", 1)[0]
        self.assertIn("ChangeCharacterEnableState(980001, Enabled);", completed)
        self.assertIn("SetCharacterInvincibility(980001, Disabled);", completed)
        self.assertIn("SetCharacterGravity(980001, Enabled);", completed)

    def test_entry_uses_native_combat_placement_without_cleric_leap_warp(self):
        original = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")
        before = event_blocks(original)[12411702]
        entry = event_blocks(patch_gascoigne_at_cleric(original, self.allocation()))[12411702]
        self.assertNotIn("2412831", entry)
        self.assertNotIn("ForceAnimationPlayback", entry)
        expected = before.replace(
            "    IssueShortWarpRequest(2410800, TargetEntityType.Area, 2412831, -1);\n", ""
        ).replace(
            "    ForceAnimationPlayback(2410800, 3028, false, false, false);\n", ""
        ).replace("WaitFixedTimeFrames(110)", "WaitFixedTimeFrames(1)")
        self.assertEqual(expected, entry)
        self.assertLess(entry.index("InArea(10000, 2412805)"),
                        entry.index("ChangeCharacterEnableState(2410800, Enabled)"))
        self.assertLess(entry.index("SetCharacterGravity(2410800, Enabled)"),
                        entry.index("SetEventFlag(12414700, ON)"))

    def test_builder_fragment_exposes_only_typed_actor_and_terminal_inputs(self):
        plan = plan_gascoigne_at_cleric(self.slots, self.allocation(), self.native_pins())
        self.assertEqual("father-gascoigne", plan["donor"])
        self.assertEqual(3, len(plan["boss_actor_additions"]))
        self.assertEqual([{"event_id": 12411700, "original_actor": 2410800, "bridge_event_id": 12990004}],
                         plan["event_patch"]["terminal_predicates"])

    def test_native_plan_swaps_only_primary_human_and_declares_scaling_outcome(self):
        npcs, effects = load_params(BUNDLE)
        plan = native_plan_gascoigne_at_cleric(self.slots, npcs, effects, self.allocation(), self.native_pins(), "test")
        self.assertEqual("c2710", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(3, len(plan["swaps"][0]["destination_keys"]))
        self.assertEqual(3, len(plan["boss_actor_additions"]))
        self.assertIn("scaling", plan)

    def test_unreviewed_or_colliding_ids_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "collides with the bundled MSB"):
            construction_request(self.slots, self.allocation(beast_entity_id=2410811), self.native_pins())
        with self.assertRaisesRegex(ValueError, "collides with a bundled EMEVD operand"):
            construction_request(self.slots, self.allocation(phase_event_ids={12414807: 12414807, 12414808: 12990002, 12414809: 12990003}), self.native_pins())
        with self.assertRaisesRegex(ValueError, "every declared phase"):
            construction_request(self.slots, self.allocation(phase_event_ids={12414807: 12990001}), self.native_pins())
        with self.assertRaisesRegex(ValueError, "collides with a bundled EMEVD operand"):
            construction_request(self.slots, self.allocation(terminal_bridge_event_id=12411800), self.native_pins())
        with self.assertRaisesRegex(ValueError, "lowercase SHA256"):
            construction_request(self.slots, self.allocation(), self.native_pins(part_sha256="A" * 64))
        with self.assertRaisesRegex(ValueError, "every destination map state"):
            construction_request(self.slots, self.allocation(), {"m24_01_00_00": self.native_pin()})

if __name__ == "__main__":
    unittest.main()
