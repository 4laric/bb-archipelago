"""Pinned Blood-starved Beast combat adapter for Lady Maria's destination arena.

Maria keeps the cutscene, fog, completion and Living Failures state.  This
module replaces only the single combat actor's health label, phases, music and
camera with source-pinned BSB behavior.  Static source/build evidence does not
establish runtime arena fit.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .maria_contract import (
    MARIA_ARENA,
    MARIA_PACKAGE,
    _noop,
    _replace_events,
    _replace_once,
    _verify,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
BSB_ACTOR = 2300800
MARIA_ACTOR = 3500800
BSB_COMPLETION = 12301800
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)


@dataclass(frozen=True)
class BsbMariaIds:
    """Project-owned m35 event identities for BSB's two HP phase routines."""

    phase_one: int
    phase_two: int

    def values(self) -> tuple[int, int]:
        return self.phase_one, self.phase_two


DEFAULT_IDS = BsbMariaIds(12991007, 12991008)

# The donor list pins every BSB event which either contributes a copied body or
# supplies the source witness for an adapted destination-owned behavior.
BSB_SOURCE_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}


def _verify_bsb(blocks: Mapping[int, str]) -> None:
    for event_id, digest in BSB_SOURCE_HASHES.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original BSB donor event {event_id}")


def _all_original_numbers() -> set[int]:
    numbers: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        numbers.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return numbers


def _require_ids(ids: BsbMariaIds, destination: str) -> None:
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
        raise ValueError("BSB/Maria ID collides with an original EMEVD literal")


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
            f"BSB Event(0) lacks {count} initializer witnesses for {event_id}"
        )
    return calls


def _remap_initializer(line: str, source_event: int, destination_event: int) -> str:
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
        r"\g<1>" + str(destination_event),
        line,
        count=1,
    )


def _remap_literals(block: str, mapping: Mapping[int, int]) -> str:
    """Map only reviewed actor, event, completion or flag operands."""
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        block,
    )


def _phase_event(
    block: str, source_event: int, destination_event: int, ids: BsbMariaIds
) -> str:
    mapping = {
        BSB_ACTOR: MARIA_ACTOR,
        BSB_COMPLETION: MARIA_ARENA.completion_event,
        source_event: destination_event,
    }
    if source_event == 12304808:
        mapping[12304807] = ids.phase_one
    return _remap_literals(block, mapping)


def _camera_event(block: str) -> str:
    """Map BSB's declared entry flags and lockcam map to Maria's arena facts."""
    block = _replace_once(
        block,
        "    SetNetworkSyncState(Disabled);",
        "    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag(13501800));",
        "completed arena camera guard",
    )
    camera = _replace_once(
        block,
        "$Event(12304804,",
        f"$Event({MARIA_ARENA.lockcam_event},",
        "BSB camera event identity",
    )
    camera = _remap_literals(
        camera,
        {
            12304800: MARIA_ARENA.encounter_start_flag,
            12304801: MARIA_ARENA.co_op_entered_flag,
        },
    )
    return _replace_once(
        camera,
        "SetLockcamSlotNumber(23, 0,",
        "SetLockcamSlotNumber(35, 0,",
        "BSB camera map binding",
    )


def _constructor(arena_zero: str, donor_zero: str, ids: BsbMariaIds) -> str:
    phase_calls = [
        _remap_initializer(
            _initializer_calls(donor_zero, 12304807, 1)[0], 12304807, ids.phase_one
        ),
        _remap_initializer(
            _initializer_calls(donor_zero, 12304808, 1)[0], 12304808, ids.phase_two
        ),
    ]
    anchor = "    $InitializeEvent(0, 13504822);"
    return _replace_once(
        arena_zero,
        anchor,
        anchor + "\n" + "\n".join(phase_calls),
        "Maria combat initializer anchor",
    )


def patch_bsb_at_maria(
    destination: str, donor_source: str, ids: BsbMariaIds = DEFAULT_IDS
) -> str:
    """Attach BSB combat without carrying Maria's opaque 3500801 reference."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, MARIA_PACKAGE.expected, "Maria arena")
    _verify_bsb(donor)
    _require_ids(ids, destination)

    health = _replace_once(
        arena[MARIA_ARENA.health_event],
        "DisplayBossHealthBar(Enabled, 3500800, 0, 452000)",
        "DisplayBossHealthBar(Enabled, 3500800, 0, 209000)",
        "BSB health-bar label",
    )
    health = _replace_once(
        health,
        "    SetCharacterEventTarget(3500800, 3500801);\n",
        "",
        "Maria-only opaque event target",
    )
    music = _replace_once(
        arena[MARIA_ARENA.music_event],
        "chrFlagArea &= CharacterHasEventMessage(3500800, 100);",
        f"chrFlagArea &= EventFlag({ids.phase_one});",
        "BSB first phase music trigger",
    )
    music = _replace_once(
        music,
        "chrFlagArea2 &= CharacterHasEventMessage(3500800, 300);",
        f"chrFlagArea2 &= EventFlag({ids.phase_two});",
        "BSB second phase music trigger",
    )
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        MARIA_ARENA.health_event: health,
        MARIA_ARENA.music_event: music,
        MARIA_ARENA.lockcam_event: _camera_event(donor[12304804]),
        MARIA_ARENA.phase_cleanup_event: _noop(arena[MARIA_ARENA.phase_cleanup_event]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(
            (
                _phase_event(donor[12304807], 12304807, ids.phase_one, ids),
                _phase_event(donor[12304808], 12304808, ids.phase_two, ids),
            )
        )
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.values()):
        raise ValueError("BSB/Maria changed event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"BSB/Maria changed unrelated Maria event {event_id}")
    for event_id in (
        MARIA_ARENA.completion_event,
        MARIA_ARENA.cutscene_entry_event,
        MARIA_ARENA.co_op_restore_event,
    ):
        if output[event_id] != arena[event_id]:
            raise ValueError("BSB/Maria changed Maria progression or cutscene")
    return result


def native_plan_bsb_at_maria(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: BsbMariaIds = DEFAULT_IDS,
) -> dict:
    """Plan a source-pinned BSB c2090 replacement for Maria's single MSB part."""
    bsb = [
        slot
        for slot in slots
        if slot.entity_id == BSB_ACTOR and slot.archetype == BSB_ARCHETYPE
    ]
    maria = [
        slot
        for slot in slots
        if slot.entity_id == MARIA_ACTOR and slot.archetype == MARIA_PACKAGE.archetype
    ]
    if (
        len(bsb) != 2
        or {slot.map_name for slot in bsb} != {"m23_00_00_00", "m23_00_00_01"}
        or any(slot.talk_id != 0 for slot in bsb)
        or len(maria) != 1
        or maria[0].map_name != "m35_00_00_00"
    ):
        raise ValueError(
            "BSB/Maria requires pinned BSB sources and one Maria destination"
        )
    source = next(slot for slot in bsb if slot.map_name == "m23_00_00_00")
    target = maria[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        BSB_ARCHETYPE,
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
            "format": "bb-bsb-maria-contract-v1",
            "arena": "lady-maria",
            "donor": "blood-starved-beast",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [
                MARIA_ARENA.completion_event,
                MARIA_ARENA.cutscene_entry_event,
                MARIA_ARENA.co_op_restore_event,
            ],
            "removed_destination_reference": {
                "event": MARIA_ARENA.health_event,
                "literal": 3500801,
                "witness": "SetCharacterEventTarget(3500800, 3500801)",
                "reason": "Maria-only opaque health target has no BSB source binding",
            },
            "health_bar": {
                "event": MARIA_ARENA.health_event,
                "label": 209000,
                "evidence": "literal DisplayBossHealthBar operand in BSB event 12304802",
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
