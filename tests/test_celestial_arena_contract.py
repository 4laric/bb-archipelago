import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer import celestial_paarl_contract as ce
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import PACKAGES
from tools.bb_enemizer.celestial_arena_contract import (
    ACTIVATION_EVENT,
    ATTACHMENT_EVENTS,
    BUNDLE,
    BULLET_OWNER_ENTITY,
    CAMERA_EVENT,
    DEFAULT_IDS,
    DESTINATION_CLEANUP_EVENT,
    EBRIETAS_EVENTS,
    EVENT_FILE,
    GENERATORS,
    GIANT,
    MAP_STATES,
    MUSIC_EVENT,
    OWNER_CLEANUP_EVENT,
    PRIMARY,
    SOURCE_PART_PINS,
    START_FLAG,
    SUPPORT,
    SUPPRESSED_EVENTS,
    TERMINAL,
    TERMINAL_BRIDGE_EVENT,
    WAVES,
    CelestialArenaIds,
    celestial_arena_contract,
    native_plan_portable_donor_at_celestial_emissary,
    patch_portable_donor_at_celestial_emissary,
    portable_celestial_donors,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]


class CelestialArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(
            BUNDLE, "event/" + EVENT_FILE
        ).decode("utf-8-sig").replace("\r\n", "\n")
        cls.sources = {
            donor.key: read_blob(BUNDLE, "event/" + donor.event_file)
            .decode("utf-8-sig").replace("\r\n", "\n")
            for donor in PACKAGES
        }
        with tempfile.TemporaryDirectory() as directory:
            slots_file = Path(directory) / "slots.tsv"
            slots_file.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(slots_file)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self, donor):
        return event_blocks(patch_portable_donor_at_celestial_emissary(
            self.destination, donor, self.sources[donor.key]
        ))

    def test_all_six_packages_preserve_exact_terminal_and_bridge_actual_death(self):
        original = event_blocks(self.destination)
        self.assertEqual(
            ["blood-starved-beast", "darkbeast-paarl", "cleric-beast",
             "vicar-amelia", "amygdala", "ebrietas"],
            [donor.key for donor in portable_celestial_donors()],
        )
        for donor in portable_celestial_donors():
            after = self.patched(donor)
            self.assertEqual(original[TERMINAL], after[TERMINAL], donor.key)
            self.assertIn("WaitFor(CharacterDead(2420811));", after[TERMINAL])
            bridge = after[TERMINAL_BRIDGE_EVENT]
            self.assertLess(bridge.index(f"WaitFor(CharacterDead({PRIMARY}))"),
                            bridge.index(f"ForceCharacterDeath({GIANT}, false)"))
            self.assertIn(f"EndIf(EventFlag({TERMINAL}))", bridge)

    def test_shared_ebrietas_and_unrelated_destination_graph_remain_exact(self):
        before = event_blocks(self.destination)
        project_call = re.compile(
            r"\n    \$InitializeEvent\([^\n]*1299690[0-8][^\n]*\);"
        )
        owner = re.compile(r"\n    CreateBulletOwner\(984300\);")
        readiness = f"    SetEventFlag({ACTIVATION_EVENT}, OFF);\n"
        for donor in portable_celestial_donors():
            after = self.patched(donor)
            for event_id in EBRIETAS_EVENTS:
                self.assertEqual(before[event_id], after[event_id],
                                 f"{donor.key}:{event_id}")
            stripped = project_call.sub("", after[0]).replace(readiness, "", 1)
            stripped = owner.sub("", stripped)
            self.assertEqual(before[0], stripped, donor.key)
            for event_id in (12421701, 12424705, 12424710, 12424711):
                self.assertEqual(before[event_id], after[event_id],
                                 f"{donor.key}:{event_id}")

    def test_destination_entry_music_camera_and_source_combat_are_bound(self):
        expected_wake = {
            "blood-starved-beast": "ForceAnimationPlayback(2420810, 7001",
            "darkbeast-paarl": "WaitFixedTimeFrames(70)",
            "cleric-beast": "ForceAnimationPlayback(2420810, 3028",
            "vicar-amelia": "ForceAnimationPlayback(2420810, 7000",
            "amygdala": "ForceAnimationPlayback(2420810, 7006",
            "ebrietas": "SetCharacterImmortality(2420810, Enabled)",
        }
        for donor in portable_celestial_donors():
            after = self.patched(donor)
            entry = after[12421702]
            self.assertIn("InArea(10000, 2422815)", entry)
            self.assertIn("IssueBossRoomEntryNotification(0)", entry)
            self.assertIn(f"SetEventFlag({START_FLAG}, ON)", entry)
            self.assertNotRegex(entry, r"24207(?:11|12|13|16|17|19|20)")
            wake = after[ACTIVATION_EVENT]
            self.assertIn(expected_wake[donor.key], wake)
            self.assertLess(wake.index(f"SetCharacterInvincibility({PRIMARY}, Enabled)"),
                            wake.index(f"WaitFor(EventFlag({START_FLAG}))"))
            health = after[12424702]
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, {PRIMARY}, 0, {donor.health_bar_label})",
                health,
            )
            self.assertIn(f"SetCharacterAIState({GIANT}, Disabled)", health)
            self.assertIn("CreatePlaylog(104)", health)
            music = after[MUSIC_EVENT]
            signal = donor.music_phase_signals[-1]
            if signal.kind == "message":
                self.assertIn(
                    f"WaitFor(CharacterHasEventMessage({PRIMARY}, {signal.message}))",
                    music,
                )
            else:
                row = next(
                    attachment for attachment in celestial_arena_contract(donor)["attachments"]
                    if attachment["source_event"] == signal.source_event
                )
                self.assertIn(
                    f"WaitFor(EventFlag({row['destination_event']}))", music
                )
            camera = after[CAMERA_EVENT]
            self.assertIn("SetLockcamSlotNumber(24, 2,", camera)
            self.assertIn(f"EndIf(EventFlag({TERMINAL}))", camera)
            for attachment in celestial_arena_contract(donor)["attachments"]:
                self.assertIn(
                    f"$Event({attachment['destination_event']},",
                    after[attachment["destination_event"]],
                )

    def test_original_waves_generators_and_transition_controllers_are_retired(self):
        for donor in portable_celestial_donors():
            after = self.patched(donor)
            for event_id in SUPPRESSED_EVENTS:
                self.assertEqual("    EndEvent();", after[event_id].splitlines()[1],
                                 f"{donor.key}:{event_id}")
            cleanup = after[DESTINATION_CLEANUP_EVENT]
            for generator in GENERATORS:
                self.assertIn(f"DeactivateGenerator({generator}, Disabled)", cleanup)
            terminal_wait = cleanup.index(f"WaitFor(EventFlag({TERMINAL}))")
            for actor in (*WAVES, *SUPPORT):
                self.assertIn(f"ChangeCharacterEnableState({actor}, Disabled)", cleanup)
                self.assertGreater(
                    cleanup.rindex(f"ForceCharacterDeath({actor}, false)"),
                    terminal_wait,
                )
            self.assertNotIn(f"ForceCharacterDeath({GIANT}", cleanup)

    def test_native_plan_pins_both_states_and_all_retained_helpers(self):
        for donor in portable_celestial_donors():
            plan = native_plan_portable_donor_at_celestial_emissary(
                donor, self.slots, self.npcs, self.effects, "celestial-arena"
            )
            swap = plan["swaps"][0]
            self.assertEqual(2, len(swap["destination_keys"]))
            self.assertEqual(set(MAP_STATES), {
                row["destination_map"]
                for row in plan["primary_init_source_bindings"]
            })
            for binding in plan["primary_init_source_bindings"]:
                self.assertEqual(
                    SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                    binding["source_provenance"]["part_sha256"],
                )
                state = binding["destination_map"]
                self.assertEqual(
                    ce.ACTOR_PINS[state][0],
                    plan["boss_contract"]["destination_native_evidence"]
                    ["primary_part_sha256"][state],
                )
            retained = plan["boss_contract"]["retained_destination_helpers"]
            self.assertEqual(20, len(retained))
            for state in MAP_STATES:
                state_rows = [row for row in retained if row["map"] == state]
                self.assertEqual(
                    {GIANT, *WAVES, *SUPPORT},
                    {row["entity_id"] for row in state_rows},
                )
                self.assertEqual(
                    set(ce.ACTOR_PINS[state][1:]),
                    {row["source_provenance"]["part_sha256"] for row in state_rows},
                )
            if donor.key == "ebrietas":
                requirements = plan["boss_actor_addition_requirements"]
                self.assertEqual(2, len(requirements))
                for requirement in requirements:
                    self.assertEqual(BULLET_OWNER_ENTITY,
                                     requirement["destination_entity_id"])
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_optional_owner_lifecycle_is_present_only_when_required(self):
        for donor in portable_celestial_donors():
            after = self.patched(donor)
            if donor.virtual_entities:
                self.assertEqual("ebrietas", donor.key)
                self.assertIn(f"CreateBulletOwner({BULLET_OWNER_ENTITY})", after[0])
                cleanup = after[OWNER_CLEANUP_EVENT]
                self.assertLess(cleanup.index(f"WaitFor(EventFlag({TERMINAL}))"),
                                cleanup.index(
                                    f"ForceCharacterDeath({BULLET_OWNER_ENTITY}, false)"))
            else:
                self.assertNotIn(OWNER_CLEANUP_EVENT, after)
                self.assertNotIn(f"CreateBulletOwner({BULLET_OWNER_ENTITY})", after[0])

    def test_ids_and_original_source_drift_fail_closed(self):
        donor = PACKAGES[0]
        with self.assertRaisesRegex(ValueError, "exact reviewed"):
            patch_portable_donor_at_celestial_emissary(
                self.destination, donor, self.sources[donor.key],
                replace(DEFAULT_IDS,
                        terminal_bridge_event=DEFAULT_IDS.activation_event),
            )
        with self.assertRaisesRegex(ValueError, "blood-starved-beast donor"):
            patch_portable_donor_at_celestial_emissary(
                self.destination, donor,
                self.sources[donor.key].replace(
                    "HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "Celestial arena"):
            patch_portable_donor_at_celestial_emissary(
                self.destination.replace(
                    "HandleBossDefeat(2420811)", "HandleBossDefeat(7)", 1
                ),
                donor, self.sources[donor.key],
            )

    def test_all_original_inputs_patch_and_compile_with_pinned_fixture(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {
            "common.emevd.dcx", EVENT_FILE.removesuffix(".js"),
            *(donor.event_file.removesuffix(".js") for donor in PACKAGES),
        }
        missing = [name for name in required if not (events / name).is_file()]
        if not compiler.is_file() or missing:
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
                "-indir", str(original), "-outdir", str(source),
                "-force", "-silent",
            ], check=True)
            destination_path = source / EVENT_FILE
            baseline = destination_path.read_text(encoding="utf-8-sig")
            for donor in portable_celestial_donors():
                donor_source = (
                    baseline if donor.event_file == EVENT_FILE
                    else (source / donor.event_file).read_text(encoding="utf-8-sig")
                )
                patched = patch_portable_donor_at_celestial_emissary(
                    baseline, donor, donor_source
                )
                destination_path.write_text(patched, encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([
                    str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output),
                    "-force", "-silent",
                ], check=True)
                self.assertTrue((output / EVENT_FILE.removesuffix(".js")).is_file())


if __name__ == "__main__":
    unittest.main()
