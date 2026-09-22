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
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bb_enemizer.boss_contracts import (
    ARENAS as ARENA_CONTRACTS, BSB_PACKAGE, PAARL_PACKAGE, event_blocks, patch_contract_swap,
    plan_contract_swap,
)
from tools.bb_enemizer.boss_pool import assign_donors, combine_native_plans, compose_event_patches
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.bb_inputs import read_blob
from tools.build_boss_canary import compile_events
from tools.build_boss_catalog import build as build_catalog
from tools.build_boss_shuffle import check_output
from tools.build_cathedral_emevd import DARKSCRIPT_SHA256

ARENAS = {arena.key: arena for arena in ARENA_CONTRACTS}
PACKAGES = {package.key: package for package in (BSB_PACKAGE, PAARL_PACKAGE)}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_for(args) -> list[str]:
    return ([str(args.dotnet)] if args.dotnet else []) + [str(args.writer)]


def event_record(original: Path, before: str, after: str, fingerprints: dict,
                 protected: list[int]) -> dict:
    """Bind the compiled replacements to the exact source and edit set."""
    source, patched = event_blocks(before), event_blocks(after)
    if source.keys() - patched.keys():
        raise ValueError("encounter contract removed original events")
    changed = sorted(key for key in source if source[key] != patched[key])
    added = sorted(patched.keys() - source.keys())
    if not changed and not added:
        raise ValueError("encounter contract produced no event changes")
    for key in protected:
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
    if getattr(args, 'pool', None):
        mapping = assign_donors(args.seed, {
            'blood-starved-beast': ('darkbeast-paarl',),
            'darkbeast-paarl': ('blood-starved-beast',),
        })
        pairs = [(ARENAS[key], PACKAGES[value]) for key, value in mapping.items()]
    else:
        pairs = [(ARENAS[args.arena], PACKAGES[args.donor])]
    if digest(args.darkscript) != DARKSCRIPT_SHA256:
        raise ValueError('requires pinned DarkScript 3.6.3')
    check_output(args.output, (args.maps, args.scripts, args.events, args.gameparam,
                              args.paramdef, args.bundle, args.writer, args.darkscript))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Same-volume scratch permits atomic publication after native verification.
    with tempfile.TemporaryDirectory(prefix='.bb-encounter-build-', dir=args.output.parent) as temporary:
        scratch = Path(temporary)
        originals, source, compiled = (scratch / name for name in ('original', 'source', 'compiled'))
        originals.mkdir()
        filenames = {item.event_file.removesuffix('.js') for pair in pairs for item in pair}
        for name in filenames | {'common.emevd.dcx'}:
            shutil.copyfile(args.events / name, originals / name)
        compile_events(args.darkscript, 'decompile', originals, source, pairs[0][0].event_file)
        texts = {name + '.js': (source / (name + '.js')).read_text(encoding='utf-8-sig')
                 for name in filenames}
        variants = {}
        for arena, package in pairs:
            patched = patch_contract_swap(arena, package, texts[arena.event_file], texts[package.event_file])
            variants.setdefault(arena.event_file, []).append(patched)
        catalog = build_catalog(args.bundle)
        protected_by_file = {}
        for filename, patches in variants.items():
            protected = [row['completion_event'] for row in catalog['encounters']
                         if row['map'] == filename[:12]]
            protected_by_file[filename] = protected
            combined = compose_event_patches(texts[filename], patches, protected)
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
                                        json.loads(pins_run.stdout), protected_by_file[filename]))
        inventory = scratch / 'inventory.tsv'
        inventory.write_bytes(read_blob(args.bundle, 'mined/msb_enemies.tsv'))
        slots = load_slots(inventory)
        npcs, effects = load_params(args.bundle)
        plans = [plan_contract_swap(arena, package, slots, npcs, effects, args.seed) for arena, package in pairs]
        plan = plans[0] if len(plans) == 1 else combine_native_plans(args.seed, plans)
        plan['boss_encounters'] = {'format': 'bb-boss-encounters-v1', 'encounters': records}
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
    parser.add_argument('--bundle', type=Path, default=ROOT / 'research/bb_inputs.db')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--arena', choices=sorted(ARENAS))
    selection.add_argument('--pool', choices=('bsb-paarl',))
    parser.add_argument('--donor', choices=sorted(PACKAGES))
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
