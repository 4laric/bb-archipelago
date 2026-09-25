import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer import celestial_paarl_contract as ce
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.celestial_donor import (
    CHARACTER_EFFECT_EVIDENCE,
    CHARACTER_PROOF_FILE,
    CHARACTER_PROOF_SHA256,
    CO_OP_RESTORE,
    DEFAULT_ALLOCATION,
    DESTINATION_SUBAREA_FFX,
    EVENT_FILE,
    PRIMARY,
    PRIMARY_ARCHETYPE,
    REQUIRED_ROOT_SHA256,
    ROOT_WITNESS_625700,
    SOURCE_FFX_FILE,
    SOURCE_FFX_SHA256,
    SOURCE_INITIALIZATION,
    CelestialDonorAllocation,
    celestial_donor_contract,
    native_plan_celestial_donor,
    patch_celestial_donor,
    portable_celestial_arenas,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_ALLOCATION


class CelestialDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode(
                "utf-8-sig"
            )
            for arena in ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self, arena):
        return event_blocks(
            patch_celestial_donor(
                arena, self.destinations[arena.key], self.donor, IDS
            )
        )

    def test_allocation_source_pins_and_asset_boundary_cover_all_six(self):
        joined = b"\n".join(
            body
            for prefix in ("event/", "mined/")
            for body in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        original_literals = {
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", joined)
        }
        self.assertEqual(
            (*range(12996600, 12996612), *range(984000, 984035)),
            IDS.values(),
        )
        for value in IDS.values():
            self.assertNotIn(value, original_literals)
        self.assertEqual(ARENAS, portable_celestial_arenas())
        for arena in ARENAS:
            contract = celestial_donor_contract(arena, IDS)
            self.assertEqual(dict(ce.SOURCE_HASHES), contract["source_hash_pins"])
            self.assertEqual(11, len(contract["source_roster"]["helpers"]) + 1)
            self.assertEqual(11, len(contract["source_roster"]["regions"]))
            self.assertEqual(7, len(contract["source_roster"]["generators"]))
            self.assertEqual(CHARACTER_EFFECT_EVIDENCE, contract["character_effect_evidence"])
            asset = contract["asset_delivery"]
            self.assertEqual(SOURCE_FFX_FILE, asset["source_file"])
            self.assertEqual(SOURCE_FFX_SHA256, asset["source_sha256"])
            self.assertEqual(REQUIRED_ROOT_SHA256, asset["required_root_sha256"])
            self.assertEqual(ROOT_WITNESS_625700, asset["selected_root_witness"])
            self.assertEqual(CHARACTER_PROOF_FILE.name, asset["source_proof_file"])
            self.assertEqual(CHARACTER_PROOF_SHA256, asset["source_proof_sha256"])
            self.assertEqual(
                DESTINATION_SUBAREA_FFX[arena.key],
                (asset["destination_file"], asset["destination_sha256"]),
            )
            self.assertFalse(asset["emevd_witness_fabricated"])
            self.assertNotIn("boss_emevd_ffx_requirements", contract)

    def test_constructor_has_full_initializer_closure_and_giant_always_update(self):
        expected_counts = {
            IDS.generator_cleanup: 8,
            IDS.giant_command: 1,
            IDS.giant_ai: 1,
            IDS.giant_home: 2,
            IDS.wave_home: 2,
            IDS.giant_phase: 1,
            IDS.support_warp: 1,
            IDS.support_phase: 2,
            IDS.giant_choreography: 1,
            IDS.terminal_bridge: 1,
            IDS.lifecycle_cleanup: 1,
        }
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                constructor = self.patched(arena)[0]
                for event_id, count in expected_counts.items():
                    self.assertEqual(
                        count,
                        len(
                            re.findall(
                                rf"\$InitializeEvent\([^,]+,\s*{event_id}(?:,|\))",
                                constructor,
                            )
                        ),
                    )
                self.assertEqual(
                    1,
                    constructor.count(
                        f"SetNetworkUpdateRate({IDS.helper_ids()[0]}, true, CharacterUpdateFrequency.AlwaysUpdate)"
                    ),
                )

    def test_host_and_client_staged_wake_health_and_foreign_actor_correction(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                activation = after[arena.activation_event]
                restore = after[CO_OP_RESTORE[arena.key]]
                health = after[arena.health_bar_event]
                original_restore = event_blocks(self.destinations[arena.key])[
                    CO_OP_RESTORE[arena.key]
                ]
                self.assertTrue(restore.startswith(original_restore.rsplit("});", 1)[0]))
                for wave in IDS.helper_ids()[1:8]:
                    self.assertIn(f"ChangeCharacterEnableState({wave}, Disabled)", activation)
                    self.assertIn(f"ChangeCharacterEnableState({wave}, Enabled)", activation)
                    self.assertIn(f"ChangeCharacterEnableState({wave}, Enabled)", restore)
                explicit = f"SetEventFlag({arena.activation_event}, ON)"
                self.assertLess(
                    activation.index(explicit),
                    activation.index("WaitFixedTimeSeconds(2)"),
                )
                self.assertIn(f"SetEventFlag({arena.start_flag}, ON)", restore)
                self.assertIn(f"SetEventFlag({arena.activation_event}, ON)", restore)
                self.assertIn(
                    f"SetNetworkUpdateAuthority({arena.actor}, AuthorityLevel.Forced)",
                    health,
                )
                self.assertIn(
                    f"SetNetworkUpdateAuthority({IDS.helper_ids()[0]}, AuthorityLevel.Forced)",
                    health,
                )
                for effect in (7500, 7501):
                    self.assertEqual(
                        1, health.count(f"SetSpEffect({arena.actor}, {effect}, true)")
                    )
                for foreign in (*range(2800800, 2800804), 2800810, 2800811):
                    self.assertNotIn(str(foreign), health)

    def test_giant_phase_generator_support_bridge_and_completed_cleanup_are_closed(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                phase = after[IDS.giant_phase]
                giant = IDS.helper_ids()[0]
                self.assertIn(f"CreateReferredDamagePair({arena.actor}, {giant})", phase)
                self.assertIn(f"HPRatio({arena.actor}) < 0.6", phase)
                self.assertIn(
                    f"WarpCharacterAndCopyFloor({giant}, TargetEntityType.Character, {arena.actor}, 203, {arena.actor})",
                    phase,
                )
                self.assertIn(f"DisplayBossHealthBar(Enabled, {giant}, 0, 257000)", phase)
                generator = after[IDS.generator_cleanup]
                self.assertIn(f"CharacterDead({giant})", generator)
                bridge = after[IDS.terminal_bridge]
                self.assertLess(
                    bridge.index(f"CharacterDead({giant})"),
                    bridge.index(f"ForceCharacterDeath({arena.actor}, false)"),
                )
                self.assertLess(
                    bridge.index(f"ForceCharacterDeath({arena.actor}, false)"),
                    bridge.index(f"WaitFor(EventFlag({arena.completion_event}))"),
                )
                cleanup = after[IDS.lifecycle_cleanup]
                self.assertLess(
                    cleanup.index(f"WaitFor(EventFlag({arena.completion_event}))"),
                    cleanup.index(f"DeactivateGenerator({IDS.generator_ids()[0]}",),
                )
                for entity in IDS.generator_ids():
                    self.assertIn(f"DeactivateGenerator({entity}, Disabled)", cleanup)
                for entity in IDS.helper_ids():
                    self.assertIn(f"ForceCharacterDeath({entity}, false)", cleanup)

    def test_destination_progression_notification_telemetry_music_and_camera_are_owned(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                changed = {
                    0,
                    arena.activation_event,
                    CO_OP_RESTORE[arena.key],
                    arena.health_bar_event,
                    arena.music_event,
                    arena.lockcam_event,
                    *celestial_donor_contract(arena, IDS)[
                        "retired_destination_controllers"
                    ],
                }
                for event_id in set(before) - changed:
                    self.assertEqual(before[event_id], after[event_id])
                health = after[arena.health_bar_event]
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    expected = [
                        line.strip()
                        for line in before[arena.health_bar_event].splitlines()
                        if line.strip().startswith(instruction + "(")
                    ]
                    actual = [
                        line.strip()
                        for line in health.splitlines()
                        if line.strip().startswith(instruction + "(")
                    ]
                    self.assertEqual(expected, actual)
                self.assertIn("DisplayBossHealthBar(Enabled", health)
                self.assertIn(", 0, 257000)", health)
                self.assertIn(f"EventFlag({IDS.giant_phase})", after[arena.music_event])
                camera = after[arena.lockcam_event]
                self.assertIn(
                    f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
                    camera,
                )
                self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", camera)
                contract = celestial_donor_contract(arena, IDS)
                for retired in contract["retired_destination_controllers"]:
                    self.assertIn("EndEvent();", after[retired])

    def test_native_plan_pins_all_actor_region_generator_states_and_scaling(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_celestial_donor(
                    arena, self.slots, self.npcs, self.effects, "celestial-donor", IDS
                )
                count = arena.destination_count
                self.assertEqual(count, len(plan["primary_init_source_bindings"]))
                self.assertEqual(10 * count, len(plan["boss_actor_additions"]))
                self.assertEqual(11 * count, len(plan["boss_region_additions"]))
                self.assertEqual(7 * count, len(plan["boss_generator_additions"]))
                self.assertEqual(10 * count, len(plan["boss_actor_scaling_requirements"]))
                for row in plan["primary_init_source_bindings"]:
                    self.assertEqual(PRIMARY, row["source_entity_id"])
                    self.assertEqual(asdict(PRIMARY_ARCHETYPE), row["source_archetype"])
                    self.assertEqual(SOURCE_INITIALIZATION, row["source_initialization"])
                    state = row["source_map"]
                    self.assertEqual(
                        ce.ACTOR_PINS[state][0], row["source_provenance"]["part_sha256"]
                    )
                for row in plan["boss_actor_additions"]:
                    self.assertEqual(SOURCE_INITIALIZATION, row["source_initialization"])
                    self.assertEqual(
                        ce.ACTOR_PINS[row["source_map"]][0],
                        row["source_provenance"]["anchor_sha256"],
                    )
                self.assertEqual(
                    set(IDS.region_ids()),
                    {row["destination_entity_id"] for row in plan["boss_region_additions"]},
                )
                self.assertEqual(
                    set(IDS.generator_ids()),
                    {row["destination_entity_id"] for row in plan["boss_generator_additions"]},
                )
                self.assertEqual(
                    set(IDS.generator_event_ids()),
                    {row["destination_event_id"] for row in plan["boss_generator_additions"]},
                )
                self.assertNotIn("boss_emevd_ffx_requirements", plan)
                requirements = plan["boss_character_ffx_requirements"]
                source_identities = {
                    (row["source_map"], row["source_part"], row["source_entity_id"])
                    for row in plan["boss_actor_additions"]
                    if row["source_archetype"]["model_name"] == "c2570"
                }
                self.assertEqual(len(source_identities), len(requirements))
                self.assertEqual(
                    source_identities,
                    {
                        (row["source_map"], row["source_part"], row["source_entity_id"])
                        for row in requirements
                    },
                )
                for row in requirements:
                    self.assertEqual("c2570", row["source_character"])
                    self.assertEqual([96, 100, 118], row["decoded_event_types"])
                    self.assertEqual(126, row["source_animation_count"])
                    self.assertEqual(128, len(row["typed_event_witnesses"]))
                    self.assertIn(ROOT_WITNESS_625700, row["typed_event_witnesses"])
                    self.assertIn(625700, row["direct_effect_ids"])

                destination_file, destination_hash = DESTINATION_SUBAREA_FFX[
                    arena.key
                ]
                if destination_file == SOURCE_FFX_FILE:
                    self.assertNotIn("boss_character_ffx_bank_requirements", plan)
                    self.assertNotIn("boss_ffx_merges", plan)
                    continue
                bank_requirements = plan["boss_character_ffx_bank_requirements"]
                giants = [
                    row
                    for row in plan["boss_actor_additions"]
                    if row["source_archetype"]["model_name"] == "c2570"
                ]
                self.assertEqual(count, len(bank_requirements))
                for giant, row in zip(giants, bank_requirements, strict=True):
                    for key in (
                        "source_map",
                        "source_part",
                        "source_entity_id",
                        "destination_map",
                        "destination_part",
                        "destination_entity_id",
                    ):
                        self.assertEqual(giant[key], row[key])
                    self.assertEqual("c2570", row["source_character"])
                    self.assertEqual(SOURCE_FFX_FILE, row["source_ffx_file"])
                    self.assertEqual(destination_file, row["destination_ffx_file"])
                    self.assertEqual(
                        [{"source_tae_entry_id": 3000000, "witness": ROOT_WITNESS_625700}],
                        row["roots"],
                    )
                self.assertEqual(
                    [
                        {
                            "source_file": SOURCE_FFX_FILE,
                            "source_sha256": SOURCE_FFX_SHA256,
                            "destination_file": destination_file,
                            "destination_sha256": destination_hash,
                            "required_effect_ids": [625700],
                            "policy": "preserve_destination_union_source_v1",
                        }
                    ],
                    plan["boss_ffx_merges"],
                )

    def test_rejects_allocation_source_and_native_roster_drift(self):
        arena = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "exact reviewed allocation"):
            patch_celestial_donor(
                arena,
                self.destinations[arena.key],
                self.donor,
                replace(IDS, helper_first=IDS.helper_first + 1),
            )
        with self.assertRaisesRegex(ValueError, "Celestial donor"):
            patch_celestial_donor(
                arena,
                self.destinations[arena.key],
                self.donor.replace(
                    "CreateReferredDamagePair(2420810, 2420811)",
                    "CreateReferredDamagePair(2420810, 2420812)",
                ),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != 2420751]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_celestial_donor(
                arena, missing, self.npcs, self.effects, "missing-support", IDS
            )

    def test_all_six_actual_decompiled_outputs_compile_with_pinned_darkscript(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        names = {
            "common.emevd.dcx",
            EVENT_FILE.removesuffix(".js"),
            *(arena.event_file.removesuffix(".js") for arena in ARENAS),
        }
        if not compiler.is_file() or any(
            not (events / name).is_file() for name in names
        ):
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
            donor = (source / EVENT_FILE).read_text(encoding="utf-8-sig")
            m23_original = (source / "m23_00_00_00.emevd.dcx.js").read_text(
                encoding="utf-8-sig"
            )
            for selected, suffix in (
                (
                    tuple(arena for arena in ARENAS if arena.key != "darkbeast-paarl"),
                    "main",
                ),
                (
                    tuple(arena for arena in ARENAS if arena.key == "darkbeast-paarl"),
                    "paarl",
                ),
            ):
                (source / "m23_00_00_00.emevd.dcx.js").write_text(
                    m23_original, encoding="utf-8-sig"
                )
                for arena in selected:
                    path = source / arena.event_file
                    path.write_text(
                        patch_celestial_donor(
                            arena,
                            path.read_text(encoding="utf-8-sig"),
                            donor,
                            IDS,
                        ),
                        encoding="utf-8-sig",
                    )
                output = work / ("output-" + suffix)
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
                self.assertTrue((output / "m23_00_00_00.emevd.dcx").is_file())


if __name__ == "__main__":
    unittest.main()
