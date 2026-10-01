import tempfile
import unittest
from pathlib import Path

from tools.bb_inputs import read_blob
from tools.bb_enemizer import chalice_gascoigne as route
from tools.bb_enemizer.boss_canary import event_blocks
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.chalice_recipes import chalice_recipes
from tools.build_boss_encounters import good_boss_routes
from tools.bb_enemizer.good_boss_pool import assign_good_bosses, GOOD_FAMILIES

BUNDLE = Path(__file__).resolve().parents[1] / "research/bb_inputs.db"


class ChaliceGascoigneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.destination = read_blob(BUNDLE, "event/" + route.ARENA.event_file).decode("utf-8-sig")
        cls.common = read_blob(BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "slots.tsv"
            inventory.write_bytes(read_blob(BUNDLE, "mined/msb_enemies.tsv"))
            cls.slots = load_slots(inventory, fixed_maps_only=False)
        cls.npcs, cls.effects = load_params(BUNDLE)

    def test_all_three_donors_preserve_rewards_guest_entry_and_retire_beast_ai(self):
        before = event_blocks(self.destination)
        for donor in route.humanoid.DONORS.values():
            after = event_blocks(route.patch_chalice_at_gascoigne(self.destination, donor, self.common))
            self.assertEqual(before[12411800], after[12411800])
            self.assertEqual(before[12411803], after[12411803])
            self.assertNotIn("12415238, 2412820", after[0])
            self.assertNotIn("CreateReferredDamagePair", after[12414802])
            self.assertIn("EventFlag(12414223)", after[12414802])
            self.assertIn("CharacterHasEventMessage(2410810, 500)", after[12414803])
            for event in (12414807, 12414808, 12414809):
                self.assertIn("EndEvent();", after[event])
                self.assertNotIn("RequestCharacterAI", after[event])
            cleanup = after[route.gascoigne.PROXY_CLEANUP_EVENT]
            self.assertLess(cleanup.index("WaitFor(EventFlag(12411800))"), cleanup.index("ForceCharacterDeath(2410811"))
            with self.assertRaises(ValueError):
                route.patch_chalice_at_gascoigne(self.destination, donor, self.common.replace("SetCharacterAIState", "UnknownInstruction"))

    def test_native_states_retain_provenance_and_shared_bank_assets(self):
        recipes = chalice_recipes()
        for donor in route.humanoid.DONORS.values():
            plan = recipes[(route.ARENA.key, donor.key)].native_plan(self.slots, self.npcs, self.effects, "gascoigne")
            self.assertEqual(3, len(plan["swaps"][0]["destination_keys"]))
            self.assertEqual(3, len(plan["primary_init_source_bindings"]))
            self.assertEqual(3, len(plan["boss_contract"]["retained_destination_helpers"]))
            for row in plan["primary_init_source_bindings"]:
                self.assertEqual(donor.part_sha256, row["source_provenance"]["part_sha256"])
                self.assertEqual(241330, row["destination_original_talk_id"])
            for bank in plan["boss_character_ffx_bank_requirements"]:
                self.assertEqual("frpg_sfxbnd_m24_01.ffxbnd.dcx", bank["destination_ffx_file"])

    def test_each_new_route_can_complete_a_good_pool_assignment(self):
        routes = good_boss_routes()
        for donor in route.humanoid.DONORS.values():
            forbidden = [{(arena, key)} for arena, key in routes
                         if arena == route.ARENA.key and key != donor.key]
            assignment = assign_good_bosses("forced-chalice-gascoigne", routes,
                allow_self=False, forbidden_combinations=forbidden)
            self.assertEqual(donor.key, assignment.arena_to_donor[route.ARENA.key])
            self.assertEqual(set(GOOD_FAMILIES), set(assignment.arena_to_family.values()))
