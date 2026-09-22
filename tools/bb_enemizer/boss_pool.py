"""Deterministic encounter matching and composition of independently reviewed edits.

This module supplies mechanics, not approval for a new donor/arena pairing.
The caller supplies the explicit compatibility graph of reviewed contracts.
"""
from __future__ import annotations

import difflib
import copy
import random
import re
from collections.abc import Mapping, Sequence

from .boss_canary import event_blocks
from .bosses import parse_events
from .scaling import NPC_CLONE_START, NPC_CLONE_END


def combine_native_plans(seed: str, plans: Sequence[dict]) -> dict:
    """Compose canonical pair plans with one shared scaling allocation."""
    if not plans:
        raise ValueError('boss pool has no pair plans')
    swaps, changes, skips, contracts, additions, generators = [], [], [], [], [], []
    added_parts, added_entities = set(), set()
    generator_names, generator_events = set(), set()
    initializations, initialized_parts = [], set()
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
        for addition in plan.get('boss_actor_additions', []):
            map_name = addition['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            part = (map_name, addition['destination_part'])
            entity = (map_name, addition['destination_entity_id'])
            if part in added_parts or entity in added_entities:
                raise ValueError('boss pair plans overlap an added actor')
            added_parts.add(part)
            added_entities.add(entity)
            additions.append(copy.deepcopy(addition))
        for generator in plan.get('boss_generator_additions', []):
            map_name = generator['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            name = (map_name, generator['destination_event'])
            event = (map_name, generator['destination_event_id'])
            entity = (map_name, generator['destination_entity_id'])
            if name in generator_names or event in generator_events or entity in added_entities:
                raise ValueError('boss pair plans overlap an added generator')
            generator_names.add(name)
            generator_events.add(event)
            added_entities.add(entity)
            generators.append(copy.deepcopy(generator))
        for initialization in plan.get('boss_actor_initializations', []):
            map_name = initialization['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            part = (map_name, initialization['destination_part'])
            if part in initialized_parts:
                raise ValueError('boss pair plans overlap a primary actor initialization')
            initialized_parts.add(part)
            initializations.append(copy.deepcopy(initialization))
    changes.sort(key=lambda row: row['logical_key'])
    for index, change in enumerate(changes):
        clone = NPC_CLONE_START + index
        if clone > NPC_CLONE_END:
            raise ValueError('boss pool exhausts NpcParam clone range')
        change['cloned_npc_param_id'] = clone
    accounted = [row['logical_key'] for row in changes + skips]
    if len(accounted) != len(logical) or set(accounted) != logical:
        raise ValueError('boss scaling changes/skips must account for every placement once')
    result = {
        'format': 'bb-enemizer-plan-v2', 'dry_run': True, 'seed': seed,
        'swap_count': len(swaps), 'swaps': sorted(swaps, key=lambda row: row['logical_key']),
        'options': {'experimental_boss_pool': True},
        'boss_contract': {'format': 'bb-boss-pool-plan-v1', 'contracts': contracts},
        'scaling': {'enabled': bool(changes), 'mechanism': 'inferred_static_npc_clone_sp_effect',
                    'change_count': len(changes), 'changes': changes,
                    'skip_count': len(skips), 'skips': skips},
    }
    if additions:
        result['boss_actor_additions'] = sorted(additions, key=lambda row: (
            row['destination_map'], row['destination_entity_id']))
    if generators:
        result['boss_generator_additions'] = sorted(generators, key=lambda row: (
            row['destination_map'], row['destination_event_id']))
    if initializations:
        result['boss_actor_initializations'] = sorted(initializations, key=lambda row: (
            row['destination_map'], row['destination_part']))
    return result


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
    insertions: dict[int, set[tuple[str, ...]]] = {}
    for variant in variants:
        output = variant.splitlines()
        for tag, first, last, out_first, out_last in difflib.SequenceMatcher(
                a=source, b=output, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            replacement = tuple(output[out_first:out_last])
            key = (first, last)
            if first == last:
                insertions.setdefault(first, set()).add(replacement)
                continue
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
    for position, groups in insertions.items():
        if any(first <= position < last for first, last in edits):
            raise ValueError('overlapping boss constructor edits')
        if len(groups) == 1:
            edits[position, position] = next(iter(groups))
            continue
        # Independent combat packages may append at the same constructor site.
        # Only literal initializer calls commute here; arbitrary statements may
        # have ordering dependencies and require an explicit shared contract.
        calls = {}
        lines = []
        for group in sorted(groups):
            for line in group:
                if not line.strip():
                    continue
                match = re.fullmatch(r'\s*\$InitializeEvent\(\s*(\d+)\s*,\s*(\d+)(?:\s*,[^;]*)?\);\s*', line)
                if match is None:
                    raise ValueError('conflicting boss constructor insertions require literal initializers')
                identity = tuple(map(int, match.groups()))
                if identity in calls:
                    if calls[identity].strip() != line.strip():
                        raise ValueError('conflicting boss constructor initializer slot')
                    continue
                calls[identity] = line
                lines.append(line)
        edits[position, position] = tuple(lines)
    for (first, last), replacement in sorted(edits.items(), reverse=True):
        source[first:last] = replacement
    return '\n'.join(source)


def validate_terminal_predicates(before: Mapping[int, str], after: Mapping[int, str],
                                 protected: Sequence[int], terminals: Sequence[dict]) -> None:
    """Permit only an explicit combat-death wait to bridge-flag substitution."""
    seen = set()
    for terminal in terminals:
        event = terminal['event_id']
        actor, bridge = terminal['original_actor'], terminal['bridge_event_id']
        if (event in seen or event not in protected or event not in before or event not in after
                or not isinstance(actor, int) or actor <= 0 or not isinstance(bridge, int) or bridge <= 0
                or bridge in before or bridge not in after):
            raise ValueError('invalid terminal predicate or missing added bridge')
        seen.add(event)
        old = f'WaitFor(CharacterDead({actor}));'
        new = f'WaitFor(EventFlag({bridge}));'
        if before[event].count(old) != 1 or before[event].replace(old, new) != after[event]:
            raise ValueError('terminal adapter changed non-predicate progression')


def compose_event_patches(original: str, variants: Sequence[str], protected: Sequence[int],
                          terminals: Sequence[dict] = ()) -> str:
    """Merge disjoint adapter event edits, retaining all original progression."""
    before = event_blocks(original)
    changes: dict[int, list[str]] = {}
    for variant in variants:
        blocks = event_blocks(variant)
        if before.keys() - blocks.keys():
            raise ValueError('boss adapter removed original events')
        active_terminals = [row for row in terminals if blocks.get(row['event_id']) != before.get(row['event_id'])]
        validate_terminal_predicates(before, blocks, protected, active_terminals)
        terminal_ids = {row['event_id'] for row in active_terminals}
        for key in protected:
            if key in terminal_ids:
                continue
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
    result = '\n'.join(lines) + '\n'
    validate_terminal_predicates(before, event_blocks(result), protected, terminals)
    return result
