from __future__ import annotations

import csv
import io
import subprocess
import sys
import unittest

from worlds.bloodborne.toast_placeholders import (
    TOAST_GOODS_END,
    TOAST_GOODS_START,
    TOAST_NAME_LIMIT,
    ToastPlacement,
    build_toast_placeholder_plan,
    display_name,
)


class ToastPlaceholderTests(unittest.TestCase):
    def placement(self, key: str, location: int, lot: int, *, important: bool = True):
        return ToastPlacement(key, location, lot, "Fire Paper x2", "oz", important)

    def test_plan_is_enabled_deterministic_and_includes_filler(self):
        placements = [
            self.placement("later", 20, 200),
            self.placement("filler", 15, 150, important=False),
            self.placement("first", 10, 100),
        ]
        first = build_toast_placeholder_plan(placements)
        second = build_toast_placeholder_plan(reversed(placements))
        self.assertEqual(first, second)
        self.assertTrue(first["enabled"])
        self.assertEqual(
            [(entry["location_key"], entry["goods_id"]) for entry in first["entries"]],
            [("first", TOAST_GOODS_START), ("filler", TOAST_GOODS_START + 1),
             ("later", TOAST_GOODS_START + 2)],
        )

    def test_names_are_bounded_and_keep_the_recipient(self):
        name = display_name("A" * 100, "other player")
        self.assertLessEqual(len(name), TOAST_NAME_LIMIT)
        self.assertTrue(name.endswith(" (other player)"))

    def test_duplicate_lot_is_refused(self):
        with self.assertRaisesRegex(ValueError, "same ItemLotParam"):
            build_toast_placeholder_plan([
                self.placement("one", 1, 10), self.placement("two", 2, 10)
            ])

    def test_unicode_names_fit_the_writer_limit_without_splitting_surrogates(self):
        name = display_name("\U0001f525" * 40, "Hunter")
        self.assertLessEqual(len(name.encode("utf-16-le")), TOAST_NAME_LIMIT * 2)
        self.assertTrue(name.endswith(" (Hunter)"))

    def test_claimed_goods_range_is_empty_in_the_bundle(self):
        text = subprocess.check_output(
            [sys.executable, "tools/bb_inputs.py", "--get", "params/EquipParamGoods.csv"],
            text=True,
            encoding="utf-8",
        )
        ids = {int(row["ID"]) for row in csv.DictReader(io.StringIO(text))}
        self.assertFalse(ids & set(range(TOAST_GOODS_START, TOAST_GOODS_END + 1)))


if __name__ == "__main__":
    unittest.main()
