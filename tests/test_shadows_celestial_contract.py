import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.shadows_celestial_contract import *


class ShadowsCelestialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, CELESTIAL_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)
        cls.before = event_blocks(cls.arena)
        cls.after = event_blocks(
            patch_shadows_at_celestial_emissary(cls.arena, cls.donor)
        )

    def test_terminal_and_progression_are_byte_identical_and_bridge_is_three_body(self):
        self.assertEqual(self.before[TERMINAL], self.after[TERMINAL])
        self.assertIn("WaitFor(CharacterDead(2420811));", self.after[TERMINAL])
        self.assertNotIn("CharacterDead(2420810)", self.after[TERMINAL])
        self.assertNotIn("CharacterDead(982100)", self.after[TERMINAL])
        for event in (12421701, 12424705, 12424710, 12424711, *EBRIETAS_EVENTS):
            self.assertEqual(self.before[event], self.after[event])

        bridge = self.after[DEFAULT_IDS.bridge]
        wait = "WaitFor(CharacterDead(2420810) && CharacterDead(982100) && CharacterDead(982101));"
        self.assertIn(wait, bridge)
        self.assertLess(
            bridge.index(wait), bridge.index("ForceCharacterDeath(2420811, false);")
        )
        self.assertLess(
            bridge.index("SetCharacterInvincibility(2420811, Disabled);"),
            bridge.index("ForceCharacterDeath(2420811, false);"),
        )

    def test_entry_health_music_and_camera_use_destination_state(self):
        entry = self.after[12421702]
        self.assertIn("InArea(10000, 2422815)", entry)
        self.assertIn("SetEventFlag(12424700, ON);", entry)
        for entity in (2420810, 982100, 982101):
            self.assertIn(f"ChangeCharacterEnableState({entity}, Enabled);", entry)
        client = self.after[12421703]
        self.assertIn("EndIf(HasMultiplayerState(MultiplayerState.Host));", client)
        self.assertIn("EventFlag(12424700)", client)

        health = self.after[12424702]
        for entity, slot, name in (
            (2420810, 2, 212010),
            (982100, 1, 212020),
            (982101, 0, 212030),
        ):
            self.assertIn(f"SetSpEffect({entity}, 7500, true);", health)
            self.assertIn(
                f"DisplayBossHealthBar(Enabled, {entity}, {slot}, {name});", health
            )
        self.assertIn("CreatePlaylog(104);", health)
        self.assertIn("StartTimeMeasurement(2420010, 40, Enabled);", health)
        self.assertIn(f"EventFlag({DEFAULT_IDS.phase_signal})", self.after[12424703])
        self.assertNotIn("12704808", self.after[12424703])
        self.assertEqual(2, self.after[12424704].count("SetLockcamSlotNumber(24, 2,"))

    def test_full_source_controller_closure_and_celestial_retirement(self):
        expected_initializers = {
            DEFAULT_IDS.group_phase: 1,
            DEFAULT_IDS.summon: 3,
            DEFAULT_IDS.body_phase: 3,
            DEFAULT_IDS.attachment: 4,
            DEFAULT_IDS.effect: 2,
            DEFAULT_IDS.summon_cleanup: 3,
        }
        constructor = self.after[0]
        for event, count in expected_initializers.items():
            self.assertEqual(count, constructor.count(f", {event}"))
        self.assertNotIn(f", {DEFAULT_IDS.distance_pair}", constructor)
        self.assertNotIn(f", {DEFAULT_IDS.distance_all}", constructor)

        for event in SUPPRESSED_EVENTS:
            self.assertEqual("    EndEvent();", self.after[event].splitlines()[1])
        cleanup = self.after[DEFAULT_IDS.destination_cleanup]
        for generator in CE_GENERATORS:
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", cleanup)
        for entity in (*WAVES, *SUPPORT):
            self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled);", cleanup)
        completion = cleanup.index(f"WaitFor(EventFlag({TERMINAL}));")
        self.assertLess(
            cleanup.index("ChangeCharacterEnableState(2420811, Disabled);"), completion
        )
        self.assertGreater(
            cleanup.index("ForceCharacterDeath(982100, false);"), completion
        )

    def test_native_plan_has_complete_actor_region_generator_and_scaling_graph(self):
        plan = native_plan_shadows_at_celestial_emissary(
            self.slots, self.npcs, self.effects, "shadows-celestial"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c2120", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(9, len(plan["boss_actor_additions"]))
        self.assertEqual(12, len(plan["boss_region_additions"]))
        self.assertEqual(3, len(plan["boss_generator_additions"]))
        self.assertEqual(9, len(plan["boss_actor_scaling_requirements"]))
        self.assertEqual(
            set(SOURCE_ACTORS[1:]),
            {row["source_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            set(HELPER_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_actor_additions"]},
        )
        self.assertEqual(
            set(range(982140, 982152)),
            {row["destination_entity_id"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(
            set(range(982130, 982133)),
            {row["destination_entity_id"] for row in plan["boss_generator_additions"]},
        )
        self.assertEqual(10, len(plan["boss_contract"]["retained_destination_helpers"]))
        self.assertIn(
            "geometry", plan["boss_contract"]["placement_anchor_policy"]["risk"]
        )

    def test_primary_and_every_added_actor_have_exact_original_pins(self):
        plan = native_plan_shadows_at_celestial_emissary(
            self.slots, self.npcs, self.effects, "shadows-celestial"
        )
        primary = plan["primary_init_source_bindings"][0]
        self.assertEqual(SHADOWS[0], primary["source_entity_id"])
        self.assertEqual(
            ACTOR_PINS[SHADOWS[0]], primary["source_provenance"]["part_sha256"]
        )
        self.assertEqual(0, primary["source_talk_id"])
        for addition in plan["boss_actor_additions"]:
            entity = addition["source_entity_id"]
            self.assertEqual(
                ACTOR_PINS[entity], addition["source_provenance"]["part_sha256"]
            )
            self.assertEqual(
                ACTOR_PINS[SHADOWS[0]], addition["source_provenance"]["anchor_sha256"]
            )
            self.assertEqual(
                {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1},
                addition["source_initialization"],
            )

    def test_project_id_collisions_and_original_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "129944xx"):
            patch_shadows_at_celestial_emissary(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, phase_signal=DEFAULT_IDS.group_phase),
            )
        with self.assertRaisesRegex(ValueError, "982100-982199"):
            patch_shadows_at_celestial_emissary(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, generator_entity_first=2420810),
            )
        with self.assertRaisesRegex(ValueError, "Shadows donor"):
            patch_shadows_at_celestial_emissary(
                self.arena,
                self.donor.replace(
                    "DisplayBossHealthBar(Enabled, 2700800",
                    "DisplayBossHealthBar(Enabled, 7",
                ),
            )
        with self.assertRaisesRegex(ValueError, "Celestial arena"):
            patch_shadows_at_celestial_emissary(
                self.arena.replace(
                    "WaitFor(CharacterDead(2420811));", "WaitFor(CharacterDead(7));"
                ),
                self.donor,
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        target = events / "m24_02_00_00.emevd.dcx"
        if not compiler.is_file() or not target.is_file():
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original, source, output = (
                work / "original",
                work / "source",
                work / "output",
            )
            original.mkdir()
            for name in ("common.emevd.dcx", target.name):
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
            (source / "m24_02_00_00.emevd.dcx.js").write_text(
                patch_shadows_at_celestial_emissary(self.arena, self.donor),
                encoding="utf-8-sig",
            )
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
            self.assertTrue((output / target.name).is_file())


if __name__ == "__main__":
    unittest.main()
