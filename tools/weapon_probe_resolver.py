"""Read-only resolver for Bloodborne equipment instance handles.

The traversal is the data-only branch of CUSA03173 01.09's descriptor
resolver at eboot RVA 0x1A89070.  It uses no remote calls or process writes.
"""

from __future__ import annotations

import hashlib
import struct


RESOLVER_RVA = 0x1A89070
RESOLVER_SIZE = 0x154
RESOLVER_SHA256 = "6277cd15112dde76f1bbc3e8d75b72a31ab45a61743abb179993fbd65c98aa33"
EQUIPMENT_REGISTRY_POINTER_RVA = 0x553E990
OBJECT_CAPTURE_SIZE = 0x100


class WeaponResolutionError(RuntimeError):
    """The handle cannot be resolved without guessing."""


def _u32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _u64(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def verify_base(memory, base: int) -> bool:
    """Verify the complete resolver body for the supported executable."""
    try:
        code = memory.read(base + RESOLVER_RVA, RESOLVER_SIZE)
    except Exception:
        return False
    return (
        len(code) == RESOLVER_SIZE
        and hashlib.sha256(code).hexdigest() == RESOLVER_SHA256
    )


def resolve_weapon(memory, base: int, handle: int, normalized: int) -> dict:
    """Resolve and capture one weapon object using external reads only.

    This reproduces the validated allocated-handle branch of the game's
    resolver.  The returned raw bytes are intentionally left uninterpreted
    except for the sole evidenced instance field, current durability at +0x18.
    """
    if not verify_base(memory, base):
        raise WeaponResolutionError("unsupported resolver bytes")
    if not 0 <= handle <= 0xFFFF_FFFF or not 0 <= normalized <= 0xFFFF_FFFF:
        raise WeaponResolutionError("handle and normalized id must be u32 values")

    compact = handle & 0x00FF_FFFF
    if compact == 0x00FF_FFFF or not (compact & 0x0080_0000):
        raise WeaponResolutionError(f"0x{handle:08X} is not an allocated instance handle")
    index = compact & 0xFFFF
    if index == 0xFFFF:
        raise WeaponResolutionError("allocated instance handle has the sentinel index")

    registry = _u64(memory.read(base + EQUIPMENT_REGISTRY_POINTER_RVA, 8))
    if registry == 0:
        raise WeaponResolutionError("equipment instance registry is unavailable")
    address = _u64(memory.read(registry + index * 8 + 8, 8))
    if address == 0:
        raise WeaponResolutionError(f"equipment instance slot {index} is empty")

    raw = memory.read(address, OBJECT_CAPTURE_SIZE)
    if len(raw) != OBJECT_CAPTURE_SIZE:
        raise WeaponResolutionError("short weapon object read")
    object_handle = _u32(raw, 0x08)
    object_normalized = _u32(raw, 0x0C)
    if object_handle != handle:
        raise WeaponResolutionError(
            f"instance slot identity mismatch: expected 0x{handle:08X}, "
            f"found 0x{object_handle:08X}"
        )
    if object_normalized != normalized:
        raise WeaponResolutionError(
            f"weapon row mismatch: expected 0x{normalized:08X}, "
            f"found 0x{object_normalized:08X}"
        )

    return {
        "status": "resolved",
        "handle": f"0x{handle:08X}",
        "normalized": f"0x{normalized:08X}",
        "registry": f"0x{registry:X}",
        "instance_index": index,
        "address": f"0x{address:X}",
        "durability": _u32(raw, 0x18),
        "raw_hex": raw.hex().upper(),
        "raw_size": len(raw),
        "raw_scope": "0x100-byte memory window from resolved object; object size unknown",
        "labelled_offsets": {"current_durability": "0x18"},
        "unresolved_fields": ["gem_slots", "attached_gems"],
    }
