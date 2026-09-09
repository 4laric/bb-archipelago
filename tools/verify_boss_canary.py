#!/usr/bin/env python3
"""Verify an offline boss canary's retained files and print its live-test worksheet."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.bb_enemizer.boss_canary import ADAPTER, CHANGED_EVENTS, COMPLETION_EVENT

EVENT = 'dvdroot_ps4/event/m24_01_00_00.emevd.dcx'
GAMEPARAM = 'dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx'
AI = 'dvdroot_ps4/script/m24_01_00_00.luabnd.dcx'
PLAN = 'bb-enemizer-plan.json'
SOURCE_PLAN = 'source-enemizer-plan.json'
SCALING = 'scaling-report.json'
AI_REPORT = 'dvdroot_ps4/script.json'
RECEIPT = 'boss-adapter-report.json'
MAPS = {f'dvdroot_ps4/map/MapStudio/m24_01_00_{state}.msb.dcx' for state in ('00', '01', '11')}
EXPECTED_FILES = MAPS | {EVENT, GAMEPARAM, AI, PLAN, SOURCE_PLAN, SCALING, AI_REPORT}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path) -> dict:
    root = root.resolve()
    receipt_path = root / RECEIPT
    need(receipt_path.resolve().is_relative_to(root), 'receipt escapes overlay')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8-sig'))
    need(receipt.get('format') == 'bb-boss-adapter-v1' and receipt.get('adapter') == ADAPTER,
         'unsupported boss adapter receipt')
    need(receipt.get('applied') is True, 'boss adapter was not applied')
    need(receipt.get('completion_event') == COMPLETION_EVENT and receipt.get('ap_location') == 'boss_cleric_beast',
         'destination completion contract differs')
    need(receipt.get('changed_events') == CHANGED_EVENTS, 'changed event set differs')
    rows = receipt.get('files', [])
    need(isinstance(rows, list) and all(isinstance(row, dict) for row in rows), 'invalid file receipt')
    paths = [row.get('path') for row in rows]
    need(len(paths) == len(EXPECTED_FILES) and set(paths) == EXPECTED_FILES,
         'receipt must cover every canary file exactly once; rebuild older receipts')
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    need(actual == EXPECTED_FILES | {RECEIPT}, 'overlay contains missing or unexpected files')
    hashes = {}
    for row in rows:
        path = root / row['path']
        need(path.resolve().is_relative_to(root), 'file escapes overlay: ' + row['path'])
        need(isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256']), 'invalid file hash')
        need(path.stat().st_size == row.get('size') and digest(path) == row['sha256'], 'file changed: ' + row['path'])
        hashes[row['path']] = row['sha256']
    def read(name):
        return json.loads((root / name).read_text(encoding='utf-8-sig'))
    plan, source, scaling, ai = (read(name) for name in (PLAN, SOURCE_PLAN, SCALING, AI_REPORT))
    for item in (plan, source):
        need(item.get('boss_adapter') == ADAPTER and item.get('required_event_overlay') == EVENT,
             'plan boss contract differs')
        need(item.get('swap_count') == 1 and len(item.get('swaps', [])) == 1, 'canary must contain one swap')
    need(plan.get('scaling', {}).get('applied') is True and scaling.get('applied') is True, 'scaling was not applied')
    need(scaling.get('source_plan_sha256') == hashes[SOURCE_PLAN]
         and scaling.get('output_plan_sha256') == hashes[PLAN]
         and scaling.get('output_gameparam_sha256') == hashes[GAMEPARAM], 'scaling provenance mismatch')
    need(ai.get('applied') is True and ai.get('plan_sha256') == hashes[PLAN], 'AI plan provenance mismatch')
    need(ai.get('gameparam_sha256') == scaling.get('source_gameparam_sha256')
         and ai.get('paramdef_sha256') == scaling.get('paramdef_sha256'), 'AI/scaling input provenance mismatch')
    ai_maps = ai.get('maps', [])
    need(len(ai_maps) == 1 and ai_maps[0].get('map') == Path(AI).name
         and ai_maps[0].get('missing_goals_after') == 0
         and ai_maps[0].get('output_sha256') == hashes[AI], 'AI archive receipt mismatch or missing goals')
    need(receipt.get('output_event_sha256') == hashes[EVENT], 'event receipt mismatch')
    return {'adapter': ADAPTER, 'receipt_sha256': digest(receipt_path), 'files_verified': len(rows),
            'plan_sha256': hashes[PLAN], 'completion_event': COMPLETION_EVENT,
            'runtime_validated': False, 'placement': plan['swaps'][0]}


def worksheet(result: dict) -> str:
    return '\n'.join([
        '# BSB at Cleric Beast: live-test worksheet', '',
        f"Receipt SHA256: {result['receipt_sha256']}",
        f"Plan SHA256: {result['plan_sha256']}",
        f"Verified retained files: {result['files_verified']}", '',
        'File consistency passed. This does not establish runtime behavior or certify a trusted build.', '',
        'Record game serial/AppVer, emulator version, NG cycle, save state, and active overlay before testing.',
        'Use a backed-up test character with Cleric undefeated. No installation is performed by this tool.', '',
        '| Check | Result / evidence |', '| --- | --- |',
        '| First entrance: BSB appears on the bridge, without a Cleric leap or falling | Not run |',
        '| Detection, pursuit and attacks after encounter activation | Not run |',
        '| First phase near 67% HP; attacks resume after animation 7010 | Not run |',
        '| Second phase near 33% HP; attacks resume after animation 7011 | Not run |',
        '| Health bar label, phase music and camera | Not run |',
        '| Bridge collision, arena containment, no passive death/echo loop | Not run |',
        '| Player death and fog re-entry | Not run |',
        '| Save/reload during an undefeated encounter; phase behavior | Not run |',
        '| Defeat: Cleric flag 12411700, lamp, destination rewards, exactly one Cleric AP check | Not run |',
        '| Reload after victory: boss stays dead, no duplicate rewards/check | Not run |',
        '| Co-op and NG+ scaling (separate runs) | Not run |', '',
        'Keep this worksheet outside the overlay so verification can detect unexpected overlay files.', '',
    ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('overlay', type=Path)
    parser.add_argument('--json', action='store_true', help='print verification evidence instead of the worksheet')
    args = parser.parse_args(argv)
    try:
        result = verify(args.overlay)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'Canary verification failed: {error}\n')
    print(json.dumps(result, indent=2) if args.json else worksheet(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
