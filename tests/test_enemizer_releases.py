"""Release-tranche tests: from blanket exclusions to working compatibility.

The default conservative policy (308 swaps) is unchanged. Each opt-in
tranche in research/enemizer/release_{contracts,spawns,chara}.json replaces
one blanket exclusion with reviewed compatibility handling; tranches compose
by union through the planner's --release-file. Quest-drop carriers, the
Snatcher progression row, talk bindings, boss wiring, NPC-part models,
AI-ID writes, AI commands and unknown ops stay protected in every
combination. See docs/ENEMIZER-EXPANSION.md.
"""
import csv
import json
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from tools.bb_enemizer.cli import RELEASE_FORMAT, RELEASE_TRANCHES, load_release_files
from tools.bb_enemizer.inventory import (
    apply_archetype_tag, classify_slot, load_slot_overrides, load_slots, load_tags,
)
from tools.bb_enemizer.model import canonical_map
from tools.bb_enemizer.planner import EnemizerConfig, plan_swaps
from tools.bb_enemizer.script_contracts import (
    HARD_OPS, SUPPORTED_OPS, classify_ops, placement_operations,
)
from tools.build_emevd_entity_usage import has_character_operation, materialize_bundle

ROOT = Path(__file__).resolve().parents[1]
RELEASE_FILES = {
    tranche: ROOT / "research" / "enemizer" / f"release_{tranche}.json"
    for tranche in RELEASE_TRANCHES
}
CARRIERS = ROOT / "research" / "enemizer" / "quest_drop_carriers.json"
SEED = "12345"
# Measured swap counts per tranche combination at SEED (seed-stable;
# determinism is pinned separately below).
PINNED_COUNTS = {
    (): 308,
    ("contracts",): 827,
    ("spawns",): 797,
    ("chara",): 345,
    ("chara", "contracts", "spawns"): 1546,
}
SNATCHER = "m24_00_00_00:c2020_0000"


def _census_rows():
    with (ROOT / "research" / "enemizer" / "emevd_entity_usage.tsv").open(
            encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


class ReleaseRecordTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = {
            tranche: json.loads(path.read_text(encoding="utf-8"))
            for tranche, path in RELEASE_FILES.items()
        }
        cls.carriers = set(json.loads(CARRIERS.read_text(encoding="utf-8"))["carriers"])

    def test_format_tranche_and_non_empty(self):
        for tranche, record in self.records.items():
            self.assertEqual(RELEASE_FORMAT, record["format"])
            self.assertEqual(tranche, record["tranche"])
            self.assertGreater(len(record["releases"]), 100)

    def test_snatcher_and_quest_carriers_never_released(self):
        for tranche, record in self.records.items():
            releases = record["releases"]
            self.assertNotIn(SNATCHER, releases)
            leaked = sorted(set(releases) & self.carriers)
            self.assertEqual(0, len(leaked))

    def test_contract_tables_cover_the_observed_vocabulary(self):
        ops = set()
        for row in _census_rows():
            ops |= placement_operations(row["operations"])
        unlisted = sorted(op for op in ops if op not in SUPPORTED_OPS and op not in HARD_OPS)
        self.assertEqual(0, len(unlisted))

    def test_hard_witnesses_stay_out_of_contracts(self):
        contracts = self.records["contracts"]["releases"]
        # Cleric Beast arena boss wiring must never be released.
        self.assertNotIn("m24_01_00_00:c5000_0000", contracts)
        for key, detail in contracts.items():
            self.assertEqual("supported", detail["contract_class"])
            self.assertEqual(0, len(detail["hard_operations"]))
            self.assertEqual(0, len(detail["unreviewed_operations"]))

    def test_record_counts(self):
        counts = {tranche: len(record["releases"]) for tranche, record in self.records.items()}
        self.assertEqual({"contracts": 750, "spawns": 588, "chara": 294}, counts)


class ReleasePlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        inventory, _events = materialize_bundle(
            ROOT / "research/bb_inputs.db", Path(cls._tmp.name))
        cls.slots = load_slots(inventory)
        cls.tags = load_tags(ROOT / "research/enemizer/enemy_tags.json")
        cls.overrides = load_slot_overrides(ROOT / "research/enemizer/slot_policy.json")
        cls.by_logical = defaultdict(list)
        for slot in cls.slots:
            cls.by_logical[slot.logical_key].append(slot)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _plan(self, tranches):
        release = load_release_files(
            [str(RELEASE_FILES[tranche]) for tranche in tranches])
        policies = {
            slot.key: apply_archetype_tag(
                classify_slot(slot, self.overrides, release), self.tags.get(slot.archetype.key))
            for slot in self.slots
        }
        swaps, rejections = plan_swaps(self.slots, policies, self.tags, EnemizerConfig(SEED))
        return swaps, rejections, release

    def test_tranche_swap_counts(self):
        for tranches, expected in PINNED_COUNTS.items():
            swaps, _rejections, _release = self._plan(tranches)
            self.assertEqual(expected, len(swaps), f"tranches={tranches}")

    def test_tranche_determinism(self):
        for tranches in [("contracts",), ("chara", "contracts", "spawns")]:
            release = load_release_files(
                [str(RELEASE_FILES[tranche]) for tranche in tranches])
            first, _, _ = self._plan(tranches)
            policies = {
                slot.key: apply_archetype_tag(
                    classify_slot(slot, self.overrides, release),
                    self.tags.get(slot.archetype.key))
                for slot in reversed(self.slots)
            }
            second, _ = plan_swaps(list(reversed(self.slots)), policies, self.tags,
                                   EnemizerConfig(SEED))
            self.assertEqual([swap.json() for swap in first],
                             [swap.json() for swap in second])

    def test_new_swaps_come_only_from_released_keys(self):
        base_swaps, _rejections, _release = self._plan(())
        base = {swap.logical_key for swap in base_swaps}
        for tranches in [("contracts",), ("spawns",), ("chara",),
                         ("chara", "contracts", "spawns")]:
            swaps, _rejections, release = self._plan(tranches)
            allowed = set()
            for key, names in release.items():
                allowed.add(key)
            added = [swap.logical_key for swap in swaps if swap.logical_key not in base]
            for key in added:
                self.assertIn(key, allowed, f"{key} not released by {tranches}")

    def test_entity_identity_preserved_across_expanded_plan(self):
        swaps, _rejections, _release = self._plan(("chara", "contracts", "spawns"))
        source_by_key = {}
        for slot in self.slots:
            source_by_key[slot.key] = slot.entity_id
        self.assertGreater(len(swaps), 1000)
        for swap in swaps:
            for destination_key in swap.destination_keys:
                destinations = swap.destinations[destination_key]
                self.assertEqual(source_by_key[destination_key], destinations["entity_id"])

    def test_hard_classes_never_swap_in_any_tranche(self):
        census_ops = defaultdict(set)
        for row in _census_rows():
            census_ops[row["logical_key"]] |= placement_operations(row["operations"])
        hard_keys = {key for key, ops in census_ops.items()
                     if classify_ops(ops)[0] == "needs_adapter"}
        self.assertGreater(len(hard_keys), 200)
        for tranches in [("contracts",), ("spawns",), ("chara",),
                         ("chara", "contracts", "spawns")]:
            swaps, _rejections, _release = self._plan(tranches)
            swapped = {swap.logical_key for swap in swaps}
            leaked = sorted(swapped & hard_keys)
            self.assertEqual(0, len(leaked), f"tranches={tranches}")

    def test_central_yharnam_visibility(self):
        expected = {(): 49, ("contracts",): 94, ("spawns",): 106,
                    ("chara",): 59, ("chara", "contracts", "spawns"): 177}
        for tranches, count in expected.items():
            swaps, _rejections, _release = self._plan(tranches)
            central = [swap for swap in swaps
                       if swap.logical_key.startswith("m24_01_00_00:")]
            self.assertEqual(count, len(central), f"tranches={tranches}")


class ClassifyReleaseTests(unittest.TestCase):
    """The release mapping suppresses exactly one gate per tranche."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        inventory, _events = materialize_bundle(
            ROOT / "research/bb_inputs.db", Path(cls._tmp.name))
        cls.slots = load_slots(inventory)
        cls.by_logical = defaultdict(list)
        for slot in cls.slots:
            cls.by_logical[slot.logical_key].append(slot)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _first(self, predicate):
        for slot in self.slots:
            if predicate(slot):
                return slot
        raise AssertionError("no witness slot")

    def test_spawns_release_suppresses_only_the_dummy_gate(self):
        slot = self._first(lambda s: s.dummy and s.talk_id <= 0
                           and s.archetype.chara_init_id <= 0
                           and s.archetype.model_name.startswith("c")
                           and s.archetype.npc_param_id > 0 and s.archetype.think_param_id > 0)
        self.assertEqual("dummy/script-spawn Part",
                         classify_slot(slot, {}, None).reason)
        self.assertTrue(classify_slot(
            slot, {}, {slot.logical_key: {"spawns"}}).randomize)
        # A contracts release does not lift the dummy gate.
        self.assertEqual("dummy/script-spawn Part",
                         classify_slot(slot, {}, {slot.logical_key: {"contracts"}}).reason)

    def test_contracts_release_suppresses_only_the_override(self):
        overrides = load_slot_overrides(ROOT / "research/enemizer/slot_policy.json")
        key = next(key for key, value in overrides.items()
                   if "entity ID referenced by area EMEVD" in value.get("reason", "")
                   and key != SNATCHER)
        slot = self.by_logical[key][0]
        self.assertFalse(classify_slot(slot, overrides, None).randomize)
        released = classify_slot(slot, overrides, {slot.logical_key: {"contracts"}})
        # The override lifts; whatever physical gate applies still decides.
        if slot.dummy or slot.talk_id > 0 or slot.archetype.chara_init_id > 0:
            self.assertFalse(released.randomize)
        # A spawns release does not lift the EMEVD override.
        self.assertFalse(classify_slot(
            slot, overrides, {slot.logical_key: {"spawns"}}).randomize)

    def test_talk_is_never_releasable(self):
        slot = self._first(lambda s: s.talk_id > 0)
        release = {slot.logical_key: {"contracts", "spawns", "chara"}}
        self.assertEqual("talk-bound character",
                         classify_slot(slot, {}, release).reason)

    def test_default_behavior_unchanged(self):
        overrides = load_slot_overrides(ROOT / "research/enemizer/slot_policy.json")
        tags = load_tags(ROOT / "research/enemizer/enemy_tags.json")
        policies = {
            slot.key: apply_archetype_tag(
                classify_slot(slot, overrides), tags.get(slot.archetype.key))
            for slot in self.slots
        }
        swaps, _ = plan_swaps(self.slots, policies, tags, EnemizerConfig(SEED))
        self.assertEqual(308, len(swaps))


class PopulationTests(unittest.TestCase):
    """The target population: hostile enemies in, non-enemies out, gaps named."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        inventory, _events = materialize_bundle(
            ROOT / "research/bb_inputs.db", Path(cls._tmp.name))
        cls.slots = load_slots(inventory)
        cls.by_logical = defaultdict(list)
        for slot in cls.slots:
            cls.by_logical[slot.logical_key].append(slot)
        import sqlite3
        import zlib
        database = sqlite3.connect(ROOT / "research/bb_inputs.db")
        try:
            blob = database.execute(
                "SELECT blob FROM files WHERE path='params/NpcParam.csv'").fetchone()[0]
        finally:
            database.close()
        path = Path(cls._tmp.name) / "npc.csv"
        path.write_bytes(zlib.decompress(blob))
        with path.open(encoding="utf-8-sig", newline="") as handle:
            cls.npcs = {row["ID"]: row for row in csv.DictReader(handle)}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def team(self, logical_key):
        row = self.npcs.get(str(self.by_logical[logical_key][0].archetype.npc_param_id))
        if row is None:
            return ("MISSING", "MISSING")
        return (row["teamType"], row["npcType"])

    def test_hostile_mob_population(self):
        hostile = [key for key in self.by_logical if self.team(key) == ("23", "0")]
        self.assertEqual(2142, len(hostile))

    def test_non_enemy_teams_excluded_with_reasons(self):
        teams = defaultdict(int)
        for key in self.by_logical:
            teams[self.team(key)] += 1
        # Patrol-dummy infrastructure, co-op guests, friendlies, markers.
        self.assertEqual(92, teams[("0", "0")])
        self.assertEqual(45, teams[("22", "0")])
        self.assertEqual(132, teams[("26", "0")])
        self.assertEqual(52, teams[("26", "2")])
        # Boss-track hostiles route through encounter templates, not mob donors.
        self.assertEqual(40, teams[("23", "1")])
        # Infighting faction + quest pigs route through future same-team handling.
        self.assertEqual(73 + 1, teams[("24", "0")] + teams[("24", "1")])

    def test_quest_carriers_pinned(self):
        carriers = json.loads(CARRIERS.read_text(encoding="utf-8"))["carriers"]
        self.assertEqual(142, len(carriers))
        hostile_carriers = [key for key in carriers if self.team(key) == ("23", "0")]
        self.assertEqual(86, len(hostile_carriers))


if __name__ == "__main__":
    unittest.main()
