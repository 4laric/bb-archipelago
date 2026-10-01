"""Refresh the finite original actor witnesses for the complex Chalice arenas."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.bb_enemizer.chalice_complex_arenas import SPECS, PIN_FILE


def build(maps, writer, dotnet):
    output = {}
    for spec in SPECS.values():
        for state in spec.states:
            command = [dotnet, str(writer), '--boss-actor-pins', str(maps / (state + '.msb.dcx'))]
            evidence = json.loads(subprocess.check_output(command))
            wanted = {spec.arena.actor, *spec.helpers}
            parts = [p for p in evidence['parts'] if p['entity_id'] in wanted]
            if len(parts) != len(wanted) or {p['entity_id'] for p in parts} != wanted:
                raise ValueError(f'{state} original actor roster changed')
            output[state] = {str(p['entity_id']): p for p in parts}
    return {
        'format': 'bb-chalice-complex-arena-pins-v1',
        'source': 'CUSA03173 AppVer 01.09 original MSB; BBEnemizerWriter --boss-actor-pins',
        'maps': output,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps', type=Path, required=True)
    parser.add_argument('--writer', type=Path, required=True)
    parser.add_argument('--dotnet', default='dotnet')
    parser.add_argument('--output', type=Path, default=PIN_FILE)
    args = parser.parse_args()
    args.output.write_text(json.dumps(build(args.maps, args.writer, args.dotnet), indent=2) + '\n', encoding='utf-8')
    print(hashlib.sha256(args.output.read_bytes()).hexdigest())
