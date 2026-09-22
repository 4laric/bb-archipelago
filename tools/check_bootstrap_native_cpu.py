"""Validate the slot-free heartbeat against the owner's exact game executable.

No game bytes are bundled. Run with a locally supplied CUSA03173 01.09
eboot.bin and unicorn==2.1.4. The image hash must match the runtime contract.
The native quantity routine executes in an emulator, stopping at the existing
consume-return hook. Inventory writes and nested native calls are forbidden.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_MEM_WRITE, UC_MODE_64, Uc
from unicorn.x86_const import (
    UC_X86_REG_R13, UC_X86_REG_RDI, UC_X86_REG_RDX, UC_X86_REG_RSI,
    UC_X86_REG_RSP,
)

from tools.bb_native_delivery import payload


# Exact SELF layout of the contract's hash-gated executable, not a general
# SELF parser. Only the small routine under test is loaded into the emulator.
SELF_CODE_OFFSET = 0x28EB0
BASE, INVENTORY, STACK, COOKIE = 0x10000000, 0x30000000, 0x31000000, 0x32000000


def check(image: bytes, last: int) -> dict:
    start = payload.QUANTITY_DELTA_RVA
    stop = payload.CONSUME_HOOK_RVA
    original = image[SELF_CODE_OFFSET + start:SELF_CODE_OFFSET + stop + 7]
    if original[-7:] != payload.CONSUME_ORIGINAL:
        raise ValueError("quantity routine does not end at the expected consume hook")
    # mov r15,[rip+disp32] is the native stack-cookie pointer load.
    if original[0x19:0x1C] != bytes.fromhex("4c 8b 3d"):
        raise ValueError("unexpected stack-cookie load")
    cookie_slot = BASE + start + 0x20 + struct.unpack_from("<i", original, 0x1C)[0]
    cpu = Uc(UC_ARCH_X86, UC_MODE_64)
    for page in { (BASE + start) & ~0xFFF, cookie_slot & ~0xFFF,
                  INVENTORY, STACK, COOKIE }:
        cpu.mem_map(page, 0x1000)
    cpu.mem_write(BASE + start, original)
    cpu.mem_write(cookie_slot, struct.pack("<Q", COOKIE))
    cpu.mem_write(COOKIE, struct.pack("<Q", 0x123456789ABCDEF0))
    cpu.mem_write(INVENTORY + 0x88, struct.pack("<I", last))
    # Bank pointers are intentionally zero: the sentinel path must never
    # inspect a slot, even when the inventory is entirely empty.
    cpu.reg_write(UC_X86_REG_RDI, INVENTORY)
    cpu.reg_write(UC_X86_REG_RSI, 0xFFFFFFFF)
    cpu.reg_write(UC_X86_REG_RDX, 0)
    cpu.reg_write(UC_X86_REG_RSP, STACK + 0x808)
    instructions = []

    def observe_instruction(cpu, address, size, _context):
        if not BASE + start <= address < BASE + stop:
            raise AssertionError(f"unexpected native call/branch to {address:#x}")
        instructions.append(address - BASE)

    def observe_write(_cpu, _access, address, size, _value, _context):
        if not (STACK <= address and address + size <= STACK + 0x1000):
            raise AssertionError(f"non-stack write at {address:#x}")

    cpu.hook_add(UC_HOOK_CODE, observe_instruction)
    cpu.hook_add(UC_HOOK_MEM_WRITE, observe_write)
    cpu.emu_start(BASE + start, BASE + stop, count=100)
    if cpu.reg_read(UC_X86_REG_R13) != INVENTORY or instructions[-1] != stop - 2:
        raise AssertionError("did not reach the delivery hook with the held inventory")
    return {"last_slot": last, "instructions": len(instructions),
            "reached_consume_hook": True, "inventory_writes": 0, "nested_calls": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eboot", type=Path)
    args = parser.parse_args()
    image = args.eboot.read_bytes()
    contract_path = Path(__file__).resolve().parents[1] / "research/runtime/bb-native-grant-contract.v5.json"
    expected = json.loads(contract_path.read_text())["target"]["eboot_sha256"]
    actual = hashlib.sha256(image).hexdigest()
    if actual != expected:
        raise SystemExit(f"Refusing unsupported executable: SHA-256 {actual}")
    print(json.dumps({"sha256": actual, "checks": [check(image, last)
          for last in (0, 42, 4095, 0xFFFFFFFF)]}, indent=2))


if __name__ == "__main__":
    main()
