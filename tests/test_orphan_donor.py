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
from tools.bb_enemizer.orphan_donor import (
    ARENAS,
    CO_OP_RESTORE_EVENTS,
    CORE,
    CORE_ARCHETYPE,
    DEFAULT_ALLOCATION,
    EVENT_FILE,
    PART_PINS,
    PHASE,
    PHASE_ARCHETYPE,
    SOURCE_HASHES,
    SOURCE_INITIALIZATION,
    SUPPORT,
    SUPPORT_ARCHETYPE,
    OrphanDonorAllocation,
    native_plan_orphan_donor,
    orphan_donor_contract,
    patch_orphan_donor,
    portable_orphan_arenas,
)
from tools.bb_enemizer.scaling import load_params

BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_ALLOCATION


class OrphanDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orphan = read_blob(BUNDLE, "event/" + EVENT_FILE).decode("utf-8-sig")
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
            patch_orphan_donor(arena, self.destinations[arena.key], self.orphan, IDS)
        )

    def test_allocation_is_disjoint_from_original_inputs_and_complete(self):
        joined = b"\n".join(
            body
            for prefix in ("event/", "mined/")
            for body in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        self.assertEqual(
            (
                12995500,
                12995501,
                12995502,
                12995503,
                12995504,
                12995505,
                12995506,
                983000,
                983001,
            ),
            IDS.values(),
        )
        for value in IDS.values():
            self.assertNotRegex(joined, rf"(?<![\w]){value}(?![\w])")
        self.assertEqual(ARENAS, portable_orphan_arenas())

    def test_full_source_combat_closure_and_saved_phase_state_all_six(self):
        added = {
            IDS.phase_event,
            IDS.support_event,
            IDS.player_effect_event,
            IDS.phase_camera_event,
            IDS.terminal_bridge_event,
        }
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
                self.assertIn(
                    f"ChangeCharacterEnableState({IDS.support_entity}, Disabled)",
                    health,
                )
                self.assertIn(f"if (EventFlag({IDS.phase_event}))", health)
                self.assertIn(
                    f"ChangeCharacterEnableState({IDS.phase_entity}, Enabled)",
                    after[IDS.phase_event],
                )
                support = after[IDS.support_event]
                self.assertLess(
                    support.index(f"CharacterHasEventMessage({IDS.phase_entity}, 100)"),
                    support.index(
                        f"ChangeCharacterEnableState({IDS.support_entity}, Enabled)"
                    ),
                )
                for source_actor in (CORE, PHASE, SUPPORT):
                    self.assertNotIn(str(source_actor), health)
                for source_event in (13604820, 13604830, 13604840, 13604850):
                    self.assertNotIn(
                        str(source_event), "\n".join(after[event] for event in added)
                    )

    def test_destination_terminal_coop_and_unrelated_events_remain_exact(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertEqual(
                    before[arena.completion_event], after[arena.completion_event]
                )
                coop = CO_OP_RESTORE_EVENTS[arena.key]
                self.assertEqual(before[coop], after[coop])
                bridge = after[IDS.terminal_bridge_event]
                self.assertIn(
                    f"EventFlag({arena.completion_event}) || ThisEvent()", bridge
                )
                self.assertIn(f"CharacterDead({arena.actor})", bridge)
                self.assertIn(f"CharacterDead({IDS.phase_entity})", bridge)
                force = f"ForceCharacterDeath({arena.actor}, false)"
                wait = f"WaitFor(EventFlag({arena.completion_event}))"
                self.assertLess(bridge.index(force), bridge.index(wait))
                self.assertGreater(
                    bridge.index(
                        f"ForceCharacterDeath({IDS.support_entity}, false)",
                        bridge.index(wait),
                    ),
                    bridge.index(wait),
                )
                contract = orphan_donor_contract(arena, IDS)
                self.assertEqual(
                    [arena.completion_event, coop],
                    contract["preserved_destination_events"],
                )

    def test_destination_entry_protection_and_notification_ownership(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                activation = after[arena.activation_event]
                health = after[arena.health_bar_event]
                self.assertNotRegex(
                    activation,
                    rf"ForceAnimationPlayback\({arena.actor}, (?:700[0-9]|3028)",
                )
                if arena.key in ("darkbeast-paarl", "amygdala"):
                    enabled = f"SetCharacterInvincibility({arena.actor}, Enabled)"
                    disabled = f"SetCharacterInvincibility({arena.actor}, Disabled)"
                    self.assertLess(
                        activation.index(enabled), activation.index("WaitFor(")
                    )
                    self.assertLess(
                        activation.index("WaitFor("), activation.index(disabled)
                    )
                if arena.key == "ebrietas":
                    immortal = f"SetCharacterImmortality({arena.actor}, Enabled)"
                    mortal = f"SetCharacterImmortality({arena.actor}, Disabled)"
                    self.assertLess(
                        activation.index(immortal), activation.index("HasDamageType(")
                    )
                    self.assertLess(
                        activation.index("HasDamageType("), activation.index(mortal)
                    )
                if arena.key == "vicar-amelia":
                    self.assertIn("if (!EventFlag(12404223))", health)
                    self.assertEqual(
                        1, activation.count("IssueBossRoomEntryNotification(0)")
                    )
                    self.assertNotIn(str(IDS.notification_flag), activation)
                else:
                    self.assertIn(f"SetEventFlag({IDS.notification_flag}, ON)", health)

    def test_destination_music_camera_and_telemetry_are_arena_owned(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                music = after[arena.music_event]
                self.assertIn(f"EventFlag({IDS.phase_event})", music)
                self.assertNotIn("3602802", music)
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    expected = [
                        line.strip()
                        for line in before[arena.health_bar_event].splitlines()
                        if line.strip().startswith(instruction + "(")
                    ]
                    actual = [
                        line.strip()
                        for line in after[arena.health_bar_event].splitlines()
                        if line.strip().startswith(instruction + "(")
                    ]
                    self.assertEqual(expected, actual)
                combined_camera = (
                    after[arena.lockcam_event] + after[IDS.phase_camera_event]
                )
                self.assertNotIn("SetLockcamSlotNumber(34, 0,", combined_camera)
                self.assertNotIn("SetLockcamSlotNumber(36, 0,", combined_camera)
                self.assertIn(
                    f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
                    combined_camera,
                )

    def test_native_plan_pins_every_primary_and_helper_state_and_scales_helpers(self):
        sources = {
            CORE: ("c4540_0000", CORE_ARCHETYPE),
            PHASE: ("c4541_0000", PHASE_ARCHETYPE),
            SUPPORT: ("c4543_0000", SUPPORT_ARCHETYPE),
        }
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_orphan_donor(
                    arena, self.slots, self.npcs, self.effects, "orphan-donor", IDS
                )
                self.assertEqual(
                    arena.destination_count, len(plan["primary_init_source_bindings"])
                )
                self.assertEqual(
                    2 * arena.destination_count, len(plan["boss_actor_additions"])
                )
                all_rows = [
                    *plan["primary_init_source_bindings"],
                    *plan["boss_actor_additions"],
                ]
                for row in all_rows:
                    entity = row["source_entity_id"]
                    self.assertEqual(sources[entity][0], row["source_part"])
                    self.assertEqual(
                        asdict(sources[entity][1]), row["source_archetype"]
                    )
                    self.assertEqual(
                        PART_PINS[entity], row["source_provenance"]["part_sha256"]
                    )
                    self.assertEqual(
                        SOURCE_INITIALIZATION, row["source_initialization"]
                    )
                for row in plan["boss_actor_additions"]:
                    self.assertEqual(
                        PART_PINS[CORE], row["source_provenance"]["anchor_sha256"]
                    )
                parents = {
                    (row["destination_map"], row["destination_part"]): plan[
                        "boss_contract"
                    ]["helper_scaling_parent"][
                        f'{row["destination_map"]}:{row["destination_part"]}'
                    ]
                    for row in plan["boss_actor_additions"]
                }
                scaled = allocate_actor_scaling(plan, self.npcs, parents)
                self.assertEqual(len(plan["boss_actor_additions"]), len(scaled))

    def test_rejects_id_source_and_native_pin_drift(self):
        cleric = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_orphan_donor(
                cleric,
                self.destinations[cleric.key],
                self.orphan,
                replace(IDS, support_event=IDS.phase_event),
            )
        with self.assertRaisesRegex(ValueError, "Orphan donor"):
            patch_orphan_donor(
                cleric,
                self.destinations[cleric.key],
                self.orphan.replace(
                    "SetSpEffect(3600801, 5333, false)",
                    "SetSpEffect(3600801, 5334, false)",
                ),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != SUPPORT]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_orphan_donor(
                cleric, missing, self.npcs, self.effects, "missing-support", IDS
            )

    def test_all_six_outputs_compile_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work" / "DarkScript3" / "DarkScript3.exe"
        events = ROOT / "work" / "boss-shuffle-validation" / "events"
        names = {
            "common.emevd.dcx",
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
            m23_original = (source / "m23_00_00_00.emevd.dcx.js").read_text(
                encoding="utf-8-sig"
            )
            for batch, suffix in (
                (ARENAS[:4] + ARENAS[4:], "bsb"),
                ((ARENAS[2],), "paarl"),
            ):
                # BSB and Paarl share m23. Compile them in separate source snapshots;
                # every other destination can be compiled with the first batch.
                selected = tuple(
                    arena
                    for arena in batch
                    if suffix == "paarl" or arena.key != "darkbeast-paarl"
                )
                (source / "m23_00_00_00.emevd.dcx.js").write_text(
                    m23_original, encoding="utf-8-sig"
                )
                for arena in selected:
                    path = source / arena.event_file
                    path.write_text(
                        patch_orphan_donor(
                            arena,
                            path.read_text(encoding="utf-8-sig"),
                            self.orphan,
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
