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

The `category8_awards` rows use the writer's own field names, which are the
`Category8Award` dataclass fields, so the fixture stays readable next to
`worlds/bloodborne/category8_awards.py`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "shop-seed-request.json"


def build_request() -> dict:
    sys.path.insert(0, str(REPO))
    from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

    return {
        "randomize_starting_weapons": False,
        "remove_weapon_requirements": False,
        "randomize_shops": True,
        "shop_gate_permutation": 10,
        "category8_awards": [
            dataclasses.asdict(award) for award in CATEGORY8_AWARDS
        ],
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
