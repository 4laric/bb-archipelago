"""Bounded contract model for BBEventWriter dump output; NOT a Bloodborne emulator.

Execute emitted instructions after applying emitted parameter substitutions.
Inventory predicate/removal and scheduling are explicit assumptions. A pass
proves the modeled protocol only, never live event scheduling or item recognition.
No game bytes or instruction-definition database are distributed here.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import struct


@dataclass
class Event:
    instructions: list = field(default_factory=list)
    parameters: list = field(default_factory=list)
    counts: tuple[int, int] = (0, 0)


def parse_dump(text: str) -> dict[int, Event]:
    events = {}
    current = None
    for line in text.splitlines():
        if match := re.fullmatch(r"event (\d+) rest=\w+ instructions=(\d+) parameters=(\d+)", line):
            event_id = int(match[1])
            if event_id in events:
                raise ValueError("duplicate event")
            current = events[event_id] = Event()
            current.counts = (int(match[2]), int(match[3]))
        elif match := re.fullmatch(r"  \[(\d+)\] (\d+)\[(\d+)\] ([0-9a-f]*)", line):
            if current is None or int(match[1]) != len(current.instructions):
                raise ValueError("noncontiguous instructions")
            current.instructions.append((int(match[2]), int(match[3]), bytes.fromhex(match[4])))
        elif match := re.fullmatch(r"  param instr=(\d+) target=(\d+) source=(\d+) bytes=(\d+) unk=0", line):
            if current is None:
                raise ValueError("parameter before event")
            current.parameters.append(tuple(map(int, match.groups())))
        elif line.startswith("  "):
            raise ValueError(f"unsupported dump record: {line}")
    if not events:
        raise ValueError("empty event population")
    for event in events.values():
        if event.counts != (len(event.instructions), len(event.parameters)):
            raise ValueError("truncated dump")
    return events


def instantiate(event: Event, arguments: bytes):
    instructions = [(bank, op, bytearray(data)) for bank, op, data in event.instructions]
    for index, target, source, size in event.parameters:
        if index >= len(instructions) or source + size > len(arguments):
            raise ValueError("parameter outside source/instruction")
        data = instructions[index][2]
        if target + size > len(data):
            raise ValueError("parameter outside target")
        data[target:target + size] = arguments[source:source + size]
    return instructions


@dataclass
class World:
    held: Counter = field(default_factory=Counter)
    boxed: Counter = field(default_factory=Counter)
    flags: dict = field(default_factory=dict)
    awards: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    removal_enabled: bool = True


def execute(instructions, world: World, budget=200):
    """Run one activation until initial wait, restart, or bounded blocked loop.

    Waits advance logical time; the model assumes fair scheduling. Removal
    affects held inventory only. Boxed tokens must be withdrawn externally.
    Condition groups here are single predicates, not a general EMEVD evaluator.
    """
    pc = 0
    conditions = {}
    labels = {op: i for i, (bank, op, _) in enumerate(instructions) if bank == 1014}
    for _ in range(budget):
        if not 0 <= pc < len(instructions):
            raise ValueError("event fell off end")
        bank, op, data = instructions[pc]
        pc += 1
        if (bank, op) == (2000, 2):
            if bytes(data) != bytes(4):
                raise ValueError("unexpected network sync")
        elif (bank, op) == (3, 16):
            group, kind, item, desired = struct.unpack('<bB2xiB3x', data)
            if kind != 3 or desired not in (0, 1):
                raise ValueError("unsupported item predicate")
            value = ((world.held[item] + world.boxed[item]) > 0) == bool(desired)
            if group == 0:
                if not value:
                    return 'waiting'
                conditions.clear()
            else:
                conditions[group] = value
        elif (bank, op) == (2003, 24):
            kind, item, quantity = struct.unpack('<iii', data)
            if kind != 3 or quantity <= 0:
                raise ValueError("unsupported removal")
            if world.removal_enabled:
                world.held[item] = max(0, world.held[item] - quantity)
            world.trace.append(('remove', item))
        elif (bank, op) == (2003, 2):
            flag, enabled = struct.unpack('<iB3x', data)
            if enabled not in (0, 1):
                raise ValueError("invalid flag state")
            world.flags[flag] = bool(enabled)
            world.trace.append(('flag', flag, bool(enabled)))
        elif (bank, op) == (2003, 4):
            lot, = struct.unpack('<i', data)
            world.awards.append(lot)
            world.trace.append(('award', lot))
        elif (bank, op) == (1001, 0):
            seconds, = struct.unpack('<f', data)
            if not 0 < seconds <= 60:
                raise ValueError("invalid wait")
        elif bank == 1014:
            if data:
                raise ValueError("label has arguments")
        elif (bank, op) == (1000, 101):
            label, desired, group, padding = struct.unpack('<BBbB', data)
            if padding or group not in conditions or label not in labels:
                raise ValueError("invalid conditional jump")
            if conditions[group] == bool(desired):
                pc = labels[label]
        elif (bank, op) == (1000, 4):
            if bytes(data) != b'\1\0\0\0':
                raise ValueError("expected restart")
            return 'restart'
        else:
            raise ValueError(f"unmodeled instruction {bank}[{op}]")
    return 'blocked'


def verify(events, rows):
    if not rows or 0 not in events:
        raise ValueError("missing rows/constructor")
    initializers = [data for bank, op, data in events[0].instructions
                    if (bank, op) == (2000, 0) and len(data) == 20
                    and 98000000 <= struct.unpack_from('<i', data, 4)[0] < 98000000 + len(rows)]
    if len(initializers) != len(rows):
        raise ValueError("missing/duplicate bridge initializer")
    for index, row in enumerate(rows):
        token, lot, ack = (row[k] for k in ('token_goods_id', 'item_lot_id', 'ack_flag'))
        expected = struct.pack('<iiiii', 0, 98000000 + index, token, lot, ack)
        if initializers.count(expected) != 1:
            raise ValueError(f"row {index}: wrong initializer arguments")
        code = instantiate(events[98000000 + index], expected[8:])
        for quantity in (0, 1, 3):
            for stale_ack in (False, True):
                world = World(held=Counter({token: quantity}), flags={ack: stale_ack})
                status = execute(code, world)
                if quantity == 0:
                    assert status == 'waiting' and not world.trace, (index, 'empty token')
                else:
                    assert status == 'restart', (index, status)
                    assert world.held[token] == 0 and world.awards == [lot], (index, 'consume/award')
                    assert world.flags[ack], (index, 'ack')
                    assert world.trace.index(('award', lot)) < world.trace.index(('flag', ack, True))
                    assert execute(code, world) == 'waiting' and world.awards == [lot], (index, 'replay')
        for boxed in (False, True):
            world = World(held=Counter({token: int(not boxed)}), boxed=Counter({token: int(boxed)}), removal_enabled=boxed)
            assert execute(code, world) == 'blocked' and not world.awards and not world.flags.get(ack), (index, 'blocked removal')
            if boxed:
                world.boxed[token] = 0
                world.held[token] = 1
                assert execute(code, world) == 'restart' and world.awards == [lot], (index, 'withdrawal')
    return len(rows)


def verify_mutation_controls(events, rows):
    """The non-pilot row must expose actual emitted-byte faults to the oracle."""
    if len(rows) <= 15:
        raise ValueError('row-15 positive population required')
    caught = []
    for fault in ('token argument', 'lot argument', 'ack substitution', 'removal', 'early ack', 'missing initializer'):
        mutated = copy.deepcopy(events)
        bridge = mutated[98000015]
        if fault in ('token argument', 'lot argument', 'missing initializer'):
            for i, (bank, op, data) in enumerate(mutated[0].instructions):
                if (bank, op) == (2000, 0) and struct.unpack_from('<i', data, 4)[0] == 98000015:
                    if fault == 'missing initializer':
                        del mutated[0].instructions[i]
                    else:
                        raw = bytearray(data)
                        struct.pack_into('<i', raw, 8 if fault == 'token argument' else 12, 1)
                        mutated[0].instructions[i] = (bank, op, bytes(raw))
                    break
        elif fault == 'ack substitution':
            bridge.parameters = [(i, t, 0 if i == 10 else s, n) for i, t, s, n in bridge.parameters]
        elif fault == 'removal':
            bridge.parameters = [(i, t, 4 if i == 5 else s, n) for i, t, s, n in bridge.parameters]
        else:
            bank, op, data = bridge.instructions[2]
            bridge.instructions[2] = (bank, op, data[:4] + b'\1\0\0\0')
        try:
            verify(mutated, rows)
        except (AssertionError, ValueError, KeyError):
            caught.append(fault)
        else:
            raise AssertionError(f'oracle accepted injected fault: {fault}')
    return caught


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dump', type=Path)
    parser.add_argument('request', type=Path)
    parser.add_argument('--mutation-controls', action='store_true')
    args = parser.parse_args()
    rows = json.loads(args.request.read_text(encoding='utf-8-sig'))['category8_awards']
    if isinstance(rows, dict):
        rows = list(rows.values())
    events = parse_dump(args.dump.read_text(encoding='utf-8-sig'))
    count = verify(events, rows)
    if args.mutation_controls:
        print('Rejected injected faults: ' + ', '.join(verify_mutation_controls(events, rows)))
    print(f'Modeled {count} emitted rows; live Bloodborne behavior remains unvalidated.')
