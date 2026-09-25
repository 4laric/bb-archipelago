import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.chalice_giant_bloodletting_donors import (
    ATTACHMENT_IDS, DONORS, GIANT, HEADLESS_BLOODLETTING,
    NORMAL_BLOODLETTING, SUPPORTED_ARENAS, chalice_recipes,
)
from tools.bb_enemizer.gascoigne_donor import CO_OP_RESTORE_EVENTS
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research" / "bb_inputs.db"


class ChaliceGiantBloodlettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        cls.destinations = {
            arena.key: read_blob(BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
            for arena in SUPPORTED_ARENAS
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slots.tsv"
            path.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(path, fixed_maps_only=False)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_source_actors_and_variant_family_are_exact(self):
        self.assertEqual(3, len(DONORS))
        self.assertEqual(GIANT.source_archetype.model_name, "c3130")
        self.assertEqual(NORMAL_BLOODLETTING.source_archetype.model_name, "c5090")
        self.assertEqual(HEADLESS_BLOODLETTING.source_archetype.model_name, "c5090")
        self.assertEqual(NORMAL_BLOODLETTING.family, HEADLESS_BLOODLETTING.family)
        self.assertNotEqual(NORMAL_BLOODLETTING.source_archetype,
                            HEADLESS_BLOODLETTING.source_archetype)
        self.assertEqual(509000, NORMAL_BLOODLETTING.source_archetype.think_param_id)
        self.assertEqual(509010, HEADLESS_BLOODLETTING.source_archetype.think_param_id)
        self.assertEqual((313000, 509000, 509010),
                         tuple(donor.health_label for donor in DONORS))
        self.assertNotIn(10509011, [d.source_archetype.npc_param_id for d in DONORS])
        for donor in DONORS:
            matches = [slot for slot in self.slots if slot.map_name == donor.source_map
                       and slot.part_name == donor.source_part]
            self.assertEqual(1, len(matches), donor.key)
            self.assertEqual(donor.source_entity, matches[0].entity_id)
            self.assertEqual(donor.source_archetype, matches[0].archetype)
            self.assertFalse(matches[0].dummy)
        for effect in list(range(480, 485)) + list(range(490, 495)):
            self.assertIn(effect, self.effects)

    def test_all_opt_in_routes_preserve_arena_progression(self):
        routes = chalice_recipes()
        self.assertEqual(18, len(routes))
        self.assertEqual(len(routes), len({route.key for route in routes}))
        for recipe in routes:
            with self.subTest(recipe=recipe.key):
                original = event_blocks(self.destinations[recipe.arena.key])
                output = event_blocks(recipe.patch(
                    self.destinations[recipe.arena.key], self.source
                ))
                arena = recipe.arena
                for protected in (arena.completion_event, CO_OP_RESTORE_EVENTS[arena.key]):
                    self.assertEqual(original[protected], output[protected])
                self.assertEqual(
                    original[arena.health_bar_event].replace(
                        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label});",
                        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {recipe.donor.health_label});"),
                    output[arena.health_bar_event],
                )
                self.assertEqual(set(original) | (set(ATTACHMENT_IDS)
                                 if recipe.donor is NORMAL_BLOODLETTING else set()),
                                 set(output))
                self.assertIn(f"CharacterHasEventMessage({arena.actor}, 500)",
                              output[arena.music_event])
                if recipe.donor is NORMAL_BLOODLETTING:
                    self.assertIn(f"$InitializeEvent(0, {ATTACHMENT_IDS[0]}, {arena.actor},",
                                  output[0])
                    self.assertIn(f"$InitializeEvent(4, {ATTACHMENT_IDS[6]}, 484, 494,",
                                  output[0])
                else:
                    self.assertEqual(original[0], output[0])

    def test_source_drift_is_rejected(self):
        recipe = chalice_recipes()[1]
        destination = self.destinations[recipe.arena.key]
        with self.assertRaisesRegex(ValueError, "handler 12904898 drifted"):
            recipe.patch(destination, self.source.replace(
                "$Event(12904898, Default, function(chrEntityId,",
                "$Event(12904898, Default, function(chrEntityIdX,", 1))
        with self.assertRaisesRegex(ValueError, "event 0 drifted"):
            recipe.patch(destination.replace("$InitializeEvent", "$InitializeEventX", 1),
                         self.source)

    def test_native_plan_pins_primary_and_reports_unknown_chalice_tier(self):
        recipe = next(r for r in chalice_recipes()
                      if r.key == ("cleric-beast", "bloodletting-beast"))
        plan = recipe.native_plan(self.slots, self.npcs, self.effects, "chalice-seed")
        self.assertEqual("bloodletting-beast", plan["boss_contract"]["family"])
        self.assertEqual(1, plan["swap_count"])
        self.assertEqual(0, plan["scaling"]["change_count"])
        self.assertEqual("unknown source or destination tier",
                         plan["scaling"]["skips"][0]["reason"])
        self.assertEqual(recipe.arena.destination_count,
                         len(plan["primary_init_source_bindings"]))
        for binding in plan["primary_init_source_bindings"]:
            self.assertEqual(NORMAL_BLOODLETTING.source_part_sha256,
                             binding["source_provenance"]["part_sha256"])
            self.assertEqual(10509006, binding["source_archetype"]["npc_param_id"])
            self.assertEqual(509000, binding["source_archetype"]["think_param_id"])


if __name__ == "__main__":
    unittest.main()
