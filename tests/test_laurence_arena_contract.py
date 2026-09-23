import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import EBRIETAS_PACKAGE, PACKAGES
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.laurence_arena_contract import (
    ATTACHMENT_EVENTS,
    BULLET_OWNER_ENTITY,
    DEFAULT_IDS,
    LAURENCE_ARENA_CONTRACT,
    OWNER_CLEANUP_EVENT,
    READINESS_EVENT,
    _event_flags,
    _original_literals,
    laurence_arena_contract,
    native_plan_portable_donor_at_laurence,
    patch_portable_donor_at_laurence,
    portable_laurence_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"
LUDWIG_EVENTS = (
    13401800,
    13404803,
    13404820,
    13404821,
    13404822,
    13404823,
    13404824,
    13404825,
    13404830,
    13404840,
)
# Reviewed neighboring reservations.  The runtime patcher validates original
# corpus/destination collisions; this test prevents this adapter from
# overlapping known project-owned ranges before whole-plan validation.
NEIGHBOR_ALLOCATIONS = frozenset(
    (*range(12995000, 12995007), 982500, *range(12995100, 12995105), 982600, 982601)
)


class LaurenceArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        cls.sources = {
            package.key: read_blob(BUNDLE, "event/" + package.event_file).decode(
                "utf-8-sig"
            )
            for package in PACKAGES
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_laurence_is_a_separate_single_actor_arena_and_preserves_ludwig_scope(self):
        self.assertEqual("laurence", LAURENCE_ARENA_CONTRACT.key)
        self.assertEqual(
            (3400850, 13401850, 13404853),
            (
                LAURENCE_ARENA_CONTRACT.actor,
                LAURENCE_ARENA_CONTRACT.completion_event,
                LAURENCE_ARENA_CONTRACT.music_event,
            ),
        )
        self.assertEqual(
            (13404870, 13404875), LAURENCE_ARENA_CONTRACT.retired_combat_events
        )
        self.assertEqual("split-cinematic", LAURENCE_ARENA_CONTRACT.activation_profile)
        self.assertIsNone(LAURENCE_ARENA_CONTRACT.part_routine_event)
        self.assertEqual(5, len(ATTACHMENT_EVENTS))

    def test_every_base_package_is_portable_without_a_donor_or_arena_pair_whitelist(
        self,
    ):
        donors = portable_laurence_donors()
        self.assertEqual(
            {package.key for package in PACKAGES}, {package.key for package in donors}
        )
        self.assertEqual(6, len(donors))

    def test_outputs_keep_laurence_progression_fog_and_ludwig_events_byte_identical(
        self,
    ):
        before = event_blocks(self.destination)
        protected = (
            13401850,
            13404850,
            13404851,
            13404855,
            13404856,
            13404857,
            *LUDWIG_EVENTS,
        )
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                after = event_blocks(
                    patch_portable_donor_at_laurence(
                        self.destination,
                        donor,
                        self.sources[donor.key],
                        DEFAULT_IDS,
                    )
                )
                for event_id in protected:
                    self.assertEqual(before[event_id], after[event_id])
                self.assertTrue(
                    after[13404870].startswith("$Event(13404870, Restart, function()")
                )
                self.assertEqual("EndEvent();", after[13404870].splitlines()[1].strip())
                self.assertTrue(after[13404875].startswith("$Event(13404875,"))
                self.assertEqual("EndEvent();", after[13404875].splitlines()[1].strip())
                self.assertNotIn("$InitializeEvent(0, 13404870", after[0])
                self.assertNotIn("$InitializeEvent(0, 13404875);", after[0])

    def test_readiness_preserves_each_donor_wake_before_health_enables_ai(self):
        expected = {
            "blood-starved-beast": (
                "ForceAnimationPlayback(3400850, 7001, false, false, false);",
            ),
            "darkbeast-paarl": (
                "SetCharacterInvincibility(3400850, Enabled);",
                "WaitFixedTimeFrames(70);",
            ),
            "cleric-beast": (
                "SetCharacterGravity(3400850, Disabled);",
                "WaitFixedTimeFrames(110);",
            ),
            "vicar-amelia": (
                "ChangeCharacterEnableState(3400850, Disabled);",
                "ForceAnimationPlayback(3400850, 7001, false, false, false);",
            ),
            "amygdala": (
                "ForceAnimationPlayback(3400850, 7003, true, false, false);",
                "WaitFixedTimeFrames(160);",
            ),
            "ebrietas": (
                "SetCharacterImmortality(3400850, Enabled);",
                "WaitFor(HasDamageType(3400850, 10000, DamageType.Unspecified));",
            ),
        }
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                after = event_blocks(
                    patch_portable_donor_at_laurence(
                        self.destination,
                        donor,
                        self.sources[donor.key],
                        DEFAULT_IDS,
                    )
                )
                readiness = after[READINESS_EVENT]
                health = after[13404852]
                for witness in expected[donor.key]:
                    self.assertIn(witness, readiness)
                self.assertIn(f"WaitFor(EventFlag({READINESS_EVENT}));", health)
                self.assertLess(
                    health.index("SetCharacterInvincibility(3400850, Disabled);"),
                    health.index("SetCharacterAIState(3400850, Enabled);"),
                )

    def test_health_uses_laurence_notification_telemetry_and_no_donor_local_flags(self):
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                health = event_blocks(
                    patch_portable_donor_at_laurence(
                        self.destination,
                        donor,
                        self.sources[donor.key],
                        DEFAULT_IDS,
                    )
                )[13404852]
                self.assertIn("if (!EventFlag(13404860)) {", health)
                self.assertIn("SetEventFlag(13404860, ON);", health)
                self.assertIn("CreatePlaylog(46);", health)
                self.assertIn("StartTimeMeasurement(3400030, 62, Enabled);", health)
                source_flags = _event_flags(
                    event_blocks(self.sources[donor.key])[donor.health_bar_event]
                )
                foreign = source_flags - {donor.completion_event, donor.start_flag}
                self.assertFalse(
                    foreign.intersection(_event_flags(health)),
                    f"{donor.key} health retained a donor-local notification flag",
                )
                self.assertEqual(
                    {13401850, 13404858, 13404860, READINESS_EVENT},
                    _event_flags(health),
                )

    def test_music_keeps_destination_reload_recovery_and_maps_only_the_first_donor_boundary(
        self,
    ):
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                output = event_blocks(
                    patch_portable_donor_at_laurence(
                        self.destination,
                        donor,
                        self.sources[donor.key],
                        DEFAULT_IDS,
                    )
                )
                music = output[13404853]
                contract = laurence_arena_contract(donor)
                targets = {
                    row["source_event"]: row["destination_event"]
                    for row in contract["attachments"]
                }
                signal = donor.music_phase_signals[0]
                if signal.kind == "event_flag":
                    self.assertIn(
                        f"chrFlagArea &= EventFlag({targets[signal.source_event]});",
                        music,
                    )
                else:
                    self.assertIn(
                        f"chrFlagArea &= CharacterHasEventMessage(3400850, {signal.message});",
                        music,
                    )
                self.assertIn("L0:\n", music)
                self.assertIn("EnableBossMapSound(3403853, Enabled);", music)
                self.assertNotIn("CharacterHasEventMessage(3400800, 400)", music)

    def test_attachments_and_ebrietas_owner_have_explicit_target_identities_and_terminal_cleanup(
        self,
    ):
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                output = event_blocks(
                    patch_portable_donor_at_laurence(
                        self.destination,
                        donor,
                        self.sources[donor.key],
                        DEFAULT_IDS,
                    )
                )
                for row in laurence_arena_contract(donor)["attachments"]:
                    body = output[row["destination_event"]]
                    self.assertIn(f"$Event({row['destination_event']},", body)
                    self.assertIn("3400850", body)
                    self.assertNotIn(str(donor.completion_event), body)
        owner_output = event_blocks(
            patch_portable_donor_at_laurence(
                self.destination,
                EBRIETAS_PACKAGE,
                self.sources["ebrietas"],
                DEFAULT_IDS,
            )
        )
        cleanup = owner_output[OWNER_CLEANUP_EVENT]
        self.assertIn("CreateBulletOwner(982700)", owner_output[0])
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(13401850))"),
            cleanup.index("ChangeCharacterEnableState(982700, Disabled)"),
        )
        self.assertIn("ForceCharacterDeath(982700, false)", cleanup)

    def test_allocations_are_absent_from_the_original_corpus_and_native_plans_pin_primary_sources(
        self,
    ):
        original_collisions = set(DEFAULT_IDS.values()).intersection(
            _original_literals()
        )
        self.assertEqual(0, len(original_collisions))
        self.assertEqual(
            0, len(set(DEFAULT_IDS.values()).intersection(NEIGHBOR_ALLOCATIONS))
        )
        self.assertEqual(
            (12995200, 12995201, 12995202, 12995203, 12995204), ATTACHMENT_EVENTS
        )
        self.assertEqual(
            (12995205, 12995206, 982700),
            (OWNER_CLEANUP_EVENT, READINESS_EVENT, BULLET_OWNER_ENTITY),
        )
        for donor in portable_laurence_donors():
            with self.subTest(donor=donor.key):
                plan = native_plan_portable_donor_at_laurence(
                    donor,
                    self.slots,
                    self.npcs,
                    self.effects,
                    "laurence-arena",
                )
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(
                    {"m34_00_00_00"}, {row["destination_map"] for row in bindings}
                )
                self.assertEqual(
                    {"c4500_0000"}, {row["destination_part"] for row in bindings}
                )
                if donor is EBRIETAS_PACKAGE:
                    helpers = plan["boss_actor_addition_requirements"]
                    self.assertEqual(
                        {982700}, {row["destination_entity_id"] for row in helpers}
                    )
                    self.assertEqual(
                        {"c9010_0003"}, {row["source_part"] for row in helpers}
                    )
                else:
                    self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_outputs_compile_with_the_pinned_darkscript_fixture_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m34_00_00_00.emevd.dcx")
        if not compiler.is_file() or any(
            not (events / name).is_file() for name in required
        ):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original, source = work / "original", work / "source"
            original.mkdir()
            for name in required:
                shutil.copyfile(events / name, original / name)
            subprocess.run(
                [
                    str(compiler),
                    "/cmd",
                    "-decompile",
                    "-game",
                    "bb",
                    "-indir",
                    str(original),
                    "-outdir",
                    str(source),
                    "-force",
                    "-silent",
                ],
                check=True,
            )
            destination_path = source / "m34_00_00_00.emevd.dcx.js"
            baseline = destination_path.read_text(encoding="utf-8-sig")
            for donor in portable_laurence_donors():
                with self.subTest(donor=donor.key):
                    destination_path.write_text(
                        patch_portable_donor_at_laurence(
                            baseline, donor, self.sources[donor.key]
                        ),
                        encoding="utf-8-sig",
                    )
                    output = work / ("compiled-" + donor.key)
                    subprocess.run(
                        [
                            str(compiler),
                            "/cmd",
                            "-compile",
                            "-game",
                            "bb",
                            "-indir",
                            str(source),
                            "-outdir",
                            str(output),
                            "-force",
                            "-silent",
                        ],
                        check=True,
                    )
                    compiled = output / "m34_00_00_00.emevd.dcx"
                    self.assertTrue(compiled.is_file())
                    self.assertGreater(compiled.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
