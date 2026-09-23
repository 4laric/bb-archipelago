import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.arena_port import (
    GEHRMAN_PORT,
    MARIA_CROSS_ARENA_PORTS,
    MICOLASH_PORT,
    MOON_PORT,
)
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.maria_contract import (
    MARIA_EVENT_FILE,
    MARIA_EVENT_TARGET,
)
from tools.bb_enemizer.maria_donor import (
    MARIA_PRIMARY_PIN,
    MariaArenaAllocation,
    native_plan_maria_donor,
    patch_maria_donor,
)
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"
ALLOCATION = MariaArenaAllocation(12994700, 12994701)


class MariaCrossArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maria = read_blob(
            BUNDLE, "event/" + MARIA_EVENT_FILE
        ).decode("utf-8-sig")
        cls.destinations = {
            port.arena.key: read_blob(
                BUNDLE, "event/" + port.arena.event_file
            ).decode("utf-8-sig")
            for port in MARIA_CROSS_ARENA_PORTS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def _patched(self, port):
        return patch_maria_donor(
            port, self.destinations[port.arena.key], self.maria, ALLOCATION
        )

    def test_ports_separate_constructor_insertion_from_event_retirement(self):
        self.assertNotIn(GEHRMAN_PORT.constructor.event_id, GEHRMAN_PORT.retired_events)
        self.assertIn(MOON_PORT.constructor.event_id, MOON_PORT.retired_events)
        self.assertNotIn(MICOLASH_PORT.constructor.event_id, MICOLASH_PORT.retired_events)
        corpus = b"\n".join(read_prefix(BUNDLE, "event/").values())
        corpus += b"\n" + b"\n".join(read_prefix(BUNDLE, "mined/").values())
        self.assertNotIn(b"12996800", corpus)

    def test_three_ports_preserve_progression_and_install_all_maria_combat_phases(self):
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(arena=port.arena.key):
                arena = port.arena
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(self._patched(port))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                for event_id in port.protected_events:
                    self.assertEqual(before[event_id], after[event_id])
                self.assertEqual(
                    1,
                    after[0].count(
                        f"$InitializeEvent(0, {ALLOCATION.phase_cleanup_event});"
                    ),
                )
                self.assertIn(port.constructor.statement(), after[0])
                self.assertNotIn("PlayCutscene", after[arena.activation_event])
                self.assertIn(
                    f"SetEventFlag({arena.start_flag}, ON)",
                    after[arena.activation_event],
                )

                health = after[arena.health_bar_event]
                for witness in (
                    f"SetNetworkUpdateAuthority({arena.actor}, AuthorityLevel.Normal)",
                    f"SetSpEffect({arena.actor}, 7500, false)",
                    f"SetSpEffect({arena.actor}, 7501, false)",
                    f"SetCharacterAIState({arena.actor}, Enabled)",
                    f"SetCharacterEventTarget({arena.actor}, {MARIA_EVENT_TARGET})",
                    f"if (!EventFlag({ALLOCATION.health_initialized_flag}))",
                ):
                    self.assertIn(witness, health)
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 100)",
                    after[arena.music_event],
                )
                self.assertEqual(
                    2,
                    after[arena.lockcam_event].count(
                        f"SetLockcamSlotNumber({arena.lockcam_map}, "
                        f"{arena.lockcam_subarea},"
                    ),
                )
                cleanup = after[ALLOCATION.phase_cleanup_event]
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 20)", cleanup)
                self.assertIn(f"ClearSpEffect({arena.actor}, 5526)", cleanup)

    def test_destination_entry_relocation_and_coop_restore_remain_owned_by_port(self):
        gehrman = event_blocks(self._patched(GEHRMAN_PORT))
        self.assertIn(
            "IssueShortWarpRequest(10000, TargetEntityType.Area, 2102808, -1)",
            gehrman[12101802],
        )
        self.assertIn("SetEventFlag(12104800, ON)", gehrman[12101803])
        moon = event_blocks(self._patched(MOON_PORT))
        self.assertEqual(2, moon[12101852].count(
            "IssueShortWarpRequest(10000, TargetEntityType.Area, 2102809, -1)"
        ))
        self.assertIn("SetEventFlag(12104850, ON)", moon[12101853])
        micolash = event_blocks(self._patched(MICOLASH_PORT))
        self.assertNotIn("PlayCutscene", micolash[12601852])
        self.assertIn("SetEventFlag(12604850, ON)", micolash[12601855])

    def test_micolash_is_a_continuous_initial_space_fight_with_terminal_bridge(self):
        before = event_blocks(self.destinations[MICOLASH_PORT.arena.key])
        after = event_blocks(self._patched(MICOLASH_PORT))
        for event_id in MICOLASH_PORT.retired_events:
            self.assertIn("WaitFor(InArea(10000, 0));", after[event_id])
            self.assertNotIn("SetCharacterAICommand", after[event_id])
            self.assertNotIn("SetDistanceLimitForConversationStateProcessing", after[event_id])
        bridge = after[MICOLASH_PORT.terminal_bridge_event]
        self.assertIn("WaitFor(CharacterDead(2600850));", bridge)
        self.assertIn("SetEventFlag(72600301, ON);", bridge)
        self.assertEqual(before[12601850], after[12601850])
        self.assertEqual(before[12604855], after[12604855])
        self.assertIn("original-initial-area-direct-fight", str(
            native_plan_maria_donor(
                MICOLASH_PORT, self.slots, self.npcs, self.effects,
                ALLOCATION, "micolash-direct",
            )["boss_contract"]
        ))

    def test_native_plans_pin_original_maria_and_destination_rosters(self):
        expected_helpers = {"gehrman": 2, "moon-presence": 2, "micolash": 0}
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(arena=port.arena.key):
                plan = native_plan_maria_donor(
                    port, self.slots, self.npcs, self.effects,
                    ALLOCATION, "native-evidence",
                )
                binding = plan["primary_init_source_bindings"][0]
                self.assertEqual("m35_00_00_00", binding["source_map"])
                self.assertEqual(3500800, binding["source_entity_id"])
                self.assertEqual(
                    MARIA_PRIMARY_PIN,
                    binding["source_provenance"]["part_sha256"],
                )
                self.assertEqual(port.primary_talk_id,
                                 binding["destination_original_talk_id"])
                if port.primary_talk_id:
                    self.assertEqual(0, binding["destination_talk_id_override"])
                else:
                    self.assertNotIn("destination_talk_id_override", binding)
                evidence = plan["boss_contract"]["destination_native_evidence"]
                self.assertEqual(port.destination_msb_sha256, evidence["msb_sha256"])
                self.assertEqual(port.primary_part_sha256,
                                 evidence["primary_part_sha256"])
                helpers = plan["boss_contract"]["retained_destination_helpers"]
                self.assertEqual(expected_helpers[port.arena.key], len(helpers))
                self.assertEqual(
                    {row.part_sha256 for row in port.retained_native_actors},
                    {row["source_provenance"]["part_sha256"] for row in helpers},
                )

    def test_native_plan_rejects_missing_retained_actor(self):
        slots = [slot for slot in self.slots if not (
            slot.map_name == GEHRMAN_PORT.destination_map
            and slot.entity_id == GEHRMAN_PORT.retained_native_actors[0].entity_id
        )]
        with self.assertRaisesRegex(ValueError, "exact pinned destination roster"):
            native_plan_maria_donor(
                GEHRMAN_PORT, slots, self.npcs, self.effects,
                ALLOCATION, "missing-helper",
            )

    def test_all_three_exact_original_routes_compile_with_pinned_darkscript(self):
        compiler = ROOT / "work/DarkScript3/DarkScript3.exe"
        events = ROOT / "work/boss-shuffle-validation/events"
        required_common = ("common.emevd.dcx", "m35_00_00_00.emevd.dcx")
        if (not compiler.is_file()
                or any(not (events / name).is_file() for name in required_common)
                or any(not (events / port.arena.event_file.removesuffix(".js")).is_file()
                       for port in MARIA_CROSS_ARENA_PORTS)):
            self.skipTest("pinned DarkScript/original event fixtures unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(arena=port.arena.key), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                original, source, output = work / "o", work / "s", work / "out"
                original.mkdir()
                destination_binary = port.arena.event_file.removesuffix(".js")
                for name in (*required_common, destination_binary):
                    shutil.copyfile(events / name, original / name)
                subprocess.run([
                    str(compiler), "/cmd", "-decompile", "-game", "bb",
                    "-indir", str(original), "-outdir", str(source),
                    "-force", "-silent",
                ], check=True)
                destination_path = source / port.arena.event_file
                maria_path = source / MARIA_EVENT_FILE
                destination_path.write_text(
                    patch_maria_donor(
                        port,
                        destination_path.read_text(encoding="utf-8-sig"),
                        maria_path.read_text(encoding="utf-8-sig"),
                        ALLOCATION,
                    ),
                    encoding="utf-8-sig",
                )
                subprocess.run([
                    str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output),
                    "-force", "-silent",
                ], check=True)
                compiled = output / destination_binary
                self.assertTrue(compiled.is_file())
                self.assertGreater(compiled.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
