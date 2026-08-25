"""A :class:`~.delivery.Runtime` backed by ReadProcessMemory/WriteProcessMemory.

DEVELOPER TOOL. Exercised against a live game on 2026-08-24 (shadPS4,
CUSA03173 01.09): the inventory walk found the absent-item and existing-stack
cases the owner checklist's items 6, 7 and 10 depend on. One build only.

The inventory geometry is transcribed from the CE harness's ``findItem``:
the cached inventory pointer leads to a split pair of fixed-stride record
arrays. ``validated`` as of 2026-08-24 -- this transcription drove live grants
through both the absent and the existing-stack paths.

Do not write into these pages from outside the guest. Issue #144: the inventory
page is protection-tracked by shadPS4, and an external ``WriteProcessMemory``
into it froze the guest twice, however correct the value was. Quantity changes
go through the cave's quantity-delta branch, on the game thread. Eboot-image
regions are unaffected -- the install's own writes remain safe.
"""

from __future__ import annotations

import time

from . import payload
from .delivery import EMPTY_SLOT, Runtime, SlotRecord, StackView
from .descriptor import ItemGrantDescriptor
from .process import AttachError, ProcessMemory

#: Offsets inside the cached inventory structure.
SPLIT_OFFSET = 0x24
LAST_OFFSET = 0x88
PRIMARY_ARRAY_OFFSET = 0x58
SECONDARY_ARRAY_OFFSET = 0x48
RECORD_STRIDE = 0x10
RECORD_ID_OFFSET = 0x04
RECORD_QUANTITY_OFFSET = 0x08
MAX_SLOTS = 4096

#: Issue #144: reads of the guest inventory geometry are intermittently
#: unavailable -- a pointer goes stale across a menu or level transition, and
#: under shadPS4 the page itself can refuse a read for a moment. A handful of
#: attempts, then a clean status; never an unbounded spin and never a traceback
#: out of the caller's poll loop.
READ_ATTEMPTS = 3
READ_RETRY_SECONDS = 0.05

#: The values the cave dispatches on. ``validated`` against the CE table's
#: ``bbAutoRequest`` comparisons, which the assembler reproduces byte for byte.
REQUEST_IDLE = 0
REQUEST_INSERT = 1
REQUEST_EXISTING = 2


def entry_address(inventory: int, slot: int, split: int, primary: int, secondary: int) -> int:
    """Which of the two banks holds ``slot``. Pure, so it is testable."""
    if slot < split:
        return primary + slot * RECORD_STRIDE
    return secondary + (slot - split) * RECORD_STRIDE


class GuestRuntime(Runtime):
    """The live runtime. It writes only inside the eboot image.

    Issue #144: every grant, including one into an existing stack, is handed to
    the cave and executed by the game's own thread. Nothing here reaches into a
    guest data page with WriteProcessMemory; :meth:`write_quantity` is retained
    for the retired path and for symmetry with the protocol, and the write guard
    in :mod:`.process` refuses it if anything ever calls it.
    """

    def __init__(self, memory: ProcessMemory, base: int) -> None:
        self.memory = memory
        self.base = base
        #: Set when a geometry read exhausted :data:`READ_ATTEMPTS`.
        self._read_failed = False
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

    def read_unavailable(self) -> bool:
        return self._read_failed

    def _bounded(self, operation, unavailable):
        """Run ``operation`` with a small bounded retry; never raise on a read.

        A failed ReadProcessMemory is a symptom, not a verdict: the cave
        re-caches the inventory pointer on every hook fire, so the honest
        response is to wait and look again, and to say so if it is still not
        there. Bounded, because a delivery that spins forever is a hang the
        player cannot tell apart from a freeze.
        """
        for attempt in range(READ_ATTEMPTS):
            try:
                value = operation()
            except AttachError:
                if attempt + 1 < READ_ATTEMPTS:
                    time.sleep(READ_RETRY_SECONDS)
                continue
            self._read_failed = False
            return value
        self._read_failed = True
        return unavailable

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
        return self._bounded(
            lambda: self.memory.read_u64(self.inventory_pointer) != 0, False
        )

    def find_stack(self, normalized_id: int) -> StackView | None:
        return self._bounded(lambda: self._find_stack(normalized_id), None)

    def _find_stack(self, normalized_id: int) -> StackView | None:
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
        return self._bounded(
            lambda: self._read_slot_record(slot), SlotRecord(None, None, None)
        )

    def _read_slot_record(self, slot: int) -> SlotRecord:
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
        """RETIRED (issue #144). Unreachable from the delivery state machine.

        Left in place to satisfy the :class:`~.delivery.Runtime` protocol. The
        address it takes is inside a guest inventory page, so the write guard in
        :mod:`.process` refuses it once a base has been armed -- deliberately: an
        external write there is what froze the emulator twice.
        """
        self.memory.write_u32(address, value)
        return self.memory.read_u32(address) == value

    def request_pending(self) -> bool:
        return self._bounded(lambda: self.memory.read_u32(self.request) != 0, False)

    def queue_native(
        self, descriptor: ItemGrantDescriptor, quantity: int, slot: int | None,
        quantity_address: int | None, manual_trigger: bool,
        existing_stack: bool = False,
    ) -> None:
        """Arm the cave. ``existing_stack`` selects its ``bbAutoExisting`` branch.

        The cave reads ``bbAutoRequest`` as the arm signal and dispatches on its
        value (``payload._program_consume``): 1 takes the ``ItemGrant`` insert
        path, 2 takes the quantity-delta path against ``bbAutoSlotIndex`` and
        ``bbAutoItemQuantityPointer``. Both run on the game thread, which is the
        whole point of issue #144.
        """
        self.memory.write(self.descriptor, descriptor.encode())
        self.memory.write_u32(self.slot_index, EMPTY_SLOT if slot is None else slot)
        self.memory.write_u64(self.item_quantity_pointer, quantity_address or 0)
        self.memory.write_u32(self.manual_trigger, 1 if manual_trigger else 0)
        self.memory.write_u32(self.quantity, quantity)
        self.memory.write_u32(self.result, EMPTY_SLOT)
        self.memory.write_u32(self.done, 0)
        # Last: the cave reads `request` as the arm signal, and its value picks
        # the branch. Written last so a crash mid-stage cannot arm a half-staged
        # request.
        self.memory.write_u32(self.request, REQUEST_EXISTING if existing_stack else REQUEST_INSERT)

    def native_done(self) -> bool:
        return self._bounded(lambda: self.memory.read_u32(self.done) == 1, False)

    def native_result(self) -> int:
        return self.memory.read_u32(self.result)

    def clear_request(self) -> None:
        self.memory.write_u32(self.request, 0)
