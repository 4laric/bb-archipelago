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
from tools.bb_enemizer.ludwig_arena_contract import (
    ACTIVATION_EVENT,
    ATTACHMENT_EVENTS,
    BULLET_OWNER_ENTITY,
    CLIENT_RESTORE_EVENT,
    DEFAULT_IDS,
    DESTINATION_PINS,
    EVENT_FILE,
    DONOR_OWNER_CLEANUP_EVENT,
    HELPER_LIFECYCLE_EVENT,
    LUDWIG_ARENA_CONTRACT,
    PHASE,
    SOURCE_PART_PINS,
    _original_literals,
    ludwig_arena_contract,
    native_plan_portable_donor_at_ludwig,
    patch_portable_donor_at_ludwig,
    portable_ludwig_donors,
)
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class LudwigArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.sources = {
            p.key: read_blob(BUNDLE, "event/" + p.event_file).decode("utf-8-sig")
            for p in PACKAGES
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_contract_and_allocations_cover_all_six_without_pair_whitelist(self):
        self.assertEqual("ludwig", LUDWIG_ARENA_CONTRACT.key)
        self.assertEqual(
            (
                13404820,
                13404821,
                13404822,
                13404823,
                13404824,
                13404825,
                13404830,
                13404835,
                13404840,
                13404841,
            ),
            LUDWIG_ARENA_CONTRACT.retired_combat_events,
        )
        self.assertEqual(
            {p.key for p in PACKAGES}, {p.key for p in portable_ludwig_donors()}
        )
        self.assertEqual(0, len(set(DEFAULT_IDS.values()) & _original_literals()))
        self.assertEqual(
            (12995900, 12995901, 12995902, 12995903, 12995904), ATTACHMENT_EVENTS
        )
        self.assertEqual(
            (12995905, 12995906, 12995907, 12995908, 983400),
            (
                ACTIVATION_EVENT,
                CLIENT_RESTORE_EVENT,
                HELPER_LIFECYCLE_EVENT,
                DONOR_OWNER_CLEANUP_EVENT,
                BULLET_OWNER_ENTITY,
            ),
        )
        # Only the exact helper is allocated; original IDs exist elsewhere in
        # the surrounding 9832xx range.
        self.assertNotIn(983400, _original_literals())
        self.assertIn(983213, _original_literals())
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            patch_portable_donor_at_ludwig(
                self.destination,
                PACKAGES[0],
                self.sources[PACKAGES[0].key],
                replace(DEFAULT_IDS, bullet_owner_entity=983201),
            )
        with self.assertRaisesRegex(ValueError, "Ludwig arena event 13401800"):
            patch_portable_donor_at_ludwig(
                self.destination.replace(
                    "AwardAchievement(36)", "AwardAchievement(35)"
                ),
                PACKAGES[0],
                self.sources[PACKAGES[0].key],
            )

    def test_terminal_fog_postboss_and_music_cleanup_remain_byte_exact(self):
        before = event_blocks(self.destination)
        for donor in portable_ludwig_donors():
            after = event_blocks(
                patch_portable_donor_at_ludwig(
                    self.destination, donor, self.sources[donor.key]
                )
            )
            for event_id in (
                13401800,
                13401801,
                13401802,
                13401803,
                13401804,
                13404800,
                13404801,
                13404805,
                13404806,
                13404807,
                13404811,
                13400941,
                13400942,
                13400943,
                13400944,
                13401850,
                13401851,
                13401853,
                13404850,
                13404851,
                13404852,
                13404853,
                13404854,
                13404855,
                13404856,
                13404857,
                13404861,
                13404870,
                13404875,
            ):
                self.assertEqual(before[event_id], after[event_id], donor.key)
            self.assertIn("PlayCutsceneToPlayer(34000020", after[13401801])
            for event_id in LUDWIG_ARENA_CONTRACT.retired_combat_events:
                self.assertEqual("    EndEvent();", after[event_id].splitlines()[1])
                self.assertEqual(3, len(after[event_id].splitlines()))
            self.assertEqual(1, after[0].count("$InitializeEvent(0, 13404841);"))
            self.assertEqual(1, after[0].count("$InitializeEvent(0, 13404804);"))
            self.assertLess(
                after[0].index(f"SetEventFlag({ACTIVATION_EVENT}, OFF)"),
                after[0].index(f"$InitializeEvent(0, {ACTIVATION_EVENT})"),
            )

    def test_health_readiness_notification_telemetry_music_and_camera_are_adapted(self):
        for donor in portable_ludwig_donors():
            blocks = event_blocks(
                patch_portable_donor_at_ludwig(
                    self.destination, donor, self.sources[donor.key]
                )
            )
            health = blocks[13404802]
            self.assertEqual(
                2, health.count(f"WaitFor(EventFlag({ACTIVATION_EVENT}));")
            )
            self.assertIn("if (!EventFlag(13404810))", health)
            self.assertIn("SetEventFlag(13404810, ON)", health)
            self.assertIn("CreatePlaylog(46)", health)
            self.assertIn("StartTimeMeasurement(3400010, 62, Enabled)", health)
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, 3400800, 0, {donor.health_bar_label})",
                health,
            )
            self.assertNotIn("EventFlag(13404824)", blocks[13404803])
            self.assertIn("SetLockcamSlotNumber(34, 0,", blocks[13404804])
            self.assertIn("EndIf(EventFlag(13401800))", blocks[13404804])
            self.assertNotIn("3400801", blocks[13404804])
            flags = set(
                map(int, re.findall(r"(?:EventFlag|SetEventFlag)\((\d+)", health))
            )
            self.assertEqual({13401800, 13404808, 13404810, ACTIVATION_EVENT}, flags)

    def test_client_restore_is_source_pinned_and_preserves_donor_specific_state(self):
        expected = {
            "blood-starved-beast": None,
            "darkbeast-paarl": "SetCharacterInvincibility(3400800, Disabled)",
            "cleric-beast": "ChangeCharacterEnableState(3400800, Enabled)",
            "vicar-amelia": "ChangeCharacterEnableState(3400800, Enabled)",
            "amygdala": None,
            "ebrietas": None,
        }
        for donor in portable_ludwig_donors():
            blocks = event_blocks(
                patch_portable_donor_at_ludwig(
                    self.destination, donor, self.sources[donor.key]
                )
            )
            restore = blocks[CLIENT_RESTORE_EVENT]
            self.assertIn("EventFlag(13404808)", restore)
            self.assertIn("SetEventFlag(13401801, ON)", restore)
            if expected[donor.key]:
                self.assertIn(expected[donor.key], restore)
            self.assertEqual(
                CLIENT_RESTORE_EVENT,
                ludwig_arena_contract(donor)["client_restore_event"],
            )

    def test_inert_helpers_cannot_affect_live_combat_and_cleanup_completed_reload(self):
        for donor in portable_ludwig_donors():
            blocks = event_blocks(
                patch_portable_donor_at_ludwig(
                    self.destination, donor, self.sources[donor.key]
                )
            )
            life = blocks[HELPER_LIFECYCLE_EVENT]
            self.assertIn("ChangeCharacterEnableState(3400801, Disabled)", life)
            self.assertIn("ForceCharacterDeath(3400801, false)", life)
            self.assertIn("SetCharacterInvincibility(3400801, Enabled)", life)
            self.assertIn("GotoIf(L0, EventFlag(13401800))", life)
            self.assertLess(
                life.index("WaitFor(EventFlag(13401800))"),
                life.index("ForceCharacterDeath(3400801, false)"),
            )
            self.assertNotIn("3400801", blocks[13404802])

    def test_native_plan_has_authored_primary_and_all_destination_actor_pins(self):
        for donor in portable_ludwig_donors():
            plan = native_plan_portable_donor_at_ludwig(
                donor, self.slots, self.npcs, self.effects, "ludwig-arena"
            )
            binding = plan["primary_init_source_bindings"][0]
            self.assertEqual("m34_00_00_00", binding["destination_map"])
            self.assertEqual(
                SOURCE_PART_PINS[(binding["source_map"], donor.actor)],
                binding["source_provenance"]["part_sha256"],
            )
            self.assertEqual(
                {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1},
                binding["source_initialization"],
            )
            retained = plan["boss_contract"]["retained_destination_helpers"]
            self.assertEqual({PHASE}, {row["entity_id"] for row in retained})
            for row in retained:
                self.assertEqual(
                    DESTINATION_PINS[row["entity_id"]],
                    row["source_provenance"]["part_sha256"],
                )
            if donor.key == "ebrietas":
                self.assertEqual(
                    {983400},
                    {
                        row["destination_entity_id"]
                        for row in plan["boss_actor_addition_requirements"]
                    },
                )
                blocks = event_blocks(
                    patch_portable_donor_at_ludwig(
                        self.destination, donor, self.sources[donor.key]
                    )
                )
                self.assertIn("CreateBulletOwner(983400);", blocks[0])
            else:
                self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_all_attachments_install_and_all_outputs_compile_with_pinned_fixture(self):
        for donor in portable_ludwig_donors():
            blocks = event_blocks(
                patch_portable_donor_at_ludwig(
                    self.destination, donor, self.sources[donor.key]
                )
            )
            for row in ludwig_arena_contract(donor)["attachments"]:
                self.assertIn(
                    f"$Event({row['destination_event']},",
                    blocks[row["destination_event"]],
                )
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = {
            "common.emevd.dcx",
            "m34_00_00_00.emevd.dcx",
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
            for donor in portable_ludwig_donors():
                path.write_text(
                    patch_portable_donor_at_ludwig(
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
                self.assertTrue((output / "m34_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
