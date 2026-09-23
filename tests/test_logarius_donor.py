import hashlib
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob, read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import AMELIA_ARENA, AMYGDALA_ARENA, EBRIETAS_ARENA, PAARL_ARENA
from tools.bb_enemizer.gascoigne_arena_contract import GASCOIGNE_ARENA_CONTRACT
from tools.bb_enemizer.laurence_arena_contract import LAURENCE_ARENA_CONTRACT
from tools.bb_enemizer.maria_arena_contract import MARIA_ARENA_CONTRACT
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.logarius_contract import CORE_PIN, EFFECT_OWNER_PIN, SWORD_PIN
from tools.bb_enemizer.logarius_donor import (
    DEFAULT_LOGARIUS_IDS,
    DESTINATION_CO_OP,
    DESTINATION_FFX,
    LOGARIUS_CORE,
    LOGARIUS_EFFECT_OWNER,
    LOGARIUS_SWORD,
    LOGARIUS_SWORD_EFFECT,
    SOURCE_HASHES,
    SUPPORTED_LOGARIUS_ARENAS,
    helper_scaling_parents,
    logarius_donor_contract,
    native_plan_logarius_donor,
    patch_logarius_donor,
)
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"
IDS = DEFAULT_LOGARIUS_IDS


class LogariusDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.donor = read_blob(BUNDLE, "event/m25_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_LOGARIUS_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_all_allocations_are_absent_from_complete_original_corpus(self):
        joined = b"\n".join(data for prefix in ("event/", "mined/")
                            for data in read_prefix(BUNDLE, prefix).values()).decode("utf-8-sig")
        self.assertEqual((982600, 982601, 12995100, 12995101, 12995102,
                          12995103, 12995104, 12995105),
                         IDS.numeric_ids())
        for value in IDS.numeric_ids():
            self.assertNotRegex(joined, rf"(?<![\w]){value}(?![\w])")

    def test_all_nine_arenas_receive_full_three_actor_combat_closure(self):
        for arena in SUPPORTED_LOGARIUS_ARENAS:
            with self.subTest(arena=arena.key):
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_logarius_donor(
                    arena, self.destinations[arena.key], self.donor, IDS))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                co_op_event, co_op_sha256 = DESTINATION_CO_OP[arena.key]
                self.assertEqual(
                    co_op_sha256,
                    hashlib.sha256(before[co_op_event].encode()).hexdigest(),
                )
                if arena is not LAURENCE_ARENA_CONTRACT:
                    self.assertEqual(before[co_op_event], after[co_op_event])
                contract = logarius_donor_contract(arena, IDS)
                if arena is LAURENCE_ARENA_CONTRACT:
                    self.assertIn(co_op_event, contract["adapted_destination_events"])
                else:
                    self.assertIn(co_op_event, contract["preserved_destination_events"])
                self.assertEqual(co_op_event,
                                 contract["destination_co_op_restore"]["event"])
                self.assertEqual(set(IDS.event_ids()), set(after) - set(before))
                health = after[arena.health_bar_event]
                self.assertIn(f"CreateBulletOwner({IDS.effect_owner_entity})", health)
                self.assertIn(f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, 232000)", health)
                readiness = (
                    IDS.readiness_flag
                    if arena is LAURENCE_ARENA_CONTRACT
                    else arena.start_flag
                )
                self.assertIn(f"WaitFor(EventFlag({readiness}))", health)
                guard = {
                    "vicar-amelia": 12404223,
                    "lady-maria": 13504810,
                    "laurence": 13404860,
                    "father-gascoigne": 12414223,
                }.get(arena.key, IDS.notification_flag)
                self.assertIn(f"if (!EventFlag({guard}))", health)
                self.assertIn(f"SetEventFlag({guard}, ON)", health)
                for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
                    line = next(line for line in before[arena.health_bar_event].splitlines()
                                if line.strip().startswith(instruction + "("))
                    self.assertIn(line, health)
                self.assertIn(f"WarpCharacterAndCopyFloor({IDS.sword_entity}",
                              after[IDS.sword_event])
                self.assertIn(str(LOGARIUS_SWORD_EFFECT), after[IDS.sword_event])
                self.assertIn(
                    f"ShootBullet({IDS.effect_owner_entity}, {arena.actor}, 6, 223200590",
                    after[IDS.aura_event])
                lifecycle = after[IDS.lifecycle_event]
                self.assertIn(f"WaitFor(EventFlag({arena.completion_event}))", lifecycle)
                self.assertIn(f"ForceCharacterDeath({IDS.sword_entity}, false)", lifecycle)
                self.assertIn(f"ForceCharacterDeath({IDS.effect_owner_entity}, false)", lifecycle)

    def test_constructor_preserves_two_sword_slots_and_retires_destination_controllers(self):
        for arena in SUPPORTED_LOGARIUS_ARENAS:
            with self.subTest(arena=arena.key):
                blocks = event_blocks(patch_logarius_donor(
                    arena, self.destinations[arena.key], self.donor, IDS))
                self.assertEqual(2, blocks[0].count(f", {IDS.sword_event})"))
                self.assertEqual(1, blocks[0].count(f", {IDS.aura_event})"))
                self.assertEqual(1, blocks[0].count(f", {IDS.cleanup_event})"))
                self.assertEqual(1, blocks[0].count(f", {IDS.lifecycle_event})"))
                retired = {event for event in (*arena.phase_slots, arena.part_routine_event,
                                                arena.cloth_routine_event,
                                                arena.attachment_anchor_event,
                                                *arena.retired_combat_events)
                           if event is not None}
                for event in retired:
                    self.assertIn("EndEvent();", blocks[event])
                    self.assertNotIn(str(arena.actor), blocks[event])

    def test_base_entry_adapters_and_new_arena_destination_lifecycles(self):
        outputs = {
            arena.key: event_blocks(patch_logarius_donor(
                arena, self.destinations[arena.key], self.donor, IDS))
            for arena in SUPPORTED_LOGARIUS_ARENAS
        }
        for arena in SUPPORTED_LOGARIUS_ARENAS:
            with self.subTest(arena=arena.key):
                self.assertIn(
                    f"CharacterHasSpEffect({arena.actor}, 5633)",
                    outputs[arena.key][arena.music_event],
                )
        for arena in (MARIA_ARENA_CONTRACT, LAURENCE_ARENA_CONTRACT):
            health = outputs[arena.key][arena.health_bar_event]
            self.assertIn(
                f"SetCharacterInvincibility({arena.actor}, Disabled);",
                health,
            )
            self.assertLess(
                health.index(f"SetCharacterInvincibility({arena.actor}, Disabled);"),
                health.index(f"SetCharacterAIState({arena.actor}, Enabled);"),
            )
        laurence = outputs[LAURENCE_ARENA_CONTRACT.key]
        zero = laurence[0]
        pre = laurence[13404861]
        host = laurence[13401851]
        client = laurence[13401853]
        self.assertNotIn("ForceAnimationPlayback(3400850, 7002", pre)
        self.assertIn("ForceAnimationPlayback(3400850, 7000, false, false, false)", pre)
        reset = f"SetEventFlag({IDS.readiness_flag}, OFF)"
        self.assertEqual(1, zero.count(reset))
        self.assertLess(zero.index(reset), zero.index("$InitializeEvent("))
        saved = "if (EventFlag(13401851))"
        self.assertLess(pre.index(saved), pre.index("IssueShortWarpRequest(3400850"))
        saved_ready = f"SetEventFlag({IDS.readiness_flag}, ON)"
        self.assertLess(pre.index("IssueShortWarpRequest(3400850"),
                        pre.index("SetCharacterGravity(3400850, Enabled)"))
        self.assertLess(pre.index("SetCharacterGravity(3400850, Enabled)"),
                        pre.index("SetCharacterInvincibility(3400850, Disabled)"))
        self.assertLess(pre.index("SetCharacterInvincibility(3400850, Disabled)"),
                        pre.index("SetCharacterMaphits(3400850, false)"))
        self.assertLess(pre.index("SetCharacterMaphits(3400850, false)"),
                        pre.index(saved_ready))
        self.assertLess(pre.index(saved_ready), pre.index("EndEvent();"))
        self.assertNotIn("ForceAnimationPlayback(3400850, 3029", host)
        host_ready = f"SetEventFlag({IDS.readiness_flag}, ON)"
        self.assertLess(host.index("IssueShortWarpRequest(3400850"), host.index(host_ready))
        self.assertLess(host.index("SetCharacterGravity(3400850, Enabled)"),
                        host.index(host_ready))
        self.assertLess(host.index("SetCharacterInvincibility(3400850, Disabled)"),
                        host.index(host_ready))
        self.assertLess(host.index("SetCharacterMaphits(3400850, false)"),
                        host.index(host_ready))
        self.assertLess(client.index("SetCharacterMaphits(3400850, false)"),
                        client.index(host_ready))
        health = laurence[LAURENCE_ARENA_CONTRACT.health_bar_event]
        gate = f"WaitFor(EventFlag({IDS.readiness_flag}))"
        self.assertEqual(2, health.count(gate))
        self.assertLess(health.rindex(gate),
                        health.index("SetCharacterAIState(3400850, Enabled)"))
        maria_music = outputs[MARIA_ARENA_CONTRACT.key][MARIA_ARENA_CONTRACT.music_event]
        self.assertIn("chrFlagArea2 &= EventFlag(13504811);", maria_music)
        self.assertIn("L1:", maria_music)
        self.assertIn("EnableBossMapSound(3503804, Enabled);", maria_music)
        gas = outputs[GASCOIGNE_ARENA_CONTRACT.key]
        gas_before = event_blocks(self.destinations[GASCOIGNE_ARENA_CONTRACT.key])
        self.assertEqual(gas_before[12411800], gas[12411800])
        self.assertEqual(gas_before[12411801], gas[12411801])
        self.assertEqual(gas_before[12411802], gas[12411802])
        self.assertEqual(gas_before[12411803], gas[12411803])
        self.assertIn("EventFlag(12414800)", gas[12414802])
        self.assertIn("SetCharacterInvincibility(2410811, Enabled);", gas[IDS.lifecycle_event])
        self.assertIn("ForceCharacterDeath(2410811, false);", gas[IDS.lifecycle_event])
        self.assertNotIn("12415238, 2412820, 2410810", gas[0])
        self.assertNotIn("12415238, 2412820, 2410811", gas[0])


    def test_native_plans_pin_every_primary_and_distinct_helper_state(self):
        for arena in SUPPORTED_LOGARIUS_ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_logarius_donor(
                    arena, self.slots, self.npcs, self.effects, "logarius-reusable", IDS)
                self.assertTrue(plan["scaling"]["enabled"])
                self.assertEqual(arena.destination_count,
                                 len(plan["primary_init_source_bindings"]))
                self.assertEqual(2 * arena.destination_count,
                                 len(plan["boss_actor_additions"]))
                self.assertEqual({LOGARIUS_CORE}, {row["source_entity_id"]
                                                   for row in plan["primary_init_source_bindings"]})
                self.assertEqual({LOGARIUS_SWORD, LOGARIUS_EFFECT_OWNER},
                                 {row["source_entity_id"] for row in plan["boss_actor_additions"]})
                self.assertEqual(
                    {CORE_PIN.part_sha256},
                    {row["source_provenance"]["part_sha256"]
                     for row in plan["primary_init_source_bindings"]},
                )
                self.assertEqual(
                    {SWORD_PIN.part_sha256, EFFECT_OWNER_PIN.part_sha256},
                    {row["source_provenance"]["part_sha256"]
                     for row in plan["boss_actor_additions"]},
                )
                self.assertEqual({IDS.sword_entity, IDS.effect_owner_entity},
                                 {row["destination_entity_id"] for row in plan["boss_actor_additions"]})
                self.assertEqual(2 * arena.destination_count,
                                 len(helper_scaling_parents(plan)))
                self.assertEqual({232000, 232100}, {row["source_npc_param_id"]
                                                    for row in plan["boss_actor_scaling_requirements"]})

    def test_gascoigne_native_plan_pins_three_primary_states_and_terminal_proxies(self):
        plan = native_plan_logarius_donor(
            GASCOIGNE_ARENA_CONTRACT, self.slots, self.npcs, self.effects, "gascoigne-logarius", IDS)
        primary = plan["primary_init_source_bindings"]
        self.assertEqual(
            {"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"},
            {row["destination_map"] for row in primary},
        )
        retained = plan["boss_contract"]["retained_destination_helpers"]
        self.assertEqual(3, len(retained))
        self.assertEqual({2410811}, {row["entity_id"] for row in retained})
        self.assertEqual(
            GASCOIGNE_ARENA_CONTRACT.event_file.removesuffix(".js"),
            plan["boss_emevd_ffx_requirements"][0]["destination_event_file"],
        )

    def test_each_native_plan_declares_pinned_event_effect_and_full_bank_union(self):
        area_banks = {
            "cleric-beast": "frpg_sfxbnd_m24.ffxbnd.dcx",
            "blood-starved-beast": "frpg_sfxbnd_m23.ffxbnd.dcx",
            "darkbeast-paarl": "frpg_sfxbnd_m23.ffxbnd.dcx",
            "vicar-amelia": "frpg_sfxbnd_m24.ffxbnd.dcx",
            "amygdala": "frpg_sfxbnd_m33.ffxbnd.dcx",
            "ebrietas": "frpg_sfxbnd_m24.ffxbnd.dcx",
            "lady-maria": "frpg_sfxbnd_m35.ffxbnd.dcx",
            "laurence": "frpg_sfxbnd_m34.ffxbnd.dcx",
            "father-gascoigne": "frpg_sfxbnd_m24.ffxbnd.dcx",
        }
        for arena in SUPPORTED_LOGARIUS_ARENAS:
            with self.subTest(arena=arena.key):
                plan = native_plan_logarius_donor(
                    arena, self.slots, self.npcs, self.effects, "logarius-ffx", IDS)
                requirement = plan["boss_emevd_ffx_requirements"][0]
                self.assertEqual((12504806, IDS.sword_event, 623206),
                                 (requirement["source_event_id"],
                                  requirement["destination_event_id"], requirement["effect_id"]))
                merge = plan["boss_ffx_merges"][0]
                self.assertEqual(area_banks[arena.key], merge["destination_file"])
                self.assertEqual("preserve_destination_union_source_v1", merge["policy"])
                self.assertEqual([623206], merge["required_effect_ids"])
                self.assertEqual(DESTINATION_FFX[arena.key],
                                 (merge["destination_file"], merge["destination_sha256"]))
                evidence = logarius_donor_contract(arena, IDS)["projectile_evidence"]
                self.assertFalse(evidence["additional_ffx_dependency"])
                self.assertEqual((223200590, 232250, -1, 0),
                                 (evidence["shoot_bullet_behavior_id"],
                                  evidence["behavior_referenced_bullet_param_id"],
                                  evidence["bullet_param_sfx_id"],
                                  evidence["bullet_param_is_attack_sfx"]))

    def test_rejects_collisions_source_drift_and_missing_helper_provenance(self):
        arena = SUPPORTED_LOGARIUS_ARENAS[0]
        with self.assertRaisesRegex(ValueError, "collides"):
            patch_logarius_donor(arena, self.destinations[arena.key], self.donor,
                                 replace(IDS, sword_event=arena.health_bar_event))
        with self.assertRaisesRegex(ValueError, "Logarius donor"):
            patch_logarius_donor(arena, self.destinations[arena.key],
                                 self.donor.replace("223200590", "223200591"), IDS)
        missing = [slot for slot in self.slots if slot.entity_id != LOGARIUS_EFFECT_OWNER]
        with self.assertRaisesRegex(ValueError, "placement provenance"):
            native_plan_logarius_donor(arena, missing, self.npcs, self.effects, "missing", IDS)

    def test_all_outputs_compile_with_pinned_darkscript_when_available(self):
        compiler = ROOT / "work/DarkScript3/DarkScript3.exe"
        events = ROOT / "work/boss-shuffle-validation/events"
        names = {"common.emevd.dcx", *(arena.event_file.removesuffix(".js")
                                       for arena in SUPPORTED_LOGARIUS_ARENAS)}
        if not compiler.is_file() or any(not (events / name).is_file() for name in names):
            self.skipTest("pinned DarkScript/original event fixture unavailable")
        self.assertEqual("c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
                         hashlib.sha256(compiler.read_bytes()).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory); original = work / "o"; source = work / "s"; output = work / "out"
            original.mkdir()
            for name in names:
                shutil.copyfile(events / name, original / name)
            subprocess.run([str(compiler), "/cmd", "-decompile", "-game", "bb",
                            "-indir", str(original), "-outdir", str(source), "-force", "-silent"],
                           check=True)
            for arena in SUPPORTED_LOGARIUS_ARENAS:
                name = arena.event_file
                current = (source / name).read_text(encoding="utf-8-sig")
                # BSB and Paarl share m23; each standalone route compiles from
                # the same original rather than composing two Logarius donors.
                patched = patch_logarius_donor(arena, current, self.donor, IDS)
                with tempfile.TemporaryDirectory() as single:
                    single_source = Path(single) / "source"; single_out = Path(single) / "out"
                    shutil.copytree(source, single_source)
                    (single_source / name).write_text(patched, encoding="utf-8-sig")
                    subprocess.run([str(compiler), "/cmd", "-compile", "-game", "bb",
                                    "-indir", str(single_source), "-outdir", str(single_out),
                                    "-force", "-silent"], check=True)
                    self.assertTrue((single_out / name.removesuffix(".js")).is_file())


if __name__ == "__main__":
    unittest.main()
