"""Emit reviewed encounter recipes directly into Bloodborne EMEVD binaries.

Python retains the source specifications and their composition rules. Native
recipes supply instruction bytes, condition registers and parameter records;
seed generation never parses arbitrary script or launches DarkScript.
"""
from __future__ import annotations

import base64
import copy
import difflib
import hashlib
import json
import struct
import subprocess
from pathlib import Path

from .boss_canary import event_blocks

CATALOG_PATH = Path(__file__).with_name('native_event_catalog.json')


def fingerprint(event: dict) -> str:
    data = bytearray(struct.pack('<qi', event['id'], event['rest_behavior']))
    for ins in event['instructions']:
        args = base64.b64decode(ins['arg_data'], validate=True)
        data.extend(struct.pack('<iii', ins['bank'], ins['id'], len(args)))
        data.extend(args)
        data.extend(struct.pack('<I', ins['layer'] if ins['layer'] is not None else 0xffffffff))
    for p in event['parameters']:
        data.extend(struct.pack('<qqqii', p['instruction_index'], p['target_start_byte'],
                                p['source_start_byte'], p['byte_count'], p['unk_id']))
    return hashlib.sha256(data).hexdigest()


def _signature(instruction: dict) -> tuple:
    return (instruction['bank'], instruction['id'], instruction['arg_data'], instruction['layer'])


# Relative skips exercised by the pinned original constructors. The first
# byte is their instruction count; label-based GOTOs do not need relocation.
RELATIVE_SKIPS = {(1000, 1): 4, (1000, 3): 4, (1003, 1): 8, (1003, 5): 4}


def _flow_signature(instruction: dict) -> tuple:
    key = instruction['bank'], instruction['id']
    if key not in RELATIVE_SKIPS:
        return _signature(instruction)
    args = base64.b64decode(instruction['arg_data'], validate=True)
    if len(args) != RELATIVE_SKIPS[key]:
        raise ValueError('unsupported native constructor skip shape')
    return key + (args[1:], instruction['layer'])


def _apply_edits(original: list[dict], edits: list[tuple]) -> list[dict]:
    intervals = sorted((a, b) for a, b, _ in edits if a != b)
    if any(a[1] > b[0] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('native constructor edits overlap')
    if any(a < position < b for a, b in intervals for position, end, _ in edits if position == end):
        raise ValueError('native constructor insertion overlaps replacement')
    result = copy.deepcopy(original)
    for a, b, group in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        result[a:b] = copy.deepcopy(group)

    def position(index, *, target=False):
        return index + sum(len(group) - (b - a) for a, b, group in edits
                           if b <= index and (a != b or a < index or not target))

    for index, instruction in enumerate(original):
        if (instruction['bank'], instruction['id']) not in RELATIVE_SKIPS:
            continue
        if any(a <= index < b for a, b, _ in edits):
            raise ValueError('native constructor edit replaces control flow')
        _flow_signature(instruction)  # validates the pinned argument shape
        data = bytearray(base64.b64decode(instruction['arg_data']))
        target = index + 1 + data[0]
        if target > len(original) or any(a < target < b for a, b in intervals):
            raise ValueError('native constructor skip target is invalid or removed')
        at = position(index)
        count = position(target, target=True) - at - 1
        if not 0 <= count <= 255:
            raise ValueError('native constructor skip exceeds byte range')
        data[0] = count
        result[at]['arg_data'] = base64.b64encode(data).decode()
    return result


class NativeEventCatalog:
    def __init__(self, path: Path = CATALOG_PATH):
        self.data = json.loads(path.read_text(encoding='utf-8'))
        if self.data.get('format') != 'bb-native-event-catalog-v1':
            raise ValueError('unsupported native event catalog')

    def source(self, filename: str, native: dict) -> str:
        witnesses = self.data['sources'].get(filename, {})
        blocks = []
        for event in native['events']:
            actual = fingerprint(event)
            if native['fingerprints'].get(str(event['id'])) != actual:
                raise ValueError('native event readback fingerprint differs')
            known = witnesses.get(str(event['id']), {}).get(actual)
            if known is None:
                # Unrelated events have no source-level role and remain native
                # byte records. An adapter trying to own one fails its existing
                # source pin, rather than silently substituting a guessed body.
                known = (f"$Event({event['id']}, Default, function() {{\n"
                         f"    // Unmodified native event {actual}\n}});")
            blocks.append(known)
        return '\n\n'.join(blocks) + '\n'

    def statement(self, line: str) -> list[dict]:
        line = line.strip()
        if not line or line.startswith('//'):
            return []
        try:
            return self.data['statements'][line]
        except KeyError as exc:
            raise ValueError(f'no native constructor recipe for {line}') from exc

    def constructor(self, native: dict, before: str, after: str) -> dict:
        if native['parameters']:
            raise ValueError('constructor edits require an unparameterized event')
        original = native['instructions']
        signatures = [_signature(i) for i in original]
        old, new = before.splitlines(), after.splitlines()

        def locate(instructions: list[dict]) -> tuple[int, int]:
            needle = [_signature(i) for i in instructions]
            if not needle:
                raise ValueError('constructor edit has no instruction witness')
            hits = [i for i in range(len(signatures) - len(needle) + 1)
                    if signatures[i:i + len(needle)] == needle]
            if len(hits) != 1:
                raise ValueError('constructor instruction witness is missing or ambiguous')
            return hits[0], hits[0] + len(needle)

        edits = []
        for tag, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            # Existing adapters also insert initializers at the end of
            # Ludwig's first branch. Anchor these before its native skip-over-
            # else instruction, then relocate the original relative skips.
            depth = sum(line.count('{') - line.count('}') for line in old[:a])
            branch_tail = tag == 'insert' and depth == 2 and old[a].strip() == '} else {'
            if depth != 1 and not branch_tail:
                raise ValueError('native constructor edit would change guarded control flow')
            removed = [i for line in old[a:b] for i in self.statement(line)]
            inserted = [copy.deepcopy(i) for line in new[c:d] for i in self.statement(line)]
            if branch_tail:
                previous = self.statement(old[a - 1])
                first = last = locate(previous)[1]
                if (original[first]['bank'], original[first]['id']) != (1000, 3):
                    raise ValueError('native constructor branch tail has no unconditional skip')
            elif removed:
                first, last = locate(removed)
            elif a <= 1:
                first = last = 0
            elif a >= len(old) - 1:
                first = last = len(original)
            else:
                # Anchor an interior insertion to the following literal call;
                # no source line -> instruction index guess is made.
                following = next((self.statement(line) for line in old[a:-1]
                                  if line.strip() in self.data['statements']), None)
                if following is None:
                    raise ValueError('native constructor insertion has no following witness')
                first = last = locate(following)[0]
            if removed or inserted:
                edits.append((first, last, inserted))
        result = copy.deepcopy(native)
        result['instructions'] = _apply_edits(original, edits)
        return result

    def recipe(self, native: dict, before: str, after: str, protected: list[int]) -> dict:
        originals = {event['id']: event for event in native['events']}
        old, new = event_blocks(before), event_blocks(after)
        if set(old) != set(originals) or old.keys() - new.keys():
            raise ValueError('native recipe source event identities differ')
        edits = []
        for eid, block in new.items():
            if block == old.get(eid):
                continue
            if eid in protected:
                raise ValueError('native recipe changes protected progression')
            if eid == 0:
                event = self.constructor(originals[0], old[0], block)
            else:
                key = hashlib.sha256(block.encode()).hexdigest()
                try:
                    event = copy.deepcopy(self.data['events'][key])
                except KeyError as exc:
                    raise ValueError(f'no reviewed native recipe for event {eid} ({key})') from exc
                if event['id'] != eid:
                    raise ValueError('native recipe event identity differs')
            edits.append(event)
        return {'format': 'bb-native-event-recipe-v1', 'original_sha256': native['sha256'],
                'events': edits, 'fingerprints': {str(e['id']): fingerprint(e) for e in edits},
                'protected_events': protected}


def read_native_sources(command: list[str], originals: Path, output: Path,
                        catalog: NativeEventCatalog) -> tuple[dict, dict]:
    subprocess.run(command + ['--native-event-dump', str(originals), str(output)], check=True)
    files = json.loads(output.read_text())
    return {name + '.js': catalog.source(name + '.js', file) for name, file in files.items()}, files


def write_native_events(command: list[str], original: Path, output: Path,
                        request: Path, recipe: dict) -> None:
    request.write_text(json.dumps(recipe, sort_keys=True) + '\n', encoding='utf-8')
    subprocess.run(command + ['--native-event-write', str(original), str(request), str(output)], check=True)


def compose_override(native: dict, recipe: dict, override: dict) -> dict:
    """Merge AP binary edits against the same original, preserving boss edits."""
    result = copy.deepcopy(recipe)
    before = {e['id']: e for e in native['events']}
    edits = {e['id']: e for e in result['events']}
    other = {e['id']: e for e in override['events']}
    if before.keys() - other.keys():
        raise ValueError('AP override removed original events')
    for eid, event in other.items():
        if eid in before and fingerprint(event) == fingerprint(before[eid]):
            continue
        if eid in result['protected_events']:
            raise ValueError('AP override changes protected boss progression')
        if eid not in edits:
            edits[eid] = copy.deepcopy(event)
        elif fingerprint(edits[eid]) != fingerprint(event):
            if eid != 0:
                raise ValueError(f'AP and boss edits overlap event {eid}')
            if any(e['parameters'] for e in (before[0], edits[0], event)):
                raise ValueError('AP constructor composition requires no parameters')
            original = before[0]['instructions']
            original_keys = [_flow_signature(i) for i in original]
            changes = {}
            inserts = {}
            for variant in (edits[0], event):
                instructions = variant['instructions']
                keys = [_flow_signature(i) for i in instructions]
                for tag, a, b, c, d in difflib.SequenceMatcher(None, original_keys, keys, autojunk=False).get_opcodes():
                    if tag == 'equal':
                        continue
                    group = instructions[c:d]
                    if a == b:
                        groups = inserts.setdefault(a, [])
                        if group not in groups:
                            groups.append(group)
                    elif (a, b) in changes and changes[a, b] != group:
                        raise ValueError('AP and boss constructor edits conflict')
                    else:
                        changes[a, b] = group
            intervals = sorted(changes)
            if any(left[1] > right[0] for left, right in zip(intervals, intervals[1:])):
                raise ValueError('AP and boss constructor edits overlap')
            if any(a < position < b for a, b in intervals for position in inserts):
                raise ValueError('AP insertion overlaps boss constructor edit')
            operations = [(a, b, group) for (a, b), group in changes.items()]
            operations += [(position, position, [i for group in groups for i in group])
                           for position, groups in inserts.items()]
            edits[0]['instructions'] = _apply_edits(original, operations)
    result['events'] = list(edits.values())
    result['fingerprints'] = {str(e['id']): fingerprint(e) for e in result['events']}
    return result
