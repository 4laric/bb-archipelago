import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import PACKAGES
from tools.bb_enemizer.boss_entrances import skip_replacement_entrance
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.moon_arena_contract import (
    ACTIVATION_EVENT,
    ATTACHMENT_EVENTS,
    BULLET_OWNER_ENTITY,
    DEFAULT_IDS,
    DESTINATION_PINS,
    DONOR_OWNER_CLEANUP_EVENT,
    EVENT_FILE,
    MOON_ARENA_CONTRACT,
    SOURCE_INITIALIZATION,
    SOURCE_PART_PINS,
    _original_literals,
    moon_arena_contract,
    native_plan_portable_donor_at_moon,
    patch_portable_donor_at_moon,
    portable_moon_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class MoonArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
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

    def patch(self, donor):
        return event_blocks(
            patch_portable_donor_at_moon(
                self.destination, donor, self.sources[donor.key]
            )
        )

    def test_contract_and_allocation_cover_all_six_without_pair_whitelist(self):
        self.assertEqual("moon-presence", MOON_ARENA_CONTRACT.key)
        self.assertEqual(
            {package.key for package in PACKAGES},
            {package.key for package in portable_moon_donors()},
        )
        self.assertEqual(
            (12996200, 12996201, 12996202, 12996203, 12996204),
            ATTACHMENT_EVENTS,
        )
        self.assertEqual(
            (12996205, 12996206, 983700),
            (ACTIVATION_EVENT, DONOR_OWNER_CLEANUP_EVENT, BULLET_OWNER_ENTITY),
        )
        self.assertEqual(0, len(set(DEFAULT_IDS.values()) & _original_literals()))
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            patch_portable_donor_at_moon(
                self.destination,
                PACKAGES[0],
                self.sources[PACKAGES[0].key],
                replace(DEFAULT_IDS, bullet_owner_entity=983701),
            )

    def test_terminal_entry_client_audio_and_gehrman_sibling_remain_exact(self):
        before = event_blocks(self.destination)
        protected = (
            12101800,
            12101802,
            12101803,
            12101850,
            12101852,
            12101853,
            12104855,
            12104880,
            12104881,
        )
        for donor in portable_moon_donors():
            with self.subTest(donor=donor.key):
                after = self.patch(donor)
                for event_id in protected:
                    self.assertEqual(before[event_id], after[event_id])
                entry = after[12101852]
                for witness in (
                    "EventFlag(12101800)",
                    "EventFlag(9900)",
                    "PlayerStandingOnHit(2103601)",
                    "PlayCutsceneAndWarpPlayer(21000050",
                    "ChangeCharacterEnableState(2100810, Enabled)",
                    "SetEventFlag(12104850, ON)",
                ):
                    self.assertIn(witness, entry)
                normalized = event_blocks(
                    skip_replacement_entrance(
                        "moon-presence",
                        self.destination,
                        patch_portable_donor_at_moon(
                            self.destination, donor, self.sources[donor.key]
                        ),
                    )
                )[12101852]
                self.assertEqual(
                    2,
                    normalized.count(
                        "IssueShortWarpRequest(10000, TargetEntityType.Area, 2102809, -1)"
                    ),
                )
                self.assertNotIn("PlayCutscene", normalized)

    def test_health_waits_for_donor_wake_on_first_entry_and_saved_reload(self):
        destination_health = event_blocks(self.destination)[12104852]
        for donor in portable_moon_donors():
            with self.subTest(donor=donor.key):
                blocks = self.patch(donor)
                health = blocks[12104852]
                self.assertEqual(
                    2, health.count(f"WaitFor(EventFlag({ACTIVATION_EVENT}));")
                )
                first_ready = health.index(f"WaitFor(EventFlag({ACTIVATION_EVENT}));")
                second_ready = health.rindex(f"WaitFor(EventFlag({ACTIVATION_EVENT}));")
                invincibility_on = health.index(
                    "SetCharacterInvincibility(2100810, Enabled)"
                )
                invincibility_off = health.index(
                    "SetCharacterInvincibility(2100810, Disabled)"
                )
                self.assertLess(invincibility_on, first_ready)
                self.assertLess(second_ready, invincibility_off)
                self.assertLess(
                    invincibility_off,
                    health.index("SetCharacterAIState(2100810, Enabled)"),
                )
                self.assertIn("EndIf(EventFlag(12101850))", health)
                self.assertIn("SetEventFlag(12104850, ON)", health)
                self.assertIn(
                    f"DisplayBossHealthBar(Enabled, 2100810, 0, {donor.health_bar_label})",
                    health,
                )
                self.assertIn("SetCharacterAIState(2100810, Enabled)", health)
                self.assertEqual(1, health.count("IssueBossRoomEntryNotification(0)"))
                flags = {
                    int(flag)
                    for flag in re.findall(r"(?:EventFlag|SetEventFlag)\((\d+)", health)
                }
                self.assertEqual({12101850, 12104850, ACTIVATION_EVENT}, flags)
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    line = next(
                        row
                        for row in destination_health.splitlines()
                        if row.strip().startswith(instruction + "(")
                    )
                    self.assertIn(line, health)
                activation = blocks[ACTIVATION_EVENT]
                self.assertIn("EndIf(EventFlag(12101850))", activation)
                self.assertIn("WaitFor(EventFlag(12104850))", activation)
                if donor.key == "ebrietas":
                    immortality_on = activation.index(
                        "SetCharacterImmortality(2100810, Enabled)"
                    )
                    invincibility_off = activation.index(
                        "SetCharacterInvincibility(2100810, Disabled)"
                    )
                    damage_wait = activation.index(
                        "HasDamageType(2100810, 10000, DamageType.Unspecified)"
                    )
                    self.assertLess(immortality_on, invincibility_off)
                    self.assertLess(invincibility_off, damage_wait)
                self.assertLess(
                    blocks[0].index(f"SetEventFlag({ACTIVATION_EVENT}, OFF)"),
                    blocks[0].index(f"$InitializeEvent(0, {ACTIVATION_EVENT});"),
                )

    def test_donor_attachments_music_camera_and_moon_controllers_are_closed(self):
        before = event_blocks(self.destination)
        for donor in portable_moon_donors():
            with self.subTest(donor=donor.key):
                blocks = self.patch(donor)
                contract = moon_arena_contract(donor)
                for row in contract["attachments"]:
                    target = row["destination_event"]
                    self.assertIn(f"$Event({target},", blocks[target])
                self.assertEqual(
                    "$Event(12104860, Default, function(unused_npcPartId, "
                    "unused_npcPartId2, unused_npcPartGroupIdx, unused_npcPartHP, "
                    "unused_spEffectId, unused_spEffectId2, unused_animationId) {\n"
                    "    EndEvent();\n});",
                    blocks[12104860],
                )
                self.assertIn("EndEvent();", blocks[12104870])
                self.assertNotEqual(before[12104853], blocks[12104853])
                self.assertIn("SetLockcamSlotNumber(21, 0,", blocks[12104854])
                self.assertIn("EndIf(EventFlag(12101850))", blocks[12104854])
                final_signal = donor.music_phase_signals[-1]
                if final_signal.kind == "message":
                    self.assertIn(
                        f"CharacterHasEventMessage(2100810, {final_signal.message})",
                        blocks[12104853],
                    )
                else:
                    imported = dict(
                        (row["source_event"], row["destination_event"])
                        for row in contract["attachments"]
                    )
                    self.assertIn(
                        f"EventFlag({imported[final_signal.source_event]})",
                        blocks[12104853],
                    )

    def test_native_plan_pins_primary_and_both_gehrman_sibling_actors(self):
        for donor in portable_moon_donors():
            with self.subTest(donor=donor.key):
                plan = native_plan_portable_donor_at_moon(
                    donor, self.slots, self.npcs, self.effects, "moon-arena"
                )
                binding = plan["primary_init_source_bindings"][0]
                self.assertEqual("m21_00_00_00", binding["destination_map"])
                self.assertEqual(2100810, binding["destination_entity_id"])
                self.assertEqual(
                    SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                    binding["source_provenance"]["part_sha256"],
                )
                self.assertEqual(
                    SOURCE_INITIALIZATION, binding["source_initialization"]
                )
                retained = plan["boss_contract"]["retained_destination_helpers"]
                self.assertEqual(
                    {2100800, 2100801}, {row["entity_id"] for row in retained}
                )
                for row in retained:
                    self.assertEqual(
                        DESTINATION_PINS[row["entity_id"]],
                        row["source_provenance"]["part_sha256"],
                    )
                gehrman = next(row for row in retained if row["entity_id"] == 2100800)
                self.assertEqual(210306, gehrman["source_initialization"]["talk_id"])

    def test_ebrietas_physical_owner_is_materialized_and_cleaned_after_terminal(self):
        donor = next(
            package for package in portable_moon_donors() if package.key == "ebrietas"
        )
        blocks = self.patch(donor)
        self.assertIn(f"CreateBulletOwner({BULLET_OWNER_ENTITY});", blocks[0])
        cleanup = blocks[DONOR_OWNER_CLEANUP_EVENT]
        self.assertLess(
            cleanup.index("WaitFor(EventFlag(12101850))"),
            cleanup.index(f"ForceCharacterDeath({BULLET_OWNER_ENTITY}, false)"),
        )
        plan = native_plan_portable_donor_at_moon(
            donor, self.slots, self.npcs, self.effects, "moon-ebrietas"
        )
        requirements = plan["boss_actor_addition_requirements"]
        self.assertEqual(1, len(requirements))
        self.assertEqual(BULLET_OWNER_ENTITY, requirements[0]["destination_entity_id"])

    def test_all_outputs_compile_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {
            "common.emevd.dcx",
            "m21_00_00_00.emevd.dcx",
            *(package.event_file.removesuffix(".js") for package in PACKAGES),
        }
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
            path = source / EVENT_FILE
            baseline = path.read_text(encoding="utf-8-sig")
            for donor in portable_moon_donors():
                path.write_text(
                    patch_portable_donor_at_moon(
                        baseline,
                        donor,
                        (source / donor.event_file).read_text(encoding="utf-8-sig"),
                    ),
                    encoding="utf-8-sig",
                )
                output = work / ("out-" + donor.key)
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
                self.assertTrue((output / "m21_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
