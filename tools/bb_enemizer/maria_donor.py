"""Reusable Lady Maria combat donor for one-actor progression arenas.

The destination keeps its entry trigger, fog, music objects, completion event,
rewards, and map geometry.  Maria contributes her complete health/network
routine, lock camera, and message-20 SpEffect cleanup.  Her unplaced 3500801
event target remains an opaque literal and is declared in the emitted native
contract; it is never materialized as an actor.
"""
from __future__ import annotations

import re
from functools import cache
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from tools.bb_inputs import read_prefix

from .boss_contracts import (
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    BSB_ARENA,
    CLERIC_ARENA,
    EBRIETAS_ARENA,
    PAARL_ARENA,
    ArenaContract,
)
from .maria_contract import (
    MARIA_ARENA,
    MARIA_EVENT_TARGET_REFERENCE,
    MARIA_PACKAGE,
    MARIA_PATCH_EXPECTED,
    _noop,
    _replace_events,
    _replace_once,
    _verify,
    event_blocks,
)
from .model import Slot, Swap
from .scaling import plan_scaling


# Capability inventory for callers and coverage reports.  The patcher itself
# is parameterized by ArenaContract and does not branch on this tuple.
SUPPORTED_MARIA_ARENAS = (
    CLERIC_ARENA,
    BSB_ARENA,
    PAARL_ARENA,
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    EBRIETAS_ARENA,
)
BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"


@dataclass(frozen=True)
class MariaArenaAllocation:
    """Caller-owned event/flag allocation, checked before source mutation."""

    phase_cleanup_event: int
    health_initialized_flag: int


def _numeric_literals(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


def validate_maria_allocation(allocation: MariaArenaAllocation,
                              original_sources: Iterable[str]) -> None:
    """Reject nonpositive, duplicate, or source-colliding project IDs.

    Builders can pass the complete original EMEVD corpus here.  The patcher
    always calls it for the destination it is about to mutate.
    """
    values = (allocation.phase_cleanup_event, allocation.health_initialized_flag)
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError("Maria allocation requires two distinct positive IDs")
    collisions: set[int] = set()
    for source in original_sources:
        collisions.update(set(values).intersection(_numeric_literals(source)))
    if collisions:
        joined = ", ".join(str(value) for value in sorted(collisions))
        raise ValueError(f"Maria allocation collides with original literal(s): {joined}")


@cache
def _original_game_literals() -> frozenset[int]:
    """Numeric boundary from every bundled original EMEVD and mined MSBB row."""
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numeric_literals(body.decode("utf-8-sig")))
    return frozenset(values)


def _require_allocation(allocation: MariaArenaAllocation) -> None:
    values = (allocation.phase_cleanup_event, allocation.health_initialized_flag)
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError("Maria allocation requires two distinct positive IDs")
    if set(values) & _original_game_literals():
        raise ValueError("Maria allocation collides with original EMEVD/MSBB corpus")


def _numbers(text: str, replacements: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(replacements.get(int(match[0]), int(match[0]))),
        text,
    )


def _destination_health_telemetry(source_health: str, destination_health: str) -> str:
    """Keep destination playlog/measurement ownership in the copied health body."""
    result = source_health
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line for line in source_health.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        destination_lines = [
            line for line in destination_health.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(
                f"health telemetry requires one source and destination {instruction} witness"
            )
        result = _replace_once(
            result,
            source_lines[0],
            destination_lines[0],
            f"destination-owned health {instruction}",
        )
    return result


def _mark_existing_entry_notification(block: str,
                                      allocation: MariaArenaAllocation) -> str:
    """Bind Maria's notification guard only when the arena already notified."""
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(
        witness,
        witness + f"        SetEventFlag({allocation.health_initialized_flag}, ON);\n",
        1,
    )


def _activation_without_destination_animations(arena: ArenaContract, block: str) -> str:
    """Retain entry triggers/geometry and remove model-specific wake-up state."""
    pattern = re.compile(
        rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", re.MULTILINE
    )
    result, count = pattern.subn("", block)
    if count == 0:
        raise ValueError(f"{arena.key} activation lacks a destination animation witness")
    # Paarl and Amygdala wrap their animation sequence in temporary collision,
    # gravity, and invincibility state. Keep invincibility around the arena's
    # entry predicate, but remove the animation delays and model-only movement
    # state. The original ordering then disables invincibility immediately
    # after the predicate succeeds.
    if f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result:
        if result.count(f"    SetCharacterInvincibility({arena.actor}, Enabled);\n") != 1:
            raise ValueError("entry invincibility-enable witness is not unique")
        if result.count(f"    SetCharacterInvincibility({arena.actor}, Disabled);\n") != 1:
            raise ValueError("entry invincibility-disable witness is not unique")
        if f"    SetCharacterMaphits({arena.actor}, true);\n" in result:
            for instruction in (
                f"    SetCharacterMaphits({arena.actor}, true);\n",
                f"    SetCharacterMaphits({arena.actor}, false);\n",
                f"    SetCharacterGravity({arena.actor}, Disabled);\n",
                f"    SetCharacterGravity({arena.actor}, Enabled);\n",
                "    WaitFixedTimeFrames(30);\n",
                "    WaitFixedTimeFrames(160);\n",
            ):
                result = _replace_once(result, instruction, "", "entry animation state")
        else:
            result = _replace_once(
                result, "    WaitFixedTimeFrames(70);\n", "", "entry animation delay"
            )
    # Ebrietas's damage predicate requires the actor to be hittable, while
    # immortality prevents that trigger damage from killing Maria. Retain the
    # protection pair around WaitFor and remove only the model-specific effect.
    if f"    SetCharacterImmortality({arena.actor}, Enabled);\n" in result:
        if result.count(f"    SetCharacterImmortality({arena.actor}, Enabled);\n") != 1:
            raise ValueError("entry immortality-enable witness is not unique")
        if result.count(f"    SetCharacterImmortality({arena.actor}, Disabled);\n") != 1:
            raise ValueError("entry immortality-disable witness is not unique")
        for instruction in (
            f"    SetSpEffect({arena.actor}, 5647, false);\n",
            f"    ClearSpEffect({arena.actor}, 5647);\n",
        ):
            result = _replace_once(result, instruction, "", "entry immortality state")
    return result


def _destination_music(arena: ArenaContract, block: str) -> str:
    """Keep destination sounds/regions and wait for Maria's phase-one message."""
    if arena.phase_music_message is None:
        old = f"flagArea2 &= EventFlag({arena.part_routine_event});"
        new = f"flagArea2 &= CharacterHasEventMessage({arena.actor}, 100);"
        return _replace_once(block, old, new, "destination music phase flag")
    witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    if block.count(witness) != 1:
        raise ValueError(f"{arena.key} music lacks its declared phase-message witness")
    if arena.phase_music_message == 100:
        return block
    return block.replace(witness, f"CharacterHasEventMessage({arena.actor}, 100)", 1)


def _append_cleanup_initializer(arena: ArenaContract, event_zero: str,
                                allocation: MariaArenaAllocation) -> str:
    anchors = [
        f"    $InitializeEvent(0, {event_id});"
        for event_id in reversed(arena.phase_slots)
        if event_zero.count(f"    $InitializeEvent(0, {event_id});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} has no unique zero-argument phase initializer")
    anchor = anchors[0]
    return _replace_once(
        event_zero,
        anchor,
        anchor + f"\n    $InitializeEvent(0, {allocation.phase_cleanup_event});",
        f"{arena.key} phase initializer anchor",
    )


def maria_donor_contract(arena: ArenaContract,
                         allocation: MariaArenaAllocation) -> dict:
    """Describe the exact source bodies and native witnesses used by a swap."""
    _require_allocation(allocation)
    copied = (
        (MARIA_ARENA.health_event, arena.health_bar_event),
        (MARIA_ARENA.lockcam_event, arena.lockcam_event),
        (MARIA_ARENA.phase_cleanup_event, allocation.phase_cleanup_event),
    )
    retired = {
        *arena.phase_slots,
        arena.part_routine_event,
        *(() if arena.cloth_routine_event is None else (arena.cloth_routine_event,)),
        *(() if arena.attachment_anchor_event is None else (arena.attachment_anchor_event,)),
    }
    exact_preserved = [arena.completion_event]
    if arena.co_op_entry_event not in retired:
        exact_preserved.append(arena.co_op_entry_event)
    return {
        "format": "bb-maria-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": MARIA_PACKAGE.key,
        "allocation": asdict(allocation),
        "preserved_destination_events": exact_preserved,
        "adapted_destination_events": [
            arena.activation_event,
            arena.health_bar_event,
            arena.music_event,
            arena.lockcam_event,
        ],
        "source_owned_not_copied": [
            MARIA_ARENA.completion_event,
            MARIA_ARENA.cutscene_entry_event,
            MARIA_ARENA.co_op_restore_event,
            MARIA_ARENA.host_fog_event,
            MARIA_ARENA.guest_fog_event,
            MARIA_ARENA.music_event,
            MARIA_ARENA.music_cleanup_event,
            *MARIA_ARENA.source_reward_flags,
        ],
        "copied_source_events": [
            {
                "source_event": source_event,
                "destination_event": destination_event,
                "expected_source_sha256": MARIA_PACKAGE.expected[source_event],
                "allowed_source_sha256s": sorted({
                    MARIA_PACKAGE.expected[source_event],
                    *(() if source_event not in MARIA_PATCH_EXPECTED
                      else (MARIA_PATCH_EXPECTED[source_event],)),
                }),
            }
            for source_event, destination_event in copied
        ],
        "destination_owned_health_telemetry": {
            "event": arena.health_bar_event,
            "instructions": ["CreatePlaylog", "StartTimeMeasurement"],
            "reason": "destination completion owns the matching measurement lifecycle",
        },
        "retired_destination_controllers": sorted(retired),
        "attachments": [{
            "source_event": MARIA_ARENA.phase_cleanup_event,
            "destination_event": allocation.phase_cleanup_event,
            "initializers": [
                asdict(binding) for binding in MARIA_PACKAGE.attachments[0].initializers
            ],
        }],
        "opaque_external_references": [{
            **asdict(MARIA_EVENT_TARGET_REFERENCE),
            "destination_event": arena.health_bar_event,
            "destination_actor": arena.actor,
        }],
        "behavioral_unknown": "3500801 remains opaque; static effect is unobserved",
    }


def patch_maria_donor(arena: ArenaContract, destination: str, donor_source: str,
                      allocation: MariaArenaAllocation) -> str:
    """Install Maria combat in an ArenaContract without moving progression."""
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, MARIA_PACKAGE.expected, "Lady Maria donor")
    _require_allocation(allocation)
    validate_maria_allocation(allocation, (destination,))
    if not arena.phase_slots:
        raise ValueError(f"{arena.key} has no phase initializer anchor")

    health = _numbers(donor[MARIA_ARENA.health_event], {
        MARIA_ARENA.health_event: arena.health_bar_event,
        MARIA_PACKAGE.actor: arena.actor,
        MARIA_ARENA.completion_event: arena.completion_event,
        MARIA_ARENA.encounter_start_flag: arena.start_flag,
        MARIA_ARENA.health_started_flag: allocation.health_initialized_flag,
    })
    health = _destination_health_telemetry(
        health, original[arena.health_bar_event]
    )
    lockcam = _numbers(donor[MARIA_ARENA.lockcam_event], {
        MARIA_ARENA.lockcam_event: arena.lockcam_event,
        MARIA_PACKAGE.actor: arena.actor,
        MARIA_ARENA.completion_event: arena.completion_event,
    })
    source_camera = (
        f"SetLockcamSlotNumber({MARIA_PACKAGE.lockcam_map}, "
        f"{MARIA_PACKAGE.lockcam_subarea},"
    )
    destination_camera = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if lockcam.count(source_camera) != 2:
        raise ValueError("Maria lockcam lacks the exact two-call source witness")
    lockcam = lockcam.replace(source_camera, destination_camera)
    cleanup = _numbers(donor[MARIA_ARENA.phase_cleanup_event], {
        MARIA_ARENA.phase_cleanup_event: allocation.phase_cleanup_event,
        MARIA_PACKAGE.actor: arena.actor,
        MARIA_ARENA.completion_event: arena.completion_event,
    })

    retired = {
        *arena.phase_slots,
        arena.part_routine_event,
        *(() if arena.cloth_routine_event is None else (arena.cloth_routine_event,)),
        *(() if arena.attachment_anchor_event is None else (arena.attachment_anchor_event,)),
    }
    edits = {event_id: _noop(original[event_id]) for event_id in retired}
    activation = _activation_without_destination_animations(
        arena, original[arena.activation_event]
    )
    activation = _mark_existing_entry_notification(activation, allocation)
    edits.update({
        0: _append_cleanup_initializer(arena, original[0], allocation),
        arena.activation_event: activation,
        arena.health_bar_event: health,
        arena.music_event: _destination_music(arena, original[arena.music_event]),
        arena.lockcam_event: lockcam,
    })
    result = _replace_events(destination, edits).rstrip() + "\n\n" + cleanup + "\n"
    output = event_blocks(result)
    if set(output) != set(original) | {allocation.phase_cleanup_event}:
        raise ValueError("Maria donor adapter changed an unexpected event identity")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"Maria donor adapter changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Maria donor adapter changed destination completion/progression")
    return result


def native_plan_maria_donor(arena: ArenaContract, slots: list[Slot],
                            npcs: Mapping[int, dict], effects: Mapping[int, dict],
                            allocation: MariaArenaAllocation, seed: str) -> dict:
    """Build one native swap with Maria's exact original MSB initialization."""
    _require_allocation(allocation)
    destinations = [
        slot for slot in slots
        if slot.entity_id == arena.actor and slot.archetype == arena.archetype
    ]
    sources = [
        slot for slot in slots
        if slot.entity_id == MARIA_PACKAGE.actor and slot.archetype == MARIA_PACKAGE.archetype
    ]
    if (len(destinations) != arena.destination_count or len(sources) != 1
            or any(slot.talk_id != 0 or slot.archetype.chara_init_id != 0
                   for slot in destinations)):
        raise ValueError(
            f"Maria/{arena.key} plan requires every exact original destination state "
            "and one Maria source part"
        )
    target, source = destinations[0], sources[0]
    swap = Swap(
        target.logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        target.archetype,
        source.archetype,
        destinations={
            slot.key: {
                "map_name": slot.map_name,
                "entity_id": slot.entity_id,
                "x": slot.x,
                "y": slot.y,
                "z": slot.z,
            }
            for slot in destinations
        },
    )
    changes, skips = plan_scaling(
        [swap], destinations, dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": maria_donor_contract(arena, allocation),
        "primary_init_source_bindings": [{
            "source_event_file": "event/" + MARIA_PACKAGE.event_file,
            "source_map": source.map_name,
            "source_part": source.part_name,
            "source_entity_id": source.entity_id,
            "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "destination_map": slot.map_name,
            "destination_part": slot.part_name,
            "destination_entity_id": slot.entity_id,
            "required_native_fields": [
                "talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"
            ],
        } for slot in destinations],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
