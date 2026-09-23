import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import PACKAGES
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.logarius_arena_contract import (
    ACTIVATION_EVENT, ATTACHMENT_EVENTS, BULLET_OWNER_ENTITY,
    CLIENT_RESTORE_EVENT, DEFAULT_IDS, DESTINATION_PINS, EVENT_FILE,
    HELPER_LIFECYCLE_EVENT, LOGARIUS_ARENA_CONTRACT, SOURCE_PART_PINS,
    _original_literals, logarius_arena_contract,
    native_plan_portable_donor_at_logarius, patch_portable_donor_at_logarius,
    portable_logarius_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class LogariusArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.sources = {p.key: read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
                       for p in PACKAGES}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_contract_and_allocations_cover_all_six_without_pair_whitelist(self):
        self.assertEqual("martyr-logarius", LOGARIUS_ARENA_CONTRACT.key)
        self.assertEqual((12504806, 12504807, 12504808),
                         LOGARIUS_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual({p.key for p in PACKAGES},
                         {p.key for p in portable_logarius_donors()})
        self.assertEqual(0, len(set(DEFAULT_IDS.values()) & _original_literals()))
        self.assertEqual((12995400, 12995401, 12995402, 12995403, 12995404),
                         ATTACHMENT_EVENTS)
        self.assertEqual((12995406, 12995407, 12995408, 982900),
                         (ACTIVATION_EVENT, CLIENT_RESTORE_EVENT,
                          HELPER_LIFECYCLE_EVENT, BULLET_OWNER_ENTITY))

    def test_terminal_fog_postboss_and_music_cleanup_remain_byte_exact(self):
        before = event_blocks(self.destination)
        for donor in portable_logarius_donors():
            after = event_blocks(patch_portable_donor_at_logarius(
                self.destination, donor, self.sources[donor.key]))
            for event_id in (12501800, 12501801, 12501803, 12504805,
                             12504810, 12504811):
                self.assertEqual(before[event_id], after[event_id], donor.key)
            self.assertNotIn("ForceAnimationPlayback(2500800, 7000", after[12501802])
            self.assertIn("PlayCutsceneToPlayer(25000020", after[12501802])
            for event_id in (12504806, 12504807, 12504808):
                self.assertEqual(f"$Event({event_id}, Default, function() {{\n    EndEvent();\n}});",
                                 after[event_id])
            self.assertEqual(2, after[0].count("$InitializeEvent(0, 12504806);"))

    def test_health_readiness_notification_telemetry_music_and_camera_are_adapted(self):
        for donor in portable_logarius_donors():
            blocks = event_blocks(patch_portable_donor_at_logarius(
                self.destination, donor, self.sources[donor.key]))
            health = blocks[12504802]
            self.assertIn(f"WaitFor(EventFlag({ACTIVATION_EVENT}));", health)
            self.assertIn("if (!EventFlag(12504223))", health)
            self.assertIn("SetEventFlag(12504223, ON)", health)
            self.assertIn("CreatePlaylog(82)", health)
            self.assertIn("StartTimeMeasurement(2500010, 98, Enabled)", health)
            self.assertIn(f"DisplayBossHealthBar(Enabled, 2500800, 0, {donor.health_bar_label})", health)
            self.assertNotIn("CharacterHasSpEffect(2500800, 5633)", blocks[12504803])
            self.assertIn("SetLockcamSlotNumber(25, 0,", blocks[12504804])
            self.assertNotIn("2500801", blocks[12504804])
            flags = set(map(int, re.findall(r"(?:EventFlag|SetEventFlag)\((\d+)", health)))
            self.assertEqual({12501800, 12504223, 12504800, ACTIVATION_EVENT}, flags)

    def test_client_restore_is_source_pinned_and_preserves_donor_specific_state(self):
        expected = {
            "blood-starved-beast": None,
            "darkbeast-paarl": "SetCharacterInvincibility(2500800, Disabled)",
            "cleric-beast": "ChangeCharacterEnableState(2500800, Enabled)",
            "vicar-amelia": "ChangeCharacterEnableState(2500800, Enabled)",
            "amygdala": None,
            "ebrietas": None,
        }
        for donor in portable_logarius_donors():
            blocks = event_blocks(patch_portable_donor_at_logarius(
                self.destination, donor, self.sources[donor.key]))
            restore = blocks[CLIENT_RESTORE_EVENT]
            self.assertIn("EventFlag(12504800)", restore)
            self.assertIn("SetEventFlag(12501802, ON)", restore)
            if expected[donor.key]:
                self.assertIn(expected[donor.key], restore)
            self.assertEqual(CLIENT_RESTORE_EVENT,
                             logarius_arena_contract(donor)["client_restore_event"])

    def test_inert_helpers_cannot_affect_live_combat_and_cleanup_completed_reload(self):
        for donor in portable_logarius_donors():
            blocks = event_blocks(patch_portable_donor_at_logarius(
                self.destination, donor, self.sources[donor.key]))
            life = blocks[HELPER_LIFECYCLE_EVENT]
            for entity in (2500801, 2500802):
                self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled)", life)
                self.assertIn(f"ForceCharacterDeath({entity}, false)", life)
            self.assertIn("SetCharacterImmortality(2500801, Enabled)", life)
            self.assertIn("GotoIf(L0, EventFlag(12501800))", life)
            self.assertLess(life.index("WaitFor(EventFlag(12501800))"),
                            life.index("ForceCharacterDeath(2500801, false)"))
            self.assertNotIn("2500801", blocks[12504802])
            self.assertNotIn("2500802", blocks[12504802])

    def test_native_plan_has_authored_primary_and_both_retained_helper_pins(self):
        for donor in portable_logarius_donors():
            plan = native_plan_portable_donor_at_logarius(
                donor, self.slots, self.npcs, self.effects, "logarius-arena")
            binding = plan["primary_init_source_bindings"][0]
            self.assertEqual("m25_00_00_00", binding["destination_map"])
            self.assertEqual(SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                             binding["source_provenance"]["part_sha256"])
            self.assertEqual({"talk_id": 0, "unk_t18": -1,
                              "init_anim_id": -1, "damage_anim_id": -1},
                             binding["source_initialization"])
            retained = plan["boss_contract"]["retained_destination_helpers"]
            self.assertEqual({2500801, 2500802}, {row["entity_id"] for row in retained})
            for row in retained:
                self.assertEqual(DESTINATION_PINS[row["entity_id"]],
                                 row["source_provenance"]["part_sha256"])
            if donor.key == "ebrietas":
                self.assertEqual({982900},
                    {row["destination_entity_id"] for row in plan["boss_actor_addition_requirements"]})
                blocks = event_blocks(patch_portable_donor_at_logarius(
                    self.destination, donor, self.sources[donor.key]))
                self.assertIn("CreateBulletOwner(982900);", blocks[0])
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_all_attachments_install_and_all_outputs_compile_with_pinned_fixture(self):
        for donor in portable_logarius_donors():
            blocks = event_blocks(patch_portable_donor_at_logarius(
                self.destination, donor, self.sources[donor.key]))
            for row in logarius_arena_contract(donor)["attachments"]:
                self.assertIn(f"$Event({row['destination_event']},",
                              blocks[row["destination_event"]])
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m25_00_00_00.emevd.dcx")
        if not compiler.is_file() or any(not (events / name).is_file() for name in required):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual("c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
                         hashlib.sha256(compiler.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original, source = work / "original", work / "source"
            original.mkdir()
            for name in required:
                shutil.copyfile(events / name, original / name)
            subprocess.run([str(compiler), "/cmd", "-decompile", "-game", "bb",
                "-indir", str(original), "-outdir", str(source), "-force", "-silent"], check=True)
            path = source / EVENT_FILE
            baseline = path.read_text(encoding="utf-8-sig")
            for donor in portable_logarius_donors():
                path.write_text(patch_portable_donor_at_logarius(
                    baseline, donor, self.sources[donor.key]), encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent"], check=True)
                self.assertTrue((output / "m25_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
