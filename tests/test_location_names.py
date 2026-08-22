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

# Witnessed populations, not targets. If the catalog gains or loses rows or
# MVP candidates, or the slice ships another named row, these numbers move in
# the same commit that names (or un-names) the rows.
TOTAL_CATALOG_ROWS = 651
MVP_CANDIDATES = 83
SHIPPED_NAMED_ROWS = 51

# Published slice names that still carry a "(Lot NNN)" research placeholder.
# The table name for these flags is the proposed replacement; the swap itself
# is the rename decision in #75. A flag may only sit here while its published
# name is lot-suffixed — once the rename lands or is rejected, the row leaves
# this set and ordinary agreement applies. This is the complete inventory:
# every shipped placeholder row, now that the table covers the full catalog.
PENDING_PLACEHOLDER_RENAMES = {
    "52410110", "52410120", "52410130", "52410140", "52410150", "52410160",
    "52410170", "52410180", "52410190", "52410200", "52410210", "52410220",
    "52410240", "52410250", "52410260", "52410270", "52410280", "52410295",
    "52410310", "52410330", "52410340", "52410360", "52410370", "52410380",
    "52410390", "52410400", "52410430", "52410440", "52410450", "52410470",
    "52410480", "52410490", "52410510", "52410530", "52410540", "52410560",
    "52410570", "52410590", "52410600", "52410610", "52410620", "52410630",
    "52410640", "52410650", "52410920",
}


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
        self.assertEqual(len(named), len(set(named)))
        missing = sorted(set(mvp_flags()) - set(named))
        self.assertEqual("", "; ".join(str(flag) for flag in missing))

    def test_every_catalog_row_is_named(self):
        catalog_flags = sorted(int(row["location_flag"]) for row in rows(CATALOG))
        self.assertEqual(TOTAL_CATALOG_ROWS, len(catalog_flags))
        named = sorted(int(row["location_flag"]) for row in rows(NAMES))
        self.assertEqual(catalog_flags, named)

    def test_names_are_unique_nonempty_ascii(self):
        table = rows(NAMES)
        names = [row["name"].strip() for row in table]
        self.assertEqual(TOTAL_CATALOG_ROWS, len(names))
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
        self.assertEqual(SHIPPED_NAMED_ROWS, len(shipped))
        mismatched = sorted(
            f"{row['key']}: {row['name']!r} != {names_by_flag[row['location_flag']]!r}"
            for row in shipped
            if row["location_flag"] not in PENDING_PLACEHOLDER_RENAMES
            and row["name"] != names_by_flag[row["location_flag"]]
        )
        self.assertEqual("", "; ".join(mismatched))

    def test_pending_renames_are_exactly_the_lot_suffixed_published_rows(self):
        names_by_flag = {row["location_flag"]: row["name"] for row in rows(NAMES)}
        shipped_by_flag = {row["location_flag"]: row["name"] for row in rows(SHIPPED)}
        pending = sorted(
            flag
            for flag in PENDING_PLACEHOLDER_RENAMES
            if flag in names_by_flag and flag in shipped_by_flag
        )
        # A pending entry that names nothing shipped, or that "renames" a
        # clean published name, is a stale gate, not a decision.
        self.assertEqual(sorted(PENDING_PLACEHOLDER_RENAMES), pending)
        for flag in pending:
            self.assertIn("(Lot ", shipped_by_flag[flag])
            self.assertNotIn("(Lot ", names_by_flag[flag])
        # And the other direction: every shipped placeholder that the table
        # names must be listed here, so the #75 inventory cannot drift.
        lot_suffixed = sorted(
            flag
            for flag, name in shipped_by_flag.items()
            if "(Lot " in name and flag in names_by_flag
        )
        self.assertEqual(lot_suffixed, sorted(PENDING_PLACEHOLDER_RENAMES))


if __name__ == "__main__":
    unittest.main()
