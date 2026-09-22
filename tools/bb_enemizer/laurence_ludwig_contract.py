"""Pinned Laurence combat adapter for Ludwig's two-body destination arena.

The destination keeps Ludwig's terminal and progression while its combat becomes
the single Laurence actor.  Laurence's original m34 combat bodies are copied to
project-owned event IDs so the concurrent Laurence encounter remains intact.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .laurence_contract import LAURENCE, PINS as LAURENCE_SOURCE_HASHES
from .ludwig_arena import (
    BUNDLE,
    LUDWIG_ARENA_HASHES,
    LUDWIG_ARCHETYPE,
    LUDWIG_COMPLETION,
    LUDWIG_PHASE_TWO,
    LUDWIG_PRIMARY,
    _end,
    _health as _single_body_health,
    _replace_events,
    _replace_once,
    _verify,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)
LAURENCE_COMPLETION = 13401850


@dataclass(frozen=True)
class LaurenceLudwigIds:
    """Project-owned copies of Laurence's limb, hitmask and cleanup routines."""

    limbs: int
    hitmask: int
    phase_two_cleanup: int

    def values(self) -> tuple[int, int, int]:
        return self.limbs, self.hitmask, self.phase_two_cleanup


DEFAULT_IDS = LaurenceLudwigIds(12991270, 12991275, 12991276)


def _all_original_numbers() -> set[int]:
    numbers: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        numbers.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return numbers


def _require_ids(ids: LaurenceLudwigIds, destination: str) -> None:
    values = ids.values()
    destination_numbers = {
        int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)
    }
    if (
        len(set(values)) != len(values)
        or any(value <= 0 for value in values)
        or set(values) & destination_numbers
        or set(values) & _all_original_numbers()
    ):
        raise ValueError("Laurence/Ludwig ID collides with an original EMEVD literal")


def _initializer_calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
            line,
        )
    ]
    if len(calls) != count:
        raise ValueError(
            f"Laurence Event(0) lacks {count} initializer witnesses for {event_id}"
        )
    return calls


def _remap_initializer(line: str, source_event: int, destination_event: int) -> str:
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
        r"\g<1>" + str(destination_event),
        line,
        count=1,
    )


def _constructor(event_zero: str, ids: LaurenceLudwigIds) -> str:
    limbs = [
        _remap_initializer(line, 13404870, ids.limbs)
        for line in _initializer_calls(event_zero, 13404870, 5)
    ]
    hitmask = [
        _remap_initializer(line, 13404875, ids.hitmask)
        for line in _initializer_calls(event_zero, 13404875, 1)
    ]
    anchor = "    $InitializeEvent(0, 13404841);"
    return _replace_once(
        event_zero,
        anchor,
        anchor
        + "\n"
        + "\n".join((*limbs, *hitmask))
        + f"\n    $InitializeEvent(0, {ids.phase_two_cleanup});",
        "Ludwig combat initializer anchor",
    )


def _remap_laurence_literals(
    block: str, source_event: int, destination_event: int
) -> str:
    mapping = {
        LAURENCE: LUDWIG_PRIMARY,
        LAURENCE_COMPLETION: LUDWIG_COMPLETION,
        source_event: destination_event,
    }
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        block,
    )


def _laurence_camera(block: str) -> str:
    return _remap_laurence_literals(block, 13404854, 13404804)


def _copied_laurence_event(
    block: str, source_event: int, destination_event: int
) -> str:
    return _remap_laurence_literals(block, source_event, destination_event)


def _health(original: str) -> str:
    """Reuse the pinned Ludwig single-body lifecycle with Laurence's label."""
    return _replace_once(
        _single_body_health(original),
        "DisplayBossHealthBar(Enabled, 3400800, 0, 500000)",
        "DisplayBossHealthBar(Enabled, 3400800, 0, 450000)",
        "Laurence health-bar label",
    )


def _phase_two_cleanup(ids: LaurenceLudwigIds) -> str:
    return f"""$Event({ids.phase_two_cleanup}, Restart, function() {{
    ChangeCharacterEnableState(3400801, Disabled);
    EndIf(EventFlag(13401800));
    WaitFor(EventFlag(13401800));
    ChangeCharacterEnableState(3400801, Disabled);
    ForceCharacterDeath(3400801, false);
}});"""


def patch_laurence_at_ludwig(
    destination: str, laurence_source: str, ids: LaurenceLudwigIds = DEFAULT_IDS
) -> str:
    """Copy Laurence combat into Ludwig's arena without mutating Laurence events."""
    arena, donor = event_blocks(destination), event_blocks(laurence_source)
    _verify(arena, LUDWIG_ARENA_HASHES, "Ludwig arena")
    _verify(donor, LAURENCE_SOURCE_HASHES, "Laurence donor")
    _require_ids(ids, destination)

    music = _replace_once(
        arena[13404803],
        "flagArea2 &= EventFlag(13404824);",
        "flagArea2 &= CharacterHasEventMessage(3400800, 400);",
        "Laurence phase music trigger",
    )
    edits = {
        0: _constructor(arena[0], ids),
        13404802: _health(arena[13404802]),
        13404803: music,
        13404804: _laurence_camera(donor[13404854]),
        13404820: _end(arena[13404820]),
        13404821: _end(arena[13404821]),
        13404822: _end(arena[13404822]),
        13404823: _end(arena[13404823]),
        13404824: _end(arena[13404824]),
        13404825: _end(arena[13404825]),
        13404830: _end(arena[13404830]),
        13404835: _end(arena[13404835]),
        13404840: _end(arena[13404840]),
        13404841: _end(arena[13404841]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(
            (
                _copied_laurence_event(donor[13404870], 13404870, ids.limbs),
                _copied_laurence_event(donor[13404875], 13404875, ids.hitmask),
                _phase_two_cleanup(ids),
            )
        )
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.values()):
        raise ValueError("Laurence/Ludwig changed event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Laurence/Ludwig changed unrelated m34 event {event_id}")
    for event_id in (LUDWIG_COMPLETION, LAURENCE_COMPLETION):
        if output[event_id] != arena[event_id]:
            raise ValueError(
                "Laurence/Ludwig changed destination completion progression"
            )
    return result


def native_plan_laurence_at_ludwig(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LaurenceLudwigIds = DEFAULT_IDS,
) -> dict:
    """Plan the native c4500 primary replacement in Ludwig's single m34 part."""
    laurence = [
        slot
        for slot in slots
        if slot.entity_id == LAURENCE and slot.archetype == LAURENCE_ARCHETYPE
    ]
    ludwig = [
        slot
        for slot in slots
        if slot.entity_id == LUDWIG_PRIMARY and slot.archetype == LUDWIG_ARCHETYPE
    ]
    if (
        len(laurence) != 1
        or laurence[0].map_name != "m34_00_00_00"
        or len(ludwig) != 1
        or ludwig[0].map_name != "m34_00_00_00"
    ):
        raise ValueError(
            "Laurence/Ludwig requires exact original m34 source and target"
        )
    source = laurence[0]
    target = ludwig[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        LAURENCE_ARCHETYPE,
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [target], dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-laurence-ludwig-contract-v1",
            "arena": "ludwig",
            "donor": "laurence",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [LUDWIG_COMPLETION, LAURENCE_COMPLETION],
            "health_bar": {
                "event": 13404802,
                "label": 450000,
                "evidence": "literal DisplayBossHealthBar operand in Laurence event 13404852",
            },
            "runtime_status": "unobserved arena fit",
        },
        "primary_init_source_bindings": [
            {
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_talk_id": source.talk_id,
                "destination_map": target.map_name,
                "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
                "destination_original_talk_id": target.talk_id,
                "required_native_fields": [
                    "talk_id",
                    "unk_t18",
                    "init_anim_id",
                    "damage_anim_id",
                    "provenance",
                ],
            }
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
