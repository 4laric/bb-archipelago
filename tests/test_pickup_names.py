from copy import deepcopy
import unittest

from bb_launcher.core import ValidationError
from bb_launcher.pickup_names import pickup_name_plan
from worlds.bloodborne.toast_placeholders import ToastPlacement, build_toast_placeholder_plan


class PickupNameValidationTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_toast_placeholder_plan([
            ToastPlacement("first", 1, 100, "Saw Cleaver", "Hunter", True),
            ToastPlacement("second", 2, 200, "Fire Paper", "Friend", True),
        ])

    def test_canary_does_not_promote_or_mutate_the_seed(self):
        original = deepcopy(self.plan)
        selected = pickup_name_plan(self.plan, canary_location="second")
        self.assertFalse(selected["enabled"])
        self.assertEqual([e["location_key"] for e in selected["entries"]], ["second"])
        self.assertEqual(self.plan, original)
        self.assertTrue(pickup_name_plan(self.plan)["enabled"])

    def test_missing_canary_is_actionable(self):
        with self.assertRaisesRegex(ValidationError, "no named pickup"):
            pickup_name_plan(self.plan, canary_location="missing")
        with self.assertRaisesRegex(ValidationError, "generate a new seed"):
            pickup_name_plan(None, canary_location="first")

    def test_all_pickups_can_be_tested_without_a_location_restriction(self):
        original = deepcopy(self.plan)
        selected = pickup_name_plan(self.plan, canary_location="*")
        self.assertEqual(selected["entries"], original["entries"])
        self.assertEqual(len(selected["entries"]), 2)
        self.assertFalse(selected["enabled"])
        self.assertEqual(self.plan, original)

    def test_refuses_collisions_bad_ids_and_malformed_names(self):
        for field, bad in [("goods_id", 999999), ("item_lot_id", True),
                           ("display_name", ""), ("display_name", "A" * 49),
                           ("display_name", "bad\x00name"), ("location_key", None)]:
            with self.subTest(field=field, bad=bad):
                plan = deepcopy(self.plan)
                plan["entries"][0][field] = bad
                with self.assertRaises(ValidationError):
                    pickup_name_plan(plan)
        for field in ("location_id", "item_lot_id", "goods_id", "location_key"):
            with self.subTest(field=field):
                plan = deepcopy(self.plan)
                plan["entries"][1][field] = plan["entries"][0][field]
                with self.assertRaisesRegex(ValidationError, "duplicate"):
                    pickup_name_plan(plan)
