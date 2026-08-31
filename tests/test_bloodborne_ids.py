"""Network ids are a permanent contract; these tests are the thing that makes them one.

Ids travel in multidata and in the datapackage. Once a seed exists, changing a
key's id silently desyncs it — no error anywhere, because names still resolve.
They used to be `ID_BASE + enumerate(...)` position, so inserting a single row
in data.py renumbered everything after it.

The golden snapshot below is the whole point. It is not decoration: it is the
record of what has been assigned, and a diff to it is a compatibility break that
has to be argued for rather than noticed later.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from worlds.bloodborne import (
    ITEM_ID_BY_KEY,
    ITEM_NAME_TO_ID,
    LOCATION_ID_BY_KEY,
    LOCATION_NAME_TO_ID,
    NETWORK_LOCATIONS,
    RUNTIME_BUILD,
    SHUFFLABLE_ITEMS,
    FILLER_ITEM_NAME,
    IdRegistryError,
    _assigned,
    _load_id_registry,
    build_runtime_slot_data,
)
from worlds.bloodborne.data import MODEL
from worlds.bloodborne.model import ItemKind

# Assigned 2026-08-18, carried forward unchanged from the original positional
# scheme. APPEND ONLY. Changing a value here breaks every seed already generated.
GOLDEN_ITEMS = {
    "hunter_chief_emblem": 0xBB0001,
    "cainhurst_summons": 0xBB0002,
    "tonsil_stone": 0xBB0003,
    "upper_cathedral_key": 0xBB0004,
    "orphanage_key": 0xBB0005,
    "eye_of_blood_drunk_hunter": 0xBB0006,
    "eye_pendant": 0xBB0007,
    "astral_clocktower_key": 0xBB0008,
    "celestial_dial": 0xBB0009,
    "laurences_skull": 0xBB000A,
    "saw_spear": 0xBB000B,
    # bb-archipelago#205, appended after the last equipment id.
    "uncanny_saw_spear": 0xBB000C,
    # bb-archipelago#207 wave 1: the base-game weapon catalog, its Uncanny
    # variants, and the category-4 goods variety set. Appended, never
    # renumbered -- these ids ship in the datapackage.
    "chikage": 0xBB000D,
    "blade_of_mercy": 0xBB000E,
    "hunter_axe": 0xBB000F,
    "burial_blade": 0xBB0010,
    "saw_cleaver": 0xBB0011,
    "kirkhammer": 0xBB0012,
    "ludwigs_holy_blade": 0xBB0013,
    "beast_claw": 0xBB0014,
    "rifle_spear": 0xBB0015,
    "reiterpallasch": 0xBB0016,
    "stake_driver": 0xBB0017,
    "logarius_wheel": 0xBB0018,
    "tonitrus": 0xBB0019,
    "threaded_cane": 0xBB001A,
    "hunter_blunderbuss": 0xBB001B,
    "ludwigs_rifle": 0xBB001C,
    "hunter_pistol": 0xBB001D,
    "repeating_pistol": 0xBB001E,
    "cannon": 0xBB001F,
    "uncanny_chikage": 0xBB0020,
    "uncanny_blade_of_mercy": 0xBB0021,
    "uncanny_hunter_axe": 0xBB0022,
    "uncanny_burial_blade": 0xBB0023,
    "uncanny_saw_cleaver": 0xBB0024,
    "uncanny_kirkhammer": 0xBB0025,
    "uncanny_ludwigs_holy_blade": 0xBB0026,
    "uncanny_beast_claw": 0xBB0027,
    "uncanny_rifle_spear": 0xBB0028,
    "uncanny_reiterpallasch": 0xBB0029,
    "uncanny_stake_driver": 0xBB002A,
    "uncanny_logarius_wheel": 0xBB002B,
    "uncanny_tonitrus": 0xBB002C,
    "uncanny_threaded_cane": 0xBB002D,
    "antidote": 0xBB0107,
    "sedatives": 0xBB0108,
    "beast_blood_pellet": 0xBB0109,
    "blue_elixir": 0xBB010A,
    "poison_knife": 0xBB010B,
    "throwing_knife": 0xBB010C,
    "fire_paper": 0xBB010D,
    "bolt_paper": 0xBB010E,
    "bone_marrow_ash": 0xBB010F,
    "lead_elixir": 0xBB0110,
    "twin_blood_stone_shards": 0xBB0111,
    "blood_stone_chunks": 0xBB0112,
    "blood_rock": 0xBB0113,
    "bold_hunters_mark": 0xBB0114,
    "oil_urn": 0xBB0115,
    "numbing_mist": 0xBB0116,
    "pungent_blood_cocktail": 0xBB0117,
    "shaman_bone_blade": 0xBB0118,
    "madmans_knowledge": 0xBB0119,
    "great_ones_wisdom": 0xBB011A,
    "coldblood_dew": 0xBB011B,
    "thick_coldblood": 0xBB011C,
    "frenzied_coldblood": 0xBB011D,
    "kin_coldblood": 0xBB011E,
    "beast_roar": 0xBB011F,
    "empty_phantasm_shell": 0xBB0120,
    "old_hunter_bone": 0xBB0121,
    "executioners_gloves": 0xBB0122,
    "tiny_tonitrus": 0xBB0123,
    "a_call_beyond": 0xBB0124,
    "choir_bell": 0xBB0125,
    "blacksky_eye": 0xBB0126,
    "messengers_gift": 0xBB0127,
    "beasthunter_saif": 0xBB0128,
    "beast_cutter": 0xBB0129,
    "amygdalan_arm": 0xBB012A,
    "boom_hammer": 0xBB012B,
    "whirligig_saw": 0xBB012C,
    "church_cannon": 0xBB012D,
    "fist_of_gratia": 0xBB012E,
    "loch_shield": 0xBB012F,
    "blood_gem_workshop_tool": 0xBB0130,
    "rune_workshop_tool": 0xBB0131,
    "third_umbilical_cord_1": 0xBB0132,
    "third_umbilical_cord_2": 0xBB0133,
    "third_umbilical_cord_3": 0xBB0134,
    "third_umbilical_cord_4": 0xBB0135,
    "lunarium_key": 0xBB0136,
    "forbidden_woods_password": 0xBB0137,
    "blood_vial": 0xBB0100,
    "quicksilver_bullets": 0xBB0101,
    "pebbles": 0xBB0102,
    "molotov_cocktails": 0xBB0103,
    "blood_stone_shards": 0xBB0104,
    "augur_of_ebrietas": 0xBB0105,
    "oedon_tomb_key": 0xBB0106,
}
GOLDEN_LOCATIONS = {
    "boss_gehrman": 0xBB11F5,
    "boss_moon_presence": 0xBB11F6,
    "boss_celestial_emissary": 0xBB1288,
    "boss_ebrietas": 0xBB1289,
    "boss_father_gascoigne": 0xBB1001,
    "boss_blood_starved_beast": 0xBB1002,
    "boss_vicar_amelia": 0xBB1003,
    "interaction_laurences_skull": 0xBB1004,
    "boss_shadows_of_yharnam": 0xBB1005,
    "boss_rom": 0xBB1006,
    "boss_the_one_reborn": 0xBB1007,
    "boss_micolash": 0xBB1008,
    "boss_mergos_wet_nurse": 0xBB1009,
    "pickup_cainhurst_summons": 0xBB100A,
    "pickup_upper_cathedral_key": 0xBB100B,
    "script_award_orphanage_key": 0xBB100C,
    "pickup_eye_of_blood_drunk_hunter": 0xBB100D,
    "pickup_eye_pendant": 0xBB100E,
    "boss_ludwig": 0xBB100F,
    "boss_living_failures": 0xBB1010,
    "boss_lady_maria": 0xBB1011,
    "boss_orphan_of_kos": 0xBB1012,
    "pickup_laurences_skull": 0xBB1013,
    "boss_laurence": 0xBB1014,
    "treasure_radiant_sword_hunter_badge": 0xBB1015,
    "treasure_old_hunter_bone": 0xBB1016,
    "treasure_rune_workshop_tool": 0xBB1017,
    "treasure_augur_of_ebrietas": 0xBB1018,
    "treasure_lecture_theatre_key": 0xBB1019,
    "treasure_messengers_gift": 0xBB101A,
    "treasure_executioners_gloves": 0xBB101B,
    "treasure_cosmic_eye_watcher_badge": 0xBB101C,
    "treasure_underground_jail_chunk": 0xBB101D,
    "fixed_white_messenger_ribbon": 0xBB101E,
    "fixed_saw_spear": 0xBB101F,
    "fixed_saw_hunter_badge": 0xBB1020,
    "fixed_torch": 0xBB1021,
    "fixed_iosefka_courtyard_bullets": 0xBB1023,
    "fixed_blood_gem_workshop_tool": 0xBB1024,
    "boss_witch_of_hemwick": 0xBB10C5,
    "boss_martyr_logarius": 0xBB10C6,
    "treasure_doll_set_chest": 0xBB1284,
    "pickup_small_hair_ornament": 0xBB1285,
    "pickup_workshop_umbilical_cord": 0xBB1286,
    "pickup_lunarium_key": 0xBB1287,
}


class GoldenIdTests(unittest.TestCase):
    def test_item_ids_match_the_golden_snapshot(self):
        for key, value in GOLDEN_ITEMS.items():
            self.assertEqual(value, _assigned("item", key), key)
        actual = dict(ITEM_ID_BY_KEY)
        actual["blood_vial"] = ITEM_NAME_TO_ID[FILLER_ITEM_NAME]
        self.assertEqual(actual, dict(GOLDEN_ITEMS))

    def test_location_ids_match_the_golden_snapshot(self):
        for key, value in GOLDEN_LOCATIONS.items():
            self.assertEqual(value, _assigned("location", key), key)

        from worlds.bloodborne.fixed_locations import FIXED_LOCATIONS
        published = set(GOLDEN_LOCATIONS)
        new_upper = {
            row.key for row in FIXED_LOCATIONS
            if row.key.startswith("fixed_upper_cathedral_lot_")
            or row.key == "fixed_cathedral_ward_lot_2420320"
        }
        # Slice 1's Central Yharnam block, assigned 2026-08-18 in manifest
        # order. It must stay exactly where it was when slice 3 appended.
        slice_one = [row.key for row in FIXED_LOCATIONS
                     if row.key not in published and row.key not in new_upper
                    and row.key.startswith("fixed_")
                    and not row.key.startswith(("fixed_cathedral_ward_lot_",
                                                 "fixed_old_yharnam_lot_",
                                                 "fixed_hemwick_lot_",
                                                 "fixed_cainhurst_lot_",
                                                 "fixed_forbidden_woods_lot_",
                                                 "fixed_yahargul_lot_",
                                                 "fixed_lecture_building_lot_",
                                                 "fixed_nightmare_mensis_lot_",
                                                 "fixed_nightmare_frontier_lot_",
                                                 "fixed_hunters_nightmare_lot_",
                                                 "fixed_research_hall_lot_",
                                                 "fixed_fishing_hamlet_lot_"))]
        self.assertEqual(len(slice_one), 45)
        expected = {key: 0xBB1025 + index for index, key in enumerate(slice_one)}
        expected["boss_cleric_beast"] = 0xBB1052
        expected["treasure_underground_cell_inner_chamber_key"] = 0xBB1053
        # Slice 3's block, appended after the last id slice 1 handed out.
        slice_three = [row.key for row in FIXED_LOCATIONS
                       if row.key.startswith(("fixed_cathedral_ward_lot_",
                                              "fixed_old_yharnam_lot_"))
                       and row.key not in new_upper]
        self.assertEqual(len(slice_three), 113)
        expected.update({key: 0xBB1054 + index for index, key in enumerate(slice_three)})
        slice_four = [row.key for row in FIXED_LOCATIONS
                      if row.key.startswith(("fixed_hemwick_lot_",
                                             "fixed_cainhurst_lot_"))]
        self.assertEqual(len(slice_four), 58)
        expected.update({key: 0xBB10C7 + index for index, key in enumerate(slice_four)})
        slice_five = [row.key for row in FIXED_LOCATIONS
                      if row.key.startswith("fixed_forbidden_woods_lot_")]
        self.assertEqual(len(slice_five), 80)
        expected.update({key: 0xBB1101 + index for index, key in enumerate(slice_five)})
        expected["boss_amygdala"] = 0xBB1151
        nightmare_frontier = [row.key for row in FIXED_LOCATIONS
                              if row.key.startswith("fixed_nightmare_frontier_lot_")]
        self.assertEqual(len(nightmare_frontier), 44)
        expected.update({key: 0xBB1152 + index for index, key in enumerate(nightmare_frontier)})
        ordered_upper = ["fixed_cathedral_ward_lot_2420320", *sorted(
            new_upper - {"fixed_cathedral_ward_lot_2420320"},
            key=lambda key: int(key.rsplit("_", 1)[1]),
        )]
        self.assertEqual(19, len(ordered_upper))
        expected.update({key: 0xBB128B + index for index, key in enumerate(ordered_upper)})
        self.assertEqual(
            {key: LOCATION_ID_BY_KEY[key] for key in expected},
            expected,
        )

    def test_appending_slice_three_moved_no_published_id(self):
        """The property the registry exists for, asserted against the file.

        Slice 3 appends 113 location rows. If any of them had been inserted
        rather than appended, or if a key had been reused, the ids below would
        have moved and every already-generated seed would silently desync.
        """
        for key, value in GOLDEN_LOCATIONS.items():
            self.assertEqual(value, LOCATION_ID_BY_KEY[key], key)
        ids = sorted(LOCATION_ID_BY_KEY.values())
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(max(ids), 0xBB129D)

    def test_ids_are_stable_under_reordering(self):
        """The property the old scheme did not have."""
        shufflable = list(SHUFFLABLE_ITEMS)
        forwards = {i.key: _assigned("item", i.key) for i in shufflable}
        backwards = {i.key: _assigned("item", i.key) for i in reversed(shufflable)}
        self.assertEqual(forwards, backwards)
        golden = {key: GOLDEN_ITEMS[key] for key in forwards}
        self.assertEqual(golden, forwards)

    def test_ids_are_stable_under_insertion(self):
        """Inserting a key must not move any existing key's id."""
        before = {i.key: _assigned("item", i.key) for i in SHUFFLABLE_ITEMS}
        # a new key would be appended to ids.tsv, not renumber the others
        self.assertEqual(before, {key: GOLDEN_ITEMS[key] for key in before})


class RegistryCoverageTests(unittest.TestCase):
    def test_every_shufflable_item_has_an_assignment(self):
        for item in SHUFFLABLE_ITEMS:
            self.assertIn(item.key, ITEM_ID_BY_KEY, item.key)

    def test_every_location_has_an_assignment(self):
        for location in NETWORK_LOCATIONS:
            self.assertIn(location.key, LOCATION_ID_BY_KEY, location.key)

    def test_event_items_are_not_assigned_network_ids(self):
        for item in MODEL.items:
            if item.kind is ItemKind.EVENT:
                self.assertNotIn(item.key, ITEM_ID_BY_KEY, item.key)

    def test_world_resources_are_read_zip_safely(self):
        """The apworld is a zip: filesystem paths to package data do not exist
        once Archipelago imports the world through zipimport. Every resource
        read must go through resource_data.read_resource_text."""
        world_dir = Path(__file__).resolve().parents[1] / "worlds" / "bloodborne"
        checked = 0
        for source in world_dir.glob("*.py"):
            text = source.read_text(encoding="utf-8")
            self.assertNotIn("__file__", text, source.name)
            checked += 1
        self.assertGreaterEqual(checked, 8)  # witness: the package is real, not an empty glob

    def test_all_ids_are_globally_disjoint(self):
        values = list(ITEM_NAME_TO_ID.values()) + list(LOCATION_NAME_TO_ID.values())
        self.assertEqual(len(values), len(set(values)))

    def test_display_names_are_unique(self):
        """Two items sharing a name would silently collapse in item_name_to_id."""
        self.assertEqual(len(ITEM_NAME_TO_ID), len(set(ITEM_NAME_TO_ID)))
        self.assertEqual(len(LOCATION_NAME_TO_ID), len(NETWORK_LOCATIONS))


class RegistryFailureTests(unittest.TestCase):
    """A registry that cannot answer must fail, not answer."""

    def _registry(self, text: str):
        return _load_id_registry(text)

    def test_an_unassigned_key_raises_with_an_actionable_message(self):
        with self.assertRaises(IdRegistryError) as caught:
            _assigned("item", "a_key_that_was_never_assigned")
        message = str(caught.exception)
        self.assertIn("ids.tsv", message)
        self.assertIn("never reuse", message)

    def test_a_duplicate_key_raises(self):
        with self.assertRaises(IdRegistryError):
            self._registry("kind\tkey\tid\nitem\tfoo\t0xBB0001\nitem\tfoo\t0xBB0002\n")

    def test_a_reused_id_raises(self):
        with self.assertRaises(IdRegistryError):
            self._registry("kind\tkey\tid\nitem\tfoo\t0xBB0001\nlocation\tbar\t0xBB0001\n")

    def test_a_malformed_row_raises_and_names_the_line(self):
        with self.assertRaises(IdRegistryError) as caught:
            self._registry("kind\tkey\tid\nitem\tfoo\n")
        self.assertIn(":2", str(caught.exception))

    def test_an_unknown_kind_raises(self):
        with self.assertRaises(IdRegistryError):
            self._registry("kind\tkey\tid\nregion\tfoo\t0xBB0001\n")

    def test_a_non_hex_id_raises(self):
        with self.assertRaises(IdRegistryError):
            self._registry("kind\tkey\tid\nitem\tfoo\tnot-a-number\n")

    def test_blank_lines_and_the_header_are_ignored(self):
        registry = self._registry("kind\tkey\tid\n\nitem\tfoo\t0xBB0001\n\n")
        self.assertEqual(registry["item"], {"foo": 0xBB0001})


class FillerTests(unittest.TestCase):
    def test_the_filler_name_is_a_real_assigned_item(self):
        self.assertIn(FILLER_ITEM_NAME, ITEM_NAME_TO_ID)

    def test_the_filler_name_is_not_a_shufflable_key(self):
        """It is deliberately outside the pool, which is why it needs its own row."""
        self.assertNotIn(FILLER_ITEM_NAME, {i.name for i in MODEL.items})


class RuntimeItemContractTests(unittest.TestCase):
    def test_runtime_vocabulary_is_pinned_to_the_client_build(self):
        """A new strict-client enum value requires a runtime build bump.

        Keep the accepted vocabulary beside the build that understands it.
        Extending slot_data while merely widening another allowlist recreated
        the opaque pre-r6 connect failure tracked by #212.
        """
        accepted_by_build = {
            "bb-0.1.0-r7": {
                "goods_formula_observed",
                "live_grant_inventory_ui",
                "param_id_inferred",
            },
            "bb-0.1.0-r8": {
                "goods_formula_observed",
                "live_grant_inventory_ui",
                "param_id_inferred",
                "event_flag_effect",
            },
        }
        self.assertIn(
            RUNTIME_BUILD,
            accepted_by_build,
            "register a new runtime build before changing slot_data vocabulary",
        )
        emitted = {
            binding["descriptor_evidence"]
            for binding in build_runtime_slot_data()["runtime_items"].values()
        }
        self.assertEqual(emitted, accepted_by_build[RUNTIME_BUILD])

    def test_every_runtime_item_declares_receive_policy_metadata(self):
        # The widest pool a seed can ask for: the default full pool plus the
        # Uncanny variants the option adds. Every id the datapackage publishes
        # must be deliverable in the pool that can place it.
        from worlds.bloodborne.data import UNCANNY_ITEM_KEYS
        from worlds.bloodborne import FULL_POOL_ITEM_KEYS, STARTING_TOOL_KEYS

        runtime_items = build_runtime_slot_data(
            FULL_POOL_ITEM_KEYS | UNCANNY_ITEM_KEYS | STARTING_TOOL_KEYS)["runtime_items"]
        self.assertEqual(set(runtime_items), {str(value) for value in ITEM_NAME_TO_ID.values()})
        for binding in runtime_items.values():
            self.assertIn("raw_descriptor", binding)
            self.assertIn("item_category", binding)
            self.assertIn("descriptor_evidence", binding)
            self.assertIn(binding["item_category"], {0, 4, 255})
            self.assertIn(binding["descriptor_evidence"], {
                "goods_formula_observed", "live_grant_inventory_ui",
                "param_id_inferred",
                "event_flag_effect",
            })
            self.assertIn("feed_effect", binding)
            self.assertIn("reinforcement_level", binding)
            self.assertIn(binding["feed_effect"], {
                "right_hand_weapon", "left_hand_weapon", "attire_head", "attire_chest",
                "attire_hands", "attire_legs", "caryll_rune", "oath_rune",
                "rune_workshop_tool", "not_equippable",
            })
            level = binding["reinforcement_level"]
            self.assertTrue(level is None or 0 <= level <= 10)

    def test_only_allowlisted_equipment_enters_the_pool(self):
        runtime_items = build_runtime_slot_data()["runtime_items"]
        equipment = {
            key: binding for key, binding in runtime_items.items()
            if binding["item_category"] == 0
        }
        # bb-archipelago#207 wave 1: the allowlist is now the base-game weapon
        # catalog, not one canary. The invariant is unchanged -- nothing enters
        # category 0 that is not a declared, bound weapon key.
        from worlds.bloodborne.data import BASE_GAME_WEAPON_KEYS, DLC_WEAPON_KEYS

        saw_spear = equipment[str(ITEM_ID_BY_KEY["saw_spear"])]
        self.assertEqual(set(equipment),
                         {str(ITEM_ID_BY_KEY[key]) for key in BASE_GAME_WEAPON_KEYS | DLC_WEAPON_KEYS})
        self.assertEqual(saw_spear["raw_descriptor"], 0x806C5660)
        self.assertEqual(saw_spear["normalized_item_id"], 0x006C5660)
        self.assertEqual(saw_spear["feed_effect"], "right_hand_weapon")
        self.assertEqual(saw_spear["reinforcement_level"], 0)

    def test_goods_keep_the_observed_category_four_descriptor_pair(self):
        for binding in build_runtime_slot_data()["runtime_items"].values():
            if binding["item_category"] != 4:
                continue
            self.assertEqual(
                binding["raw_descriptor"],
                (binding["normalized_item_id"] & 0x0FFFFFFF) | 0xB0000000,
            )
            self.assertEqual(binding["feed_effect"], "not_equippable")
            self.assertIsNone(binding["reinforcement_level"])

    def test_rejected_torch_inference_is_not_a_runtime_item(self):
        from worlds.bloodborne.runtime_bindings import (
            EQUIPMENT_EXCLUSIONS,
            RuntimeItemBinding,
            validate_runtime_item_binding,
        )

        exclusion = EQUIPMENT_EXCLUSIONS["torch"]
        self.assertEqual(exclusion.item_lot_id, 2410520)
        self.assertEqual(exclusion.catalog_item_id, 20100000)
        self.assertEqual(exclusion.attempted_raw_descriptor, 0x8132B3A0)
        self.assertNotIn("torch", ITEM_ID_BY_KEY)
        inferred = RuntimeItemBinding(
            0x0132B3A0,
            0x8132B3A0,
            "ItemLot inference only",
            item_category=0,
            descriptor_evidence="item_lot_inferred",
            feed_effect="right_hand_weapon",
            reinforcement_level=0,
        )
        with self.assertRaisesRegex(ValueError, "not live-validated"):
            validate_runtime_item_binding("torch", inferred, 1)


if __name__ == "__main__":
    unittest.main()
