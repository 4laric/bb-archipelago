import unittest

from tools.bb_enemizer.inventory import apply_archetype_tag
from tools.bb_enemizer.model import Archetype, EnemyTag, Slot, SlotPolicy, canonical_map
from tools.bb_enemizer.planner import EnemizerConfig, compatible, plan_swaps


def slot(map_name, part_name, npc, model="c1000"):
    return Slot(
        map_path=f"{map_name}.msb",
        map_name=map_name,
        part_name=part_name,
        entity_id=100,
        talk_id=0,
        collision_name="h000000",
        dummy=False,
        x=0,
        y=0,
        z=0,
        archetype=Archetype(model, npc, npc, 0),
    )


class BloodborneEnemizerTests(unittest.TestCase):
    def test_alternate_states_share_logical_slot(self):
        self.assertEqual("m24_01_00_00", canonical_map("m24_01_00_11"))

    def test_size_up_is_asymmetric(self):
        policy = SlotPolicy(True, "test", size_class="M")
        config = EnemizerConfig("seed", max_size_up=1, max_size_down=3)
        self.assertTrue(compatible(policy, "large", EnemyTag(size_class="L"), config)[0])
        self.assertFalse(compatible(policy, "huge", EnemyTag(size_class="XL"), config)[0])
        self.assertTrue(compatible(policy, "tiny", EnemyTag(size_class="XS"), config)[0])

    def test_archetype_tag_enriches_or_protects_slot(self):
        policy = SlotPolicy(True, "heuristic")
        tagged = apply_archetype_tag(
            policy, EnemyTag(size_class="L", tier="elite", locomotion="move_type_3")
        )
        self.assertEqual(("L", "elite", "move_type_3"),
                         (tagged.size_class, tagged.tier, tagged.locomotion))
        blocked = apply_archetype_tag(policy, EnemyTag(target=False))
        self.assertFalse(blocked.randomize)

    def test_family_choice_uses_closest_scaling_variant(self):
        source = slot("m22_00_00_00", "c1000_0000", 1000)
        low = slot("m23_00_00_00", "c2000_0000", 2000, "c2000")
        high = slot("m24_00_00_00", "c2000_0001", 2001, "c2000")
        policies = {
            source.key: SlotPolicy(True, "test", scaling_hp=4.0),
            low.key: SlotPolicy(True, "test", scaling_hp=1.0),
            high.key: SlotPolicy(True, "test", scaling_hp=4.0),
        }
        tags = {
            low.archetype.key: EnemyTag(scaling_hp=1.0),
            high.archetype.key: EnemyTag(scaling_hp=4.0),
            source.archetype.key: EnemyTag(scaling_hp=4.0),
        }
        swaps, _ = plan_swaps([source, low, high], policies, tags, EnemizerConfig("x"))
        chosen = next(s for s in swaps if s.logical_key == source.logical_key)
        self.assertEqual(2001, chosen.target.npc_param_id)

    def test_plan_is_stable_and_couples_alternate_state_copies(self):
        slots = [
            slot("m24_01_00_00", "c1000_0000", 1000),
            slot("m24_01_00_11", "c1000_0000", 1000),
            slot("m22_00_00_00", "c2000_0000", 2000, "c2000"),
            slot("m23_00_00_00", "c3000_0000", 3000, "c3000"),
        ]
        policies = {s.key: SlotPolicy(True, "test") for s in slots}
        first, rejected = plan_swaps(slots, policies, {}, EnemizerConfig("12345"))
        second, _ = plan_swaps(list(reversed(slots)), policies, {}, EnemizerConfig("12345"))
        self.assertEqual(0, len(rejected))
        self.assertEqual([s.json() for s in first], [s.json() for s in second])
        coupled = next(s for s in first if s.logical_key.startswith("m24_01"))
        self.assertEqual(2, len(coupled.destination_keys))
        self.assertEqual(2, len(coupled.destination_sources))

    def test_alternate_copy_retains_its_physical_source_tuple(self):
        a = slot("m24_01_00_00", "c1000_0000", 1000)
        b = Slot(**{**a.__dict__, "map_path": "m24_01_00_11.msb", "map_name": "m24_01_00_11",
                    "archetype": Archetype("c1000", 1000, 1001, 0)})
        donor = slot("m22_00_00_00", "c2000_0000", 2000, "c2000")
        policies = {s.key: SlotPolicy(True, "test") for s in (a, b, donor)}
        swaps, _ = plan_swaps([a, b, donor], policies, {}, EnemizerConfig("x"))
        coupled = next(s for s in swaps if s.logical_key == a.logical_key)
        self.assertEqual(1000, coupled.destination_sources[a.key].think_param_id)
        self.assertEqual(1001, coupled.destination_sources[b.key].think_param_id)

    def test_one_protected_copy_protects_logical_slot(self):
        a = slot("m24_01_00_00", "c1000_0000", 1000)
        b = slot("m24_01_00_11", "c1000_0000", 1000)
        donor = slot("m22_00_00_00", "c2000_0000", 2000, "c2000")
        policies = {
            a.key: SlotPolicy(True, "test"),
            b.key: SlotPolicy(False, "scripted in alternate state"),
            donor.key: SlotPolicy(True, "test"),
        }
        swaps, rejected = plan_swaps([a, b, donor], policies, {}, EnemizerConfig("x"))
        self.assertFalse(any(s.logical_key == a.logical_key for s in swaps))
        self.assertTrue(any(r["logical_key"] == a.logical_key for r in rejected))

    def test_protected_archetype_cannot_leak_into_target_pool(self):
        ordinary_a = slot("m22_00_00_00", "c1000_0000", 1000)
        ordinary_b = slot("m23_00_00_00", "c2000_0000", 2000, "c2000")
        protected = slot("m24_00_00_00", "c9000_0000", 9000, "c9000")
        policies = {
            ordinary_a.key: SlotPolicy(True, "test"),
            ordinary_b.key: SlotPolicy(True, "test"),
            protected.key: SlotPolicy(False, "talk-bound"),
        }
        swaps, _ = plan_swaps(
            [ordinary_a, ordinary_b, protected], policies, {}, EnemizerConfig("x")
        )
        self.assertTrue(swaps)
        self.assertNotIn(9000, {swap.target.npc_param_id for swap in swaps})


if __name__ == "__main__":
    unittest.main()
