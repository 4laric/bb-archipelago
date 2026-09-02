from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from worlds.bloodborne.enemy_drops import (
    build_enemy_drop_assignments,
    enemy_drop_catalog,
)

ROOT = Path(__file__).resolve().parents[1]


def test_catalog_is_conservative_and_measured():
    catalog = enemy_drop_catalog()
    assert catalog["summary"] == {
        "referenced_npc_fields": 473,
        "groups": 26,
        "assignments": 149,
        "distinct_lots": 73,
        "exclusions": {
            "empty_lot": 65,
            "missing_lot": 3,
            "non_goods_or_unknown": 75,
            "persistent_acquisition_flag": 115,
        },
    }
    assert catalog["policy"]["categories"] == [4]
    assert catalog["policy"]["persistent_flags"] is False
    assert catalog["policy"]["repeatable_goods_only"] is True


def test_assignments_are_deterministic_unique_and_change_the_lot():
    first = build_enemy_drop_assignments("AP_TEST:1")
    assert first == build_enemy_drop_assignments("AP_TEST:1")
    assert first != build_enemy_drop_assignments("AP_TEST:2")
    assert len(first) >= 100
    keys = [(row["npc_param_id"], row["drop_field"]) for row in first]
    assert len(keys) == len(set(keys))
    assert all(row["source_lot_id"] != row["target_lot_id"] for row in first)


def test_dropsanity_is_global_deterministic_and_preserves_safe_lot_multiset():
    catalog = enemy_drop_catalog()
    entries = [entry for group in catalog["groups"] for entry in group["entries"]]
    assignments = build_enemy_drop_assignments("AP_TEST:1", "dropsanity")
    assert assignments == build_enemy_drop_assignments("AP_TEST:1", "dropsanity")
    assert assignments != build_enemy_drop_assignments("AP_TEST:1", "balanced")
    by_key = {(row["npc_param_id"], row["drop_field"]): row for row in assignments}
    assert Counter(int(row["source_lot_id"]) for row in entries) == Counter(
        int(by_key.get((row["npc_param_id"], row["drop_field"]), row)[
            "target_lot_id" if (row["npc_param_id"], row["drop_field"]) in by_key
            else "source_lot_id"
        ])
        for row in entries
    )
    group_by_key = {
        (row["npc_param_id"], row["drop_field"]): group["group"]
        for group in catalog["groups"] for row in group["entries"]
    }
    assert any(
        group_by_key[(row["npc_param_id"], row["drop_field"])]
        != next(
            group["group"] for group in catalog["groups"]
            if any(entry["source_lot_id"] == row["target_lot_id"] for entry in group["entries"])
        )
        for row in assignments
    )


def test_each_group_preserves_its_lot_multiset_including_unavoidable_fixed_rows():
    catalog = enemy_drop_catalog()
    assignments = {
        (row["npc_param_id"], row["drop_field"]): row
        for row in build_enemy_drop_assignments("AP_TEST:1")
    }
    for group in catalog["groups"]:
        sources = Counter(int(row["source_lot_id"]) for row in group["entries"])
        targets = Counter(
            int(assignments.get((row["npc_param_id"], row["drop_field"]), row)[
                "target_lot_id" if (row["npc_param_id"], row["drop_field"]) in assignments
                else "source_lot_id"
            ])
            for row in group["entries"]
        )
        assert sources == targets


def test_catalog_regenerates_byte_for_byte():
    path = ROOT / "worlds" / "bloodborne" / "enemy_drop_catalog.json"
    before = path.read_bytes()
    subprocess.run(
        [sys.executable, "tools/build_enemy_drop_catalog.py"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    assert path.read_bytes() == before


def test_yaml_option_is_opt_in():
    try:
        from worlds.bloodborne import BloodborneOptions
    except ImportError:
        return
    option = BloodborneOptions.type_hints["randomize_enemy_drops"]
    assert option.default == 0
    assert option.display_name == "Randomize Enemy Consumable Drops"
    assert option.options["balanced"] == 1
    assert option.options["dropsanity"] == 2


def test_native_writer_guards_only_declared_npc_drop_fields():
    source = (ROOT / "tools/bb_suppression_writer/Program.cs").read_text(encoding="utf-8")
    assert 'RequireSingleFile(game, "NpcParam.param")' in source
    assert "enemy drop assignments contain an invalid or repeated NPC field" in source
    assert "request says {edit.SourceLotId}" in source
    assert "enemy drop target lot {edit.TargetLotId} does not exist" in source
    assert 'originalNpcRows[row.ID].RequireEqualExcept' in source
