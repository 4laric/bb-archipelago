import hashlib, shutil, subprocess, tempfile, unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.moon_micolash_contract import (
    BUNDLE,
    DONOR_SOURCE,
    ARENA_SOURCE,
    DEFAULT_IDS,
    native_plan_moon_at_micolash,
    patch_moon_at_micolash,
)


class MoonMicolashContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
        cls.moon = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "slots.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(p)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_moon_health_limbs_and_actual_death_bridge_are_explicit(self):
        before = event_blocks(self.arena)
        after = event_blocks(patch_moon_at_micolash(self.arena, self.moon))
        health = after[12604852]
        self.assertIn("DisplayBossHealthBar(Enabled, 2600850, 0, 540000);", health)
        self.assertIn("SetCharacterInvincibility(2600850, Disabled);", health)
        self.assertIn("StartTimeMeasurement(2601010, 232, Enabled);", health)
        limbs = after[DEFAULT_IDS.limb_controller]
        self.assertIn("CreateNPCPart(2600850, npcPartId", limbs)
        bridge = after[DEFAULT_IDS.terminal_bridge]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2600850));"),
            bridge.index("SetEventFlag(72600301, ON);"),
        )
        self.assertEqual(before[12601850], after[12601850])

    def test_direct_combat_retires_chase_and_uses_moon_music_camera(self):
        after = event_blocks(patch_moon_at_micolash(self.arena, self.moon))
        self.assertIn("CharacterHasEventMessage(2600850, 500)", after[12604853])
        camera = after[12604854]
        self.assertIn("SetLockcamSlotNumber(26, 0, 1)", camera)
        self.assertEqual(
            "    WaitFor(InArea(10000, 0));", after[12604879].splitlines()[1]
        )
        self.assertIn(
            "SetCharacterImmortality(10000, Enabled);",
            after[DEFAULT_IDS.player_immortality],
        )

    def test_plan_is_single_pinned_primary_with_no_invented_helpers(self):
        plan = native_plan_moon_at_micolash(
            self.slots, self.npcs, self.effects, "moon-mico"
        )
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual("c5400", plan["swaps"][0]["target"]["model_name"])
        self.assertNotIn("boss_actor_additions", plan)
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual(0, binding["destination_talk_id_override"])
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])
        self.assertIn(
            12604879, plan["boss_contract"]["disabled_destination_chase_events"]
        )

    def test_ids_and_pins_refuse(self):
        with self.assertRaisesRegex(ValueError, "allocation"):
            patch_moon_at_micolash(
                self.arena,
                self.moon,
                replace(DEFAULT_IDS, terminal_bridge=DEFAULT_IDS.limb_controller),
            )
        with self.assertRaisesRegex(ValueError, "Micolash arena"):
            patch_moon_at_micolash(
                self.arena.replace("HandleBossDefeat(2600850)", "HandleBossDefeat(7)"),
                self.moon,
            )
        with self.assertRaisesRegex(ValueError, "Moon Presence donor"):
            patch_moon_at_micolash(
                self.arena,
                self.moon.replace(
                    "DisplayBossHealthBar(Enabled, 2100810, 0, 540000)",
                    "DisplayBossHealthBar(Enabled, 2100810, 0, 1)",
                ),
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        required = (
            "common.emevd.dcx",
            "m21_00_00_00.emevd.dcx",
            "m26_00_00_00.emevd.dcx",
        )
        if not compiler.is_file() or any(not (events / x).is_file() for x in required):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as d:
            work = Path(d)
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
            (source / "m26_00_00_00.emevd.dcx.js").write_text(
                patch_moon_at_micolash(
                    (source / "m26_00_00_00.emevd.dcx.js").read_text(
                        encoding="utf-8-sig"
                    ),
                    (source / "m21_00_00_00.emevd.dcx.js").read_text(
                        encoding="utf-8-sig"
                    ),
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
            self.assertTrue((output / "m26_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
