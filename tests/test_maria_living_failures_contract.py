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
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.maria_living_failures_contract import (
    BUNDLE,
    DEFAULT_IDS,
    MARIA_SOURCE,
    MariaLivingFailuresIds,
    maria_living_failures_external_reference_requirement,
    native_plan_maria_at_living_failures,
    patch_maria_at_living_failures,
)
from tools.bb_enemizer.scaling import load_params


class MariaLivingFailuresContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (
            read_blob(BUNDLE, MARIA_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_maria_death_releases_only_the_unchanged_aggregate_terminal(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_maria_at_living_failures(self.source, self.source))
        self.assertEqual(before[13501850], after[13501850])
        self.assertIn("WaitFor(HPRatio(3500850) == 0);", after[13501850])
        bridge = after[DEFAULT_IDS.death_to_proxy]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(3500851));"),
            bridge.index("ForceCharacterDeath(3500850, false);"),
        )
        health = after[13504852]
        self.assertIn("DisplayBossHealthBar(Enabled, 3500851, 0, 452000);", health)
        self.assertNotIn("CreateReferredDamagePair", health)

    def test_complete_living_failures_roster_and_generators_stay_disabled(self):
        after = event_blocks(patch_maria_at_living_failures(self.source, self.source))
        for event in (
            13504865,
            13504880,
            13504881,
            13504885,
            13504890,
            13504895,
            13505655,
            13505656,
            13505661,
            13505662,
            13505680,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1], event)
        cleanup = after[DEFAULT_IDS.retire_helpers]
        for generator in range(3503814, 3503818):
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", cleanup)
        for actor in (3500852, 3500853, 3500854, 3500860):
            self.assertIn(f"ChangeCharacterEnableState({actor}, Disabled);", cleanup)
            self.assertIn(f"ForceCharacterDeath({actor}, false);", cleanup)

    def test_entry_music_camera_and_phase_cleanup_are_maria_specific(self):
        after = event_blocks(patch_maria_at_living_failures(self.source, self.source))
        self.assertNotIn("ForceAnimationPlayback(3500851", after[13501851])
        self.assertNotIn("RequestCharacterAIReplan(3500851)", after[13501851])
        self.assertIn("CharacterHasEventMessage(3500851, 100)", after[13504853])
        self.assertIn("SetMapSoundState(3503812, Disabled);", after[13504853])
        self.assertIn("SetLockcamSlotNumber(35, 0, 1);", after[13504854])
        self.assertIn("ClearSpEffect(3500851, 5526);", after[DEFAULT_IDS.phase_cleanup])

    def test_shared_maria_arena_events_and_constructor_state_remain_composable(self):
        before = event_blocks(self.source)
        after = event_blocks(patch_maria_at_living_failures(self.source, self.source))
        for event in (
            13501800,
            13501801,
            13501807,
            13504800,
            13504801,
            13504802,
            13504803,
            13504804,
            13504805,
            13504822,
        ):
            self.assertEqual(before[event], after[event], event)
        remove = re.compile(r"\n    \$InitializeEvent\(0, 129936(?:00|01|02)\);")
        self.assertEqual(before[0], remove.sub("", after[0]))
        health = after[13504852]
        self.assertEqual(1, health.count("SetCharacterEventTarget(3500851, 3500801);"))
        self.assertNotRegex(
            health, r"(?<!\d)(?:3500800|13501800|13504808|13504810)(?!\d)"
        )

    def test_native_plan_pins_maria_initialization_and_every_retained_helper(self):
        plan = native_plan_maria_at_living_failures(
            self.slots, self.npcs, self.effects, "maria-failures"
        )
        self.assertEqual(1, plan["swap_count"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(
            ("c4520_0002", 0),
            (binding["source_part"], binding["source_initialization"]["talk_id"]),
        )
        self.assertEqual(
            "4c8e1f5185a8026aca281a0402ee06fe1c60c361043609b31f178b0b974ef906",
            binding["source_provenance"]["part_sha256"],
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(
            {3500850, 3500852, 3500853, 3500854, 3500860},
            {row["entity_id"] for row in retained},
        )
        self.assertFalse(
            plan["boss_contract"]["actor_additions"],
            "Maria is a primary replacement; this adapter does not invent helper actors",
        )
        opaque = maria_living_failures_external_reference_requirement()
        self.assertEqual(
            (3500801, 13504852, 3500851),
            (
                opaque["entity_id"],
                opaque["destination_event_id"],
                opaque["destination_actor"],
            ),
        )

    def test_drift_and_collision_refuse_before_any_overlay_is_produced(self):
        with self.assertRaisesRegex(ValueError, "129936xx"):
            patch_maria_at_living_failures(
                self.source,
                self.source,
                replace(DEFAULT_IDS, death_to_proxy=DEFAULT_IDS.phase_cleanup),
            )
        with self.assertRaisesRegex(ValueError, "Lady Maria donor"):
            patch_maria_at_living_failures(
                self.source,
                self.source.replace("CreatePlaylog(58);", "CreatePlaylog(7);", 1),
            )
        with self.assertRaisesRegex(ValueError, "Living Failures arena"):
            patch_maria_at_living_failures(
                self.source.replace(
                    "HandleBossDefeat(3500850)", "HandleBossDefeat(7)", 1
                ),
                self.source,
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        if not compiler.is_file() or not (events / "m35_00_00_00.emevd.dcx").is_file():
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
            for name in ("common.emevd.dcx", "m35_00_00_00.emevd.dcx"):
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
            (source / "m35_00_00_00.emevd.dcx.js").write_text(
                patch_maria_at_living_failures(self.source, self.source),
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
            self.assertTrue((output / "m35_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
