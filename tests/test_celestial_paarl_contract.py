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
from tools.bb_enemizer.celestial_paarl_contract import (
    ACTOR_PINS,
    BUNDLE,
    CE_SOURCE,
    DEFAULT_IDS,
    DESTINATION_PINS,
    DESTINATION_STATES,
    GENERATOR_ENTITIES,
    GENERATOR_EVENT_IDS,
    GIANT,
    HELPERS,
    PAARL_SOURCE,
    PRIMARY,
    REGION_ENTITIES,
    SOURCE_STATES,
    SUPPORT,
    WAVES,
    celestial_helper_scaling_parents,
    native_plan_celestial_at_paarl,
    patch_celestial_emissary_at_paarl,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class CelestialPaarlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, PAARL_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, CE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self):
        return event_blocks(patch_celestial_emissary_at_paarl(self.arena, self.donor))

    def plan(self):
        return native_plan_celestial_at_paarl(
            self.slots, self.npcs, self.effects, "celestial-paarl"
        )

    def test_paarl_terminal_rewards_death_sound_and_music_cleanup_are_preserved(self):
        before, after = event_blocks(self.arena), self.patched()
        for event_id in (12301700, 12301701, 12304705):
            self.assertEqual(before[event_id], after[event_id])
        terminal = after[12301700]
        self.assertIn("HandleBossDefeat(2300810)", terminal)
        self.assertIn("AwardAchievement(24)", terminal)
        self.assertIn("AwardItemLot(50800000)", terminal)
        self.assertIn("SetEventFlag(2301, ON)", terminal)

    def test_entry_coop_health_music_and_camera_use_only_materialized_actors(self):
        after = self.patched()
        entry = after[12301702]
        self.assertIn("EntityInRadiusOfEntity(2300810, 10000, 16)", entry)
        self.assertIn("$InitializeEvent(0, 9350, 1)", entry)
        self.assertIn("ChangeCharacterEnableState(980607, Enabled)", entry)
        coop = after[12301703]
        self.assertIn("EventFlag(12304700)", coop)
        self.assertIn("ChangeCharacterEnableState(980601, Enabled)", coop)
        health = after[12304702]
        self.assertIn("SetNetworkUpdateAuthority(2300810", health)
        self.assertIn("SetNetworkUpdateAuthority(980600", health)
        self.assertEqual(2, health.count("SetSpEffect(2300810, 750"))
        self.assertNotRegex(health, r"(?<!\d)28008\d+(?!\d)")
        self.assertIn("CreatePlaylog(86)", health)
        self.assertIn("StartTimeMeasurement(2300010, 102, Enabled)", health)
        music = after[12304703]
        self.assertIn("SetMapSoundState(2303812, Disabled)", music)
        self.assertIn("SetMapSoundState(2303813, Disabled)", music)
        self.assertNotIn("270380", music)
        camera = after[12304704]
        self.assertIn("EndIf(EventFlag(12301700))", camera)
        self.assertEqual(2, camera.count("SetLockcamSlotNumber(23, 0,"))

    def test_phase_preserves_damage_pair_then_hides_primary_at_sixty_percent(self):
        phase = self.patched()[DEFAULT_IDS.giant_phase]
        pair = phase.index(f"CreateReferredDamagePair({PRIMARY}, {GIANT})")
        threshold = phase.index(f"HPRatio({PRIMARY}) < 0.6")
        hide = phase.index(f"ChangeCharacterEnableState({PRIMARY}, Disabled)")
        self.assertLess(pair, threshold)
        self.assertLess(threshold, hide)
        self.assertIn(f"SetCharacterHome({GIANT}, {REGION_ENTITIES[7]})", phase)
        self.assertIn(f"DisplayBossHealthBar(Enabled, {GIANT}, 0, 257000)", phase)

    def test_giant_death_is_the_only_added_bridge_to_primary_death(self):
        after = self.patched()
        bridge = after[DEFAULT_IDS.giant_death_bridge]
        wait = bridge.index(f"WaitFor(CharacterDead({GIANT}))")
        death = bridge.index(f"ForceCharacterDeath({PRIMARY}, false)")
        self.assertLess(wait, death)
        for event_id in DEFAULT_IDS.events():
            if event_id != DEFAULT_IDS.giant_death_bridge:
                self.assertNotIn(f"ForceCharacterDeath({PRIMARY}", after[event_id])

    def test_constructor_preserves_every_original_controller_slot_and_literal_map(self):
        constructor = self.patched()[0]
        expected = {
            DEFAULT_IDS.generator_cleanup: 8,
            DEFAULT_IDS.giant_command: 1,
            DEFAULT_IDS.giant_ai: 1,
            DEFAULT_IDS.giant_home: 2,
            DEFAULT_IDS.wave_home: 2,
            DEFAULT_IDS.giant_phase: 1,
            DEFAULT_IDS.support_warp: 1,
            DEFAULT_IDS.support_phase: 2,
            DEFAULT_IDS.giant_choreography: 1,
            DEFAULT_IDS.giant_death_bridge: 1,
            DEFAULT_IDS.lifecycle_cleanup: 1,
        }
        for event_id, count in expected.items():
            self.assertEqual(
                count,
                len(
                    re.findall(
                        r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                        constructor,
                    )
                ),
            )
        copied = (
            constructor
            + "\n"
            + "\n".join(self.patched()[event] for event in DEFAULT_IDS.events())
        )
        for entity in (*REGION_ENTITIES[7:], *GENERATOR_ENTITIES):
            self.assertIn(str(entity), copied)
        self.assertNotRegex(copied, r"(?<!\d)242(?:27|37)\d+(?!\d)")

    def test_completed_reload_cleanup_covers_every_helper_and_generator(self):
        cleanup = self.patched()[DEFAULT_IDS.lifecycle_cleanup]
        self.assertIn("WaitFor(EventFlag(12301700))", cleanup)
        for entity in HELPERS:
            self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled)", cleanup)
            self.assertIn(f"ForceCharacterDeath({entity}, false)", cleanup)
        for entity in GENERATOR_ENTITIES:
            self.assertIn(f"DeactivateGenerator({entity}, Disabled)", cleanup)
        self.assertEqual("    EndEvent();", self.patched()[12304707].splitlines()[1])
        self.assertEqual("    EndEvent();", self.patched()[12304715].splitlines()[1])

    def test_native_plan_is_full_two_state_pinned_graph_with_scaling(self):
        plan = self.plan()
        self.assertEqual("c2500", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(2, len(plan["swaps"][0]["destination_keys"]))
        self.assertEqual(20, len(plan["boss_actor_additions"]))
        self.assertEqual(22, len(plan["boss_region_additions"]))
        self.assertEqual(14, len(plan["boss_generator_additions"]))
        self.assertEqual(2, len(plan["primary_init_source_bindings"]))
        self.assertEqual(20, len(celestial_helper_scaling_parents(plan)))
        self.assertIn("changes", plan["scaling"])
        for index, binding in enumerate(plan["primary_init_source_bindings"]):
            source_state, destination_state = (
                SOURCE_STATES[index],
                DESTINATION_STATES[index],
            )
            self.assertEqual(
                ACTOR_PINS[source_state][0], binding["source_provenance"]["part_sha256"]
            )
            self.assertEqual(
                {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1},
                binding["source_initialization"],
            )
            self.assertEqual(destination_state, binding["destination_map"])
        for row in plan["boss_region_additions"]:
            self.assertNotEqual(-1, row["source_entity_id"])
            self.assertEqual(
                DESTINATION_PINS[row["destination_map"]],
                row["destination_anchor_provenance"]["part_sha256"],
            )
        self.assertEqual(
            set(REGION_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_region_additions"]},
        )
        self.assertEqual(
            set(GENERATOR_ENTITIES),
            {row["destination_entity_id"] for row in plan["boss_generator_additions"]},
        )
        self.assertEqual(
            set(GENERATOR_EVENT_IDS),
            {row["destination_event_id"] for row in plan["boss_generator_additions"]},
        )

    def test_generator_bindings_and_event_literal_evidence_are_exact(self):
        plan = self.plan()
        for state in DESTINATION_STATES:
            rows = [
                row
                for row in plan["boss_generator_additions"]
                if row["destination_map"] == state
            ]
            self.assertEqual(7, len(rows))
            for index, row in enumerate(rows):
                self.assertEqual(
                    {
                        f"c2500_{(1, 2, 3, 6, 7, 9, 10)[index]:04d}": f"ap_ce_wave_{(1, 2, 3, 6, 7, 9, 10)[index]}"
                    },
                    row["spawn_part_map"],
                )
                self.assertEqual(1, len(row["spawn_point_map"]))
                self.assertEqual(64, len(row["source_fingerprint"]))
        literal_map = plan["boss_contract"]["event_literal_map"]
        self.assertEqual(18, len(literal_map))
        self.assertEqual(REGION_ENTITIES[7], literal_map["2422721"])
        self.assertEqual(GENERATOR_ENTITIES[-1], literal_map["2423720"])
        self.assertEqual(
            [2800800, 2800801, 2800802, 2800803],
            plan["boss_contract"]["foreign_literal_policy"]["literals"],
        )
        self.assertNotIn("280080", str(plan["boss_contract"]["source_roster"]))

    def test_source_destination_drift_and_id_collision_refuse(self):
        with self.assertRaisesRegex(ValueError, "unsupported original Celestial donor"):
            patch_celestial_emissary_at_paarl(
                self.arena,
                self.donor.replace("HPRatio(2420810) < 0.6", "HPRatio(2420810) < 0.5"),
            )
        with self.assertRaisesRegex(ValueError, "129927xx"):
            patch_celestial_emissary_at_paarl(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, giant_phase=DEFAULT_IDS.giant_ai),
            )
        reduced = [
            row
            for row in self.slots
            if not (row.map_name == SOURCE_STATES[1] and row.entity_id == 2420811)
        ]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_celestial_at_paarl(
                reduced, self.npcs, self.effects, "missing-giant"
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        if not compiler.is_file() or not (events / "m23_00_00_00.emevd.dcx").is_file():
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
            for name in ("common.emevd.dcx", "m23_00_00_00.emevd.dcx"):
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
            (source / "m23_00_00_00.emevd.dcx.js").write_text(
                patch_celestial_emissary_at_paarl(self.arena, self.donor),
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
            self.assertTrue((output / "m23_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
