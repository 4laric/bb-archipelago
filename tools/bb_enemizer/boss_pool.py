"""Deterministic encounter matching and composition of independently reviewed edits.

This module supplies mechanics, not approval for a new donor/arena pairing.
The caller supplies the explicit compatibility graph of reviewed contracts.
"""
from __future__ import annotations

import difflib
import copy
import random
import re
from collections.abc import Iterable, Mapping, Sequence

from .boss_canary import event_blocks
from .bosses import parse_events
from .scaling import NPC_CLONE_START, NPC_CLONE_END


def _plan_swaps(plan: Mapping, label: str) -> list[dict]:
    """Return independently-owned placements after checking their identity.

    The native writer treats a logical placement and every physical state it
    covers as one unit.  Do this validation before plans are combined: a
    duplicate inside one input must not be hidden by a later set union.
    """
    swaps = plan.get('swaps')
    if not isinstance(swaps, list):
        raise ValueError(f'{label} has no swaps list')
    logical, physical = set(), set()
    output = []
    for swap in swaps:
        if not isinstance(swap, dict):
            raise ValueError(f'{label} has a non-object swap')
        key, destinations = swap.get('logical_key'), swap.get('destination_keys')
        if (not isinstance(key, str) or not key
                or not isinstance(destinations, list) or not destinations
                or any(not isinstance(item, str) or not item for item in destinations)):
            raise ValueError(f'{label} has an invalid swap identity')
        if key in logical:
            raise ValueError(f'{label} repeats a logical destination')
        logical.add(key)
        if len(set(destinations)) != len(destinations) or physical.intersection(destinations):
            raise ValueError(f'{label} repeats a physical destination')
        physical.update(destinations)
        output.append(swap)
    return output


def _scaling_rows(plan: Mapping, swaps: Sequence[dict], label: str) -> tuple[list[dict], list[dict]]:
    """Require every placement to have exactly one declared scaling outcome."""
    scaling = plan.get('scaling')
    if not isinstance(scaling, dict):
        raise ValueError(f'{label} has no scaling section')
    if scaling.get('mechanism') != 'inferred_static_npc_clone_sp_effect':
        raise ValueError(f'{label} has an unsupported scaling mechanism')
    changes, skips = scaling.get('changes'), scaling.get('skips')
    if not isinstance(changes, list) or not isinstance(skips, list):
        raise ValueError(f'{label} has invalid scaling rows')
    if scaling.get('change_count') != len(changes) or scaling.get('skip_count') != len(skips):
        raise ValueError(f'{label} scaling counts differ from rows')
    expected = {swap['logical_key'] for swap in swaps}
    accounted = set()
    for kind, rows in (('change', changes), ('skip', skips)):
        for row in rows:
            key = row.get('logical_key') if isinstance(row, dict) else None
            if not isinstance(key, str) or key not in expected or key in accounted:
                raise ValueError(f'{label} scaling {kind} does not uniquely match a swap')
            accounted.add(key)
    if accounted != expected:
        raise ValueError(f'{label} scaling does not account for every swap')
    enabled = scaling.get('enabled')
    if not isinstance(enabled, bool) or enabled != bool(changes):
        raise ValueError(f'{label} scaling enabled flag disagrees with changes')
    if not enabled and changes:
        raise ValueError(f'{label} disabled scaling has changes')
    return changes, skips


def combine_native_plans(seed: str, plans: Sequence[dict]) -> dict:
    """Compose canonical pair plans with one shared scaling allocation."""
    if not plans:
        raise ValueError('boss pool has no pair plans')
    swaps, changes, skips, contracts, additions, generators, regions, objects = [], [], [], [], [], [], [], []
    region_names = set()
    sfx_additions, ffx_merges, emevd_ffx_requirements = [], {}, []
    emevd_ffx_bindings = set()
    character_ffx_requirements = {}
    character_bank_requirements = {}
    added_parts, added_entities = set(), set()
    generator_names, generator_events = set(), set()
    initializations, initialized_parts = [], set()
    external_references, external_bindings = [], set()
    logical, physical = set(), set()
    # Swaps, actor additions and primary initializations each place or modify
    # an actor on a physical (map, part). Their own per-category sets above
    # only reject a duplicate within the same category, so one pair's swap
    # and a different pair's primary-initialization anchor could silently
    # share a Part -- exactly what crashed BossActorTransplant with "primary
    # actor initialization target does not match source combat archetype"
    # (bb-archipelago#451). A pair's own swap and its own initialization of
    # that same swap are the ordinary, legitimate case (re-stamping dialogue/
    # animation IDs on the actor the pair already swapped), so occupancy is
    # claimed per plan index and only rejected across different plans.
    occupied_parts: dict[tuple[str, str], int] = {}

    def _claim(parts: Iterable[tuple[str, str]], plan_index: int) -> None:
        for part in parts:
            owner = occupied_parts.get(part)
            if owner is not None and owner != plan_index:
                raise ValueError('boss pair plans overlap a physical actor placement')
            occupied_parts[part] = plan_index

    for plan_index, plan in enumerate(plans):
        if plan.get('format') != 'bb-enemizer-plan-v2' or plan.get('seed') != seed or plan.get('dry_run') is not True:
            raise ValueError('boss pair plan identity differs')
        plan_swaps = _plan_swaps(plan, 'boss pair plan')
        plan_changes, plan_skips = _scaling_rows(plan, plan_swaps, 'boss pair plan')
        for swap in plan_swaps:
            if swap['logical_key'] in logical or physical.intersection(swap['destination_keys']):
                raise ValueError('boss pair plans overlap a destination')
            logical.add(swap['logical_key'])
            physical.update(swap['destination_keys'])
            _claim((tuple(key.split(':', 1)) for key in swap['destination_keys']), plan_index)
            swaps.append(copy.deepcopy(swap))
        changes.extend(copy.deepcopy(plan_changes))
        skips.extend(copy.deepcopy(plan_skips))
        contracts.append(copy.deepcopy(plan['boss_contract']))
        character_bindings = set()
        for requirement in plan.get('boss_character_ffx_requirements', []):
            binding = (requirement['source_map'], requirement['source_part'],
                       requirement['source_entity_id'])
            if binding in character_bindings:
                raise ValueError('boss pair repeats a character FFX actor binding')
            character_bindings.add(binding)
            previous = character_ffx_requirements.get(binding)
            if previous is not None and previous != requirement:
                raise ValueError('boss pair plans disagree on character FFX provenance')
            character_ffx_requirements[binding] = copy.deepcopy(requirement)
        for requirement in plan.get('boss_character_ffx_bank_requirements', []):
            binding = (requirement['destination_map'], requirement['destination_part'],
                       requirement['destination_entity_id'])
            if binding in character_bank_requirements:
                raise ValueError('boss pair plans overlap a character FFX bank destination')
            character_bank_requirements[binding] = copy.deepcopy(requirement)
        for reference in plan.get('boss_external_references', []):
            binding = (reference['destination_event_file'], reference['destination_event_id'],
                       reference['destination_actor'], reference['entity_id'])
            if binding in external_bindings:
                raise ValueError('boss pair plans overlap an external reference')
            external_bindings.add(binding)
            external_references.append(copy.deepcopy(reference))
        for addition in plan.get('boss_actor_additions', []):
            map_name = addition['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            part = (map_name, addition['destination_part'])
            entity = (map_name, addition['destination_entity_id'])
            if part in added_parts or entity in added_entities:
                raise ValueError('boss pair plans overlap an added actor')
            added_parts.add(part)
            added_entities.add(entity)
            _claim((part,), plan_index)
            additions.append(copy.deepcopy(addition))
        for addition in plan.get('boss_object_additions', []):
            map_name = addition['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            part = (map_name, addition['destination_part'])
            entity = (map_name, addition['destination_entity_id'])
            if part in added_parts or entity in added_entities:
                raise ValueError('boss pair plans overlap an added object')
            added_parts.add(part)
            added_entities.add(entity)
            objects.append(copy.deepcopy(addition))
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
        for effect in plan.get('boss_sfx_additions', []):
            map_name = effect['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            name = (map_name, effect['destination_event'])
            event = (map_name, effect['destination_event_id'])
            entity = (map_name, effect['destination_entity_id'])
            if name in generator_names or event in generator_events or entity in added_entities:
                raise ValueError('boss pair plans overlap an added SFX')
            generator_names.add(name)
            generator_events.add(event)
            added_entities.add(entity)
            sfx_additions.append(copy.deepcopy(effect))
        for merge in plan.get('boss_ffx_merges', []):
            key = (merge['source_file'], merge['destination_file'])
            if key in ffx_merges:
                previous = ffx_merges[key]
                if ({k: v for k, v in previous.items() if k != 'required_effect_ids'}
                        != {k: v for k, v in merge.items() if k != 'required_effect_ids'}):
                    raise ValueError('boss pair plans disagree on FFX binder provenance')
                previous['required_effect_ids'] = sorted(set(previous['required_effect_ids'])
                                                        | set(merge['required_effect_ids']))
            else:
                ffx_merges[key] = copy.deepcopy(merge)
        for requirement in plan.get('boss_emevd_ffx_requirements', []):
            binding = (requirement['source_event_file'], requirement['source_event_id'],
                       requirement['destination_event_file'], requirement['destination_event_id'],
                       requirement['effect_id'])
            if binding in emevd_ffx_bindings:
                raise ValueError('boss pair plans overlap an EMEVD FFX requirement')
            emevd_ffx_bindings.add(binding)
            emevd_ffx_requirements.append(copy.deepcopy(requirement))
        for region in plan.get('boss_region_additions', []):
            map_name = region['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            name = (map_name, region['destination_region'])
            entity = (map_name, region['destination_entity_id'])
            if name in region_names or (entity[1] >= 0 and entity in added_entities):
                raise ValueError('boss pair plans overlap an added region')
            region_names.add(name)
            if entity[1] >= 0:
                added_entities.add(entity)
            regions.append(copy.deepcopy(region))
        for initialization in plan.get('boss_actor_initializations', []):
            map_name = initialization['destination_map'].removesuffix('.dcx').removesuffix('.msb')
            part = (map_name, initialization['destination_part'])
            if part in initialized_parts:
                raise ValueError('boss pair plans overlap a primary actor initialization')
            initialized_parts.add(part)
            _claim((part,), plan_index)
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
    if objects:
        result['boss_object_additions'] = sorted(objects, key=lambda row: (
            row['destination_map'], row['destination_part']))
    if generators:
        result['boss_generator_additions'] = sorted(generators, key=lambda row: (
            row['destination_map'], row['destination_event_id']))
    if sfx_additions:
        result['boss_sfx_additions'] = sorted(sfx_additions, key=lambda row: (
            row['destination_map'], row['destination_event_id']))
    if ffx_merges:
        result['boss_ffx_merges'] = [ffx_merges[key] for key in sorted(ffx_merges)]
    if character_ffx_requirements:
        result['boss_character_ffx_requirements'] = [
            character_ffx_requirements[key] for key in sorted(character_ffx_requirements)]
    if character_bank_requirements:
        result['boss_character_ffx_bank_requirements'] = [
            character_bank_requirements[key] for key in sorted(character_bank_requirements)]
    if emevd_ffx_requirements:
        result['boss_emevd_ffx_requirements'] = sorted(emevd_ffx_requirements, key=lambda row: (
            row['source_event_file'], row['source_event_id'], row['destination_event_file'],
            row['destination_event_id'], row['effect_id']))
    if regions:
        result['boss_region_additions'] = sorted(regions, key=lambda row: (
            row['destination_map'], row['destination_region']))
    if initializations:
        result['boss_actor_initializations'] = sorted(initializations, key=lambda row: (
            row['destination_map'], row['destination_part']))
    if external_references:
        result['boss_external_references'] = sorted(external_references, key=lambda row: (
            row['destination_event_file'], row['destination_event_id'], row['entity_id']))
    return result


def combine_ordinary_and_boss_plans(ordinary_plan: Mapping, boss_plans: Sequence[dict]) -> dict:
    """Make one native manifest from ordinary placements and reviewed bosses.

    Both planners historically allocate from the same NpcParam clone range.
    This is the only composition boundary for a player build: it rejects
    overlapping placements, requires an explicit scaling outcome for every
    combined swap, and rewrites clone IDs once over the complete change set.
    The ordinary manifest owns its seed, diagnostics, and player-selected
    options; boss pair plans add only reviewed encounter metadata.
    """
    if (ordinary_plan.get('format') != 'bb-enemizer-plan-v2'
            or ordinary_plan.get('dry_run') is not True):
        raise ValueError('ordinary plan is not a dry-run bb-enemizer-plan-v2 manifest')
    seed = ordinary_plan.get('seed')
    if not isinstance(seed, str) or not seed:
        raise ValueError('ordinary plan has no seed')
    options = ordinary_plan.get('options')
    if not isinstance(options, Mapping):
        raise ValueError('ordinary plan has invalid options')
    forbidden = {
        'boss_adapter', 'boss_contract', 'boss_encounters', 'boss_actor_additions',
        'boss_actor_initializations', 'boss_generator_additions', 'boss_region_additions',
        'boss_object_additions', 'boss_sfx_additions', 'boss_ffx_merges',
        'boss_emevd_ffx_requirements', 'boss_character_ffx_requirements',
        'boss_character_ffx_bank_requirements', 'boss_external_references',
    }
    present = forbidden.intersection(ordinary_plan)
    if present:
        raise ValueError('ordinary plan already carries boss metadata: ' + ', '.join(sorted(present)))

    ordinary_swaps = _plan_swaps(ordinary_plan, 'ordinary plan')
    if not ordinary_swaps:
        raise ValueError('ordinary plan has no swaps')
    ordinary_changes, ordinary_skips = _scaling_rows(
        ordinary_plan, ordinary_swaps, 'ordinary plan')
    bosses = combine_native_plans(seed, boss_plans)
    boss_swaps = _plan_swaps(bosses, 'combined boss plan')
    boss_changes, boss_skips = _scaling_rows(bosses, boss_swaps, 'combined boss plan')

    ordinary_physical = {
        destination for swap in ordinary_swaps for destination in swap['destination_keys']
    }
    boss_logical = {swap['logical_key'] for swap in boss_swaps}
    if {swap['logical_key'] for swap in ordinary_swaps}.intersection(boss_logical):
        raise ValueError('ordinary and boss plans overlap a logical destination')
    if ordinary_physical.intersection(
            destination for swap in boss_swaps for destination in swap['destination_keys']):
        raise ValueError('ordinary and boss plans overlap a physical destination')

    # Copy the whole ordinary document so inventory, rejection evidence and
    # future ordinary-only fields survive verbatim.  The three fields below
    # are the single shared native allocation ledger.
    result = copy.deepcopy(dict(ordinary_plan))
    swaps = [*ordinary_swaps, *boss_swaps]
    changes = [*ordinary_changes, *boss_changes]
    skips = [*ordinary_skips, *boss_skips]
    changes.sort(key=lambda row: row['logical_key'])
    skips.sort(key=lambda row: row['logical_key'])
    for index, change in enumerate(changes):
        clone = NPC_CLONE_START + index
        if clone > NPC_CLONE_END:
            raise ValueError('combined plan exhausts NpcParam clone range')
        change = copy.deepcopy(change)
        change['cloned_npc_param_id'] = clone
        changes[index] = change
    result['swap_count'] = len(swaps)
    result['swaps'] = [copy.deepcopy(swap) for swap in sorted(swaps, key=lambda row: row['logical_key'])]
    result['scaling'] = {
        'enabled': bool(changes),
        'mechanism': 'inferred_static_npc_clone_sp_effect',
        'change_count': len(changes),
        'changes': changes,
        'skip_count': len(skips),
        'skips': [copy.deepcopy(skip) for skip in skips],
    }
    result['boss_contract'] = copy.deepcopy(bosses['boss_contract'])
    for field in ('boss_actor_additions', 'boss_generator_additions', 'boss_region_additions', 'boss_object_additions',
                  'boss_actor_initializations', 'boss_sfx_additions', 'boss_ffx_merges',
                  'boss_emevd_ffx_requirements', 'boss_character_ffx_requirements',
                  'boss_character_ffx_bank_requirements', 'boss_external_references'):
        if field in bosses:
            result[field] = copy.deepcopy(bosses[field])
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

    def can_complete(remaining: list[str], used: set[str]) -> bool:
        # A donor can be reachable from every remaining arena yet still leave
        # a subset with too few distinct donors. Detect that with an augmenting
        # matching instead of enumerating every doomed seeded permutation.
        # This only prunes impossible branches; search keeps its original RNG
        # order and therefore its existing seed-to-assignment behavior.
        owners: dict[str, str] = {}

        def augment(arena: str, visited: set[str]) -> bool:
            for donor in choices[arena]:
                if donor in used or donor in visited:
                    continue
                visited.add(donor)
                owner = owners.get(donor)
                if owner is None or augment(owner, visited):
                    owners[donor] = arena
                    return True
            return False

        return all(augment(arena, set()) for arena in remaining)

    def search(remaining: list[str], used: set[str]) -> bool:
        if not remaining:
            return True
        if not can_complete(remaining, used):
            return False
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
        # An insertion immediately before a removed/replaced range is adjacent,
        # not overlapping. Reverse application below edits the range first and
        # then inserts at that boundary, independently of adapter order.
        if any(first < position < last for first, last in edits):
            raise ValueError('overlapping boss constructor edits')
        if len(groups) == 1:
            edits[position, position] = next(iter(groups))
            continue
        # Per-load readiness events must be reset before any constructor
        # initializer. Independent literal OFF writes at that leading boundary
        # commute; do not extend this rule to mixed statements or later sites.
        resets = [re.fullmatch(r'\s*SetEventFlag\(\s*(\d+)\s*,\s*OFF\);\s*', line)
                  for group in groups for line in group if line.strip()]
        if position == 1 and resets and all(reset is not None for reset in resets):
            flags = sorted({int(reset[1]) for reset in resets})
            if any(flag <= 0 for flag in flags):
                raise ValueError('constructor readiness reset requires positive flag IDs')
            edits[position, position] = tuple(f'    SetEventFlag({flag}, OFF);' for flag in flags)
            continue
        # Independent combat packages may append at the same constructor site.
        # Literal initializers and distinct virtual bullet-owner declarations
        # can coexist. Preserve each package's instruction order; arbitrary
        # statements still require an explicit shared contract.
        calls = {}
        owners = set()
        existing_owners = set(map(int, re.findall(r'CreateBulletOwner\(\s*(\d+)\s*\)', original)))
        lines = []
        for group in sorted(groups):
            for line in group:
                if not line.strip():
                    continue
                owner = re.fullmatch(r'\s*CreateBulletOwner\(\s*(\d+)\s*\);\s*', line)
                if owner is not None:
                    entity = int(owner[1])
                    if entity <= 0 or entity in owners or entity in existing_owners:
                        raise ValueError('conflicting boss constructor bullet owner')
                    owners.add(entity)
                    lines.append(line)
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
