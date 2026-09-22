"""Pinned Lady Maria combat overlay for Amelia's progression-owned arena.

This contract keeps Amelia's fog/cutscene/reward lifecycle local.  It imports
only Maria's verified health label, camera body, event-target witness and the
message-20 cleanup routine.  The unplaced ``3500801`` operand remains opaque:
the builder must bind its original source and destination absence witnesses
before asking the native writer to retain it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .boss_contracts import AMELIA_ARENA
from .maria_contract import (
    MARIA_ARENA,
    MARIA_EVENT_TARGET,
    MARIA_EVENT_TARGET_REFERENCE,
    MARIA_PACKAGE,
    _noop,
    _replace_events,
    _replace_once,
    _verify,
    event_blocks,
)
from .model import Slot, Swap
from .scaling import plan_scaling


@dataclass(frozen=True)
class MariaAmeliaAttachmentIds:
    """Project-owned event allocation for Maria's portable cleanup routine."""

    phase_cleanup_event: int


def _numbers(text: str, replacements: Mapping[int, int]) -> str:
    """Remap only the declared actor, terminal, and event identifiers."""
    import re
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(replacements.get(int(match[0]), int(match[0]))), text)


def _append_initializer(constructor: str, ids: MariaAmeliaAttachmentIds) -> str:
    anchor = "    $InitializeEvent(0, 12404808);"
    if constructor.count(anchor) != 1:
        raise ValueError("Amelia Event(0) phase initializer witness drift")
    return _replace_once(constructor, anchor,
                         anchor + f"\n    $InitializeEvent(0, {ids.phase_cleanup_event});",
                         "Amelia phase initializer anchor")


def _nooped_amelia_events(arena: Mapping[int, str]) -> dict[int, str]:
    """Keep all source-witnessed Amelia initializer signatures callable."""
    event_ids = (*AMELIA_ARENA.phase_slots, AMELIA_ARENA.part_routine_event,
                 AMELIA_ARENA.cloth_routine_event, 12404830)
    if len(set(event_ids)) != 5 or any(event_id not in arena for event_id in event_ids):
        raise ValueError("Amelia residual combat event witness drift")
    return {event_id: _noop(arena[event_id]) for event_id in event_ids}


def _remap_lockcam_map(block: str) -> str:
    """Maria's exact two lockcam calls retain their radii and slot numbers."""
    source, destination = "SetLockcamSlotNumber(35, 0,", "SetLockcamSlotNumber(24, 0,"
    if block.count(source) != 2:
        raise ValueError("Maria lockcam map bindings are not the exact two-call witness")
    return block.replace(source, destination)


def maria_at_amelia_plan(ids: MariaAmeliaAttachmentIds) -> dict:
    """Static source contract; native hashes are bound by the builder later."""
    return {
        "format": "bb-maria-amelia-contract-v1",
        "status": "experimental",
        "arena": AMELIA_ARENA.key,
        "donor": MARIA_PACKAGE.key,
        "preserved_destination_events": [AMELIA_ARENA.completion_event,
                                           AMELIA_ARENA.activation_event,
                                           AMELIA_ARENA.co_op_entry_event],
        "source_owned_not_copied": [MARIA_ARENA.completion_event,
                                      MARIA_ARENA.cutscene_entry_event,
                                      MARIA_ARENA.co_op_restore_event,
                                      MARIA_ARENA.host_fog_event,
                                      MARIA_ARENA.guest_fog_event,
                                      *MARIA_ARENA.source_reward_flags],
        "attachments": [{"source_event": MARIA_ARENA.phase_cleanup_event,
                           "destination_event": ids.phase_cleanup_event,
                           "initializers": [asdict(binding)
                                            for binding in MARIA_PACKAGE.attachments[0].initializers]}],
        "opaque_external_references": [{
            **asdict(MARIA_EVENT_TARGET_REFERENCE),
            "destination_event": AMELIA_ARENA.health_bar_event,
            "destination_actor": AMELIA_ARENA.actor,
        }],
        "behavioral_unknown": "3500801 remains opaque; static effect is unobserved",
    }


def maria_at_amelia_external_reference_requirement() -> dict:
    """Describe the source/destination witness that native code must hash-pin."""
    return {
        "format": "bb-boss-external-reference-v1",
        "entity_id": MARIA_EVENT_TARGET,
        "source_map": "m35_00_00_00",
        "destination_map_prefix": AMELIA_ARENA.map_prefix,
        "source_event_file": MARIA_PACKAGE.event_file.removesuffix(".js"),
        "source_event_id": MARIA_ARENA.health_event,
        "source_actor": MARIA_PACKAGE.actor,
        "destination_event_file": AMELIA_ARENA.event_file.removesuffix(".js"),
        "destination_event_id": AMELIA_ARENA.health_bar_event,
        "destination_actor": AMELIA_ARENA.actor,
        "evidence_status": "inferred",
        "runtime_status": "unobserved",
    }


def patch_maria_at_amelia(destination: str, donor_source: str,
                          ids: MariaAmeliaAttachmentIds) -> str:
    """Overlay Maria combat while retaining Amelia's cutscene and terminal."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, AMELIA_ARENA.expected, "Amelia arena")
    _verify(donor, MARIA_PACKAGE.expected, "Lady Maria donor")
    literals = {int(value) for value in __import__("re").findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if ids.phase_cleanup_event <= 0 or ids.phase_cleanup_event in literals:
        raise ValueError("Maria phase-cleanup event ID collides with original Amelia literal")

    # Amelia's location/cutscene trigger remains intact. Maria has no source
    # ForceAnimationPlayback witness, so only the two c5020 entry calls leave.
    activation = arena[AMELIA_ARENA.activation_event]
    for instruction in (
        f"    ForceAnimationPlayback({AMELIA_ARENA.actor}, 7000, false, false, false);\n",
        f"    ForceAnimationPlayback({AMELIA_ARENA.actor}, 7001, false, false, false);\n",
    ):
        activation = _replace_once(activation, instruction, "", "Amelia-only entry animation")
    health = _replace_once(arena[AMELIA_ARENA.health_bar_event],
        f"DisplayBossHealthBar(Enabled, {AMELIA_ARENA.actor}, 0, {AMELIA_ARENA.health_bar_label})",
        f"DisplayBossHealthBar(Enabled, {AMELIA_ARENA.actor}, 0, {MARIA_PACKAGE.health_bar_label})",
        "Maria health-bar label")
    health = _replace_once(health, f"    SetCharacterAIState({AMELIA_ARENA.actor}, Enabled);\n",
        f"    SetCharacterAIState({AMELIA_ARENA.actor}, Enabled);\n"
        f"    SetCharacterEventTarget({AMELIA_ARENA.actor}, {MARIA_EVENT_TARGET});\n",
        "opaque Maria event target")
    lockcam = _numbers(donor[MARIA_ARENA.lockcam_event], {
        MARIA_PACKAGE.actor: AMELIA_ARENA.actor,
        MARIA_ARENA.completion_event: AMELIA_ARENA.completion_event,
        MARIA_ARENA.lockcam_event: AMELIA_ARENA.lockcam_event,
    })
    lockcam = _remap_lockcam_map(lockcam)
    cleanup = _numbers(donor[MARIA_ARENA.phase_cleanup_event], {
        MARIA_PACKAGE.actor: AMELIA_ARENA.actor,
        MARIA_ARENA.completion_event: AMELIA_ARENA.completion_event,
        MARIA_ARENA.phase_cleanup_event: ids.phase_cleanup_event,
    })
    edits = _nooped_amelia_events(arena)
    edits.update({
        0: _append_initializer(arena[0], ids),
        AMELIA_ARENA.activation_event: activation,
        AMELIA_ARENA.health_bar_event: health,
        AMELIA_ARENA.lockcam_event: lockcam,
    })
    result = _replace_events(destination, edits).rstrip() + "\n\n" + cleanup + "\n"
    output = event_blocks(result)
    if set(output) != set(arena) | {ids.phase_cleanup_event}:
        raise ValueError("Maria/Amelia adapter changed unexpected event identity")
    for event_id, original in arena.items():
        if event_id not in edits and output[event_id] != original:
            raise ValueError(f"Maria/Amelia adapter changed unrelated arena event {event_id}")
    if output[AMELIA_ARENA.completion_event] != arena[AMELIA_ARENA.completion_event]:
        raise ValueError("Maria/Amelia adapter changed Amelia completion/progression")
    return result


def native_plan_maria_at_amelia(slots: list[Slot], npcs: Mapping[int, dict],
                                effects: Mapping[int, dict], ids: MariaAmeliaAttachmentIds,
                                seed: str) -> dict:
    """Native v2 plan with Maria's exact source initialization declared."""
    amelia = [slot for slot in slots if slot.entity_id == AMELIA_ARENA.actor
              and slot.archetype == AMELIA_ARENA.archetype]
    maria = [slot for slot in slots if slot.entity_id == MARIA_PACKAGE.actor
             and slot.archetype == MARIA_PACKAGE.archetype]
    if (len(amelia) != AMELIA_ARENA.destination_count or len(maria) != 1
            or any(slot.talk_id != 0 or slot.archetype.chara_init_id != 0 for slot in amelia)):
        raise ValueError("Maria/Amelia plan requires exact original Amelia states and Maria part")
    target, source = amelia[0], maria[0]
    swap = Swap(target.logical_key, [slot.key for slot in amelia],
                {slot.key: slot.archetype for slot in amelia}, target.archetype,
                source.archetype, destinations={slot.key: {
                    "map_name": slot.map_name, "entity_id": slot.entity_id,
                    "x": slot.x, "y": slot.y, "z": slot.z,
                } for slot in amelia})
    changes, skips = plan_scaling([swap], amelia, dict(npcs), dict(effects))
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": maria_at_amelia_plan(ids),
        "primary_init_source_bindings": [{
            "source_map": source.map_name, "source_part": source.part_name,
            "source_entity_id": source.entity_id, "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id, "destination_map": slot.map_name,
            "destination_part": slot.part_name, "destination_entity_id": slot.entity_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
        } for slot in amelia],
        "scaling": {
            "enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes), "changes": [change.json() for change in changes],
            "skip_count": len(skips), "skips": skips,
        },
    }
