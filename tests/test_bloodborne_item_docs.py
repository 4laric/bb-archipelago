"""Keep the player-facing Items wiki synchronized with the world catalog."""

import re
import unittest
from pathlib import Path

from worlds.bloodborne import FILLER_ITEM_NAME
from worlds.bloodborne.data import ITEMS


ROOT = Path(__file__).resolve().parents[1]
ITEMS_DOC = ROOT / "worlds" / "bloodborne" / "docs" / "items_en.md"


class BloodborneItemDocumentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = ITEMS_DOC.read_text(encoding="utf-8")
        manifest = re.search(r"<!-- ITEM-DOC-KEYS(.*?)-->", cls.text, re.DOTALL)
        if manifest is None:
            raise AssertionError("items_en.md has no ITEM-DOC-KEYS manifest")
        cls.coverage_keys = set(re.findall(r"\b[a-z][a-z0-9_]*\b", manifest.group(1)))

    def test_standard_archipelago_items_document_exists(self):
        self.assertTrue(self.text.startswith("# Bloodborne Items\n"))
        self.assertIn("/games/Bloodborne/info/en", self.text)
        self.assertIn("/tutorial/Bloodborne/locations/en", self.text)

    def test_every_catalog_item_has_a_coverage_key(self):
        expected = {item.key for item in ITEMS} | {"blood_vial"}
        self.assertEqual(expected, self.coverage_keys)

    def test_every_player_facing_item_name_is_visible(self):
        for item in ITEMS:
            with self.subTest(item=item.key):
                self.assertIn(item.name, self.text)
        self.assertIn(FILLER_ITEM_NAME, self.text)

    def test_local_events_are_not_described_as_shuffled(self):
        self.assertIn("never shuffled to another player", self.text)
        self.assertIn("Forbidden Woods Password Learned", self.text)
        self.assertIn("not an inventory item", self.text)


if __name__ == "__main__":
    unittest.main()
