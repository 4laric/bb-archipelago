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
from tools.bb_enemizer import one_reborn_ebrietas_contract as one
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.one_reborn_donor import (
    ARCH,
    BODY,
    CASTERS,
    CONTROLLER,
    CORE,
    DEFAULT_ALLOCATION,
    EVENT_FILE,
    PROXY,
    SOURCE_INITIALIZATION,
    OneRebornDonorAllocation,
    native_plan_one_reborn_donor,
    one_reborn_donor_contract,
    patch_one_reborn_donor,
    portable_one_reborn_arenas,
)
from tools.bb_enemizer.scaling import load_params

BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_ALLOCATION


class OneRebornDonorTests(unittest.TestCase):
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
            patch_one_reborn_donor(
                arena, self.destinations[arena.key], self.donor, IDS
            )
        )

    def test_allocation_and_full_actor_only_source_closure(self):
        original = b"\n".join(
            blob
            for prefix in ("event/", "mined/")
            for blob in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        original_literals = {
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", original)
        }
        self.assertEqual(
            {
                *range(12996700, 12996731),
                *range(12996740, 12996745),
                *range(984100, 984109),
            },
            set(IDS.values()),
        )
        self.assertFalse(set(IDS.values()) & original_literals)
        self.assertEqual(ARENAS, portable_one_reborn_arenas())
        for arena in ARENAS:
            contract = one_reborn_donor_contract(arena, IDS)
            self.assertEqual(dict(one.DONOR_HASHES), contract["source_hash_pins"])
            self.assertEqual(
                [BODY, CONTROLLER, PROXY, *CASTERS],
                contract["source_roster"]["helpers"],
            )
            self.assertEqual(0, len(contract["source_roster"]["regions"]))
            self.assertEqual(0, len(contract["source_roster"]["generators"]))
            policy = contract["character_asset_policy"]
            self.assertIn("typed 96/100/118 direct roots", policy["delivery"])
            self.assertEqual("not-validated", policy["recursive_fxr_dependencies"])
            self.assertEqual("not-runtime-validated", policy["destination_bank_precedence"])

    def test_constructor_preserves_every_authored_source_initializer_slot(self):
        source_zero = event_blocks(self.donor)[0]
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                constructor = self.patched(arena)[0]
                expected = {
                    IDS.camera: 1,
                    IDS.tether: 1,
                    IDS.limb_guard: 1,
                    **{event: 1 for event in range(IDS.limb_first, IDS.limb_first + 7)},
                    **{
                        event: 1
                        for event in range(
                            IDS.controller_first, IDS.controller_first + 8
                        )
                    },
                    IDS.caster_react: 1,
                    IDS.caster_react + 1: 1,
                    **{
                        event: 1
                        for event in range(IDS.caster_count, IDS.caster_count + 6)
                    },
                    IDS.phase_one: 1,
                    IDS.phase_two: 1,
                    IDS.terminal_bridge: 1,
                    IDS.lifecycle_cleanup: 1,
                }
                for event_id, count in expected.items():
                    self.assertEqual(
                        count,
                        len(
                            re.findall(
                                rf"\$InitializeEvent\([^,]+,\s*{event_id}(?:,|\))",
                                constructor,
                            )
                        ),
                    )
                self.assertIn(
                    "$InitializeEvent(0, 12996704, 2800, 2800, NPCPartType.Part1, 100, 480, 490, 7000);",
                    constructor,
                )
                self.assertIn(
                    "$InitializeEvent(9, 12996726, 984108);", constructor
                )
        self.assertEqual(7, source_zero.count(", 12804820,"))

    def test_entry_client_health_and_destination_telemetry_are_ordered(self):
        body, controller, proxy, *casters = IDS.helper_ids()
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                activation = after[arena.activation_event]
                self.assertLess(
                    activation.index(
                        f"ChangeCharacterEnableState({body}, Disabled)"
                    ),
                    activation.index("WaitFor("),
                )
                self.assertGreater(
                    activation.index(f"ChangeCharacterEnableState({body}, Enabled)"),
                    activation.index("WaitFor("),
                )
                self.assertLess(
                    activation.index(f"ChangeCharacterEnableState({body}, Enabled)"),
                    activation.index(f"SetEventFlag({arena.start_flag}, ON)"),
                )
                client = after[one_reborn_donor_contract(arena)["adapted_destination_events"][1]]
                self.assertIn(f"ChangeCharacterEnableState({body}, Enabled)", client)
                health = after[arena.health_bar_event]
                self.assertIn(
                    f"SetCharacterImmortality({arena.actor}, Enabled);", health
                )
                self.assertNotIn(
                    f"SetCharacterImmortality({arena.actor}, Disabled);",
                    activation,
                )
                self.assertIn(
                    f"CreateReferredDamagePair({arena.actor}, {proxy});", health
                )
                self.assertIn(f"CreateReferredDamagePair({body}, {proxy});", health)
                self.assertIn(
                    f"DisplayBossHealthBar(Enabled, {proxy}, 0, 507000);", health
                )
                for entity in (arena.actor, body, controller, proxy, *casters):
                    self.assertIn(f"SetCharacterAIState({entity}, Enabled);", health)
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

    def test_limb_controller_caster_phase_music_camera_and_terminal_close(self):
        body, controller, proxy, *casters = IDS.helper_ids()
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertIn(
                    f"CreateNPCPart({arena.actor}, npcPartId,", after[IDS.limb_first]
                )
                self.assertIn(
                    f"IssueShortWarpRequest({controller}, TargetEntityType.Character, 10000, 246)",
                    after[IDS.controller_first],
                )
                self.assertIn(
                    f"SetCharacterEventTarget(chrEntityId, {body});",
                    after[IDS.caster_react],
                )
                self.assertIn(
                    f"IncrementEventValue({IDS.caster_count_flag}, 4, 10);",
                    after[IDS.caster_count],
                )
                self.assertIn(
                    f"HPRatio({proxy}) < 0.5", after[IDS.phase_two]
                )
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 300)",
                    after[arena.music_event],
                )
                self.assertEqual(
                    2,
                    after[arena.lockcam_event].count(
                        f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
                    ),
                )
                bridge = after[IDS.terminal_bridge]
                self.assertLess(
                    bridge.index(f"WaitFor(HPRatio({proxy}) <= 0)"),
                    bridge.index(f"ForceCharacterDeath({arena.actor}, false)"),
                )
                self.assertEqual(
                    before[arena.completion_event], after[arena.completion_event]
                )
                cleanup = after[IDS.lifecycle_cleanup]
                self.assertIn(
                    f"WaitFor(EventFlag({arena.completion_event}))", cleanup
                )
                for entity in IDS.helper_ids():
                    self.assertIn(f"ForceCharacterDeath({entity}, false)", cleanup)

    def test_native_plan_pins_all_ten_actors_in_every_physical_state(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_one_reborn_donor(
                    arena, self.slots, self.npcs, self.effects, "one-reborn", IDS
                )
                count = arena.destination_count
                self.assertEqual(count, len(plan["primary_init_source_bindings"]))
                self.assertEqual(9 * count, len(plan["boss_actor_additions"]))
                self.assertEqual(
                    9 * count, len(plan["boss_actor_scaling_requirements"])
                )
                self.assertNotIn("boss_region_additions", plan)
                self.assertNotIn("boss_generator_additions", plan)
                for row in plan["primary_init_source_bindings"]:
                    state = row["source_map"]
                    self.assertEqual(asdict(ARCH[CORE]), row["source_archetype"])
                    self.assertEqual(SOURCE_INITIALIZATION, row["source_initialization"])
                    self.assertEqual(
                        one.PINS[state][CORE],
                        row["source_provenance"]["part_sha256"],
                    )
                for row in plan["boss_actor_additions"]:
                    state, entity = row["source_map"], row["source_entity_id"]
                    self.assertEqual(SOURCE_INITIALIZATION, row["source_initialization"])
                    self.assertEqual(
                        one.PINS[state][entity],
                        row["source_provenance"]["part_sha256"],
                    )
                    self.assertEqual(
                        one.PINS[state][CORE],
                        row["source_provenance"]["anchor_sha256"],
                    )
                self.assertNotIn("boss_emevd_ffx_requirements", plan)
                self.assertEqual(
                    9 * count, len(plan["boss_character_ffx_bank_requirements"])
                )
                self.assertEqual(
                    9 * len({row["source_map"] for row in plan["primary_init_source_bindings"]}),
                    len(plan["boss_character_ffx_requirements"]),
                )
                merge, = plan["boss_ffx_merges"]
                self.assertEqual("frpg_sfxbnd_m28.ffxbnd.dcx", merge["source_file"])
                self.assertEqual(20, len(merge["required_effect_ids"]))

    def test_rejects_source_allocation_and_native_roster_drift(self):
        arena = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "exact reviewed allocation"):
            patch_one_reborn_donor(
                arena,
                self.destinations[arena.key],
                self.donor,
                replace(IDS, helper_first=984101),
            )
        with self.assertRaisesRegex(ValueError, "One Reborn donor"):
            patch_one_reborn_donor(
                arena,
                self.destinations[arena.key],
                self.donor.replace(
                    "CreateReferredDamagePair(2800800, 2800803)",
                    "CreateReferredDamagePair(2800800, 2800802)",
                ),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != CASTERS[-1]]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_one_reborn_donor(
                arena, missing, self.npcs, self.effects, "missing-caster", IDS
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
                ],
                check=True,
                capture_output=True,
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
                        patch_one_reborn_donor(
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
