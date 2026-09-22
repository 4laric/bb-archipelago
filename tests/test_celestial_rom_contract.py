import hashlib, shutil, subprocess, tempfile, unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.celestial_rom_contract import *


class CelestialRomContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rom = read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig")
        cls.ce = read_blob(BUNDLE, CE_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(p)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_full_ce_proxy_graph_and_actual_giant_death_bridge(self):
        before = event_blocks(self.rom)
        after = event_blocks(patch_celestial_emissary_at_rom(self.rom, self.ce))
        health = after[13204802]
        self.assertIn("DisplayBossHealthBar(Enabled, 3200800, 0, 257000)", health)
        phase = after[DEFAULT_IDS.giant_phase]
        self.assertIn("CreateReferredDamagePair(3200800, 982000)", phase)
        bridge = after[DEFAULT_IDS.giant_death_bridge]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(982000));"),
            bridge.index("ForceCharacterDeath(3200800, false);"),
        )
        self.assertEqual(before[13201800], after[13201800])

    def test_rom_progression_spiders_and_teleports_remain_safe(self):
        before = event_blocks(self.rom)
        after = event_blocks(patch_celestial_emissary_at_rom(self.rom, self.ce))
        for event in (
            13201801,
            13201803,
            13201804,
            13204805,
            13204820,
            13204821,
            13204830,
            13204831,
            13204832,
            13204833,
            13204834,
        ):
            self.assertEqual(before[event], after[event])
        for event in (
            13204000,
            13204050,
            13204730,
            13204807,
            13204808,
            13204809,
            13204810,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1])
        cleanup = after[DEFAULT_IDS.lifecycle_cleanup]
        wait = cleanup.index("WaitFor(EventFlag(13201800));")
        self.assertEqual(30, cleanup[:wait].count("ChangeCharacterEnableState("))
        self.assertEqual(30, cleanup[wait:].count("ForceCharacterDeath(32002"))

    def test_music_uses_rom_combat_region_without_rewriting_other_regions(self):
        before = event_blocks(self.rom)
        after = event_blocks(patch_celestial_emissary_at_rom(self.rom, self.ce))
        self.assertEqual(2, after[13204803].count("InArea(10000, 3202801)"))
        self.assertNotIn("InArea(10000, 3202812)", after[13204803])
        self.assertEqual(before[13201803], after[13201803])
        self.assertIn("InArea(10000, 3202812)", after[13201803])

    def test_native_plan_materializes_two_state_full_source_graph(self):
        plan = native_plan_celestial_at_rom(
            self.slots, self.npcs, self.effects, "ce-rom"
        )
        self.assertEqual("c2500", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(20, len(plan["boss_actor_additions"]))
        self.assertEqual(22, len(plan["boss_region_additions"]))
        self.assertEqual(14, len(plan["boss_generator_additions"]))
        self.assertEqual(
            {
                982000,
                982001,
                982002,
                982003,
                982004,
                982005,
                982006,
                982007,
                982008,
                982009,
            },
            {x["destination_entity_id"] for x in plan["boss_actor_additions"]},
        )
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(60, len(retained))
        self.assertEqual(set(ROM_STATES), {row["map"] for row in retained})
        for state in ROM_STATES:
            rows = [row for row in retained if row["map"] == state]
            self.assertEqual(
                list(range(3200200, 3200230)), [row["entity_id"] for row in rows]
            )
            self.assertEqual(
                list(ROM_SPIDER_PINS[state]),
                [row["source_provenance"]["part_sha256"] for row in rows],
            )
        policy = plan["boss_contract"]["destination_operand_policy"]
        self.assertEqual(3202801, policy["destination_region"])
        self.assertIn("event13204803", policy["evidence"])

    def test_pin_and_allocation_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129943"):
            patch_celestial_emissary_at_rom(
                self.rom,
                self.ce,
                replace(DEFAULT_IDS, giant_ai=DEFAULT_IDS.giant_command),
            )
        with self.assertRaisesRegex(ValueError, "129943"):
            patch_celestial_emissary_at_rom(
                self.rom,
                self.ce,
                replace(DEFAULT_IDS, music_flag=DEFAULT_IDS.giant_phase),
            )
        with self.assertRaisesRegex(ValueError, "allocation"):
            patch_celestial_emissary_at_rom(
                self.rom, self.ce, replace(DEFAULT_IDS, evidence="")
            )
        with self.assertRaisesRegex(ValueError, "Celestial donor"):
            patch_celestial_emissary_at_rom(
                self.rom,
                self.ce.replace("HPRatio(2420810) < 0.6", "HPRatio(2420810) < 0.5"),
            )
        with self.assertRaisesRegex(ValueError, "Rom arena"):
            patch_celestial_emissary_at_rom(
                self.rom.replace("HandleBossDefeat(3200800)", "HandleBossDefeat(8)"),
                self.ce,
            )
        missing_spider = [
            row
            for row in self.slots
            if not (row.map_name == ROM_STATES[1] and row.entity_id == 3200229)
        ]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_celestial_at_rom(
                missing_spider, self.npcs, self.effects, "missing-spider"
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        required = (
            "common.emevd.dcx",
            "m24_02_00_00.emevd.dcx",
            "m32_00_00_00.emevd.dcx",
        )
        if not compiler.is_file() or any(not (events / x).is_file() for x in required):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
            o, s, out = work / "o", work / "s", work / "out"
            o.mkdir()
            for x in required:
                shutil.copyfile(events / x, o / x)
            subprocess.run(
                [
                    str(compiler),
                    "/cmd",
                    "-decompile",
                    "-game",
                    "bb",
                    "-indir",
                    str(o),
                    "-outdir",
                    str(s),
                    "-force",
                    "-silent",
                ],
                check=True,
            )
            (s / "m32_00_00_00.emevd.dcx.js").write_text(
                patch_celestial_emissary_at_rom(
                    (s / "m32_00_00_00.emevd.dcx.js").read_text(encoding="utf-8-sig"),
                    (s / "m24_02_00_00.emevd.dcx.js").read_text(encoding="utf-8-sig"),
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
                    str(s),
                    "-outdir",
                    str(out),
                    "-force",
                    "-silent",
                ],
                check=True,
            )
            self.assertTrue((out / "m32_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
