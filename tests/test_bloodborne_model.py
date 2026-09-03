import csv
import unittest
from collections import Counter
from itertools import combinations
from pathlib import Path

from worlds.bloodborne.data import (
    ALTERNATE_GAOL_LOCATION_KEYS,
    BASE_GAME_WEAPON_KEYS,
    DLC_ENTRANCE_NAMES,
    DLC_ITEM_KEYS,
    DLC_LOCATION_KEYS,
    DLC_REGIONS,
    GOODS_VARIETY_KEYS,
    SLICE_ITEM_KEYS,
    UNCANNY_ITEM_KEYS,
    UNCANNY_WEAPONS,
    MODEL,
)
from worlds.bloodborne.model import ItemKind, Rule
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS
from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS
from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS
from worlds.bloodborne import (
    ALL_NETWORK_LOCATIONS,
    FILLER_ITEM_NAME,
    FILLER_SHED_TIER,
    FILLER_WEIGHTS,
    FULL_POOL_ITEM_KEYS,
    GOAL_LOCATION_KEY,
    GOAL_LOCATION_KEYS,
    ITEM_ID_BY_KEY,
    ITEM_NAME_TO_ID,
    LOCATION_ID_BY_KEY,
    LOCATION_NAME_TO_ID,
    NETWORK_LOCATIONS,
    SHUFFLABLE_ITEMS,
    build_item_pool_names,
    build_runtime_slot_data,
    build_shop_gate_permutation,
    build_starting_weapon_choices,
    build_weapon_requirement_families,
    _weighted_filler,
)

ROOT = Path(__file__).resolve().parents[1]

try:
    import Options  # noqa: F401  (the world's option classes need Archipelago)
    from worlds.bloodborne import BloodborneWorld  # noqa: F401
    AP_AVAILABLE = True
except ImportError:                      # pragma: no cover - environment dependent
    AP_AVAILABLE = False



def seeded_locations():
    from worlds.bloodborne import NETWORK_LOCATIONS
    # Default YAML leaves the progression-changing Gaol route disabled.
    seeded = {n.key for n in NETWORK_LOCATIONS} - ALTERNATE_GAOL_LOCATION_KEYS
    return [location for location in MODEL.locations if location.key in seeded]


def slice_reachable(held: set[str], *, locations=None) -> set[str]:
    """Fixed point over seeded regions and the events their locations grant.

    Archipelago-free on purpose: the property is a property of the model, and a
    test that needed a checkout to state it would not run in the AP-free tier
    where most of the suite lives.
    """
    from worlds.bloodborne.data import SLICE_ENTRANCES

    locations = seeded_locations() if locations is None else locations
    owned = set(held)
    while True:
        regions = {"Menu"}
        grown = True
        while grown:
            grown = False
            for entrance in SLICE_ENTRANCES:
                if (entrance.source in regions and entrance.target not in regions
                        and entrance.rule.allows(owned)):
                    regions.add(entrance.target)
                    grown = True
        open_keys = {
            location.key for location in locations
            if location.region in regions and location.rule.allows(owned)
        }
        events = {location.locked_item for location in locations
                  if location.key in open_keys and location.locked_item}
        if events <= owned:
            return open_keys
        owned |= events


class BloodborneModelTests(unittest.TestCase):
    def test_category8_awards_cover_the_reviewed_fixed_catalog(self):
        reviewed = {
            row.item_lot_id: row.item_id
            for row in FIXED_LOCATIONS if row.item_category == 8
        }
        self.assertEqual(58, len(reviewed))
        self.assertEqual(
            reviewed,
            {row.source_lot_id: row.gemgen_id for row in CATEGORY8_AWARDS},
        )

    def test_category8_runtime_ids_and_ack_flags_are_unique(self):
        self.assertEqual(58, len(CATEGORY8_AWARDS))
        for field in ("item_key", "display_name", "token_goods_id",
                      "item_lot_id", "ack_flag", "source_lot_id"):
            values = [getattr(row, field) for row in CATEGORY8_AWARDS]
            self.assertEqual(len(values), len(set(values)), field)
        # 12401000 is vanilla-owned (event_flag_references.tsv); the AP bridge
        # deliberately stays in the audited-empty 12400900..12400999 window.
        ack_flags = {row.ack_flag for row in CATEGORY8_AWARDS}
        self.assertGreaterEqual(min(ack_flags), 12_400_900)
        self.assertLessEqual(max(ack_flags), 12_400_999)
        self.assertNotIn(12_401_000, ack_flags)

    def test_category8_duplicate_recipes_remain_distinct_items(self):
        duplicate = [row for row in CATEGORY8_AWARDS if row.gemgen_id == 126_000]
        self.assertEqual(2, len(duplicate))
        self.assertEqual(2, len({row.item_key for row in duplicate}))
        self.assertEqual(2, len({row.source_lot_id for row in duplicate}))

    def test_model_references_are_valid(self):
        errors = MODEL.validate()
        self.assertFalse(errors, "invalid model references: " + "; ".join(errors))

    def test_rule_dnf(self):
        rule = Rule.any(("a", "b"), ("c",))
        self.assertTrue(rule.allows({"a", "b"}))
        self.assertTrue(rule.allows({"c"}))
        self.assertFalse(rule.allows({"a"}))

    def test_runtime_item_bindings_cover_shufflable_items(self):
        expected = {item.key for item in SHUFFLABLE_ITEMS}
        self.assertTrue(expected <= set(ITEM_BINDINGS))

    def test_fixed_pickup_flags_cover_randomized_pickups(self):
        expected = {location.key for location in NETWORK_LOCATIONS}
        self.assertTrue(expected <= set(LOCATION_BINDINGS))
        self.assertTrue(all(LOCATION_BINDINGS[key].event_flag for key in expected))

    def test_eye_gift_checks_event_completion_without_reusing_suppressed_lot_flag(self):
        binding = LOCATION_BINDINGS["pickup_eye_of_blood_drunk_hunter"]
        self.assertEqual(12101028, binding.event_flag)
        self.assertEqual(50000100, binding.item_lot_flag)
        self.assertEqual(10040, binding.item_lot_id)

    def test_slice_contains_rom_route_and_queue_jumped_frontier(self):
        # Slice 5 adds the Woods catalog, both clinic backyard rows and their
        # scripted Summons check, plus Shadows and Rom. The White Messenger Ribbon (a
        # post-Rom quest reward whose region IS in the slice), and the NG+-only
        # Bold Hunter's Mark corpse, lot 2410295 (#220).
        # 2026-09-03: the 22 fixed Caryll rune rows joined the seeded pool
        # once rune delivery was confirmed live (#214).
        self.assertEqual(668, len(NETWORK_LOCATIONS))
        by_region = Counter(location.region for location in NETWORK_LOCATIONS)
        self.assertEqual(
            dict(by_region),
            {"Central Yharnam": 47, "Cathedral Ward": 64,
             "Old Yharnam": 56, "Grand Cathedral": 2,
             "Hemwick Charnel Lane": 34, "Castle Cainhurst": 29,
             "Forbidden Woods": 81, "Iosefka's Clinic": 3, "Byrgenwerth": 1,
             "Moonside Lake": 1,
            "Yahar'gul": 51, "Lecture Building 1F": 9,
             "Lecture Building 2F": 8, "Nightmare Frontier": 46,
             "Nightmare of Mensis": 57, "Hunter's Dream": 3,
             "Hunter's Nightmare": 68, "Underground Corpse Pile": 1,
             "Research Hall": 37, "Lumenwood Garden": 1,
             "Astral Clocktower": 1, "Fishing Hamlet": 41,
             "Nightmare Grand Cathedral": 1, "Healing Church Workshop": 4,
             "Upper Cathedral Ward": 21, "Graveyard of the Darkbeast": 1},
        )
        self.assertEqual(12411700, LOCATION_BINDINGS["boss_cleric_beast"].event_flag)
        self.assertEqual(12411800, LOCATION_BINDINGS["boss_father_gascoigne"].event_flag)
        self.assertEqual(12301800, LOCATION_BINDINGS["boss_blood_starved_beast"].event_flag)
        self.assertEqual(12201800, LOCATION_BINDINGS["boss_witch_of_hemwick"].event_flag)
        self.assertEqual(12501800, LOCATION_BINDINGS["boss_martyr_logarius"].event_flag)
        self.assertEqual(12421700, LOCATION_BINDINGS["boss_celestial_emissary"].event_flag)
        self.assertEqual(12421800, LOCATION_BINDINGS["boss_ebrietas"].event_flag)
        self.assertEqual(12701800, LOCATION_BINDINGS["boss_shadows_of_yharnam"].event_flag)
        self.assertEqual(13201800, LOCATION_BINDINGS["boss_rom"].event_flag)
        self.assertEqual(13301800, LOCATION_BINDINGS["boss_amygdala"].event_flag)
        self.assertEqual(12801800, LOCATION_BINDINGS["boss_the_one_reborn"].event_flag)
        self.assertEqual(12601850, LOCATION_BINDINGS["boss_micolash"].event_flag)
        self.assertEqual(12601800, LOCATION_BINDINGS["boss_mergos_wet_nurse"].event_flag)
        self.assertEqual(12101800, LOCATION_BINDINGS["boss_gehrman"].event_flag)
        self.assertEqual(12101850, LOCATION_BINDINGS["boss_moon_presence"].event_flag)
        self.assertEqual("boss_moon_presence", GOAL_LOCATION_KEY)
        self.assertEqual(
            LOCATION_ID_BY_KEY[GOAL_LOCATION_KEY],
            build_runtime_slot_data()["goal_location"],
        )
        for location_key in GOAL_LOCATION_KEYS.values():
            self.assertEqual(
                LOCATION_ID_BY_KEY[location_key],
                build_runtime_slot_data(goal_location_key=location_key)["goal_location"],
            )

    def test_slice_excludes_out_of_slice_fixed_rows(self):
        keys = {location.key for location in NETWORK_LOCATIONS}
        self.assertIn("fixed_central_yharnam_lot_2410140", keys)
        # Communion (+3) is a seeded check since rune delivery through the
        # event-award lane was confirmed live (#214).
        self.assertIn("fixed_central_yharnam_lot_2410640", keys)
        self.assertNotIn("fixed_white_messenger_ribbon", keys)
        # The post-Gascoigne strip pickups stay in as Cathedral Ward checks.
        self.assertIn("fixed_blood_gem_workshop_tool", keys)
        self.assertIn("fixed_central_yharnam_lot_2410920", keys)

    def test_full_pool_places_every_validated_item_once_then_filler(self):
        counts = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
        for name in (
            "Hunter Chief Emblem",
            "Cainhurst Summons",
            "Tonsil Stone",
            "Upper Cathedral Key",
            "Orphanage Key",
            "Eye of a Blood-drunk Hunter",
            "Eye Pendant",
            "Astral Clocktower Key",
            "Celestial Dial",
            "Laurence's Skull",
            "Saw Spear",
            "Augur of Ebrietas",
            "Oedon Tomb Key",
            "Sword Hunter Badge",
            "Old Hunter Badge",
            "Gold Pendant",
            "Saw Hunter Badge",
            "Crow Hunter Badge",
            "Powder Keg Hunter Badge",
            "Radiant Sword Hunter Badge",
            "Wheel Hunter Badge",
            "Cainhurst Badge",
            "Spark Hunter Badge",
            "Cosmic Eye Watcher Badge",
        ):
            self.assertEqual(counts[name], 1, name)
        # bb-archipelago#207 wave 1: the rest of the base-game trick weapons
        # and firearms are one-each members of the default pool too.
        for name in (
            "Saw Cleaver", "Hunter Axe", "Threaded Cane", "Kirkhammer",
            "Ludwig's Holy Blade", "Rifle Spear", "Stake Driver", "Beast Claw",
            "Blade of Mercy", "Burial Blade", "Chikage", "Reiterpallasch",
            "Tonitrus", "Logarius' Wheel",
            "Hunter Pistol", "Hunter Blunderbuss", "Repeating Pistol",
            "Ludwig's Rifle", "Cannon", "Evelyn", "Rosmarinus", "Flamesprayer",
            "Wooden Shield", "Hunter's Torch",
        ):
            self.assertEqual(counts[name], 1, name)
        # The exact weighted shares are restated here so an economy edit is a
        # visible pool change, not a silent one.
        self.assertEqual(counts["Blood Vial"], 24)
        self.assertEqual(counts["Quicksilver Bullets x3"], 6)
        self.assertEqual(counts["Blood Stone Shards x2"], 32)
        self.assertEqual(counts["Twin Blood Stone Shards x2"], 32)
        self.assertEqual(counts["Blood Stone Chunk"], 21)
        self.assertEqual(counts["Bold Hunter's Mark x2"], 21)
        for name in ("Pebbles x3", "Molotov Cocktails x2", "Throwing Knife x4",
                     "Fire Paper x2"):
            self.assertEqual(counts[name], 21, name)
        self.assertEqual(counts["Bolt Paper x2"], 21)
        self.assertEqual(counts["Bone Marrow Ash x3"], 21)
        for name in ("Poison Knife x3", "Antidote x2", "Sedatives x2",
                     "Blue Elixir", "Beast Blood Pellet", "Lead Elixir",
                     "Oil Urn x2", "Numbing Mist x2",
                     ):
            self.assertEqual(counts[name], 11, name)
        for name in ("Pungent Blood Cocktail x2", "Shaman Bone Blade",
                     "Madman's Knowledge"):
            self.assertEqual(counts[name], 11, name)
        self.assertEqual(counts["Great One's Wisdom"], 11)
        self.assertEqual(counts["Coldblood Dew (1)"], 0)
        self.assertEqual(counts["Coldblood Dew (2)"], 0)
        self.assertEqual(counts["Coldblood Dew (3)"], 0)
        self.assertEqual(counts["Thick Coldblood (4)"], 0)
        self.assertEqual(counts["Thick Coldblood (5)"], 0)
        self.assertEqual(counts["Thick Coldblood (6)"], 11)
        self.assertEqual(counts["Frenzied Coldblood (8)"], 10)
        self.assertEqual(counts["Kin Coldblood (11)"], 10)
        self.assertEqual(counts["Blood Rock"], 1)
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))

    def test_slice_pool_option_off_preserves_the_original_grant_shapes(self):
        """The grant shapes the first live sessions validated are unchanged.

        Slice 3 added the Hunter Chief Emblem to this pool because the plaza
        gate is emblem-only, and the Oedon Tomb Key joins it for the same
        reason: with the key shuffled, a pool without it cannot leave Central
        Yharnam. 364 - 4 one-off items = 360 filler slots over the slice's own
        five filler names.
        """
        counts = Counter(build_item_pool_names(SLICE_ITEM_KEYS))
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
        self.assertEqual(counts["Saw Spear"], 1)
        self.assertEqual(counts["Augur of Ebrietas"], 1)
        self.assertEqual(counts["Hunter Chief Emblem"], 1)
        self.assertEqual(counts["Oedon Tomb Key"], 1)
        for number in range(1, 5):
            self.assertEqual(counts[f"Third Umbilical Cord #{number}"], 1)
        for name in ("Sword Hunter Badge", "Old Hunter Badge", "Gold Pendant"):
            self.assertEqual(counts[name], 1)
        # The slice pool keeps its four validated filler types, so wave 1's
        # goods variety does not reach it: this pool is the canary set, not a
        # play experience. 484 - 4 one-each = 480 slots over five weighted names.
        self.assertEqual(counts["Blood Vial"], 233)
        self.assertEqual(counts["Quicksilver Bullets x3"], 150)
        self.assertEqual(counts["Blood Stone Shards x2"], 116)
        self.assertEqual(counts["Pebbles x3"], 78)
        self.assertEqual(counts["Molotov Cocktails x2"], 78)
        self.assertNotIn("Fire Paper x2", counts)  # control: goods stay out
        slot_data = build_runtime_slot_data(SLICE_ITEM_KEYS)
        self.assertEqual(len(slot_data["runtime_items"]), 18)  # seventeen slice items + Blood Vial

    def test_runtime_location_flags_are_specific_to_one_item_lot(self):
        """A short flag is valid; sharing one between lots is not."""
        with (ROOT / "research/joined/lot_items.tsv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        with (ROOT / "research/joined/fixed_treasure_lots.tsv").open(
                encoding="utf-8", newline="") as handle:
            placed_lots = {
                row["item_lot_id"] for row in csv.DictReader(handle, delimiter="\t")
                if row["item_lot_id"]
            }
        lots_by_flag = {}
        for row in rows:
            for flag in filter(None, row["all_acquisition_flags"].split(";")):
                lots_by_flag.setdefault(int(flag), set()).add(row["item_lot_id"])

        for location, binding in LOCATION_BINDINGS.items():
            if binding.item_lot_id is None:
                continue
            item_lot_flag = binding.item_lot_flag or binding.event_flag
            self.assertIn(item_lot_flag, lots_by_flag, location)
            lots = lots_by_flag[item_lot_flag]
            self.assertIn(str(binding.item_lot_id), lots, location)
            self.assertTrue(
                all(lot not in placed_lots for lot in lots - {str(binding.item_lot_id)}),
                f"{location}: acquisition flag is shared by another placed lot",
            )

        self.assertEqual({"3401810"}, lots_by_flag[9470])

    def test_runtime_location_provenance_matches_the_validation_census(self):
        """Evidence must describe the source row, not merely contain a plausible flag."""
        names_by_key = {location.key: location.name.rsplit(" - ", 1)[-1]
                        for location in MODEL.locations if not location.locked_item}
        with (ROOT / "research/validation/progression_items.tsv").open(
                encoding="utf-8", newline="") as handle:
            rows_by_name = {row["item_name"]: row for row in csv.DictReader(handle, delimiter="\t")}
        with (ROOT / "research/catalog/fixed_location_items.tsv").open(
                encoding="utf-8", newline="") as handle:
            catalog_items = list(csv.DictReader(handle, delimiter="\t"))
        with (ROOT / "research/catalog/fixed_location_catalog.tsv").open(
                encoding="utf-8", newline="") as handle:
            catalog_locations = {row["location_flag"]: row
                                 for row in csv.DictReader(handle, delimiter="\t")}

        for key, binding in LOCATION_BINDINGS.items():
            if binding.source_kind in ("boss_defeat", "interaction", "one_time_enemy"):
                # Flag-only checks: no item lot to trace; the evidence string
                # must carry the flag itself.
                self.assertIsNone(binding.item_lot_id)
                self.assertIn(str(binding.event_flag), binding.evidence)
                continue
            if binding.source_kind in ("script_award", "npc_or_enemy_award", "npc_award"):
                candidates = [
                    row for row in rows_by_name.values()
                    if (binding.item_lot_id is not None
                        and str(binding.item_lot_id) in row["item_lot_ids"].split(";"))
                    or (binding.item_lot_id is None
                        and str(binding.event_flag) in row["acquisition_flags"].split(";"))
                ]
                self.assertEqual(1, len(candidates), key)
                row = candidates[0]
                item_lot_flag = binding.item_lot_flag or binding.event_flag
                self.assertIn(str(item_lot_flag), row["acquisition_flags"], key)
                if binding.item_lot_id is not None:
                    self.assertIn(str(binding.item_lot_id), row["item_lot_ids"], key)
                    self.assertIn(binding.source_kind, row["observed_sources"].split(";"), key)
                    expected_ref = row["script_awards"]
                else:
                    expected_ref = binding.source_ref
            else:
                matches = [row for row in catalog_items
                           if row["location_flag"] == str(binding.event_flag)
                           and row["item_lot_id"] == str(binding.item_lot_id)
                           and row["category"] == str(binding.item_category)
                           and row["item_param_id"] == str(binding.item_id)]
                self.assertEqual(1, len(matches), key)
                expected_ref = catalog_locations[str(binding.event_flag)]["map_variants"]
            self.assertEqual(expected_ref, binding.source_ref, key)
            if binding.item_lot_id is not None:
                self.assertIn(str(binding.item_lot_id), binding.evidence, key)

    def test_progression_validation_covers_every_pool_item(self):
        from tools.validate_progression_items import EXPECTED
        validated_names = {name for name, _, _ in EXPECTED}
        pool_names = {
            item.name for item in MODEL.items
            if item.kind is ItemKind.PROGRESSION
        }
        self.assertEqual(set(), pool_names - validated_names)

    def test_hunter_chief_emblem_catalog_review_is_resolved(self):
        with (ROOT / "research/catalog/fixed_location_items.tsv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        emblem = next(row for row in rows if row["item_param_id"] == "4011")
        self.assertEqual("Hunter Chief Emblem", emblem["english_name"])
        self.assertEqual("0x40000FAB", emblem["normalized_runtime_id"])
        self.assertEqual("hunter_chief_emblem_validation", emblem["classification_reason"])

    def test_vertical_slice_ids_are_complete_and_disjoint(self):
        shufflable = {item.key for item in SHUFFLABLE_ITEMS}
        self.assertEqual(shufflable, set(ITEM_ID_BY_KEY))
        # Every model location has a permanent id (ids.tsv is append-only);
        # the datapackage map is restricted to what the slice seeds.
        self.assertTrue({location.key for location in NETWORK_LOCATIONS} <= set(LOCATION_ID_BY_KEY))
        self.assertEqual(
            {location.name for location in ALL_NETWORK_LOCATIONS},
            set(LOCATION_NAME_TO_ID),
        )
        self.assertEqual(len(ITEM_NAME_TO_ID), len(shufflable) + 1)  # Blood Vial filler
        self.assertFalse(set(ITEM_NAME_TO_ID.values()) & set(LOCATION_ID_BY_KEY.values()))

    def test_region_progression_graph_is_acyclic(self):
        edges = {}
        for entrance in MODEL.entrances:
            edges.setdefault(entrance.source, set()).add(entrance.target)
        visiting = set()
        visited = set()

        def visit(region):
            self.assertNotIn(region, visiting, f"progression cycle at {region}")
            if region in visited:
                return
            visiting.add(region)
            for target in edges.get(region, ()):
                visit(target)
            visiting.remove(region)
            visited.add(region)

        for region in MODEL.regions:
            visit(region)

    def test_the_seeded_slice_is_fully_reachable_by_either_cathedral_route(self):
        """Reachability, without needing an Archipelago checkout.

        Every seeded location must be reachable with the seeded pool. The
        emblem is a shortcut, not a Go-mode requirement: after Blood-starved
        Beast, the Workshop route reaches the same plaza.
        """
        from worlds.bloodborne.data import SLICE_ITEM_KEYS, SLICE_REGIONS

        locations = seeded_locations()
        reachable = slice_reachable

        # The Dream now contributes the two ending bosses.
        self.assertEqual(set(SLICE_REGIONS) - {"Menu"},
                         {l.region for l in locations})
        with_everything = reachable(set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS))
        self.assertEqual(with_everything, {l.key for l in locations})

        without_emblem = reachable(
            (set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)) - {"hunter_chief_emblem"})
        self.assertEqual(with_everything, without_emblem)

    def test_abandoned_workshop_checks_open_after_blood_starved_beast(self):
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        workshop_keys = {
            "treasure_old_hunter_bone",
            "treasure_doll_set_chest",
            "pickup_small_hair_ornament",
            "pickup_workshop_umbilical_cord",
        }
        locations = {location.key: location for location in seeded_locations()}
        self.assertTrue(workshop_keys <= set(locations), sorted(set(locations)))
        locked_workshop = {
            key: locations[key].locked_item
            for key in workshop_keys
            if locations[key].locked_item is not None
        }
        self.assertFalse(locked_workshop, locked_workshop)

        inventory = set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)
        without_beast = slice_reachable(
            inventory - {"event_blood_starved_beast_defeated"},
            locations=[location for location in locations.values()
                       if location.key != "boss_blood_starved_beast"],
        )
        self.assertTrue(workshop_keys.isdisjoint(without_beast), sorted(without_beast))
        with_beast = slice_reachable(inventory)
        self.assertTrue(workshop_keys <= with_beast, sorted(with_beast))

    def test_withholding_the_oedon_tomb_key_strands_the_seed_in_central_yharnam(self):
        """The point of shuffling the key: sphere 0 is a place, not the world.

        Before this, the Tomb of Oedon gate cost only Gascoigne's defeat event,
        which the seed grants itself from a Central Yharnam check -- so every
        seeded check was reachable from the start and the seed opened in
        go-mode. With the key shuffled, withholding it must leave exactly the
        Central Yharnam checks open, and nothing beyond them.
        """
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        locations = seeded_locations()
        everything = set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)
        with_everything = slice_reachable(everything)
        without_key = slice_reachable(everything - {"oedon_tomb_key"})

        # Sphere 0 is what a player can open holding nothing at all. Hunter's
        # Dream is a seeded region but seeds no check in this slice (its Eye
        # belongs to the post-Amelia chain), so sphere 0 is Central Yharnam.
        sphere_zero = slice_reachable(set())
        central_yharnam = {l.key for l in locations if l.region == "Central Yharnam"}
        self.assertTrue(central_yharnam)  # witness: the region really seeds checks
        self.assertEqual(sphere_zero, central_yharnam)
        self.assertEqual(without_key, central_yharnam)

        gated = with_everything - without_key
        self.assertEqual(gated, {l.key for l in locations
                                 if l.region != "Central Yharnam"})
        # Most of the 228 checks sit behind the key, so it remains the slice's
        # seed that could not place it reachably would be mostly unplayable.
        self.assertEqual(len(gated), len(locations) - len(central_yharnam))
        self.assertGreater(len(gated), len(locations) // 2)

    def test_any_three_of_four_cord_pieces_are_go_mode_for_moon_presence(self):
        everything = set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)
        cords = {
            "third_umbilical_cord_1",
            "third_umbilical_cord_2",
            "third_umbilical_cord_3",
            "third_umbilical_cord_4",
        }
        without_cords = everything - cords
        for held in combinations(cords, 3):
            reachable = slice_reachable(without_cords | set(held))
            self.assertIn("boss_gehrman", reachable, held)
            self.assertIn("boss_moon_presence", reachable, held)
        for held in combinations(cords, 2):
            reachable = slice_reachable(without_cords | set(held))
            self.assertIn("boss_gehrman", reachable, held)
            self.assertNotIn("boss_moon_presence", reachable, held)

    def test_the_ng_plus_only_lot_is_not_a_check_but_its_partner_is(self):
        """#220: lot 2410295 only spawns on NG+, so it cannot be a check.

        Its param name is `\u5b9d\u6b7b\u4f5319 \u5f8c\u534a\uff082\u5468\u76ee\u4ee5\u964d\uff09` -- "treasure corpse 19, second
        playthrough onward". It is the substitution partner of the Saw Hunter
        Badge corpse (2410290) at the same MSB coordinates: in a first
        playthrough only 2410290 spawns, so a check on flag 52410295 was
        unobtainable filler in every seed a player could actually reach.
        """
        # Both names are read from the name table rather than spelled out, so
        # a rename (#222 gave most names a landmark hint) cannot turn this
        # witness red without changing what it is actually asserting.
        from worlds.bloodborne.location_names import location_name

        keys = {location.key for location in NETWORK_LOCATIONS}
        self.assertNotIn("fixed_central_yharnam_lot_2410295", keys)
        self.assertNotIn(location_name(52410295), LOCATION_NAME_TO_ID)
        # Control: the NG(1) half of the same substitution pair is untouched.
        # Removing both would silently delete a real check.
        self.assertIn("fixed_saw_hunter_badge", keys)
        self.assertIn(location_name(52410290), LOCATION_NAME_TO_ID)

    def test_the_unseeded_ng_plus_lot_keeps_its_permanent_network_id(self):
        """Ids are append-only: unseeding a check must never free its id.

        The row stays in fixed_locations.tsv (its vanilla award is still
        suppressed for NG+ players, see #220), so the key keeps its id and the
        id can never be handed to a future location.
        """
        self.assertIn("fixed_central_yharnam_lot_2410295", LOCATION_ID_BY_KEY)
        self.assertEqual(0xBB1036,
                         LOCATION_ID_BY_KEY["fixed_central_yharnam_lot_2410295"])

    def test_the_goal_requires_the_oedon_and_lunarium_keys_but_not_the_emblem(self):
        """BSB opens the Workshop route, making the emblem an optional shortcut."""
        from worlds.bloodborne import GOAL_LOCATION_KEY
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        everything = set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)
        self.assertIn(GOAL_LOCATION_KEY, slice_reachable(everything))
        self.assertNotIn(GOAL_LOCATION_KEY,
                         slice_reachable(everything - {"oedon_tomb_key"}))
        self.assertNotIn(GOAL_LOCATION_KEY,
                         slice_reachable(everything - {"lunarium_key"}))
        self.assertNotIn(GOAL_LOCATION_KEY,
                         slice_reachable(everything - {"forbidden_woods_password"}))
        self.assertIn(GOAL_LOCATION_KEY,
                      slice_reachable(everything - {"hunter_chief_emblem"}))

    def test_the_progression_keys_are_in_every_pool_the_world_can_build(self):
        """A progression item the pool may omit is a generation failure waiting."""
        from worlds.bloodborne import build_item_pool_names
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        for keys in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            self.assertIn("oedon_tomb_key", keys)
            self.assertIn("Oedon Tomb Key", build_item_pool_names(keys))
            self.assertIn("lunarium_key", keys)
            self.assertIn("Lunarium Key", build_item_pool_names(keys))
            self.assertIn("forbidden_woods_password", keys)
            self.assertIn('"Fear the Old Blood"', build_item_pool_names(keys))

    def test_every_playable_region_contributes_a_location(self):
        populated = {location.region for location in MODEL.locations}
        self.assertEqual({"Menu", "Hypogean Gaol"}, set(MODEL.regions) - populated)


class UncannyWeaponPoolTests(unittest.TestCase):
    """bb-archipelago#205: opt-in Uncanny variants displace filler, never checks."""

    def _keys_with_uncanny(self, base):
        return frozenset(base) | frozenset(
            uncanny for weapon, uncanny in UNCANNY_WEAPONS.items() if weapon in base)

    def test_the_default_pool_carries_no_uncanny_name(self):
        """The control. With the option off, not one variant reaches the pool.

        Wave 1 (#207) deliberately changed what the DEFAULT pool contains --
        base weapons and goods variety are pool improvements, not options -- so
        this control no longer asserts a byte-identical pre-#205 pool. What it
        still asserts is the option's whole contract: the Uncanny keys are
        unreachable without it.
        """
        for keys in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            pool = build_item_pool_names(keys)
            self.assertEqual(len(pool), len(NETWORK_LOCATIONS))
            self.assertIn("Saw Spear", pool)          # witness: a real pool
            self.assertFalse([name for name in pool if "Uncanny" in name])
        counts = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        self.assertEqual(counts["Saw Spear"], 1)
        self.assertFalse(FULL_POOL_ITEM_KEYS & UNCANNY_ITEM_KEYS)

    def test_one_uncanny_per_pooled_weapon_and_the_seed_size_identity_holds(self):
        for base in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            with self.subTest(pool=len(base)):
                counts = Counter(build_item_pool_names(self._keys_with_uncanny(base)))
                self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
                placed = {name for name in counts if "Uncanny" in name}
                self.assertIn("Uncanny Saw Spear", placed)
                for name in placed:
                    self.assertEqual(counts[name], 1, name)
                # every weapon in the pool contributed exactly one variant
                self.assertEqual(len(placed),
                                 len([w for w in UNCANNY_WEAPONS if w in base]))

    def test_each_uncanny_copy_displaces_exactly_one_filler_item(self):
        before = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        after = Counter(build_item_pool_names(self._keys_with_uncanny(FULL_POOL_ITEM_KEYS)))
        added = sum(count for name, count in after.items() if "Uncanny" in name)
        self.assertEqual(added, len(UNCANNY_WEAPONS))
        filler_names = {item.name for item in SHUFFLABLE_ITEMS
                        if item.kind is ItemKind.FILLER} | {"Blood Vial"}
        lost = sum(before[name] - after[name] for name in filler_names)
        self.assertEqual(lost, added)
        # nothing but filler moved
        for name in set(before) | set(after):
            if name in filler_names or "Uncanny" in name:
                continue
            self.assertEqual(before[name], after[name], name)

    def test_a_pool_with_no_filler_slack_sheds_uncanny_copies_deterministically(self):
        """A small seed must degrade, not overflow: the tail is dropped in order."""
        import worlds.bloodborne as world

        keys = self._keys_with_uncanny(FULL_POOL_ITEM_KEYS)
        one_each = len([item for item in SHUFFLABLE_ITEMS
                        if item.key in keys and item.kind is not ItemKind.FILLER
                        and not item.key.startswith("uncanny_")])
        tiny = NETWORK_LOCATIONS[:one_each]
        original = world.NETWORK_LOCATIONS
        world.NETWORK_LOCATIONS = tiny
        try:
            pool = build_item_pool_names(keys)
            again = build_item_pool_names(keys)
        finally:
            world.NETWORK_LOCATIONS = original
        self.assertEqual(len(pool), len(tiny))
        self.assertEqual(pool, again)  # deterministic, not draw-dependent
        self.assertIn("Saw Spear", pool)              # witness: a real pool
        self.assertFalse([name for name in pool if "Uncanny" in name])
        self.assertIn("Oedon Tomb Key", pool)  # progression survives the shed

    def test_uncanny_variants_are_useful_and_leave_their_base_alone(self):
        by_key = {item.key: item for item in MODEL.items}
        self.assertTrue(UNCANNY_WEAPONS)  # witness: the mapping is not empty
        for weapon, uncanny in UNCANNY_WEAPONS.items():
            self.assertEqual(by_key[uncanny].kind, ItemKind.USEFUL, uncanny)
            self.assertEqual(by_key[weapon].kind, ItemKind.USEFUL, weapon)
            self.assertEqual(ITEM_BINDINGS[uncanny].item_category, 0, uncanny)
            self.assertEqual(ITEM_BINDINGS[uncanny].item_category,
                             ITEM_BINDINGS[weapon].item_category)

    def test_the_uncanny_descriptor_is_the_base_weapon_plus_the_uncanny_offset(self):
        """The offset is the whole id claim, so it is asserted, not commented."""
        for weapon, uncanny in UNCANNY_WEAPONS.items():
            base = ITEM_BINDINGS[weapon]
            variant = ITEM_BINDINGS[uncanny]
            self.assertEqual(variant.normalized_item_id - base.normalized_item_id, 10000)
            self.assertEqual(variant.raw_descriptor,
                             variant.normalized_item_id | 0x80000000)
            self.assertEqual(variant.descriptor_evidence, "param_id_inferred")

    def test_an_uncanny_row_carries_slot_data_only_when_the_option_places_it(self):
        with_uncanny = build_runtime_slot_data(
            self._keys_with_uncanny(FULL_POOL_ITEM_KEYS))["runtime_items"]
        without = build_runtime_slot_data(FULL_POOL_ITEM_KEYS)["runtime_items"]
        uncanny_id = str(ITEM_ID_BY_KEY["uncanny_saw_spear"])
        self.assertIn(uncanny_id, with_uncanny)
        self.assertNotIn(uncanny_id, without)
        self.assertEqual(len(with_uncanny), len(without) + len(UNCANNY_WEAPONS))
        self.assertEqual(with_uncanny[uncanny_id]["item_category"], 0)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class UncannyOptionWiringTests(unittest.TestCase):
    """The option is the only door into the Uncanny keys."""

    class _Options:
        def __init__(self, full_item_pool, uncanny_weapons, include_dlc=1):
            self.full_item_pool = full_item_pool
            self.uncanny_weapons = uncanny_weapons
            self.include_dlc = include_dlc
            self.randomize_armor = 0

    def _keys(self, *, full, uncanny):
        from worlds.bloodborne import BloodborneWorld

        world = BloodborneWorld.__new__(BloodborneWorld)
        world.options = self._Options(full, uncanny)
        return BloodborneWorld._pool_item_keys(world)

    def test_the_option_off_yields_todays_keys_exactly(self):
        self.assertEqual(self._keys(full=1, uncanny=0), FULL_POOL_ITEM_KEYS)
        self.assertEqual(self._keys(full=0, uncanny=0), SLICE_ITEM_KEYS)

    def test_the_option_on_adds_exactly_the_variants_of_pooled_weapons(self):
        for full, base in ((1, FULL_POOL_ITEM_KEYS), (0, SLICE_ITEM_KEYS)):
            keys = self._keys(full=full, uncanny=1)
            self.assertEqual(keys - base, frozenset(
                uncanny for weapon, uncanny in UNCANNY_WEAPONS.items() if weapon in base))
            self.assertIn("uncanny_saw_spear", keys)

    def test_the_option_is_a_plain_opt_in_toggle(self):
        from worlds.bloodborne import BloodborneOptions

        option = BloodborneOptions.type_hints["uncanny_weapons"]
        self.assertEqual(option.default, 0)
        self.assertEqual(option.display_name, "Uncanny Weapon Variants")
        self.assertIn("Uncanny", option.__doc__)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class DlcOptionWiringTests(unittest.TestCase):
    class _Options:
        full_item_pool = 1
        uncanny_weapons = 0
        randomize_armor = 0

        def __init__(self, include_dlc):
            self.include_dlc = include_dlc

    def _world(self, include_dlc):
        from worlds.bloodborne import BloodborneWorld

        world = BloodborneWorld.__new__(BloodborneWorld)
        world.options = self._Options(include_dlc)
        return world

    def test_the_dlc_option_defaults_off(self):
        from worlds.bloodborne import BloodborneOptions

        option = BloodborneOptions.type_hints["include_dlc"]
        self.assertEqual(0, option.default)
        self.assertEqual("Include The Old Hunters DLC", option.display_name)

    def test_disabling_dlc_removes_its_items_and_locations_together(self):
        off = self._world(0)
        on = self._world(1)
        active_dlc_items = DLC_ITEM_KEYS & on._pool_item_keys()
        self.assertEqual(active_dlc_items, on._pool_item_keys() - off._pool_item_keys())
        self.assertEqual(
            DLC_LOCATION_KEYS,
            {location.key for location in on._active_locations()}
            - {location.key for location in off._active_locations()},
        )

    def test_the_declared_dlc_boundary_is_complete(self):
        from worlds.bloodborne.data import SLICE_ENTRANCES

        self.assertEqual(
            DLC_ENTRANCE_NAMES,
            {entrance.name for entrance in SLICE_ENTRANCES
             if entrance.source in DLC_REGIONS or entrance.target in DLC_REGIONS},
        )


class StartingWeaponChoiceTests(unittest.TestCase):
    def test_choices_are_deterministic_unique_and_independent(self):
        first = build_starting_weapon_choices("AP_TEST:1")
        self.assertEqual(first, build_starting_weapon_choices("AP_TEST:1"))
        self.assertEqual(3, len(first["right_hand"]))
        self.assertEqual(3, len(set(first["right_hand"])))
        self.assertEqual(2, len(first["left_hand"]))
        self.assertEqual(2, len(set(first["left_hand"])))

        expected = {
            hand: {
                binding.normalized_item_id for key, binding in ITEM_BINDINGS.items()
                if key not in UNCANNY_ITEM_KEYS and binding.feed_effect == f"{hand}_weapon"
            }
            for hand in ("right_hand", "left_hand")
        }
        for hand, values in first.items():
            self.assertLessEqual(set(values), expected[hand])

    def test_option_defaults_on(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions
        option = BloodborneOptions.type_hints["randomize_starting_weapons"]
        self.assertEqual(1, option.default)
        self.assertEqual("Randomize Starting Weapons", option.display_name)

    def test_requirement_families_cover_base_and_optionally_uncanny_weapons(self):
        base = set(build_weapon_requirement_families(False))
        with_uncanny = set(build_weapon_requirement_families(True))
        uncanny = {
            ITEM_BINDINGS[key].normalized_item_id for key in UNCANNY_ITEM_KEYS
            if ITEM_BINDINGS[key].feed_effect in {"right_hand_weapon", "left_hand_weapon"}
        }
        self.assertEqual(uncanny, with_uncanny - base)
        self.assertTrue(base)

    def test_remove_requirements_option_defaults_on(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions
        option = BloodborneOptions.type_hints["remove_weapon_requirements"]
        self.assertEqual(1, option.default)
        self.assertEqual("Remove Weapon Requirements", option.display_name)

    def test_shop_gate_permutation_is_deterministic_and_bijective(self):
        first = build_shop_gate_permutation("AP_TEST:1")
        self.assertEqual(first, build_shop_gate_permutation("AP_TEST:1"))
        expected = set(range(12101000, 12101010))
        self.assertEqual({str(value) for value in expected}, set(first))
        self.assertEqual(expected, set(first.values()))

    def test_shop_randomization_is_explicitly_opt_in(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions
        option = BloodborneOptions.type_hints["randomize_shops"]
        self.assertEqual(0, option.default)
        self.assertEqual("Randomize Bath Messenger Shops", option.display_name)

    def test_death_link_is_explicitly_opt_in_and_receive_only(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions

        option = BloodborneOptions.type_hints["death_link"]
        self.assertEqual(0, option.default)
        self.assertEqual("DeathLink (Receive Only)", option.display_name)

    def test_death_link_amnesty_is_independent_and_defaults_off(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions

        option = BloodborneOptions.type_hints["death_link_amnesty"]
        self.assertEqual(0, option.default)
        self.assertEqual(0, option.range_start)
        self.assertGreater(option.range_end, 1)
        self.assertIn("Local Deaths Forgiven", option.display_name)

    def test_goal_option_tracks_the_three_endings(self):
        if not AP_AVAILABLE:
            self.skipTest("requires Archipelago options")
        from worlds.bloodborne import BloodborneOptions

        option = BloodborneOptions.type_hints["goal"]
        self.assertEqual(2, option.default)
        self.assertEqual(
            {
                "submit_to_gehrman": 0,
                "refuse_gehrman": 1,
                "moon_presence": 2,
            },
            option.options,
        )
        self.assertEqual(
            "Submit to Gehrman (Mergo's Wet Nurse)", option.get_option_name(0)
        )
        self.assertEqual("Refuse Gehrman (Gehrman)", option.get_option_name(1))
        self.assertEqual(
            "Moon Presence (Three Umbilical Cords)", option.get_option_name(2)
        )
        self.assertEqual(
            {
                0: "boss_mergos_wet_nurse",
                1: "boss_gehrman",
                2: "boss_moon_presence",
            },
            GOAL_LOCATION_KEYS,
        )


class Wave1WeaponPoolTests(unittest.TestCase):
    """bb-archipelago#207 wave 1, weapon half: the base-game catalog joins the pool."""

    # The list is the claim, so it is written out rather than derived from the
    # code under test. Ids are EquipParamWeapon rows, agreed by Smithbox's BB
    # row names and the Bloodborne save editor's weapons.json.
    TRICK_WEAPONS = {
        "chikage": (2000000, "Chikage"),
        "blade_of_mercy": (4000000, "Blade of Mercy"),
        "hunter_axe": (5000000, "Hunter Axe"),
        "burial_blade": (5100000, "Burial Blade"),
        "saw_cleaver": (7000000, "Saw Cleaver"),
        "saw_spear": (7100000, "Saw Spear"),
        "kirkhammer": (8000000, "Kirkhammer"),
        "ludwigs_holy_blade": (8100000, "Ludwig's Holy Blade"),
        "beast_claw": (9000000, "Beast Claw"),
        "rifle_spear": (10000000, "Rifle Spear"),
        "reiterpallasch": (10100000, "Reiterpallasch"),
        "stake_driver": (11000000, "Stake Driver"),
        "logarius_wheel": (12000000, "Logarius' Wheel"),
        "tonitrus": (13000000, "Tonitrus"),
        "threaded_cane": (22000000, "Threaded Cane"),
    }
    FIREARMS = {
        "hunter_blunderbuss": (6000000, "Hunter Blunderbuss"),
        "ludwigs_rifle": (6100000, "Ludwig's Rifle"),
        "hunter_pistol": (14000000, "Hunter Pistol"),
        "repeating_pistol": (14200000, "Repeating Pistol"),
        "cannon": (15000000, "Cannon"),
        "evelyn": (14100000, "Evelyn"),
        "rosmarinus": (18000000, "Rosmarinus"),
        "flamesprayer": (18100000, "Flamesprayer"),
    }
    LEFT_HAND_TOOLS = {
        "wooden_shield": (19000000, "Wooden Shield"),
        "hunters_torch": (20000000, "Hunter's Torch"),
    }

    def test_every_base_game_weapon_is_in_the_default_pool_as_useful(self):
        by_key = {item.key: item for item in MODEL.items}
        expected = set(self.TRICK_WEAPONS) | set(self.FIREARMS) | set(self.LEFT_HAND_TOOLS)
        self.assertEqual(BASE_GAME_WEAPON_KEYS, frozenset(expected))
        pool = set(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        for key, (_, name) in {**self.TRICK_WEAPONS, **self.FIREARMS,
                               **self.LEFT_HAND_TOOLS}.items():
            self.assertIn(key, FULL_POOL_ITEM_KEYS, key)
            self.assertEqual(by_key[key].name, name, key)
            self.assertEqual(by_key[key].kind, ItemKind.USEFUL, key)
            self.assertIn(name, pool, name)

    def test_each_weapon_descriptor_is_its_param_row_under_the_category_0_formula(self):
        for key, (param_id, _) in {**self.TRICK_WEAPONS, **self.FIREARMS,
                                   **self.LEFT_HAND_TOOLS}.items():
            binding = ITEM_BINDINGS[key]
            self.assertEqual(binding.normalized_item_id, param_id, key)
            self.assertEqual(binding.raw_descriptor, param_id | 0x80000000, key)
            self.assertEqual(binding.item_category, 0, key)
            self.assertEqual(binding.reinforcement_level, 0, key)
        for key in self.TRICK_WEAPONS:
            self.assertEqual(ITEM_BINDINGS[key].feed_effect, "right_hand_weapon", key)
        for key in set(self.FIREARMS) | set(self.LEFT_HAND_TOOLS):
            self.assertEqual(ITEM_BINDINGS[key].feed_effect, "left_hand_weapon", key)

    def test_firearms_have_no_uncanny_variant(self):
        """The finding, encoded.

        Smithbox's BB EquipParamWeapon row names carry Uncanny (+10000) and
        Lost (+20000) rows for every trick weapon and for NO firearm: the
        firearm blocks (Hunter Blunderbuss 6000000, Ludwig's Rifle 6100000,
        Hunter Pistol 14000000, Evelyn 14100000, Repeating Pistol 14200000,
        Cannon 15000000, Rosmarinus 18000000, Flamesprayer 18100000) hold only
        the base row and a `- Ghost` row. The save editor's weapons.json agrees:
        it lists 7110000 Uncanny Saw Spear but has no 6010000 or 14010000. So
        the Uncanny catalog is trick-weapon-only, and this asserts the code
        never quietly grows a firearm variant.
        """
        for key in self.FIREARMS:
            self.assertNotIn(key, UNCANNY_WEAPONS, key)
        self.assertTrue(set(self.TRICK_WEAPONS) < set(UNCANNY_WEAPONS))

    def test_one_uncanny_row_per_trick_weapon_at_the_uncanny_offset(self):
        self.assertEqual(len(UNCANNY_ITEM_KEYS), 26)
        for key, (param_id, _) in self.TRICK_WEAPONS.items():
            variant = ITEM_BINDINGS[UNCANNY_WEAPONS[key]]
            self.assertEqual(variant.normalized_item_id, param_id + 10000, key)
            self.assertEqual(variant.descriptor_evidence, "param_id_inferred", key)

    def test_complete_dlc_weapon_catalog_and_failed_torch_stay_separate(self):
        """All obtainable DLC equipment enters; the failed Torch stays out.

        EquipParamWeapon ids from 23000000 up are The Old Hunters block
        (Beasthunter Saif 23000000, Beast Cutter 24000000, Amygdalan Arm
        25000000, Holy Moonlight Sword 26000000, Rakuyo 27000000, Boom Hammer
        28000000, Bloodletter 29000000, Church Pick 30000000, Whirligig Saw
        31000000, Simon's Bowblade 32000000, Kos Parasite 38000000). The Torch
        is base game but is a standing negative canary, not an omission.
        """
        names = {item.name for item in MODEL.items}
        for name in ("Holy Moonlight Sword", "Rakuyo", "Bloodletter", "Church Pick",
                     "Simon's Bowblade", "Kos Parasite", "Gatling Gun", "Piercing Rifle"):
            self.assertIn(name, names, name)
        self.assertNotIn("Torch", names)
        from worlds.bloodborne.data import DLC_WEAPON_KEYS
        for key in DLC_WEAPON_KEYS:
            self.assertEqual(ITEM_BINDINGS[key].item_category, 0, key)
        self.assertEqual(
            {key for key, binding in ITEM_BINDINGS.items()
             if binding.item_category == 0 and binding.normalized_item_id >= 23000000},
            {key for key in DLC_WEAPON_KEYS if key != "loch_shield"},
        )


class CompleteObtainableWeaponCatalogTests(unittest.TestCase):
    DLC_TRICK_WEAPONS = {
        "beasthunter_saif": 23000000, "beast_cutter": 24000000,
        "amygdalan_arm": 25000000, "holy_moonlight_sword": 26000000,
        "rakuyo": 27000000, "boom_hammer": 28000000, "bloodletter": 29000000,
        "church_pick": 30000000, "whirligig_saw": 31000000,
        "simons_bowblade": 32000000, "kos_parasite": 38000000,
    }
    DLC_LEFT_HAND = {
        "church_cannon": 35000000, "gatling_gun": 33000000,
        "piercing_rifle": 36000000, "fist_of_gratia": 34000000,
        "loch_shield": 19100000,
    }

    def test_all_obtainable_dlc_rows_have_exact_descriptors(self):
        for key, param_id in {**self.DLC_TRICK_WEAPONS, **self.DLC_LEFT_HAND}.items():
            binding = ITEM_BINDINGS[key]
            self.assertEqual(binding.normalized_item_id, param_id, key)
            self.assertEqual(binding.raw_descriptor, param_id | 0x80000000, key)
            self.assertEqual(binding.item_category, 0, key)
            self.assertEqual(binding.reinforcement_level, 0, key)

    def test_every_obtainable_dlc_trick_weapon_has_uncanny_variant(self):
        for key, param_id in self.DLC_TRICK_WEAPONS.items():
            uncanny = UNCANNY_WEAPONS[key]
            self.assertEqual(ITEM_BINDINGS[uncanny].normalized_item_id, param_id + 10000, key)

    def test_lost_variants_are_deliberately_not_ap_items(self):
        names = {item.name for item in MODEL.items}
        self.assertFalse(any(name.startswith("Lost ") for name in names))


class Wave1GoodsVarietyTests(unittest.TestCase):
    """bb-archipelago#207 wave 1, goods half: filler stops being a wall of one name."""

    # id -> (key, display name, quantity). Every id below is a row in the
    # repo's own bundled params/EquipParamGoods.csv, which is the authoritative
    # category-4 source; the test re-reads the bundle rather than trusting this.
    GOODS = {
        1100: ("antidote", "Antidote x2", 2),
        1101: ("sedatives", "Sedatives x2", 2),
        1110: ("beast_blood_pellet", "Beast Blood Pellet", 1),
        1120: ("blue_elixir", "Blue Elixir", 1),
        1210: ("poison_knife", "Poison Knife x3", 3),
        1240: ("throwing_knife", "Throwing Knife x4", 4),
        1300: ("fire_paper", "Fire Paper x2", 2),
        1320: ("bolt_paper", "Bolt Paper x2", 2),
        1330: ("bone_marrow_ash", "Bone Marrow Ash x3", 3),
        2030: ("lead_elixir", "Lead Elixir", 1),
    }

    def test_the_variety_set_is_exactly_the_declared_goods(self):
        by_key = {item.key: item for item in MODEL.items}
        self.assertEqual(GOODS_VARIETY_KEYS,
                         frozenset(key for key, _, _ in self.GOODS.values()))
        for param_id, (key, name, quantity) in self.GOODS.items():
            self.assertEqual(by_key[key].name, name, key)
            self.assertEqual(by_key[key].kind, ItemKind.FILLER, key)
            self.assertEqual(by_key[key].quantity, quantity, key)
            binding = ITEM_BINDINGS[key]
            self.assertEqual(binding.item_category, 4, key)
            self.assertEqual(binding.normalized_item_id, 0x40000000 | param_id, key)
            self.assertEqual(binding.raw_descriptor, 0xB0000000 | param_id, key)

    def test_every_goods_id_is_a_row_in_the_bundled_param(self):
        """The bundle is the promotion: these ids are not inferred from anywhere."""
        import subprocess
        import sys

        text = subprocess.run(
            [sys.executable, "tools/bb_inputs.py", "--get", "params/EquipParamGoods.csv"],
            cwd=ROOT, capture_output=True, text=True, check=True).stdout
        rows = {int(row["ID"]): row for row in csv.DictReader(text.splitlines())}
        self.assertIn(1000, rows)  # witness: the bundle really parsed
        for param_id, (key, _, quantity) in self.GOODS.items():
            self.assertIn(param_id, rows, key)
            # A grant that exceeds the row's own cap is not a grant.
            self.assertLessEqual(quantity, int(rows[param_id]["maxNum"]), key)

    def test_the_goods_reach_the_default_pool_as_filler(self):
        counts = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        for _, (key, name, _) in sorted(self.GOODS.items()):
            self.assertGreater(counts[name], 0, name)
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))


class WeightedFillerTests(unittest.TestCase):
    """The filler mix is a function of the seed, not of a draw."""

    def test_the_mix_is_stable_for_one_seed_and_varies_across_seeds(self):
        first = build_item_pool_names(FULL_POOL_ITEM_KEYS, "seed-a")
        again = build_item_pool_names(FULL_POOL_ITEM_KEYS, "seed-a")
        other = build_item_pool_names(FULL_POOL_ITEM_KEYS, "seed-b")
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        # Only the ARRANGEMENT moves: the composition is the same multiset, so
        # no seed can be luckier than another.
        self.assertEqual(Counter(first), Counter(other))
        self.assertEqual(len(first), len(NETWORK_LOCATIONS))

    def test_the_identity_holds_for_every_seed_and_both_modes(self):
        for keys in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS,
                     FULL_POOL_ITEM_KEYS | UNCANNY_ITEM_KEYS):
            for seed in ("", "1", "99999", "a much longer seed name:3"):
                pool = build_item_pool_names(keys, seed)
                self.assertEqual(len(pool), len(NETWORK_LOCATIONS), (len(keys), seed))

    def test_marginal_unique_items_shed_filler_in_explicit_tier_order(self):
        candidates = [
            ("coldblood_dew", "echo"),
            ("blood_vial", "vial"),
            ("quicksilver_bullets", "bullets"),
            ("pebbles", "pebbles"),
            ("thick_coldblood", "higher echo"),
            ("molotov_cocktails", "molotov"),
            ("blood_stone_shards", "shards"),
        ]
        envelope = 140
        previous = Counter(_weighted_filler(
            candidates, envelope, "shed-order", envelope=envelope))
        removed_tiers = []
        # Below the sum of the configured floors scarcity necessarily starts
        # consuming guarantees; the ordinary marginal-addition range ends
        # before that emergency regime.
        for count in range(envelope - 1, 30, -1):
            current = Counter(_weighted_filler(
                candidates, count, "shed-order", envelope=envelope))
            removed = list((previous - current).elements())
            self.assertEqual(len(removed), 1)
            key_by_name = {name: key for key, name in candidates}
            removed_tiers.append(FILLER_SHED_TIER.get(key_by_name[removed[0]], 4))
            previous = current
        self.assertEqual(removed_tiers, sorted(removed_tiers))

    def test_reinforcement_and_combat_floors_outlive_disposable_filler(self):
        candidates = [
            ("coldblood_dew", "echo"),
            ("blood_vial", "vial"),
            ("pebbles", "pebbles"),
            ("molotov_cocktails", "molotov"),
            ("blood_stone_shards", "shards"),
        ]
        names = _weighted_filler(candidates, 12, "floors", envelope=100)
        self.assertNotIn("echo", names)
        self.assertNotIn("pebbles", names)
        self.assertIn("vial", names)
        self.assertIn("molotov", names)
        self.assertIn("shards", names)

    def test_blood_vial_stays_in_the_mix_and_stays_the_filler_contract(self):
        pool = build_item_pool_names(FULL_POOL_ITEM_KEYS, "seed-a")
        self.assertIn(FILLER_ITEM_NAME, pool)
        self.assertIn(FILLER_ITEM_NAME, ITEM_NAME_TO_ID)
        # Vials retain a useful floor even though surplus low-quantity vial
        # bundles are intentionally shed before combat and upgrade supplies.
        counts = Counter(pool)
        self.assertGreaterEqual(counts[FILLER_ITEM_NAME], 8)
        self.assertEqual(FILLER_WEIGHTS["blood_vial"], max(FILLER_WEIGHTS.values()))

    def test_every_filler_item_carries_a_weight(self):
        """A new filler type must be weighted on purpose, not defaulted into."""
        for item in SHUFFLABLE_ITEMS:
            if item.kind is ItemKind.FILLER:
                self.assertIn(item.key, FILLER_WEIGHTS, item.key)

    def test_a_pool_that_cannot_hold_its_progression_raises(self):
        import worlds.bloodborne as world

        original = world.NETWORK_LOCATIONS
        world.NETWORK_LOCATIONS = original[:3]
        try:
            with self.assertRaises(ValueError):
                build_item_pool_names(FULL_POOL_ITEM_KEYS)
        finally:
            world.NETWORK_LOCATIONS = original

    def test_scarce_seeds_shed_uncanny_before_base_weapons(self):
        """The shed order, asserted: variants go first, then the useful tail."""
        import worlds.bloodborne as world

        keys = FULL_POOL_ITEM_KEYS | UNCANNY_ITEM_KEYS
        progression = [item for item in SHUFFLABLE_ITEMS
                       if item.key in keys and item.kind is ItemKind.PROGRESSION]
        useful = [item for item in SHUFFLABLE_ITEMS
                  if item.key in keys and item.kind is ItemKind.USEFUL
                  and item.key not in UNCANNY_ITEM_KEYS]
        original = world.NETWORK_LOCATIONS
        # Exactly enough room for progression plus every base useful item and
        # not one variant.
        world.NETWORK_LOCATIONS = original[:len(progression) + len(useful)]
        try:
            pool = build_item_pool_names(keys)
            self.assertEqual(pool, build_item_pool_names(keys))  # deterministic
            self.assertFalse([name for name in pool if "Uncanny" in name])
            for item in useful:
                self.assertIn(item.name, pool, item.name)
            # One location fewer, and the useful TAIL is what goes.
            world.NETWORK_LOCATIONS = original[:len(progression) + len(useful) - 1]
            smaller = build_item_pool_names(keys)
            self.assertNotIn(useful[-1].name, smaller)
            self.assertIn(useful[0].name, smaller)
            for item in progression:
                self.assertIn(item.name, smaller, item.name)
        finally:
            world.NETWORK_LOCATIONS = original


if __name__ == "__main__":
    unittest.main()
