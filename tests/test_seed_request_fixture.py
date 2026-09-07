"""The writer fixture must carry every category-8 award the world emits.

CI hands `tests/fixtures/shop-seed-request.json` to
`BBSuppressionWriter --seed-weapons`. Before #396 that fixture carried no
`category8_awards` at all, so the writer's award path was never exercised: an
award whose source lot keeps its recipe in slot 02 shipped in beta.7 and every
seed was refused at launch while CI stayed green. Pinning the fixture to the
world's own table means a future award addition fails here unless the fixture
is regenerated with `python tools/build_seed_request_fixture.py`.
"""

from __future__ import annotations

import dataclasses
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_seed_request_fixture import FIXTURE, render, build_request  # noqa: E402
from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS  # noqa: E402


class SeedRequestFixtureTests(unittest.TestCase):
    def test_fixture_carries_every_category8_award(self):
        request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        rows = request.get("category8_awards")
        self.assertIsInstance(rows, list)
        # A witness that the population is non-empty and covers all three
        # bands: the two live pilots, the generated block, and the reserved
        # event-award band the beta.7 regression came from.
        self.assertGreater(len(CATEGORY8_AWARDS), 2)
        self.assertIn(
            "category8_cathedral_ward_avatar_beast_rune",
            {row["item_key"] for row in rows},
        )
        self.assertEqual(
            rows, [dataclasses.asdict(award) for award in CATEGORY8_AWARDS])

    def test_fixture_is_byte_for_byte_what_the_builder_writes(self):
        self.assertEqual(
            FIXTURE.read_text(encoding="utf-8"), render(build_request()))

    def test_fixture_still_requests_the_bath_shop_permutation(self):
        request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertTrue(request["randomize_shops"])
        self.assertEqual(request["shop_gate_permutation"], 10)


if __name__ == "__main__":
    unittest.main()
