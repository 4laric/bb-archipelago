#!/usr/bin/env python3
"""Build the experimental BSB-at-Cleric overlay from original game inputs."""
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
from tools.bb_inputs import read_blob
from tools.bb_enemizer.boss_canary import DESTINATION_EVENT_FILE, DONOR_EVENT_FILE, patch_event_source, plan_canary
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.scaling import load_params
from tools.build_cathedral_emevd import DARKSCRIPT_SHA256


def compile_events(executable: Path, mode: str, source: Path, output: Path, expected: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(executable), '/cmd', '-' + mode, '-game', 'bb',
                             '-indir', str(source), '-outdir', str(output), '-force', '-silent'],
                            capture_output=True, check=True)
    # DarkScript can return success after a per-file compilation exception.
    if not (output / expected).is_file():
        detail = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        raise ValueError(f'DarkScript did not produce {expected}: {detail}')


def build(args) -> None:
    if hashlib.sha256(args.darkscript.read_bytes()).hexdigest() != DARKSCRIPT_SHA256:
        raise ValueError('requires pinned DarkScript 3.6.3')
    if args.output.exists():
        raise ValueError('output must not exist')
    for path in (args.events, args.maps, args.scripts, args.gameparam.parent, args.paramdef.parent):
        if args.output.is_relative_to(path):
            raise ValueError('output must be outside input directories')
    with tempfile.TemporaryDirectory(prefix='bb-boss-build-') as temp:
        root = Path(temp)
        original, source, compiled = root / 'original', root / 'source', root / 'compiled'
        original.mkdir()
        for name in (DESTINATION_EVENT_FILE, DONOR_EVENT_FILE, 'common.emevd.dcx'):
            shutil.copyfile(args.events / name, original / name)
        compile_events(args.darkscript, 'decompile', original, source, DESTINATION_EVENT_FILE + '.js')
        destination = source / (DESTINATION_EVENT_FILE + '.js')
        donor = source / (DONOR_EVENT_FILE + '.js')
        destination.write_text(patch_event_source(destination.read_text(encoding='utf-8-sig'),
                                                  donor.read_text(encoding='utf-8-sig')), encoding='utf-8')
        compile_events(args.darkscript, 'compile', source, compiled, DESTINATION_EVENT_FILE)
        inventory = root / 'inventory.tsv'
        inventory.write_bytes(read_blob(args.bundle, 'mined/msb_enemies.tsv'))
        npcs, effects = load_params(args.bundle)
        plan = root / 'plan.json'
        plan.write_text(json.dumps(plan_canary(load_slots(inventory), npcs, effects), indent=2) + '\n', encoding='utf-8')
        command = ([str(args.dotnet)] if args.dotnet else []) + [str(args.writer), '--boss-scaled',
            str(plan), str(args.gameparam), str(args.paramdef), str(args.maps), str(args.scripts),
            str(original / DESTINATION_EVENT_FILE), str(compiled / DESTINATION_EVENT_FILE), str(args.output), '--apply']
        subprocess.run(command, check=True)
        if not (args.output / 'boss-adapter-report.json').is_file():
            raise ValueError('writer returned without a boss adapter receipt')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('darkscript', 'writer', 'gameparam', 'paramdef', 'maps', 'scripts', 'events', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--dotnet', type=Path)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'research/bb_inputs.db')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if not args.apply:
        parser.error('refusing to build without --apply')
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    build(args)
    print('Experimental boss overlay built: ' + str(args.output))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
