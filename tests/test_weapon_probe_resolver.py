import hashlib
import struct
import unittest

from tools import weapon_probe_resolver as resolver


class Memory:
    def __init__(self):
        self.regions = {}

    def put(self, address, data):
        self.regions[address] = bytes(data)

    def read(self, address, size):
        for start, data in self.regions.items():
            offset = address - start
            if 0 <= offset and offset + size <= len(data):
                return data[offset:offset + size]
        raise OSError(f"unmapped read 0x{address:X}+0x{size:X}")


class ResolverTests(unittest.TestCase):
    BASE = 0x05720000
    HANDLE = 0x808004BA
    NORMALIZED = 0x00C65DA4
    REGISTRY = 0x208000000
    OBJECT = 0x224F8E5C0

    def fixture(self):
        memory = Memory()
        # Tests bind to the published hash while avoiding a copied executable
        # fixture: replace hashlib only around base verification below.
        memory.put(self.BASE + resolver.RESOLVER_RVA, b"R" * resolver.RESOLVER_SIZE)
        memory.put(
            self.BASE + resolver.EQUIPMENT_REGISTRY_POINTER_RVA,
            struct.pack("<Q", self.REGISTRY),
        )
        index = self.HANDLE & 0xFFFF
        memory.put(self.REGISTRY + index * 8 + 8, struct.pack("<Q", self.OBJECT))
        raw = bytearray(resolver.OBJECT_CAPTURE_SIZE)
        struct.pack_into("<I", raw, 0x08, self.HANDLE)
        struct.pack_into("<I", raw, 0x0C, self.NORMALIZED)
        struct.pack_into("<I", raw, 0x18, 100)
        memory.put(self.OBJECT, raw)
        return memory

    def resolve(self, memory):
        original = resolver.RESOLVER_SHA256
        try:
            resolver.RESOLVER_SHA256 = hashlib.sha256(
                b"R" * resolver.RESOLVER_SIZE
            ).hexdigest()
            return resolver.resolve_weapon(
                memory, self.BASE, self.HANDLE, self.NORMALIZED
            )
        finally:
            resolver.RESOLVER_SHA256 = original

    def test_exact_external_traversal_and_capture(self):
        result = self.resolve(self.fixture())
        self.assertEqual("0x224F8E5C0", result["address"])
        self.assertEqual(100, result["durability"])
        self.assertEqual(0x04BA, result["instance_index"])
        self.assertEqual(0x100, result["raw_size"])
        self.assertEqual(["gem_slots", "attached_gems"], result["unresolved_fields"])

    def test_identity_mismatch_fails_closed(self):
        memory = self.fixture()
        raw = bytearray(memory.regions[self.OBJECT])
        struct.pack_into("<I", raw, 0x08, self.HANDLE + 1)
        memory.put(self.OBJECT, raw)
        with self.assertRaisesRegex(resolver.WeaponResolutionError, "identity mismatch"):
            self.resolve(memory)

    def test_non_instance_descriptor_is_rejected(self):
        with self.assertRaisesRegex(resolver.WeaponResolutionError, "not an allocated"):
            original = resolver.RESOLVER_SHA256
            try:
                resolver.RESOLVER_SHA256 = hashlib.sha256(
                    b"R" * resolver.RESOLVER_SIZE
                ).hexdigest()
                resolver.resolve_weapon(
                    self.fixture(), self.BASE, 0x800004BA, self.NORMALIZED
                )
            finally:
                resolver.RESOLVER_SHA256 = original

    def test_wrong_resolver_bytes_fail_closed(self):
        memory = self.fixture()
        memory.put(self.BASE + resolver.RESOLVER_RVA, b"X" * resolver.RESOLVER_SIZE)
        self.assertFalse(resolver.verify_base(memory, self.BASE))


if __name__ == "__main__":
    unittest.main()
