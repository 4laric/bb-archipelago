import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import AMYGDALA_PACKAGE, BSB_PACKAGE, PACKAGES
from tools.bb_enemizer.gascoigne_arena_contract import (
    ACTIVATION_EVENT, ATTACHMENT_EVENTS, BACKED_EVENT_RANGE, BEAST_PINS, BULLET_OWNER_ENTITY,
    DEFAULT_IDS, EVENT_FILE, GASCOIGNE_ARENA_CONTRACT, MAP_STATES,
    OWNER_CLEANUP_EVENT, PROXY_CLEANUP_EVENT, SOURCE_PART_PINS, GascoigneArenaIds, _original_literals,
    gascoigne_arena_contract, native_plan_portable_donor_at_gascoigne,
    patch_portable_donor_at_gascoigne, portable_gascoigne_donors,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class GascoigneArenaContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.sources = {package.key: read_blob(BUNDLE, "event/" + package.event_file).decode("utf-8-sig")
                       for package in PACKAGES}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_contract_shape_and_allocations_are_source_collision_free(self):
        self.assertEqual("father-gascoigne", GASCOIGNE_ARENA_CONTRACT.key)
        self.assertEqual(3, GASCOIGNE_ARENA_CONTRACT.destination_count)
        self.assertEqual((12414807, 12414808, 12414809),
                         GASCOIGNE_ARENA_CONTRACT.retired_combat_events)
        self.assertEqual({package.key for package in PACKAGES},
                         {package.key for package in portable_gascoigne_donors()})
        self.assertEqual(0, len(set(DEFAULT_IDS.values()) & _original_literals()))
        self.assertEqual((12414880, 12414881, 12414882, 12414883, 12414884),
                         ATTACHMENT_EVENTS)
        self.assertEqual((12414885, 12414886, 12414887, 982800),
                         (OWNER_CLEANUP_EVENT, ACTIVATION_EVENT,
                          PROXY_CLEANUP_EVENT, BULLET_OWNER_ENTITY))
        self.assertEqual(tuple(range(12414880, 12414888)), BACKED_EVENT_RANGE)

    def test_runtime_persistent_events_require_the_exact_live_backed_range(self):
        old_unbacked = GascoigneArenaIds(
            attachment_events=(12995300, 12995301, 12995302, 12995303, 12995304),
            owner_cleanup_event=12995305,
            activation_event=12995306,
            proxy_cleanup_event=12995307,
        )
        with self.assertRaisesRegex(ValueError, "live-backed range 12414880-12414887"):
            patch_portable_donor_at_gascoigne(
                self.destination, BSB_PACKAGE, self.sources[BSB_PACKAGE.key], old_unbacked)
        with self.assertRaisesRegex(ValueError, "live-backed range 12414880-12414887"):
            native_plan_portable_donor_at_gascoigne(
                BSB_PACKAGE, self.slots, self.npcs, self.effects, "unbacked", old_unbacked)
        with self.assertRaisesRegex(ValueError, "live-backed range 12414880-12414887"):
            gascoigne_arena_contract(BSB_PACKAGE, old_unbacked)

    def test_all_donors_preserve_terminal_entry_coop_and_generic_navigation_body(self):
        before = event_blocks(self.destination)
        for donor in portable_gascoigne_donors():
            with self.subTest(donor=donor.key):
                after = event_blocks(patch_portable_donor_at_gascoigne(
                    self.destination, donor, self.sources[donor.key]))
                for event_id in (12411800, 12411801, 12411802, 12411803,
                                 12414805, 12414810, 12414811, 12414812,
                                 12414813, 12415238):
                    self.assertEqual(before[event_id], after[event_id])
                self.assertNotIn("$InitializeEvent(0, 12415238, 2412820, 2410810", after[0])
                self.assertNotIn("$InitializeEvent(1, 12415238, 2412820, 2410811", after[0])
                self.assertEqual("$Event(12414807, Default, function() {\n    EndEvent();\n});",
                                 after[12414807])
                self.assertEqual("$Event(12414808, Default, function() {\n    EndEvent();\n});",
                                 after[12414808])
                self.assertEqual("$Event(12414809, Default, function() {\n    EndEvent();\n});",
                                 after[12414809])

    def test_proxy_cannot_complete_the_or_terminal_early_and_dies_on_completed_reload(self):
        for donor in portable_gascoigne_donors():
            with self.subTest(donor=donor.key):
                blocks = event_blocks(patch_portable_donor_at_gascoigne(
                    self.destination, donor, self.sources[donor.key]))
                proxy = blocks[PROXY_CLEANUP_EVENT]
                self.assertIn("SetCharacterInvincibility(2410811, Enabled);", proxy)
                self.assertIn("GotoIf(L0, EventFlag(12411800));", proxy)
                self.assertIn("WaitFor(EventFlag(12411800));", proxy)
                self.assertLess(proxy.index("WaitFor(EventFlag(12411800));"),
                                proxy.index("ForceCharacterDeath(2410811, false);"))
                self.assertNotIn("ForceCharacterDeath(2410811", blocks[12414802])
                self.assertIn(f"$InitializeEvent(0, {PROXY_CLEANUP_EVENT});", blocks[0])

    def test_source_health_readiness_telemetry_and_notification_are_complete(self):
        wake = {
            "blood-starved-beast": "ForceAnimationPlayback(2410810, 7001, false, false, false)",
            "darkbeast-paarl": "WaitFixedTimeFrames(70)",
            "cleric-beast": "ForceAnimationPlayback(2410810, 3028, false, false, false)",
            "vicar-amelia": "ForceAnimationPlayback(2410810, 7000, false, false, false)",
            "amygdala": "ForceAnimationPlayback(2410810, 7003, true, false, false)",
            "ebrietas": "WaitFor(HasDamageType(2410810, 10000, DamageType.Unspecified))",
        }
        for donor in portable_gascoigne_donors():
            with self.subTest(donor=donor.key):
                blocks = event_blocks(patch_portable_donor_at_gascoigne(
                    self.destination, donor, self.sources[donor.key]))
                health, ready = blocks[12414802], blocks[ACTIVATION_EVENT]
                self.assertIn(f"WaitFor(EventFlag({ACTIVATION_EVENT}));", health)
                self.assertIn("if (!EventFlag(12414223)) {", health)
                self.assertIn("SetEventFlag(12414223, ON);", health)
                self.assertIn("CreatePlaylog(80);", health)
                self.assertIn("StartTimeMeasurement(2410010, 96, Enabled);", health)
                self.assertNotIn("CreateReferredDamagePair(2410810, 2410811)", health)
                self.assertIn(wake[donor.key], ready)
                self.assertEqual(12414800,
                    int(gascoigne_arena_contract(donor)["readiness_adapter"]["trigger"].split("(")[1][:-1]))

    def test_final_donor_phase_drives_destination_final_music(self):
        for donor in portable_gascoigne_donors():
            with self.subTest(donor=donor.key):
                blocks = event_blocks(patch_portable_donor_at_gascoigne(
                    self.destination, donor, self.sources[donor.key]))
                music = blocks[12414803]
                self.assertNotIn("EventFlag(12414807)", music)
                signal = donor.music_phase_signals[-1]
                if signal.kind == "message":
                    self.assertIn(f"CharacterHasEventMessage(2410810, {signal.message})", music)
                else:
                    attachments = {row["source_event"]: row["destination_event"]
                                   for row in gascoigne_arena_contract(donor)["attachments"]}
                    self.assertIn(f"EventFlag({attachments[signal.source_event]})", music)
                if donor in (BSB_PACKAGE, AMYGDALA_PACKAGE):
                    first = donor.music_phase_signals[0]
                    self.assertNotEqual(first.source_event, signal.source_event)

    def test_native_plan_pins_three_primary_and_three_inert_proxy_states(self):
        for donor in portable_gascoigne_donors():
            with self.subTest(donor=donor.key):
                plan = native_plan_portable_donor_at_gascoigne(
                    donor, self.slots, self.npcs, self.effects, "gascoigne-arena")
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(set(MAP_STATES), {row["destination_map"] for row in bindings})
                self.assertEqual({"c2710_0000"}, {row["destination_part"] for row in bindings})
                self.assertEqual({0}, {row["source_talk_id"] for row in bindings})
                for row in bindings:
                    self.assertEqual(
                        SOURCE_PART_PINS[(row["source_map"], row["source_entity_id"])],
                        row["source_provenance"]["part_sha256"],
                    )
                    self.assertEqual(
                        {"talk_id": 0, "unk_t18": -1,
                         "init_anim_id": -1, "damage_anim_id": -1},
                        row["source_initialization"],
                    )
                retained = plan["boss_contract"]["retained_destination_helpers"]
                self.assertEqual(set(MAP_STATES), {row["map"] for row in retained})
                self.assertEqual({2410811}, {row["entity_id"] for row in retained})
                self.assertEqual(set(BEAST_PINS.values()),
                                 {row["source_provenance"]["part_sha256"] for row in retained})
                if donor.key == "ebrietas":
                    helpers = plan["boss_actor_addition_requirements"]
                    self.assertEqual(3, len(helpers))
                    self.assertEqual({982800}, {row["destination_entity_id"] for row in helpers})
                    self.assertEqual(set(MAP_STATES), {row["destination_map"] for row in helpers})
                else:
                    self.assertNotIn("boss_actor_addition_requirements", plan)

    def test_every_declared_attachment_is_installed_and_output_compiles_when_fixture_exists(self):
        for donor in portable_gascoigne_donors():
            with self.subTest(closure=donor.key):
                blocks = event_blocks(patch_portable_donor_at_gascoigne(
                    self.destination, donor, self.sources[donor.key]))
                for attachment in gascoigne_arena_contract(donor)["attachments"]:
                    body = blocks[attachment["destination_event"]]
                    self.assertIn(f"$Event({attachment['destination_event']},", body)
                    self.assertNotIn(str(donor.actor), body)
                    self.assertNotIn(str(donor.completion_event), body)
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        required = ("common.emevd.dcx", "m24_01_00_00.emevd.dcx")
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
            for donor in portable_gascoigne_donors():
                path.write_text(patch_portable_donor_at_gascoigne(
                    baseline, donor, self.sources[donor.key]), encoding="utf-8-sig")
                output = work / ("out-" + donor.key)
                subprocess.run([str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent"], check=True)
                self.assertTrue((output / "m24_01_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
