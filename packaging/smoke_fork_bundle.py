"""Check the actual frozen protocol executable without touching an installation."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib


def smoke(package: Path) -> None:
    backend = package / 'ap_backend' / 'bb-ap-backend.exe'
    required = [package / 'BBLauncher-AP.exe', backend,
                package / 'ap_backend/ap-client/bb-ap-client.exe',
                package / 'ap_backend/suppression/gameparam.parambnd.dcx',
                package / 'ap_backend/suppression/build-manifest.json']
    for path in required:
        if not path.is_file():
            raise RuntimeError(f'Missing packaged file: {path}')
    qt = subprocess.run(
        [str((package / 'BBLauncher-AP.exe').resolve()), '--ap-package-smoke'],
        # The smoke flag exits before constructing a window. Exercise the
        # deployed Windows platform plugin; offscreen is a development plugin
        # and is intentionally not part of the player bundle.
        env=dict(os.environ, QT_QPA_PLATFORM='windows'),
        capture_output=True, text=True, timeout=30,
    )
    if qt.returncode:
        raise RuntimeError(f'Packaged Qt launcher exited {qt.returncode}: {qt.stderr}')
    client = subprocess.run(
        [str((package / 'ap_backend/ap-client/bb-ap-client.exe').resolve()), '--version'],
        capture_output=True, text=True, timeout=15,
    )
    if client.returncode or not client.stdout.strip():
        raise RuntimeError(f'Packaged client could not report its version: {client.stderr}')
    with tempfile.TemporaryDirectory(prefix='bb-fork-smoke-') as temp:
        seed = Path(temp) / 'seed.bbseed.json'
        seed.write_text(json.dumps({
            'format': 'bb-seed-request-v1', 'seed': 'Package smoke',
            'player': 1, 'player_name': 'Package tester',
            'runtime_build': 'smoke', 'world_version': '0.1.0',
        }), encoding='utf-8')
        requests = [
            {'protocol': 'bb-ap-integration-v1', 'id': 'caps', 'seq': 1,
             'op': 'capabilities', 'params': {}},
            {'protocol': 'bb-ap-integration-v1', 'id': 'seed', 'seq': 2,
             'op': 'inspect_seed', 'params': {'seed_path': str(seed)}},
        ]
        result = subprocess.run(
            [str(backend.resolve()), '--state-root', str(Path(temp) / 'state')],
            input=''.join(json.dumps(item) + '\n' for item in requests),
            capture_output=True, text=True, timeout=60, cwd=temp,
        )
        if result.returncode:
            raise RuntimeError(f'Frozen backend exited {result.returncode}: {result.stderr}')
        responses = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        if len(responses) != 2 or any(not reply.get('ok') for reply in responses):
            raise RuntimeError(f'Unexpected frozen protocol responses: {responses}')
        if responses[0]['id'] != 'caps' or responses[1]['id'] != 'seed':
            raise RuntimeError('Frozen response IDs do not match requests')
        if responses[1]['result'].get('selected') != 'Package tester':
            raise RuntimeError('Frozen seed inspection did not select the sole player')
        # Run the shipped planner, with shipped catalogs, from outside the
        # checkout. This catches stale executables or missing expansion data.
        data = package / 'ap_backend/_internal/research'
        planner = package / 'ap_backend/tools/BBEnemizerPlanner/BBEnemizerPlanner.exe'
        with sqlite3.connect(data / 'bb_inputs.db') as database:
            row = database.execute(
                "SELECT blob FROM files WHERE path = 'mined/msb_enemies.tsv'"
            ).fetchone()
        if row is None:
            raise RuntimeError('Packaged inputs lack the enemy inventory')
        inventory = Path(temp) / 'enemies.tsv'
        inventory.write_bytes(zlib.decompress(row[0]))
        counts = []
        for expanded in (False, True):
            output = Path(temp) / f'enemies-{expanded}.json'
            command = [str(planner), '--inventory', str(inventory), '--seed', '12345',
                       '--output', str(output), '--tags', str(data / 'enemizer/enemy_tags.json'),
                       '--slot-policy', str(data / 'enemizer/slot_policy.json'),
                       '--facts', str(data / 'enemizer/archetype_facts.json')]
            if expanded:
                for name in ('contracts', 'spawns', 'chara'):
                    command += ['--release-file', str(data / f'enemizer/release_{name}.json')]
            result = subprocess.run(command, capture_output=True, text=True, timeout=90, cwd=temp)
            if result.returncode:
                raise RuntimeError(f'Packaged enemy planner failed: {result.stderr}')
            plan = json.loads(output.read_text(encoding='utf-8'))
            counts.append(plan['swap_count'])
            if expanded and plan['options']['release_tranches'] != ['chara', 'contracts', 'spawns']:
                raise RuntimeError('Packaged planner did not apply expanded coverage')
        if not 0 < counts[0] < counts[1]:
            raise RuntimeError(f'Expanded coverage did not increase enemy swaps: {counts}')
    print(f'Packaged client: {client.stdout.strip()}')
    print('Packaged Qt launcher: startup passed (no installation opened).')
    print('Frozen fork backend: capabilities and seed inspection passed (no game touched).')
    print(f'Packaged enemy planner: {counts[0]} normal / {counts[1]} expanded swaps (seed 12345).')


if __name__ == '__main__':
    smoke(Path(sys.argv[1]).resolve())
