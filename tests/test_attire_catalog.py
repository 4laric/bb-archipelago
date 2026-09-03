from __future__ import annotations

import unittest

from worlds.bloodborne.attire import ATTIRE_CATALOG
from worlds.bloodborne.starting_attire import STARTING_ATTIRE_CATALOG


class FullAttireCatalogTests(unittest.TestCase):
    def test_catalog_is_complete_player_obtainable_corpus(self):
        self.assertEqual(127, len(ATTIRE_CATALOG))
        self.assertEqual(127, len({piece.protector_id for piece in ATTIRE_CATALOG}))
        self.assertEqual(127, len({piece.item_key for piece in ATTIRE_CATALOG}))
        self.assertTrue(
            {piece.protector_id for piece in STARTING_ATTIRE_CATALOG}
            < {piece.protector_id for piece in ATTIRE_CATALOG}
        )

    def test_known_non_equipment_and_cut_rows_are_excluded(self):
        ids = {piece.protector_id for piece in ATTIRE_CATALOG}
        # 192000 is Micolash's hidden arms row; 330000 was a cut wolf head in
        # the base params but is replaced by the obtainable DLC Butcher Mask.
        # 362000 has no player-facing item and is not the Old Hunter Gloves
        # used by the Decorative Old Hunter ensemble.
        self.assertNotIn(192000, ids)
        self.assertNotIn(362000, ids)
        self.assertTrue(all(value < 480000 for value in ids))

    def test_dlc_boundary_covers_every_old_hunters_piece(self):
        dlc = {piece.protector_id for piece in ATTIRE_CATALOG if piece.dlc}
        self.assertEqual(32, len(dlc))
        self.assertIn(330000, dlc)
        self.assertIn(430000, dlc)
        self.assertNotIn(320000, dlc)

    def test_two_obtainable_league_helm_variants_remain_distinct(self):
        by_id = {piece.protector_id: piece for piece in ATTIRE_CATALOG}
        self.assertEqual("Master's Iron Helm", by_id[260000].name)
        self.assertEqual("One-eyed Iron Helm", by_id[380000].name)


if __name__ == "__main__":
    unittest.main()
