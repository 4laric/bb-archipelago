"""Execute assembled x86-64 inventory guards in Unicorn, never a live process.

Native callees are observation/stop boundaries, not implementations of the game.
Requires unicorn==2.1.4; CI installs it explicitly and cannot skip this check.
"""
import struct
import unittest
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_R13, UC_X86_REG_R12, UC_X86_REG_RSP, UC_X86_REG_RDI
from tools.bb_native_delivery import payload as p


BASE, HELD, STORAGE, STACK = 0x10000000, 0x30000000, 0x30001000, 0x31000000


def run_hook(*, heartbeat=False, storage_call=False, cached_storage=False, pending=1, data=None):
    cpu = Uc(UC_ARCH_X86, UC_MODE_64)
    cpu.mem_map(BASE + 0x50DB000, 0x2000)
    cpu.mem_map(HELD, 0x2000)
    cpu.mem_map(STACK, 0x2000)
    blob = p.heartbeat_cave() if heartbeat else p.consume_cave()
    cpu.mem_write(BASE + blob.rva, data if data is not None else blob.relocated(BASE))
    cpu.mem_write(STORAGE + p.INVENTORY_STORAGE_MODE_OFFSET, b'\1')
    cpu.mem_write(BASE + p.INVENTORY_RVA, struct.pack('<Q', STORAGE if cached_storage else HELD))
    cpu.mem_write(BASE + p.REQUEST_RVA, struct.pack('<I', pending))
    cpu.mem_write(BASE + p.QUANTITY_RVA, struct.pack('<I', 1))
    cpu.mem_write(BASE + p.DESCRIPTOR_RVA, struct.pack('<IIQIIII', 0xB00004CE, 0, 0, 0x400004CE, 0, 0, 0))
    cpu.reg_write(UC_X86_REG_R13, STORAGE if storage_call else HELD)
    cpu.reg_write(UC_X86_REG_R12, 17)
    cpu.reg_write(UC_X86_REG_RSP, STACK + 0x800)
    calls = []
    targets = [BASE + r for r in (p.ITEM_GRANT_RVA, p.FIND_SLOT_RVA, p.QUANTITY_DELTA_RVA)]
    for page in {a & ~0xfff for a in targets}:
        cpu.mem_map(page, 0x1000)
    def observe(cpu, address, _size, _context):
        if address in targets:
            calls.append((address - BASE, cpu.reg_read(UC_X86_REG_RDI)))
            cpu.emu_stop()
    cpu.hook_add(UC_HOOK_CODE, observe)
    end = BASE + (p.HEARTBEAT_RETURN_RVA if heartbeat else p.CONSUME_RETURN_RVA)
    if (end & ~0xfff) not in {a & ~0xfff for a in targets}:
        cpu.mem_map(end & ~0xfff, 0x1000)
    cpu.emu_start(BASE + blob.rva, end, count=300)
    return {
        'cache': struct.unpack('<Q', cpu.mem_read(BASE + p.INVENTORY_RVA, 8))[0],
        'request': struct.unpack('<I', cpu.mem_read(BASE + p.REQUEST_RVA, 4))[0],
        'calls': calls,
    }


class InventoryHookCpuTests(unittest.TestCase):
    def test_held_call_captures_and_dispatches(self):
        result = run_hook(cached_storage=True)
        self.assertEqual(result['cache'], HELD)
        self.assertEqual(result['calls'], [(p.ITEM_GRANT_RVA, HELD)])
        self.assertEqual(result['request'], 0)

    def test_storage_call_cannot_poison_cache_or_dispatch(self):
        for pending in (0, 1, 2):
            with self.subTest(pending=pending):
                result = run_hook(storage_call=True, pending=pending)
                self.assertEqual(result, {'cache': HELD, 'request': pending, 'calls': []})

    def test_heartbeat_refuses_retained_storage_cache(self):
        result = run_hook(heartbeat=True, cached_storage=True)
        self.assertEqual(result, {'cache': STORAGE, 'request': 1, 'calls': []})

    def test_heartbeat_held_positive_control(self):
        self.assertEqual(run_hook(heartbeat=True)['calls'], [(p.FIND_SLOT_RVA, HELD)])

    def test_disabling_guard_reproduces_wrong_inventory_dispatch(self):
        data = bytearray(p.consume_cave().relocated(BASE))
        # Replace only the initial cmp/jne with NOPs; retain all relocated code.
        self.assertEqual(data[:3], b'\x41\x80\xbd')
        data[:14] = b'\x90' * 14
        result = run_hook(storage_call=True, data=bytes(data))
        self.assertEqual(result['cache'], STORAGE)
        self.assertEqual(result['calls'], [(p.ITEM_GRANT_RVA, STORAGE)])


if __name__ == '__main__':
    unittest.main()
