import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_actor_scaling import allocate_actor_scaling
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.ludwig_donor import (
    ARENAS, CO_OP_RESTORE_EVENTS, DEFAULT_ALLOCATION, DESTINATION_FFX,
    EVENT_FILE, EVENTS, LUDWIG_EFFECT, PART_PINS, PHASE_ONE, PHASE_TWO,
    P1, P2, SOURCE_FFX_FILE, SOURCE_FFX_SHA256, SOURCE_HASHES,
    LUDWIG_EFFECT_OCCURRENCE_COUNT,
    SOURCE_INITIALIZATION, SOURCE_PARTS, LudwigDonorAllocation,
    ludwig_donor_contract, native_plan_ludwig_donor, patch_ludwig_donor,
    portable_ludwig_arenas,
)
from tools.bb_enemizer.scaling import load_params

BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_ALLOCATION


class LudwigDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ludwig = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self, arena):
        return event_blocks(patch_ludwig_donor(
            arena, self.destinations[arena.key], self.ludwig, IDS
        ))

    def test_allocation_is_disjoint_from_original_and_reserved_project_ranges(self):
        joined = b"\n".join(
            body for prefix in ("event/", "mined/")
            for body in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        self.assertEqual(
            (*range(12995800, 12995813), 983300), IDS.values()
        )
        for value in IDS.values():
            self.assertNotRegex(joined, rf"(?<![\w]){value}(?![\w])")
        self.assertTrue(set(range(12995800, 12995900)).isdisjoint(
            set(range(12995600, 12995800))))
        self.assertTrue(set(range(983300, 983400)).isdisjoint(
            set(range(983100, 983300))))
        self.assertEqual(ARENAS, portable_ludwig_arenas())

    def test_full_normal_source_graph_phase_transition_and_saved_state_all_six(self):
        added = {*IDS.event_ids().values(), IDS.readiness_event,
                 IDS.terminal_bridge_event}
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertEqual(added, set(after) - set(before))
                health = after[arena.health_bar_event]
                self.assertIn(
                    f"CreateReferredDamagePair({arena.actor}, {IDS.phase_entity})",
                    health,
                )
                self.assertIn(
                    f"ChangeCharacterEnableState({IDS.phase_entity}, Disabled)", health
                )
                self.assertIn(f"if (EventFlag({IDS.phase_25}))", health)
                self.assertIn(
                    f"ChangeCharacterEnableState({IDS.phase_entity}, Enabled)", health
                )
                transition = after[IDS.phase_25]
                self.assertIn(
                    f"WarpCharacterAndCopyFloor({IDS.phase_entity}, "
                    f"TargetEntityType.Character, {arena.actor}, -1, {arena.actor})",
                    transition,
                )
                self.assertIn(
                    f"ChangeCharacterEnableState({IDS.phase_entity}, Enabled)", transition
                )
                self.assertNotIn("PlayCutscene", transition)
                self.assertNotIn("TargetEntityType.Area", transition)
                self.assertNotIn("13400999", "\n".join(
                    after[IDS.event_ids()[event]] for event in EVENTS
                ))
                self.assertEqual(3, after[0].count(
                    f", {IDS.limb_event},"))

    def test_per_load_readiness_gates_first_and_saved_health_paths(self):
        restorations = {
            "cleric-beast": "SetCharacterGravity",
            "blood-starved-beast": None,
            "darkbeast-paarl": "SetCharacterInvincibility",
            "vicar-amelia": "ChangeCharacterEnableState",
            "amygdala": "SetCharacterInvincibility",
            "ebrietas": "SetCharacterImmortality",
        }
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                constructor = after[0]
                reset = f"SetEventFlag({IDS.readiness_event}, OFF)"
                initialize = f"$InitializeEvent(0, {IDS.readiness_event})"
                self.assertLess(constructor.index(reset), constructor.index(initialize))
                ready = after[IDS.readiness_event]
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))", ready)
                if restorations[arena.key]:
                    self.assertIn(restorations[arena.key], ready)
                health = after[arena.health_bar_event]
                gate = f"WaitFor(EventFlag({IDS.readiness_event}))"
                self.assertEqual(2, health.count(gate))
                self.assertLess(health.rindex(gate),
                                health.index("GotoIf(L1, NumberOfCoopClients()"))
                self.assertLess(health.rindex(gate),
                                health.index(f"SetCharacterAIState({arena.actor}, Enabled)"))

    def test_terminal_coop_entry_and_progression_remain_exact(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                coop = CO_OP_RESTORE_EVENTS[arena.key]
                self.assertEqual(before[coop], after[coop])
                bridge = after[IDS.terminal_bridge_event]
                self.assertIn(f"CharacterDead({arena.actor})", bridge)
                self.assertIn(f"CharacterDead({IDS.phase_entity})", bridge)
                force = f"ForceCharacterDeath({arena.actor}, false)"
                completion = f"WaitFor(EventFlag({arena.completion_event}))"
                self.assertLess(bridge.index(force), bridge.index(completion))
                self.assertIn(
                    f"EventFlag({arena.completion_event}) || ThisEvent()", bridge
                )
                self.assertEqual(
                    [arena.completion_event, coop],
                    ludwig_donor_contract(arena, IDS)["preserved_destination_events"],
                )

    def test_destination_entry_music_camera_notification_and_telemetry(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                activation = after[arena.activation_event]
                self.assertNotRegex(
                    activation,
                    rf"ForceAnimationPlayback\({arena.actor}, (?:700[0-9]|3028)",
                )
                if arena.key in ("darkbeast-paarl", "amygdala"):
                    self.assertLess(
                        activation.index(
                            f"SetCharacterInvincibility({arena.actor}, Enabled)"),
                        activation.index("WaitFor("),
                    )
                if arena.key == "ebrietas":
                    self.assertLess(
                        activation.index(
                            f"SetCharacterImmortality({arena.actor}, Enabled)"),
                        activation.index("HasDamageType("),
                    )
                self.assertIn(f"EventFlag({IDS.phase_24})", after[arena.music_event])
                camera = after[arena.lockcam_event]
                self.assertIn(
                    f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
                    camera,
                )
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    expected = [line.strip() for line in before[arena.health_bar_event].splitlines()
                                if line.strip().startswith(instruction + "(")]
                    actual = [line.strip() for line in after[arena.health_bar_event].splitlines()
                              if line.strip().startswith(instruction + "(")]
                    self.assertEqual(expected, actual)
                if arena.key == "vicar-amelia":
                    self.assertIn("if (!EventFlag(12404223))",
                                  after[arena.health_bar_event])
                else:
                    self.assertIn(f"SetEventFlag({IDS.notification_flag}, ON)",
                                  after[arena.health_bar_event])

    def test_native_plan_pins_all_states_scales_helper_and_declares_ffx(self):
        source_effect = event_blocks(self.ludwig)[13404840]
        self.assertEqual(
            LUDWIG_EFFECT_OCCURRENCE_COUNT,
            source_effect.count(f"SpawnOneshotSFX(TargetEntityType.Character, 10000, 236, {LUDWIG_EFFECT})"),
        )
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_ludwig_donor(
                    arena, self.slots, self.npcs, self.effects, "ludwig-donor", IDS
                )
                primary = plan["primary_init_source_bindings"]
                helpers = plan["boss_actor_additions"]
                self.assertEqual(arena.destination_count, len(primary))
                self.assertEqual(arena.destination_count, len(helpers))
                for row, entity, archetype in (
                    *((row, PHASE_ONE, P1) for row in primary),
                    *((row, PHASE_TWO, P2) for row in helpers),
                ):
                    self.assertEqual(SOURCE_PARTS[entity], row["source_part"])
                    self.assertEqual(asdict(archetype), row["source_archetype"])
                    self.assertEqual(PART_PINS[entity],
                                     row["source_provenance"]["part_sha256"])
                    self.assertEqual(SOURCE_INITIALIZATION,
                                     row["source_initialization"])
                parents = {
                    (row["destination_map"], row["destination_part"]):
                    plan["boss_contract"]["helper_scaling_parent"][
                        f'{row["destination_map"]}:{row["destination_part"]}'
                    ] for row in helpers
                }
                self.assertEqual(len(helpers), len(allocate_actor_scaling(
                    plan, self.npcs, parents
                )))
                requirement = plan["boss_emevd_ffx_requirements"][0]
                self.assertEqual((13404840, IDS.player_warp_event, LUDWIG_EFFECT,
                                  LUDWIG_EFFECT_OCCURRENCE_COUNT),
                                 (requirement["source_event_id"],
                                  requirement["destination_event_id"],
                                  requirement["effect_id"],
                                  requirement["occurrence_count"]))
                merge = plan["boss_ffx_merges"][0]
                self.assertEqual(SOURCE_FFX_FILE, merge["source_file"])
                self.assertEqual(SOURCE_FFX_SHA256, merge["source_sha256"])
                self.assertEqual(DESTINATION_FFX[arena.key],
                                 (merge["destination_file"],
                                  merge["destination_sha256"]))

    def test_rejects_allocation_source_and_native_pin_drift(self):
        arena = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_ludwig_donor(
                arena, self.destinations[arena.key], self.ludwig,
                replace(IDS, phase_21=IDS.phase_20),
            )
        with self.assertRaisesRegex(ValueError, "Ludwig donor"):
            patch_ludwig_donor(
                arena, self.destinations[arena.key],
                self.ludwig.replace("SetSpEffect(3400801, 5333, false)",
                                    "SetSpEffect(3400801, 5334, false)"), IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != PHASE_TWO]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_ludwig_donor(
                arena, missing, self.npcs, self.effects, "missing-phase", IDS
            )

    def test_all_six_actual_decompiled_outputs_compile_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        names = {"common.emevd.dcx", "m34_00_00_00.emevd.dcx",
                 *(arena.event_file.removesuffix(".js") for arena in ARENAS)}
        if not compiler.is_file() or any(not (events / name).is_file() for name in names):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            original, source = work / "original", work / "source"
            original.mkdir()
            for name in names:
                shutil.copyfile(events / name, original / name)
            subprocess.run([
                str(compiler), "/cmd", "-decompile", "-game", "bb",
                "-indir", str(original), "-outdir", str(source), "-force", "-silent",
            ], check=True)
            actual_donor = (source / "m34_00_00_00.emevd.dcx.js").read_text(
                encoding="utf-8-sig"
            )
            m23_original = (source / "m23_00_00_00.emevd.dcx.js").read_text(
                encoding="utf-8-sig"
            )
            for selected, suffix in (
                (tuple(a for a in ARENAS if a.key != "darkbeast-paarl"), "main"),
                ((next(a for a in ARENAS if a.key == "darkbeast-paarl"),), "paarl"),
            ):
                (source / "m23_00_00_00.emevd.dcx.js").write_text(
                    m23_original, encoding="utf-8-sig"
                )
                for arena in selected:
                    path = source / arena.event_file
                    current = path.read_text(encoding="utf-8-sig")
                    path.write_text(
                        patch_ludwig_donor(arena, current, actual_donor, IDS),
                        encoding="utf-8-sig",
                    )
                output = work / ("output-" + suffix)
                subprocess.run([
                    str(compiler), "/cmd", "-compile", "-game", "bb",
                    "-indir", str(source), "-outdir", str(output), "-force", "-silent",
                ], check=True)
                self.assertTrue((output / "m23_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
