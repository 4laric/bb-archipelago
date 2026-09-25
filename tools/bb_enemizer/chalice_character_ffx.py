"""Pinned direct character effects for experimental chalice donors.

Whole source banks are retained. This proves staged bytes, not recursive FXR
dependencies or the game's runtime precedence between area and subarea banks.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

PROOF_FILE = Path(__file__).with_suffix('.json')
PROOF_SHA256 = 'cf79f4be62ccd5f6f4b66973d6141e1b060f30cf9b2f890f836507538107a754'


def _proof() -> dict:
    raw = PROOF_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PROOF_SHA256:
        raise ValueError('chalice character effect proof resource changed')
    return json.loads(raw)


def supports_character(arena_key: str, character: str) -> bool:
    destination = _proof()['destinations'].get(arena_key)
    return destination is not None and character in destination['characters']


def character_ffx_plan(actor: dict, arena_key: str) -> dict:
    proof = _proof()
    character = actor['source_archetype']['model_name']
    target = proof['destinations'].get(arena_key)
    if target is None or character not in target['characters']:
        raise ValueError('chalice character bank delivery lacks a conflict-free arena proof')
    if not actor['destination_map'].startswith(target['bank'] + '_'):
        raise ValueError('chalice character bank destination map mismatch')
    template = proof['characters'][character]
    requirement = copy.deepcopy(template['requirement_template'])
    requirement.update({key: actor[key] for key in
                        ('source_map', 'source_part', 'source_entity_id')})
    destination = proof['banks'][target['bank']]
    deliveries, merges = [], []
    for bank, roots in template['bank_roots'].items():
        source = proof['banks'][bank]
        deliveries.append({
            'format': 'bb-boss-character-ffx-bank-requirement-v1',
            **{key: actor[key] for key in (
                'source_map', 'source_part', 'source_entity_id',
                'destination_map', 'destination_part', 'destination_entity_id')},
            'source_character': character,
            'source_ffx_file': source['file'],
            'destination_ffx_file': destination['file'],
            'roots': copy.deepcopy(roots),
        })
        merges.append({
            'source_file': source['file'], 'source_sha256': source['sha256'],
            'destination_file': destination['file'],
            'destination_sha256': destination['sha256'],
            'required_effect_ids': sorted(root['witness']['effect_id'] for root in roots),
            'policy': 'preserve_destination_union_source_v1',
        })
    return {
        'boss_character_ffx_requirements': [requirement],
        'boss_character_ffx_bank_requirements': deliveries,
        'boss_ffx_merges': merges,
        'chalice_character_effect_limits': {
            'global_bank_roots_not_delivered': template['global_bank_roots_not_delivered'],
            'unresolved_direct_roots': template['unresolved_direct_roots'],
            'recursive_fxr_dependencies': 'not-validated',
            'runtime_bank_precedence': 'not-validated',
        },
    }
