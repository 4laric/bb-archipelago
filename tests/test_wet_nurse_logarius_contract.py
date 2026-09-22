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
from tools.bb_enemizer.wet_nurse_logarius_contract import (
    BUNDLE,
    DEFAULT_IDS,
    LOGARIUS_SOURCE,
    WET_NURSE_SOURCE,
    native_plan_wet_nurse_at_logarius,
    patch_wet_nurse_at_logarius,
)


class WetNurseLogariusContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logarius = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
        cls.nurse = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_source_proxy_completion_drives_unchanged_cainhurst_terminal(self):
        before = event_blocks(self.logarius)
        after = event_blocks(patch_wet_nurse_at_logarius(self.logarius, self.nurse))
        health = after[12504802]
        self.assertIn("DisplayBossHealthBar(Enabled, 981601, 0, 551000);", health)
        self.assertIn("CreateReferredDamagePair(2500800, 981601);", health)
        self.assertIn("CreateReferredDamagePair(981600, 981601);", health)
        bridge = after[DEFAULT_IDS.proxy_death_bridge]
        self.assertLess(
            bridge.index("WaitFor(HPRatio(981601) <= 0);"),
            bridge.index("ForceCharacterDeath(2500800, false);"),
        )
        self.assertLess(
            bridge.index("ForceCharacterDeath(2500800, false);"),
            bridge.index("ClearSpEffect(10000, 5630);"),
        )
        self.assertEqual(before[12501800], after[12501800])
        self.assertIn("HandleBossDefeat(2500800);", after[12501800])

    def test_destination_entry_music_and_retained_helpers_are_explicit(self):
        after = event_blocks(patch_wet_nurse_at_logarius(self.logarius, self.nurse))
        activation = after[12501802]
        self.assertLess(
            activation.index("ChangeCharacterEnableState(2500800, Disabled);"),
            activation.index("WaitFor("),
        )
        self.assertLess(
            activation.index("WaitFor("),
            activation.index("ChangeCharacterEnableState(2500800, Enabled);"),
        )
        self.assertNotIn("ForceAnimationPlayback(2500800, 7000", activation)
        music = after[12504803]
        self.assertIn("HPRatio(981601) < 0.7", music)
        self.assertNotIn("CharacterHasSpEffect(2500800, 5633)", music)
        self.assertEqual("    EndEvent();", after[12504804].splitlines()[1])
        cleanup = after[DEFAULT_IDS.helper_cleanup]
        for actor in (2500801, 2500802, 981600, 981601):
            self.assertIn(str(actor), cleanup)
        self.assertNotIn("EndIf(ThisEvent());", cleanup)
        constructor = after[0]
        self.assertIn(
            "$InitializeEvent(0, 12993802, 2500800, 12993821, 12993826);", constructor
        )
        emergence = after[DEFAULT_IDS.support_emergence]
        self.assertIn("BatchSetEventFlags(12993827, 12993830, OFF);", emergence)
        self.assertIn("RandomlySetEventFlagInRange(12993827, 12993830, ON);", emergence)

    def test_plan_requires_source_pinned_full_wet_graph_and_logarius_helpers(self):
        plan = native_plan_wet_nurse_at_logarius(
            self.slots, self.npcs, self.effects, "wet-logarius"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5510", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {981600, 981601},
            {x["destination_entity_id"] for x in plan["boss_actor_additions"]},
        )
        self.assertEqual(6, len(plan["boss_region_additions"]))
        self.assertEqual(
            981608, plan["boss_object_additions"][0]["destination_entity_id"]
        )
        contract = plan["boss_contract"]
        self.assertEqual("unobserved", contract["runtime_status"])
        self.assertIn("Micolash", contract["source_m26_policy"])
        retained = contract["retained_destination_helpers"]
        self.assertEqual({2500801, 2500802}, {x["entity_id"] for x in retained})
        self.assertEqual(
            12604802,
            next(
                x["source_event_id"]
                for x in contract["event_patch"]["changed_events"]
                if x["destination_event_id"] == 12504802
            ),
        )

    def test_custom_health_entry_flag_is_remapped_without_default_literal(self):
        ids = replace(DEFAULT_IDS, health_entered_flag=12993840)
        health = event_blocks(
            patch_wet_nurse_at_logarius(self.logarius, self.nurse, ids)
        )[12504802]
        self.assertIn("EventFlag(12993840)", health)
        self.assertIn("SetEventFlag(12993840, ON);", health)
        self.assertNotIn("12993820", health)

    def test_id_and_pin_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129938xx"):
            patch_wet_nurse_at_logarius(
                self.logarius,
                self.nurse,
                replace(DEFAULT_IDS, health_entered_flag=DEFAULT_IDS.warp_flag_first),
            )
        with self.assertRaisesRegex(ValueError, "helper IDs"):
            patch_wet_nurse_at_logarius(
                self.logarius, self.nurse, replace(DEFAULT_IDS, proxy_entity=2500800)
            )
        with self.assertRaisesRegex(ValueError, "Logarius arena"):
            patch_wet_nurse_at_logarius(
                self.logarius.replace(
                    "HandleBossDefeat(2500800)", "HandleBossDefeat(7)"
                ),
                self.nurse,
            )
        with self.assertRaisesRegex(ValueError, "Wet Nurse donor"):
            patch_wet_nurse_at_logarius(
                self.logarius,
                self.nurse.replace(
                    "CreateReferredDamagePair(2600800, 2600802)",
                    "CreateReferredDamagePair(2600800, 1)",
                ),
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        required = (
            "common.emevd.dcx",
            "m25_00_00_00.emevd.dcx",
            "m26_00_00_00.emevd.dcx",
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
            source_donor = (source / "m26_00_00_00.emevd.dcx.js").read_text(
                encoding="utf-8-sig"
            )
            (source / "m25_00_00_00.emevd.dcx.js").write_text(
                patch_wet_nurse_at_logarius(
                    (source / "m25_00_00_00.emevd.dcx.js").read_text(
                        encoding="utf-8-sig"
                    ),
                    source_donor,
                ),
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
            self.assertTrue((output / "m25_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
