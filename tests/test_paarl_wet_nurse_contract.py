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
from tools.bb_enemizer.paarl_wet_nurse_contract import (
    BUNDLE,
    DEFAULT_IDS,
    PAARL_SOURCE,
    PAARL_SOURCE_PINS,
    WET_NURSE_SOURCE,
    native_plan_paarl_at_wet_nurse,
    patch_paarl_at_wet_nurse,
)
from tools.bb_enemizer.scaling import load_params


class PaarlWetNurseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
        cls.donor = read_blob(BUNDLE, PAARL_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_native_terminal_waits_for_proxy_released_only_after_paarl_death(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_paarl_at_wet_nurse(self.arena, self.donor))
        self.assertEqual(before[12601800], after[12601800])
        bridge = after[DEFAULT_IDS.death_to_proxy]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2600800));"),
            bridge.index("SetCharacterInvincibility(2600802, Disabled);"),
        )
        self.assertLess(
            bridge.index("SetCharacterInvincibility(2600802, Disabled);"),
            bridge.index("ForceCharacterDeath(2600802, false);"),
        )
        for literal in (
            "HandleBossDefeat(2600803);",
            "AwardAchievement(20);",
            "AwardItemLot(55100000);",
            "SetEventFlag(9462, ON);",
        ):
            self.assertIn(literal, after[12601800])

    def test_full_paarl_health_activation_phase_limb_and_camera_package(self):
        after = event_blocks(patch_paarl_at_wet_nurse(self.arena, self.donor))
        activation = after[12601802]
        self.assertIn("PlayCutsceneToPlayer(26000010", activation)
        self.assertIn("ForceAnimationPlayback(2600800, 7000, true", activation)
        self.assertIn("ForceAnimationPlayback(2600800, 7001, false", activation)
        self.assertIn("WaitFixedTimeFrames(70);", activation)
        health = after[12604802]
        self.assertIn("DisplayBossHealthBar(Enabled, 2600800, 0, 508000);", health)
        self.assertIn("SetSpEffect(2600800, 7501, true);", health)
        self.assertNotIn("CreateReferredDamagePair", health)
        phase = after[DEFAULT_IDS.phase]
        self.assertIn("HPRatio(2600800) < 0.67", phase)
        self.assertIn("RequestCharacterAICommand(2600800, 100, 2);", phase)
        limb = after[DEFAULT_IDS.limb]
        self.assertIn("CreateNPCPart(2600800, npcPartId", limb)
        self.assertIn("SetNPCPartSEAndSFX(2600800", limb)
        self.assertIn("SetLockcamSlotNumber(26, 0, 1);", after[12604804])
        self.assertIn("SetLockcamSlotNumber(26, 0, 0);", after[12604804])
        constructor = after[0]
        self.assertEqual(5, constructor.count(f", {DEFAULT_IDS.limb},"))
        self.assertEqual(1, constructor.count(f", {DEFAULT_IDS.phase});"))

    def test_destination_music_coop_cleanup_and_micolash_graph_remain_owned(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_paarl_at_wet_nurse(self.arena, self.donor))
        music = after[12604803]
        self.assertIn("SetMapSoundState(2603802, Disabled);", music)
        self.assertIn("WaitFor(HPRatio(2600800) < 0.7);", music)
        self.assertNotIn("2303812", music)
        for event in (
            12601803,
            12604805,
            12601850,
            12601851,
            12601852,
            12601853,
            12604860,
            12604861,
            12604877,
            12604879,
        ):
            self.assertEqual(before[event], after[event])

    def test_wet_nurse_phase_clone_warp_graph_retires_and_proxy_stays_inert(self):
        after = event_blocks(patch_paarl_at_wet_nurse(self.arena, self.donor))
        for event in (
            12604806,
            12604810,
            12604815,
            12604820,
            12604830,
            12604840,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        cleanup = after[DEFAULT_IDS.helper_cleanup]
        self.assertLess(
            cleanup.index("ChangeCharacterEnableState(2600802, Disabled);"),
            cleanup.index("WaitFor(EventFlag(12601800));"),
        )
        self.assertIn("SetCharacterInvincibility(2600802, Enabled);", cleanup)
        health = after[12604802]
        self.assertIn("ChangeCharacterEnableState(2600801, Disabled);", health)
        self.assertIn("ChangeCharacterEnableState(2600802, Disabled);", health)

    def test_native_plan_pins_paarl_and_both_retained_destination_actors(self):
        plan = native_plan_paarl_at_wet_nurse(
            self.slots, self.npcs, self.effects, "paarl-wet-nurse"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5080", plan["swaps"][0]["target"]["model_name"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual(
            PAARL_SOURCE_PINS["m23_00_00_00"].part_sha256,
            binding["source_provenance"]["part_sha256"],
        )
        self.assertEqual(
            {2600801, 2600802},
            {
                row["entity_id"]
                for row in plan["boss_contract"]["retained_destination_helpers"]
            },
        )
        self.assertNotIn("boss_actor_additions", plan)
        self.assertIn(
            "no added actor",
            plan["boss_contract"]["helper_entity_reservation"],
        )

    def test_source_destination_and_project_id_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "Paarl donor"):
            patch_paarl_at_wet_nurse(
                self.arena,
                self.donor.replace(
                    "HPRatio(2300810) < 0.67", "HPRatio(2300810) < 0.68"
                ),
            )
        with self.assertRaisesRegex(ValueError, "Wet Nurse arena"):
            patch_paarl_at_wet_nurse(
                self.arena.replace(
                    "HandleBossDefeat(2600803);", "HandleBossDefeat(2600802);"
                ),
                self.donor,
            )
        with self.assertRaisesRegex(ValueError, "129939xx"):
            patch_paarl_at_wet_nurse(
                self.arena,
                self.donor,
                replace(DEFAULT_IDS, death_to_proxy=DEFAULT_IDS.phase),
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        if not compiler.is_file() or not (events / "m26_00_00_00.emevd.dcx").is_file():
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
            for name in ("common.emevd.dcx", "m26_00_00_00.emevd.dcx"):
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
            (source / "m26_00_00_00.emevd.dcx.js").write_text(
                patch_paarl_at_wet_nurse(self.arena, self.donor),
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
            self.assertTrue((output / "m26_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
