import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import AMYGDALA_PACKAGE, BSB_PACKAGE, PACKAGES
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.maria_arena_contract import (
    ACTIVATION_EVENT,
    ATTACHMENT_EVENTS,
    BULLET_OWNER_ENTITY,
    DEFAULT_IDS,
    MARIA_ARENA_CONTRACT,
    OWNER_CLEANUP_EVENT,
    MariaArenaIds,
    _original_literals,
    maria_arena_contract,
    native_plan_portable_donor_at_maria,
    patch_portable_donor_at_maria,
    portable_maria_donors,
)
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class MariaArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(BUNDLE, "event/m35_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        cls.sources = {
            package.key: read_blob(BUNDLE, "event/" + package.event_file).decode("utf-8-sig")
            for package in PACKAGES
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_arena_contract_is_separate_from_the_base_six_and_uses_pinned_maria_shape(self):
        self.assertEqual("lady-maria", MARIA_ARENA_CONTRACT.key)
        self.assertEqual("m35_00_00_00.emevd.dcx.js", MARIA_ARENA_CONTRACT.event_file)
        self.assertEqual(3500800, MARIA_ARENA_CONTRACT.actor)
        self.assertEqual((100, 300), MARIA_ARENA_CONTRACT.music_phase_messages)
        self.assertEqual((13504822,), MARIA_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual("normalized-cinematic", MARIA_ARENA_CONTRACT.activation_profile)
        self.assertIsNone(MARIA_ARENA_CONTRACT.part_routine_event)
        self.assertEqual(0, MARIA_ARENA_CONTRACT.attachment_anchor_slot)
        self.assertEqual(13504822, MARIA_ARENA_CONTRACT.attachment_anchor_event)

    def test_all_six_base_packages_are_structurally_portable_without_a_pair_whitelist(self):
        donors = portable_maria_donors()
        self.assertEqual({package.key for package in PACKAGES}, {package.key for package in donors})
        self.assertEqual(6, len(donors))

    def test_every_portable_donor_keeps_maria_terminal_and_retires_target_controller(self):
        before = event_blocks(self.maria)
        for donor in portable_maria_donors():
            with self.subTest(donor=donor.key):
                after = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))
                self.assertEqual(before[13501800], after[13501800])
                self.assertEqual(before[13501801], after[13501801])
                self.assertEqual(before[13501807], after[13501807])
                self.assertEqual(
                    "$Event(13504822, Default, function() {\n    EndEvent();\n});",
                    after[13504822],
                )
                self.assertNotIn("3500801", after[13504802])
                self.assertIn(
                    f"DisplayBossHealthBar(Enabled, 3500800, 0, {donor.health_bar_label})",
                    after[13504802],
                )
                source_health = event_blocks(self.sources[donor.key])[donor.health_bar_event]
                if "AuthorityLevel.Forced" in source_health:
                    self.assertIn("SetNetworkUpdateAuthority(3500800, AuthorityLevel.Forced)",
                                  after[13504802])
                self.assertIn("CreatePlaylog(58)", after[13504802])
                self.assertIn("StartTimeMeasurement(3500010, 74, Enabled)", after[13504802])
                self.assertLess(
                    after[13504802].index("SetCharacterInvincibility(3500800, Disabled);"),
                    after[13504802].index("SetCharacterAIState(3500800, Enabled);"),
                )
                self.assertNotIn("$InitializeEvent(0, 13504822);", after[0])
                self.assertIn(f"$InitializeEvent(0, {ACTIVATION_EVENT});", after[0])
                self.assertIn(
                    f"WaitFor(EventFlag({ACTIVATION_EVENT}));",
                    after[13504802],
                )

    def test_each_source_backed_readiness_profile_runs_before_maria_health_enables_ai(self):
        expected = {
            "blood-starved-beast": (
                "WaitFor(EventFlag(13504808));",
                "ForceAnimationPlayback(3500800, 7001, false, false, false);",
            ),
            "darkbeast-paarl": (
                "SetCharacterInvincibility(3500800, Enabled);",
                "WaitFixedTimeFrames(70);",
                "SetCharacterInvincibility(3500800, Disabled);",
            ),
            "cleric-beast": (
                "SetCharacterGravity(3500800, Disabled);",
                "ForceAnimationPlayback(3500800, 3028, false, false, false);",
                "SetCharacterMaphits(3500800, false);",
            ),
            "vicar-amelia": (
                "ChangeCharacterEnableState(3500800, Disabled);",
                "ForceAnimationPlayback(3500800, 7000, false, false, false);",
                "ForceAnimationPlayback(3500800, 7001, false, false, false);",
            ),
            "amygdala": (
                "SetCharacterMaphits(3500800, true);",
                "ForceAnimationPlayback(3500800, 7003, true, false, false);",
                "WaitFixedTimeFrames(160);",
                "SetCharacterGravity(3500800, Enabled);",
            ),
            "ebrietas": (
                "SetCharacterImmortality(3500800, Enabled);",
                "WaitFor(HasDamageType(3500800, 10000, DamageType.Unspecified));",
                "ClearSpEffect(3500800, 5647);",
            ),
        }
        for donor in portable_maria_donors():
            with self.subTest(donor=donor.key):
                blocks = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))
                activation = blocks[ACTIVATION_EVENT]
                self.assertEqual(donor.activation_event,
                                 maria_arena_contract(donor)["readiness_adapter"]["source_event"])
                self.assertEqual("destination-m35-geometry",
                                 maria_arena_contract(donor)["readiness_adapter"]["camera_policy"])
                for witness in expected[donor.key]:
                    self.assertIn(witness, activation)
                self.assertLess(
                    activation.index("WaitFor(EventFlag(13504808));"),
                    activation.rindex("});"),
                )

    def test_two_boundary_and_one_boundary_music_follow_the_declared_policy(self):
        for donor in (BSB_PACKAGE, AMYGDALA_PACKAGE):
            with self.subTest(two_boundaries=donor.key):
                blocks = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))
                contract = maria_arena_contract(donor)
                attached = {entry["source_event"]: entry["destination_event"]
                            for entry in contract["attachments"]}
                music = blocks[13504803]
                self.assertIn(f"chrFlagArea &= EventFlag({attached[donor.phase_events[0]]})", music)
                self.assertIn(f"chrFlagArea2 &= EventFlag({attached[donor.phase_events[1]]})", music)
                self.assertIn("EnableBossMapSound(3503803, Enabled)", music)
                self.assertIn("EnableBossMapSound(3503804, Enabled)", music)
        for donor in (package for package in PACKAGES if package not in (BSB_PACKAGE, AMYGDALA_PACKAGE)):
            with self.subTest(one_boundary=donor.key):
                music = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))[13504803]
                self.assertIn("EnableBossMapSound(3503804, Enabled)", music)
                self.assertNotIn("EnableBossMapSound(3503803, Enabled)", music)
                self.assertNotIn("CharacterHasEventMessage(3500800, 300)", music)
                self.assertIn("SpawnMapSFX(3503501)", music)
                self.assertIn("DeleteMapSFX(3503500, true)", music)
                self.assertIn("L1:\n", music)
                self.assertIn("chrFlagArea2 &= EventFlag(13504811);", music)
                self.assertLess(
                    music.index("SetEventFlag(13504811, ON);"),
                    music.index("L1:\n"),
                )
                self.assertGreaterEqual(music.count("EnableBossMapSound(3503804, Enabled)"), 2)

    def test_every_declared_source_phase_body_is_installed_with_explicit_identity_remaps(self):
        for donor in portable_maria_donors():
            with self.subTest(donor=donor.key):
                output = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))
                attachments = maria_arena_contract(donor)["attachments"]
                self.assertGreater(len(attachments), 0)
                self.assertLessEqual(len(attachments), len(ATTACHMENT_EVENTS))
                for attachment in attachments:
                    body = output[attachment["destination_event"]]
                    self.assertIn(f"$Event({attachment['destination_event']},", body)
                    self.assertIn("3500800", body)
                    self.assertNotIn(str(donor.actor), body)
                    self.assertNotIn(str(donor.completion_event), body)
                    self.assertNotIn(str(donor.start_flag), body)

    def test_donor_health_keeps_maria_room_notification_state_and_drops_foreign_local_flags(self):
        before = event_blocks(self.maria)
        for donor in portable_maria_donors():
            with self.subTest(donor=donor.key):
                after = event_blocks(patch_portable_donor_at_maria(
                    self.maria, donor, self.sources[donor.key], DEFAULT_IDS,
                ))
                health = after[13504802]
                self.assertEqual(before[13504800], after[13504800])
                self.assertEqual(before[13504801], after[13504801])
                self.assertIn("if (!EventFlag(13504810)) {", health)
                self.assertIn("SetEventFlag(13504810, ON);", health)
                self.assertLess(health.index("if (!EventFlag(13504810)) {"),
                                health.index("IssueBossRoomEntryNotification(0);"))
                source_flags = {
                    int(flag) for flag in re.findall(
                        r"\b(?:EventFlag|SetEventFlag)\((\d+)(?:\)|,)",
                        event_blocks(self.sources[donor.key])[donor.health_bar_event],
                    )
                }
                foreign_flags = source_flags - {donor.completion_event, donor.start_flag}
                for flag in foreign_flags:
                    self.assertNotIn(f"EventFlag({flag})", health)
                    self.assertNotIn(f"SetEventFlag({flag},", health)
                health_flags = {
                    int(flag) for flag in re.findall(
                        r"\b(?:EventFlag|SetEventFlag)\((\d+)(?:\)|,)", health,
                    )
                }
                self.assertEqual(
                    {13501800, 13504808, 13504810, ACTIVATION_EVENT}, health_flags,
                )

    def test_allocation_is_absent_from_original_corpus_and_ebrietas_gets_pinned_owner_cleanup(self):
        collisions = set(DEFAULT_IDS.values()).intersection(_original_literals())
        self.assertEqual(8, len(DEFAULT_IDS.values()))
        self.assertEqual(0, len(collisions))
        self.assertEqual((12995000, 12995001, 12995002, 12995003, 12995004), ATTACHMENT_EVENTS)
        self.assertEqual(12995005, OWNER_CLEANUP_EVENT)
        self.assertEqual(12995006, ACTIVATION_EVENT)
        self.assertEqual(982500, BULLET_OWNER_ENTITY)
        output = event_blocks(patch_portable_donor_at_maria(
            self.maria, next(package for package in PACKAGES if package.key == "ebrietas"),
            self.sources["ebrietas"], DEFAULT_IDS,
        ))
        cleanup = output[OWNER_CLEANUP_EVENT]
        self.assertIn("ChangeCharacterEnableState(982500, Disabled)", cleanup)
        self.assertIn("WaitFor(EventFlag(13501800))", cleanup)
        self.assertIn("ForceCharacterDeath(982500, false)", output[OWNER_CLEANUP_EVENT])
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(13501800))"),
            cleanup.index("ChangeCharacterEnableState(982500, Disabled)"),
        )
        self.assertIn("CreateBulletOwner(982500)", output[0])
        self.assertIn(f"$InitializeEvent(0, {OWNER_CLEANUP_EVENT});", output[0])

    def test_native_plans_pin_each_real_source_and_only_ebrietas_adds_a_helper(self):
        for donor in portable_maria_donors():
            with self.subTest(donor=donor.key):
                plan = native_plan_portable_donor_at_maria(
                    donor, self.slots, self.npcs, self.effects, "maria-arena",
                )
                binding = plan["primary_init_source_bindings"]
                self.assertEqual({"m35_00_00_00"}, {row["destination_map"] for row in binding})
                self.assertEqual({"c4520_0002"}, {row["destination_part"] for row in binding})
                if donor is AMYGDALA_PACKAGE:
                    self.assertEqual({"m33_00_00_00"}, {row["source_map"] for row in binding})
                if donor.key == "ebrietas":
                    helpers = plan["boss_actor_addition_requirements"]
                    self.assertEqual({982500}, {row["destination_entity_id"] for row in helpers})
                    self.assertEqual({"c9010_0003"}, {row["source_part"] for row in helpers})
                else:
                    self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_output_compiles_with_the_pinned_darkscript_fixture_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m35_00_00_00.emevd.dcx")
        if not compiler.is_file() or any(not (events / name).is_file() for name in required):
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
                [str(compiler), "/cmd", "-decompile", "-game", "bb", "-indir", str(original),
                 "-outdir", str(source), "-force", "-silent"],
                check=True,
            )
            destination_path = source / "m35_00_00_00.emevd.dcx.js"
            baseline = destination_path.read_text(encoding="utf-8-sig")
            for donor in portable_maria_donors():
                with self.subTest(donor=donor.key):
                    # Other maps are not part of this decompile input.  The source-pinned
                    # bundle body is sufficient because the patcher verifies its hashes.
                    destination_path.write_text(
                        patch_portable_donor_at_maria(baseline, donor, self.sources[donor.key]),
                        encoding="utf-8-sig",
                    )
                    output = work / ("output-" + donor.key)
                    subprocess.run(
                        [str(compiler), "/cmd", "-compile", "-game", "bb", "-indir", str(source),
                         "-outdir", str(output), "-force", "-silent"],
                        check=True,
                    )
                    compiled = output / "m35_00_00_00.emevd.dcx"
                    self.assertTrue(compiled.is_file())
                    self.assertGreater(compiled.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
