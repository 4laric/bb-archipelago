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
TOTAL_TABLE_ROWS = 670  # catalog rows + the scripted checks below
MVP_CANDIDATES = 83
SHIPPED_NAMED_ROWS = 51

# Non-catalog checks the table names: boss defeats and EMEVD script awards
# whose check flag is committed in runtime_bindings.py. Every boss in the
# model is now keyed by its mapped defeat flag; checks without a committed
# flag (e.g. interaction_laurences_skull) stay named inline in data.py.
SCRIPTED_CHECK_FLAGS = {
    "12411700",   # boss_cleric_beast
    "12411800",   # boss_father_gascoigne
    "12301800",   # boss_blood_starved_beast
    "12401800",   # boss_vicar_amelia
    "12701800",   # boss_shadows_of_yharnam
    "13201800",   # boss_rom
    "12801800",   # boss_the_one_reborn
    "12601850",   # boss_micolash
    "12601800",   # boss_mergos_wet_nurse
    "13401800",   # boss_ludwig
    "13501850",   # boss_living_failures
    "13501800",   # boss_lady_maria
    "13601800",   # boss_orphan_of_kos
    "13401850",   # boss_laurence
    "52410990",   # pickup_cainhurst_summons
    "52420900",   # script_award_orphanage_key
    "50000100",   # pickup_eye_of_blood_drunk_hunter
    "9470",       # pickup_eye_pendant
    "53502000",   # pickup_laurences_skull
}

# data.py checks that draw their name from the table: key -> the flag its
# location_name(...) call must resolve to. The join is witnessed both ways:
# the name must agree byte-for-byte, and the committed runtime binding for
# the key must carry the same flag.
DATA_PY_TABLED_CHECKS = {
    "boss_cleric_beast": 12411700,
    "boss_father_gascoigne": 12411800,
    "boss_blood_starved_beast": 12301800,
    "boss_vicar_amelia": 12401800,
    "boss_shadows_of_yharnam": 12701800,
    "boss_rom": 13201800,
    "boss_the_one_reborn": 12801800,
    "boss_micolash": 12601850,
    "boss_mergos_wet_nurse": 12601800,
    "boss_ludwig": 13401800,
    "boss_living_failures": 13501850,
    "boss_lady_maria": 13501800,
    "boss_orphan_of_kos": 13601800,
    "boss_laurence": 13401850,
    "pickup_cainhurst_summons": 52410990,
    "pickup_upper_cathedral_key": 52800290,
    "script_award_orphanage_key": 52420900,
    "pickup_eye_of_blood_drunk_hunter": 50000100,
    "pickup_eye_pendant": 9470,
    "pickup_laurences_skull": 53502000,
    "treasure_radiant_sword_hunter_badge": 52400480,
    "treasure_old_hunter_bone": 52110000,
    "treasure_rune_workshop_tool": 52200360,
    "treasure_augur_of_ebrietas": 53200600,
    "treasure_lecture_theatre_key": 53200720,
    "treasure_messengers_gift": 53300330,
    "treasure_executioners_gloves": 52500250,
    "treasure_cosmic_eye_watcher_badge": 52420270,
}

# Published slice names that still carry a "(Lot NNN)" research placeholder.
# The #75 rename landed: every placeholder row now publishes its table name.
# The set is empty on purpose — the gate below stays so a future lot-suffixed
# publish fails loudly instead of slipping in unnamed. A flag may only sit
# here while its published name is lot-suffixed — once the rename lands or is
# rejected, the row leaves this set and ordinary agreement applies.
PENDING_PLACEHOLDER_RENAMES: set[str] = set()


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
        self.assertEqual(TOTAL_TABLE_ROWS, len(named))
        # The table is exactly the catalog plus the witnessed scripted checks.
        self.assertEqual(
            sorted(catalog_flags + [int(flag) for flag in SCRIPTED_CHECK_FLAGS]),
            named,
        )

    def test_data_py_tabled_names_agree(self):
        from worlds.bloodborne.data import LOCATIONS
        from worlds.bloodborne.runtime_bindings import LOCATION_BINDINGS

        names_by_flag = {int(row["location_flag"]): row["name"] for row in rows(NAMES)}
        regions_by_flag = {int(row["location_flag"]): row["region"] for row in rows(NAMES)}
        locations = {location.key: location for location in LOCATIONS}
        mismatched = sorted(
            f"{key}: {locations[key].name!r} != {names_by_flag.get(flag)!r}"
            for key, flag in DATA_PY_TABLED_CHECKS.items()
            if key not in locations
            or locations[key].name != names_by_flag.get(flag)
            or locations[key].region != regions_by_flag.get(flag)
        )
        self.assertEqual("", "; ".join(mismatched))
        # The key -> flag join must match the committed runtime binding, or a
        # rename in the table would silently pin to the wrong check.
        bad_bindings = sorted(
            f"{key}: binding {LOCATION_BINDINGS[key].event_flag} != {flag}"
            for key, flag in DATA_PY_TABLED_CHECKS.items()
            if key not in LOCATION_BINDINGS
            or LOCATION_BINDINGS[key].event_flag != flag
        )
        self.assertEqual("", "; ".join(bad_bindings))

    def test_names_are_unique_nonempty_ascii(self):
        table = rows(NAMES)
        names = [row["name"].strip() for row in table]
        self.assertEqual(TOTAL_TABLE_ROWS, len(names))
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
