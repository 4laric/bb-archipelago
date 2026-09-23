import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import (
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    CLERIC_ARENA,
    EBRIETAS_ARENA,
    PAARL_ARENA,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.laurence_contract import LaurenceIds, patch_laurence_at_cleric
from tools.bb_enemizer.laurence_donor import (
    DEFAULT_LAURENCE_ALLOCATION,
    LAURENCE_ACTOR,
    LAURENCE_ARCHETYPE,
    LAURENCE_CAMERA_EVENT,
    LAURENCE_ENTRY_ANIMATION,
    LAURENCE_EVENT_FILE,
    LAURENCE_HEALTH_EVENT,
    LAURENCE_HITMASK_EVENT,
    LAURENCE_LIMB_EVENT,
    LAURENCE_SOURCE_HASHES,
    SUPPORTED_LAURENCE_ARENAS,
    LaurenceDonorAllocation,
    laurence_donor_contract,
    native_plan_laurence_donor,
    patch_laurence_donor,
)
from tools.bb_enemizer.scaling import load_params


BUNDLE = ROOT / "research/bb_inputs.db"
IDS = DEFAULT_LAURENCE_ALLOCATION


class LaurenceDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laurence = read_blob(BUNDLE, "event/" + LAURENCE_EVENT_FILE).decode(
            "utf-8-sig"
        )
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_LAURENCE_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_reserved_ids_are_absent_from_original_emevd_and_mined_msb(self):
        originals = [
            data.decode("utf-8-sig")
            for prefix in ("event/", "mined/")
            for data in read_prefix(BUNDLE, prefix).values()
        ]
        joined = "\n".join(originals)
        self.assertEqual((12994900, 12994901, 12994902), IDS.values())
        for value in IDS.values():
            self.assertNotIn(str(value), joined)

    def test_all_six_arenas_receive_full_combat_with_destination_telemetry(self):
        for arena in SUPPORTED_LAURENCE_ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_laurence_donor(
                    arena, self.destinations[arena.key], self.laurence, IDS
                ))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                self.assertEqual(
                    {IDS.limbs_event, IDS.hitmask_event}, set(after).difference(before)
                )
                health = after[arena.health_bar_event]
                self.assertIn(f"$Event({arena.health_bar_event}, Restart", health)
                self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", health)
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))", health)
                self.assertIn(f"if (!EventFlag({IDS.health_initialized_flag}))", health)
                self.assertIn(f"SetEventFlag({IDS.health_initialized_flag}, ON)", health)
                self.assertIn(
                    f"SetNetworkUpdateAuthority({arena.actor}, AuthorityLevel.Forced)", health
                )
                self.assertIn(f"SetSpEffect({arena.actor}, 7500, true)", health)
                self.assertIn(f"SetSpEffect({arena.actor}, 7501, true)", health)
                self.assertIn(f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, 450000)", health)
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    destination_line = next(
                        line for line in before[arena.health_bar_event].splitlines()
                        if line.strip().startswith(instruction + "(")
                    )
                    self.assertIn(destination_line, health)
                self.assertNotIn("CreatePlaylog(46)", health)
                self.assertNotIn("StartTimeMeasurement(3400030, 62, Enabled)", health)

                camera = after[arena.lockcam_event]
                self.assertIn(f"EntityInRadiusOfEntity(10000, {arena.actor}, 14)", camera)
                self.assertIn(f"EntityInRadiusOfEntity(10000, {arena.actor}, 17)", camera)
                self.assertEqual(
                    2,
                    camera.count(
                        f"SetLockcamSlotNumber({arena.lockcam_map}, "
                        f"{arena.lockcam_subarea},"
                    ),
                )
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 400)",
                    after[arena.music_event],
                )
                self.assertIn(f"CreateNPCPart({arena.actor}", after[IDS.limbs_event])
                self.assertIn(
                    f"ChangeCharacterHitmask({arena.actor}, 10, ON)",
                    after[IDS.hitmask_event],
                )

    def test_constructor_and_retired_controllers_match_source_closure(self):
        for arena in SUPPORTED_LAURENCE_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_laurence_donor(
                    arena, self.destinations[arena.key], self.laurence, IDS
                ))
                self.assertEqual(5, blocks[0].count(str(IDS.limbs_event)))
                self.assertEqual(1, blocks[0].count(str(IDS.hitmask_event)))
                retired = {
                    *arena.phase_slots,
                    arena.part_routine_event,
                    *(() if arena.cloth_routine_event is None else (arena.cloth_routine_event,)),
                    *(() if arena.attachment_anchor_event is None
                      else (arena.attachment_anchor_event,)),
                }
                for event_id in retired:
                    self.assertIn("EndEvent();", blocks[event_id])
                    self.assertNotIn(str(arena.actor), blocks[event_id])

    def test_entry_animation_and_protection_order_are_arena_safe(self):
        patched = {
            arena.key: event_blocks(patch_laurence_donor(
                arena, self.destinations[arena.key], self.laurence, IDS
            ))[arena.activation_event]
            for arena in SUPPORTED_LAURENCE_ARENAS
        }
        for arena in SUPPORTED_LAURENCE_ARENAS:
            activation = patched[arena.key]
            self.assertEqual(
                1,
                activation.count(
                    f"ForceAnimationPlayback({arena.actor}, {LAURENCE_ENTRY_ANIMATION},"
                ),
                arena.key,
            )

        paarl = patched[PAARL_ARENA.key]
        self.assertLess(paarl.index("Invincibility(2300810, Enabled)"),
                        paarl.index("WaitFor("))
        self.assertLess(paarl.index("WaitFor("), paarl.index("3029"))
        self.assertLess(paarl.index("3029"), paarl.index("WaitFixedTimeFrames(70)"))
        self.assertLess(paarl.index("WaitFixedTimeFrames(70)"),
                        paarl.index("Invincibility(2300810, Disabled)"))

        amygdala = patched[AMYGDALA_ARENA.key]
        self.assertLess(amygdala.index("Invincibility(3300800, Enabled)"),
                        amygdala.index("WaitFor("))
        self.assertLess(amygdala.index("WaitFor("),
                        amygdala.index("Invincibility(3300800, Disabled)"))
        self.assertLess(amygdala.index("Invincibility(3300800, Disabled)"),
                        amygdala.index("3029"))
        self.assertLess(amygdala.index("3029"),
                        amygdala.index("SetEventFlag(13304800, ON)"))
        for witness in ("SetCharacterGravity(3300800", "SetCharacterMaphits(3300800",
                        "WaitFixedTimeFrames(30)", "WaitFixedTimeFrames(160)"):
            self.assertNotIn(witness, amygdala)

        ebrietas = patched[EBRIETAS_ARENA.key]
        self.assertLess(ebrietas.index("Immortality(2420800, Enabled)"),
                        ebrietas.index("WaitFor("))
        self.assertLess(ebrietas.index("HasDamageType(2420800"), ebrietas.index("3029"))
        self.assertLess(ebrietas.index("3029"),
                        ebrietas.index("Immortality(2420800, Disabled)"))
        self.assertNotIn("5647", ebrietas)

        amelia = patched[AMELIA_ARENA.key]
        self.assertLess(amelia.index("IssueBossRoomEntryNotification(0)"),
                        amelia.index(f"SetEventFlag({IDS.health_initialized_flag}, ON)"))

    def test_contract_records_full_source_graph_and_destination_ownership(self):
        for arena in SUPPORTED_LAURENCE_ARENAS:
            with self.subTest(arena=arena.key):
                contract = laurence_donor_contract(arena, IDS)
                self.assertEqual(
                    {str(event_id) for event_id in LAURENCE_SOURCE_HASHES},
                    set(contract["source_event_hashes"]),
                )
                self.assertEqual(
                    {
                        LAURENCE_HEALTH_EVENT,
                        LAURENCE_CAMERA_EVENT,
                        LAURENCE_LIMB_EVENT,
                        LAURENCE_HITMASK_EVENT,
                    },
                    {row["source_event"] for row in contract["copied_source_events"]},
                )
                self.assertIn(arena.completion_event,
                              contract["preserved_destination_events"])
                self.assertIn(arena.activation_event,
                              contract["adapted_destination_events"])
                self.assertEqual(
                    ["CreatePlaylog", "StartTimeMeasurement"],
                    contract["destination_owned_health_telemetry"]["instructions"],
                )
                self.assertEqual(3029, contract["entry_animation"]["animation_id"])

    def test_existing_cleric_adapter_is_byte_compatible_outside_full_health(self):
        old = event_blocks(patch_laurence_at_cleric(
            self.destinations[CLERIC_ARENA.key], self.laurence,
            LaurenceIds(IDS.limbs_event, IDS.hitmask_event),
        ))
        new = event_blocks(patch_laurence_donor(
            CLERIC_ARENA, self.destinations[CLERIC_ARENA.key], self.laurence, IDS
        ))
        self.assertNotEqual(old[CLERIC_ARENA.health_bar_event],
                            new[CLERIC_ARENA.health_bar_event])
        self.assertEqual(
            {event_id: block for event_id, block in old.items()
             if event_id != CLERIC_ARENA.health_bar_event},
            {event_id: block for event_id, block in new.items()
             if event_id != CLERIC_ARENA.health_bar_event},
        )

    def test_native_plan_binds_exact_source_to_every_physical_destination(self):
        for arena in SUPPORTED_LAURENCE_ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_laurence_donor(
                    arena, self.slots, self.npcs, self.effects, "reusable-laurence", IDS
                )
                self.assertEqual("c4500", plan["swaps"][0]["target"]["model_name"])
                self.assertTrue(plan["scaling"]["enabled"])
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(arena.destination_count, len(bindings))
                self.assertEqual({"m34_00_00_00"},
                                 {row["source_map"] for row in bindings})
                self.assertEqual({"c4500_0000"},
                                 {row["source_part"] for row in bindings})
                self.assertEqual({LAURENCE_ACTOR},
                                 {row["source_entity_id"] for row in bindings})
                self.assertEqual(asdict(LAURENCE_ARCHETYPE),
                                 bindings[0]["source_archetype"])

    def test_rejects_allocation_source_and_native_provenance_drift(self):
        cleric = self.destinations[CLERIC_ARENA.key]
        with self.assertRaisesRegex(ValueError, "distinct positive"):
            patch_laurence_donor(
                CLERIC_ARENA, cleric, self.laurence,
                LaurenceDonorAllocation(12994900, 12994900, 12994902),
            )
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_laurence_donor(
                CLERIC_ARENA, cleric, self.laurence,
                LaurenceDonorAllocation(CLERIC_ARENA.health_bar_event, 12994901, 12994902),
            )
        with self.assertRaisesRegex(ValueError, "Laurence donor"):
            patch_laurence_donor(
                CLERIC_ARENA, cleric,
                self.laurence.replace("ChangeCharacterHitmask(3400850, 10, ON)",
                                      "ChangeCharacterHitmask(3400850, 9, ON)"),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != LAURENCE_ACTOR]
        with self.assertRaisesRegex(ValueError, "pinned c4500_0000 source"):
            native_plan_laurence_donor(
                CLERIC_ARENA, missing, self.npcs, self.effects, "missing", IDS
            )

    def test_reusable_output_compiles_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m24_00_00_00.emevd.dcx")
        if not compiler.is_file() or any(not (events / name).is_file() for name in required):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original, source, output = work / "o", work / "s", work / "out"
            original.mkdir()
            for name in required:
                shutil.copyfile(events / name, original / name)
            subprocess.run([
                str(compiler), "/cmd", "-decompile", "-game", "bb",
                "-indir", str(original), "-outdir", str(source), "-force", "-silent",
            ], check=True)
            destination_path = source / AMELIA_ARENA.event_file
            destination_path.write_text(
                patch_laurence_donor(
                    AMELIA_ARENA,
                    destination_path.read_text(encoding="utf-8-sig"),
                    self.laurence,
                    IDS,
                ),
                encoding="utf-8-sig",
            )
            subprocess.run([
                str(compiler), "/cmd", "-compile", "-game", "bb",
                "-indir", str(source), "-outdir", str(output), "-force", "-silent",
            ], check=True)
            self.assertTrue((output / "m24_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
