import re
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.bsb_celestial_emissary_contract import (
    BSB_SOURCE,
    BUNDLE,
    CELESTIAL_SOURCE,
    DEFAULT_IDS,
    EBRIETAS_EVENTS,
    GENERATORS,
    GIANT,
    SUPPORT,
    TERMINAL,
    WAVES,
    BsbCelestialIds,
    native_plan_bsb_at_celestial_emissary,
    patch_bsb_at_celestial_emissary,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params


class BsbCelestialEmissaryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bsb = (
            read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig").replace("\r\n", "\n")
        )
        cls.celestial = (
            read_blob(BUNDLE, CELESTIAL_SOURCE)
            .decode("utf-8-sig")
            .replace("\r\n", "\n")
        )
        with tempfile.TemporaryDirectory() as directory:
            slots_file = Path(directory) / "slots.tsv"
            slots_file.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(slots_file)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self):
        return event_blocks(patch_bsb_at_celestial_emissary(self.celestial, self.bsb))

    def test_giant_terminal_is_byte_identical_and_bsb_death_bridges_afterward(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        self.assertEqual(before[TERMINAL], after[TERMINAL])
        self.assertIn("WaitFor(CharacterDead(2420811));", after[TERMINAL])
        bridge = after[DEFAULT_IDS.death_to_giant]
        self.assertLess(
            bridge.index("WaitFor(CharacterDead(2420810));"),
            bridge.index("ForceCharacterDeath(2420811, false);"),
        )
        self.assertIn("EndIf(EventFlag(12421700));", bridge)

    def test_entry_fog_retry_and_coop_remain_destination_owned(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        for event in (12421701, 12424705, 12424710, 12424711):
            self.assertEqual(before[event], after[event], event)
        self.assertIn("InArea(10000, 2422815)", after[12421702])
        self.assertIn("ForceAnimationPlayback(2420810, 7001", after[12421702])
        self.assertIn("EventFlag(12424700)", after[12421703])
        self.assertIn("SetEventFlag(12421702, ON);", after[12421703])

    def test_health_music_camera_and_phases_are_destination_bound(self):
        after = self.patched()
        health = after[12424702]
        self.assertIn("DisplayBossHealthBar(Enabled, 2420810, 0, 209000);", health)
        self.assertIn(
            "SetNetworkUpdateAuthority(2420811, AuthorityLevel.Forced);", health
        )
        self.assertNotIn("CreateReferredDamagePair", health)
        self.assertIn("SetMapSoundState(2423812, Disabled);", after[12424703])
        self.assertIn("InArea(10000, 2422812)", after[12424703])
        self.assertIn("EventFlag(12992301)", after[12424703])
        camera = after[12424704]
        self.assertIn("SetLockcamSlotNumber(24, 2, 1);", camera)
        self.assertNotIn("SetLockcamSlotNumber(23,", camera)
        self.assertLess(
            camera.index("EndIf(EventFlag(12421700));"), camera.index("WaitFor(")
        )
        self.assertIn("HPRatio(2420810) < 0.67", after[DEFAULT_IDS.phase_one])
        self.assertIn(
            "HPRatio(2420810) < 0.33 && EventFlag(12992300)",
            after[DEFAULT_IDS.phase_two],
        )
        copied = "\n".join(
            after[event]
            for event in (
                12421702,
                12421703,
                12424702,
                12424703,
                12424704,
                *DEFAULT_IDS.values(),
            )
        )
        self.assertNotRegex(copied, r"(?<!\d)(?:123|230)\d+(?!\d)")

    def test_wave_giant_phase_and_generator_controllers_are_retired_without_early_death(
        self,
    ):
        after = self.patched()
        for event in (
            12424770,
            12424780,
            12424784,
            12424785,
            12424787,
            12424790,
            12424791,
            12424792,
            12424795,
        ):
            self.assertEqual("    EndEvent();", after[event].splitlines()[1], event)
        retire = after[DEFAULT_IDS.retire_celestial]
        for generator in GENERATORS:
            self.assertIn(f"DeactivateGenerator({generator}, Disabled);", retire)
        wait = retire.index("WaitFor(EventFlag(12421700));")
        for actor in (*WAVES, *SUPPORT):
            self.assertIn(f"ChangeCharacterEnableState({actor}, Disabled);", retire)
            self.assertGreater(
                retire.rindex(f"ForceCharacterDeath({actor}, false);"), wait
            )
        self.assertNotIn("ForceCharacterDeath(2420811", retire)

    def test_ebrietas_and_unrelated_destination_events_remain_exact(self):
        before = event_blocks(self.celestial)
        after = self.patched()
        for event in EBRIETAS_EVENTS:
            self.assertEqual(before[event], after[event], event)
        remove = re.compile(r"\n    \$InitializeEvent\(0, 129923(?:00|01|02|03)\);")
        self.assertEqual(before[0], remove.sub("", after[0]))

    def test_native_plan_pins_giant_waves_and_support(self):
        plan = native_plan_bsb_at_celestial_emissary(
            self.slots, self.npcs, self.effects, "celestial"
        )
        self.assertEqual(1, plan["swap_count"])
        destination = plan["swaps"][0]["destinations"][
            plan["swaps"][0]["destination_keys"][0]
        ]
        self.assertEqual(2420810, destination["entity_id"])
        binding = plan["primary_init_source_bindings"][0]
        self.assertEqual("m23_00_00_00", binding["source_map"])
        self.assertEqual("c2500_0000", binding["destination_part"])
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(
            {GIANT, *WAVES, *SUPPORT}, {row["entity_id"] for row in retained}
        )
        for row in retained:
            self.assertRegex(row["source_provenance"]["part_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(plan["scaling"]["enabled"])

    def test_ids_and_source_drift_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "129923xx"):
            patch_bsb_at_celestial_emissary(
                self.celestial,
                self.bsb,
                replace(DEFAULT_IDS, phase_two=DEFAULT_IDS.phase_one),
            )
        with self.assertRaisesRegex(ValueError, "BSB donor"):
            patch_bsb_at_celestial_emissary(
                self.celestial,
                self.bsb.replace(
                    "HPRatio(2300800) < 0.67", "HPRatio(2300800) < 0.5", 1
                ),
            )
        with self.assertRaisesRegex(ValueError, "Celestial arena"):
            patch_bsb_at_celestial_emissary(
                self.celestial.replace(
                    "HandleBossDefeat(2420811)", "HandleBossDefeat(7)"
                ),
                self.bsb,
            )


if __name__ == "__main__":
    unittest.main()
