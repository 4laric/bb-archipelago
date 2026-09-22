"""Golden contracts for the declared multi-actor boss rosters."""
from dataclasses import replace
import unittest

from tools.bb_enemizer.boss_actor_rosters import BY_KEY, ROSTERS, verify_rosters


class BossActorRosterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.verified = {item.roster.key: item for item in verify_rosters()}

    def test_all_ten_rosters_are_source_pinned_and_placeable(self):
        self.assertEqual(10, len(ROSTERS))
        self.assertEqual(set(BY_KEY), set(self.verified))
        for result in self.verified.values():
            self.assertEqual(64, len(result.roster.source_sha256))
            self.assertTrue(result.roster.witnesses)
            self.assertTrue(result.placements)
            for placement in result.placements:
                self.assertTrue(placement.key)
                self.assertTrue(placement.logical_key)
                self.assertEqual(3, len(placement.position))

    def test_source_hash_mismatch_fails_closed(self):
        altered = replace(BY_KEY["ludwig"], source_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "source hash changed"):
            verify_rosters(rosters=(altered,))

    def test_witch_support_and_generators_are_not_lost(self):
        roster = BY_KEY["witch_of_hemwick"]
        self.assertEqual({2200810, 2200811, 2200812},
                         {actor.entity_id for actor in roster.actors if actor.role == "support"})
        self.assertEqual((2205000, 2205001, 2205002), roster.generators)
        self.assertIn((12204811, (2200800, 2200810)),
                      {witness.fingerprint for witness in roster.witnesses})

    def test_shadows_keep_generators_and_parameterized_assistants(self):
        roster = BY_KEY["shadows_of_yharnam"]
        self.assertEqual((2705001, 2705002, 2705003), roster.generators)
        ids = {actor.entity_id for actor in roster.actors}
        self.assertTrue({2700803, 2700804, 2700805}.issubset(ids))
        self.assertTrue({2700810, 2700811, 2700813, 2700814}.issubset(ids))
        self.assertIn((0, (2700810, 2700811, 2700813, 2700814)),
                      {witness.fingerprint for witness in roster.witnesses})

    def test_living_failures_controller_is_a_combat_support_actor(self):
        roster = BY_KEY["living_failures"]
        roles = {actor.entity_id: actor.role for actor in roster.actors}
        self.assertEqual("support", roles[3500860])
        self.assertIn((13505680, (3500851, 3500852, 3500853, 3500854, 3500860)),
                      {witness.fingerprint for witness in roster.witnesses})

    def test_orphan_excludes_postfight_actor_and_wet_nurse_marks_unresolved_proxy(self):
        orphan = BY_KEY["orphan_of_kos"]
        orphan_ids = {actor.entity_id for actor in orphan.actors}
        self.assertIn(3600803, orphan_ids)
        self.assertNotIn(3600802, orphan_ids)
        self.assertEqual((3600802,), orphan.excluded_destination_entities)
        wet = self.verified["mergos_wet_nurse"]
        self.assertEqual((2600803,), wet.roster.unresolved_entities)
        self.assertNotIn(2600803, {placement.entity_id for placement in wet.placements})


if __name__ == "__main__":
    unittest.main()
