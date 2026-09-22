"""Allocate pinned combat-helper clones after the complete primary plan exists."""
from __future__ import annotations

import copy
import json
from collections.abc import Mapping

from .scaling import NPC_CLONE_START, NPC_CLONE_END, free_effect_slot, npc_native_level


def allocate_actor_scaling(plan: dict, npcs: Mapping[int, dict],
                           parents: Mapping[tuple[str, str], str]) -> list[dict]:
    """Return one physical record per explicitly declared combat helper.

    Noncombat additions are outside this ledger. The caller identifies combat
    helpers from reviewed encounter contracts; the native writer verifies their
    source pins, parent effect and free parameter slot against original inputs.
    """
    changes = {row['logical_key']: row for row in plan['scaling']['changes']}
    used = {row['cloned_npc_param_id'] for row in changes.values()}
    next_clone = max(used, default=NPC_CLONE_START - 1) + 1
    additions = {(row['destination_map'], row['destination_part']): row
                 for row in plan.get('boss_actor_additions', [])}
    if len(additions) != len(plan.get('boss_actor_additions', [])):
        raise ValueError('duplicate physical helper addition')
    swaps = {row['logical_key']: row for row in plan['swaps']}
    clones, records = {}, []
    fields = ('source_map', 'source_part', 'source_entity_id', 'source_archetype',
              'source_provenance', 'source_initialization', 'destination_map',
              'destination_part', 'destination_entity_id')
    for destination, parent_key in sorted(parents.items()):
        addition = additions.get(destination)
        change, swap = changes.get(parent_key), swaps.get(parent_key)
        if addition is None or change is None or swap is None:
            raise ValueError('combat helper requires one addition and scaled parent')
        anchor = f"{addition['destination_map']}:{addition['destination_anchor_part']}"
        if anchor not in swap['destination_keys']:
            raise ValueError('combat helper anchor differs from parent placement')
        source_id = addition['source_archetype']['npc_param_id']
        row = npcs.get(source_id)
        if row is None or npc_native_level(row, boss_tiers=True) != change['source_level']:
            raise ValueError('combat helper source tier differs from parent')
        slot = free_effect_slot(row)
        if slot is None:
            raise ValueError('combat helper has no free effect slot')
        if (source_id == change['source_npc_param_id']
                and addition['source_part'] == addition.get('source_anchor_part')):
            raise ValueError('same-NPC helper must be a distinct original actor')
        # Physical map states carry distinct source-part fingerprints. Each is
        # verified independently by native code; identical NPC identities in
        # the same logical fight still share one parameter clone.
        identity = (parent_key, json.dumps(addition['source_archetype'], sort_keys=True), slot)
        if identity not in clones:
            if next_clone > NPC_CLONE_END or next_clone in npcs:
                raise ValueError('combat helper clone range exhausted or occupied')
            clones[identity] = next_clone
            next_clone += 1
        record = {key: copy.deepcopy(addition[key]) for key in fields}
        record.update(parent_logical_key=parent_key,
                      cloned_npc_param_id=clones[identity], sp_effect_slot=slot)
        records.append(record)
    return records
