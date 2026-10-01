import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer import group_donors as group
from tools.bb_enemizer.boss_activation import guard_shuffled_activation, arena_entry_predicate
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.boss_contracts import ARENAS
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.build_boss_encounters import reviewed_compatibility, good_boss_routes, validate_allocations
from tools.bb_enemizer.good_boss_pool import GOOD_FAMILIES, assign_good_bosses


class GroupDonorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = {key: read_blob(group.lf.BUNDLE, "event/" + filename).decode("utf-8-sig")
                       for key, filename in group.DONOR_FILES.items()}
        cls.destinations = {arena.key: read_blob(group.lf.BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
                            for arena in ARENAS}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "slots.tsv"
            path.write_bytes(read_blob(group.lf.BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path)
        cls.npcs, cls.effects = load_params(group.lf.BUNDLE)

    def patched(self, arena, donor):
        return group.patch_group_donor(arena, donor, self.destinations[arena.key], self.sources[donor])

    def test_progression_and_unrelated_events_remain_exact(self):
        for arena in ARENAS:
            before = event_blocks(self.destinations[arena.key])
            allowed = {0, arena.activation_event, arena.health_bar_event,
                       arena.music_event, arena.lockcam_event, *group._retired(arena)}
            for donor in group.DONOR_FILES:
                if arena not in group.portable_group_arenas(donor):
                    continue
                with self.subTest(arena=arena.key, donor=donor):
                    after = event_blocks(self.patched(arena, donor))
                    for event in set(before) - allowed:
                        self.assertEqual(before[event], after[event])
                    self.assertEqual(before[arena.completion_event], after[arena.completion_event])

    def test_all_native_states_have_pinned_complete_rosters(self):
        for arena in ARENAS:
            for donor, helpers, regions, generators in (
                    ("shadows-of-yharnam", 10, 12, 3), ("living-failures", 5, 5, 4)):
                if arena not in group.portable_group_arenas(donor):
                    continue
                with self.subTest(arena=arena.key, donor=donor):
                    plan = group.native_plan_group_donor(arena, donor, self.slots, self.npcs, self.effects, "group")
                    self.assertEqual(arena.destination_count, len(plan["swaps"][0]["destination_keys"]))
                    for field, count in (("boss_actor_additions", helpers), ("boss_region_additions", regions),
                                         ("boss_generator_additions", generators), ("primary_init_source_bindings", 1)):
                        self.assertEqual(count * arena.destination_count, len(plan[field]))
                    for row in plan["boss_region_additions"]:
                        self.assertEqual(group.DESTINATION_PART_PINS[(row["destination_map"], arena.actor)],
                                         row["destination_anchor_provenance"]["part_sha256"])
                    after = event_blocks(self.patched(arena, donor))
                    before = event_blocks(self.destinations[arena.key])
                    validate_allocations(group.lf.BUNDLE, self.slots,
                                         [{"added_event_ids": sorted(set(after) - set(before))}], plan)
                    parents = plan["boss_actor_scaling_requirements"]
                    self.assertEqual(len(plan["boss_actor_additions"]), len(parents))
                    self.assertEqual({plan["swaps"][0]["logical_key"]}, {row["parent_logical_key"] for row in parents})
                    if donor == "living-failures":
                        self.assertEqual("frpg_sfxbnd_" + arena.map_prefix[:3] + ".ffxbnd.dcx",
                                         plan["boss_ffx_merges"][0]["destination_file"])

    def test_source_and_destination_drift_fail_closed(self):
        arena = ARENAS[0]
        for donor in group.DONOR_FILES:
            with self.assertRaises(ValueError):
                group.patch_group_donor(arena, donor, self.destinations[arena.key],
                                       self.sources[donor].replace("SetCharacterAIState", "SetCharacterGravity"))
            with self.assertRaises(ValueError):
                group.patch_group_donor(arena, donor,
                                       self.destinations[arena.key].replace("CreatePlaylog(", "CreatePlaylog(999, "),
                                       self.sources[donor])
        with self.assertRaises(ValueError):
            group.native_plan_group_donor(arena, "living-failures", self.slots[1:1], self.npcs, self.effects, "group")
        with self.assertRaises(ValueError):
            group.patch_group_donor(replace(arena, key="unknown"), "living-failures",
                                   self.destinations[arena.key], self.sources["living-failures"])
        for unsupported in (ARENAS[1], ARENAS[2]):
            with self.assertRaisesRegex(ValueError, "unsupported group donor route"):
                self.patched(unsupported, "living-failures")

    def test_constructor_keeps_authored_initializer_slots(self):
        for arena in ARENAS:
            for donor, counts in group.INITIALIZER_COUNTS.items():
                if arena not in group.portable_group_arenas(donor):
                    continue
                constructor = event_blocks(self.patched(arena, donor))[0]
                mapping = group._mapping(arena, donor)
                source = event_blocks(self.sources[donor])[0]
                for event, count in counts.items():
                    for row in group.shadows._initializer_rows(source, event, count, mapping):
                        self.assertEqual(1, constructor.count(row))

    def test_referred_health_body_stays_enabled_and_cleanup_clears_player_effect(self):
        ids = group.lf.DEFAULT_IDS
        for arena in group.portable_group_arenas("living-failures"):
            blocks = event_blocks(self.patched(arena, "living-failures"))
            health = blocks[arena.health_bar_event]
            self.assertIn(f"CreateReferredDamagePair({arena.actor}, {ids.proxy_entity});", health)
            self.assertNotIn(f"ChangeCharacterEnableState({ids.proxy_entity}, Disabled)", health)
            cleanup = blocks[ids.lifecycle_cleanup]
            self.assertIn("ClearSpEffect(10000, 8035);", cleanup)
            for entity in group.lf.SFX_ENTITY_IDS:
                self.assertIn(f"DeleteMapSFX({entity}, true);", cleanup)

    def test_shadow_terminal_requires_all_three_and_helpers_wait_for_entry(self):
        ids = group.shadows.DEFAULT_IDS
        for arena in ARENAS:
            blocks = event_blocks(self.patched(arena, "shadows-of-yharnam"))
            self.assertIn("CharacterDead(981310) && CharacterDead(981300) && CharacterDead(981301)", blocks[ids.bridge])
            for event in ids.event_map().values():
                self.assertIn(f"WaitFor(EventFlag({arena.health_bar_event}) || EventFlag({arena.completion_event}));", blocks[event])
            bounded = guard_shuffled_activation(arena, self.destinations[arena.key], self.patched(arena, "shadows-of-yharnam"))
            self.assertIn(arena_entry_predicate(arena.key), bounded)

    def test_new_routes_reach_both_pools_without_excluded_good_donors(self):
        graph, routes = reviewed_compatibility(), good_boss_routes()
        for arena in ARENAS:
            self.assertEqual(arena in group.portable_group_arenas("living-failures"),
                             "living-failures" in graph[arena.key])
            self.assertIn((arena.key, "shadows-of-yharnam"), routes)
        for arena in ARENAS:
            forbidden = [{(destination, donor)} for destination, donor in routes
                         if donor == "shadows-of-yharnam" and destination != arena.key]
            assignment = assign_good_bosses("forced-shadow-route", routes, allow_self=False,
                                            forbidden_combinations=forbidden)
            self.assertEqual(set(GOOD_FAMILIES), set(assignment.arena_to_family.values()))
            self.assertFalse({"living-failures", "witch-of-hemwick", "rom"} & set(assignment.arena_to_donor.values()))
            self.assertEqual("shadows-of-yharnam", assignment.arena_to_donor[arena.key])
