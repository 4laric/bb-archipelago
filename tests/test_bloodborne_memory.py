"""Tests for the read-only shadPS4 reader.

The point of these is that the PE walk and the hook-site comparison are proved
without Windows, without shadPS4 and without the game — because that is where
the bugs are, and requiring the game to exercise them would mean they were
never exercised.

Every test builds a synthetic image and asserts against bytes it laid down
itself, so a passing run means the parser really parsed something.
"""

from __future__ import annotations

import struct
import unittest

from worlds.bloodborne.memory import (
    FALLBACK_GUEST_BASE,
    HOOK_SITES,
    AttachReport,
    ImageParseError,
    MemoryReadError,
    resolve_export,
    resolve_guest_base,
    summarise,
    verify_sites,
)

MODULE_BASE = 0x140000000
GUEST_BASE = 0x800000000
EXPORT_DIR_RVA = 0x1000
EBOOT_VAR_RVA = 0x2000


class FakeReader:
    """Sparse read-only memory. Unmapped reads raise, exactly like the real one."""

    def __init__(self) -> None:
        self.regions: list[tuple[int, bytearray]] = []
        self.reads = 0

    def map(self, address: int, data: bytes) -> None:
        self.regions.append((address, bytearray(data)))

    def poke(self, address: int, data: bytes) -> None:
        for start, buf in self.regions:
            if start <= address and address + len(data) <= start + len(buf):
                buf[address - start:address - start + len(data)] = data
                return
        raise AssertionError(f"poke outside any mapped region: 0x{address:X}")

    def read(self, address: int, size: int) -> bytes:
        self.reads += 1
        for start, buf in self.regions:
            if start <= address and address + size <= start + len(buf):
                return bytes(buf[address - start:address - start + size])
        raise MemoryReadError(f"unmapped read at 0x{address:X}+{size}")


def build_image(exports: dict[str, int], *, magic: int = 0x20B) -> bytes:
    """A minimal but structurally real PE32+ image with an export directory."""
    image = bytearray(0x3000)
    image[0:2] = b"MZ"
    struct.pack_into("<I", image, 0x3C, 0x80)
    image[0x80:0x84] = b"PE\0\0"
    struct.pack_into("<H", image, 0x98, magic)          # optional header magic
    data_dir = 0x98 + (112 if magic == 0x20B else 96)
    struct.pack_into("<II", image, data_dir, EXPORT_DIR_RVA, 0x100)

    names = sorted(exports)
    n = len(names)
    functions_rva = EXPORT_DIR_RVA + 0x40
    names_rva = functions_rva + n * 4
    ordinals_rva = names_rva + n * 4
    strings_rva = ordinals_rva + n * 2

    struct.pack_into("<I", image, EXPORT_DIR_RVA + 0x18, n)
    struct.pack_into("<I", image, EXPORT_DIR_RVA + 0x1C, functions_rva)
    struct.pack_into("<I", image, EXPORT_DIR_RVA + 0x20, names_rva)
    struct.pack_into("<I", image, EXPORT_DIR_RVA + 0x24, ordinals_rva)

    cursor = strings_rva
    for i, name in enumerate(names):
        struct.pack_into("<I", image, functions_rva + i * 4, exports[name])
        struct.pack_into("<I", image, names_rva + i * 4, cursor)
        struct.pack_into("<H", image, ordinals_rva + i * 2, i)
        encoded = name.encode("ascii") + b"\0"
        image[cursor:cursor + len(encoded)] = encoded
        cursor += len(encoded)
    return bytes(image)


def reader_with_game(*, exports: dict[str, int] | None = None,
                     eboot_value: int = GUEST_BASE,
                     guest_base: int = GUEST_BASE) -> FakeReader:
    """A reader carrying both a shadPS4 image and correct bytes at every site."""
    if exports is None:
        exports = {"g_eboot_address": EBOOT_VAR_RVA, "some_other_export": 0x2100}
    reader = FakeReader()
    reader.map(MODULE_BASE, build_image(exports))
    reader.poke(MODULE_BASE + EBOOT_VAR_RVA, struct.pack("<Q", eboot_value))
    for site in HOOK_SITES:
        body = site.expected if site.expected is not None else b"\x90"
        reader.map(guest_base + site.offset, (body + b"\xcc" * 16)[:16])
    return reader


class ExportResolutionTests(unittest.TestCase):
    def test_resolves_a_named_data_export(self):
        reader = reader_with_game()
        self.assertEqual(resolve_export(reader, MODULE_BASE, "g_eboot_address"),
                         MODULE_BASE + EBOOT_VAR_RVA)

    def test_resolves_the_right_one_of_several(self):
        reader = reader_with_game(exports={"aaa": 0x2100, "g_eboot_address": EBOOT_VAR_RVA,
                                           "zzz": 0x2200})
        self.assertEqual(resolve_export(reader, MODULE_BASE, "zzz"), MODULE_BASE + 0x2200)
        self.assertEqual(resolve_export(reader, MODULE_BASE, "aaa"), MODULE_BASE + 0x2100)

    def test_pe32_image_also_parses(self):
        reader = FakeReader()
        reader.map(MODULE_BASE, build_image({"g_eboot_address": EBOOT_VAR_RVA}, magic=0x10B))
        self.assertEqual(resolve_export(reader, MODULE_BASE, "g_eboot_address"),
                         MODULE_BASE + EBOOT_VAR_RVA)

    def test_missing_symbol_raises(self):
        reader = reader_with_game(exports={"something_else": 0x2100})
        with self.assertRaises(ImageParseError):
            resolve_export(reader, MODULE_BASE, "g_eboot_address")

    def test_non_pe_image_raises(self):
        reader = FakeReader()
        reader.map(MODULE_BASE, b"\x00" * 0x200)
        with self.assertRaises(ImageParseError):
            resolve_export(reader, MODULE_BASE, "g_eboot_address")

    def test_unknown_optional_header_magic_raises(self):
        reader = FakeReader()
        reader.map(MODULE_BASE, build_image({"g_eboot_address": EBOOT_VAR_RVA}, magic=0x1234))
        with self.assertRaises(ImageParseError):
            resolve_export(reader, MODULE_BASE, "g_eboot_address")


class GuestBaseTests(unittest.TestCase):
    def test_export_is_preferred_and_reported_as_such(self):
        reader = reader_with_game()
        base = resolve_guest_base(reader, MODULE_BASE)
        self.assertEqual(base.guest_base, GUEST_BASE)
        self.assertEqual(base.source, "export")
        self.assertTrue(base.trustworthy)

    def test_a_relocated_base_is_followed_not_assumed(self):
        """The whole reason this exists: do not hardcode 0x800000000."""
        moved = 0x900000000
        reader = reader_with_game(eboot_value=moved, guest_base=moved)
        base = resolve_guest_base(reader, MODULE_BASE)
        self.assertEqual(base.guest_base, moved)
        self.assertNotEqual(base.guest_base, FALLBACK_GUEST_BASE)
        results = verify_sites(reader, base.guest_base)
        self.assertTrue(all(r.matched is not False for r in results))

    def test_missing_export_falls_back_but_is_marked_untrustworthy(self):
        reader = reader_with_game(exports={"nope": 0x2100})
        base = resolve_guest_base(reader, MODULE_BASE)
        self.assertEqual(base.guest_base, FALLBACK_GUEST_BASE)
        self.assertFalse(base.trustworthy)
        self.assertIn("g_eboot_address", base.detail)

    def test_zero_pointer_means_the_game_is_not_loaded(self):
        reader = reader_with_game(eboot_value=0)
        base = resolve_guest_base(reader, MODULE_BASE)
        self.assertFalse(base.trustworthy)
        self.assertIn("not be loaded", base.detail.replace("probably not loaded", "not be loaded"))


class HookSiteTests(unittest.TestCase):
    def test_a_clean_image_verifies_every_recorded_site(self):
        reader = reader_with_game()
        results = verify_sites(reader, GUEST_BASE)
        self.assertTrue(all(r.matched is not False for r in results))
        verified = [r for r in results if r.matched is True]
        self.assertEqual(len(verified), sum(1 for s in HOOK_SITES if s.expected is not None))

    def test_a_changed_byte_is_caught(self):
        reader = reader_with_game()
        site = next(s for s in HOOK_SITES if s.name == "consumable_quantity")
        reader.poke(GUEST_BASE + site.offset, b"\xe9\x00\x00\x00\x00")
        results = verify_sites(reader, GUEST_BASE)
        bad = [r for r in results if r.matched is False]
        self.assertEqual([r.site.name for r in bad], ["consumable_quantity"])
        self.assertIn("MISMATCH", summarise(results))

    def test_a_site_with_no_recorded_bytes_is_uncheckable_not_passing(self):
        reader = reader_with_game()
        results = verify_sites(reader, GUEST_BASE)
        one_hit = next(r for r in results if r.site.name == "one_hit")
        self.assertIsNone(one_hit.matched)
        self.assertEqual(one_hit.status, "uncheckable")
        # and it must not inflate the verified count
        self.assertNotIn("one_hit", summarise(results))
        self.assertIn("no recorded bytes", summarise(results))

    def test_uncheckable_sites_still_report_what_was_read(self):
        reader = reader_with_game()
        report = AttachReport(1234, MODULE_BASE, resolve_guest_base(reader, MODULE_BASE),
                              verify_sites(reader, GUEST_BASE))
        text = "\n".join(report.lines())
        self.assertIn("no recorded bytes for one_hit", text)

    def test_the_banner_says_so_when_the_base_was_not_resolved(self):
        reader = reader_with_game(exports={"nope": 0x2100})
        report = AttachReport(1234, MODULE_BASE, resolve_guest_base(reader, MODULE_BASE),
                              verify_sites(reader, FALLBACK_GUEST_BASE))
        self.assertIn("NOT resolved from the export", "\n".join(report.lines()))

    def test_an_unreachable_site_raises_rather_than_reporting_ok(self):
        reader = reader_with_game()
        with self.assertRaises(MemoryReadError):
            verify_sites(reader, 0x123400000)


class HookTableTests(unittest.TestCase):
    """The table is a claim about the game; keep it honest."""

    def test_every_site_declares_its_evidence(self):
        allowed = {"published", "observed", "inferred", "unrecorded"}
        for site in HOOK_SITES:
            self.assertIn(site.evidence, allowed, site.name)

    def test_unrecorded_sites_carry_no_expected_bytes_and_vice_versa(self):
        for site in HOOK_SITES:
            if site.evidence == "unrecorded":
                self.assertIsNone(site.expected, site.name)
            else:
                self.assertIsNotNone(site.expected, site.name)
                self.assertGreaterEqual(len(site.expected), 5, site.name)

    def test_inferred_sites_say_they_have_not_been_read_back(self):
        for site in HOOK_SITES:
            if site.evidence == "inferred":
                self.assertTrue(site.note, f"{site.name} is inferred and must explain itself")

    def test_offsets_are_distinct_and_eboot_relative(self):
        offsets = [s.offset for s in HOOK_SITES]
        self.assertEqual(len(offsets), len(set(offsets)))
        for site in HOOK_SITES:
            # an eboot-relative offset, never an already-based absolute address
            self.assertLess(site.offset, 0x10000000, site.name)


if __name__ == "__main__":
    unittest.main()
