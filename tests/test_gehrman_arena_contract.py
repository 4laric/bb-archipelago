import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import PACKAGES
from tools.bb_enemizer.boss_entrances import skip_replacement_entrance
from tools.bb_enemizer.gehrman_arena_contract import (
    ACTIVATION_EVENT,
    ATTACHMENT_EVENTS,
    BULLET_OWNER_ENTITY,
    DEFAULT_IDS,
    DESTINATION_MSB_SHA256,
    DESTINATION_PINS,
    DIALOGUE,
    DONOR_OWNER_CLEANUP_EVENT,
    EVENT_FILE,
    EVENT_TARGET,
    GEHRMAN_ARENA_CONTRACT,
    HEALTH_INITIALIZED_FLAG,
    SOURCE_PART_PINS,
    _original_literals,
    gehrman_arena_contract,
    native_plan_portable_donor_at_gehrman,
    patch_portable_donor_at_gehrman,
    portable_gehrman_donors,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class GehrmanArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.sources = {
            package.key: read_blob(BUNDLE, "event/" + package.event_file).decode("utf-8-sig")
            for package in PACKAGES
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self, donor):
        return patch_portable_donor_at_gehrman(
            self.destination, donor, self.sources[donor.key]
        )

    def test_api_allocation_and_all_six_are_data_driven(self):
        self.assertEqual("gehrman", GEHRMAN_ARENA_CONTRACT.key)
        self.assertEqual((12104807, 12104808), GEHRMAN_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual({package.key for package in PACKAGES},
                         {package.key for package in portable_gehrman_donors()})
        self.assertEqual((12996100, 12996101, 12996102, 12996103, 12996104),
                         ATTACHMENT_EVENTS)
        self.assertEqual((12996105, 12996106, 12996107, 983600),
                         (ACTIVATION_EVENT, DONOR_OWNER_CLEANUP_EVENT,
                          HEALTH_INITIALIZED_FLAG, BULLET_OWNER_ENTITY))
        self.assertFalse(set(DEFAULT_IDS.values()) & _original_literals())
        # Adjacent reusable-final-donor allocation is deliberately separate.
        self.assertFalse(set(DEFAULT_IDS.values()) & set(range(12996000, 12996007)))
        self.assertNotEqual(983500, BULLET_OWNER_ENTITY)
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            patch_portable_donor_at_gehrman(
                self.destination, PACKAGES[0], self.sources[PACKAGES[0].key],
                replace(DEFAULT_IDS, activation_event=12996108),
            )

    def test_destination_terminal_entry_client_progression_and_npc_are_exact(self):
        before = event_blocks(self.destination)
        preserved = (12101800, 12101801, 12101802, 12101803,
                     12104805, 12104810, 12104811,
                     12101850, 12101852, 12101853)
        for donor in portable_gehrman_donors():
            after = event_blocks(self.patched(donor))
            for event_id in preserved:
                self.assertEqual(before[event_id], after[event_id],
                                 (donor.key, event_id))
            self.assertIn("WaitFor(EventFlag(72100131))", after[12101802])
            self.assertIn("PlayCutsceneAndWarpPlayer(21000040", after[12101802])
            self.assertIn("2102808, 21, 0, 10000", after[12101802])
            self.assertIn("ChangeCharacterEnableState(2100600, Disabled)",
                          after[12101802])
            self.assertIn("SetCharacterHPBarDisplay(2100600, Disabled)", after[0])
            self.assertEqual(1, after[0].count("$InitializeEvent(0, 12101803);"))
            self.assertEqual(1, after[0].count(f"$InitializeEvent(0, {ACTIVATION_EVENT});"))
            for retired in (12104807, 12104808):
                self.assertEqual(
                    f"$Event({retired}, Default, function() {{\n    EndEvent();\n}});",
                    after[retired],
                )

    def test_fresh_and_saved_health_wait_for_wake_and_own_notification_once(self):
        for donor in portable_gehrman_donors():
            blocks = event_blocks(self.patched(donor))
            health = blocks[12104802]
            self.assertEqual(2, health.count(f"WaitFor(EventFlag({ACTIVATION_EVENT}));"),
                             donor.key)
            self.assertEqual(1, health.count("IssueBossRoomEntryNotification(0)"))
            self.assertIn(f"if (!EventFlag({HEALTH_INITIALIZED_FLAG}))", health)
            self.assertIn(f"SetEventFlag({HEALTH_INITIALIZED_FLAG}, ON)", health)
            self.assertIn("SetEventFlag(12104800, ON)", health)
            self.assertIn("CreatePlaylog(64)", health)
            self.assertIn("StartTimeMeasurement(2100010, 80, Enabled)", health)
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, 2100800, 0, {donor.health_bar_label})",
                health,
            )
            self.assertNotIn("SetCharacterEventTarget(2100800, 2100801)", health)
            self.assertNotIn("CreateReferredDamagePair", health)
            self.assertNotIn("12404223", health)
            self.assertLess(health.index(f"WaitFor(EventFlag({ACTIVATION_EVENT}));"),
                            health.index("SetCharacterAIState(2100800, Enabled)"))

    def test_source_wakes_and_central_cinematic_policy_keep_trigger_and_warp(self):
        expected = {
            "blood-starved-beast": "ForceAnimationPlayback(2100800, 7001",
            "darkbeast-paarl": "SetCharacterInvincibility(2100800, Enabled)",
            "cleric-beast": "SetCharacterGravity(2100800, Disabled)",
            "vicar-amelia": "ForceAnimationPlayback(2100800, 7000",
            "amygdala": "SetCharacterMaphits(2100800, true)",
            "ebrietas": "SetCharacterImmortality(2100800, Enabled)",
        }
        for donor in portable_gehrman_donors():
            patched = self.patched(donor)
            blocks = event_blocks(patched)
            wake = blocks[ACTIVATION_EVENT]
            self.assertIn("WaitFor(EventFlag(12104800))", wake)
            self.assertIn(expected[donor.key], wake)
            self.assertLess(
                wake.index("SetCharacterInvincibility(2100800, Enabled)"),
                wake.index("WaitFor(EventFlag(12104800))"),
            )
            self.assertGreater(
                wake.rindex("SetCharacterInvincibility(2100800, Disabled)"),
                wake.index("WaitFor(EventFlag(12104800))"),
            )
            if donor.key == "ebrietas":
                self.assertLess(
                    wake.index("SetCharacterInvincibility(2100800, Disabled)"),
                    wake.index("WaitFor(HasDamageType(2100800, 10000"),
                )
                self.assertLess(
                    wake.index("SetCharacterImmortality(2100800, Enabled)"),
                    wake.index("SetCharacterInvincibility(2100800, Disabled)"),
                )
            normalized = event_blocks(skip_replacement_entrance(
                "gehrman", self.destination, patched
            ))
            entry = normalized[12101802]
            self.assertIn("WaitFor(EventFlag(72100131))", entry)
            self.assertIn(
                "IssueShortWarpRequest(10000, TargetEntityType.Area, 2102808, -1)",
                entry,
            )
            self.assertNotIn("PlayCutsceneAndWarpPlayer", entry)
            self.assertIn("SetEventFlag(12104800, ON)", entry)

    def test_music_camera_and_owner_cleanup_use_destination_geometry(self):
        for donor in portable_gehrman_donors():
            blocks = event_blocks(self.patched(donor))
            music = blocks[12104803]
            signal = donor.music_phase_signals[-1]
            if signal.kind == "message":
                self.assertIn(
                    f"CharacterHasEventMessage(2100800, {signal.message})", music
                )
                if signal.message != 100:
                    self.assertNotIn("CharacterHasEventMessage(2100800, 100)", music)
            else:
                self.assertNotIn("CharacterHasEventMessage(2100800, 100)", music)
                row = next(row for row in gehrman_arena_contract(donor)["attachments"]
                           if row["source_event"] == signal.source_event)
                self.assertIn(f"EventFlag({row['destination_event']})", music)
            self.assertIn("L0:", music)
            self.assertIn("EnableBossMapSound(2103803, Enabled)", music)
            camera = blocks[12104804]
            self.assertIn("SetLockcamSlotNumber(21, 0,", camera)
            self.assertIn("EndIf(EventFlag(12101800))", camera)
            if donor.key == "ebrietas":
                cleanup = blocks[DONOR_OWNER_CLEANUP_EVENT]
                self.assertLess(cleanup.index("WaitFor(EventFlag(12101800))"),
                                cleanup.index("ForceCharacterDeath(983600, false)"))
            else:
                self.assertNotIn(DONOR_OWNER_CLEANUP_EVENT, blocks)

    def test_native_plan_pins_primary_dialogue_event_target_and_added_owner(self):
        for donor in portable_gehrman_donors():
            plan = native_plan_portable_donor_at_gehrman(
                donor, self.slots, self.npcs, self.effects, "gehrman-arena"
            )
            binding = plan["primary_init_source_bindings"][0]
            self.assertEqual("m21_00_00_00", binding["destination_map"])
            self.assertEqual(210306, binding["destination_original_talk_id"])
            self.assertEqual(SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                             binding["source_provenance"]["part_sha256"])
            self.assertEqual({"talk_id": 0, "unk_t18": -1,
                              "init_anim_id": -1, "damage_anim_id": -1},
                             binding["source_initialization"])
            self.assertEqual(1, plan["swap_count"])
            self.assertEqual(1, plan["scaling"]["change_count"])
            retained = plan["boss_contract"]["retained_destination_helpers"]
            self.assertEqual({DIALOGUE, EVENT_TARGET},
                             {row["entity_id"] for row in retained})
            for row in retained:
                self.assertEqual(DESTINATION_PINS[row["entity_id"]],
                                 row["source_provenance"]["part_sha256"])
            dialogue = next(row for row in retained if row["entity_id"] == DIALOGUE)
            self.assertEqual(210305, dialogue["source_initialization"]["talk_id"])
            if donor.key == "ebrietas":
                self.assertEqual({BULLET_OWNER_ENTITY}, {
                    row["destination_entity_id"]
                    for row in plan["boss_actor_addition_requirements"]
                })
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)
            self.assertEqual(DESTINATION_MSB_SHA256,
                             plan["boss_contract"]["destination_native_evidence"]["msb_sha256"])

    def test_all_original_inputs_patch_and_compile(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {
            "common.emevd.dcx", "m21_00_00_00.emevd.dcx",
            *(package.event_file.removesuffix(".js") for package in PACKAGES),
        }
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
            subprocess.run([
                str(compiler), "/cmd", "-decompile", "-game", "bb",
                "-indir", str(original), "-outdir", str(source), "-force", "-silent",
            ], check=True)
            destination_path = source / EVENT_FILE
            baseline = destination_path.read_text(encoding="utf-8-sig")
            for donor in portable_gehrman_donors():
                donor_source = (source / donor.event_file).read_text(encoding="utf-8-sig")
                patched = patch_portable_donor_at_gehrman(
                    baseline, donor, donor_source
                )
                patched = skip_replacement_entrance("gehrman", baseline, patched)
                destination_path.write_text(patched, encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([
                    str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent",
                ], check=True)
                self.assertTrue((output / "m21_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
