"""Bounded external reads for the weapon probe. No writes or guest calls."""
import struct
from datetime import datetime, timezone

import weapon_probe_resolver as resolver

INVENTORY_CELL = 0x50DBE10
BASES = (2000000,4000000,5000000,5100000,6000000,6100000,7000000,
         7100000,8000000,8100000,9000000,10000000,10100000,11000000,
         12000000,13000000,14000000,14200000,15000000,19100000,22000000,
         23000000,24000000,25000000,28000000,31000000,34000000,35000000)
UNCANNY = (2000000,4000000,5000000,5100000,7000000,7100000,8000000,
           8100000,9000000,10000000,10100000,11000000,12000000,13000000,22000000)

def u32(memory, address):
    return struct.unpack('<I', memory.read(address, 4))[0]

def u64(memory, address):
    return struct.unpack('<Q', memory.read(address, 8))[0]

def verify_base(memory, base):
    try:
        return resolver.verify_base(memory, base)
    except (OSError, ValueError, RuntimeError):
        return False

def weapon_level(row):
    for family in (*BASES, *(x + 10000 for x in UNCANNY)):
        delta = row - family
        if 0 <= delta <= 1000 and delta % 100 == 0:
            return family, delta // 100
    return None

def snapshot(memory, base):
    inventory = u64(memory, base + INVENTORY_CELL)
    if not inventory:
        raise ValueError('No held inventory cached by AP client. Send the incomplete bundle for review; do not attack to trigger capture.')
    header = memory.read(inventory, 0x90)
    if header[0x8C] != 0:
        raise ValueError('Cached inventory is storage, not held inventory. Capture refused.')
    split = struct.unpack_from('<I', header, 0x24)[0]
    last = struct.unpack_from('<I', header, 0x88)[0]
    primary = struct.unpack_from('<Q', header, 0x58)[0]
    secondary = struct.unpack_from('<Q', header, 0x48)[0]
    if last >= 4096 or split > 4096 or not primary or not secondary:
        raise ValueError('Inventory geometry is unavailable or outside the capture bounds.')
    records = []
    for slot in range(last + 1):
        address = primary + slot * 16 if slot < split else secondary + (slot-split)*16
        data = memory.read(address, 16)
        handle, row, quantity, flags = struct.unpack('<4I', data)
        if handle == 0xFFFFFFFF or quantity == 0:
            continue
        records.append(dict(slot=slot, address=hex(address), handle=handle, normalized_id=row,
                            quantity=quantity, flags=flags, raw_hex=data.hex()))
    # Structural changes invalidate this read; gameplay is never paused by this tool.
    if u64(memory, base + INVENTORY_CELL) != inventory or memory.read(inventory, 0x90) != header:
        raise ValueError('Inventory changed during capture. Stand still and retry.')
    return dict(address=hex(inventory), split=split, last=last, records=records)

def capture(memory, base):
    result = dict(format='bb-weapon-readonly-v1', status='incomplete',
                  captured_utc=datetime.now(timezone.utc).isoformat(), eboot_base=hex(base),
                  access='external_read_only', guest_calls=0, writes=0, hooks_installed=0,
                  resolver_sha256=resolver.RESOLVER_SHA256,
                  control_status='operator_confirmation_required', weapons=[], limitations=[
                      'A capture is not a corruption diagnosis. Compare against a known working weapon.',
                      'Gem/socket fields remain undecoded; raw bytes are preserved.',
                      'No attacks, buff use, item delivery, or save operations are performed.'])
    try:
        if not verify_base(memory, base):
            raise ValueError('Loaded resolver code does not match the supported image. Capture refused.')
        result['image_validation'] = 'resolver_code_guards_passed'
        before = snapshot(memory, base)
        result['inventory'] = before
        for record in before['records']:
            level = weapon_level(record['normalized_id'])
            if level is None:
                continue
            weapon = dict(record, family=level[0], reinforcement_level=level[1],
                          is_tonitrus=level[0] in (13000000,13010000))
            try:
                weapon['backing'] = resolver.resolve_weapon(memory, base, record['handle'], record['normalized_id'])
            except (OSError, ValueError, RuntimeError) as exc:
                weapon['error'] = str(exc)
            result['weapons'].append(weapon)
        if snapshot(memory, base) != before:
            raise ValueError('Inventory changed during weapon reads. Stand still and retry.')
        result['inventory_stable'] = True
        result['tonitrus_captured'] = any(w['is_tonitrus'] for w in result['weapons'])
        result['comparison_weapon_captured'] = any(not w['is_tonitrus'] for w in result['weapons'])
        if not result['weapons']:
            raise ValueError('No catalogued weapons captured; this is a diagnostic miss, not evidence of absence.')
        if any('error' in weapon for weapon in result['weapons']):
            raise ValueError('Some backing objects could not be resolved. Treat this as an incomplete capture.')
        result['status'] = 'captured'
    except (OSError, ValueError, RuntimeError) as exc:
        result['error'] = str(exc)
    return result
