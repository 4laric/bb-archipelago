"""Assemble the Bloodborne native-grant cave payload from source.

Provenance: the assembly source below is transcribed instruction-for-instruction
from the ``autoAssemble`` template in
``tables/Bloodborne-native-item-grant-auto-v2.CT`` (harness ``bb-native-grant-v5``).
That template is ``validated`` in the sense of RESEARCH-BASELINE.md -- it has been
installed and exercised live on CUSA03173 01.09 under shadPS4 0.18. The *byte
encoding* produced here is ``validated`` too, as of 2026-08-24: the caves were
read back from a live armed process and matched these blobs (owner checklist
item 1), and on the same day an armed install of these bytes ran the guest
through native grants without Cheat Engine loaded at all (items 5 through 9).

Every operand in the template is a constant or a label, so the blob is static.
Assembling at ``base = 0`` makes it fully position-independent apart from three
``mov rax, imm64`` operands, because every other absolute in the template is
reached through a RIP-relative or REL32 form whose displacement is a difference
of two eboot RVAs. Those three quadwords are the entire relocation table.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field


# --- eboot-relative geometry (see research/runtime/bb-native-grant-contract.v5.json)

CONSUME_HOOK_RVA = 0x14D9575
CONSUME_RETURN_RVA = 0x14D957C
HEARTBEAT_HOOK_RVA = 0x1BFE882
HEARTBEAT_RETURN_RVA = 0x1BFE889

ITEM_GRANT_RVA = 0x14DA0A0
QUANTITY_DELTA_RVA = 0x14D94A0
FIND_SLOT_RVA = 0x14DA2C0

CONSUME_CAVE_RVA = 0x50DBA00
HEARTBEAT_CAVE_RVA = 0x50DBC00
STATE_RVA = 0x50DBE00

# Cells inside the state region, as eboot RVAs.
REQUEST_RVA = STATE_RVA + 0x00
QUANTITY_RVA = STATE_RVA + 0x04
RESULT_RVA = STATE_RVA + 0x08
DONE_RVA = STATE_RVA + 0x0C
INVENTORY_RVA = STATE_RVA + 0x10
OVERFLOW_RVA = STATE_RVA + 0x30
SLOT_INDEX_RVA = STATE_RVA + 0x34
ITEM_QUANTITY_POINTER_RVA = STATE_RVA + 0x38
HEARTBEAT_DESCRIPTOR_RVA = STATE_RVA + 0x40
HEARTBEAT_DELTA_ARG_RVA = STATE_RVA + 0x4C
MANUAL_TRIGGER_RVA = STATE_RVA + 0x50
DESCRIPTOR_RVA = STATE_RVA + 0x60

CONSUME_ORIGINAL = bytes((0x44, 0x89, 0xE0, 0x48, 0x83, 0xC4, 0x28))
HEARTBEAT_ORIGINAL = bytes((0x48, 0x81, 0xC4, 0xE8, 0x07, 0x00, 0x00))


class AssemblyError(Exception):
    """The template could not be encoded."""


@dataclass
class _Insn:
    size: int
    encode: object  # (here_rva: int, labels: dict[str, int]) -> bytes
    relocation_offset: int | None = None
    relocation_target_rva: int | None = None


@dataclass
class Relocation:
    """One absolute quadword inside the blob that install time must fix up."""

    offset: int
    width: int
    target_rva: int

    def as_dict(self) -> dict:
        return {"offset": self.offset, "width": self.width, "target_rva": self.target_rva}


@dataclass
class AssembledBlob:
    """A contiguous run of bytes destined for one eboot RVA."""

    name: str
    rva: int
    data: bytes
    relocations: list[Relocation] = field(default_factory=list)

    def relocated(self, eboot_base: int) -> bytes:
        out = bytearray(self.data)
        for reloc in self.relocations:
            if reloc.width != 8:
                raise AssemblyError(f"unsupported relocation width {reloc.width}")
            value = eboot_base + reloc.target_rva
            out[reloc.offset : reloc.offset + 8] = struct.pack("<Q", value)
        return bytes(out)


# --- encoders ------------------------------------------------------------
# Only the forms the template actually uses. Anything else raises rather than
# guessing: a wrong encoding here becomes a wrong detour on a player's machine.


def _rip32(target_rva: int, here_rva: int, size: int) -> bytes:
    disp = target_rva - (here_rva + size)
    if not -0x8000_0000 <= disp <= 0x7FFF_FFFF:
        raise AssemblyError("RIP-relative displacement out of range")
    return struct.pack("<i", disp)


def _imm32(value: int) -> bytes:
    if -0x8000_0000 <= value <= 0x7FFF_FFFF:
        return struct.pack("<i", value)
    if 0 <= value <= 0xFFFF_FFFF:
        return struct.pack("<I", value)
    raise AssemblyError(f"immediate {value:#x} does not fit in 32 bits")


def _fixed(prefix: bytes) -> _Insn:
    return _Insn(len(prefix), lambda here, labels, b=prefix: b)


def _rip_form(prefix: bytes, label: str, trailer: bytes = b"") -> _Insn:
    size = len(prefix) + 4 + len(trailer)

    def encode(here: int, labels: dict[str, int]) -> bytes:
        return prefix + _rip32(labels[label], here, size) + trailer

    return _Insn(size, encode)


def _rel32_jump(opcode: bytes, label: str) -> _Insn:
    size = len(opcode) + 4

    def encode(here: int, labels: dict[str, int]) -> bytes:
        return opcode + _rip32(labels[label], here, size)

    return _Insn(size, encode)


def _mov_rax_imm64(target_rva: int) -> _Insn:
    def encode(here: int, labels: dict[str, int]) -> bytes:
        # Assembled at base 0; install relocates the quadword.
        return b"\x48\xb8" + struct.pack("<Q", target_rva)

    return _Insn(10, encode, relocation_offset=2, relocation_target_rva=target_rva)


CALL_RAX = b"\xff\xd0"


def _program_consume() -> list[tuple[str | None, _Insn | None]]:
    """The consume-return detour cave (CE label block ``8050DBA00``)."""
    return [
        # mov [bbAutoInventory],r13
        (None, _rip_form(b"\x4c\x89\x2d", "inventory")),
        # cmp dword ptr [bbAutoRequest],0
        (None, _rip_form(b"\x83\x3d", "request", b"\x00")),
        # je bbAutoConsumeOriginal
        (None, _rel32_jump(b"\x0f\x84", "consume_original")),
        # cmp dword ptr [bbAutoRequest],2
        (None, _rip_form(b"\x83\x3d", "request", b"\x02")),
        # je bbAutoExisting
        (None, _rel32_jump(b"\x0f\x84", "existing")),
        # mov dword ptr [bbAutoRequest],0
        (None, _rip_form(b"\xc7\x05", "request", _imm32(0))),
        # mov eax,[bbAutoDescriptor]
        (None, _rip_form(b"\x8b\x05", "descriptor")),
        # mov [rsp],eax
        (None, _fixed(b"\x89\x04\x24")),
        # mov qword ptr [rsp+8],0
        (None, _fixed(b"\x48\xc7\x44\x24\x08" + _imm32(0))),
        # mov eax,[bbAutoDescriptor+10]
        (None, _rip_form(b"\x8b\x05", "descriptor_normalized")),
        # mov [rsp+10],eax
        (None, _fixed(b"\x89\x44\x24\x10")),
        # mov dword ptr [rsp+14],0
        (None, _fixed(b"\xc7\x44\x24\x14" + _imm32(0))),
        # mov rdi,r13  (CE assembles the RM form: 49 8B FD)
        (None, _fixed(b"\x49\x8b\xfd")),
        # mov rsi,rsp  (CE assembles the RM form: 48 8B F4)
        (None, _fixed(b"\x48\x8b\xf4")),
        # mov eax,[bbAutoDescriptor]
        (None, _rip_form(b"\x8b\x05", "descriptor")),
        # and eax,F0000000
        (None, _fixed(b"\x25" + struct.pack("<I", 0xF0000000))),
        # cmp eax,80000000
        (None, _fixed(b"\x3d" + struct.pack("<I", 0x80000000))),
        # jne bbAutoDescriptorReady
        (None, _rel32_jump(b"\x0f\x85", "descriptor_ready")),
        # lea rsi,[bbAutoDescriptor]
        (None, _rip_form(b"\x48\x8d\x35", "descriptor")),
        ("descriptor_ready", None),
        # mov edx,[bbAutoQuantity]
        (None, _rip_form(b"\x8b\x15", "quantity")),
        # mov rax,ItemGrant / call rax
        (None, _mov_rax_imm64(ITEM_GRANT_RVA)),
        (None, _fixed(CALL_RAX)),
        # jmp bbAutoFinish
        (None, _rel32_jump(b"\xe9", "finish")),
        ("existing", None),
        # mov dword ptr [bbAutoRequest],0
        (None, _rip_form(b"\xc7\x05", "request", _imm32(0))),
        # mov rdi,r13  (CE assembles the RM form: 49 8B FD)
        (None, _fixed(b"\x49\x8b\xfd")),
        # mov esi,[bbAutoSlotIndex]
        (None, _rip_form(b"\x8b\x35", "slot_index")),
        # mov edx,[bbAutoQuantity]
        (None, _rip_form(b"\x8b\x15", "quantity")),
        # lea rcx,[bbAutoOverflow]
        (None, _rip_form(b"\x48\x8d\x0d", "overflow")),
        # mov r8,[bbAutoItemQuantityPointer]
        (None, _rip_form(b"\x4c\x8b\x05", "item_quantity_pointer")),
        # xor r9d,r9d
        (None, _fixed(b"\x45\x31\xc9")),
        # mov rax,quantity-delta / call rax
        (None, _mov_rax_imm64(QUANTITY_DELTA_RVA)),
        (None, _fixed(CALL_RAX)),
        ("finish", None),
        # mov [bbAutoResult],eax
        (None, _rip_form(b"\x89\x05", "result")),
        # mov dword ptr [bbAutoDone],1
        (None, _rip_form(b"\xc7\x05", "done", _imm32(1))),
        ("consume_original", None),
        # mov eax,r12d ; add rsp,28  -- the displaced original
        (None, _fixed(b"\x44\x89\xe0")),
        (None, _fixed(b"\x48\x83\xc4\x28")),
        # jmp <consume return>
        (None, _rel32_jump(b"\xe9", "consume_return")),
    ]


def _program_heartbeat() -> list[tuple[str | None, _Insn | None]]:
    """The idle-heartbeat detour cave (CE label block ``8050DBC00``)."""
    return [
        # cmp dword ptr [bbAutoManualTrigger],0 / jne original
        (None, _rip_form(b"\x83\x3d", "manual_trigger", b"\x00")),
        (None, _rel32_jump(b"\x0f\x85", "heartbeat_original")),
        # cmp dword ptr [bbAutoRequest],0 / je original
        (None, _rip_form(b"\x83\x3d", "request", b"\x00")),
        (None, _rel32_jump(b"\x0f\x84", "heartbeat_original")),
        # cmp qword ptr [bbAutoInventory],0 / je original
        (None, _rip_form(b"\x48\x83\x3d", "inventory", b"\x00")),
        (None, _rel32_jump(b"\x0f\x84", "heartbeat_original")),
        # mov rdi,[bbAutoInventory]
        (None, _rip_form(b"\x48\x8b\x3d", "inventory")),
        # lea rsi,[heartbeat descriptor]
        (None, _rip_form(b"\x48\x8d\x35", "heartbeat_descriptor")),
        # mov rax,find-slot / call rax
        (None, _mov_rax_imm64(FIND_SLOT_RVA)),
        (None, _fixed(CALL_RAX)),
        # cmp eax,-1 / je original
        (None, _fixed(b"\x83\xf8\xff")),
        (None, _rel32_jump(b"\x0f\x84", "heartbeat_original")),
        # mov rdi,[bbAutoInventory]
        (None, _rip_form(b"\x48\x8b\x3d", "inventory")),
        # mov esi,eax ; xor edx,edx
        (None, _fixed(b"\x8b\xf0")),  # mov esi,eax (CE RM form)
        (None, _fixed(b"\x31\xd2")),
        # lea rcx,[heartbeat delta arg]
        (None, _rip_form(b"\x48\x8d\x0d", "heartbeat_delta_arg")),
        # mov rax,quantity-delta / call rax
        (None, _mov_rax_imm64(QUANTITY_DELTA_RVA)),
        (None, _fixed(CALL_RAX)),
        ("heartbeat_original", None),
        # add rsp,7E8 -- the displaced original
        (None, _fixed(b"\x48\x81\xc4" + struct.pack("<I", 0x7E8))),
        (None, _rel32_jump(b"\xe9", "heartbeat_return")),
    ]


_EXTERNAL_LABELS = {
    "request": REQUEST_RVA,
    "quantity": QUANTITY_RVA,
    "result": RESULT_RVA,
    "done": DONE_RVA,
    "inventory": INVENTORY_RVA,
    "overflow": OVERFLOW_RVA,
    "slot_index": SLOT_INDEX_RVA,
    "item_quantity_pointer": ITEM_QUANTITY_POINTER_RVA,
    "heartbeat_descriptor": HEARTBEAT_DESCRIPTOR_RVA,
    "heartbeat_delta_arg": HEARTBEAT_DELTA_ARG_RVA,
    "manual_trigger": MANUAL_TRIGGER_RVA,
    "descriptor": DESCRIPTOR_RVA,
    "descriptor_normalized": DESCRIPTOR_RVA + 0x10,
    "consume_return": CONSUME_RETURN_RVA,
    "heartbeat_return": HEARTBEAT_RETURN_RVA,
}


def _assemble(name: str, rva: int, program) -> AssembledBlob:
    labels = dict(_EXTERNAL_LABELS)
    cursor = rva
    for label, insn in program:
        if label is not None:
            labels[label] = cursor
        if insn is not None:
            cursor += insn.size

    out = bytearray()
    relocations: list[Relocation] = []
    cursor = rva
    for _label, insn in program:
        if insn is None:
            continue
        encoded = insn.encode(cursor, labels)
        if len(encoded) != insn.size:
            raise AssemblyError(f"{name}: encoder emitted {len(encoded)} bytes, declared {insn.size}")
        if insn.relocation_offset is not None:
            relocations.append(
                Relocation(
                    offset=len(out) + insn.relocation_offset,
                    width=8,
                    target_rva=insn.relocation_target_rva,
                )
            )
        out += encoded
        cursor += insn.size
    return AssembledBlob(name=name, rva=rva, data=bytes(out), relocations=relocations)


def consume_cave() -> AssembledBlob:
    return _assemble("consume_cave", CONSUME_CAVE_RVA, _program_consume())


def heartbeat_cave() -> AssembledBlob:
    return _assemble("heartbeat_cave", HEARTBEAT_CAVE_RVA, _program_heartbeat())


def _detour(name: str, hook_rva: int, cave_rva: int, original: bytes) -> AssembledBlob:
    # E9 rel32 + 0x90 padding to exactly cover the displaced original bytes,
    # matching the table's `jmp <cave>` / `nop 2`.
    disp = cave_rva - (hook_rva + 5)
    data = b"\xe9" + struct.pack("<i", disp) + b"\x90" * (len(original) - 5)
    return AssembledBlob(name=name, rva=hook_rva, data=data)


def consume_detour() -> AssembledBlob:
    return _detour("consume_detour", CONSUME_HOOK_RVA, CONSUME_CAVE_RVA, CONSUME_ORIGINAL)


def heartbeat_detour() -> AssembledBlob:
    return _detour("heartbeat_detour", HEARTBEAT_HOOK_RVA, HEARTBEAT_CAVE_RVA, HEARTBEAT_ORIGINAL)


def state_region() -> AssembledBlob:
    """The 0x70-byte request/state block, including the heartbeat descriptor.

    Mirrors the CE data blocks at 8050DBE00 / DBE30 / DBE40 / DBE50 / DBE60.
    """
    data = bytearray(0x70)
    struct.pack_into("<i", data, 0x34, -1)  # bbAutoSlotIndex = FFFFFFFF
    struct.pack_into("<I", data, 0x40, 0xB0000384)  # heartbeat raw descriptor (Bullets)
    struct.pack_into("<I", data, 0x44, 0x40000384)  # heartbeat normalized id
    return AssembledBlob(name="state_region", rva=STATE_RVA, data=bytes(data))


def blobs() -> list[AssembledBlob]:
    """Everything the installer writes, in install order.

    Data and caves first; the two detours last, because a detour that lands
    before its cave points a live guest thread at zeroed memory.
    """
    return [state_region(), consume_cave(), heartbeat_cave(), consume_detour(), heartbeat_detour()]
