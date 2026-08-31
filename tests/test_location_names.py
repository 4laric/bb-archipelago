"""Contract tests for the player-facing location-name table.

docs/LOCATION-NAMING.md owns the rules; this module owns the ratchets that keep
worlds/bloodborne/location_names.tsv complete, unique, and consistent with the
names the datapackage already publishes. The population witnesses are
deliberate (#10): a green run over a shrunk or empty input proves nothing.
"""

from __future__ import annotations

import ast
import csv
import re
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
TOTAL_TABLE_ROWS = 681  # catalog rows + the scripted checks below
MVP_CANDIDATES = 83
SHIPPED_NAMED_ROWS = 606

# Non-catalog checks the table names: boss defeats, EMEVD script awards, and
# the one evidenced interaction, each keyed by the check flag committed in
# runtime_bindings.py. Every check in data.py is now table-backed.
SCRIPTED_CHECK_FLAGS = {
    "12411700",   # boss_cleric_beast
    "12411800",   # boss_father_gascoigne
    "12301800",   # boss_blood_starved_beast
    "12401800",   # boss_vicar_amelia
    "12401898",   # interaction_laurences_skull
    "12421700",   # boss_celestial_emissary
    "12421800",   # boss_ebrietas
    "12201800",   # boss_witch_of_hemwick
    "12501800",   # boss_martyr_logarius
    "12701800",   # boss_shadows_of_yharnam
    "13201800",   # boss_rom
    "12801800",   # boss_the_one_reborn
    "12601850",   # boss_micolash
    "12601800",   # boss_mergos_wet_nurse
    "12101800",   # boss_gehrman
    "12101850",   # boss_moon_presence
    "13301800",   # boss_amygdala
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
    "52110800",   # pickup_small_hair_ornament
    "52110810",   # pickup_workshop_umbilical_cord
    "53200810",   # pickup_lunarium_key
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
    "boss_witch_of_hemwick": 12201800,
    "boss_martyr_logarius": 12501800,
    "interaction_laurences_skull": 12401898,
    "boss_celestial_emissary": 12421700,
    "boss_ebrietas": 12421800,
    "boss_shadows_of_yharnam": 12701800,
    "boss_rom": 13201800,
    "boss_the_one_reborn": 12801800,
    "boss_micolash": 12601850,
    "boss_mergos_wet_nurse": 12601800,
    "boss_gehrman": 12101800,
    "boss_moon_presence": 12101850,
    "boss_amygdala": 13301800,
    "boss_ludwig": 13401800,
    "boss_living_failures": 13501850,
    "boss_lady_maria": 13501800,
    "boss_orphan_of_kos": 13601800,
    "boss_laurence": 13401850,
    "pickup_cainhurst_summons": 52410990,
    "pickup_upper_cathedral_key": 52800290,
    "pickup_lunarium_key": 53200810,
    "script_award_orphanage_key": 52420900,
    "pickup_eye_of_blood_drunk_hunter": 50000100,
    "pickup_eye_pendant": 9470,
    "pickup_laurences_skull": 53502000,
    "treasure_radiant_sword_hunter_badge": 52400480,
    "treasure_old_hunter_bone": 52110000,
    "treasure_doll_set_chest": 52110020,
    "pickup_small_hair_ornament": 52110800,
    "pickup_workshop_umbilical_cord": 52110810,
    "treasure_rune_workshop_tool": 52200360,
    "treasure_augur_of_ebrietas": 53200600,
    "treasure_lecture_theatre_key": 53200720,
    "treasure_messengers_gift": 53300330,
    "treasure_executioners_gloves": 52500250,
    "treasure_underground_jail_chunk": 53500630,
    "treasure_underground_cell_inner_chamber_key": 50002360,
    "treasure_cosmic_eye_watcher_badge": 52420270,
}

# Published slice names that still carry a "(Lot NNN)" research placeholder.
# The #75 rename landed: every placeholder row now publishes its table name.
# The set is empty on purpose — the gate below stays so a future lot-suffixed
# publish fails loudly instead of slipping in unnamed. A flag may only sit
# here while its published name is lot-suffixed — once the rename lands or is
# rejected, the row leaves this set and ordinary agreement applies.
PENDING_PLACEHOLDER_RENAMES: set[str] = set()

# --- landmark hints (#222) -------------------------------------------------

VOCABULARY = ROOT / "docs" / "location_hint_vocabulary.tsv"
OVERRIDES = ROOT / "docs" / "location_hint_overrides.tsv"
LOT_ITEMS = ROOT / "research" / "joined" / "lot_items.tsv"
DOC = ROOT / "docs" / "LOCATION-NAMING.md"
PLAYER_DOC = ROOT / "worlds" / "bloodborne" / "docs" / "locations_en.md"
LANDMARK_EVIDENCE = ROOT / "docs" / "location_landmark_evidence.tsv"

# Witnessed populations, not targets, exactly like the counts above. The pass
# deliberately leaves rows bare: a name with no landmark yet is honest, and
# raising this number means new evidence, not new invention.
HINTED_ROWS = 183
BARE_ROWS = 498

# The three rows oz hunted with a video guide open and still needed operator
# support to find (#222). Each must publish a hint naming the area, not an
# ordinal. The substring is what the player has to read, not the whole hint.
OZ_HUNTED_HINTS = {
    "52410110": "sewer",       # Blood Stone Shard x2, the dangling sewer pair
    "52410130": "backstreets",  # Coldblood Dew (1) #1
    "52410650": "bridge",      # Blood Stone Shard #8, the "#8"-style name
}

# Two placements this close in the same map are one prop cluster to a player,
# so they may not publish contradictory hints. Five units, not twenty: the
# maps stack vertically and the developers' halves interleave at their
# boundary, so a wider radius flags honest neighbours (a corpse against the
# fish-tank's outer wall, one floor of the Research Hall tower above another)
# as contradictions. Five is the radius at which the committed table is clean.
CLUSTER_RADIUS = 5.0


def place_hint(name: str) -> str | None:
    """The trailing landmark hint, or None. A bare number is an item name."""
    if not name.endswith(")"):
        return None
    inner = name[name.rindex("(") + 1 : -1]
    return None if inner.isdigit() else inner


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


class LandmarkHintTests(unittest.TestCase):
    """Ratchets for the landmark-hint convention (#222)."""

    def test_hint_population_witness(self):
        names = [row["name"] for row in rows(NAMES)]
        hinted = [name for name in names if place_hint(name)]
        self.assertEqual(HINTED_ROWS, len(hinted))
        self.assertEqual(BARE_ROWS, len(names) - len(hinted))
        self.assertEqual(TOTAL_TABLE_ROWS, len(names))

    def test_hint_bearing_names_are_unique(self):
        hinted = [row["name"] for row in rows(NAMES) if place_hint(row["name"])]
        self.assertEqual(HINTED_ROWS, len(hinted))
        self.assertEqual(len(hinted), len(set(hinted)))
        for name in hinted:
            self.assertTrue(name.isascii(), f"non-ASCII hint: {name!r}")

    def test_documented_vocabulary_matches_the_committed_table(self):
        """The doc's per-map tables and the vocabulary TSV say the same thing.

        The doc is what a reviewer reads; the TSV is what the generator obeys.
        A gate that only checked one of them would let them drift.
        """
        table = {
            (row["canonical_map"], row["tag"], row["hint"]) for row in rows(VOCABULARY)
        }
        self.assertTrue(table, "empty hint vocabulary")
        text = DOC.read_text(encoding="utf-8")
        documented = set()
        current_map = None
        for line in text.splitlines():
            found = re.search(r"#### (m\d\d_\d\d_\d\d_\d\d)", line)
            if found:
                current_map = found.group(1)
                continue
            if current_map and line.startswith("| `"):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                if len(cells) >= 2 and cells[0].startswith("`"):
                    documented.add(
                        (current_map, cells[0].strip("`"), cells[1].strip("`"))
                    )
        self.assertEqual(table, documented)

    def test_every_emitted_hint_is_vocabulary_or_carries_provenance(self):
        """Documented-matches-emitted, the other direction.

        A tag-derived hint must be the vocabulary's word for that map's tag; a
        hand-written one must name its override row; anything else has to have
        been reviewed as a place name before this pass.
        """
        from tools.build_location_hints import lot_names_by_flag, tag_hint, vocabulary

        vocab = vocabulary()
        lots = lot_names_by_flag()
        catalog = {row["location_flag"]: row for row in rows(CATALOG)}
        overrides = {row["location_flag"]: row["hint"] for row in rows(OVERRIDES)}
        self.assertTrue(overrides, "empty override table")

        checked = 0
        wrong = []
        for row in rows(NAMES):
            flag = row["location_flag"]
            hint = place_hint(row["name"])
            if hint is None:
                continue
            if "hint from lot tag" not in row["basis"]:
                if flag in overrides:
                    checked += 1
                    if overrides[flag] not in hint:
                        wrong.append(f"{flag}: override {overrides[flag]!r} not in {hint!r}")
                continue
            checked += 1
            entry = catalog[flag]
            expected = tag_hint(lots.get(flag, ""), entry["canonical_map"], vocab)
            if expected is None:
                wrong.append(f"{flag}: basis claims a tag hint, vocabulary has none")
                continue
            word, tag = expected
            if word not in hint:
                wrong.append(f"{flag}: emitted {hint!r}, vocabulary says {word!r}")
            if f"lot tag {tag} " not in row["basis"]:
                wrong.append(f"{flag}: basis does not name tag {tag}")
        self.assertEqual("", "; ".join(wrong))
        # Witness: the join actually examined the tag-hinted population.
        self.assertGreaterEqual(checked, 90)

    def test_the_three_rows_oz_hunted_carry_area_hints(self):
        names = {row["location_flag"]: row["name"] for row in rows(NAMES)}
        missing = sorted(
            f"{flag}: {names.get(flag)!r} lacks {word!r}"
            for flag, word in OZ_HUNTED_HINTS.items()
            if word not in (place_hint(names.get(flag, "")) or "")
        )
        self.assertEqual("", "; ".join(missing))

    def test_neighbouring_placements_do_not_contradict(self):
        """Lots within CLUSTER_RADIUS of each other share their hint.

        Coordinates come from the catalog, which is the MSB placement join.
        Two corpses a player cannot tell apart must not be told apart by the
        name table either.
        """
        table = rows(NAMES)
        catalog = {row["location_flag"]: row for row in rows(CATALOG)}
        placed = []
        for row in table:
            entry = catalog.get(row["location_flag"])
            if entry is None or not entry["coordinates"]:
                continue
            # A multi-placement catalog row lists every copy, ";"-separated;
            # the first is the canonical map's.
            first = entry["coordinates"].split(";")[0]
            point = tuple(float(value) for value in first.split(","))
            placed.append((entry["canonical_map"], point, place_hint(row["name"]), row))
        self.assertGreater(len(placed), 600, "coordinate witness collapsed")

        clashes = []
        for index, (map_a, point_a, hint_a, row_a) in enumerate(placed):
            if hint_a is None:
                continue
            for map_b, point_b, hint_b, row_b in placed[index + 1 :]:
                if map_a != map_b or hint_b is None or hint_a == hint_b:
                    continue
                # "tower" and "tower 3F" are the same claim at two
                # resolutions, not a contradiction.
                if hint_a in hint_b or hint_b in hint_a:
                    continue
                distance = sum((a - b) ** 2 for a, b in zip(point_a, point_b)) ** 0.5
                if distance <= CLUSTER_RADIUS:
                    clashes.append(
                        f"{row_a['location_flag']}({hint_a}) vs "
                        f"{row_b['location_flag']}({hint_b}) at {distance:.1f}"
                    )
        self.assertEqual("", "; ".join(sorted(clashes)))

    def test_ordinals_survive_hinting(self):
        """#N is stable on purpose.

        A hint can make a name unique on its own, but dropping the ordinal
        would churn every tracker pack and every player's memory for no
        mechanical gain. The pass appends; it never renumbers.
        """
        table = {row["location_flag"]: row["name"] for row in rows(NAMES)}
        ordinal_rows = [name for name in table.values() if re.search(r"#\d+", name)]
        self.assertEqual(407, len(ordinal_rows))
        hinted_ordinals = [name for name in ordinal_rows if place_hint(name)]
        self.assertEqual(98, len(hinted_ordinals))
        for name in hinted_ordinals:
            # the ordinal stays ahead of the hint, never replaced by it
            self.assertRegex(name, r"#\d+ \([^()]+\)$")


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


class PlayerLocationDocsTests(unittest.TestCase):
    def test_player_locations_page_is_current_and_exhaustive(self):
        from tools.build_location_docs import render

        self.assertTrue(PLAYER_DOC.is_file())
        self.assertEqual(render(), PLAYER_DOC.read_text(encoding="utf-8"))
        page = PLAYER_DOC.read_text(encoding="utf-8")
        missing = [row["name"] for row in rows(NAMES) if row["name"] not in page]
        self.assertEqual([], missing)

    def test_landmark_ledger_joins_back_to_names_catalog_and_ids(self):
        names = {row["location_flag"]: row for row in rows(NAMES)}
        catalog = {row["location_flag"]: row for row in rows(CATALOG)}
        ids = {
            row["key"]: row["id"]
            for row in rows(ROOT / "worlds/bloodborne/ids.tsv")
        }
        evidence = rows(LANDMARK_EVIDENCE)
        self.assertGreaterEqual(len(evidence), 6)
        for row in evidence:
            with self.subTest(flag=row["location_flag"]):
                self.assertIn(row["location_flag"], names)
                self.assertIn(row["location_flag"], catalog)
                self.assertIn(
                    row["item_lot"],
                    catalog[row["location_flag"]]["item_lot_ids"].split(";"),
                )
                self.assertEqual(row["network_id"], ids[row["location_key"]])
                self.assertIn(row["landmark"], names[row["location_flag"]]["name"])
                self.assertTrue(row["source"])
                self.assertTrue(row["confidence"])


if __name__ == "__main__":
    unittest.main()
