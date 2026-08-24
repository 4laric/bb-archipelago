"""A :class:`~.delivery.Runtime` backed by ReadProcessMemory/WriteProcessMemory.

DEVELOPER TOOL, untested against a live game.

The inventory geometry is transcribed from the CE harness's ``findItem``:
the cached inventory pointer leads to a split pair of fixed-stride record
arrays. ``observed`` -- it was exercised live by the harness, but this
transcription of it has not been.
"""

from __future__ import annotations

from . import payload
from .delivery import EMPTY_SLOT, Runtime, SlotRecord, StackView
from .descriptor import ItemGrantDescriptor
from .process import ProcessMemory

#: Offsets inside the cached inventory structure.
SPLIT_OFFSET = 0x24
LAST_OFFSET = 0x88
PRIMARY_ARRAY_OFFSET = 0x58
SECONDARY_ARRAY_OFFSET = 0x48
RECORD_STRIDE = 0x10
RECORD_ID_OFFSET = 0x04
RECORD_QUANTITY_OFFSET = 0x08
MAX_SLOTS = 4096


def entry_address(inventory: int, slot: int, split: int, primary: int, secondary: int) -> int:
    """Which of the two banks holds ``slot``. Pure, so it is testable."""
    if slot < split:
        return primary + slot * RECORD_STRIDE
    return secondary + (slot - split) * RECORD_STRIDE


class GuestRuntime(Runtime):
    def __init__(self, memory: ProcessMemory, base: int) -> None:
        self.memory = memory
        self.base = base
        self.request = base + payload.REQUEST_RVA
        self.quantity = base + payload.QUANTITY_RVA
        self.result = base + payload.RESULT_RVA
        self.done = base + payload.DONE_RVA
        self.inventory_pointer = base + payload.INVENTORY_RVA
        self.slot_index = base + payload.SLOT_INDEX_RVA
        self.item_quantity_pointer = base + payload.ITEM_QUANTITY_POINTER_RVA
        self.manual_trigger = base + payload.MANUAL_TRIGGER_RVA
        self.descriptor = base + payload.DESCRIPTOR_RVA

    # -- geometry

    def _inventory(self) -> tuple[int, int, int, int, int] | None:
        inventory = self.memory.read_u64(self.inventory_pointer)
        if not inventory:
            return None
        split = self.memory.read_u32(inventory + SPLIT_OFFSET)
        last = self.memory.read_u32(inventory + LAST_OFFSET)
        primary = self.memory.read_u64(inventory + PRIMARY_ARRAY_OFFSET)
        secondary = self.memory.read_u64(inventory + SECONDARY_ARRAY_OFFSET)
        if last >= MAX_SLOTS or not primary or not secondary:
            return None
        return inventory, split, last, primary, secondary

    def inventory_ready(self) -> bool:
        return self.memory.read_u64(self.inventory_pointer) != 0

    def find_stack(self, normalized_id: int) -> StackView | None:
        geometry = self._inventory()
        if geometry is None:
            return None
        _inventory, split, last, primary, secondary = geometry
        for slot in range(last + 1):
            entry = entry_address(_inventory, slot, split, primary, secondary)
            if self.memory.read_u32(entry + RECORD_ID_OFFSET) == normalized_id:
                return StackView(
                    quantity=self.memory.read_u32(entry + RECORD_QUANTITY_OFFSET),
                    exists=True,
                    slot=slot,
                    quantity_address=entry + RECORD_QUANTITY_OFFSET,
                )
        return StackView(quantity=0, exists=False)

    def read_slot_record(self, slot: int) -> SlotRecord:
        geometry = self._inventory()
        if geometry is None or slot in (None, EMPTY_SLOT) or slot < 0:
            return SlotRecord(None, None, None)
        _inventory, split, last, primary, secondary = geometry
        if slot > last:
            return SlotRecord(None, None, None)
        entry = entry_address(_inventory, slot, split, primary, secondary)
        return SlotRecord(
            normalized_id=self.memory.read_u32(entry + RECORD_ID_OFFSET),
            quantity=self.memory.read_u32(entry + RECORD_QUANTITY_OFFSET),
            address=entry,
        )

    # -- the request cells

    def write_quantity(self, address: int, value: int) -> bool:
        self.memory.write_u32(address, value)
        return self.memory.read_u32(address) == value

    def request_pending(self) -> bool:
        return self.memory.read_u32(self.request) != 0

    def queue_native(
        self, descriptor: ItemGrantDescriptor, quantity: int, slot: int | None,
        quantity_address: int | None, manual_trigger: bool,
    ) -> None:
        self.memory.write(self.descriptor, descriptor.encode())
        self.memory.write_u32(self.slot_index, EMPTY_SLOT if slot is None else slot)
        self.memory.write_u64(self.item_quantity_pointer, quantity_address or 0)
        self.memory.write_u32(self.manual_trigger, 1 if manual_trigger else 0)
        self.memory.write_u32(self.quantity, quantity)
        self.memory.write_u32(self.result, EMPTY_SLOT)
        self.memory.write_u32(self.done, 0)
        # Last: the cave reads `request` as the arm signal.
        self.memory.write_u32(self.request, 1)

    def native_done(self) -> bool:
        return self.memory.read_u32(self.done) == 1

    def native_result(self) -> int:
        return self.memory.read_u32(self.result)

    def clear_request(self) -> None:
        self.memory.write_u32(self.request, 0)
