"""Deterministic encounter matching and composition of independently reviewed edits.

This module supplies mechanics, not approval for a new donor/arena pairing.
The caller supplies the explicit compatibility graph of reviewed contracts.
"""
from __future__ import annotations

import difflib
import copy
import random
from collections.abc import Mapping, Sequence

from .boss_canary import event_blocks
from .bosses import parse_events
from .scaling import NPC_CLONE_START, NPC_CLONE_END


def combine_native_plans(seed: str, plans: Sequence[dict]) -> dict:
    """Compose canonical pair plans with one shared scaling allocation."""
    if not plans:
        raise ValueError('boss pool has no pair plans')
    swaps, changes, skips, contracts = [], [], [], []
    logical, physical = set(), set()
    for plan in plans:
        if plan.get('format') != 'bb-enemizer-plan-v2' or plan.get('seed') != seed or plan.get('dry_run') is not True:
            raise ValueError('boss pair plan identity differs')
        for swap in plan['swaps']:
            if swap['logical_key'] in logical or physical.intersection(swap['destination_keys']):
                raise ValueError('boss pair plans overlap a destination')
            logical.add(swap['logical_key'])
            physical.update(swap['destination_keys'])
            swaps.append(copy.deepcopy(swap))
        changes.extend(copy.deepcopy(plan['scaling']['changes']))
        skips.extend(copy.deepcopy(plan['scaling']['skips']))
        contracts.append(copy.deepcopy(plan['boss_contract']))
    changes.sort(key=lambda row: row['logical_key'])
    for index, change in enumerate(changes):
        clone = NPC_CLONE_START + index
        if clone > NPC_CLONE_END:
            raise ValueError('boss pool exhausts NpcParam clone range')
        change['cloned_npc_param_id'] = clone
    accounted = [row['logical_key'] for row in changes + skips]
    if len(accounted) != len(logical) or set(accounted) != logical:
        raise ValueError('boss scaling changes/skips must account for every placement once')
    return {
        'format': 'bb-enemizer-plan-v2', 'dry_run': True, 'seed': seed,
        'swap_count': len(swaps), 'swaps': sorted(swaps, key=lambda row: row['logical_key']),
        'options': {'experimental_boss_pool': True},
        'boss_contract': {'format': 'bb-boss-pool-plan-v1', 'contracts': contracts},
        'scaling': {'enabled': bool(changes), 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': len(changes), 'changes': changes,
                    'skip_count': len(skips), 'skips': skips},
    }


def assign_donors(seed: str, compatible: Mapping[str, Sequence[str]], *,
                  allow_identity: bool = False) -> dict[str, str]:
    """Find a seeded one-to-one assignment; never silently shrink the roster."""
    arenas = sorted(compatible)
    if not arenas:
        raise ValueError('boss pool is empty')
    donors = set(arenas)
    choices = {}
    rng = random.Random('bb-boss-pool-v1:' + seed)
    for arena in arenas:
        candidates = sorted(set(compatible[arena]))
        if set(candidates) - donors:
            raise ValueError(f'boss pool donor outside the roster: {arena}')
        if not allow_identity:
            candidates = [donor for donor in candidates if donor != arena]
        rng.shuffle(candidates)
        choices[arena] = candidates
    result = {}

    def search(remaining: list[str], used: set[str]) -> bool:
        if not remaining:
            return True
        arena = min(remaining, key=lambda key: (sum(donor not in used for donor in choices[key]), key))
        for donor in choices[arena]:
            if donor in used:
                continue
            result[arena] = donor
            if search([key for key in remaining if key != arena], used | {donor}):
                return True
        result.pop(arena, None)
        return False

    if not search(arenas, set()):
        raise ValueError('reviewed boss compatibility graph has no complete one-to-one assignment')
    return dict(sorted(result.items()))


def _merge_constructor(original: str, variants: list[str]) -> str:
    """Compose nonoverlapping constructor edits against a shared original.

    Each adapter was validated against that original, not another adapter's
    mutated output. Overlapping changes are a conflict requiring an explicit
    shared contract; order-dependent last-writer-wins is never used.
    """
    source = original.splitlines()
    edits: dict[tuple[int, int], tuple[str, ...]] = {}
    for variant in variants:
        output = variant.splitlines()
        for tag, first, last, out_first, out_last in difflib.SequenceMatcher(
                a=source, b=output, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            replacement = tuple(output[out_first:out_last])
            key = (first, last)
            if key in edits:
                if edits[key] != replacement:
                    raise ValueError('conflicting boss constructor edits')
                continue
            for other_first, other_last in edits:
                overlap = max(first, other_first) < min(last, other_last)
                insertion_overlap = (first == last and other_first <= first < other_last
                                     or other_first == other_last and first <= other_first < last)
                if overlap or insertion_overlap:
                    raise ValueError('overlapping boss constructor edits')
            edits[key] = replacement
    for (first, last), replacement in sorted(edits.items(), reverse=True):
        source[first:last] = replacement
    return '\n'.join(source)


def compose_event_patches(original: str, variants: Sequence[str], protected: Sequence[int]) -> str:
    """Merge disjoint adapter event edits, retaining all original progression."""
    before = event_blocks(original)
    changes: dict[int, list[str]] = {}
    for variant in variants:
        blocks = event_blocks(variant)
        if before.keys() - blocks.keys():
            raise ValueError('boss adapter removed original events')
        for key in protected:
            if key not in before or blocks[key] != before[key]:
                raise ValueError(f'boss adapter changed protected completion event {key}')
        for key, block in blocks.items():
            if block != before.get(key):
                changes.setdefault(key, []).append(block)
    edits = {}
    for key, candidates in changes.items():
        distinct = list(dict.fromkeys(candidates))
        if len(distinct) == 1:
            edits[key] = distinct[0]
        elif key == 0:
            edits[key] = _merge_constructor(before[key], distinct)
        else:
            raise ValueError(f'boss adapters overlap event {key}')
    lines = original.splitlines()
    for event in reversed(parse_events(original)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    for key in sorted(edits.keys() - before.keys()):
        lines.extend(['', edits[key]])
    return '\n'.join(lines) + '\n'
