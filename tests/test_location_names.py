"""Contract tests for the player-facing location-name table.

docs/LOCATION-NAMING.md owns the rules; this module owns the ratchets that keep
worlds/bloodborne/location_names.tsv complete, unique, and consistent with the
names the datapackage already publishes. The population witnesses are
deliberate (#10): a green run over a shrunk or empty input proves nothing.
"""

from __future__ import annotations

import ast
import csv
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "research" / "catalog" / "fixed_location_catalog.tsv"
NAMES = ROOT / "worlds" / "bloodborne" / "location_names.tsv"
SHIPPED = ROOT / "worlds" / "bloodborne" / "fixed_locations.tsv"
DATA_PY = ROOT / "worlds" / "bloodborne" / "data.py"

# Witnessed populations, not targets. If the catalog gains or loses MVP
# candidates, or the slice ships another named MVP row, these numbers move in
# the same commit that names (or un-names) the rows.
MVP_CANDIDATES = 83
SHIPPED_MVP_ROWS = 6


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def mvp_flags() -> list[int]:
    return [
        int(row["location_flag"])
        for row in rows(CATALOG)
        if row["mvp_candidate"] == "True"
    ]


def world_regions() -> set[str]:
    """REGIONS, read from data.py without importing the Archipelago package."""
    tree = ast.parse(DATA_PY.read_text(encoding="utf-8"), filename=str(DATA_PY))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "REGIONS"
            for target in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError("REGIONS assignment not found in data.py")


class LocationNameTableTests(unittest.TestCase):
    def test_mvp_population_witness(self):
        self.assertEqual(MVP_CANDIDATES, len(mvp_flags()))

    def test_every_mvp_candidate_is_named_exactly_once(self):
        named = [int(row["location_flag"]) for row in rows(NAMES)]
        self.assertEqual(sorted(mvp_flags()), sorted(named))
        self.assertEqual(len(named), len(set(named)))

    def test_names_are_unique_nonempty_ascii(self):
        table = rows(NAMES)
        names = [row["name"].strip() for row in table]
        self.assertEqual(MVP_CANDIDATES, len(names))
        self.assertEqual(len(names), len(set(names)))
        for name in names:
            self.assertTrue(name, "empty location name")
            self.assertTrue(name.isascii(), f"non-ASCII location name: {name!r}")

    def test_names_carry_no_research_placeholders(self):
        for row in rows(NAMES):
            name = row["name"]
            self.assertNotIn("(Lot ", name)
            self.assertNotIn("unknown", name.lower())
            self.assertTrue(row["basis"].strip(), f"{row['location_flag']} has no basis")

    def test_regions_are_world_regions(self):
        known = world_regions()
        foreign = sorted(
            f"{row['location_flag']}:{row['region']}"
            for row in rows(NAMES)
            if row["region"] not in known
        )
        self.assertEqual("", "; ".join(foreign))

    def test_published_slice_names_agree(self):
        names_by_flag = {row["location_flag"]: row["name"] for row in rows(NAMES)}
        shipped = [
            row for row in rows(SHIPPED) if row["location_flag"] in names_by_flag
        ]
        self.assertEqual(SHIPPED_MVP_ROWS, len(shipped))
        mismatched = sorted(
            f"{row['key']}: {row['name']!r} != {names_by_flag[row['location_flag']]!r}"
            for row in shipped
            if row["name"] != names_by_flag[row["location_flag"]]
        )
        self.assertEqual("", "; ".join(mismatched))


if __name__ == "__main__":
    unittest.main()
