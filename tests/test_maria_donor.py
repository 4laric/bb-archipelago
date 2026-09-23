import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

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
from tools.bb_enemizer.laurence_arena_contract import LAURENCE_ARENA_CONTRACT
from tools.bb_enemizer.maria_amelia_contract import (
    MariaAmeliaAttachmentIds,
    patch_maria_at_amelia,
)
from tools.bb_enemizer.maria_contract import (
    MARIA_ARENA,
    MARIA_EVENT_FILE,
    MARIA_EVENT_TARGET,
    MARIA_PACKAGE,
    MariaClericAttachmentIds,
    patch_maria_at_cleric,
)
from tools.bb_enemizer.maria_donor import (
    SUPPORTED_MARIA_ARENAS,
    MARIA_PRIMARY_INITIALIZATION,
    MARIA_PRIMARY_PIN,
    MariaArenaAllocation,
    maria_donor_contract,
    native_plan_maria_donor,
    patch_maria_donor,
    validate_maria_allocation,
)
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"
ALLOCATION = MariaArenaAllocation(12994700, 12994701)


class MariaDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(BUNDLE, "event/" + MARIA_EVENT_FILE).decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_MARIA_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_reserved_ids_are_absent_from_the_complete_original_event_corpus(self):
        event_originals = [
            data.decode("utf-8-sig")
            for data in read_prefix(BUNDLE, "event/").values()
        ]
        mined_originals = [
            data.decode("utf-8-sig")
            for data in read_prefix(BUNDLE, "mined/").values()
        ]
        originals = event_originals + mined_originals
        self.assertEqual(27, len(event_originals))
        self.assertGreater(len(mined_originals), 0)
        validate_maria_allocation(ALLOCATION, originals)
        joined = "\n".join(originals)
        self.assertNotIn(str(ALLOCATION.phase_cleanup_event), joined)
        self.assertNotIn(str(ALLOCATION.health_initialized_flag), joined)

    def test_all_supported_arenas_receive_full_maria_health_camera_and_cleanup(self):
        for arena in SUPPORTED_MARIA_ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_maria_donor(
                    arena, self.destinations[arena.key], self.maria, ALLOCATION
                ))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                self.assertEqual(
                    {ALLOCATION.phase_cleanup_event}, set(after).difference(before)
                )
                self.assertNotIn(
                    f"ForceAnimationPlayback({arena.actor},",
                    after[arena.activation_event],
                )
                self.assertIn(f"SetEventFlag({arena.start_flag}, ON)",
                              after[arena.activation_event])

                health = after[arena.health_bar_event]
                self.assertIn(f"$Event({arena.health_bar_event}, Default", health)
                self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", health)
                health_flag = (13404860 if arena is LAURENCE_ARENA_CONTRACT
                               else ALLOCATION.health_initialized_flag)
                self.assertIn(f"if (!EventFlag({health_flag}))", health)
                self.assertIn(f"SetEventFlag({health_flag}, ON)", health)
                self.assertIn(
                    f"SetNetworkUpdateAuthority({arena.actor}, AuthorityLevel.Normal)", health
                )
                self.assertIn(f"SetSpEffect({arena.actor}, 7500, false)", health)
                self.assertIn(f"SetSpEffect({arena.actor}, 7501, false)", health)
                self.assertIn(f"SetCharacterInvincibility({arena.actor}, Disabled)", health)
                self.assertIn(
                    f"SetCharacterEventTarget({arena.actor}, {MARIA_EVENT_TARGET})", health
                )
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    destination_line = next(
                        line for line in before[arena.health_bar_event].splitlines()
                        if line.strip().startswith(instruction + "(")
                    )
                    self.assertIn(destination_line, health)
                self.assertNotIn("CreatePlaylog(58)", health)
                self.assertNotIn("StartTimeMeasurement(3500010, 74, Enabled)", health)

                camera = after[arena.lockcam_event]
                self.assertIn(
                    f"EntityInRadiusOfEntity(10000, {arena.actor}, 8)", camera
                )
                self.assertIn(
                    f"EntityInRadiusOfEntity(10000, {arena.actor}, 10)", camera
                )
                self.assertEqual(
                    2,
                    camera.count(
                        f"SetLockcamSlotNumber({arena.lockcam_map}, "
                        f"{arena.lockcam_subarea},"
                    ),
                )
                cleanup = after[ALLOCATION.phase_cleanup_event]
                self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", cleanup)
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 20)", cleanup)
                self.assertIn(f"ClearSpEffect({arena.actor}, 5526)", cleanup)
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 100)",
                    after[arena.music_event],
                )

    def test_residual_destination_combat_controllers_are_inert(self):
        for arena in SUPPORTED_MARIA_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_maria_donor(
                    arena, self.destinations[arena.key], self.maria, ALLOCATION
                ))
                retired = {
                    *arena.phase_slots,
                    *arena.retired_combat_events,
                    *(() if arena.part_routine_event is None else (arena.part_routine_event,)),
                    *(() if arena.cloth_routine_event is None else (arena.cloth_routine_event,)),
                    *(() if arena.attachment_anchor_event is None
                      else (arena.attachment_anchor_event,)),
                }
                for event_id in retired:
                    self.assertIn("EndEvent();", blocks[event_id])
                    self.assertNotIn(str(arena.actor), blocks[event_id])
                self.assertEqual(
                    1,
                    blocks[0].count(
                        f"$InitializeEvent(0, {ALLOCATION.phase_cleanup_event});"
                    ),
                )

    def test_laurence_reuses_its_room_notification_and_one_transition_without_touching_ludwig(self):
        before = event_blocks(self.destinations[LAURENCE_ARENA_CONTRACT.key])
        after = event_blocks(patch_maria_donor(
            LAURENCE_ARENA_CONTRACT,
            self.destinations[LAURENCE_ARENA_CONTRACT.key], self.maria, ALLOCATION,
        ))
        health = after[LAURENCE_ARENA_CONTRACT.health_bar_event]
        self.assertIn("if (!EventFlag(13404860))", health)
        self.assertIn("SetEventFlag(13404860, ON)", health)
        self.assertNotIn(str(ALLOCATION.health_initialized_flag), health)
        music = after[LAURENCE_ARENA_CONTRACT.music_event]
        self.assertIn("CharacterHasEventMessage(3400850, 100)", music)
        self.assertIn("L0:\n", music)
        self.assertNotIn("CharacterHasEventMessage(3400850, 300)", music)
        for event_id in (13401800, 13404803, 13404820, 13404821, 13404822, 13404823):
            self.assertEqual(before[event_id], after[event_id])
        self.assertNotIn("$InitializeEvent(0, 13404870", after[0])
        self.assertNotIn("$InitializeEvent(0, 13404875);", after[0])
        self.assertEqual("EndEvent();", after[13404870].splitlines()[1].strip())
        self.assertEqual("EndEvent();", after[13404875].splitlines()[1].strip())

    def test_entry_protection_brackets_trigger_after_model_choreography_is_removed(self):
        paarl = event_blocks(patch_maria_donor(
            PAARL_ARENA, self.destinations[PAARL_ARENA.key], self.maria, ALLOCATION
        ))[PAARL_ARENA.activation_event]
        self.assertLess(
            paarl.index("SetCharacterInvincibility(2300810, Enabled)"),
            paarl.index("WaitFor("),
        )
        self.assertLess(
            paarl.index("WaitFor("),
            paarl.index("SetCharacterInvincibility(2300810, Disabled)"),
        )
        self.assertLess(
            paarl.index("SetCharacterInvincibility(2300810, Disabled)"),
            paarl.index("SetEventFlag(12304700, ON)"),
        )
        self.assertNotIn("WaitFixedTimeFrames(70)", paarl)

        amygdala = event_blocks(patch_maria_donor(
            AMYGDALA_ARENA, self.destinations[AMYGDALA_ARENA.key],
            self.maria, ALLOCATION
        ))[AMYGDALA_ARENA.activation_event]
        self.assertLess(
            amygdala.index("SetCharacterInvincibility(3300800, Enabled)"),
            amygdala.index("WaitFor("),
        )
        self.assertLess(
            amygdala.index("SetEventFlag(13304800, ON)"),
            amygdala.index("SetCharacterInvincibility(3300800, Disabled)"),
        )
        for witness in (
            "SetCharacterGravity(3300800",
            "SetCharacterMaphits(3300800",
            "WaitFixedTimeFrames(30)",
            "WaitFixedTimeFrames(160)",
        ):
            self.assertNotIn(witness, amygdala)

        ebrietas = event_blocks(patch_maria_donor(
            EBRIETAS_ARENA, self.destinations[EBRIETAS_ARENA.key],
            self.maria, ALLOCATION
        ))[EBRIETAS_ARENA.activation_event]
        self.assertLess(
            ebrietas.index("SetCharacterImmortality(2420800, Enabled)"),
            ebrietas.index("WaitFor("),
        )
        self.assertLess(
            ebrietas.index("HasDamageType(2420800"),
            ebrietas.index("SetCharacterImmortality(2420800, Disabled)"),
        )
        self.assertLess(
            ebrietas.index("SetCharacterImmortality(2420800, Disabled)"),
            ebrietas.index("SetEventFlag(12424800, ON)"),
        )
        self.assertNotIn("5647", ebrietas)

        amelia = event_blocks(patch_maria_donor(
            AMELIA_ARENA, self.destinations[AMELIA_ARENA.key],
            self.maria, ALLOCATION
        ))[AMELIA_ARENA.activation_event]
        self.assertEqual(1, amelia.count("IssueBossRoomEntryNotification(0)"))
        self.assertLess(
            amelia.index("IssueBossRoomEntryNotification(0)"),
            amelia.index(f"SetEventFlag({ALLOCATION.health_initialized_flag}, ON)"),
        )
        for arena in SUPPORTED_MARIA_ARENAS:
            if arena is AMELIA_ARENA:
                continue
            activation = event_blocks(patch_maria_donor(
                arena, self.destinations[arena.key], self.maria, ALLOCATION
            ))[arena.activation_event]
            self.assertNotIn(
                f"SetEventFlag({ALLOCATION.health_initialized_flag}, ON)", activation
            )

    def test_contract_pins_source_bodies_and_opaque_reference_for_every_arena(self):
        expected_sources = {
            MARIA_ARENA.health_event,
            MARIA_ARENA.lockcam_event,
            MARIA_ARENA.phase_cleanup_event,
        }
        for arena in SUPPORTED_MARIA_ARENAS:
            with self.subTest(arena=arena.key):
                contract = maria_donor_contract(arena, ALLOCATION)
                copied = contract["copied_source_events"]
                self.assertEqual(expected_sources, {item["source_event"] for item in copied})
                for item in copied:
                    self.assertEqual(
                        MARIA_PACKAGE.expected[item["source_event"]],
                        item["expected_source_sha256"],
                    )
                    self.assertIn(item["expected_source_sha256"],
                                  item["allowed_source_sha256s"])
                opaque = contract["opaque_external_references"][0]
                self.assertEqual(MARIA_EVENT_TARGET, opaque["original_source_id"])
                self.assertEqual(arena.actor, opaque["destination_actor"])
                self.assertEqual(arena.health_bar_event, opaque["destination_event"])
                self.assertNotIn(MARIA_ARENA.completion_event,
                                 contract["preserved_destination_events"])
                self.assertIn(arena.completion_event,
                              contract["preserved_destination_events"])
                self.assertNotIn(arena.activation_event,
                                 contract["preserved_destination_events"])
                self.assertIn(arena.activation_event,
                              contract["adapted_destination_events"])
                telemetry = contract["destination_owned_health_telemetry"]
                self.assertEqual(arena.health_bar_event, telemetry["event"])
                self.assertEqual(
                    ["CreatePlaylog", "StartTimeMeasurement"],
                    telemetry["instructions"],
                )

    def test_existing_cleric_and_amelia_outputs_change_only_for_full_health_body(self):
        cleric_old = event_blocks(patch_maria_at_cleric(
            self.destinations[CLERIC_ARENA.key], self.maria,
            MariaClericAttachmentIds(ALLOCATION.phase_cleanup_event),
        ))
        cleric_new = event_blocks(patch_maria_donor(
            CLERIC_ARENA, self.destinations[CLERIC_ARENA.key], self.maria, ALLOCATION
        ))
        amelia_old = event_blocks(patch_maria_at_amelia(
            self.destinations[AMELIA_ARENA.key], self.maria,
            MariaAmeliaAttachmentIds(ALLOCATION.phase_cleanup_event),
        ))
        amelia_new = event_blocks(patch_maria_donor(
            AMELIA_ARENA, self.destinations[AMELIA_ARENA.key], self.maria, ALLOCATION
        ))
        for old, new, health_event, intentional_changes in (
            (cleric_old, cleric_new, CLERIC_ARENA.health_bar_event,
             {CLERIC_ARENA.health_bar_event}),
            (amelia_old, amelia_new, AMELIA_ARENA.health_bar_event,
             {AMELIA_ARENA.health_bar_event, AMELIA_ARENA.activation_event}),
        ):
            self.assertNotEqual(old[health_event], new[health_event])
            self.assertEqual(
                {event_id: block for event_id, block in old.items()
                 if event_id not in intentional_changes},
                {event_id: block for event_id, block in new.items()
                 if event_id not in intentional_changes},
            )
            self.assertIn("AuthorityLevel.Normal", new[health_event])
            self.assertIn(str(ALLOCATION.health_initialized_flag), new[health_event])

    def test_installed_patch_health_authority_is_copied_without_normalization(self):
        source = event_blocks(self.maria)[MARIA_ARENA.health_event]
        installed = self.maria.replace("\r\n", "\n").replace(
            source,
            source.replace("AuthorityLevel.Normal", "AuthorityLevel.Forced"),
        )
        health = event_blocks(patch_maria_donor(
            AMELIA_ARENA, self.destinations[AMELIA_ARENA.key], installed, ALLOCATION
        ))[AMELIA_ARENA.health_bar_event]
        self.assertIn("AuthorityLevel.Forced", health)
        self.assertNotIn("AuthorityLevel.Normal", health)
        hashes = maria_donor_contract(AMELIA_ARENA, ALLOCATION)[
            "copied_source_events"
        ][0]["allowed_source_sha256s"]
        self.assertEqual(2, len(hashes))

    def test_native_plan_covers_every_physical_destination_with_maria_source_pin(self):
        for arena in SUPPORTED_MARIA_ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_maria_donor(
                    arena, self.slots, self.npcs, self.effects,
                    ALLOCATION, "reusable-maria",
                )
                self.assertEqual("bb-enemizer-plan-v2", plan["format"])
                self.assertEqual("c4520", plan["swaps"][0]["target"]["model_name"])
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(arena.destination_count, len(bindings))
                self.assertEqual(
                    {"m35_00_00_00"}, {binding["source_map"] for binding in bindings}
                )
                self.assertEqual(
                    {"c4520_0002"}, {binding["source_part"] for binding in bindings}
                )
                self.assertEqual(
                    {MARIA_PACKAGE.actor},
                    {binding["source_entity_id"] for binding in bindings},
                )
                self.assertEqual(
                    {MARIA_PRIMARY_PIN},
                    {binding["source_provenance"]["part_sha256"] for binding in bindings},
                )
                self.assertEqual(
                    {tuple(sorted(MARIA_PRIMARY_INITIALIZATION.items()))},
                    {tuple(sorted(binding["source_initialization"].items())) for binding in bindings},
                )
                self.assertEqual(
                    {slot.map_name for slot in self.slots
                     if slot.entity_id == arena.actor and slot.archetype == arena.archetype},
                    {binding["destination_map"] for binding in bindings},
                )

    def test_adapter_rejects_collisions_source_drift_and_missing_native_state(self):
        cleric = self.destinations[CLERIC_ARENA.key]
        with self.assertRaisesRegex(ValueError, "distinct positive"):
            patch_maria_donor(
                CLERIC_ARENA, cleric, self.maria,
                MariaArenaAllocation(12994700, 12994700),
            )
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_maria_donor(
                CLERIC_ARENA, cleric, self.maria,
                MariaArenaAllocation(CLERIC_ARENA.health_bar_event, 12994701),
            )
        with self.assertRaisesRegex(ValueError, "Lady Maria donor"):
            patch_maria_donor(
                CLERIC_ARENA, cleric,
                self.maria.replace("ClearSpEffect(3500800, 5526)",
                                   "ClearSpEffect(3500800, 5525)"),
                ALLOCATION,
            )
        one_missing = [
            slot for slot in self.slots
            if not (slot.entity_id == CLERIC_ARENA.actor
                    and slot.map_name == "m24_01_00_11")
        ]
        with self.assertRaisesRegex(ValueError, "every exact original destination state"):
            native_plan_maria_donor(
                CLERIC_ARENA, one_missing, self.npcs, self.effects,
                ALLOCATION, "missing-state",
            )

    def test_one_reusable_output_compiles_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m35_00_00_00.emevd.dcx",
                    "m24_00_00_00.emevd.dcx")
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
            maria_path = source / MARIA_EVENT_FILE
            destination_path.write_text(
                patch_maria_donor(
                    AMELIA_ARENA,
                    destination_path.read_text(encoding="utf-8-sig"),
                    maria_path.read_text(encoding="utf-8-sig"),
                    ALLOCATION,
                ),
                encoding="utf-8-sig",
            )
            subprocess.run([
                str(compiler), "/cmd", "-compile", "-game", "bb",
                "-indir", str(source), "-outdir", str(output), "-force", "-silent",
            ], check=True)
            self.assertTrue((output / "m24_00_00_00.emevd.dcx").is_file())

    def test_laurence_output_compiles_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m34_00_00_00.emevd.dcx", "m35_00_00_00.emevd.dcx")
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
            destination_path = source / LAURENCE_ARENA_CONTRACT.event_file
            maria_path = source / MARIA_EVENT_FILE
            destination_path.write_text(
                patch_maria_donor(
                    LAURENCE_ARENA_CONTRACT,
                    destination_path.read_text(encoding="utf-8-sig"),
                    maria_path.read_text(encoding="utf-8-sig"), ALLOCATION,
                ), encoding="utf-8-sig",
            )
            subprocess.run([
                str(compiler), "/cmd", "-compile", "-game", "bb",
                "-indir", str(source), "-outdir", str(output), "-force", "-silent",
            ], check=True)
            compiled = output / "m34_00_00_00.emevd.dcx"
            self.assertTrue(compiled.is_file())
            self.assertGreater(compiled.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
