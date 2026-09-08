"""Regenerate the writer's seed-request fixture from the current world.

`tests/fixtures/shop-seed-request.json` is the request CI hands to
`BBSuppressionWriter --seed-weapons`. It used to carry only the Bath shop
permutation, so the whole category-8 award path went unexercised: PR #396 added
an award whose source lot keeps its recipe in slot 02, the writer only looked at
slot 01, and every beta.7 seed was refused at launch with CI green. The fixture
now carries the full award table, and `tests/test_seed_request_fixture.py`
fails when the world gains an award that was not regenerated into it.

Usage:

    python tools/build_seed_request_fixture.py          # rewrite the fixture
    python tools/build_seed_request_fixture.py --check   # verify, do not write

The `category8_awards` rows carry exactly the six fields the launcher puts in a
real `.bbseed.json` request (`_validate_category8_bridge_rows` in
`bb_launcher/workflow.py` rejects any other key), so the fixture is the shape
the writer actually sees in the field, not a repo-only variant.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "shop-seed-request.json"

# The reviewed ten-gate Bath permutation this fixture has always exercised: the
# ordinary Bath stock gates 12101000..12101009 reversed onto each other.
SHOP_GATE_PERMUTATION = {
    str(12_101_000 + index): 12_101_009 - index for index in range(10)
}

# The fields a real request carries per award, in the launcher's order.
AWARD_FIELDS = (
    "item_key", "token_goods_id", "item_lot_id", "gemgen_id", "ack_flag",
    "source_lot_id",
)


def award_row(award) -> dict:
    return {field: getattr(award, field) for field in AWARD_FIELDS}


def build_request() -> dict:
    sys.path.insert(0, str(REPO))
    from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

    return {
        "randomize_starting_weapons": False,
        "remove_weapon_requirements": False,
        "randomize_shops": True,
        "shop_gate_permutation": SHOP_GATE_PERMUTATION,
        "category8_awards": [award_row(award) for award in CATEGORY8_AWARDS],
    }


def render(request: dict) -> str:
    return json.dumps(request, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="fail instead of writing when the fixture is stale")
    args = parser.parse_args()
    text = render(build_request())
    if args.check:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current != text:
            print(f"{FIXTURE} is stale; run python tools/build_seed_request_fixture.py")
            return 1
        print(f"{FIXTURE} is current")
        return 0
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
