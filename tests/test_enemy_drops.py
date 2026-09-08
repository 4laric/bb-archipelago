from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from worlds.bloodborne.enemy_drops import (
    MODE_POOLS,
    PLAN_FORMAT,
    build_enemy_drop_assignments,
    enemy_drop_catalog,
)

ROOT = Path(__file__).resolve().parents[1]

# Seed sentinels. Every assertion below is measured from these exact seeds; a
# new sentinel needs its own witness, never a loosened bound.
SEED_A = "AP_TEST:1"
SEED_B = "AP_TEST:2"
FIXTURE_SEED = "BB_FIXTURE:v2"

DROP_FIELDS = {f"itemLotId_{index}" for index in range(1, 7)}


def populated_slots(assignments: list[dict]) -> list[dict]:
    return [
        slot
        for row in assignments
        for slot in row["lot"]["slots"]
        if slot["category"] != -1
    ]


def test_catalog_is_conservative_and_measured():
    catalog = enemy_drop_catalog()
    assert catalog["summary"] == {
        "referenced_npc_fields": 473,
        "eligible_fields": 280,
        "vanilla_populated_fields": 215,
        "vanilla_empty_fields": 65,
        "consumable_pool": 25,
        "material_pool": 3,
        "coldblood_pool": 14,
        "gem_pool": 28,
        "cadence_profiles": 69,
        "vanilla_lots_in_reserved_band": 0,
        "exclusions": {
            "missing_lot": 3,
            "non_goods_or_unknown": 75,
            "persistent_acquisition_flag": 115,
        },
    }
    assert catalog["policy"]["categories"] == [4, 8]
    assert catalog["policy"]["persistent_flags"] is False
    assert catalog["policy"]["repeatable_goods_only"] is True
    assert catalog["policy"]["rewrites_contents"] is True
    assert catalog["policy"]["edits_vanilla_lot_rows"] is False
    # The 65 formerly excluded empty tables are now targets, not exclusions.
    assert "empty_lot" not in catalog["summary"]["exclusions"]
    assert sum(1 for row in catalog["fields"] if not row["vanilla"]["populated"]) == 65


def test_assignments_are_deterministic_and_unique_per_seed_and_mode():
    for mode in MODE_POOLS:
        first = build_enemy_drop_assignments(SEED_A, mode)
        assert first == build_enemy_drop_assignments(SEED_A, mode)
        assert first != build_enemy_drop_assignments(SEED_B, mode)
        assert len(first) >= 200
        keys = [(row["npc_param_id"], row["drop_field"]) for row in first]
        assert len(keys) == len(set(keys))
        assert all(row["drop_field"] in DROP_FIELDS for row in first)
    assert build_enemy_drop_assignments(SEED_A, "balanced") != (
        build_enemy_drop_assignments(SEED_A, "dropsanity")
    )


def test_balanced_draws_only_consumables_and_dropsanity_widens_the_pool():
    catalog = enemy_drop_catalog()
    pools = catalog["pools"]
    consumables = {int(entry["item_id"]) for entry in pools["consumables"]}
    widened = {
        int(entry["item_id"])
        for name in ("materials", "coldblood", "gems")
        for entry in pools[name]
    }
    balanced = populated_slots(build_enemy_drop_assignments(SEED_A, "balanced"))
    assert balanced, "witness: the balanced plan populated at least one slot"
    assert all(slot["category"] == 4 for slot in balanced)
    assert {slot["item_id"] for slot in balanced} <= consumables
    assert not {slot["item_id"] for slot in balanced} & widened

    wide = populated_slots(build_enemy_drop_assignments(SEED_A, "dropsanity"))
    assert wide, "witness: the dropsanity plan populated at least one slot"
    assert {slot["item_id"] for slot in wide} <= consumables | widened
    drawn = {slot["item_id"] for slot in wide} & widened
    assert drawn, "witness: dropsanity actually drew from the widened pool"
    assert any(slot["category"] == 8 for slot in wide), "witness: a gem was placed"
    gems = {int(entry["item_id"]) for entry in pools["gems"]}
    assert all(
        slot["item_id"] in gems and slot["quantity"] == 1
        for slot in wide
        if slot["category"] == 8
    )


def test_gem_slots_stay_inside_the_fields_own_map_tier():
    catalog = enemy_drop_catalog()
    tiers = {
        (row["npc_param_id"], row["drop_field"]): set(row["gem_recipes"])
        for row in catalog["fields"]
    }
    checked = 0
    for row in build_enemy_drop_assignments(SEED_A, "dropsanity"):
        gem_slots = [s for s in row["lot"]["slots"] if s["category"] == 8]
        assert len(gem_slots) <= 1
        for slot in gem_slots:
            assert slot["item_id"] in tiers[(row["npc_param_id"], row["drop_field"])]
            checked += 1
    assert checked > 0, "witness: gem placements were actually examined"


def test_the_vial_share_of_balanced_output_is_bounded():
    """The v1 bug: 35.0% of vanilla enemy drop weight was Blood Vials, so a
    permutation of whole tables swapped one vial table for another."""
    slots = populated_slots(build_enemy_drop_assignments(SEED_A, "balanced"))
    assert len(slots) > 300, "witness: the sample is large enough to bound"
    counts = Counter(slot["item_id"] for slot in slots)
    assert counts[1000] > 0, "witness: Blood Vials are still in the pool"
    assert counts[900] > 0, "witness: Quicksilver Bullets are still in the pool"
    assert counts[1000] / len(slots) < 0.25
    assert counts[900] / len(slots) < 0.25
    # ...and the rewrite is not a two-item pool either.
    assert len(counts) >= 20


def test_empty_tables_gain_drops_and_density_stays_near_vanilla():
    catalog = enemy_drop_catalog()
    eligible = catalog["density"]["eligible_fields"]
    vanilla_share = catalog["density"]["vanilla_populated_fraction"]
    empty_fields = {
        (row["npc_param_id"], row["drop_field"])
        for row in catalog["fields"]
        if not row["vanilla"]["populated"]
    }
    assert empty_fields, "witness: vanilla-empty fields exist to be filled"
    for mode in MODE_POOLS:
        assignments = build_enemy_drop_assignments(SEED_A, mode)
        by_key = {(r["npc_param_id"], r["drop_field"]): r for r in assignments}
        filled = [
            key
            for key in empty_fields
            if key in by_key
            and any(s["category"] != -1 for s in by_key[key]["lot"]["slots"])
        ]
        assert len(filled) >= 30, f"{mode}: vanilla-empty tables gained drops"
        populated = sum(
            1
            for row in assignments
            if any(s["category"] != -1 for s in row["lot"]["slots"])
        )
        assert abs(populated / eligible - vanilla_share) < 0.10, mode


def test_every_emitted_slot_is_a_legal_vanilla_shaped_lot():
    catalog = enemy_drop_catalog()
    caps = {
        (int(entry["category"]), int(entry["item_id"])): int(entry["max_num"])
        for pool in catalog["pools"].values()
        for entry in pool
    }
    fields = {
        (row["npc_param_id"], row["drop_field"]): row for row in catalog["fields"]
    }
    profiles = {
        (profile["total_points"], profile["empty_points"])
        for shapes in catalog["cadence"]["profiles"].values()
        for profile in shapes
    }
    checked = 0
    for mode in MODE_POOLS:
        for row in build_enemy_drop_assignments(SEED_A, mode):
            field = fields[(row["npc_param_id"], row["drop_field"])]
            assert row["source_lot_id"] == field["source_lot_id"]
            assert row["lot"]["id"] == field["lot_id"]
            slots = row["lot"]["slots"]
            assert 1 <= len(slots) <= 8
            assert [s["slot"] for s in slots] == list(range(1, len(slots) + 1))
            assert all(s["base_point"] > 0 for s in slots)
            assert sum(1 for s in slots if s["category"] == -1) <= 1
            total = sum(s["base_point"] for s in slots)
            empty = sum(s["base_point"] for s in slots if s["category"] == -1)
            # Every emitted cadence is a shape a real vanilla enemy already
            # uses, so farm rates are vanilla by construction.
            assert (total, empty) in profiles or (
                total == field["vanilla"]["total_points"]
            )
            for slot in slots:
                if slot["category"] == -1:
                    assert slot["item_id"] == 0 and slot["quantity"] == 0
                    continue
                cap = caps[(slot["category"], slot["item_id"])]
                assert 1 <= slot["quantity"] <= cap
                checked += 1
    assert checked > 500, "witness: slot legality was checked at scale"


def test_the_reserved_lot_band_is_free_of_vanilla_and_category8_rows():
    import csv

    from tools.bb_inputs import read_blob
    from worlds.bloodborne.category8_awards import CATEGORY8_AWARDS

    catalog = enemy_drop_catalog()
    band = catalog["reserved_lot_band"]
    assert band["base"] == 99_000_000 and band["stride"] == 10
    ids = {int(row["lot_id"]) for row in catalog["fields"]}
    assert len(ids) == len(catalog["fields"]) == band["count"]
    assert min(ids) == band["base"] and max(ids) == band["top"]
    # Above both category-8 bands (98_000_000 generated, 98_100_000 events).
    assert min(ids) > max(award.item_lot_id for award in CATEGORY8_AWARDS)
    assert not ids & {award.item_lot_id for award in CATEGORY8_AWARDS}

    text = read_blob(ROOT / "research" / "bb_inputs.db", "params/ItemLotParam.csv")
    vanilla = {
        int(row["ID"])
        for row in csv.DictReader(text.decode("utf-8-sig").splitlines())
    }
    assert vanilla, "witness: the vanilla lot table was actually read"
    assert not ids & vanilla


def duplicate_vanilla_lot_ids() -> set[int]:
    """ItemLotParam row ids that appear more than once in the shipped table.

    Vanilla ships 14 of them. The writer fetches a rewritten enemy's vanilla lot
    as a template, and until this was fixed it demanded exactly one match, so
    0.1.0.0 refused every enemy-drop seed that rewrote a field pointing at one
    (the field report was 11800010). Read from the bundle rather than a
    hard-coded list so a rebundled param table cannot make this stale.
    """
    import csv

    from tools.bb_inputs import read_blob

    text = read_blob(ROOT / "research" / "bb_inputs.db", "params/ItemLotParam.csv")
    counts = Counter(
        int(row["ID"])
        for row in csv.DictReader(text.decode("utf-8-sig").splitlines())
    )
    assert counts, "witness: the vanilla lot table was actually read"
    return {lot_id for lot_id, count in counts.items() if count > 1}


def test_duplicate_source_lots_are_interchangeable_templates():
    """Why the writer may take the first duplicate in file order.

    The template only seeds the new row's non-slot shape: the writer overwrites
    `Name`, clears and rewrites every slot 01-08 from the plan, and sets
    `lotItem_Rarity` from the assignment. Prove the duplicate pairs differ in
    nothing else, so which one is used cannot change the emitted row.
    """
    import csv

    from tools.bb_inputs import read_blob

    text = read_blob(ROOT / "research" / "bb_inputs.db", "params/ItemLotParam.csv")
    rows = list(csv.DictReader(text.decode("utf-8-sig").splitlines()))
    by_id: dict[int, list[dict]] = {}
    for row in rows:
        by_id.setdefault(int(row["ID"]), []).append(row)
    duplicates = {k: v for k, v in by_id.items() if len(v) > 1}
    assert len(duplicates) == 14, "witness: the duplicated ids were found"
    assert 11_800_010 in duplicates, "the id the field report died on"
    # Fields the writer rewrites unconditionally for a v2 enemy drop lot.
    rewritten = {"Name", "lotItem_Rarity", "getItemFlagId", "cumulateNumFlagId",
                 "cumulateNumMax"}
    for index in range(1, 9):
        rewritten |= {
            f"lotItemCategory{index:02}", f"lotItemId{index:02}",
            f"lotItemNum{index:02}", f"lotItemBasePoint{index:02}",
            f"cumulateLotPoint{index:02}", f"getItemFlagId{index:02}",
            f"enableLuck{index:02}", f"cumulateReset{index:02}",
        }
    checked = 0
    for lot_id, group in sorted(duplicates.items()):
        first, *rest = group
        for other in rest:
            differing = {f for f in first if first[f] != other[f]}
            assert not differing - rewritten, (
                f"lot {lot_id} duplicates differ in {sorted(differing - rewritten)}, "
                "so first-in-file-order is no longer an immaterial choice"
            )
            checked += 1
    assert checked == 14, "witness: every duplicate pair was compared"


def test_generated_plan_covers_a_duplicated_source_lot():
    """The regression the fixture must keep exercising."""
    duplicates = duplicate_vanilla_lot_ids()
    assert duplicates, "witness: the duplicate id set is non-empty"
    assignments = build_enemy_drop_assignments(FIXTURE_SEED, "dropsanity")
    assert assignments, "witness: the plan was actually generated"
    hit = sorted(
        {row["source_lot_id"] for row in assignments} & duplicates
    )
    assert hit == [11_800_010], (
        "the fixture seed no longer rewrites a duplicated vanilla lot; pin a "
        "seed that does, or the binder job stops covering the duplicate path"
    )


def test_v2_fixture_exercises_the_duplicate_template_path():
    """The binder job feeds this fixture to `--seed-weapons`; if no row's
    source lot is duplicated, CI never compiles the path that broke 0.1.0.0."""
    fixture = json.loads(
        (ROOT / "tests/fixtures/enemy-drop-request-v2.json").read_text(
            encoding="utf-8"
        )
    )
    sources = {row["source_lot_id"] for row in fixture["enemy_drop_assignments"]}
    assert sources & duplicate_vanilla_lot_ids(), (
        "the committed v2 fixture no longer covers a duplicated source lot"
    )


def build_v2_fixture() -> dict:
    """The committed v2 writer fixture, derived from the world it must match."""
    assignments = build_enemy_drop_assignments(FIXTURE_SEED, "dropsanity")
    gem = next(
        row for row in assignments
        if any(slot["category"] == 8 for slot in row["lot"]["slots"])
    )
    empty = next(
        row for row in assignments
        if all(slot["category"] == -1 for slot in row["lot"]["slots"])
    )
    # A field whose vanilla lot id is duplicated in ItemLotParam. Without one
    # the binder job never exercises the template fetch that refused every
    # 0.1.0.0 enemy-drop seed rolling such a field.
    duplicates = duplicate_vanilla_lot_ids()
    duplicated = next(
        row for row in assignments
        if row is not gem and row is not empty
        and row["source_lot_id"] in duplicates
    )
    plain = [
        row for row in assignments
        if row is not gem and row is not empty and row is not duplicated
        and any(slot["category"] == 4 for slot in row["lot"]["slots"])
    ][:2]
    chosen = sorted(
        [*plain, gem, empty, duplicated],
        key=lambda row: (row["npc_param_id"], row["drop_field"]),
    )
    return {
        "enemy_drop_plan_format": PLAN_FORMAT,
        "randomize_enemy_drops": True,
        "enemy_drop_mode": "dropsanity",
        "enemy_drop_assignments": chosen,
    }


def test_v1_fixture_still_parses_as_the_permutation_plan():
    """Seeds rolled by the shipped world are still in flight; the writer
    branches on the marker and the v1 request must keep its old shape."""
    fixture = json.loads(
        (ROOT / "tests/fixtures/enemy-drop-request.json").read_text(encoding="utf-8")
    )
    assert fixture["randomize_enemy_drops"] is True
    assert "enemy_drop_plan_format" not in fixture
    assert fixture["enemy_drop_assignments"]
    for row in fixture["enemy_drop_assignments"]:
        assert set(row) == {
            "npc_param_id", "drop_field", "source_lot_id", "target_lot_id"
        }
        assert row["source_lot_id"] != row["target_lot_id"]
        assert row["drop_field"] in DROP_FIELDS


def test_v2_fixture_matches_the_world():
    path = ROOT / "tests/fixtures/enemy-drop-request-v2.json"
    assert json.loads(path.read_text(encoding="utf-8")) == build_v2_fixture()


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


def test_native_writer_handles_both_plan_formats():
    source = (ROOT / "tools/bb_suppression_writer/Program.cs").read_text(
        encoding="utf-8"
    )
    # v1 permutation path survives untouched.
    assert "enemy drop assignments contain an invalid or repeated NPC field" in source
    assert "enemy drop target lot {edit.TargetLotId} does not exist" in source
    # v2 rewrite path, branched on the marker.
    assert '"bb-enemy-drop-plan-v2"' in source
    assert '"enemy_drop_plan_format"' in source
    assert "unsupported enemy drop plan format {dropPlanFormat}" in source
    assert "enemy drop lot {edit.Lot.Id} already exists in the input binder" in source
    assert "whose maxNum is {maxNum}" in source
    assert "awards unwitnessed gem recipe {slot.ItemId}" in source
    assert "uses forbidden category {slot.Category}" in source
    assert "seed parameter write changed the ItemLotParam row set" in source
    # The template fetch tolerates vanilla's duplicated lot ids (0.1.0.0 died
    # on 11800010) and no longer demands exactly one match.
    assert "expected an ItemLotParam row {edit.SourceLotId}, found none" in source
    assert "FirstOrDefault(row => row.ID == edit.SourceLotId)" in source
    # ...while the suppression path, whose plan provably touches no duplicated
    # id, keeps its strict one-row rule.
    assert "expected one ItemLotParam row {lotId}, found {lotRows.Count}" in source
    assert "slot {slot} failed round-trip verification" in source
    assert "originalNpcRows[row.ID].RequireEqualExcept" in source
