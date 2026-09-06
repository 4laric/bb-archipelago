"""Control fixtures use the recorded ZCrashv5 Tonitrus slot, not a fabricated ID."""
import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import weapon_probe_core as core

class Memory:
    def __init__(self):
        self.data = {}
    def put(self, address, data):
        self.data.update((address+i, value) for i, value in enumerate(data))
    def read(self, address, size):
        try:
            return bytes(self.data[address+i] for i in range(size))
        except KeyError as exc:
            raise OSError('unmapped fixture memory') from exc

def fixture():
    mem = Memory()
    base, inv, primary, secondary = 0x6000000, 0x208067778, 0x208067710, 0x208067BD0
    mem.put(base + core.INVENTORY_CELL, struct.pack('<Q', inv))
    header = bytearray(0x90)
    struct.pack_into('<I', header, 0x24, 76)
    struct.pack_into('<I', header, 0x88, 76)
    struct.pack_into('<Q', header, 0x58, primary)
    struct.pack_into('<Q', header, 0x48, secondary)
    # Use disjoint primary allocation in this synthetic geometry.
    primary = 0x300000000
    struct.pack_into('<Q', header, 0x58, primary)
    mem.put(inv, header)
    mem.put(primary, bytes(76 * 16))
    mem.put(secondary, bytes.fromhex('BA048080 A45DC600 01000000 4C407B8A'))
    return mem, base, inv, secondary

class ProbeTests(unittest.TestCase):
    def test_recorded_tonitrus_control_and_split_boundary(self):
        mem, base, _, _ = fixture()
        records = core.snapshot(mem, base)['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['slot'], 76)
        self.assertEqual(records[0]['handle'], 0x808004BA)
        self.assertEqual(core.weapon_level(records[0]['normalized_id']), (13000000, 1))

    def test_storage_is_refused(self):
        mem, base, inv, _ = fixture()
        mem.put(inv + 0x8C, b'\x01')
        with self.assertRaisesRegex(ValueError, 'storage'):
            core.snapshot(mem, base)

    def test_huge_geometry_is_refused(self):
        mem, base, inv, _ = fixture()
        mem.put(inv + 0x88, struct.pack('<I', 4096))
        with self.assertRaisesRegex(ValueError, 'bounds'):
            core.snapshot(mem, base)

    def test_failed_resolver_is_incomplete(self):
        mem, base, _, _ = fixture()
        with patch.object(core, 'verify_base', return_value=True), patch.object(core.resolver, 'resolve_weapon', side_effect=ValueError('stale handle')):
            result = core.capture(mem, base)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(result['weapons'][0]['error'], 'stale handle')

    def test_changed_slot_invalidates_capture(self):
        mem, base, _, slot = fixture()
        def resolve(*_):
            mem.put(slot + 4, struct.pack('<I', 13000200))
            return {'status': 'captured'}
        with patch.object(core, 'verify_base', return_value=True), patch.object(core.resolver, 'resolve_weapon', side_effect=resolve):
            result = core.capture(mem, base)
        self.assertEqual(result['status'], 'incomplete')
        self.assertIn('changed', result['error'])

    def test_wrong_image_never_walks_inventory(self):
        with patch.object(core, 'verify_base', return_value=False):
            result = core.capture(Memory(), 0)
        self.assertEqual(result['status'], 'incomplete')
        self.assertNotIn('inventory', result)

    def test_non_weapon_ids_not_classified_by_prefix(self):
        for row in (13000001, 0x400003E8, 0x00C65DA5):
            self.assertIsNone(core.weapon_level(row))

if __name__ == '__main__':
    unittest.main()
