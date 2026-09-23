"""Check the actual frozen protocol executable without touching an installation."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile


def smoke(package: Path) -> None:
    backend = package / 'ap_backend' / 'bb-ap-backend.exe'
    required = [package / 'BBLauncher-AP.exe', backend,
                package / 'ap_backend/ap-client/bb-ap-client.exe',
                package / 'ap_backend/suppression/gameparam.parambnd.dcx',
                package / 'ap_backend/suppression/build-manifest.json']
    for path in required:
        if not path.is_file():
            raise RuntimeError(f'Missing packaged file: {path}')
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
    print(f'Packaged client: {client.stdout.strip()}')
    print('Frozen fork backend: capabilities and seed inspection passed (no game touched).')


if __name__ == '__main__':
    smoke(Path(sys.argv[1]).resolve())
