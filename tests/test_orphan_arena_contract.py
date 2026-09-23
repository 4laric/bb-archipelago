import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import PACKAGES
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.orphan_arena_contract import (
    ACTIVATION_EVENT, ATTACHMENT_EVENTS, BULLET_OWNER_ENTITY,
    CLIENT_RESTORE_EVENT, DEFAULT_IDS, DESTINATION_PINS, EVENT_FILE,
    DONOR_OWNER_CLEANUP_EVENT, HELPER_LIFECYCLE_EVENT, ORPHAN_ARENA_CONTRACT,
    PHASE, SHADOW, SOURCE_PART_PINS, SUPPORT,
    _original_literals, orphan_arena_contract,
    native_plan_portable_donor_at_orphan, patch_portable_donor_at_orphan,
    portable_orphan_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class OrphanArenaContractTests(unittest.TestCase):
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
        self.assertEqual("orphan-of-kos", ORPHAN_ARENA_CONTRACT.key)
        self.assertEqual((13604820, 13604830, 13604840, 13604850),
                         ORPHAN_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual({p.key for p in PACKAGES},
                         {p.key for p in portable_orphan_donors()})
        self.assertEqual(0, len(set(DEFAULT_IDS.values()) & _original_literals()))
        self.assertEqual((12995700, 12995701, 12995702, 12995703, 12995704),
                         ATTACHMENT_EVENTS)
        self.assertEqual((12995705, 12995706, 12995707, 12995708, 983200),
                         (ACTIVATION_EVENT, CLIENT_RESTORE_EVENT,
                          HELPER_LIFECYCLE_EVENT, DONOR_OWNER_CLEANUP_EVENT,
                          BULLET_OWNER_ENTITY))
        # Only the exact helper is allocated; original IDs exist elsewhere in
        # the surrounding 9832xx range.
        self.assertNotIn(983200, _original_literals())
        self.assertIn(983213, _original_literals())
        self.assertIn(983242, _original_literals())
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            patch_portable_donor_at_orphan(
                self.destination, PACKAGES[0], self.sources[PACKAGES[0].key],
                replace(DEFAULT_IDS, bullet_owner_entity=983201),
            )
        with self.assertRaisesRegex(ValueError, "Orphan arena event 13601800"):
            patch_portable_donor_at_orphan(
                self.destination.replace("AwardAchievement(35)", "AwardAchievement(34)"),
                PACKAGES[0], self.sources[PACKAGES[0].key],
            )

    def test_terminal_fog_postboss_and_music_cleanup_remain_byte_exact(self):
        before = event_blocks(self.destination)
        for donor in portable_orphan_donors():
            after = event_blocks(patch_portable_donor_at_orphan(
                self.destination, donor, self.sources[donor.key]))
            for event_id in (13601800, 13601801, 13601802, 13601803,
                             13601804, 13604800, 13604801, 13604805,
                             13604806, 13604807, 13604811):
                self.assertEqual(before[event_id], after[event_id], donor.key)
            self.assertIn("PlayCutsceneToPlayer(36000000", after[13601801])
            for event_id in (13604820, 13604830, 13604840, 13604850):
                self.assertEqual(f"$Event({event_id}, Default, function() {{\n    EndEvent();\n}});",
                                 after[event_id])
            self.assertEqual(1, after[0].count("$InitializeEvent(0, 13604820);"))
            self.assertEqual(1, after[0].count("$InitializeEvent(0, 13604804);"))
            self.assertLess(after[0].index(f"SetEventFlag({ACTIVATION_EVENT}, OFF)"),
                            after[0].index(f"$InitializeEvent(0, {ACTIVATION_EVENT})"))

    def test_health_readiness_notification_telemetry_music_and_camera_are_adapted(self):
        for donor in portable_orphan_donors():
            blocks = event_blocks(patch_portable_donor_at_orphan(
                self.destination, donor, self.sources[donor.key]))
            health = blocks[13604802]
            self.assertEqual(2, health.count(f"WaitFor(EventFlag({ACTIVATION_EVENT}));"))
            self.assertIn("if (!EventFlag(13604810))", health)
            self.assertIn("SetEventFlag(13604810, ON)", health)
            self.assertIn("SetEventFlag(13604812, ON)", health)
            self.assertIn("CreatePlaylog(42)", health)
            self.assertIn("StartTimeMeasurement(3600010, 58, Enabled)", health)
            self.assertIn(f"DisplayBossHealthBar(Enabled, 3600800, 0, {donor.health_bar_label})", health)
            self.assertNotIn("EventFlag(13604820)", blocks[13604803])
            self.assertIn("EventFlag(13604812)", blocks[13604803])
            self.assertIn("SetLockcamSlotNumber(36, 0,", blocks[13604804])
            self.assertIn("EndIf(EventFlag(13601800))", blocks[13604804])
            self.assertNotIn("3600801", blocks[13604804])
            flags = set(map(int, re.findall(r"(?:EventFlag|SetEventFlag)\((\d+)", health)))
            self.assertEqual({13601800, 13604808, 13604810, 13604812,
                              ACTIVATION_EVENT}, flags)

    def test_client_restore_is_source_pinned_and_preserves_donor_specific_state(self):
        expected = {
            "blood-starved-beast": None,
            "darkbeast-paarl": "SetCharacterInvincibility(3600800, Disabled)",
            "cleric-beast": "ChangeCharacterEnableState(3600800, Enabled)",
            "vicar-amelia": "ChangeCharacterEnableState(3600800, Enabled)",
            "amygdala": None,
            "ebrietas": None,
        }
        for donor in portable_orphan_donors():
            blocks = event_blocks(patch_portable_donor_at_orphan(
                self.destination, donor, self.sources[donor.key]))
            restore = blocks[CLIENT_RESTORE_EVENT]
            self.assertIn("EventFlag(13604808)", restore)
            self.assertIn("SetEventFlag(13601801, ON)", restore)
            if expected[donor.key]:
                self.assertIn(expected[donor.key], restore)
            self.assertEqual(CLIENT_RESTORE_EVENT,
                             orphan_arena_contract(donor)["client_restore_event"])

    def test_inert_helpers_cannot_affect_live_combat_and_cleanup_completed_reload(self):
        for donor in portable_orphan_donors():
            blocks = event_blocks(patch_portable_donor_at_orphan(
                self.destination, donor, self.sources[donor.key]))
            life = blocks[HELPER_LIFECYCLE_EVENT]
            for entity in (3600801, 3600803):
                self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled)", life)
                self.assertIn(f"ForceCharacterDeath({entity}, false)", life)
            self.assertIn("SetCharacterInvincibility(3600801, Enabled)", life)
            self.assertIn("GotoIf(L0, EventFlag(13601800))", life)
            self.assertLess(life.index("WaitFor(EventFlag(13601800))"),
                            life.index("ForceCharacterDeath(3600801, false)"))
            self.assertNotIn("3600801", blocks[13604802])
            self.assertNotIn("3600803", blocks[13604802])
            self.assertNotIn("3600802", life)

    def test_native_plan_has_authored_primary_and_all_destination_actor_pins(self):
        for donor in portable_orphan_donors():
            plan = native_plan_portable_donor_at_orphan(
                donor, self.slots, self.npcs, self.effects, "orphan-arena")
            binding = plan["primary_init_source_bindings"][0]
            self.assertEqual("m36_00_00_00", binding["destination_map"])
            self.assertEqual(SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                             binding["source_provenance"]["part_sha256"])
            self.assertEqual({"talk_id": 0, "unk_t18": -1,
                              "init_anim_id": -1, "damage_anim_id": -1},
                             binding["source_initialization"])
            retained = plan["boss_contract"]["retained_destination_helpers"]
            self.assertEqual({PHASE, SHADOW, SUPPORT},
                             {row["entity_id"] for row in retained})
            for row in retained:
                self.assertEqual(DESTINATION_PINS[row["entity_id"]],
                                 row["source_provenance"]["part_sha256"])
            if donor.key == "ebrietas":
                self.assertEqual({983200},
                    {row["destination_entity_id"] for row in plan["boss_actor_addition_requirements"]})
                blocks = event_blocks(patch_portable_donor_at_orphan(
                    self.destination, donor, self.sources[donor.key]))
                self.assertIn("CreateBulletOwner(983200);", blocks[0])
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_all_attachments_install_and_all_outputs_compile_with_pinned_fixture(self):
        for donor in portable_orphan_donors():
            blocks = event_blocks(patch_portable_donor_at_orphan(
                self.destination, donor, self.sources[donor.key]))
            for row in orphan_arena_contract(donor)["attachments"]:
                self.assertIn(f"$Event({row['destination_event']},",
                              blocks[row["destination_event"]])
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {"common.emevd.dcx", "m36_00_00_00.emevd.dcx",
                    *(package.event_file.removesuffix(".js") for package in PACKAGES)}
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
            for donor in portable_orphan_donors():
                path.write_text(patch_portable_donor_at_orphan(
                    baseline, donor,
                    (source / donor.event_file).read_text(encoding="utf-8-sig")),
                    encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent"], check=True)
                self.assertTrue((output / "m36_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()


