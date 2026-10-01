"""Refresh authored native event recipes with the pinned development oracle.

Seed generation consumes the resulting recipes, never this tool or DarkScript.
The catalog contains reviewed event bodies and literal instruction encodings;
it does not vendor the compiler's EMEDF instruction definitions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import base64
import struct
import sys
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bb_inputs import read_prefix
from tools.bb_enemizer.boss_canary import event_blocks
from tools.build_boss_canary import compile_events
from tools.build_cathedral_emevd import DARKSCRIPT_SHA256
from tools.build_boss_encounters import (
    ARENAS, PACKAGES, good_boss_routes, patch_pair_events, reusable_recipes, chalice_recipes,
)

CALL = re.compile(r"^\s*\$?\w+\([^\n]*\);\s*$")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def dump(writer: Path, source: Path, output: Path) -> dict:
    subprocess.run(['dotnet', str(writer), '--native-event-dump', str(source), str(output)], check=True)
    return json.loads(output.read_text())


def generate(args) -> dict:
    if hashlib.sha256(args.darkscript.read_bytes()).hexdigest() != DARKSCRIPT_SHA256:
        raise ValueError('catalog refresh requires the pinned DarkScript 3.6.3 oracle')
    # Adapters repeatedly inspect the same original maps. Cache parses for the
    # oracle sweep, returning fresh dictionaries to preserve caller ownership.
    original_parser = event_blocks
    cached = lru_cache(maxsize=128)(original_parser)
    def copied_parse(text):
        return dict(cached(text))
    for module_name, module in list(sys.modules.items()):
        if module_name.startswith('tools.') and getattr(module, 'event_blocks', None) is original_parser:
            module.event_blocks = copied_parse
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=args.resume)
    original, source, compiled = [work / name for name in ('original', 'source', 'compiled')]
    original.mkdir(exist_ok=args.resume)
    bundled = {Path(name).name: blob.decode('utf-8-sig')
               for name, blob in read_prefix(args.bundle, 'event/').items()}
    for name in bundled:
        shutil.copyfile(args.events / name.removesuffix('.js'), original / name.removesuffix('.js'))
    if not args.resume:
        compile_events(args.darkscript, 'decompile', original, source, 'm24_01_00_00.emevd.dcx.js')
    installed = {name: (source / name).read_text(encoding='utf-8-sig') for name in bundled}
    native_originals = (json.loads((work / 'original-native.json').read_text()) if args.resume
                        else dump(args.writer, original, work / 'original-native.json'))
    for name, record in native_originals.items():
        if hashlib.sha256((original / name).read_bytes()).hexdigest() != record['sha256']:
            raise ValueError('resume inputs differ from the extracted native originals')
    sources = {}
    for name, text in installed.items():
        blocks = event_blocks(text)
        records = native_originals[name.removesuffix('.js')]
        sources[name] = {str(eid): {records['fingerprints'][str(eid)]: block}
                         for eid, block in blocks.items()}

    recipes = reusable_recipes()
    recipes.update(chalice_recipes())
    blocks, calls, coverage = {}, {}, []
    direct_statements = {}
    for name, text in installed.items():
        native = native_originals[name.removesuffix('.js')]
        constructor = next((e for e in native['events'] if e['id'] == 0), None)
        if constructor is None:
            continue
        initializers = [i for i in constructor['instructions'] if i['bank'] == 2000 and i['id'] in (0, 6)]
        at = 0
        for line in event_blocks(text)[0].splitlines():
            match = re.fullmatch(r'\s*\$?Initialize(?:Common)?Event\(\s*(\d+)\s*,\s*(\d+)[^\n]*\);\s*', line)
            if match:
                slot, eid = map(int, match.groups())
                while at < len(initializers):
                    instruction = initializers[at]
                    at += 1
                    data = base64.b64decode(instruction['arg_data'])
                    if len(data) >= 8 and struct.unpack_from('<II', data) == (slot, eid):
                        direct_statements[line.strip()] = [instruction]
                        break
                else:
                    raise ValueError(f'no original initializer witness for {name}: {line}')
    definitions = {}
    def collect(text: str, before: str | None = None) -> None:
        old = event_blocks(before) if before else {}
        for eid, block in event_blocks(text).items():
            variants = definitions.setdefault(eid, [])
            if block not in variants:
                variants.append(block)
            if eid != 0 and before is not None and old.get(eid) != block:
                blocks.setdefault(digest(block), block)
            elif eid == 0:
                for line in block.splitlines()[1:-1]:
                    if CALL.fullmatch(line) and line.strip() not in direct_statements:
                        calls.setdefault(line.strip(), line.strip())

    for text in bundled.values():
        collect(text)
    for text in installed.values():
        collect(text)
    for arena_key, donor_key in sorted(good_boss_routes()):
        arena, donor = ARENAS[arena_key], PACKAGES[donor_key]
        for label, texts in [('bundle', bundled), ('installed', installed)]:
            patched = patch_pair_events(arena, donor, texts, recipes, {}, materialized=True)
            collect(patched, texts[arena.event_file])
        coverage.append([arena_key, donor_key])
    from tools.bb_enemizer.winter_lanterns import CALLEES, patch_winter_lanterns
    for name in CALLEES:
        for texts in (bundled, installed):
            collect(patch_winter_lanterns(name, texts[name + '.emevd.dcx.js']), texts[name + '.emevd.dcx.js'])

    # Compile each distinct body once under an isolated temporary ID. The ID
    # is restored after export; instruction arguments and parameter records
    # remain exactly as compiled. Constructors use individual literal calls,
    # allowing seed-dependent insertions/removals without a script compiler.
    # A fresh stage prevents stale batches from a prior resume entering the
    # oracle dump and shadowing newly compiled temporary event IDs.
    import uuid
    stage = work / ('recipes-' + uuid.uuid4().hex)
    source_out, compiled = stage / 'source', stage / 'compiled'
    source_out.mkdir(parents=True)
    header = installed['m24_01_00_00.emevd.dcx.js'].split('$Event(', 1)[0]
    (source_out / 'common.emevd.dcx.js').write_text(installed['common.emevd.dcx.js'], encoding='utf-8')
    entries = [('event', key, body) for key, body in blocks.items()]
    entries += [('call', key, f'$Event(0, Default, function() {{\n    {body}\n}});')
                for key, body in calls.items()]
    index = {}
    files = {}
    aliases = {}
    # Bounded batches keep the oracle's per-file parser/compiler work small.
    for offset in range(0, len(entries), 100):
        chunk = entries[offset:offset + 100]
        filename = f'recipes{offset // 100:04d}.emevd.dcx.js'
        bodies = []
        local_aliases = {}
        extra_definitions = []
        common_ids = set(event_blocks(installed['common.emevd.dcx.js']))
        def resolve_calls(body):
            def resolve(match):
                eid = int(match[2])
                if eid in common_ids:
                    return match[0]
                count = match[3].count(',')
                key = (eid, count)
                if key not in local_aliases:
                    candidates = [block for block in definitions.get(eid, [])
                                  if len([p for p in re.search(r'function\(([^)]*)\)', block)[1].split(',') if p.strip()]) == count]
                    if not candidates:
                        raise ValueError(f'no development callee definition for {eid} with {count} arguments')
                    alias = 800000000 + len(aliases) + 1
                    aliases[alias] = eid
                    local_aliases[key] = alias
                    definition = re.sub(r'\$Event\(\d+,', f'$Event({alias},', candidates[0], count=1)
                    extra_definitions.append(resolve_calls(definition))
                return match[1] + str(local_aliases[key]) + match[3]
            return re.sub(r'(\$InitializeEvent\(\s*[^,]+,\s*)(\d+)([^\n;]*)', resolve, body)
        for n, (kind, key, body) in enumerate(chunk, start=offset + 1):
            temp_id = 900000000 + n
            bodies.append(resolve_calls(re.sub(r'\$Event\(\d+,', f'$Event({temp_id},', body, count=1)))
            index[temp_id] = (kind, key, int(re.search(r'\$Event\((\d+),', body)[1]))
        bodies += extra_definitions
        (source_out / filename).write_text(header + '\n\n'.join(bodies) + '\n', encoding='utf-8')
        files[filename.removesuffix('.js')] = chunk
    compile_events(args.darkscript, 'compile', source_out, compiled, next(iter(files)))
    emitted = dump(args.writer, compiled, stage / 'native.json')
    events, statements = {}, {}
    for file in emitted.values():
        for event in file['events']:
            if event['id'] not in index:
                continue
            kind, key, real_id = index[event['id']]
            event['id'] = real_id
            for instruction in event['instructions']:
                data = bytearray(base64.b64decode(instruction['arg_data']))
                if instruction['bank'] == 2000 and instruction['id'] == 0 and len(data) >= 8:
                    target = struct.unpack_from('<I', data, 4)[0]
                    if target in aliases:
                        struct.pack_into('<I', data, 4, aliases[target])
                        instruction['arg_data'] = base64.b64encode(data).decode()
            if kind == 'event':
                events[key] = event
            else:
                if event['parameters']:
                    raise ValueError('constructor literal acquired parameter substitutions')
                statements[key] = event['instructions']
    if len(events) != len(blocks) or len(statements) != len(calls):
        raise ValueError('oracle failed to emit the complete recipe corpus')
    statements.update(direct_statements)
    result = {'format': 'bb-native-event-catalog-v1', 'coverage': coverage,
              'sources': sources, 'events': events, 'statements': statements}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, sort_keys=True, separators=(',', ':')) + '\n', encoding='utf-8')
    return {'routes': len(coverage), 'events': len(events), 'statements': len(statements)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('events', 'darkscript', 'writer', 'work', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'research/bb_inputs.db')
    parser.add_argument('--resume', action='store_true', help='reuse completed original-source extraction')
    print(json.dumps(generate(parser.parse_args()), sort_keys=True))


if __name__ == '__main__':
    main()
