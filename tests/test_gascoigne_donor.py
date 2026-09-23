import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.gascoigne_donor import (
    BEAST_PINS,
    CO_OP_RESTORE_EVENTS,
    DEFAULT_GASCOIGNE_IDS,
    GASCOIGNE_BEAST,
    GASCOIGNE_HUMAN,
    GASCOIGNE_STATE_BINDINGS,
    HUMAN_PINS,
    SOURCE_ALTERNATES,
    SUPPORTED_GASCOIGNE_ARENAS,
    helper_scaling_parents,
    native_plan_gascoigne_donor,
    patch_gascoigne_donor,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"
IDS = DEFAULT_GASCOIGNE_IDS


class GascoigneDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_GASCOIGNE_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_reserved_ids_are_absent_from_original_corpus_and_next_allocations(self):
        corpus = b"\n".join(
            body for prefix in ("event/", "mined/") for body in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        self.assertEqual((983100, 12995600, 12995601, 12995602, 12995603,
                          12995604, 12995605, 12995606),
                         IDS.numeric_ids())
        for value in IDS.numeric_ids():
            self.assertNotRegex(corpus, rf"(?<![\w]){value}(?![\w])")
        next_root = ROOT.parent / "bb-boss-next-arenas"
        if next_root.is_dir():
            declared = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                                 for path in next_root.rglob("*.py"))
            self.assertNotRegex(declared, r"(?<![\w])1299560[0-6](?![\w])")

    def test_all_six_preserve_destination_terminal_and_coop_while_importing_two_actor_graph(self):
        for arena in SUPPORTED_GASCOIGNE_ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_gascoigne_donor(arena, self.destinations[arena.key], self.donor))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                co_op = CO_OP_RESTORE_EVENTS[arena.key]
                self.assertEqual(before[co_op], after[co_op])
                self.assertEqual(set(IDS.event_ids()), set(after) - set(before))
                health = after[arena.health_bar_event]
                self.assertIn(f"CreateReferredDamagePair({arena.actor}, {IDS.beast_entity})", health)
                self.assertEqual(2, health.count(
                    f"WaitFor(EventFlag({IDS.readiness_event}))"))
                phase = after[IDS.phase_event]
                self.assertIn(f"ChangeCharacterEnableState({IDS.beast_entity}, Enabled)", phase)
                self.assertIn(f"SetCharacterInvincibility({IDS.beast_entity}, Disabled)", phase)
                self.assertIn(
                    f"WarpCharacterAndCopyFloor({IDS.beast_entity}, TargetEntityType.Character, "
                    f"{arena.actor}, 203, {arena.actor})", phase)
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 30)", phase)
                self.assertNotIn("SetEventFlag(9337, ON)", phase)
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 10)", after[IDS.human_special_event])
                self.assertIn(f"CharacterHasEventMessage({IDS.beast_entity}, 20)", after[IDS.beast_special_event])

    def test_lifecycle_keeps_beast_hidden_until_phase_then_transfers_death_to_unchanged_terminal(self):
        for arena in SUPPORTED_GASCOIGNE_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_gascoigne_donor(
                    arena, self.destinations[arena.key], self.donor))
                cleanup = blocks[IDS.cleanup_event]
                restore = (
                    f"if (EventFlag({IDS.phase_event})) {{\n"
                    f"        ChangeCharacterEnableState({IDS.beast_entity}, Enabled);\n"
                    f"        SetCharacterInvincibility({IDS.beast_entity}, Disabled);\n"
                    f"        SetCharacterGravity({IDS.beast_entity}, Enabled);\n"
                    "        EndEvent();\n    }"
                )
                self.assertIn(restore, cleanup)
                self.assertLess(cleanup.index(restore),
                                cleanup.index(f"ChangeCharacterEnableState({IDS.beast_entity}, Disabled)"))
                self.assertLess(cleanup.index(f"ChangeCharacterEnableState({IDS.beast_entity}, Disabled)"),
                                cleanup.index(f"WaitFor(EventFlag({arena.completion_event}))"))
                self.assertIn(f"ForceCharacterDeath({IDS.beast_entity}, false)", cleanup)
                bridge = blocks[IDS.terminal_bridge_event]
                self.assertIn(f"humanDead = CharacterDead({arena.actor})", bridge)
                self.assertIn(f"beastDead = CharacterDead({IDS.beast_entity})", bridge)
                self.assertLess(bridge.index("WaitFor(humanDead || beastDead)"),
                                bridge.index(f"ForceCharacterDeath({arena.actor}, false)"))
                retired = set(arena.phase_slots) - {CO_OP_RESTORE_EVENTS[arena.key]}
                for event in retired:
                    self.assertIn("EndEvent();", blocks[event])
                self.assertNotIn("ForceAnimationPlayback", blocks[arena.activation_event])

    def test_per_load_readiness_restores_entry_state_before_health_ai(self):
        for arena in SUPPORTED_GASCOIGNE_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_gascoigne_donor(
                    arena, self.destinations[arena.key], self.donor))
                constructor = blocks[0]
                reset = f"SetEventFlag({IDS.readiness_event}, OFF)"
                initialize = f"$InitializeEvent(0, {IDS.readiness_event})"
                self.assertLess(constructor.index(reset), constructor.index(initialize))
                ready = blocks[IDS.readiness_event]
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))", ready)
                health = blocks[arena.health_bar_event]
                gate = f"WaitFor(EventFlag({IDS.readiness_event}))"
                self.assertEqual(2, health.count(gate))
                self.assertLess(health.rindex(gate),
                                health.index(f"SetCharacterAIState({arena.actor}, Enabled)"))
                if arena.key == "amygdala":
                    for instruction in (
                        f"SetCharacterGravity({arena.actor}, Enabled)",
                        f"SetCharacterInvincibility({arena.actor}, Disabled)",
                        f"SetCharacterMaphits({arena.actor}, false)",
                    ):
                        self.assertIn(instruction, ready)
                    activation = blocks[arena.activation_event]
                    self.assertLess(activation.index(f"SetEventFlag({arena.start_flag}, ON)"),
                                    activation.index(
                                        f"SetCharacterInvincibility({arena.actor}, Disabled)"))

    def test_music_camera_and_authored_state_bindings_are_destination_specific(self):
        for arena in SUPPORTED_GASCOIGNE_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_gascoigne_donor(
                    arena, self.destinations[arena.key], self.donor))
                self.assertIn(f"EventFlag({IDS.phase_event})", blocks[arena.music_event])
                self.assertIn("L0:", blocks[arena.music_event])
                self.assertIn("EnableBossMapSound", blocks[arena.music_event])
                camera = blocks[arena.lockcam_event]
                self.assertEqual(4, camera.count(
                    f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"))
                self.assertEqual(tuple(state for state, _ in GASCOIGNE_STATE_BINDINGS[arena.key]),
                                 tuple(sorted({slot.map_name.removesuffix(".msb").rsplit("_", 1)[-1]
                                               for slot in self.slots
                                               if slot.entity_id == arena.actor})))

    def test_native_plans_pin_primary_and_beast_for_every_physical_destination(self):
        for arena in SUPPORTED_GASCOIGNE_ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_gascoigne_donor(arena, self.slots, self.npcs, self.effects,
                                                    "gascoigne-reusable")
                primary = plan["primary_init_source_bindings"]
                additions = plan["boss_actor_additions"]
                self.assertEqual(arena.destination_count, len(primary))
                self.assertEqual(arena.destination_count, len(additions))
                self.assertEqual({GASCOIGNE_HUMAN}, {row["source_entity_id"] for row in primary})
                self.assertEqual({GASCOIGNE_BEAST}, {row["source_entity_id"] for row in additions})
                self.assertEqual({IDS.beast_entity}, {row["destination_entity_id"] for row in additions})
                self.assertEqual(arena.destination_count, len(helper_scaling_parents(plan)))
                self.assertTrue(plan["scaling"]["enabled"])
                for row in primary:
                    self.assertIn(row["source_provenance"]["part_sha256"], HUMAN_PINS.values())
                    self.assertEqual(0, row["destination_talk_id_override"])
                for row in additions:
                    self.assertIn(row["source_provenance"]["part_sha256"], BEAST_PINS.values())
                    self.assertIn(row["source_provenance"]["anchor_sha256"], HUMAN_PINS.values())

    def test_rejects_collision_and_unpinned_source_drift(self):
        arena = SUPPORTED_GASCOIGNE_ARENAS[0]
        with self.assertRaisesRegex(ValueError, "collision-free"):
            patch_gascoigne_donor(arena, self.destinations[arena.key], self.donor,
                                  replace(IDS, phase_event=arena.health_bar_event))
        with self.assertRaisesRegex(ValueError, "Gascoigne donor event 12414807"):
            patch_gascoigne_donor(arena, self.destinations[arena.key],
                                  self.donor.replace("3030, false, true, false", 
                                                     "3031, false, true, false", 1))
        self.assertEqual(SOURCE_ALTERNATES[12411800][0],
                         "c6eb236fba9e48406dd9088747c3d54bc054784718a67305da498934c2c98b9c")

    def test_all_six_compile_from_pinned_decompiled_originals_when_fixture_available(self):
        compiler = ROOT / "work/DarkScript3/DarkScript3.exe"
        events = ROOT / "work/boss-shuffle-validation/events"
        names = {"common.emevd.dcx", *(arena.event_file.removesuffix(".js")
                                        for arena in SUPPORTED_GASCOIGNE_ARENAS)}
        if not compiler.is_file() or any(not (events / name).is_file() for name in names):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual("c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
                         hashlib.sha256(compiler.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); original = root / "original"; source = root / "source"
            original.mkdir()
            for name in names:
                shutil.copyfile(events / name, original / name)
            subprocess.run([str(compiler), "/cmd", "-decompile", "-game", "bb",
                            "-indir", str(original), "-outdir", str(source), "-force", "-silent"],
                           check=True)
            donor = (source / "m24_01_00_00.emevd.dcx.js").read_text(encoding="utf-8-sig")
            for arena in SUPPORTED_GASCOIGNE_ARENAS:
                with self.subTest(arena=arena.key):
                    single = root / arena.key; input_dir = single / "source"; output_dir = single / "out"
                    shutil.copytree(source, input_dir)
                    destination = (input_dir / arena.event_file).read_text(encoding="utf-8-sig")
                    (input_dir / arena.event_file).write_text(
                        patch_gascoigne_donor(arena, destination, donor), encoding="utf-8-sig")
                    subprocess.run([str(compiler), "/cmd", "-compile", "-game", "bb",
                                    "-indir", str(input_dir), "-outdir", str(output_dir),
                                    "-force", "-silent"], check=True)
                    self.assertTrue((output_dir / arena.event_file.removesuffix(".js")).is_file())


if __name__ == "__main__":
    unittest.main()
