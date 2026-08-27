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

# Category 4 goods use the in-frame source. Weapons and armor use a persistent
# descriptor after native allocation. All other categories remain refused.
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

    The cave dispatches the 0x8 weapon and 0x9 armor prefixes to separate native
    allocators. Every other prefix remains on the in-frame path and is rejected
    by the descriptor allowlist before it can reach the cave.
    """
    return (raw_id & 0xF000_0000) in {0x8000_0000, 0x9000_0000}


# -- the descriptor allowlist (issue #146)
#
# The CLI used to arm any hand-typed (raw, normalized) pair: ItemGrantDescriptor
# checks u32 range and nothing else. On 2026-08-24 that let the Torch negative
# canary execute against a live save -- the cave returned slot 79 and reproduced
# the invisible-record hazard RESEARCH-BASELINE.md had already recorded. So the
# pair now has to be derivable from a formula this project validated live.

#: raw -> (normalized, item name). Equipment is allowlisted by exact pair, never
#: by formula: RESEARCH-BASELINE.md says an ItemLot weapon id is not a runtime
#: descriptor, and the current evidence validates Saw Spear only. Its normalized
#: id is the live-verified 7100000 (= 0x006C5660). Provenance: ``observed``.
VALIDATED_EQUIPMENT_ROWS: dict[int, tuple[int, str]] = {
    0x806C_5660: (0x006C_5660, "Saw Spear"),
}

# Category-1 armor uses its own native allocator. Charred Hunter Garb was
# inserted, rendered, and equipped successfully on the throwaway live save.
VALIDATED_ARMOR_ROWS: dict[int, tuple[int, str]] = {
    0x9000_2AF8: (0x1000_2AF8, "Charred Hunter Garb"),
}

#: raw -> (normalized, why it is refused); a ``None`` normalized refuses the raw
#: id whatever it is paired with. Named so a refusal can cite the reproduction
#: rather than only the missing derivation. Provenance: ``observed``.
EXCLUDED_DESCRIPTORS: dict[int, tuple[int | None, str]] = {
    0x8132_B3A0: (
        None,
        "Torch (ItemLot 20100000): raw 0x8132B3A0 / normalized 0x0032B3A0 returned a "
        "native slot but produced an invisible record; RESEARCH-BASELINE.md records it "
        "as an executable exclusion that cannot be regenerated from its ItemLot weapon id",
    ),
    0x8098_9680: (
        None,
        "Rifle Spear (ItemLot 10000000): raw 0x80989680 arrived with normalized "
        "0xFFFFFFFF and produced an invisible record (RESEARCH-BASELINE.md)",
    ),
}

_CITATION = (
    "See issue #146 and docs/RESEARCH-BASELINE.md. Override with "
    "--unvalidated-descriptor only for research, on a throwaway save."
)


def describe_validated_descriptor(raw_id: int, normalized_id: int) -> str:
    """The derivation that validates this pair, or raise :class:`DescriptorError`.

    Fail closed: a pair is armed only when it is a category-4 goods pair built by
    :func:`goods_descriptor_ids` (both prefixes present, goods ids equal) or an
    exact row in :data:`VALIDATED_EQUIPMENT_ROWS`. Nothing else is derivable from
    anything this project has checked against a live guest.
    """
    for name, value in (("raw_id", raw_id), ("normalized_id", normalized_id)):
        if not 0 <= value <= 0xFFFF_FFFF:
            raise DescriptorError(f"{name} {value:#x} is not a u32")

    excluded = EXCLUDED_DESCRIPTORS.get(raw_id)
    if excluded is not None and excluded[0] in (None, normalized_id):
        raise DescriptorError(
            f"raw {raw_id:#010x} / normalized {normalized_id:#010x} is a NAMED NEGATIVE "
            f"CANARY, refused by exact value: {excluded[1]}. {_CITATION}"
        )

    goods_id = raw_id & 0x0FFF_FFFF
    if category_of(raw_id) == category_of(GOODS_RAW_PREFIX):
        if category_of(normalized_id) == category_of(GOODS_NORMALIZED_PREFIX) and (
            normalized_id & 0x0FFF_FFFF
        ) == goods_id:
            return f"category-4 goods formula, goods id {goods_id:#x} (inferred)"
        raise DescriptorError(
            f"raw {raw_id:#010x} carries the category-4 goods prefix but normalized "
            f"{normalized_id:#010x} is not {GOODS_NORMALIZED_PREFIX | goods_id:#010x}. "
            "Missing evidence: a goods pair is validated only when both prefixes are "
            f"present and the low 28 bits agree. {_CITATION}"
        )

    row = VALIDATED_EQUIPMENT_ROWS.get(raw_id)
    if row is not None:
        if normalized_id == row[0]:
            return f"validated equipment row: {row[1]} (observed)"
        raise DescriptorError(
            f"raw {raw_id:#010x} is the validated {row[1]} row, but its live-verified "
            f"normalized id is {row[0]:#010x}, not {normalized_id:#010x}. {_CITATION}"
        )

    row = VALIDATED_ARMOR_ROWS.get(raw_id)
    if row is not None:
        if normalized_id == row[0]:
            return f"validated armor row: {row[1]} (observed insert and equip)"
        raise DescriptorError(
            f"raw {raw_id:#010x} is the validated {row[1]} armor row, but its "
            f"live-verified normalized id is {row[0]:#010x}, not "
            f"{normalized_id:#010x}. {_CITATION}"
        )

    known = ", ".join(
        f"{value:#010x} ({name})"
        for value, (_normalized, name) in sorted(VALIDATED_EQUIPMENT_ROWS.items())
    )
    known_armor = ", ".join(
        f"{value:#010x} ({name})"
        for value, (_normalized, name) in sorted(VALIDATED_ARMOR_ROWS.items())
    )
    raise DescriptorError(
        f"raw {raw_id:#010x} / normalized {normalized_id:#010x} is not a validated "
        "descriptor. Missing evidence: it is neither a category-4 goods pair "
        "(raw 0xB0000000|id with normalized 0x40000000|id) nor an allowlisted "
        f"equipment row [{known}] nor an allowlisted armor row [{known_armor}]. "
        "RESEARCH-BASELINE.md validates instance-backed "
        "descriptors one at a time, from a live dump; this pair has no such dump. "
        f"{_CITATION}"
    )


def is_validated_descriptor(raw_id: int, normalized_id: int) -> bool:
    """True when :func:`describe_validated_descriptor` accepts the pair."""
    try:
        describe_validated_descriptor(raw_id, normalized_id)
    except DescriptorError:
        return False
    return True


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
