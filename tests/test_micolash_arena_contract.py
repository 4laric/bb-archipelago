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
from tools.bb_enemizer.boss_entrances import skip_replacement_entrance
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.micolash_arena_contract import (
    ACTIVATION_EVENT, ATTACHMENT_EVENTS, BULLET_OWNER_ENTITY, CHASE_EVENTS,
    DEFAULT_IDS, DESTINATION_MSB_SHA256, DONOR_OWNER_CLEANUP_EVENT,
    EVENT_FILE, MICOLASH_ARENA_CONTRACT, MICOLASH_PIN, SOURCE_PART_PINS,
    TERMINAL_BRIDGE_EVENT, _original_literals, micolash_arena_contract,
    native_plan_portable_donor_at_micolash, patch_portable_donor_at_micolash,
    portable_micolash_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class MicolashArenaContractTests(unittest.TestCase):
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
        return patch_portable_donor_at_micolash(
            self.destination, donor, self.sources[donor.key]
        )

    def test_contract_allocation_and_initial_area_policy_cover_all_six(self):
        self.assertEqual("micolash", MICOLASH_ARENA_CONTRACT.key)
        self.assertEqual(tuple(CHASE_EVENTS), MICOLASH_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual({package.key for package in PACKAGES},
                         {package.key for package in portable_micolash_donors()})
        self.assertEqual((12996300, 12996301, 12996302, 12996303, 12996304),
                         ATTACHMENT_EVENTS)
        self.assertEqual((12996305, 12996306, 12996307, 983800),
                         (ACTIVATION_EVENT, TERMINAL_BRIDGE_EVENT,
                          DONOR_OWNER_CLEANUP_EVENT, BULLET_OWNER_ENTITY))
        self.assertFalse(set(DEFAULT_IDS.values()) & _original_literals())
        for donor in portable_micolash_donors():
            metadata = micolash_arena_contract(donor)
            self.assertEqual("original-initial-area-direct-fight",
                             metadata["placement_policy"])
            self.assertIn("2602851/2602852", metadata["placement_evidence"])
            self.assertEqual(list(CHASE_EVENTS),
                             metadata["disabled_destination_chase_events"])
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            patch_portable_donor_at_micolash(
                self.destination, PACKAGES[0], self.sources[PACKAGES[0].key],
                replace(DEFAULT_IDS, bullet_owner_entity=983801),
            )

    def test_terminal_entry_client_postboss_and_unrelated_encounter_stay_exact(self):
        before = event_blocks(self.destination)
        preserved = (12601850, 12601852, 12601854, 12601855,
                     12604855, 12604860, 12604861,
                     12601800, 12604802, 12604803, 12604804)
        for donor in portable_micolash_donors():
            after = event_blocks(self.patched(donor))
            for event_id in preserved:
                self.assertEqual(before[event_id], after[event_id],
                                 (donor.key, event_id))
            terminal = after[12601850]
            self.assertLess(terminal.index("WaitFor(CharacterDead(2600850))"),
                            terminal.index("WaitFor(EventFlag(72600301))"))
            bridge = after[TERMINAL_BRIDGE_EVENT]
            self.assertLess(bridge.index("WaitFor(CharacterDead(2600850))"),
                            bridge.index("SetEventFlag(72600301, ON)"))
            self.assertIn("IssueBossRoomEntryNotification(0)", after[12601852])
            self.assertIn("SetEventFlag(12604850, ON)", after[12601852])
            self.assertIn("SetEventFlag(12601852, ON)", after[12601855])

    def test_chase_graph_is_inert_without_completing_event_flags(self):
        for donor in portable_micolash_donors():
            blocks = event_blocks(self.patched(donor))
            for event_id in CHASE_EVENTS:
                body = blocks[event_id]
                self.assertIn("WaitFor(InArea(10000, 0))", body)
                self.assertNotIn("SetEventFlag(", body)
                self.assertNotIn("2600850", body)
            self.assertEqual(1, blocks[0].count("$InitializeEvent(0, 12604879);"))
            # Destination post-boss logic deliberately still sees the unset
            # 12604879 flag and chooses its original branch.
            self.assertIn("EventFlag(12604879)", blocks[12601854])

    def test_health_readiness_notification_telemetry_and_wake_are_source_backed(self):
        expected = {
            "blood-starved-beast": "ForceAnimationPlayback(2600850, 7001",
            "darkbeast-paarl": "WaitFixedTimeFrames(70)",
            "cleric-beast": "ForceAnimationPlayback(2600850, 3028",
            "vicar-amelia": "ForceAnimationPlayback(2600850, 7000",
            "amygdala": "ForceAnimationPlayback(2600850, 7006",
            "ebrietas": "SetCharacterImmortality(2600850, Enabled)",
        }
        for donor in portable_micolash_donors():
            blocks = event_blocks(self.patched(donor))
            health = blocks[12604852]
            self.assertEqual(2, health.count(f"WaitFor(EventFlag({ACTIVATION_EVENT}))"))
            self.assertNotIn("IssueBossRoomEntryNotification", health)
            self.assertIn("CreatePlaylog(88)", health)
            self.assertIn("StartTimeMeasurement(2601010, 232, Enabled)", health)
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, 2600850, 0, {donor.health_bar_label})",
                health,
            )
            wake = blocks[ACTIVATION_EVENT]
            self.assertIn(expected[donor.key], wake)
            self.assertLess(wake.index("SetCharacterInvincibility(2600850, Enabled)"),
                            wake.index("WaitFor(EventFlag(12604850))"))
            self.assertGreater(
                wake.rindex("SetCharacterInvincibility(2600850, Disabled)"),
                wake.index("WaitFor(EventFlag(12604850))"),
            )
            if donor.key == "ebrietas":
                self.assertLess(
                    wake.index("SetCharacterInvincibility(2600850, Disabled)"),
                    wake.index("WaitFor(HasDamageType(2600850, 10000"),
                )
            self.assertLess(blocks[0].index(f"SetEventFlag({ACTIVATION_EVENT}, OFF)"),
                            blocks[0].index(f"$InitializeEvent(0, {ACTIVATION_EVENT})"))
            normalized = event_blocks(skip_replacement_entrance(
                "micolash", self.destination, self.patched(donor)
            ))
            self.assertNotIn("PlayCutsceneToPlayer", normalized[12601852])
            self.assertIn("EntityInRadiusOfEntity(10000, 2600850, 32)",
                          normalized[12601852])
            self.assertIn("SetEventFlag(12604850, ON)", normalized[12601852])

    def test_music_camera_attachments_and_owner_cleanup_use_destination_state(self):
        for donor in portable_micolash_donors():
            blocks = event_blocks(self.patched(donor))
            signal = donor.music_phase_signals[-1]
            music = blocks[12604853]
            if signal.kind == "message":
                self.assertIn(
                    f"WaitFor(CharacterHasEventMessage(2600850, {signal.message}))",
                    music,
                )
            else:
                attachment = next(
                    row for row in micolash_arena_contract(donor)["attachments"]
                    if row["source_event"] == signal.source_event
                )
                self.assertIn(f"WaitFor(EventFlag({attachment['destination_event']}))",
                              music)
            self.assertIn("L0:", music)
            self.assertIn("EnableBossMapSound(2603853, Enabled)", music)
            camera = blocks[12604854]
            self.assertIn("SetLockcamSlotNumber(26, 0,", camera)
            self.assertIn("EndIf(EventFlag(12601850))", camera)
            for row in micolash_arena_contract(donor)["attachments"]:
                self.assertIn(f"$Event({row['destination_event']},",
                              blocks[row["destination_event"]])
            if donor.key == "ebrietas":
                cleanup = blocks[DONOR_OWNER_CLEANUP_EVENT]
                self.assertLess(cleanup.index("WaitFor(EventFlag(12601850))"),
                                cleanup.index("ForceCharacterDeath(983800, false)"))
                self.assertIn("CreateBulletOwner(983800)", blocks[0])
            else:
                self.assertNotIn(DONOR_OWNER_CLEANUP_EVENT, blocks)

    def test_native_plan_pins_source_primary_talk_override_and_scaling(self):
        for donor in portable_micolash_donors():
            plan = native_plan_portable_donor_at_micolash(
                donor, self.slots, self.npcs, self.effects, "micolash-arena"
            )
            self.assertEqual(1, plan["swap_count"])
            self.assertEqual(1, plan["scaling"]["change_count"])
            binding = plan["primary_init_source_bindings"][0]
            self.assertEqual("m26_00_00_00", binding["destination_map"])
            self.assertEqual(260311, binding["destination_original_talk_id"])
            self.assertEqual(0, binding["destination_talk_id_override"])
            self.assertIn("destination_talk_id_override",
                          binding["required_native_fields"])
            self.assertEqual(SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                             binding["source_provenance"]["part_sha256"])
            self.assertEqual({"talk_id": 0, "unk_t18": -1,
                              "init_anim_id": -1, "damage_anim_id": -1},
                             binding["source_initialization"])
            evidence = plan["boss_contract"]["destination_native_evidence"]
            self.assertEqual(DESTINATION_MSB_SHA256, evidence["msb_sha256"])
            self.assertEqual(MICOLASH_PIN, evidence["primary_part_sha256"])
            self.assertEqual(
                0, len(plan["boss_contract"]["retained_destination_helpers"])
            )
            if donor.key == "ebrietas":
                self.assertEqual({BULLET_OWNER_ENTITY}, {
                    row["destination_entity_id"]
                    for row in plan["boss_actor_addition_requirements"]
                })
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_all_original_inputs_patch_and_compile_with_pinned_fixture(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {
            "common.emevd.dcx", "m26_00_00_00.emevd.dcx",
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
            for donor in portable_micolash_donors():
                donor_source = (source / donor.event_file).read_text(encoding="utf-8-sig")
                patched = patch_portable_donor_at_micolash(
                    baseline, donor, donor_source
                )
                patched = skip_replacement_entrance("micolash", baseline, patched)
                destination_path.write_text(patched, encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([
                    str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent",
                ], check=True)
                self.assertTrue((output / "m26_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
