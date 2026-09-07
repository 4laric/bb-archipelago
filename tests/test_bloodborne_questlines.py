"""Coverage for the `questlines_hold_progression` option (off by default).

Questline locations are the NPC/ESD dialogue badge awards -- goods acquisition
flags that fire when a quest NPC hands over their reward at the end of a
questline, rather than a placed treasure, a boss defeat, a shop purchase, or
an enemy drop. `QUESTLINE_LOCATION_KEYS` in `worlds/bloodborne/data.py` is
derived, not hand-listed: every location whose key starts with "award_" and
whose `docs/LOCATION-NAMING.md` name ends in " award". This file asserts that
derivation stays sound, that the option restricts progression placement when
off, and that turning it off never starves the progression pool of somewhere
legal to land.
"""

from __future__ import annotations

import unittest

from worlds.bloodborne.data import (
    DLC_ITEM_KEYS,
    DLC_LOCATION_KEYS,
    DLC_WEAPON_KEYS,
    ITEMS,
    LOCATIONS,
    ONE_TIME_ENEMY_LOCATION_KEYS,
    QUESTLINE_LOCATION_KEYS,
    SLICE_ITEM_KEYS,
    SLICE_LOCATION_KEYS,
)
from worlds.bloodborne.model import ItemKind

from worlds.bloodborne import FULL_POOL_ITEM_KEYS, NETWORK_LOCATIONS

try:
    import Options  # noqa: F401  (the world's option classes need Archipelago)
    from worlds.bloodborne import BloodborneWorld  # noqa: F401
    AP_AVAILABLE = True
except ImportError:  # pragma: no cover - environment dependent
    AP_AVAILABLE = False


LOCATIONS_BY_KEY = {location.key: location for location in LOCATIONS}
PROGRESSION_ITEM_KEYS = frozenset(
    item.key for item in ITEMS if item.kind is ItemKind.PROGRESSION
)


class QuestlineLocationDerivationTests(unittest.TestCase):
    """The award-location set is non-empty and matches the naming corpus."""

    def test_questline_location_keys_is_nonempty(self):
        self.assertTrue(QUESTLINE_LOCATION_KEYS)

    def test_every_questline_key_starts_with_award(self):
        for key in QUESTLINE_LOCATION_KEYS:
            self.assertTrue(key.startswith("award_"), key)

    def test_every_questline_location_name_ends_with_award(self):
        for key in QUESTLINE_LOCATION_KEYS:
            location = LOCATIONS_BY_KEY[key]
            self.assertTrue(location.name.endswith(" award"), location.name)

    def test_known_npc_badge_awards_are_covered(self):
        # The four committed dialogue awards (Eileen, Djura, Alfred, the
        # Annalise/Vileblood oath) documented in location_names.tsv.
        self.assertEqual(
            {
                "award_crow_hunter_badge",
                "award_powder_keg_hunter_badge",
                "award_wheel_hunter_badge",
                "award_cainhurst_badge",
            },
            QUESTLINE_LOCATION_KEYS,
        )

    def test_excludes_boss_treasure_shop_and_drop_locations(self):
        for key in QUESTLINE_LOCATION_KEYS:
            self.assertFalse(key.startswith("boss_"), key)
            self.assertFalse(key.startswith("treasure_"), key)
            self.assertFalse(key.startswith("fixed_"), key)


def _non_questline_location_count(*, include_dlc: bool, one_time_enemy_checks: bool) -> int:
    keys = {location.key for location in NETWORK_LOCATIONS if location.key in SLICE_LOCATION_KEYS}
    if one_time_enemy_checks:
        # Mirrors BloodborneWorld._active_locations, which re-adds these keys
        # from the full slice manifest when the option is on.
        from worlds.bloodborne import ALL_NETWORK_LOCATIONS
        keys = {location.key for location in ALL_NETWORK_LOCATIONS}
    else:
        keys -= ONE_TIME_ENEMY_LOCATION_KEYS
    if not include_dlc:
        keys -= DLC_LOCATION_KEYS
    return len(keys - QUESTLINE_LOCATION_KEYS)


def _progression_item_count(*, full_item_pool: bool, include_dlc: bool) -> int:
    base = FULL_POOL_ITEM_KEYS if full_item_pool else SLICE_ITEM_KEYS
    if not include_dlc:
        base = base - (DLC_ITEM_KEYS - DLC_WEAPON_KEYS)
    return len(base & PROGRESSION_ITEM_KEYS)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class FillSafetyTests(unittest.TestCase):
    """With questlines off, progression must always have somewhere else to land."""

    def test_default_options_have_room(self):
        # full_item_pool off, include_dlc off, one_time_enemy_checks off: the
        # documented default.
        progression = _progression_item_count(full_item_pool=False, include_dlc=False)
        room = _non_questline_location_count(include_dlc=False, one_time_enemy_checks=False)
        self.assertLessEqual(progression, room)

    def test_smallest_configuration_has_room(self):
        for full_item_pool in (False, True):
            for include_dlc in (False, True):
                for one_time_enemy_checks in (False, True):
                    with self.subTest(
                        full_item_pool=full_item_pool,
                        include_dlc=include_dlc,
                        one_time_enemy_checks=one_time_enemy_checks,
                    ):
                        progression = _progression_item_count(
                            full_item_pool=full_item_pool, include_dlc=include_dlc)
                        room = _non_questline_location_count(
                            include_dlc=include_dlc,
                            one_time_enemy_checks=one_time_enemy_checks)
                        self.assertLessEqual(progression, room)


@unittest.skipUnless(AP_AVAILABLE, "requires an Archipelago checkout on sys.path")
class QuestlineItemRuleTests(unittest.TestCase):
    """create_regions wires item_rule onto questline locations only when off."""

    class _Options:
        full_item_pool = 0
        uncanny_weapons = 0
        randomize_armor = 0
        include_dlc = 0
        include_dlc_gear = 1
        alternate_hypogean_gaol_routes = 0
        one_time_enemy_checks = 0

        def __init__(self, questlines_hold_progression):
            self.questlines_hold_progression = questlines_hold_progression

    def _build_world(self, questlines_hold_progression):
        from BaseClasses import ItemClassification, MultiWorld
        from worlds.bloodborne import BloodborneItem, BloodborneWorld

        multiworld = MultiWorld(1)
        multiworld.game[1] = "Bloodborne"
        multiworld.player_name = {1: "Tester"}
        multiworld.set_seed(0)
        world = BloodborneWorld(multiworld, 1)
        world.options = self._Options(questlines_hold_progression)
        world.create_regions()
        return world, BloodborneItem, ItemClassification

    def _questline_location(self, world):
        location = next(
            location for region in world.multiworld.regions
            if region.player == world.player
            for location in region.locations
            if location.name.endswith(" award")
        )
        return location

    def test_option_off_rejects_progression_but_allows_filler(self):
        world, BloodborneItem, ItemClassification = self._build_world(False)
        location = self._questline_location(world)
        self.assertIsNotNone(location.item_rule)
        progression_item = BloodborneItem("probe", ItemClassification.progression, 1, world.player)
        filler_item = BloodborneItem("probe", ItemClassification.filler, 1, world.player)
        self.assertFalse(location.item_rule(progression_item))
        self.assertTrue(location.item_rule(filler_item))

    def test_option_on_leaves_locations_unrestricted(self):
        world, BloodborneItem, ItemClassification = self._build_world(True)
        location = self._questline_location(world)
        progression_item = BloodborneItem("probe", ItemClassification.progression, 1, world.player)
        # Default item_rule (no restriction) accepts everything.
        self.assertTrue(location.item_rule(progression_item))


if __name__ == "__main__":
    unittest.main()
