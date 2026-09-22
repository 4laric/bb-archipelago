#!/usr/bin/env python3
"""Compile reviewed arena/combat contracts into an experimental boss overlay.

Uses the owner's original binaries and the pinned development compiler. No
overlay is activated and no game process is started. Runtime behavior remains
unvalidated even after all structural and serialization checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bb_enemizer.boss_contracts import (
    ARENAS as ARENA_CONTRACTS, PACKAGES as COMBAT_PACKAGES, COMPATIBILITY, event_blocks, patch_contract_swap,
    plan_contract_swap,
)
from tools.bb_enemizer.boss_pool import (
    assign_donors, combine_native_plans, compose_event_patches, validate_terminal_predicates,
)
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.gascoigne_contract import (
    ProjectOwnedIds, NativeActorPin, patch_gascoigne_at_cleric, native_plan_gascoigne_at_cleric,
)
from tools.bb_enemizer.scaling import load_params
from tools.bb_inputs import read_blob, read_prefix
from tools.build_boss_canary import compile_events
from tools.build_boss_catalog import build as build_catalog
from tools.build_boss_shuffle import check_output
from tools.build_cathedral_emevd import DARKSCRIPT_SHA256

ARENAS = {arena.key: arena for arena in ARENA_CONTRACTS}
PACKAGES = {package.key: package for package in COMBAT_PACKAGES}

# Project-owned allocation, not original game IDs. The Gascoigne planner scans
# every bundled EMEVD operand and MSB actor before accepting these numbers.
GASCOIGNE_ALLOCATION = ProjectOwnedIds(
    beast_entity_id=980001,
    phase_event_ids={12414807: 12990001, 12414808: 12990002, 12414809: 12990003},
    terminal_bridge_event_id=12990004, destination_part='ap_gascoigne_beast',
    evidence='BB AP Gascoigne-at-Cleric allocation v1; full original corpus collision scan',
)


def gascoigne_actor_pins(args, slots) -> tuple[dict[str, NativeActorPin], list[dict]]:
    pins, initializations = {}, []
    for name in sorted({slot.map_name for slot in slots
                        if slot.entity_id == 2410800 and slot.map_name.startswith('m24_01_')}):
        path = next((args.maps / (name + suffix) for suffix in ('.msb.dcx', '.msb')
                     if (args.maps / (name + suffix)).is_file()), None)
        if path is None:
            raise ValueError('missing Gascoigne source map state ' + name)
        run = subprocess.run(command_for(args) + ['--boss-actor-pins', str(path)],
                             check=True, capture_output=True, text=True)
        report = json.loads(run.stdout)
        if report.get('format') != 'bb-boss-actor-pins-v1' or report.get('map') != name:
            raise ValueError('invalid native actor pin report')
        parts = {part['name']: part for part in report['parts']}
        beast, human = parts['c2720_0000'], parts['c2710_0000']
        pins[name] = NativeActorPin(part_sha256=beast['fingerprint'], anchor_sha256=human['fingerprint'],
                                   **beast['source_initialization'])
        initializations.append({
            'source_map': name, 'source_part': human['name'], 'source_entity_id': human['entity_id'],
            'source_archetype': human['source_archetype'],
            'source_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': human['fingerprint']},
            'source_initialization': human['source_initialization'],
            'destination_map': name, 'destination_part': 'c5000_0000', 'destination_entity_id': 2410800,
        })
    return pins, initializations


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_for(args) -> list[str]:
    return ([str(args.dotnet)] if args.dotnet else []) + [str(args.writer)]


def lift_zero_argument_initializers(source: str) -> str:
    """Lift native AP calls whose absent argument payload DarkScript won't recompile.

    Only zero-parameter functions declared in this file qualify. The high-level
    form lets DarkScript encode its required unused argument padding.
    """
    no_parameters = {int(match[1]) for match in re.finditer(
        r'\$Event\((\d+),\s*\w+,\s*function\(\s*\)', source)}
    def replace(match):
        if int(match[2]) not in no_parameters:
            raise ValueError('argumentless initializer has no declared zero-parameter event')
        return f'$InitializeEvent({match[1]}, {match[2]});'
    return re.sub(r'(?<![\w$])InitializeEvent\((\d+),\s*(\d+)\);', replace, source)


def validate_allocations(bundle: Path, slots, records: list[dict], plan: dict) -> None:
    """Check project-owned identifiers against the entire original corpus."""
    used = {slot.entity_id for slot in slots}
    for body in read_prefix(bundle, 'event/').values():
        used.update(int(value) for value in re.findall(r'(?<![\w])-?\d+(?![\w])', body.decode('utf-8-sig')))
    events = [event for record in records for event in record['added_event_ids']]
    if len(events) != len(set(events)):
        raise ValueError('added event IDs collide across output maps')
    actors = {row['destination_entity_id'] for row in plan.get('boss_actor_additions', [])}
    if set(events) & actors:
        raise ValueError('added event and actor identifiers collide')
    allocated = set(events) | actors
    if any(not isinstance(value, int) or value <= 0 for value in allocated) or allocated & used:
        raise ValueError('project-owned identifier collides with an original corpus operand or actor')


def event_record(original: Path, before: str, after: str, fingerprints: dict,
                 protected: list[int], terminals: tuple[dict, ...] = ()) -> dict:
    """Bind the compiled replacements to the exact source and edit set."""
    source, patched = event_blocks(before), event_blocks(after)
    if source.keys() - patched.keys():
        raise ValueError("encounter contract removed original events")
    changed = sorted(key for key in source if source[key] != patched[key])
    added = sorted(patched.keys() - source.keys())
    if not changed and not added:
        raise ValueError("encounter contract produced no event changes")
    validate_terminal_predicates(source, patched, protected, terminals)
    terminal_ids = {row['event_id'] for row in terminals}
    for key in protected:
        if key in terminal_ids:
            continue
        if key not in source or source[key] != patched[key]:
            raise ValueError(f"encounter contract changed AP completion event {key}")
    pins = {}
    for key in changed + added:
        pin = fingerprints.get(str(key))
        if not isinstance(pin, str) or len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
            raise ValueError(f"missing or invalid compiled event fingerprint {key}")
        pins[str(key)] = pin
    return {
        "destination_event_file": original.name,
        "original_event_sha256": digest(original),
        "changed_event_ids": changed,
        "added_event_ids": added,
        "compiled_event_fingerprints": pins,
        "protected_completion_event_ids": sorted(protected),
        "terminal_predicates": list(terminals),
    }


def verify_receipt(root: Path) -> dict:
    receipt = json.loads((root / 'boss-encounters-report.json').read_text(encoding='utf-8-sig'))
    if receipt.get('format') != 'bb-boss-encounters-v1' or receipt.get('applied') is not True:
        raise ValueError('writer did not produce an applied encounter receipt')
    rows = receipt.get('files')
    if not isinstance(rows, list) or not rows:
        raise ValueError('encounter receipt has no files')
    expected = set()
    for row in rows:
        name = row['path']
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or name in expected:
            raise ValueError('duplicate or escaping encounter receipt path')
        expected.add(name)
        if not path.is_file() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError('encounter output changed: ' + name)
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    if actual != expected | {'boss-encounters-report.json'}:
        raise ValueError('encounter output file set differs from receipt')
    return receipt


def build(args) -> dict:
    gascoigne = getattr(args, 'donor', None) == 'father-gascoigne'
    if gascoigne and (getattr(args, 'pool', None) or args.arena != 'cleric-beast'):
        raise ValueError('Gascoigne currently requires the reviewed Cleric arena adapter')
    if getattr(args, 'pool', None):
        graph = {
            'blood-starved-beast': ('darkbeast-paarl',),
            'darkbeast-paarl': ('blood-starved-beast',),
        } if args.pool == 'bsb-paarl' else {
            arena: tuple(donor for donor in donors if donor in ARENAS)
            for arena, donors in COMPATIBILITY.items() if arena in ARENAS}
        mapping = assign_donors(args.seed, graph)
        pairs = [(ARENAS[key], PACKAGES[value]) for key, value in mapping.items()]
    else:
        pairs = [(ARENAS[args.arena], None if gascoigne else PACKAGES[args.donor])]
    if digest(args.darkscript) != DARKSCRIPT_SHA256:
        raise ValueError('requires pinned DarkScript 3.6.3')
    check_output(args.output, (args.maps, args.scripts, args.events, args.gameparam,
                              args.paramdef, args.bundle, args.writer, args.darkscript))
    event_overrides = getattr(args, 'event_overrides', None)
    if event_overrides is not None:
        if not event_overrides.is_dir():
            raise ValueError('event override directory does not exist')
        check_output(args.output, (event_overrides,))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Same-volume scratch permits atomic publication after native verification.
    with tempfile.TemporaryDirectory(prefix='.bb-encounter-build-', dir=args.output.parent) as temporary:
        scratch = Path(temporary)
        originals, source, compiled = (scratch / name for name in ('original', 'source', 'compiled'))
        originals.mkdir()
        filenames = {item.event_file.removesuffix('.js') for pair in pairs for item in pair if item is not None}
        for name in filenames | {'common.emevd.dcx'}:
            shutil.copyfile(args.events / name, originals / name)
        compile_events(args.darkscript, 'decompile', originals, source, pairs[0][0].event_file)
        texts = {name + '.js': (source / (name + '.js')).read_text(encoding='utf-8-sig')
                 for name in filenames}
        variants = {}
        terminals = {}
        for arena, package in pairs:
            if gascoigne:
                patched = patch_gascoigne_at_cleric(texts[arena.event_file], GASCOIGNE_ALLOCATION)
                terminals[arena.event_file] = ({'event_id': 12411700, 'original_actor': 2410800,
                    'bridge_event_id': GASCOIGNE_ALLOCATION.terminal_bridge_event_id},)
            else:
                patched = patch_contract_swap(arena, package, texts[arena.event_file], texts[package.event_file])
            variants.setdefault(arena.event_file, []).append(patched)
        override_inputs = []
        if event_overrides is not None:
            override_binary, override_source = scratch / 'override-binary', scratch / 'override-source'
            override_binary.mkdir()
            for filename in variants:
                path = event_overrides / filename.removesuffix('.js')
                if path.is_file():
                    shutil.copyfile(path, override_binary / path.name)
                    override_inputs.append({'file': path.name, 'sha256': digest(path)})
            if override_inputs:
                shutil.copyfile(originals / 'common.emevd.dcx', override_binary / 'common.emevd.dcx')
                compile_events(args.darkscript, 'decompile', override_binary, override_source,
                               override_inputs[0]['file'] + '.js')
                for item in override_inputs:
                    filename = item['file'] + '.js'
                    variants[filename].append(lift_zero_argument_initializers(
                        (override_source / filename).read_text(encoding='utf-8-sig')))
        catalog = build_catalog(args.bundle)
        protected_by_file = {}
        for filename, patches in variants.items():
            protected = [row['completion_event'] for row in catalog['encounters']
                         if row['map'] == filename[:12]]
            protected_by_file[filename] = protected
            combined = compose_event_patches(texts[filename], patches, protected, terminals.get(filename, ()))
            (source / filename).write_text(combined, encoding='utf-8')
        compile_events(args.darkscript, 'compile', source, compiled,
                       pairs[0][0].event_file.removesuffix('.js'))
        records = []
        for filename in sorted(variants):
            event_name = filename.removesuffix('.js')
            pins_run = subprocess.run(command_for(args) + ['--boss-encounter-pins', str(compiled / event_name)],
                                      check=True, capture_output=True, text=True)
            records.append(event_record(originals / event_name, texts[filename],
                                        (source / filename).read_text(encoding='utf-8'),
                                        json.loads(pins_run.stdout), protected_by_file[filename],
                                        terminals.get(filename, ())))
        inventory = scratch / 'inventory.tsv'
        inventory.write_bytes(read_blob(args.bundle, 'mined/msb_enemies.tsv'))
        slots = load_slots(inventory)
        npcs, effects = load_params(args.bundle)
        if gascoigne:
            actor_pins, initializations = gascoigne_actor_pins(args, slots)
            plans = [native_plan_gascoigne_at_cleric(slots, npcs, effects, GASCOIGNE_ALLOCATION,
                                                   actor_pins, args.seed)]
            plans[0]['boss_actor_initializations'] = initializations
        else:
            plans = [plan_contract_swap(arena, package, slots, npcs, effects, args.seed) for arena, package in pairs]
        plan = plans[0] if len(plans) == 1 else combine_native_plans(args.seed, plans)
        validate_allocations(args.bundle, slots, records, plan)
        plan['boss_encounters'] = {'format': 'bb-boss-encounters-v1', 'encounters': records}
        if override_inputs:
            plan['input_event_overrides'] = override_inputs
        plan_path = scratch / 'plan' / 'plan.json'
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        output = scratch / 'overlay'
        subprocess.run(command_for(args) + [
            '--boss-encounters', str(plan_path), str(args.gameparam), str(args.paramdef),
            str(args.maps), str(args.scripts), str(originals), str(compiled), str(output), '--apply',
        ], check=True)
        receipt = verify_receipt(output)
        if args.output.exists():
            raise ValueError('output appeared during build; refusing to replace it')
        output.rename(args.output)
        return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('darkscript', 'writer', 'gameparam', 'paramdef', 'maps', 'scripts', 'events', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--dotnet', type=Path)
    parser.add_argument('--event-overrides', type=Path,
                        help='compose existing AP event patches affecting boss maps against the same originals')
    parser.add_argument('--bundle', type=Path, default=ROOT / 'research/bb_inputs.db')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--arena', choices=sorted(ARENAS))
    selection.add_argument('--pool', choices=('bsb-paarl', 'reviewed'))
    parser.add_argument('--donor', choices=sorted((*PACKAGES, 'father-gascoigne')))
    parser.add_argument('--seed', required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if bool(args.arena) != bool(args.donor):
        parser.error('--arena and --donor must be supplied together')
    if not args.apply:
        parser.error('refusing to build without --apply')
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    result = build(args)
    print(json.dumps({'output': str(args.output), 'files_verified': len(result['files']),
                      'runtime_validated': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
