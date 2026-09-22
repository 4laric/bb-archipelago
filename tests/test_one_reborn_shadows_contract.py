import hashlib, shutil, subprocess, tempfile, unittest
from dataclasses import replace
from pathlib import Path
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.one_reborn_shadows_contract import *


class OneRebornShadowsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
        cls.d = read_blob(BUNDLE, ONE_REBORN_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.tsv"
            p.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(p)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_proxy_death_releases_three_body_terminal_with_full_source_helpers(self):
        before = event_blocks(self.a)
        after = event_blocks(patch_one_reborn_at_shadows(self.a, self.d))
        health = after[12704802]
        self.assertIn("CreateReferredDamagePair(2700800, 982302);", health)
        self.assertIn("DisplayBossHealthBar(Enabled, 982302, 0, 507000);", health)
        bridge = after[DEFAULT_IDS.bridge]
        self.assertLess(
            bridge.index("WaitFor(HPRatio(982302) <= 0);"),
            bridge.index("ForceCharacterDeath(2700801, false);"),
        )
        self.assertLess(
            bridge.index("ForceCharacterDeath(2700802, false);"),
            bridge.index("ForceCharacterDeath(2700800, false);"),
        )
        self.assertEqual(before[12701800], after[12701800])
        self.assertIn(
            "CharacterDead(2700800) && CharacterDead(2700801) && CharacterDead(2700802)",
            after[12701800],
        )
        self.assertLess(
            bridge.index("SetCharacterImmortality(2700801, Disabled);"),
            bridge.index("ForceCharacterDeath(2700801, false);"),
        )

    def test_precombat_retires_shadow_combat_without_releasing_terminal_witnesses(self):
        after = event_blocks(patch_one_reborn_at_shadows(self.a, self.d))
        health = after[12704802]
        activation = after[12701802]
        for entity in (2700801, 2700802):
            self.assertIn(f"SetCharacterAIState({entity}, Disabled);", health)
            self.assertIn(f"SetCharacterHPBarDisplay({entity}, Disabled);", health)
            self.assertIn(f"SetCharacterImmortality({entity}, Enabled);", health)
            self.assertIn(f"ChangeCharacterEnableState({entity}, Disabled);", health)
            self.assertNotIn(f"ForceCharacterDeath({entity}, false);", health)
            self.assertNotIn(
                f"ChangeCharacterEnableState({entity}, Enabled);", activation
            )
        for generator in (2705001, 2705002, 2705003):
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", health)
        for entity in (2700803, 2700804, 2700805, 2700810, 2700811, 2700813, 2700814):
            self.assertIn(f"ForceCharacterDeath({entity}, false);", health)

    def test_source_caster_counterbits_music_and_shadow_retirement_are_explicit(self):
        after = event_blocks(patch_one_reborn_at_shadows(self.a, self.d))
        self.assertIn(
            "SetCharacterEventTarget(chrEntityId, 982300);",
            after[DEFAULT_IDS.caster_react],
        )
        self.assertEqual(1, after[0].count("$InitializeEvent(0, 12994619, 982304);"))
        for event_id in (DEFAULT_IDS.bridge, DEFAULT_IDS.cleanup):
            self.assertEqual(1, after[0].count(f"$InitializeEvent(0, {event_id});"))
        self.assertIn("CharacterHasEventMessage(2700800, 300)", after[12704803])
        self.assertIn("InArea(10000, 2702802)", after[12704803])
        self.assertNotIn("2803804", after[12704803])
        policy = native_plan_one_reborn_at_shadows(
            self.slots, self.npcs, self.effects, "one-shadows"
        )["boss_contract"]["destination_operand_policy"]
        self.assertEqual(2702802, policy["destination_region"])
        self.assertIn("event 12704803", policy["evidence"])
        for e in (
            12704806,
            12704807,
            12704810,
            12704811,
            12704812,
            12704815,
            12704825,
            12704830,
        ):
            self.assertEqual("    EndEvent();", after[e].splitlines()[1])

    def test_native_plan_requires_full_nine_helper_two_state_roster(self):
        p = native_plan_one_reborn_at_shadows(
            self.slots, self.npcs, self.effects, "one-shadows"
        )
        self.assertEqual("the-one-reborn", p["boss_contract"]["donor"])
        self.assertEqual(18, len(p["boss_actor_additions"]))
        self.assertEqual(
            set(range(982300, 982309)),
            {x["destination_entity_id"] for x in p["boss_actor_additions"]},
        )
        retained = p["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(18, len(retained))
        self.assertEqual(
            {
                2700801,
                2700802,
                2700803,
                2700804,
                2700805,
                2700810,
                2700811,
                2700813,
                2700814,
            },
            {row["entity_id"] for row in retained},
        )
        self.assertEqual(
            {"m27_00_00_00", "m27_00_00_01"},
            {row["map"] for row in retained},
        )
        for row in retained:
            self.assertEqual("bb-boss-actor-pin-v1", row["source_provenance"]["format"])
            self.assertRegex(row["source_provenance"]["part_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(
                {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                row["source_initialization"],
            )
        self.assertEqual("unobserved", p["boss_contract"]["runtime_status"])

    def test_retained_helper_rows_require_every_state_and_exact_archetype(self):
        missing_secondary = [
            slot
            for slot in self.slots
            if not (slot.map_name == "m27_00_00_01" and slot.entity_id == 2700802)
        ]
        with self.assertRaisesRegex(ValueError, "pinned actor 2700802"):
            native_plan_one_reborn_at_shadows(
                missing_secondary, self.npcs, self.effects, "missing-secondary"
            )
        missing_helper = [
            slot
            for slot in self.slots
            if not (slot.map_name == "m27_00_00_00" and slot.entity_id == 2700814)
        ]
        with self.assertRaisesRegex(ValueError, "pinned actor 2700814"):
            native_plan_one_reborn_at_shadows(
                missing_helper, self.npcs, self.effects, "missing-helper"
            )
        changed_helper = [
            (
                replace(slot, archetype=Archetype("c5033", 1, 1, 0))
                if slot.map_name == "m27_00_00_01" and slot.entity_id == 2700803
                else slot
            )
            for slot in self.slots
        ]
        with self.assertRaisesRegex(ValueError, "pinned actor 2700803"):
            native_plan_one_reborn_at_shadows(
                changed_helper, self.npcs, self.effects, "changed-helper"
            )

    def test_pin_and_counter_allocation_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129946"):
            patch_one_reborn_at_shadows(
                self.a, self.d, replace(DEFAULT_IDS, bridge=DEFAULT_IDS.phase_one)
            )
        with self.assertRaisesRegex(ValueError, "129946"):
            patch_one_reborn_at_shadows(
                self.a, self.d, replace(DEFAULT_IDS, caster_react=DEFAULT_IDS.camera)
            )
        with self.assertRaisesRegex(ValueError, "129946"):
            patch_one_reborn_at_shadows(
                self.a, self.d, replace(DEFAULT_IDS, phase_two=DEFAULT_IDS.phase_one)
            )
        with self.assertRaisesRegex(ValueError, "129946"):
            patch_one_reborn_at_shadows(
                self.a,
                self.d,
                replace(DEFAULT_IDS, notification_flag=DEFAULT_IDS.caster_count_flag),
            )
        with self.assertRaisesRegex(ValueError, "One Reborn donor"):
            patch_one_reborn_at_shadows(
                self.a,
                self.d.replace(
                    "CreateReferredDamagePair(2800800, 2800803)",
                    "CreateReferredDamagePair(1, 2800803)",
                ),
            )
        with self.assertRaisesRegex(ValueError, "Shadows arena"):
            patch_one_reborn_at_shadows(
                self.a.replace("HandleBossDefeat(2700800)", "HandleBossDefeat(1)"),
                self.d,
            )

    def test_patched_source_compiles_with_pinned_darkscript_when_available(self):
        root = Path(__file__).resolve().parents[1]
        compiler = root / "work" / "DarkScript3" / "DarkScript3.exe"
        events = root / "work" / "boss-shuffle-validation" / "events"
        required = (
            "common.emevd.dcx",
            "m27_00_00_00.emevd.dcx",
            "m28_00_00_00.emevd.dcx",
            "m24_02_00_00.emevd.dcx",
        )
        if not compiler.is_file() or any(not (events / x).is_file() for x in required):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as d:
            w = Path(d)
            o, s, out = w / "o", w / "s", w / "out"
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
            (s / "m27_00_00_00.emevd.dcx.js").write_text(
                patch_one_reborn_at_shadows(
                    (s / "m27_00_00_00.emevd.dcx.js").read_text(encoding="utf-8-sig"),
                    (s / "m28_00_00_00.emevd.dcx.js").read_text(encoding="utf-8-sig"),
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
            self.assertTrue((out / "m27_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
