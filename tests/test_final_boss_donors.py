import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.final_boss_contracts import GEHRMAN_PACKAGE, MOON_PACKAGE
from tools.bb_enemizer.final_boss_donors import (
    CO_OP_RESTORE_EVENTS,
    DEFAULT_FINAL_BOSS_ALLOCATION,
    GEHRMAN_DONOR,
    GEHRMAN_INITIALIZATION,
    GEHRMAN_OWNER,
    GEHRMAN_OWNER_ARCHETYPE,
    GEHRMAN_OWNER_PIN,
    GEHRMAN_PRIMARY_PIN,
    MOON_DONOR,
    MOON_PRIMARY_PIN,
    SOURCE_INITIALIZATION,
    SUPPORTED_FINAL_BOSS_ARENAS,
    final_boss_actor_requirements,
    final_boss_donor_contract,
    native_plan_final_boss_donor,
    patch_final_boss_donor,
    portable_final_boss_donors,
    validate_final_boss_allocation,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_FINAL_BOSS_ALLOCATION


class FinalBossDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_blob(BUNDLE, "event/" + GEHRMAN_DONOR.event_file).decode(
            "utf-8-sig"
        )
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode(
                "utf-8-sig"
            )
            for arena in SUPPORTED_FINAL_BOSS_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def patched(self, arena, donor):
        return event_blocks(
            patch_final_boss_donor(
                arena, donor, self.destinations[arena.key], self.source, IDS
            )
        )

    def test_allocation_and_contract_scope_are_explicit(self):
        originals = [
            body.decode("utf-8-sig")
            for prefix in ("event/", "mined/")
            for body in read_prefix(BUNDLE, prefix).values()
        ]
        validate_final_boss_allocation(IDS, originals)
        with self.assertRaisesRegex(ValueError, "exact reviewed narrow allocation"):
            validate_final_boss_allocation(replace(IDS, gehrman_phase_event=12996020))

        self.assertEqual(
            ("gehrman", "moon-presence"),
            tuple(donor.key for donor in portable_final_boss_donors()),
        )
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            for donor in portable_final_boss_donors():
                contract = final_boss_donor_contract(arena, donor, IDS)
                self.assertEqual(arena.key, contract["arena"])
                self.assertEqual(donor.key, contract["donor"])
                self.assertEqual(
                    [arena.completion_event, CO_OP_RESTORE_EVENTS[arena.key]],
                    contract["preserved_destination_events"],
                )
                self.assertEqual("incomplete", contract["asset_delivery"]["status"])
                self.assertFalse(contract["asset_delivery"]["production_recipe_ready"])
                self.assertEqual("unobserved", contract["runtime_status"])

    def test_destination_terminal_client_restore_and_unrelated_events_are_preserved(
        self,
    ):
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            before = event_blocks(self.destinations[arena.key])
            for donor in portable_final_boss_donors():
                with self.subTest(arena=arena.key, donor=donor.key):
                    after = self.patched(arena, donor)
                    self.assertEqual(
                        before[arena.completion_event], after[arena.completion_event]
                    )
                    client = CO_OP_RESTORE_EVENTS[arena.key]
                    self.assertEqual(before[client], after[client])
                    self.assertIn(
                        f"SetEventFlag({arena.start_flag}, ON)", after[client]
                    )
                    expected_added = {
                        target
                        for _source, target in (
                            (
                                (12104807, IDS.gehrman_phase_event),
                                (12104808, IDS.gehrman_effect_cleanup_event),
                            )
                            if donor is GEHRMAN_DONOR
                            else (
                                (12104860, IDS.moon_limb_event),
                                (12104870, IDS.moon_player_protection_event),
                            )
                        )
                    }
                    if donor is GEHRMAN_DONOR:
                        expected_added.add(IDS.gehrman_owner_cleanup_event)
                    self.assertEqual(expected_added, set(after) - set(before))

    def test_entry_health_retry_coop_and_destination_telemetry_are_closed(self):
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            before = event_blocks(self.destinations[arena.key])
            for donor in portable_final_boss_donors():
                with self.subTest(arena=arena.key, donor=donor.key):
                    after = self.patched(arena, donor)
                    activation = after[arena.activation_event]
                    self.assertNotIn(
                        f"ForceAnimationPlayback({arena.actor},", activation
                    )
                    self.assertIn(f"SetEventFlag({arena.start_flag}, ON)", activation)
                    health = after[arena.health_bar_event]
                    health_flag = (
                        IDS.gehrman_health_initialized_flag
                        if donor is GEHRMAN_DONOR
                        else IDS.moon_health_initialized_flag
                    )
                    self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", health)
                    self.assertIn(f"if (!EventFlag({health_flag}))", health)
                    self.assertIn(f"SetEventFlag({health_flag}, ON)", health)
                    # The imported source health event's saved-state branch
                    # skips only its first-entry wait, then falls through L0
                    # and restores both destination readiness flags.  This is
                    # why the notification flag is persistent rather than an
                    # Event(0) per-load readiness flag.
                    self.assertLess(
                        health.index("if (!ThisEvent())"), health.index("L0:")
                    )
                    self.assertLess(
                        health.index("L0:"),
                        health.index(f"SetEventFlag({arena.start_flag}, ON)"),
                    )
                    self.assertIn(f"SetNetworkUpdateAuthority({arena.actor},", health)
                    self.assertIn(f"SetSpEffect({arena.actor}, 7500,", health)
                    self.assertIn(f"SetSpEffect({arena.actor}, 7501,", health)
                    self.assertIn(
                        f"SetCharacterAIState({arena.actor}, Enabled)", health
                    )
                    self.assertIn(
                        f"SetCharacterInvincibility({arena.actor}, Disabled)", health
                    )
                    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                        destination_line = next(
                            line
                            for line in before[arena.health_bar_event].splitlines()
                            if line.strip().startswith(instruction + "(")
                        )
                        self.assertIn(destination_line, health)
                    self.assertNotIn("CreatePlaylog(64)", health)
                    self.assertNotIn("CreatePlaylog(128)", health)

    def test_gehrman_phase_event_target_and_physical_owner_cleanup_are_complete(self):
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena, GEHRMAN_DONOR)
                health = after[arena.health_bar_event]
                owner = IDS.gehrman_owner_entity
                self.assertIn(
                    f"SetCharacterEventTarget({arena.actor}, {owner})", health
                )
                phase = after[IDS.gehrman_phase_event]
                for witness in (
                    f"HPRatio({arena.actor}) < 0.5",
                    f"RequestCharacterAICommand({arena.actor}, 100, 0)",
                    f"CharacterHasEventMessage({arena.actor}, 100)",
                    f"ClearSpEffect({arena.actor}, 5305)",
                    f"RequestCharacterAICommand({arena.actor}, 1, 1)",
                ):
                    self.assertIn(witness, phase)
                cleanup = after[IDS.gehrman_effect_cleanup_event]
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 20)", cleanup)
                self.assertIn(f"ClearSpEffect({arena.actor}, 5526)", cleanup)
                owner_cleanup = after[IDS.gehrman_owner_cleanup_event]
                wait = owner_cleanup.index(
                    f"WaitFor(EventFlag({arena.completion_event}))"
                )
                self.assertLess(
                    wait, owner_cleanup.index(f"ForceCharacterDeath({owner}, false)")
                )
                self.assertNotIn("CreateBulletOwner", owner_cleanup)
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 100)",
                    after[arena.music_event],
                )

    def test_moon_limb_and_player_effect_closure_uses_exact_source_bindings(self):
        expected = (
            "0, 12996004, 5, 5, NPCPartType.Part1, 100, 480, 490, 8000",
            "1, 12996004, 6, 6, NPCPartType.Part2, 150, 481, 491, 8010",
            "2, 12996004, 7, 7, NPCPartType.Part3, 150, 482, 492, 8030",
            "3, 12996004, 8, 8, NPCPartType.Part4, 200, 483, 493, 8020",
            "4, 12996004, 9, 9, NPCPartType.Part5, 200, 484, 494, 8040",
        )
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena, MOON_DONOR)
                for arguments in expected:
                    self.assertEqual(
                        1, after[0].count(f"$InitializeEvent({arguments});")
                    )
                limb = after[IDS.moon_limb_event]
                for witness in (
                    f"CreateNPCPart({arena.actor},",
                    f"SetNPCPartSEAndSFX({arena.actor},",
                    f"RequestCharacterAnimationReset({arena.actor},",
                    f"CharacterHasEventMessage({arena.actor}, 300)",
                ):
                    self.assertIn(witness, limb)
                protection = after[IDS.moon_player_protection_event]
                self.assertIn(f"EndIf(EventFlag({arena.completion_event}))", protection)
                for witness in (
                    f"CharacterHasEventMessage({arena.actor}, 10)",
                    "SetCharacterImmortality(10000, Enabled)",
                    "CharacterHasSpEffect(10000, 5570)",
                    "ClearSpEffect(10000, 5572)",
                ):
                    self.assertIn(witness, protection)
                self.assertIn(
                    f"CharacterHasEventMessage({arena.actor}, 500)",
                    after[arena.music_event],
                )

    def test_native_plan_and_physical_actor_requirements_are_source_pinned(self):
        for arena in SUPPORTED_FINAL_BOSS_ARENAS:
            for donor in portable_final_boss_donors():
                with self.subTest(arena=arena.key, donor=donor.key):
                    plan = native_plan_final_boss_donor(
                        arena,
                        donor,
                        self.slots,
                        self.npcs,
                        self.effects,
                        "final-boss-test",
                        IDS,
                    )
                    self.assertEqual(1, plan["swap_count"])
                    self.assertEqual(
                        arena.destination_count,
                        len(plan["primary_init_source_bindings"]),
                    )
                    pin = (
                        GEHRMAN_PRIMARY_PIN
                        if donor is GEHRMAN_DONOR
                        else MOON_PRIMARY_PIN
                    )
                    initialization = (
                        GEHRMAN_INITIALIZATION
                        if donor is GEHRMAN_DONOR
                        else SOURCE_INITIALIZATION
                    )
                    for row in plan["primary_init_source_bindings"]:
                        self.assertEqual(pin, row["source_provenance"]["part_sha256"])
                        self.assertEqual(initialization, row["source_initialization"])
                        if donor is GEHRMAN_DONOR:
                            self.assertEqual(0, row["destination_talk_id_override"])
                    requirements = final_boss_actor_requirements(
                        arena, donor, self.slots, IDS
                    )
                    if donor is MOON_DONOR:
                        self.assertEqual(0, len(requirements))
                        self.assertNotIn("boss_actor_additions", plan)
                        continue
                    self.assertEqual(arena.destination_count, len(requirements))
                    for row in requirements:
                        self.assertEqual(GEHRMAN_OWNER, row["source_entity_id"])
                        self.assertEqual(
                            asdict(GEHRMAN_OWNER_ARCHETYPE), row["source_archetype"]
                        )
                        self.assertEqual(
                            GEHRMAN_OWNER_PIN,
                            row["source_provenance"]["part_sha256"],
                        )
                        self.assertEqual(
                            GEHRMAN_OWNER_PIN,
                            row["source_provenance"]["anchor_sha256"],
                        )
                        self.assertEqual(
                            SOURCE_INITIALIZATION, row["source_initialization"]
                        )

    def test_rejects_source_allocation_and_native_actor_drift(self):
        arena = SUPPORTED_FINAL_BOSS_ARENAS[0]
        with self.assertRaisesRegex(ValueError, "gehrman donor"):
            patch_final_boss_donor(
                arena,
                GEHRMAN_DONOR,
                self.destinations[arena.key],
                self.source.replace(
                    "ClearSpEffect(2100800, 5305)", "ClearSpEffect(2100800, 5306)"
                ),
                IDS,
            )
        with self.assertRaisesRegex(ValueError, "exact original event-target actor"):
            final_boss_actor_requirements(
                arena,
                GEHRMAN_DONOR,
                [slot for slot in self.slots if slot.entity_id != GEHRMAN_OWNER],
                IDS,
            )

    def test_all_twelve_outputs_compile_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        names = {
            "common.emevd.dcx",
            *(
                arena.event_file.removesuffix(".js")
                for arena in SUPPORTED_FINAL_BOSS_ARENAS
            ),
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
            original, decoded = work / "original", work / "decoded"
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
                    str(decoded),
                    "-force",
                    "-silent",
                ],
                check=True,
            )
            pristine = {
                arena.event_file: (decoded / arena.event_file).read_text(
                    encoding="utf-8-sig"
                )
                for arena in SUPPORTED_FINAL_BOSS_ARENAS
            }
            for donor in portable_final_boss_donors():
                for group, label in (
                    (
                        tuple(
                            arena
                            for arena in SUPPORTED_FINAL_BOSS_ARENAS
                            if arena.key != "darkbeast-paarl"
                        ),
                        "base",
                    ),
                    (
                        tuple(
                            arena
                            for arena in SUPPORTED_FINAL_BOSS_ARENAS
                            if arena.key == "darkbeast-paarl"
                        ),
                        "paarl",
                    ),
                ):
                    for path, text in pristine.items():
                        (decoded / path).write_text(text, encoding="utf-8-sig")
                    for arena in group:
                        path = decoded / arena.event_file
                        path.write_text(
                            patch_final_boss_donor(
                                arena,
                                donor,
                                path.read_text(encoding="utf-8-sig"),
                                self.source,
                                IDS,
                            ),
                            encoding="utf-8-sig",
                        )
                    output = work / f"{donor.key}-{label}"
                    subprocess.run(
                        [
                            str(compiler),
                            "/cmd",
                            "-compile",
                            "-game",
                            "bb",
                            "-indir",
                            str(decoded),
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
