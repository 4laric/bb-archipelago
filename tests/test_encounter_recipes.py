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
from tools.bb_enemizer.maria_arena_contract import MARIA_ARENA_CONTRACT
from tools.bb_enemizer.laurence_arena_contract import LAURENCE_ARENA_CONTRACT
from tools.bb_enemizer.gascoigne_arena_contract import GASCOIGNE_ARENA_CONTRACT
from tools.bb_enemizer.orphan_arena_contract import ORPHAN_ARENA_CONTRACT
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

    def test_registry_is_exact_union_of_base_and_specialized_donor_bindings(self):
        base_keys = {
            (arena, donor)
            for arena, donors in COMPATIBILITY.items()
            for donor in donors
        }
        maria_keys = {(arena.key, "lady-maria") for arena in (*ARENAS, LAURENCE_ARENA_CONTRACT)}
        laurence_keys = {(arena.key, "laurence") for arena in (*ARENAS, MARIA_ARENA_CONTRACT)}
        maria_arena_keys = {("lady-maria", donor.key) for donor in PACKAGES}
        logarius_keys = {(arena.key, "martyr-logarius") for arena in
                         (*ARENAS, MARIA_ARENA_CONTRACT, LAURENCE_ARENA_CONTRACT,
                          GASCOIGNE_ARENA_CONTRACT)}
        laurence_arena_keys = {("laurence", donor.key) for donor in PACKAGES}
        gascoigne_arena_keys = {("father-gascoigne", donor.key) for donor in PACKAGES}
        logarius_arena_keys = {("martyr-logarius", donor.key) for donor in PACKAGES}
        orphan_keys = {(arena.key, "orphan-of-kos") for arena in ARENAS}
        orphan_arena_keys = {
            ("orphan-of-kos", donor.key)
            for donor in PACKAGES
            if donor.key != "blood-starved-beast"
        }
        ludwig_arena_keys = {("ludwig", donor.key) for donor in PACKAGES
                             if donor.key != "cleric-beast"}
        ludwig_keys = {(arena.key, "ludwig") for arena in ARENAS}
        gascoigne_donor_keys = {(arena.key, "father-gascoigne") for arena in ARENAS}
        final_boss_donor_keys = {(arena.key, donor) for arena in ARENAS
                                 for donor in ("gehrman", "moon-presence")}
        final_arena_keys = {(arena, donor.key) for donor in PACKAGES
                            for arena in ("gehrman", "moon-presence")}
        micolash_arena_keys = {("micolash", donor.key) for donor in PACKAGES}
        wet_nurse_keys = {(arena.key, "mergos-wet-nurse") for arena in ARENAS}
        micolash_donor_keys = {(arena.key, "micolash") for arena in ARENAS}
        celestial_donor_keys = {(arena.key, "celestial-emissary") for arena in ARENAS}
        groups = (base_keys, maria_keys, laurence_keys, maria_arena_keys, logarius_keys,
                  laurence_arena_keys, gascoigne_arena_keys, logarius_arena_keys,
                  orphan_keys, orphan_arena_keys, ludwig_keys, gascoigne_donor_keys,
                  ludwig_arena_keys, final_boss_donor_keys, final_arena_keys,
                  micolash_arena_keys, wet_nurse_keys, micolash_donor_keys, celestial_donor_keys)
        self.assertEqual(set.union(*groups), set(self.recipes))
        self.assertEqual(
            sum(len(donors) for donors in COMPATIBILITY.values()), len(base_keys)
        )
        self.assertEqual(7, len(maria_keys))
        self.assertEqual(7, len(laurence_keys))
        self.assertEqual(6, len(maria_arena_keys))
        self.assertEqual(9, len(logarius_keys))
        self.assertEqual(6, len(laurence_arena_keys))
        self.assertEqual(6, len(gascoigne_arena_keys))
        self.assertEqual(6, len(logarius_arena_keys))
        self.assertEqual(6, len(orphan_keys))
        self.assertEqual(5, len(orphan_arena_keys))
        self.assertEqual(5, len(ludwig_arena_keys))
        self.assertEqual(6, len(ludwig_keys))
        self.assertEqual(6, len(gascoigne_donor_keys))
        self.assertEqual(12, len(final_boss_donor_keys))
        self.assertEqual(12, len(final_arena_keys))
        self.assertEqual(6, len(micolash_arena_keys))
        self.assertEqual(6, len(wet_nurse_keys))
        self.assertEqual(6, len(micolash_donor_keys))
        self.assertEqual(
            sum(map(len, groups)),
            len(self.recipes),
        )
        self.assertFalse({key for key in self.recipes if key[0] == key[1]})
        self.assertEqual(
            len(self.recipes), len({id(recipe) for recipe in self.recipes.values()})
        )

        arenas = {arena.key: arena for arena in (*ARENAS, MARIA_ARENA_CONTRACT, LAURENCE_ARENA_CONTRACT)}
        packages = {package.key: package for package in PACKAGES}
        for key in base_keys:
            recipe = self.recipes[key]
            self.assertIs(arenas[key[0]], recipe.arena)
            self.assertIs(packages[key[1]], recipe.donor)
        for key in maria_keys:
            recipe = self.recipes[key]
            self.assertIs(arenas[key[0]], recipe.arena)
            self.assertEqual("lady-maria", recipe.donor.key)
        for key in laurence_keys:
            recipe = self.recipes[key]
            self.assertIs(arenas[key[0]], recipe.arena)
            self.assertEqual("laurence", recipe.donor.key)

        self.assertNotIn(("orphan-of-kos", "blood-starved-beast"), self.recipes)
        for key in orphan_arena_keys:
            self.assertIs(ORPHAN_ARENA_CONTRACT, self.recipes[key].arena)

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

    def test_specialized_donor_recipes_use_real_sources_and_owned_allocations(self):
        from tools.bb_enemizer.maria_contract import MARIA_EVENT_FILE
        from tools.bb_enemizer.laurence_donor import LAURENCE_EVENT_FILE
        from tools.bb_enemizer.orphan_donor import EVENT_FILE as ORPHAN_EVENT_FILE

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

        laurence = self.recipes[(arena.key, "laurence")]
        donor_source = read_blob(BUNDLE, "event/" + LAURENCE_EVENT_FILE).decode(
            "utf-8-sig"
        )
        after = event_blocks(laurence.patch(destination, donor_source))
        self.assertEqual(before[arena.completion_event], after[arena.completion_event])
        self.assertEqual({12994900, 12994901}, set(after) - set(before))
        self.assertIn("SetEventFlag(12994902, ON)", after[arena.health_bar_event])

        plan = laurence.native_plan(
            self.slots, self.npcs, self.effects, "recipe-laurence"
        )
        self.assertEqual("bb-enemizer-plan-v2", plan["format"])
        self.assertEqual("laurence", plan["boss_contract"]["donor"])
        self.assertEqual(arena.key, plan["boss_contract"]["arena"])
        self.assertEqual(
            arena.destination_count, len(plan["primary_init_source_bindings"])
        )
        self.assertEqual("c4500", plan["swaps"][0]["target"]["model_name"])
        self.assertEqual(
            {3400850},
            {
                binding["source_entity_id"]
                for binding in plan["primary_init_source_bindings"]
            },
        )

        orphan = self.recipes[(arena.key, "orphan-of-kos")]
        donor_source = read_blob(BUNDLE, "event/" + ORPHAN_EVENT_FILE).decode(
            "utf-8-sig"
        )
        after = event_blocks(orphan.patch(destination, donor_source))
        self.assertEqual(before[arena.completion_event], after[arena.completion_event])
        self.assertEqual(
            {12995500, 12995501, 12995502, 12995503, 12995504},
            set(after) - set(before),
        )
        plan = orphan.native_plan(
            self.slots, self.npcs, self.effects, "recipe-orphan"
        )
        self.assertEqual("orphan-of-kos", plan["boss_contract"]["donor"])
        self.assertEqual(arena.key, plan["boss_contract"]["arena"])
        self.assertEqual(
            2 * arena.destination_count, len(plan["boss_actor_additions"])
        )
        self.assertEqual(
            {3600800},
            {
                binding["source_entity_id"]
                for binding in plan["primary_init_source_bindings"]
            },
        )

        ludwig = self.recipes[(arena.key, "ludwig")]
        donor_source = read_blob(BUNDLE, "event/m34_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        after = event_blocks(ludwig.patch(destination, donor_source))
        self.assertEqual(before[arena.completion_event], after[arena.completion_event])
        self.assertEqual(
            {12995800, 12995801, 12995802, 12995803, 12995804, 12995805,
             12995806, 12995807, 12995808, 12995809, 12995810, 12995811},
            set(after) - set(before),
        )
        plan = ludwig.native_plan(self.slots, self.npcs, self.effects, "recipe-ludwig")
        self.assertEqual("ludwig", plan["boss_contract"]["donor"])
        self.assertEqual(arena.destination_count, len(plan["boss_actor_additions"]))
        self.assertEqual(645114, plan["boss_emevd_ffx_requirements"][0]["effect_id"])

        gascoigne = self.recipes[(arena.key, "father-gascoigne")]
        donor_source = read_blob(BUNDLE, "event/m24_01_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        after = event_blocks(gascoigne.patch(destination, donor_source))
        self.assertEqual(before[arena.completion_event], after[arena.completion_event])
        self.assertEqual(
            {12995600, 12995601, 12995602, 12995603, 12995604, 12995606},
            set(after) - set(before),
        )
        plan = gascoigne.native_plan(self.slots, self.npcs, self.effects, "recipe-gascoigne")
        self.assertEqual("father-gascoigne", plan["boss_contract"]["donor"])
        self.assertEqual(arena.destination_count, len(plan["boss_actor_additions"]))
        self.assertEqual({983100}, {row["destination_entity_id"]
                                    for row in plan["boss_actor_additions"]})

        orphan_arena = self.recipes[("orphan-of-kos", "cleric-beast")]
        destination = read_blob(BUNDLE, "event/m36_00_00_00.emevd.dcx.js").decode(
            "utf-8-sig"
        )
        donor_source = self.sources[arena.event_file]
        before = event_blocks(destination)
        after = event_blocks(orphan_arena.patch(destination, donor_source))
        self.assertEqual(before[13601800], after[13601800])
        self.assertEqual(
            {12995700, 12995701, 12995702, 12995703,
             12995705, 12995706, 12995707},
            set(after) - set(before),
        )
        plan = orphan_arena.native_plan(
            self.slots, self.npcs, self.effects, "recipe-orphan-arena"
        )
        self.assertEqual("orphan-of-kos", plan["boss_contract"]["arena"])
        self.assertEqual("cleric-beast", plan["boss_contract"]["donor"])
        self.assertEqual({3600800}, {
            row["destination_entity_id"]
            for row in plan["primary_init_source_bindings"]
        })

        final_source = read_blob(BUNDLE, "event/m21_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        for final_arena in ARENAS:
            for donor in ("gehrman", "moon-presence"):
                with self.subTest(arena=final_arena.key, donor=donor):
                    recipe = self.recipes[(final_arena.key, donor)]
                    destination = self.sources[final_arena.event_file]
                    before = event_blocks(destination)
                    after = event_blocks(recipe.patch(destination, final_source))
                    self.assertEqual(before[final_arena.completion_event],
                                     after[final_arena.completion_event])
                    plan = recipe.native_plan(self.slots, self.npcs, self.effects,
                                              "recipe-final-boss")
                    self.assertEqual(final_arena.key, plan["boss_contract"]["arena"])
                    self.assertEqual(donor, plan["boss_contract"]["donor"])
                    self.assertEqual({final_arena.actor}, {
                        row["destination_entity_id"]
                        for row in plan["primary_init_source_bindings"]
                    })
                    helpers = recipe.actor_requirements(self.slots)
                    self.assertEqual(final_arena.destination_count if donor == "gehrman" else 0,
                                     len(helpers))
                    for helper in helpers:
                        self.assertEqual("c9010_0004", helper["source_part"])
                        self.assertEqual(2100801, helper["source_entity_id"])

        wet_source = read_blob(BUNDLE, "event/m26_00_00_00.emevd.dcx.js").decode("utf-8-sig")
        for arena in ARENAS:
            with self.subTest(arena=arena.key, donor="micolash"):
                recipe = self.recipes[(arena.key, "micolash")]
                destination = self.sources[arena.event_file]
                before = event_blocks(destination)
                after = event_blocks(recipe.patch(destination, wet_source))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                plan = recipe.native_plan(self.slots, self.npcs, self.effects, "recipe-micolash")
                self.assertEqual(arena.key, plan["boss_contract"]["arena"])
                self.assertEqual("micolash", plan["boss_contract"]["donor"])
                bindings = plan["primary_init_source_bindings"]
                self.assertEqual(arena.destination_count, len(bindings))
                for binding in bindings:
                    self.assertEqual(2600850, binding["source_entity_id"])
                    self.assertEqual(0, binding["destination_talk_id_override"])
        for arena in ARENAS:
            with self.subTest(arena=arena.key, donor="mergos-wet-nurse"):
                recipe = self.recipes[(arena.key, "mergos-wet-nurse")]
                destination = self.sources[arena.event_file]
                before = event_blocks(destination)
                after = event_blocks(recipe.patch(destination, wet_source))
                self.assertEqual(before[arena.completion_event], after[arena.completion_event])
                plan = recipe.native_plan(self.slots, self.npcs, self.effects, "recipe-wet-nurse")
                self.assertEqual(arena.key, plan["boss_contract"]["arena"])
                self.assertEqual("mergos-wet-nurse", plan["boss_contract"]["donor"])
                self.assertEqual(2 * arena.destination_count, len(plan["boss_actor_additions"]))
                self.assertEqual(6 * arena.destination_count, len(plan["boss_region_additions"]))
                self.assertEqual(arena.destination_count, len(plan["boss_object_additions"]))

        for arena, terminal, actor in (("gehrman", 12101800, 2100800),
                                       ("moon-presence", 12101850, 2100810),
                                       ("micolash", 12601850, 2600850)):
            for donor in PACKAGES:
                with self.subTest(arena=arena, donor=donor.key):
                    recipe = self.recipes[(arena, donor.key)]
                    destination = read_blob(BUNDLE, "event/" + recipe.arena.event_file).decode("utf-8-sig")
                    before = event_blocks(destination)
                    after = event_blocks(recipe.patch(destination, self.sources[donor.event_file]))
                    self.assertEqual(before[terminal], after[terminal])
                    plan = recipe.native_plan(self.slots, self.npcs, self.effects, "recipe-final-arena")
                    self.assertEqual(arena, plan["boss_contract"]["arena"])
                    self.assertEqual(donor.key, plan["boss_contract"]["donor"])
                    self.assertEqual({actor}, {
                        row["destination_entity_id"] for row in plan["primary_init_source_bindings"]
                    })
                    self.assertEqual(recipe.actor_requirements(self.slots),
                                     plan.get("boss_actor_addition_requirements", []))


if __name__ == "__main__":
    unittest.main()
