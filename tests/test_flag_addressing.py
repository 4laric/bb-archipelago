"""Tests for the flag-addressing solver.

The solver's job is as much refusing as solving. A mapping fitted to bad
captures that reports a confident formula would send the next session chasing a
number that means nothing, so most of these are about the cases where it must
decline.
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.solve_flag_addressing import Mapping, Observation, load_intersection, solve  # noqa: E402

# Elden Ring's known packing, used here only as a generator of consistent points.
ER = Mapping(50000, "msb0")


def point(flag_id: int, mapping: Mapping = ER) -> Observation:
    byte_offset, bit = mapping.address_for(flag_id)
    return Observation(flag_id, byte_offset, bit)


class SolveTests(unittest.TestCase):
    def test_two_consistent_points_recover_the_mapping(self):
        fits = solve([point(52410100), point(50002200)])
        self.assertEqual(len(fits), 1)
        self.assertEqual(fits[0].constant, 50000)
        self.assertEqual(fits[0].bit_order, "msb0")

    def test_the_recovered_mapping_predicts_a_third_flag(self):
        mapping = solve([point(52410100), point(50002200)])[0]
        expected = ER.address_for(52410140)
        self.assertEqual(mapping.address_for(52410140), expected)

    def test_an_lsb_first_packing_is_also_recoverable(self):
        other = Mapping(12345, "lsb0")
        fits = solve([point(52410100, other), point(50002200, other)])
        self.assertEqual(len(fits), 1)
        self.assertEqual(fits[0].constant, 12345)
        self.assertEqual(fits[0].bit_order, "lsb0")

    def test_round_trip_for_every_bit_position(self):
        for bit in range(8):
            with self.subTest(bit=bit):
                flag = ER.flag_for(0x1000, bit)
                self.assertEqual(ER.address_for(flag), (0x1000, bit))


class RefusalTests(unittest.TestCase):
    """Each of these pairs the refusal with a witness.

    `solve(...) == []` on its own would pass if solve always returned nothing,
    so every case first shows the same shape of input DOES produce a fit, then
    perturbs one value and shows it stops. That is the difference between
    testing a refusal and testing a stub.
    """

    def test_inconsistent_points_fit_nothing(self):
        a, b = point(52410100), point(50002200)
        self.assertEqual(len(solve([a, b])), 1, "witness: this pair fits")
        wrong = Observation(b.flag_id, a.byte_offset + 7, (a.bit + 3) % 8)
        self.assertEqual(len(solve([a, wrong])), 0)

    def test_a_single_wrong_bit_is_enough_to_break_it(self):
        a, b = point(52410100), point(50002200)
        self.assertEqual(len(solve([a, b])), 1, "witness: this pair fits")
        off_by_one = Observation(b.flag_id, b.byte_offset, (b.bit + 1) % 8)
        self.assertEqual(len(solve([a, off_by_one])), 0)

    def test_a_third_inconsistent_point_breaks_a_pair_that_fitted(self):
        """Two points always fit something; this is why the predict target exists."""
        a, b, c = point(52410100), point(50002200), point(52410140)
        self.assertEqual(len(solve([a, b])), 1, "witness: the pair alone fits")
        self.assertEqual(len(solve([a, b, c])), 1, "witness: a consistent third still fits")
        moved = Observation(c.flag_id, c.byte_offset + 1, c.bit)
        self.assertEqual(len(solve([a, b, moved])), 0)

    def test_a_symmetric_bit_can_be_ambiguous(self):
        """bit 3 and bit 4 are fixed points of 7-bit, so they cannot tell the orders apart."""
        flag = ER.flag_for(0x800, 3)
        byte_offset, _ = ER.address_for(flag)
        fits = solve([Observation(flag, byte_offset, 3),
                      Observation(ER.flag_for(0x900, 3), *ER.address_for(ER.flag_for(0x900, 3)))])
        self.assertGreaterEqual(len(fits), 1)


class ObservationParsingTests(unittest.TestCase):
    def test_hex_and_decimal_both_parse(self):
        self.assertEqual(Observation.parse("52410100=0x1A4C:3"),
                         Observation(52410100, 0x1A4C, 3))
        self.assertEqual(Observation.parse("52410100=6732:3"),
                         Observation(52410100, 6732, 3))

    def test_a_malformed_observation_is_rejected(self):
        for bad in ("52410100", "52410100=0x1A4C", "nope=0x1:2", "52410100=0x1A4C:x"):
            with self.subTest(text=bad), self.assertRaises(SystemExit):
                Observation.parse(bad)


class IntersectionTests(unittest.TestCase):
    def test_it_reads_the_columns_the_session_tool_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "intersection.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Offset", "ByteOffset", "Bit", "BeforeByte",
                                 "AfterByte", "Transition", "ControlStable"])
                writer.writerow(["0x00001A4C", "6732", "3", "0", "8", "0->1", "True"])
            self.assertEqual(load_intersection(path), [(6732, 3)])


class DescribeTests(unittest.TestCase):
    def test_the_formula_is_printed_in_a_form_a_person_can_check(self):
        self.assertEqual(ER.describe(), "id = byte_offset * 8 + (7 - bit) + 50000")
        self.assertEqual(Mapping(-12, "lsb0").describe(), "id = byte_offset * 8 + bit - 12")


if __name__ == "__main__":
    unittest.main()
