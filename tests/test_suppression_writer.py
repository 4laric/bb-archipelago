"""Tests for the ItemLotParam writer.

A param writer's failure mode is not a crash. It is a file that loads, plays,
and is subtly wrong — a shifted column, a cleared flag, a row that changed when
nobody asked. So the tests are mostly about what must NOT have changed.

The round-trip test runs against the real 2 MB table from the committed bundle,
because a writer that cannot reproduce its own input has no business modifying
it, and that is only worth knowing about the actual file.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.apply_vanilla_suppression import (  # noqa: E402
    SuppressionError,
    Table,
    apply_plan,
    read_params,
    verify,
)

BUNDLE = REPO / "research" / "bb_inputs.db"
NATIVE_WRITER = REPO / "tools" / "bb_suppression_writer" / "Program.cs"

# A miniature ItemLotParam with the same shape as the real one: a header with a
# trailing empty field, and data rows one field shorter.
COLUMNS = (["ID", "Name"]
           + [f"lotItemId{n:02d}" for n in range(1, 9)]
           + [f"lotItemCategory{n:02d}" for n in range(1, 9)]
           + [f"lotItemNum{n:02d}" for n in range(1, 9)]
           + ["getItemFlagId", ""])
FLAG_AT = COLUMNS.index("getItemFlagId")


def row(lot: str, name: str, items: dict[int, tuple[str, str]], flag: str) -> str:
    fields = ["0"] * (len(COLUMNS) - 1)
    fields[COLUMNS.index("ID")] = lot
    fields[COLUMNS.index("Name")] = name
    fields[COLUMNS.index("getItemFlagId")] = flag
    for slot, (goods, category) in items.items():
        fields[COLUMNS.index(f"lotItemId{slot:02d}")] = goods
        fields[COLUMNS.index(f"lotItemCategory{slot:02d}")] = category
        fields[COLUMNS.index(f"lotItemNum{slot:02d}")] = "2"
    return ",".join(fields)


def table(*rows: str) -> Table:
    return Table.load(",".join(COLUMNS) + "\n" + "\n".join(rows) + "\n")


def plan(*edits: dict, placeholder: str = "1000") -> dict:
    return {"format": "bb-vanilla-suppression-plan-v2",
            "placeholder": {"goods_id": placeholder, "name": "Blood Vial", "quantity": 1},
            "edits": list(edits)}


def edit(key: str, lot: str, goods: str, flag: str, category: str = "4") -> dict:
    return {"item_key": key, "item_category": category, "goods_id": goods, "item_lot_id": lot,
            "lot_name": "n", "acquisition_flag": flag, "placements": 1}


class RoundTripTests(unittest.TestCase):
    """The control. Everything else is only meaningful if this holds."""

    @unittest.skipUnless(BUNDLE.exists(), "needs the committed inputs bundle")
    def test_the_real_table_round_trips_byte_for_byte(self):
        text = read_params(BUNDLE)
        self.assertEqual(Table.load(text).dump(), text)

    @unittest.skipUnless(BUNDLE.exists(), "needs the committed inputs bundle")
    def test_the_real_header_is_one_field_longer_than_its_rows(self):
        """The asymmetry that makes csv.DictWriter corrupt this file."""
        text = read_params(BUNDLE)
        loaded = Table.load(text)
        self.assertEqual(len(loaded.header), 71)
        self.assertEqual(loaded.header[-1], "")
        self.assertEqual(len(loaded.lines[0].split(",")), 70)

    def test_a_fixture_round_trips(self):
        text = ",".join(COLUMNS) + "\n" + row("1", "a", {1: ("4001", "4")}, "500") + "\n"
        self.assertEqual(Table.load(text).dump(), text)

    def test_native_writer_exposes_read_only_shop_inspection(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('args[0] == "--inspect-shops"', source)
        self.assertIn('RequireSingleFile(game, "ShopLineupParam.param")', source)
        self.assertIn('cell.Def.InternalName', source)

    def test_native_writer_can_verify_the_committed_shop_gate_witnesses(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('args[0] == "--audit-shop-gates"', source)
        self.assertIn('Enumerable.Range(12101000, 10)', source)
        self.assertIn('representative row {rowId} no longer matches its stock witness', source)
        self.assertIn('ordinary Bath gate groups are incomplete', source)

    def test_native_writer_applies_only_a_bijective_ordinary_bath_permutation(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('shop_gate_permutation', source)
        self.assertIn('bijection over the ten ordinary Bath gates', source)
        self.assertIn('Convert.ToInt32(RequireCell(row, "shopType").Value) == 0', source)
        self.assertIn('allowed.Add("qwcId")', source)

    def test_starting_attire_canary_is_explicit_and_refusal_safe(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('args[0] == "--write-starting-attire-canary"', source)
        self.assertIn('args[8] == "--apply"', source)
        self.assertIn('input and output paths must differ', source)
        self.assertIn('refusing to overwrite existing output', source)
        self.assertIn('row.ID is >= 2000 and <= 2009', source)
        self.assertIn('round-trip changed unrelated binder file', source)

    def test_starting_attire_canary_validates_literal_protector_slots(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('"headEquip", "bodyEquip", "armEquip", "legEquip"', source)
        self.assertIn('expected one EquipParamProtector row', source)
        self.assertIn('is not exclusively a {slotFields[index]} row', source)

    def test_starting_attire_catalog_has_a_native_corpus_audit(self):
        source = NATIVE_WRITER.read_text(encoding="utf-8")
        self.assertIn('args[0] == "--audit-starting-attire-catalog"', source)
        self.assertIn('set_key\\tprotector_id\\tslot\\tname\\tgrant_descriptor', source)
        self.assertIn('protector {id} is not exclusively a {piece[2]} row', source)
        self.assertIn('starting-attire catalog repeats a protector id', source)


class ApplyTests(unittest.TestCase):
    def test_the_planned_slot_is_replaced_and_the_flag_is_not(self):
        t = table(row("100", "lot", {1: ("4001", "4")}, "50000001"))
        applied = apply_plan(t, plan(edit("k", "100", "4001", "50000001")))
        self.assertEqual(len(applied), 1)
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemId01"), "1000")
        self.assertEqual(t.field(t.row_by_id["100"], "getItemFlagId"), "50000001")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemCategory01"), "4")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemNum01"), "1")

    def test_it_finds_the_right_slot_rather_than_assuming_the_first(self):
        t = table(row("100", "lot", {1: ("9999", "4"), 3: ("4001", "4")}, "50000001"))
        applied = apply_plan(t, plan(edit("k", "100", "4001", "50000001")))
        self.assertEqual(applied[0].slot, "03")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemId01"), "9999")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemId03"), "1000")

    def test_equipment_is_replaced_by_a_goods_placeholder(self):
        t = table(row("100", "lot", {2: ("7100000", "0")}, "50000001"))
        applied = apply_plan(
            t, plan(edit("saw_spear", "100", "7100000", "50000001", category="0"))
        )
        self.assertEqual(applied[0].was_category, "0")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemId02"), "1000")
        self.assertEqual(t.field(t.row_by_id["100"], "lotItemCategory02"), "4")

    def test_a_flagless_lot_is_edited_and_its_absent_flag_is_left_absent(self):
        """A lot with getItemFlagId -1 must not be refused, or invented into.

        The Oedon Tomb Key's vanilla award (lot 31000, handed out by EMEVD
        event 12411800) has no acquisition flag at all. The writer's invariant
        is "the flag did not move", and -1 is what not moving looks like here;
        refusing the row instead would leave the vanilla key in the game.
        """
        t = table(row("31000", "lot", {1: ("4000", "4")}, "-1"))
        applied = apply_plan(t, plan(edit("oedon_tomb_key", "31000", "4000", "-1")))
        self.assertEqual(applied[0].acquisition_flag, "-1")
        self.assertEqual(t.field(t.row_by_id["31000"], "lotItemId01"), "1000")
        self.assertEqual(t.field(t.row_by_id["31000"], "getItemFlagId"), "-1")

    def test_untouched_rows_are_byte_identical(self):
        t = table(row("100", "a", {1: ("4001", "4")}, "1"),
                  row("200", "b", {1: ("4002", "4")}, "2"))
        original = list(t.lines)
        apply_plan(t, plan(edit("k", "100", "4001", "1")))
        self.assertEqual(t.lines[1], original[1])

    def test_a_dry_run_changes_nothing(self):
        t = table(row("100", "lot", {1: ("4001", "4")}, "1"))
        original = list(t.lines)
        apply_plan(t, plan(edit("k", "100", "4001", "1")), dry_run=True)
        self.assertEqual(t.lines, original)


class RefusalTests(unittest.TestCase):
    def apply(self, t: Table, p: dict):
        with self.assertRaises(SuppressionError) as caught:
            apply_plan(t, p)
        return str(caught.exception)

    def test_an_absent_lot(self):
        t = table(row("100", "a", {1: ("4001", "4")}, "1"))
        self.assertIn("not in ItemLotParam", self.apply(t, plan(edit("k", "999", "4001", "1"))))

    def test_the_item_is_not_where_the_plan_says(self):
        t = table(row("100", "a", {1: ("4002", "4")}, "1"))
        self.assertIn("0 slots", self.apply(t, plan(edit("k", "100", "4001", "1"))))

    def test_two_slots_award_the_same_item(self):
        t = table(row("100", "a", {1: ("4001", "4"), 2: ("4001", "4")}, "1"))
        self.assertIn("2 slots", self.apply(t, plan(edit("k", "100", "4001", "1"))))

    def test_the_flag_moved_since_the_plan_was_built(self):
        t = table(row("100", "a", {1: ("4001", "4")}, "77777"))
        message = self.apply(t, plan(edit("k", "100", "4001", "1")))
        self.assertIn("detection target moved", message)

    def test_a_matching_id_in_the_wrong_category_is_not_a_match(self):
        """Goods 4001 and weapon 4001 are different items."""
        t = table(row("100", "a", {1: ("4001", "1")}, "1"))
        self.assertIn("0 slots", self.apply(t, plan(edit("k", "100", "4001", "1"))))

    def test_a_foreign_plan_format(self):
        t = table(row("100", "a", {1: ("4001", "4")}, "1"))
        bad = plan(edit("k", "100", "4001", "1")); bad["format"] = "something-else"
        self.assertIn("expected a bb-vanilla-suppression-plan-v2", self.apply(t, bad))

    def test_a_non_numeric_placeholder(self):
        t = table(row("100", "a", {1: ("4001", "4")}, "1"))
        self.assertIn("must be numeric",
                     self.apply(t, plan(edit("k", "100", "4001", "1"), placeholder="vial")))

    def test_a_table_missing_a_required_column(self):
        with self.assertRaises(SuppressionError):
            Table.load("ID,Name\n1,a\n")


class VerifyTests(unittest.TestCase):
    """verify() is what turns 'the write succeeded' into 'the write was right'."""

    def setUp(self):
        self.before = table(row("100", "a", {1: ("4001", "4")}, "1"),
                            row("200", "b", {1: ("4002", "4")}, "2"))
        self.after = table(row("100", "a", {1: ("4001", "4")}, "1"),
                           row("200", "b", {1: ("4002", "4")}, "2"))
        self.applied = apply_plan(self.after, plan(edit("k", "100", "4001", "1")))

    def test_a_correct_edit_verifies(self):
        verify(self.before, self.after, self.applied)

    def test_an_unrequested_row_change_is_caught(self):
        self.after.set_field(self.after.row_by_id["200"], "lotItemId01", "1000")
        with self.assertRaises(SuppressionError) as caught:
            verify(self.before, self.after, self.applied)
        self.assertIn("unexpected", str(caught.exception))

    def test_a_cleared_flag_is_caught(self):
        self.after.set_field(self.after.row_by_id["100"], "getItemFlagId", "0")
        with self.assertRaises(SuppressionError) as caught:
            verify(self.before, self.after, self.applied)
        self.assertIn("acquisition flag changed", str(caught.exception))

    def test_a_changed_category_is_caught(self):
        self.after.set_field(self.after.row_by_id["100"], "lotItemCategory01", "1")
        with self.assertRaises(SuppressionError) as caught:
            verify(self.before, self.after, self.applied)
        self.assertIn("category changed", str(caught.exception))

    def test_a_row_that_was_not_actually_edited_is_caught(self):
        self.after.set_field(self.after.row_by_id["100"], "lotItemId01", "4001")
        with self.assertRaises(SuppressionError):
            verify(self.before, self.after, self.applied)

    def test_a_dropped_row_is_caught(self):
        self.after.lines.pop()
        with self.assertRaises(SuppressionError) as caught:
            verify(self.before, self.after, self.applied)
        self.assertIn("row count", str(caught.exception))


@unittest.skipUnless(BUNDLE.exists(), "needs the committed inputs bundle")
class EndToEndTests(unittest.TestCase):
    """Plan the real pool, apply it to the real table, check what moved."""

    @classmethod
    def setUpClass(cls):
        from tools.plan_vanilla_suppression import build_complete_plan
        p = build_complete_plan(REPO / "research", {"goods_id": "1000", "name": "Blood Vial"})
        cls.plan = json.loads(json.dumps({
            "format": "bb-vanilla-suppression-plan-v2",
            "placeholder": p.placeholder,
            "edits": [e.__dict__ for e in p.edits]}))
        cls.text = read_params(BUNDLE)
        cls.before = Table.load(cls.text)
        cls.after = Table.load(cls.text)
        cls.applied = apply_plan(cls.after, cls.plan)

    def test_it_verifies(self):
        verify(self.before, self.after, self.applied)

    def test_the_flagless_script_award_lands_in_the_real_table(self):
        """The one row in the real plan that carries no acquisition flag."""
        applied = {a.item_lot_id: a for a in self.applied}
        self.assertIn("31000", applied)
        self.assertEqual(applied["31000"].was, "4000")
        self.assertEqual(applied["31000"].now, "1000")
        self.assertEqual(applied["31000"].acquisition_flag, "-1")
        self.assertEqual(self.after.field(self.after.row_by_id["31000"], "getItemFlagId"), "-1")

    def test_exactly_the_planned_rows_changed(self):
        changed = sum(1 for a, b in zip(self.before.lines, self.after.lines) if a != b)
        no_ops = [a for a in self.applied if a.already_placeholder]
        self.assertEqual(changed, len(self.plan["edits"]) - len(no_ops))
        # Witness: the no-op branch is exercised by the real corpus rather
        # than merely tolerated. These lots already award one Blood Vial.
        self.assertEqual(
            sorted(a.item_lot_id for a in no_ops),
            ["2300090", "2300100", "2300110", "2400190",
             "3400090", "3400110", "3400150", "3400250", "3400260",
             "3400330", "3401050"],
        )

    def test_every_flag_survived(self):
        for a in self.applied:
            row_index = self.after.row_by_id[a.item_lot_id]
            self.assertEqual(self.after.field(row_index, "getItemFlagId"), a.acquisition_flag)
            self.assertNotEqual(a.acquisition_flag, "0")

    def test_the_output_is_still_the_same_shape(self):
        reloaded = Table.load(self.after.dump())
        self.assertEqual(len(reloaded.lines), len(self.before.lines))
        self.assertEqual(reloaded.header, self.before.header)

    def test_the_placeholder_is_a_real_stackable_good(self):
        """1000 is the Blood Vial: 0x400003E8 in DELIVERY_FIXTURES, cap 20, not unique."""
        from worlds.bloodborne.runtime_bindings import DELIVERY_FIXTURES
        vial = DELIVERY_FIXTURES["blood_vial"]
        self.assertEqual(vial.normalized_item_id & 0x0FFFFFFF,
                         int(self.plan["placeholder"]["goods_id"]))


if __name__ == "__main__":
    unittest.main()
