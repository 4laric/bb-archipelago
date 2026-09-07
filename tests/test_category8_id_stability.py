"""Category-8 award identities must never move (bb-archipelago#388).

An award row's token goods id, private award lot and acknowledgement flag are
all derived from its POSITION: the pilots first, then one row per category-8
entry of ``FIXED_LOCATIONS`` in catalog order. The acknowledgement flag is the
save-resident record that a delivery already happened, so renumbering one does
not merely rename an identity -- it tells a live save that a rune it already
received has not arrived, or that one it has not received has.

This module is the snapshot that makes that failure loud. It was taken from
``origin/main`` before #388 appended the first non-catalog award row, and every
row in it must keep exactly the identity it had then.
"""

from __future__ import annotations

import unittest

from worlds.bloodborne.category8_awards import (
    CATEGORY8_AWARDS,
    EVENT_AWARD_BAND,
    _EVENT_AWARDS,
    _GENERATED,
    _PILOTS,
)


# (item_key, token_goods_id, item_lot_id, ack_flag, source_lot_id), in order.
GOLDEN_CATEGORY8_IDENTITIES = (
    ('caryll_rune_communion_1', 9800, 98000000, 12400990, 2400640),
    ('blood_gem_old_yharnam_123000', 9801, 98000010, 12400991, 2300040),
    ('category8_central_yharnam_lot_2410640', 9802, 98000020, 12400900, 2410640),
    ('category8_cathedral_ward_lot_2400300', 9803, 98000030, 12400901, 2400300),
    ('category8_cathedral_ward_lot_2400430', 9804, 98000040, 12400902, 2400430),
    ('category8_cathedral_ward_lot_2400760', 9805, 98000050, 12400903, 2400760),
    ('category8_cathedral_ward_lot_2400650', 9806, 98000060, 12400904, 2400650),
    ('category8_cathedral_ward_lot_2400690', 9807, 98000070, 12400905, 2400690),
    ('category8_cathedral_ward_lot_2400740', 9808, 98000080, 12400906, 2400740),
    ('category8_old_yharnam_lot_2300300', 9809, 98000090, 12400907, 2300300),
    ('category8_hemwick_lot_2200190', 9810, 98000100, 12400908, 2200190),
    ('category8_hemwick_lot_2200280', 9811, 98000110, 12400909, 2200280),
    ('category8_hemwick_lot_2200380', 9812, 98000120, 12400910, 2200380),
    ('category8_cainhurst_lot_2501040', 9813, 98000130, 12400911, 2501040),
    ('category8_cainhurst_lot_2501060', 9814, 98000140, 12400912, 2501060),
    ('category8_forbidden_woods_lot_2700180', 9815, 98000150, 12400913, 2700180),
    ('category8_forbidden_woods_lot_2700200', 9816, 98000160, 12400914, 2700200),
    ('category8_forbidden_woods_lot_2700300', 9817, 98000170, 12400915, 2700300),
    ('category8_forbidden_woods_lot_2700380', 9818, 98000180, 12400916, 2700380),
    ('category8_forbidden_woods_lot_2700540', 9819, 98000190, 12400917, 2700540),
    ('category8_forbidden_woods_lot_2700570', 9820, 98000200, 12400918, 2700570),
    ('category8_forbidden_woods_lot_2700650', 9821, 98000210, 12400919, 2700650),
    ('category8_forbidden_woods_lot_2700660', 9822, 98000220, 12400920, 2700660),
    ('category8_forbidden_woods_lot_2700690', 9823, 98000230, 12400921, 2700690),
    ('category8_forbidden_woods_lot_2700700', 9824, 98000240, 12400922, 2700700),
    ('category8_yahargul_lot_2800020', 9825, 98000250, 12400923, 2800020),
    ('category8_yahargul_lot_2800050', 9826, 98000260, 12400924, 2800050),
    ('category8_yahargul_lot_2800140', 9827, 98000270, 12400925, 2800140),
    ('category8_yahargul_lot_2800350', 9828, 98000280, 12400926, 2800350),
    ('category8_yahargul_lot_2800530', 9829, 98000290, 12400927, 2800530),
    ('category8_yahargul_lot_2800710', 9830, 98000300, 12400928, 2800710),
    ('category8_lecture_building_lot_3200010', 9831, 98000310, 12400929, 3200010),
    ('category8_lecture_building_lot_3200640', 9832, 98000320, 12400930, 3200640),
    ('category8_nightmare_mensis_lot_2600150', 9833, 98000330, 12400931, 2600150),
    ('category8_nightmare_mensis_lot_2600200', 9834, 98000340, 12400932, 2600200),
    ('category8_nightmare_mensis_lot_2600220', 9835, 98000350, 12400933, 2600220),
    ('category8_nightmare_mensis_lot_2600300', 9836, 98000360, 12400934, 2600300),
    ('category8_nightmare_mensis_lot_2600390', 9837, 98000370, 12400935, 2600390),
    ('category8_nightmare_mensis_lot_2600480', 9838, 98000380, 12400936, 2600480),
    ('category8_nightmare_mensis_lot_2600510', 9839, 98000390, 12400937, 2600510),
    ('category8_nightmare_mensis_lot_2600530', 9840, 98000400, 12400938, 2600530),
    ('category8_nightmare_frontier_lot_3300010', 9841, 98000410, 12400939, 3300010),
    ('category8_nightmare_frontier_lot_3300050', 9842, 98000420, 12400940, 3300050),
    ('category8_nightmare_frontier_lot_3300220', 9843, 98000430, 12400941, 3300220),
    ('category8_nightmare_frontier_lot_3300320', 9844, 98000440, 12400942, 3300320),
    ('category8_nightmare_frontier_lot_3300380', 9845, 98000450, 12400943, 3300380),
    ('category8_upper_cathedral_lot_2420120', 9846, 98000460, 12400944, 2420120),
    ('category8_research_hall_lot_3500160', 9847, 98000470, 12400945, 3500160),
    ('category8_research_hall_lot_3500190', 9848, 98000480, 12400946, 3500190),
    ('category8_research_hall_lot_3501100', 9849, 98000490, 12400947, 3501100),
    ('category8_research_hall_lot_3501500', 9850, 98000500, 12400948, 3501500),
    ('category8_fishing_hamlet_lot_3600140', 9851, 98000510, 12400949, 3600140),
    ('category8_fishing_hamlet_lot_3600160', 9852, 98000520, 12400950, 3600160),
    ('category8_fishing_hamlet_lot_3600340', 9853, 98000530, 12400951, 3600340),
    ('category8_fishing_hamlet_lot_3600430', 9854, 98000540, 12400952, 3600430),
    ('category8_fishing_hamlet_lot_3600560', 9855, 98000550, 12400953, 3600560),
    ('category8_fishing_hamlet_lot_3600570', 9856, 98000560, 12400954, 3600570),
    ('category8_fishing_hamlet_lot_3600610', 9857, 98000570, 12400955, 3600610),
)


class Category8IdStabilityTests(unittest.TestCase):
    def test_the_pre_existing_award_identities_are_unchanged(self):
        self.assertEqual(58, len(GOLDEN_CATEGORY8_IDENTITIES))  # witness: the snapshot is populated
        actual = [(row.item_key, row.token_goods_id, row.item_lot_id,
                   row.ack_flag, row.source_lot_id)
                  for row in CATEGORY8_AWARDS]
        self.assertEqual(list(GOLDEN_CATEGORY8_IDENTITIES),
                         actual[:len(GOLDEN_CATEGORY8_IDENTITIES)])
        # And they are a prefix, not merely present somewhere: a row inserted
        # anywhere in FIXED_LOCATIONS would shift the tail of this list.
        self.assertEqual(len(_PILOTS) + len(_GENERATED),
                         len(GOLDEN_CATEGORY8_IDENTITIES))

    def test_appended_rows_live_in_a_band_the_generated_block_cannot_reach(self):
        """Headroom, asserted rather than assumed.

        The generated block grows upward from the pilots as the fixed-location
        catalog grows. The appended rows are written out by hand in a reserved
        band above it. If the generated block ever grew into that band the
        collision would show up as a duplicate ack flag on a player's save, so
        the gap is checked here instead.
        """
        token_floor, lot_floor, ack_floor = EVENT_AWARD_BAND
        self.assertTrue(_GENERATED)      # witness: the generated block is real
        self.assertTrue(_EVENT_AWARDS)   # witness: so is the appended block
        for row in _PILOTS + _GENERATED:
            with self.subTest(row=row.item_key):
                self.assertLess(row.token_goods_id, token_floor)
                self.assertLess(row.item_lot_id, lot_floor)
        # Only the generated block grows; the pilots' ack flags (12400990/991)
        # sit above the band on purpose and are pinned by the snapshot above.
        for row in _GENERATED:
            with self.subTest(row=row.item_key):
                self.assertLess(row.ack_flag, ack_floor)
        for row in _EVENT_AWARDS:
            with self.subTest(row=row.item_key):
                self.assertGreaterEqual(row.token_goods_id, token_floor)
                self.assertGreaterEqual(row.item_lot_id, lot_floor)
                self.assertGreaterEqual(row.ack_flag, ack_floor)
        # At least ten more catalog rows can be admitted before the generated
        # block reaches the reserved ack flags.
        self.assertGreaterEqual(ack_floor - max(row.ack_flag for row in _GENERATED), 10)

    def test_appended_rows_never_reuse_an_identity(self):
        for field in ("item_key", "display_name", "token_goods_id",
                      "item_lot_id", "ack_flag", "source_lot_id"):
            values = [getattr(row, field) for row in CATEGORY8_AWARDS]
            with self.subTest(field=field):
                self.assertEqual(len(values), len(set(values)))


if __name__ == "__main__":
    unittest.main()
