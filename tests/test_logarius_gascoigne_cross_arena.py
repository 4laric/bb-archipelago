import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.arena_port import MARIA_CROSS_ARENA_PORTS, MICOLASH_PORT
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.gascoigne_donor import (
    BEAST_PINS,
    DEFAULT_GASCOIGNE_IDS,
    GASCOIGNE_EVENT_SOURCE,
    HUMAN_PINS,
    native_plan_gascoigne_donor,
    patch_gascoigne_donor,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.logarius_contract import (
    CORE_PIN,
    EFFECT_OWNER_PIN,
    LOGARIUS_EVENT_SOURCE,
    SWORD_PIN,
)
from tools.bb_enemizer.logarius_donor import (
    DEFAULT_LOGARIUS_IDS,
    LOGARIUS_PHASE_EFFECT,
    PORT_LOGARIUS_ACTIVATION_EVENT,
    native_plan_logarius_donor,
    patch_logarius_donor,
)
from tools.bb_enemizer.scaling import load_params


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class LogariusGascoigneCrossArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logarius = read_blob(BUNDLE, LOGARIUS_EVENT_SOURCE).decode("utf-8-sig")
        cls.gascoigne = read_blob(BUNDLE, GASCOIGNE_EVENT_SOURCE).decode("utf-8-sig")
        cls.destinations = {
            port.arena.key: read_blob(
                BUNDLE, "event/" + port.arena.event_file
            ).decode("utf-8-sig")
            for port in MARIA_CROSS_ARENA_PORTS
        }
        with tempfile.TemporaryDirectory() as directory:
            inventory = Path(directory) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_logarius_fragments_keep_three_actor_combat_and_destination_lifecycle(self):
        ids = DEFAULT_LOGARIUS_IDS
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(arena=port.arena.key):
                arena = port.arena
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_logarius_donor(
                    port, self.destinations[arena.key], self.logarius, ids
                ))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                for event_id in port.protected_events:
                    self.assertEqual(before[event_id], after[event_id])
                self.assertNotIn("PlayCutscene", after[arena.activation_event])
                wake = after[PORT_LOGARIUS_ACTIVATION_EVENT]
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))", wake)
                self.assertIn(f"ForceAnimationPlayback({arena.actor}, 7000", wake)
                health = after[arena.health_bar_event]
                self.assertIn(f"CreateBulletOwner({ids.effect_owner_entity})", health)
                self.assertIn(f"SetCharacterImmortality({ids.sword_entity}, Enabled)", health)
                self.assertIn(f"WaitFor(EventFlag({ids.readiness_flag}))", health)
                self.assertIn(
                    f"CharacterHasSpEffect({arena.actor}, {LOGARIUS_PHASE_EFFECT})",
                    after[arena.music_event],
                )
                self.assertIn(f"WarpCharacterAndCopyFloor({ids.sword_entity}",
                              after[ids.sword_event])
                self.assertIn(f"ShootBullet({ids.effect_owner_entity}",
                              after[ids.aura_event])
                self.assertIn(f"WaitFor(EventFlag({arena.completion_event}))",
                              after[ids.lifecycle_event])
                if port is MICOLASH_PORT:
                    self.assertIn("SetEventFlag(72600301, ON)",
                                  after[port.terminal_bridge_event])

    def test_gascoigne_fragments_keep_transformation_specials_and_active_form_terminal(self):
        ids = DEFAULT_GASCOIGNE_IDS
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(arena=port.arena.key):
                arena = port.arena
                before = event_blocks(self.destinations[arena.key])
                after = event_blocks(patch_gascoigne_donor(
                    port, self.destinations[arena.key], self.gascoigne, ids
                ))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                for event_id in port.protected_events:
                    self.assertEqual(before[event_id], after[event_id])
                self.assertNotIn("PlayCutscene", after[arena.activation_event])
                self.assertIn(f"WaitFor(EventFlag({arena.start_flag}))",
                              after[ids.readiness_event])
                phase = after[ids.phase_event]
                self.assertIn(f"ChangeCharacterEnableState({ids.beast_entity}, Enabled)", phase)
                self.assertNotIn("9337", phase)
                self.assertNotIn("$InitializeEvent(0, 9350", phase)
                self.assertIn(str(arena.actor), after[ids.human_special_event])
                self.assertIn(str(ids.beast_entity), after[ids.beast_special_event])
                terminal = after[ids.terminal_bridge_event]
                self.assertIn(f"humanDead = CharacterDead({arena.actor})", terminal)
                self.assertIn(f"beastDead = EventFlag({ids.phase_event}) && CharacterDead({ids.beast_entity})", terminal)
                self.assertIn(f"ForceCharacterDeath({arena.actor}, false)", terminal)
                self.assertIn(f"EventFlag({ids.phase_event})", after[arena.music_event])
                if port is MICOLASH_PORT:
                    self.assertIn("SetEventFlag(72600301, ON)",
                                  after[port.terminal_bridge_event])

    def test_native_plans_pin_donors_helpers_destinations_and_retained_actors(self):
        helper_counts = {"gehrman": 2, "moon-presence": 2, "micolash": 0}
        for port in MARIA_CROSS_ARENA_PORTS:
            with self.subTest(donor="logarius", arena=port.arena.key):
                plan = native_plan_logarius_donor(
                    port, self.slots, self.npcs, self.effects, "logarius-port"
                )
                primary = plan["primary_init_source_bindings"][0]
                self.assertEqual(CORE_PIN.part_sha256,
                                 primary["source_provenance"]["part_sha256"])
                self.assertEqual(port.primary_talk_id,
                                 primary["destination_original_talk_id"])
                self.assertEqual(
                    {SWORD_PIN.part_sha256, EFFECT_OWNER_PIN.part_sha256},
                    {row["source_provenance"]["part_sha256"]
                     for row in plan["boss_actor_additions"]},
                )
                self.assertEqual(helper_counts[port.arena.key], len(
                    plan["boss_contract"]["retained_destination_helpers"]
                ))
            with self.subTest(donor="gascoigne", arena=port.arena.key):
                plan = native_plan_gascoigne_donor(
                    port, self.slots, self.npcs, self.effects, "gascoigne-port"
                )
                primary = plan["primary_init_source_bindings"][0]
                self.assertEqual(HUMAN_PINS["00"],
                                 primary["source_provenance"]["part_sha256"])
                self.assertEqual(0, primary["destination_talk_id_override"])
                self.assertEqual(BEAST_PINS["00"],
                                 plan["boss_actor_additions"][0]["source_provenance"]["part_sha256"])
                self.assertEqual(helper_counts[port.arena.key], len(
                    plan["boss_contract"]["retained_destination_helpers"]
                ))

    def test_six_routes_compile_from_exact_originals_with_pinned_darkscript(self):
        compiler = ROOT / "work/DarkScript3/DarkScript3.exe"
        events = ROOT / "work/boss-shuffle-validation/events"
        if not compiler.is_file():
            self.skipTest("pinned DarkScript unavailable")
        self.assertEqual(
            "c86fd23ee28f7d39032a5bc792f9510bbd171ca72de1c547d956fe5e161d54de",
            hashlib.sha256(compiler.read_bytes()).hexdigest(),
        )
        donors = (
            ("logarius", LOGARIUS_EVENT_SOURCE.removeprefix("event/").removesuffix(".js"),
             self.logarius, patch_logarius_donor),
            ("gascoigne", GASCOIGNE_EVENT_SOURCE.removeprefix("event/").removesuffix(".js"),
             self.gascoigne, patch_gascoigne_donor),
        )
        for donor_key, donor_binary, _, patcher in donors:
            for port in MARIA_CROSS_ARENA_PORTS:
                with self.subTest(donor=donor_key, arena=port.arena.key), \
                        tempfile.TemporaryDirectory() as directory:
                    work = Path(directory)
                    original, source, output = work / "o", work / "s", work / "out"
                    original.mkdir()
                    destination_binary = port.arena.event_file.removesuffix(".js")
                    required = ("common.emevd.dcx", donor_binary, destination_binary)
                    if any(not (events / name).is_file() for name in required):
                        self.skipTest("exact original event fixture unavailable")
                    for name in required:
                        shutil.copyfile(events / name, original / name)
                    subprocess.run([
                        str(compiler), "/cmd", "-decompile", "-game", "bb",
                        "-indir", str(original), "-outdir", str(source),
                        "-force", "-silent",
                    ], check=True)
                    destination_path = source / port.arena.event_file
                    donor_path = source / (donor_binary + ".js")
                    destination_path.write_text(
                        patcher(
                            port,
                            destination_path.read_text(encoding="utf-8-sig"),
                            donor_path.read_text(encoding="utf-8-sig"),
                        ),
                        encoding="utf-8-sig",
                    )
                    subprocess.run([
                        str(compiler), "/cmd", "-compile", "-game", "bb",
                        "-indir", str(source), "-outdir", str(output),
                        "-force", "-silent",
                    ], check=True)
                    self.assertGreater((output / destination_binary).stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
