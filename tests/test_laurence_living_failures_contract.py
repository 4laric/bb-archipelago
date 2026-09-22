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
from tools.bb_enemizer.laurence_living_failures_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LAURENCE_SOURCE,
    LaurenceLivingFailuresIds,
    native_plan_laurence_at_living_failures,
    patch_laurence_at_living_failures,
)
from tools.bb_enemizer.scaling import load_params


class LaurenceLivingFailuresContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.failures = (
            read_blob(BUNDLE, "event/m35_00_00_00.emevd.dcx.js")
            .decode("utf-8-sig")
            .replace("\r\n", "\n")
        )
        cls.laurence = (
            read_blob(BUNDLE, LAURENCE_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_laurence_death_releases_only_the_unchanged_aggregate_terminal(self):
        before = event_blocks(self.failures)
        after = event_blocks(
            patch_laurence_at_living_failures(self.failures, self.laurence)
        )
        self.assertEqual(before[13501850], after[13501850])
        self.assertIn("WaitFor(HPRatio(3500850) == 0);", after[13501850])
        bridge = after[DEFAULT_IDS.death_to_proxy]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(3500851));"),
            bridge.index("ForceCharacterDeath(3500850, false);"),
        )
        self.assertIn(
            "DisplayBossHealthBar(Enabled, 3500851, 0, 450000);", after[13504852]
        )

    def test_all_living_failures_bodies_support_and_generators_are_retired(self):
        after = event_blocks(
            patch_laurence_at_living_failures(self.failures, self.laurence)
        )
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

    def test_laurence_phase_limbs_and_camera_use_all_six_source_initializers(self):
        after = event_blocks(
            patch_laurence_at_living_failures(self.failures, self.laurence)
        )
        constructor = after[0]
        self.assertEqual(5, constructor.count(f", {DEFAULT_IDS.limbs},"))
        self.assertEqual(
            1, constructor.count(f"$InitializeEvent(0, {DEFAULT_IDS.hitmask});")
        )
        limbs = after[DEFAULT_IDS.limbs]
        self.assertIn("CreateNPCPart(3500851", limbs)
        self.assertIn("CharacterHasEventMessage(3500851, 300)", limbs)
        self.assertIn(
            "ChangeCharacterHitmask(3500851, 10, ON);", after[DEFAULT_IDS.hitmask]
        )
        self.assertIn("CharacterHasEventMessage(3500851, 400)", after[13504853])
        self.assertEqual(2, after[13504854].count("SetLockcamSlotNumber(35, 0,"))
        self.assertNotIn("SetLockcamSlotNumber(34,", after[13504854])

    def test_destination_entry_and_retry_stay_local_without_laurence_cutscene_state(
        self,
    ):
        before = event_blocks(self.failures)
        after = event_blocks(
            patch_laurence_at_living_failures(self.failures, self.laurence)
        )
        self.assertEqual(before[13501852], after[13501852])
        self.assertIn("SetEventFlag(13504858, ON);", after[13501851])
        self.assertNotIn("ForceAnimationPlayback(3500851", after[13501851])
        self.assertNotIn(
            "PlayCutsceneAndWarpPlayer(34000010", "\n".join(after.values())
        )
        self.assertNotIn("IssueShortWarpRequest(3400850", "\n".join(after.values()))

    def test_native_plan_pins_laurence_init_and_retained_helpers(self):
        plan = native_plan_laurence_at_living_failures(
            self.slots, self.npcs, self.effects, "laurence-failures"
        )
        self.assertEqual(1, plan["swap_count"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(
            ("c4500_0000", 0),
            (binding["source_part"], binding["source_initialization"]["talk_id"]),
        )
        self.assertEqual(
            "cdf84241072ed9304f89d145ca746572548edf26bcd5c80e571d3237e0e7a12c",
            binding["source_provenance"]["part_sha256"],
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(
            {3500850, 3500852, 3500853, 3500854, 3500860},
            {row["entity_id"] for row in retained},
        )
        self.assertFalse(
            plan["boss_contract"]["actor_additions"],
            "the source is a single primary actor",
        )
        self.assertIn("Ludwig", plan["boss_contract"]["source_ludwig_policy"])

    def test_source_ludwig_drift_and_project_id_collisions_refuse(self):
        with self.assertRaisesRegex(ValueError, "collocated Ludwig"):
            patch_laurence_at_living_failures(
                self.failures,
                self.laurence.replace(
                    "HandleBossDefeat(3400800)", "HandleBossDefeat(7)", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "129937xx"):
            patch_laurence_at_living_failures(
                self.failures,
                self.laurence,
                replace(DEFAULT_IDS, hitmask=DEFAULT_IDS.limbs),
            )
        with self.assertRaisesRegex(ValueError, "Living Failures arena"):
            patch_laurence_at_living_failures(
                self.failures.replace(
                    "HandleBossDefeat(3500850)", "HandleBossDefeat(7)", 1
                ),
                self.laurence,
            )

    def test_witnessed_installed_ludwig_always_update_variant_is_accepted(self):
        fixture = (
            Path(__file__).resolve().parents[1]
            / "work"
            / "ludwig-source-inspect"
            / "source"
            / "m34_00_00_00.emevd.dcx.js"
        )
        if not fixture.is_file():
            self.skipTest("reviewed installed Ludwig source fixture unavailable")
        installed = fixture.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        output = event_blocks(
            patch_laurence_at_living_failures(self.failures, installed)
        )
        self.assertIn("CharacterHasEventMessage(3500851, 400)", output[13504853])
        self.assertIn("CreateNPCPart(3500851", output[DEFAULT_IDS.limbs])

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        required = (
            "common.emevd.dcx",
            "m34_00_00_00.emevd.dcx",
            "m35_00_00_00.emevd.dcx",
        )
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
            original, source, output = (
                work / "original",
                work / "source",
                work / "output",
            )
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
            (source / "m35_00_00_00.emevd.dcx.js").write_text(
                patch_laurence_at_living_failures(self.failures, self.laurence),
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
