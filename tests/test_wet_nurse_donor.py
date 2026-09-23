import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.boss_entrances import skip_replacement_entrance
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.wet_nurse_donor import (
    CHARACTER_ARCHIVE_SHA256,
    CHARACTER_TAE_SHA256,
    CORE,
    DEFAULT_ALLOCATION,
    EMEVD_EFFECT,
    EVENT_FILE,
    MISSING_TAE_EFFECT,
    OBJECT_PIN,
    PROXY,
    REGION_PINS,
    SOURCE_FFX_SHA256,
    SOURCE_HASHES,
    SOURCE_INITIALIZATION,
    SOURCE_PART_PINS,
    SUPPORT,
    WET_ARCHETYPE,
    WetNurseDonorAllocation,
    native_plan_wet_nurse_donor,
    patch_wet_nurse_donor,
    portable_wet_nurse_arenas,
    wet_nurse_donor_contract,
)

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"
IDS = DEFAULT_ALLOCATION


class WetNurseDonorTests(unittest.TestCase):
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

    def patch(self, arena):
        return event_blocks(
            patch_wet_nurse_donor(arena, self.destinations[arena.key], self.donor, IDS)
        )

    def test_allocation_and_contract_cover_all_six_arenas(self):
        arenas = portable_wet_nurse_arenas()
        self.assertEqual(
            tuple(arena.key for arena in ARENAS), tuple(a.key for a in arenas)
        )
        self.assertEqual(tuple(range(12996400, 12996407)), IDS.event_ids())
        self.assertEqual(
            set(range(12996420, 12996431)),
            set(IDS.values()[7:18]),
        )
        self.assertEqual(
            set(range(983900, 983909)), set(IDS.values()) & set(range(983900, 984000))
        )
        for arena in arenas:
            contract = wet_nurse_donor_contract(arena, IDS)
            self.assertEqual("mergos-wet-nurse", contract["donor"])
            self.assertEqual(arena.key, contract["arena"])
            self.assertEqual(
                [EMEVD_EFFECT, MISSING_TAE_EFFECT],
                contract["character_asset_evidence"]["observed_direct_effect_ids"],
            )
            self.assertEqual("not-validated", contract["character_asset_evidence"]["character_delivery_status"])
            self.assertEqual(
                "unproven", contract["character_asset_evidence"]["runtime_closure"]
            )

    def test_preserves_terminal_coop_camera_and_adapts_only_destination_entry_setpiece(
        self,
    ):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = self.patch(arena)
                contract = wet_nurse_donor_contract(arena, IDS)
                for event_id in contract["preserved_destination_events"]:
                    self.assertEqual(before[event_id], after[event_id])
                normalized = event_blocks(
                    skip_replacement_entrance(
                        arena.key,
                        self.destinations[arena.key],
                        patch_wet_nurse_donor(
                            arena, self.destinations[arena.key], self.donor, IDS
                        ),
                    )
                )
                self.assertNotIn("PlayCutscene", normalized[arena.activation_event])
                self.assertNotIn("26000010", normalized[arena.activation_event])
                self.assertIn(
                    f"SetEventFlag({arena.start_flag}, ON)",
                    normalized[arena.activation_event],
                )

    def test_health_keeps_full_three_body_proxy_graph_and_destination_telemetry(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                health = self.patch(arena)[arena.health_bar_event]
                self.assertIn(
                    f"SetCharacterImmortality({arena.actor}, Enabled)", health
                )
                self.assertIn(
                    f"SetCharacterImmortality({IDS.support_entity}, Enabled)", health
                )
                self.assertIn(
                    f"DisplayBossHealthBar(Enabled, {IDS.proxy_entity}, 0, 551000)",
                    health,
                )
                self.assertIn(
                    f"CreateReferredDamagePair({arena.actor}, {IDS.proxy_entity})",
                    health,
                )
                self.assertIn(
                    f"CreateReferredDamagePair({IDS.support_entity}, {IDS.proxy_entity})",
                    health,
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
                flags = {
                    int(flag)
                    for flag in re.findall(r"(?:EventFlag|SetEventFlag)\((\d+)", health)
                }
                notification = re.search(
                    r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification",
                    before[arena.health_bar_event],
                )
                notification_flag = (
                    IDS.notification_flag
                    if notification is None
                    else int(notification[1])
                )
                self.assertEqual(
                    {arena.completion_event, arena.start_flag, notification_flag}, flags
                )

    def test_nightmare_routes_support_spawn_music_bridge_and_cleanup_are_closed(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                after = self.patch(arena)
                for event_id in IDS.event_ids():
                    self.assertIn(event_id, after)
                self.assertIn(
                    f"HPRatio({IDS.proxy_entity}) < 0.7", after[arena.music_event]
                )
                emergence = after[IDS.support_emergence_event]
                self.assertEqual(2, emergence.count(f"{EMEVD_EFFECT}"))
                self.assertIn(f"WarpObjectToCharacter({IDS.object_entity}", emergence)
                bridge = after[IDS.terminal_bridge_event]
                self.assertLess(
                    bridge.index(f"HPRatio({IDS.proxy_entity}) <= 0"),
                    bridge.index(f"ForceCharacterDeath({arena.actor}, false)"),
                )
                self.assertLess(
                    bridge.index(f"ForceCharacterDeath({arena.actor}, false)"),
                    bridge.index(f"WaitFor(EventFlag({arena.completion_event}))"),
                )
                cleanup = after[IDS.helper_cleanup_event]
                self.assertLess(
                    cleanup.index(f"WaitFor(EventFlag({arena.completion_event}))"),
                    cleanup.index(
                        f"ChangeCharacterEnableState({IDS.support_entity}, Disabled)"
                    ),
                )
                self.assertNotIn(
                    "PlaySE(", "\n".join(after[x] for x in IDS.event_ids())
                )
                for retired in wet_nurse_donor_contract(arena, IDS)[
                    "retired_destination_controllers"
                ]:
                    self.assertIn("EndEvent();", after[retired])

    def test_native_plan_pins_actors_regions_object_scaling_and_effect_delivery(self):
        for arena in ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_wet_nurse_donor(
                    arena, self.slots, self.npcs, self.effects, "wet-donor", IDS
                )
                count = arena.destination_count
                self.assertEqual(count, len(plan["primary_init_source_bindings"]))
                self.assertEqual(2 * count, len(plan["boss_actor_additions"]))
                self.assertEqual(6 * count, len(plan["boss_region_additions"]))
                self.assertEqual(count, len(plan["boss_object_additions"]))
                self.assertEqual(
                    2 * count, len(plan["boss_actor_scaling_requirements"])
                )
                rows = [
                    *plan["primary_init_source_bindings"],
                    *plan["boss_actor_additions"],
                ]
                self.assertEqual(
                    {CORE, SUPPORT, PROXY}, {row["source_entity_id"] for row in rows}
                )
                for row in rows:
                    self.assertEqual(asdict(WET_ARCHETYPE), row["source_archetype"])
                    self.assertEqual(
                        SOURCE_PART_PINS[row["source_entity_id"]],
                        row["source_provenance"]["part_sha256"],
                    )
                    self.assertEqual(
                        SOURCE_INITIALIZATION, row["source_initialization"]
                    )
                self.assertEqual(
                    set(REGION_PINS),
                    {row["source_entity_id"] for row in plan["boss_region_additions"]},
                )
                self.assertEqual(
                    {OBJECT_PIN},
                    {
                        row["source_provenance"]["part_sha256"]
                        for row in plan["boss_object_additions"]
                    },
                )
                requirement = plan["boss_emevd_ffx_requirements"][0]
                self.assertEqual(
                    (12604840, IDS.support_emergence_event, EMEVD_EFFECT, 2),
                    (
                        requirement["source_event_id"],
                        requirement["destination_event_id"],
                        requirement["effect_id"],
                        requirement["occurrence_count"],
                    ),
                )
                merge = plan["boss_ffx_merges"][0]
                self.assertEqual(SOURCE_FFX_SHA256, merge["source_sha256"])
                self.assertEqual(
                    [EMEVD_EFFECT], merge["required_effect_ids"]
                )
                evidence = plan["boss_contract"]["character_asset_evidence"]
                self.assertEqual(CHARACTER_ARCHIVE_SHA256, evidence["archive_sha256"])
                self.assertEqual(CHARACTER_TAE_SHA256, evidence["tae_sha256"])

    def test_rejects_allocation_source_and_native_roster_drift(self):
        arena = ARENAS[0]
        with self.assertRaisesRegex(ValueError, "exact reviewed allocation"):
            patch_wet_nurse_donor(
                arena,
                self.destinations[arena.key],
                self.donor,
                replace(IDS, proxy_entity=IDS.support_entity),
            )
        with self.assertRaisesRegex(ValueError, "Wet Nurse donor"):
            patch_wet_nurse_donor(
                arena,
                self.destinations[arena.key],
                self.donor.replace(
                    "SetSpEffect(2600800, 5631", "SetSpEffect(2600800, 5632"
                ),
                IDS,
            )
        missing = [slot for slot in self.slots if slot.entity_id != PROXY]
        with self.assertRaisesRegex(ValueError, "exact source actor"):
            native_plan_wet_nurse_donor(
                arena, missing, self.npcs, self.effects, "missing-proxy", IDS
            )

    def test_all_six_outputs_compile_with_pinned_darkscript_when_available(self):
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
                        patch_wet_nurse_donor(arena, destination, donor, IDS),
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
