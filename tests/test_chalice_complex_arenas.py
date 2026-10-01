import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch as mock_patch

from tools.bb_inputs import read_blob
from tools.bb_enemizer import chalice_complex_arenas as route
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.chalice_recipes import chalice_recipes
from tools.bb_enemizer.good_boss_pool import assign_good_bosses, GOOD_FAMILIES
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.build_boss_encounters import good_boss_routes, validate_allocations

BUNDLE = Path(__file__).resolve().parents[1] / "research/bb_inputs.db"


class ChaliceComplexArenaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        cls.destinations = {
            key: read_blob(BUNDLE, "event/" + s.arena.event_file).decode("utf-8-sig")
            for key, s in route.SPECS.items()
        }
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory, fixed_maps_only=False)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_twelve_routes_preserve_terminal_guest_and_shared_progression(self):
        examined = 0
        for spec in route.SPECS.values():
            before = event_blocks(self.destinations[spec.arena.key])
            for donor in route.humanoid.DONORS.values():
                after = event_blocks(
                    route.patch(
                        spec, donor, self.destinations[spec.arena.key], self.common
                    )
                )
                self.assertEqual(set(before) | {spec.bridge}, set(after))
                for eid in spec.preserved:
                    self.assertEqual(before[eid], after[eid])
                for eid in spec.retired:
                    self.assertIn("EndEvent();", after[eid])
                    self.assertNotIn("RequestCharacterAI", after[eid])
                self.assertNotIn(
                    "CreateReferredDamagePair", after[spec.arena.health_bar_event]
                )
                self.assertIn(
                    f"CharacterHasEventMessage({spec.arena.actor}, 500)",
                    after[spec.arena.music_event],
                )
                examined += 1
        self.assertEqual(12, examined)

    def test_combat_waits_for_source_wake_and_completion_guards(self):
        for spec in route.SPECS.values():
            for donor in route.humanoid.DONORS.values():
                after = event_blocks(
                    route.patch(
                        spec, donor, self.destinations[spec.arena.key], self.common
                    )
                )
                health = after[spec.arena.health_bar_event]
                combat = health.index(
                    f"SetCharacterAIState({spec.arena.actor}, Enabled)"
                )
                self.assertLess(
                    health.index(f"WaitFor(EventFlag({spec.arena.start_flag}))"), combat
                )
                self.assertLess(health.index("L4:\n    EndIf(EventFlag"), combat)
                if donor.wake_animation is not None:
                    self.assertLess(
                        health.index(
                            f"ForceAnimationPlayback({spec.arena.actor}, {donor.wake_animation}"
                        ),
                        combat,
                    )
                for entity in spec.helpers:
                    self.assertLess(
                        health.index(f"ChangeCharacterEnableState({entity}, Disabled)"),
                        combat,
                    )
                bridge = after[spec.bridge]
                tail = bridge[
                    bridge.index(f"WaitFor(CharacterDead({spec.arena.actor})") :
                ]
                for entity in spec.terminal_helpers:
                    self.assertIn(
                        f"SetCharacterInvincibility({entity}, Disabled)", tail
                    )
                    self.assertIn(f"ForceCharacterDeath({entity}, false)", tail)

    def test_native_plans_cover_all_states_helpers_initialization_and_effects(self):
        recipes = chalice_recipes()
        examined = 0
        for spec in route.SPECS.values():
            for donor in route.humanoid.DONORS.values():
                plan = recipes[(spec.arena.key, donor.key)].native_plan(
                    self.slots, self.npcs, self.effects, "complex"
                )
                self.assertEqual(
                    set(spec.states),
                    {
                        r["destination_map"]
                        for r in plan["primary_init_source_bindings"]
                    },
                )
                self.assertEqual(
                    len(spec.states) * len(spec.helpers),
                    len(plan["boss_contract"]["retained_destination_helpers"]),
                )
                for row in plan["primary_init_source_bindings"]:
                    self.assertEqual(
                        donor.part_sha256, row["source_provenance"]["part_sha256"]
                    )
                    self.assertEqual(
                        route.humanoid.SOURCE_INITIALIZATION,
                        row["source_initialization"],
                    )
                self.assertGreater(len(plan["boss_ffx_merges"]), 0)
                validate_allocations(
                    BUNDLE, self.slots, [{"added_event_ids": [spec.bridge]}], plan
                )
                examined += 1
        self.assertEqual(12, examined)

    def test_missing_duplicate_or_wrong_destination_states_fail_closed(self):
        donor = next(iter(route.humanoid.DONORS.values()))
        for spec in route.SPECS.values():
            row = next(
                r
                for r in self.slots
                if r.map_name == spec.states[0] and r.entity_id == spec.arena.actor
            )
            for slots in ([r for r in self.slots if r is not row], [*self.slots, row]):
                with self.assertRaisesRegex(ValueError, "roster drift"):
                    route.native_plan(
                        spec, donor, slots, self.npcs, self.effects, "drift"
                    )

    def test_source_destination_and_bridge_drift_fail_closed(self):
        donor = next(iter(route.humanoid.DONORS.values()))
        for spec in route.SPECS.values():
            dest = self.destinations[spec.arena.key]
            with self.assertRaises(ValueError):
                route.patch(
                    spec,
                    donor,
                    dest,
                    self.common.replace("SetCharacterAIState", "UnknownInstruction"),
                )
            with self.assertRaises(ValueError):
                route.patch(
                    spec,
                    donor,
                    dest.replace("WaitFor", "UnknownInstruction"),
                    self.common,
                )
            with self.assertRaisesRegex(ValueError, "bridge ID collision"):
                route.patch(spec, donor, dest + f"\n// {spec.bridge}\n", self.common)
        with mock_patch.object(route, "PIN_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "actor pins changed"):
                route._pins()

    def test_each_new_route_can_complete_the_exact_good_family_pool(self):
        routes = good_boss_routes()
        examined = 0
        for spec in route.SPECS.values():
            for donor in route.humanoid.DONORS.values():
                forbidden = [
                    {(arena, key)}
                    for arena, key in routes
                    if arena == spec.arena.key and key != donor.key
                ]
                assignment = assign_good_bosses(
                    "forced-complex",
                    routes,
                    allow_self=False,
                    forbidden_combinations=forbidden,
                )
                self.assertEqual(donor.key, assignment.arena_to_donor[spec.arena.key])
                self.assertEqual(
                    set(GOOD_FAMILIES), set(assignment.arena_to_family.values())
                )
                examined += 1
        self.assertEqual(12, examined)

    def test_living_failures_cleanup_does_not_depend_on_maria_completion(self):
        spec = route.FAILURES
        donor = next(iter(route.humanoid.DONORS.values()))
        after = event_blocks(
            route.patch(spec, donor, self.destinations[spec.arena.key], self.common)
        )
        self.assertNotIn("EventFlag(13501800)", after[spec.arena.music_event])
        bridge = after[spec.bridge]
        self.assertIn("ClearSpEffect(10000, 8035)", bridge)
        for entity in range(3503850, 3503855):
            self.assertIn(f"DeleteMapSFX({entity}, false)", bridge)
