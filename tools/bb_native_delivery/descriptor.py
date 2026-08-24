"""The 24-byte native ``ItemGrant`` source object.

Layout is ``validated`` (RESEARCH-BASELINE.md, 2026-08-19 live dump of the
decrypted inventory code): raw descriptor at ``+0x00``, an internal pointer at
``+0x08``, normalized ID at ``+0x10``. The harness stages 32 bytes because the
CE template also zeroes ``+0x04`` and ``+0x14``; only the three named fields
carry meaning.

``normalized = 0x40000000 + goods_id`` and ``raw = 0xB0000000 + goods_id`` hold
for the validated category-4 goods canaries (Pebble ``0x4CE``, Bullets ``0x384``,
Vials ``0x3E8``). They are ``inferred`` as a general formula and must not be
used to synthesise an equipment descriptor: the Torch and Rifle Spear negative
canaries produced invisible records from ItemLot-derived IDs.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

DESCRIPTOR_SIZE = 24
STAGED_SIZE = 32

GOODS_RAW_PREFIX = 0xB0000000
GOODS_NORMALIZED_PREFIX = 0x40000000

# Category 4 (goods) uses the in-frame stack source; category 0 (equipment)
# requires the persistent descriptor. Both are validated; nothing else is.
CATEGORY_GOODS = 4
CATEGORY_EQUIPMENT = 0


class DescriptorError(ValueError):
    """The descriptor is not one this project has validated."""


def goods_descriptor_ids(goods_id: int) -> tuple[int, int]:
    """(raw, normalized) for a category-4 goods id."""
    if not 0 <= goods_id <= 0x0FFF_FFFF:
        raise DescriptorError(f"goods id {goods_id:#x} is out of range")
    return GOODS_RAW_PREFIX | goods_id, GOODS_NORMALIZED_PREFIX | goods_id


def category_of(raw_id: int) -> int:
    """The high nibble the cave tests with ``and eax,F0000000``."""
    return (raw_id >> 28) & 0xF


def uses_persistent_source(raw_id: int) -> bool:
    """True when the cave takes the ``lea rsi,[bbAutoDescriptor]`` branch.

    The cave compares ``raw & 0xF0000000`` against ``0x80000000``; equipment
    descriptors (``0x806C5660`` Saw Spear) are the validated case.
    """
    return (raw_id & 0xF000_0000) == 0x8000_0000


@dataclass(frozen=True)
class ItemGrantDescriptor:
    raw_id: int
    normalized_id: int

    def __post_init__(self) -> None:
        for name, value in (("raw_id", self.raw_id), ("normalized_id", self.normalized_id)):
            if not 0 <= value <= 0xFFFF_FFFF:
                raise DescriptorError(f"{name} {value:#x} is not a u32")

    def encode(self) -> bytes:
        """The 32 bytes the harness stages into the descriptor cell."""
        buffer = bytearray(STAGED_SIZE)
        struct.pack_into("<I", buffer, 0x00, self.raw_id)
        struct.pack_into("<I", buffer, 0x04, 0)
        struct.pack_into("<Q", buffer, 0x08, 0)  # internal pointer, filled by the game
        struct.pack_into("<I", buffer, 0x10, self.normalized_id)
        struct.pack_into("<I", buffer, 0x14, 0)
        return bytes(buffer)

    @classmethod
    def decode(cls, data: bytes) -> "ItemGrantDescriptor":
        if len(data) < DESCRIPTOR_SIZE:
            raise DescriptorError(f"need {DESCRIPTOR_SIZE} bytes, got {len(data)}")
        raw, = struct.unpack_from("<I", data, 0x00)
        normalized, = struct.unpack_from("<I", data, 0x10)
        return cls(raw_id=raw, normalized_id=normalized)

    @classmethod
    def for_goods(cls, goods_id: int) -> "ItemGrantDescriptor":
        raw, normalized = goods_descriptor_ids(goods_id)
        return cls(raw_id=raw, normalized_id=normalized)
