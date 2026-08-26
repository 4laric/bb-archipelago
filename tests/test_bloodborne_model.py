import csv
import unittest
from collections import Counter
from pathlib import Path

from worlds.bloodborne.data import SLICE_ITEM_KEYS, UNCANNY_WEAPONS, MODEL
from worlds.bloodborne.model import ItemKind, Rule
from worlds.bloodborne.runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS
from worlds.bloodborne import (
    FULL_POOL_ITEM_KEYS,
    GOAL_LOCATION_KEY,
    ITEM_ID_BY_KEY,
    ITEM_NAME_TO_ID,
    LOCATION_ID_BY_KEY,
    LOCATION_NAME_TO_ID,
    NETWORK_LOCATIONS,
    SHUFFLABLE_ITEMS,
    build_item_pool_names,
    build_runtime_slot_data,
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
    seeded = {n.key for n in NETWORK_LOCATIONS}
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
    def test_model_references_are_valid(self):
        self.assertEqual([], MODEL.validate())

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

    def test_slice_contains_the_three_maps_and_their_bosses(self):
        # 161 in-slice fixed pickups + 6 scripted checks. Out of slice seeds:
        # the two clinic back-yard rows (#124) and the White Messenger Ribbon,
        # a post-Rom quest reward whose region IS in the slice.
        self.assertEqual(167, len(NETWORK_LOCATIONS))
        by_region = Counter(location.region for location in NETWORK_LOCATIONS)
        self.assertEqual(
            dict(by_region),
            {"Central Yharnam": 48, "Cathedral Ward": 62,
             "Old Yharnam": 55, "Grand Cathedral": 2},
        )
        self.assertEqual(12411700, LOCATION_BINDINGS["boss_cleric_beast"].event_flag)
        self.assertEqual(12411800, LOCATION_BINDINGS["boss_father_gascoigne"].event_flag)
        self.assertEqual(12301800, LOCATION_BINDINGS["boss_blood_starved_beast"].event_flag)
        self.assertEqual("boss_blood_starved_beast", GOAL_LOCATION_KEY)
        self.assertEqual(
            LOCATION_ID_BY_KEY[GOAL_LOCATION_KEY],
            build_runtime_slot_data()["goal_location"],
        )

    def test_slice_excludes_out_of_slice_fixed_rows(self):
        keys = {location.key for location in NETWORK_LOCATIONS}
        self.assertNotIn("fixed_central_yharnam_lot_2410140", keys)
        self.assertNotIn("fixed_central_yharnam_lot_2410640", keys)
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
        ):
            self.assertEqual(counts[name], 1, name)
        # 167 locations - 13 one-off items = 154 filler slots cycling five
        # names: the first four get 31, the last gets 30.
        for name in (
            "Blood Vial",
            "Quicksilver Bullets x3",
            "Pebbles x3",
            "Molotov Cocktails x2",
        ):
            self.assertEqual(counts[name], 31, name)
        self.assertEqual(counts["Blood Stone Shards x2"], 30)

    def test_slice_pool_option_off_preserves_the_original_grant_shapes(self):
        """The grant shapes the first live sessions validated are unchanged.

        Slice 3 added the Hunter Chief Emblem to this pool because the plaza
        gate is emblem-only, and the Oedon Tomb Key joins it for the same
        reason: with the key shuffled, a pool without it cannot leave Central
        Yharnam. 167 - 4 one-off items = 163 filler slots over five names, so
        the first three get 33 and the last two get 32.
        """
        counts = Counter(build_item_pool_names(SLICE_ITEM_KEYS))
        self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
        self.assertEqual(counts["Saw Spear"], 1)
        self.assertEqual(counts["Augur of Ebrietas"], 1)
        self.assertEqual(counts["Hunter Chief Emblem"], 1)
        self.assertEqual(counts["Oedon Tomb Key"], 1)
        for name in (
            "Blood Vial",
            "Quicksilver Bullets x3",
            "Pebbles x3",
        ):
            self.assertEqual(counts[name], 33, name)
        for name in ("Molotov Cocktails x2", "Blood Stone Shards x2"):
            self.assertEqual(counts[name], 32, name)
        slot_data = build_runtime_slot_data(SLICE_ITEM_KEYS)
        self.assertEqual(len(slot_data["runtime_items"]), 9)  # eight slice items + Blood Vial

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
            self.assertIn(binding.event_flag, lots_by_flag, location)
            lots = lots_by_flag[binding.event_flag]
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
            if binding.source_kind in ("boss_defeat", "interaction"):
                # Flag-only checks: no item lot to trace; the evidence string
                # must carry the flag itself.
                self.assertIsNone(binding.item_lot_id)
                self.assertIn(str(binding.event_flag), binding.evidence)
                continue
            if binding.source_kind == "script_award":
                row = rows_by_name[names_by_key[key]]
                self.assertIn(str(binding.item_lot_id), row["item_lot_ids"], key)
                self.assertIn(str(binding.event_flag), row["acquisition_flags"], key)
                self.assertIn(binding.source_kind, row["observed_sources"].split(";"), key)
                expected_ref = row["script_awards"]
            else:
                matches = [row for row in catalog_items
                           if row["location_flag"] == str(binding.event_flag)
                           and row["item_lot_id"] == str(binding.item_lot_id)
                           and row["category"] == str(binding.item_category)
                           and row["item_param_id"] == str(binding.item_id)]
                self.assertEqual(1, len(matches), key)
                expected_ref = catalog_locations[str(binding.event_flag)]["map_variants"]
            self.assertEqual(expected_ref, binding.source_ref, key)
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
        self.assertEqual({location.name for location in NETWORK_LOCATIONS}, set(LOCATION_NAME_TO_ID))
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

    def test_the_seeded_slice_is_fully_reachable_and_the_emblem_is_load_bearing(self):
        """Reachability, without needing an Archipelago checkout.

        Two claims, and the second is the one worth having. Every seeded
        location must be reachable with the seeded pool -- otherwise
        generation would have to bury real checks under filler. And with the
        Hunter Chief Emblem withheld, some seeded locations must become
        unreachable, or the emblem-only plaza gate is decoration.
        """
        from worlds.bloodborne.data import SLICE_ITEM_KEYS, SLICE_REGIONS

        locations = seeded_locations()
        reachable = slice_reachable

        # Menu and Hunter's Dream are transit regions in this slice: the
        # Dream's own check (the Eye) belongs to the post-Amelia chain.
        self.assertEqual(set(SLICE_REGIONS) - {"Menu", "Hunter's Dream"},
                         {l.region for l in locations})
        with_everything = reachable(set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS))
        self.assertEqual(with_everything, {l.key for l in locations})

        without_emblem = reachable(
            (set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)) - {"hunter_chief_emblem"})
        gated = with_everything - without_emblem
        self.assertEqual(
            gated,
            {l.key for l in locations if l.region == "Grand Cathedral"},
        )
        self.assertTrue(gated, "the Hunter Chief Emblem gates nothing in the seeded slice")

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
                                 if l.region not in ("Central Yharnam", "Hunter's Dream")})
        # 119 of 167: the key is the single largest gate in the slice, so a
        # seed that could not place it reachably would be mostly unplayable.
        self.assertEqual(len(gated), len(locations) - len(central_yharnam))
        self.assertGreater(len(gated), len(locations) // 2)

    def test_the_goal_is_behind_the_oedon_tomb_key(self):
        """The Blood-starved Beast is in Old Yharnam, two gates past the key."""
        from worlds.bloodborne import GOAL_LOCATION_KEY
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        everything = set(SLICE_ITEM_KEYS) | set(FULL_POOL_ITEM_KEYS)
        self.assertIn(GOAL_LOCATION_KEY, slice_reachable(everything))
        self.assertNotIn(GOAL_LOCATION_KEY,
                         slice_reachable(everything - {"oedon_tomb_key"}))

    def test_the_key_is_in_every_pool_the_world_can_build(self):
        """A progression item the pool may omit is a generation failure waiting."""
        from worlds.bloodborne import build_item_pool_names
        from worlds.bloodborne.data import SLICE_ITEM_KEYS

        for keys in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            self.assertIn("oedon_tomb_key", keys)
            self.assertIn("Oedon Tomb Key", build_item_pool_names(keys))

    def test_every_playable_region_contributes_a_location(self):
        populated = {location.region for location in MODEL.locations}
        self.assertEqual({"Menu"}, set(MODEL.regions) - populated)


class UncannyWeaponPoolTests(unittest.TestCase):
    """bb-archipelago#205: opt-in Uncanny variants displace filler, never checks."""

    def _keys_with_uncanny(self, base):
        return frozenset(base) | frozenset(
            uncanny for weapon, uncanny in UNCANNY_WEAPONS.items() if weapon in base)

    def test_the_default_pool_is_the_pool_it_was_before_the_option_existed(self):
        """The control. Option off must be indistinguishable from pre-#205."""
        for keys in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            pool = build_item_pool_names(keys)
            self.assertEqual(len(pool), len(NETWORK_LOCATIONS))
            self.assertIn("Saw Spear", pool)          # witness: a real pool
            self.assertNotIn("Uncanny Saw Spear", pool)
        # The exact pre-#205 distribution, restated here so a silent shift in
        # the default pool fails this test and not only the older one.
        counts = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        self.assertEqual(counts["Blood Vial"], 31)
        self.assertEqual(counts["Blood Stone Shards x2"], 30)
        self.assertEqual(counts["Saw Spear"], 1)
        self.assertNotIn("uncanny_saw_spear", FULL_POOL_ITEM_KEYS)

    def test_one_uncanny_per_pooled_weapon_and_the_seed_size_identity_holds(self):
        for base in (FULL_POOL_ITEM_KEYS, SLICE_ITEM_KEYS):
            with self.subTest(pool=len(base)):
                counts = Counter(build_item_pool_names(self._keys_with_uncanny(base)))
                self.assertEqual(sum(counts.values()), len(NETWORK_LOCATIONS))
                placed = {name for name in counts if name.startswith("Uncanny")}
                self.assertEqual(placed, {"Uncanny Saw Spear"})
                for name in placed:
                    self.assertEqual(counts[name], 1, name)
                # every weapon in the pool contributed exactly one variant
                self.assertEqual(len(placed),
                                 len([w for w in UNCANNY_WEAPONS if w in base]))

    def test_each_uncanny_copy_displaces_exactly_one_filler_item(self):
        before = Counter(build_item_pool_names(FULL_POOL_ITEM_KEYS))
        after = Counter(build_item_pool_names(self._keys_with_uncanny(FULL_POOL_ITEM_KEYS)))
        added = sum(count for name, count in after.items() if name.startswith("Uncanny"))
        self.assertEqual(added, 1)
        filler_names = {"Blood Vial", "Quicksilver Bullets x3", "Pebbles x3",
                        "Molotov Cocktails x2", "Blood Stone Shards x2"}
        lost = sum(before[name] - after[name] for name in filler_names)
        self.assertEqual(lost, added)
        # nothing but filler moved
        for name in set(before) | set(after):
            if name in filler_names or name.startswith("Uncanny"):
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
        self.assertNotIn("Uncanny Saw Spear", pool)
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
        self.assertEqual(len(with_uncanny), len(without) + 1)
        self.assertEqual(with_uncanny[uncanny_id]["item_category"], 0)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class UncannyOptionWiringTests(unittest.TestCase):
    """The option is the only door into the Uncanny keys."""

    class _Options:
        def __init__(self, full_item_pool, uncanny_weapons):
            self.full_item_pool = full_item_pool
            self.uncanny_weapons = uncanny_weapons

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


if __name__ == "__main__":
    unittest.main()
