"""Coverage for the `hemwick_access_gate` option (off by default).

bb-archipelago#326. The gate closes the Cathedral Ward-Hemwick boundary fog
until a shuffled `Hemwick Access` item is received, putting Hemwick and the
downstream Cainhurst checks behind an explicit Archipelago progression item.
It is opt-in, so the interesting property is not that the gate works but that
a default roll is byte-for-byte the build that existed before the option: no
`Hemwick Access` in the pool, no runtime binding for it, an unconditional
`Road to Hemwick`, and a `hemwick_gate` slot-data value of `None`, which is
the launcher's own "no gate" shape (see `bb_launcher/core.py`: it is what
keeps the Cathedral event owning exactly [12400760, 12401803, 12405710] and
emits no `hemwick_event` witness at all).

Both halves are asserted here. A test that only checked the ON path would pass
while the option silently leaked into every seed.
"""

from __future__ import annotations

import unittest

from worlds.bloodborne.data import (
    HEMWICK_GATE_ENTRANCE_NAME,
    HEMWICK_GATE_ENTRANCE_RULE,
    HEMWICK_GATE_ITEM_KEY,
    HEMWICK_GATE_ITEM_KEYS,
    ENTRANCES,
    SLICE_ITEM_KEYS,
)
from worlds.bloodborne import FULL_POOL_ITEM_KEYS

try:
    from worlds.bloodborne import BloodborneOptions, BloodborneWorld
except ImportError:  # pragma: no cover - environment dependent
    BloodborneOptions = BloodborneWorld = None


class HemwickGateDataShapeTests(unittest.TestCase):
    """The static model stays vanilla; the gated shape is stated separately."""

    def test_the_authored_entrance_is_free(self):
        entrance = next(e for e in ENTRANCES if e.name == HEMWICK_GATE_ENTRANCE_NAME)
        self.assertEqual(entrance.rule.any_of, (frozenset(),))

    def test_the_installed_rule_requires_the_access_item(self):
        self.assertEqual(
            HEMWICK_GATE_ENTRANCE_RULE.any_of,
            (frozenset({HEMWICK_GATE_ITEM_KEY}),),
        )

    def test_the_access_item_is_in_no_default_pool(self):
        # Witness that these pools are non-empty and really are the default
        # ones, so "not in" is a fact about a populated set.
        self.assertGreater(len(FULL_POOL_ITEM_KEYS), 100)
        self.assertGreater(len(SLICE_ITEM_KEYS), 10)
        self.assertNotIn(HEMWICK_GATE_ITEM_KEY, FULL_POOL_ITEM_KEYS)
        self.assertNotIn(HEMWICK_GATE_ITEM_KEY, SLICE_ITEM_KEYS)


@unittest.skipIf(BloodborneWorld is None, "requires Archipelago core")
class HemwickGateOptionTests(unittest.TestCase):
    class _Options:
        full_item_pool = 0
        uncanny_weapons = 0
        randomize_armor = 0
        include_dlc = 0
        include_dlc_gear = 1
        alternate_hypogean_gaol_routes = 0
        one_time_enemy_checks = 0
        questlines_hold_progression = 0

        def __init__(self, hemwick_access_gate):
            self.hemwick_access_gate = hemwick_access_gate

    def _pool_keys(self, enabled):
        world = BloodborneWorld.__new__(BloodborneWorld)
        world.options = self._Options(enabled)
        return world._pool_item_keys()

    def test_option_defaults_off_and_is_named(self):
        option = BloodborneOptions.type_hints["hemwick_access_gate"]
        self.assertEqual(0, option.default)
        self.assertEqual("Hemwick Access Gate", option.display_name)

    def test_option_off_omits_the_access_item_and_on_adds_exactly_it(self):
        off = self._pool_keys(0)
        on = self._pool_keys(1)
        self.assertNotIn(HEMWICK_GATE_ITEM_KEY, off)
        self.assertEqual(set(HEMWICK_GATE_ITEM_KEYS), set(on) - set(off))

    def test_a_world_that_cannot_answer_fails_closed(self):
        """An old option object or a small test double gets the OFF build."""
        class _Bare:
            full_item_pool = 0
            uncanny_weapons = 0
            randomize_armor = 0
            include_dlc = 0
            include_dlc_gear = 1

        world = BloodborneWorld.__new__(BloodborneWorld)
        world.options = _Bare()
        self.assertFalse(world._hemwick_access_gate_enabled())
        self.assertNotIn(HEMWICK_GATE_ITEM_KEY, world._pool_item_keys())

    def _build_world(self, enabled):
        from BaseClasses import MultiWorld

        multiworld = MultiWorld(1)
        multiworld.game[1] = "Bloodborne"
        multiworld.player_name = {1: "Tester"}
        multiworld.set_seed(0)
        world = BloodborneWorld(multiworld, 1)
        world.options = self._Options(enabled)
        world.create_regions()
        return world

    def _hemwick_entrance(self, world):
        return next(
            entrance for region in world.multiworld.regions
            if region.player == world.player
            for entrance in region.exits
            if entrance.name == HEMWICK_GATE_ENTRANCE_NAME
        )

    def test_option_off_leaves_the_road_to_hemwick_unconditional(self):
        from BaseClasses import CollectionState

        world = self._build_world(0)
        entrance = self._hemwick_entrance(world)
        # A fresh state satisfies it: nothing has been collected at all.
        state = CollectionState(world.multiworld)
        self.assertTrue(entrance.access_rule(state))

    def test_option_on_closes_the_road_until_hemwick_access_is_received(self):
        from BaseClasses import CollectionState, ItemClassification
        from worlds.bloodborne import BloodborneItem, ITEM_NAME_TO_ID

        world = self._build_world(1)
        entrance = self._hemwick_entrance(world)
        state = CollectionState(world.multiworld)
        self.assertFalse(entrance.access_rule(state))
        state.collect(BloodborneItem(
            "Hemwick Access", ItemClassification.progression,
            ITEM_NAME_TO_ID["Hemwick Access"], world.player), prevent_sweep=True)
        self.assertTrue(entrance.access_rule(state))


if __name__ == "__main__":
    unittest.main()
