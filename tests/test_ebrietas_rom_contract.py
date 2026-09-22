import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.ebrietas_rom_contract import (
    BUNDLE,
    DEFAULT_IDS,
    EBRIETAS_SOURCE,
    OWNER_ENTITY,
    ROM_SOURCE,
    ebrietas_rom_helper_scaling_parents,
    native_plan_ebrietas_at_rom,
    patch_ebrietas_at_rom,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class EbrietasRomContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ebrietas = read_blob(BUNDLE, EBRIETAS_SOURCE).decode("utf-8-sig")
        cls.rom = read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self):
        return event_blocks(patch_ebrietas_at_rom(self.rom, self.ebrietas))

    def test_rom_terminal_blood_moon_coop_entry_and_player_fall_are_preserved(self):
        before, after = event_blocks(self.rom), self.patched()
        protected = (
            13201800,
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
        )
        self.assertEqual(
            {event: before[event] for event in protected},
            {event: after[event] for event in protected},
        )
        self.assertIn("PlayCutsceneAndChangeTimePeriod(32000000", after[13201803])
        self.assertIn("WarpPlayerToRespawnPoint(2802958)", after[13201803])

    def test_rom_damage_trigger_runs_ebrietas_wake_sequence(self):
        activation = self.patched()[13201802]
        self.assertIn("HasDamageType(3200800, -1, DamageType.Unspecified)", activation)
        self.assertIn("ForceAnimationPlayback(3200800, 7001, true", activation)
        self.assertIn("SetCharacterImmortality(3200800, Enabled)", activation)
        self.assertIn("SetSpEffect(3200800, 5647, false)", activation)
        self.assertIn("ForceAnimationPlayback(3200800, 7000, false, true", activation)
        self.assertLess(
            activation.index("ClearSpEffect(3200800, 5647)"),
            activation.index("SetEventFlag(13204800, ON)"),
        )
        self.assertIn("$InitializeEvent(0, 9350, 2)", activation)

    def test_ebrietas_combat_closure_uses_rom_arena_operands(self):
        after = self.patched()
        health = after[13204802]
        self.assertIn("DisplayBossHealthBar(Enabled, 3200800, 0, 251000)", health)
        self.assertIn("CreatePlaylog(124)", health)
        self.assertIn("StartTimeMeasurement(3200010, 62, Enabled)", health)
        music = after[13204803]
        self.assertIn("InArea(10000, 3202801)", music)
        self.assertIn("SetMapSoundState(3203802, Disabled)", music)
        self.assertNotIn("12425246", music)
        self.assertEqual(2, after[13204804].count("SetLockcamSlotNumber(32, 0,"))
        self.assertIn("HPRatio(3200800) < 0.5", after[DEFAULT_IDS.phase])
        self.assertIn(
            f"ShootBullet({OWNER_ENTITY}, 3200800, 6, 225100310",
            after[DEFAULT_IDS.bullet],
        )

    def test_constructor_copies_exact_phase_bullet_and_five_limb_bindings(self):
        constructor = self.patched()[0]
        expected = {
            DEFAULT_IDS.phase: 1,
            DEFAULT_IDS.bullet: 1,
            DEFAULT_IDS.limb_part5: 1,
            DEFAULT_IDS.limb_parts1_4: 4,
            DEFAULT_IDS.owner_cleanup: 1,
            DEFAULT_IDS.spider_cleanup: 1,
        }
        self.assertEqual(
            expected,
            {
                event: len(
                    re.findall(
                        r"\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))",
                        constructor,
                    )
                )
                for event in expected
            },
        )
        self.assertEqual(1, constructor.count(f"CreateBulletOwner({OWNER_ENTITY});"))

    def test_native_spider_controllers_are_retired_and_cleanup_waits_for_terminal(self):
        after = self.patched()
        retired = (13204000, 13204050, 13204730, 13204807, 13204808, 13204809, 13204810)
        self.assertEqual(
            {event: "    EndEvent();" for event in retired},
            {event: after[event].splitlines()[1] for event in retired},
        )
        cleanup = after[DEFAULT_IDS.spider_cleanup]
        wait = cleanup.index("WaitFor(EventFlag(13201800));")
        self.assertEqual(30, cleanup[:wait].count("ChangeCharacterEnableState("))
        self.assertEqual(30, cleanup[:wait].count("SetCharacterAIState("))
        self.assertNotIn("ForceCharacterDeath", cleanup[:wait])
        self.assertEqual(30, cleanup[wait:].count("ForceCharacterDeath("))
        self.assertIn(
            f"ForceCharacterDeath({OWNER_ENTITY}, false)",
            after[DEFAULT_IDS.owner_cleanup],
        )

    def test_native_plan_pins_owner_spiders_and_post_defeat_actors(self):
        plan = native_plan_ebrietas_at_rom(
            self.slots, self.npcs, self.effects, "ebrietas-rom"
        )
        self.assertEqual("c2510", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {("m32_00_00_00", OWNER_ENTITY), ("m32_00_00_01", OWNER_ENTITY)},
            {
                (row["destination_map"], row["destination_entity_id"])
                for row in plan["boss_actor_additions"]
            },
        )
        self.assertEqual(2, len(plan["primary_init_source_bindings"]))
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(64, len(retained))
        self.assertEqual(60, sum(row["part"].startswith("c1400_") for row in retained))
        self.assertEqual(
            {
                (state, part)
                for state in ("m32_00_00_00", "m32_00_00_01")
                for part in ("c8070_0000", "c3060_0000")
            },
            {
                (row["map"], row["part"])
                for row in retained
                if row["entity_id"] == 3200801
            },
        )
        self.assertEqual(2, len(ebrietas_rom_helper_scaling_parents(plan)))
        self.assertNotIn("boss_generator_additions", plan)
        self.assertEqual("unobserved", plan["boss_contract"]["runtime_status"])

    def test_collisions_source_destination_and_roster_drift_refuse(self):
        with self.assertRaisesRegex(ValueError, "129922xx"):
            patch_ebrietas_at_rom(
                self.rom, self.ebrietas, replace(DEFAULT_IDS, phase=DEFAULT_IDS.bullet)
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Ebrietas donor"):
            patch_ebrietas_at_rom(
                self.rom,
                self.ebrietas.replace(
                    "HPRatio(2420800) < 0.5", "HPRatio(2420800) < 0.4"
                ),
            )
        with self.assertRaisesRegex(ValueError, "unsupported original Rom arena"):
            patch_ebrietas_at_rom(
                self.rom.replace("HandleBossDefeat(3200800)", "HandleBossDefeat(9)"),
                self.ebrietas,
            )
        reduced = [slot for slot in self.slots if slot.entity_id != 3200229]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_ebrietas_at_rom(
                reduced, self.npcs, self.effects, "missing-spider"
            )


if __name__ == "__main__":
    unittest.main()
