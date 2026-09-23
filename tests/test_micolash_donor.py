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
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.micolash_donor import (
    AI_BINDER_SHA256,
    AI_GOAL_SHA256,
    CHARACTER_ARCHIVE_SHA256,
    CO_OP_RESTORE,
    DEFAULT_IDS,
    EVENT_FILE,
    MICOLASH,
    MICOLASH_ARCHETYPE,
    MICOLASH_PIN,
    SOURCE_INITIALIZATION,
    SOURCE_PART,
    SOURCE_TALK_ID,
    TALK_SOURCE_SHA256,
    MicolashDonorIds,
    micolash_donor_contract,
    native_plan_micolash_donor,
    patch_micolash_donor,
    portable_micolash_arenas,
)
from tools.bb_enemizer.scaling import load_params

BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_IDS


class MicolashDonorTests(unittest.TestCase):
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
            patch_micolash_donor(
                arena, self.destinations[arena.key], self.donor, IDS
            )
        )

    def test_allocation_contract_and_source_evidence_cover_all_six(self):
        joined = b"\n".join(
            body
            for prefix in ("event/", "mined/")
            for body in read_prefix(BUNDLE, prefix).values()
        ).decode("utf-8-sig")
        self.assertEqual(tuple(range(12996500, 12996504)), IDS.values())
        for value in IDS.values():
            self.assertNotRegex(joined, rf"(?<![\w]){value}(?![\w])")
        self.assertEqual(ARENAS, portable_micolash_arenas())
        for arena in ARENAS:
            contract = micolash_donor_contract(arena, IDS)
            self.assertEqual("micolash", contract["donor"])
            self.assertIn("continuous direct combat", contract["transition_policy"])
            self.assertEqual(AI_BINDER_SHA256, contract["ai_source_evidence"]["binder_sha256"])
            self.assertEqual(AI_GOAL_SHA256, contract["ai_source_evidence"]["goal_sha256"])
            self.assertEqual(TALK_SOURCE_SHA256, contract["talk_source_evidence"]["sha256"])
            self.assertFalse(contract["talk_source_evidence"]["transplanted"])
            assets = contract["character_asset_evidence"]
            self.assertEqual(CHARACTER_ARCHIVE_SHA256, assets["archive_sha256"])
            self.assertEqual("unproven", assets["executed_tae_entries"])
            self.assertEqual("not-validated", assets["recursive_effect_delivery"])

    def test_destination_terminal_coop_camera_and_unrelated_events_remain_exact(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                self.assertEqual(
                    {IDS.readiness_event, IDS.phase_event}, set(after) - set(before)
                )
                co_op_event, co_op_hash = CO_OP_RESTORE[arena.key]
                self.assertEqual(
                    co_op_hash,
                    hashlib.sha256(before[co_op_event].encode()).hexdigest(),
                )
                for event_id in (
                    arena.completion_event,
                    arena.lockcam_event,
                    co_op_event,
                ):
                    self.assertEqual(before[event_id], after[event_id])
                changed = {
                    0,
                    arena.activation_event,
                    arena.health_bar_event,
                    arena.music_event,
                    *micolash_donor_contract(arena, IDS)[
                        "retired_destination_controllers"
                    ],
                }
                for event_id in set(before) - changed:
                    self.assertEqual(before[event_id], after[event_id])

    def test_entry_readiness_protects_fresh_saved_and_client_paths(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                constructor = after[0]
                readiness = after[IDS.readiness_event]
                health = after[arena.health_bar_event]
                self.assertLess(
                    constructor.index(f"SetEventFlag({IDS.readiness_event}, OFF)"),
                    constructor.index(
                        f"$InitializeEvent(0, {IDS.readiness_event})"
                    ),
                )
                for flag in (IDS.phase_event, IDS.phase_marker_flag):
                    self.assertLess(
                        constructor.index(f"SetEventFlag({flag}, OFF)"),
                        constructor.index(f"$InitializeEvent(0, {IDS.phase_event})"),
                    )
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))", readiness)
                command = f"RequestCharacterAICommand({arena.actor}, -1, 0)"
                self.assertLess(readiness.index(command), readiness.index(
                    f"SetEventFlag({IDS.readiness_event}, ON)"
                ))
                self.assertEqual(
                    2,
                    health.count(f"WaitFor(EventFlag({IDS.readiness_event}))"),
                )
                self.assertLess(
                    health.rindex(f"WaitFor(EventFlag({IDS.readiness_event}))"),
                    health.index(f"SetCharacterInvincibility({arena.actor}, Disabled)"),
                )
                self.assertLess(
                    health.index(f"SetCharacterInvincibility({arena.actor}, Disabled)"),
                    health.index(f"SetCharacterAIState({arena.actor}, Enabled)"),
                )
                self.assertIn(
                    f"SetCharacterDefaultBackreadState({arena.actor}, Enabled)", health
                )
                self.assertIn(
                    f"SetNetworkUpdateRate({arena.actor}, true, CharacterUpdateFrequency.AlwaysUpdate)",
                    health,
                )
                self.assertNotRegex(
                    after[arena.activation_event],
                    rf"ForceAnimationPlayback\({arena.actor}, (?:700[0-9]|3028)",
                )

    def test_continuous_half_health_replan_drives_destination_music_without_chase(self):
        forbidden = (
            "726003",
            "126049",
            "SetDistanceLimitForConversationStateProcessing",
            "WarpCharacterAndSetFloor",
        )
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patched(arena)
                phase = after[IDS.phase_event]
                self.assertLess(
                    phase.index(f"EventFlag({IDS.readiness_event})"),
                    phase.index(f"HPRatio({arena.actor}) <= 0.5"),
                )
                self.assertIn(f"EventFlag({arena.health_bar_event})", phase)
                self.assertNotIn("ThisEvent()", phase)
                self.assertIn(f"SetEventFlag({IDS.phase_marker_flag}, ON)", phase)
                self.assertIn(
                    f"RequestCharacterAICommand({arena.actor}, -1, 0)", phase
                )
                self.assertIn(f"RequestCharacterAIReplan({arena.actor})", phase)
                self.assertIn(
                    f"EventFlag({IDS.phase_marker_flag})", after[arena.music_event]
                )
                combat = after[arena.health_bar_event] + phase
                self.assertNotIn(
                    f"RequestCharacterAICommand({arena.actor}, 10, 0)", combat
                )
                for value in forbidden:
                    self.assertNotIn(value, combat)

    def test_destination_notification_telemetry_and_health_label_are_owned(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patched(arena)
                activation = after[arena.activation_event]
                health = after[arena.health_bar_event]
                self.assertIn(f"SetEventFlag({IDS.notification_flag}, ON)", health)
                if "IssueBossRoomEntryNotification(0)" in before[arena.activation_event]:
                    self.assertIn(
                        f"SetEventFlag({IDS.notification_flag}, ON)", activation
                    )
                    self.assertIn(
                        f"if (!EventFlag({IDS.notification_flag}))", health
                    )
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
                self.assertIn(
                    f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
                    health,
                )

    def test_native_plan_pins_every_state_talk_override_ai_and_rejects_drift(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_micolash_donor(
                    arena, self.slots, self.npcs, self.effects, "micolash-donor", IDS
                )
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(arena.destination_count, len(bindings))
                self.assertEqual(1, plan["swap_count"])
                self.assertNotIn("boss_actor_additions", plan)
                self.assertNotIn("boss_region_additions", plan)
                self.assertNotIn("boss_generator_additions", plan)
                for row in bindings:
                    self.assertEqual(MICOLASH, row["source_entity_id"])
                    self.assertEqual(SOURCE_PART, row["source_part"])
                    self.assertEqual(asdict(MICOLASH_ARCHETYPE), row["source_archetype"])
                    self.assertEqual(SOURCE_TALK_ID, row["source_talk_id"])
                    self.assertEqual(0, row["destination_talk_id_override"])
                    self.assertIn(
                        "destination_talk_id_override", row["required_native_fields"]
                    )
                    self.assertEqual(
                        MICOLASH_PIN, row["source_provenance"]["part_sha256"]
                    )
                    self.assertEqual(SOURCE_INITIALIZATION, row["source_initialization"])
        arena = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "exact reviewed allocation"):
            patch_micolash_donor(
                arena,
                self.destinations[arena.key],
                self.donor,
                replace(IDS, phase_event=IDS.readiness_event),
            )
        with self.assertRaisesRegex(ValueError, "Micolash donor"):
            patch_micolash_donor(
                arena,
                self.destinations[arena.key],
                self.donor.replace(
                    "RequestCharacterAICommand(2600850, 10, 0)",
                    "RequestCharacterAICommand(2600850, 11, 0)",
                    1,
                ),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != MICOLASH]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_micolash_donor(
                arena, missing, self.npcs, self.effects, "missing-micolash", IDS
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
                    destination = path.read_text(encoding="utf-8-sig")
                    path.write_text(
                        patch_micolash_donor(arena, destination, donor, IDS),
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
