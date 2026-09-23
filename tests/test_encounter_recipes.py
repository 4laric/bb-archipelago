import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_contracts import (
    ARENAS,
    COMPATIBILITY,
    EBRIETAS_PACKAGE,
    PACKAGES,
    PAARL_ARENA,
    event_blocks,
)
from tools.bb_enemizer.encounter_recipes import reusable_recipes
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "research/bb_inputs.db"


class EncounterRecipeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory)
        cls.npcs, cls.effects = load_params(BUNDLE)
        cls.sources = {
            arena.event_file: read_blob(BUNDLE, "event/" + arena.event_file).decode(
                "utf-8-sig"
            )
            for arena in ARENAS
        }
        cls.recipes = reusable_recipes()

    def test_registry_is_exact_union_of_base_capabilities_and_six_maria_bindings(self):
        base_keys = {
            (arena, donor)
            for arena, donors in COMPATIBILITY.items()
            for donor in donors
        }
        maria_keys = {(arena.key, "lady-maria") for arena in ARENAS}
        self.assertEqual(base_keys | maria_keys, set(self.recipes))
        self.assertEqual(
            sum(len(donors) for donors in COMPATIBILITY.values()), len(base_keys)
        )
        self.assertEqual(6, len(maria_keys))
        self.assertEqual(len(base_keys) + len(maria_keys), len(self.recipes))
        self.assertFalse({key for key in self.recipes if key[0] == key[1]})
        self.assertEqual(
            len(self.recipes), len({id(recipe) for recipe in self.recipes.values()})
        )

        arenas = {arena.key: arena for arena in ARENAS}
        packages = {package.key: package for package in PACKAGES}
        for key in base_keys:
            recipe = self.recipes[key]
            self.assertIs(arenas[key[0]], recipe.arena)
            self.assertIs(packages[key[1]], recipe.donor)
        for key in maria_keys:
            recipe = self.recipes[key]
            self.assertIs(arenas[key[0]], recipe.arena)
            self.assertEqual("lady-maria", recipe.donor.key)

    def test_recipe_metadata_is_explicit_and_frozen_without_runtime_claim(self):
        recipe = self.recipes[(PAARL_ARENA.key, EBRIETAS_PACKAGE.key)]
        self.assertEqual("donor-source", recipe.combat_owner)
        self.assertEqual("destination-arena", recipe.progression_owner)
        self.assertEqual("static-contract-only", recipe.validation_status)
        with self.assertRaises(FrozenInstanceError):
            recipe.validation_status = "runtime-validated"

    def test_base_recipe_uses_real_sources_and_keeps_materialization_separate(self):
        recipe = self.recipes[(PAARL_ARENA.key, EBRIETAS_PACKAGE.key)]
        destination = self.sources[PAARL_ARENA.event_file]
        donor_source = self.sources[EBRIETAS_PACKAGE.event_file]
        before = event_blocks(destination)
        after = event_blocks(recipe.patch(destination, donor_source))
        self.assertEqual(
            before[PAARL_ARENA.completion_event], after[PAARL_ARENA.completion_event]
        )
        self.assertIn("CreateBulletOwner(2300891)", after[0])

        requirements = recipe.actor_requirements(self.slots)
        self.assertEqual(2, len(requirements))
        self.assertEqual(
            {2300891}, {row["destination_entity_id"] for row in requirements}
        )
        plan = recipe.native_plan(self.slots, self.npcs, self.effects, "recipe-base")
        self.assertEqual("bb-enemizer-plan-v2", plan["format"])
        self.assertEqual(requirements, plan["boss_actor_addition_requirements"])
        self.assertNotIn("boss_actor_additions", plan)

    def test_maria_recipe_uses_real_sources_and_caller_owned_allocation(self):
        from tools.bb_enemizer.maria_contract import MARIA_EVENT_FILE

        arena = next(arena for arena in ARENAS if arena.key == "cleric-beast")
        recipe = self.recipes[(arena.key, "lady-maria")]
        destination = self.sources[arena.event_file]
        donor_source = read_blob(BUNDLE, "event/" + MARIA_EVENT_FILE).decode(
            "utf-8-sig"
        )
        before = event_blocks(destination)
        after = event_blocks(recipe.patch(destination, donor_source))
        self.assertEqual(before[arena.completion_event], after[arena.completion_event])
        self.assertEqual({12994700}, set(after) - set(before))
        self.assertIn("SetEventFlag(12994701, ON)", after[arena.health_bar_event])

        plan = recipe.native_plan(self.slots, self.npcs, self.effects, "recipe-maria")
        self.assertEqual("bb-enemizer-plan-v2", plan["format"])
        self.assertEqual("lady-maria", plan["boss_contract"]["donor"])
        self.assertEqual(arena.key, plan["boss_contract"]["arena"])
        self.assertEqual(
            arena.destination_count, len(plan["primary_init_source_bindings"])
        )
        self.assertEqual("c4520", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {3500800},
            {
                binding["source_entity_id"]
                for binding in plan["primary_init_source_bindings"]
            },
        )


if __name__ == "__main__":
    unittest.main()
