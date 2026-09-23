"""Reusable Laurence combat donor for one-actor progression arenas.

Laurence contributes his full health/network lifecycle, five limb routines,
message-400 hitmask phase, camera, and source-pinned entry animation.  The
destination continues to own progression, fog, co-op entry, music objects,
telemetry, and arena geometry.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

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
    _noop,
    _replace_events,
    _replace_once,
    _verify,
    event_blocks,
)
from .maria_arena_contract import MARIA_ARENA_CONTRACT
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling


BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
LAURENCE_EVENT_FILE = "m34_00_00_00.emevd.dcx.js"
LAURENCE_ACTOR = 3400850
LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)
LAURENCE_COMPLETION = 13401850
LAURENCE_ENTRY_EVENT = 13401851
LAURENCE_PRE_ENTRY_EVENT = 13404861
LAURENCE_HEALTH_EVENT = 13404852
LAURENCE_MUSIC_EVENT = 13404853
LAURENCE_CAMERA_EVENT = 13404854
LAURENCE_LIMB_EVENT = 13404870
LAURENCE_HITMASK_EVENT = 13404875
LAURENCE_START_FLAG = 13404858
LAURENCE_HEALTH_INITIALIZED_FLAG = 13404860
LAURENCE_PHASE_MESSAGE = 400
LAURENCE_ENTRY_ANIMATION = 3029


SUPPORTED_LAURENCE_ARENAS = (
    CLERIC_ARENA,
    BSB_ARENA,
    PAARL_ARENA,
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    EBRIETAS_ARENA,
    MARIA_ARENA_CONTRACT,
)


# Every original source body which supplies portable combat or witnesses the
# arena-owned lifecycle deliberately left behind in m34.
LAURENCE_SOURCE_HASHES = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13401851: "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
    13401853: "c34731a06e8cacbec558610668b60c0be8646079e70a52997047a729085db0f0",
    13404850: "8a9150872345a8ce6e8e2f8be8bef234c84d5294c8dbb6074d361b031019e9f4",
    13404851: "3697777dafa1624393090874701ba5f93e5a1937ba16f91f996013b69b272bb9",
    13404852: "a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",
    13404853: "6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",
    13404854: "67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",
    13404855: "e11b2c88da282d31e4a68f6c53606aa3b8b07b85025074c800db31937e0ea780",
    13404856: "79586243afa9f1fdc159e34f13df970674494a1c2ec5d9616805686e339a52ce",
    13404857: "fc77bafabd1c1ebeb901731941af156b176b990c5b835c52c54addab151e8670",
    13404861: "7888497bc33ab25bdc668813a50cbc6a3ad44c2d6321b05fecdf4c500a297f7e",
    13404870: "237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",
    13404875: "e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",
}


@dataclass(frozen=True)
class LaurenceDonorAllocation:
    limbs_event: int
    hitmask_event: int
    health_initialized_flag: int

    def values(self) -> tuple[int, int, int]:
        return self.limbs_event, self.hitmask_event, self.health_initialized_flag


DEFAULT_LAURENCE_ALLOCATION = LaurenceDonorAllocation(12994900, 12994901, 12994902)


def _numeric_literals(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_game_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numeric_literals(body.decode("utf-8-sig")))
    return frozenset(values)


def _require_allocation(allocation: LaurenceDonorAllocation) -> None:
    values = allocation.values()
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError("Laurence allocation requires three distinct positive IDs")
    if set(values) & _original_game_literals():
        raise ValueError("Laurence allocation collides with original EMEVD/MSBB corpus")


def _numbers(text: str, replacements: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(replacements.get(int(match[0]), int(match[0]))),
        text,
    )


def _destination_health_telemetry(source_health: str, destination_health: str) -> str:
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
                                      allocation: LaurenceDonorAllocation) -> str:
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


def _adapt_activation(arena: ArenaContract, block: str,
                      allocation: LaurenceDonorAllocation) -> str:
    """Keep arena entry predicates and play Laurence's pinned 3029 wake-up."""
    if arena.key == MARIA_ARENA_CONTRACT.key:
        enabled = f"    ChangeCharacterEnableState({arena.actor}, Enabled);\n"
        start = f"    SetEventFlag({arena.start_flag}, ON);\n"
        if block.count(enabled) != 1 or block.count(start) != 1:
            raise ValueError("Maria entry lacks its pinned enable/start sequence")
        if block.index(enabled) > block.index(start):
            raise ValueError("Maria entry enables its actor after the start flag")
        return _replace_once(
            block,
            enabled,
            enabled + f"    ForceAnimationPlayback({arena.actor}, "
            f"{LAURENCE_ENTRY_ANIMATION}, false, false, false);\n",
            "Maria Laurence wake insertion",
        )
    result = block
    if f"    SetCharacterImmortality({arena.actor}, Enabled);\n" in result:
        # Ebrietas must remain immortal while damage is used as the start
        # predicate. Replace only her model animation/effect choreography.
        for instruction in (
            f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n",
            f"    SetSpEffect({arena.actor}, 5647, false);\n",
            f"    ClearSpEffect({arena.actor}, 5647);\n",
        ):
            result = _replace_once(result, instruction, "", "Ebrietas entry choreography")
        result = _replace_once(
            result,
            f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n",
            f"    ForceAnimationPlayback({arena.actor}, {LAURENCE_ENTRY_ANIMATION}, "
            "false, false, false);\n",
            "Ebrietas wake animation",
        )
        return _mark_existing_entry_notification(result, allocation)

    if (f"    SetCharacterMaphits({arena.actor}, true);\n" in result
            and f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result):
        # Amygdala's gravity/maphit animation is model-specific. Keep only the
        # invincibility pair around the destination area predicate.
        for instruction in (
            f"    SetCharacterMaphits({arena.actor}, true);\n",
            f"    SetCharacterGravity({arena.actor}, Disabled);\n",
            f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n",
        ):
            result = _replace_once(result, instruction, "", "Amygdala pre-entry choreography")
        old = (
            f"    SetEventFlag({arena.start_flag}, ON);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7006, false, false, false);\n"
            "    WaitFixedTimeFrames(30);\n"
            f"    ForceAnimationPlayback({arena.actor}, 7002, false, false, false);\n"
            "    WaitFixedTimeFrames(160);\n"
            f"    SetCharacterGravity({arena.actor}, Enabled);\n"
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    SetCharacterMaphits({arena.actor}, false);\n"
        )
        new = (
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    ForceAnimationPlayback({arena.actor}, {LAURENCE_ENTRY_ANIMATION}, "
            "false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n"
        )
        result = _replace_once(result, old, new, "Amygdala post-entry choreography")
        return _mark_existing_entry_notification(result, allocation)

    # Paarl uses an invincible dormant animation before its trigger. Remove it
    # but retain the 70-frame protected wake timing around Laurence's 3029.
    if f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result:
        result = _replace_once(
            result,
            f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n",
            "",
            "Paarl dormant animation",
        )

    animation_pattern = re.compile(
        rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", re.MULTILINE
    )
    animations = list(animation_pattern.finditer(result))
    if not animations:
        raise ValueError(f"{arena.key} activation lacks a destination animation witness")
    # Cleric/BSB have one wake call; Amelia has two consecutive calls. Remove
    # every earlier call and replace the final one with Laurence's source pin.
    final = animations[-1].group(0)
    for match in reversed(animations[:-1]):
        result = result[:match.start()] + result[match.end():]
    result = _replace_once(
        result,
        final,
        f"    ForceAnimationPlayback({arena.actor}, {LAURENCE_ENTRY_ANIMATION}, "
        "false, false, false);\n",
        "Laurence entry animation",
    )
    return _mark_existing_entry_notification(result, allocation)


def _destination_music(arena: ArenaContract, block: str) -> str:
    if arena.key == MARIA_ARENA_CONTRACT.key:
        first = "        chrFlagArea &= CharacterHasEventMessage(3500800, 100);\n"
        second = "        chrFlagArea2 &= CharacterHasEventMessage(3500800, 300);\n"
        result = _replace_once(
            block,
            first,
            f"        chrFlagArea &= CharacterHasEventMessage(3500800, "
            f"{LAURENCE_PHASE_MESSAGE});\n",
            "Maria opening music boundary",
        )
        # Laurence has one source-backed combat boundary. Preserve Maria's
        # outside-L1 recovery path for active-fight reloads, while sending the
        # first boundary directly to the final track. The first transition
        # sets 13504811, so the retained second predicate becomes immediate.
        result = _replace_once(
            result,
            "    EnableBossMapSound(3503803, Enabled);\n",
            "    EnableBossMapSound(3503804, Enabled);\n",
            "Maria intermediate music enable",
        )
        result = _replace_once(
            result,
            second,
            "        chrFlagArea2 &= EventFlag(13504811);\n",
            "Maria unreachable second music boundary",
        )
        if "    SetEventFlag(13504811, ON);\n" not in result:
            raise ValueError("Maria music lacks its destination phase/SFX marker")
        return result
    if arena.phase_music_message is None:
        return _replace_once(
            block,
            f"flagArea2 &= EventFlag({arena.part_routine_event});",
            f"flagArea2 &= CharacterHasEventMessage({arena.actor}, "
            f"{LAURENCE_PHASE_MESSAGE});",
            "destination music phase flag",
        )
    witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    if block.count(witness) != 1:
        raise ValueError(f"{arena.key} music lacks its declared phase-message witness")
    return block.replace(
        witness,
        f"CharacterHasEventMessage({arena.actor}, {LAURENCE_PHASE_MESSAGE})",
        1,
    )


def _initializer_calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [
        line for line in event_zero.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))", line)
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


def _constructor(arena: ArenaContract, destination_zero: str, donor_zero: str,
                 allocation: LaurenceDonorAllocation) -> str:
    calls = [
        *(
            _remap_initializer(line, LAURENCE_LIMB_EVENT, allocation.limbs_event)
            for line in _initializer_calls(donor_zero, LAURENCE_LIMB_EVENT, 5)
        ),
        _remap_initializer(
            _initializer_calls(donor_zero, LAURENCE_HITMASK_EVENT, 1)[0],
            LAURENCE_HITMASK_EVENT,
            allocation.hitmask_event,
        ),
    ]
    if arena.key == MARIA_ARENA_CONTRACT.key:
        anchor = "    $InitializeEvent(0, 13504822);"
        return _replace_once(
            destination_zero,
            anchor,
            anchor + "\n" + "\n".join(calls),
            "Maria cleanup initializer anchor",
        )
    anchors = [
        f"    $InitializeEvent(0, {event_id});"
        for event_id in reversed(arena.phase_slots)
        if destination_zero.count(f"    $InitializeEvent(0, {event_id});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} has no unique zero-argument phase initializer")
    anchor = anchors[0]
    return _replace_once(
        destination_zero,
        anchor,
        anchor + "\n" + "\n".join(calls),
        f"{arena.key} phase initializer anchor",
    )


def _retired_controllers(arena: ArenaContract) -> set[int]:
    return {
        event_id
        for event_id in (
            *arena.phase_slots,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
        )
        if event_id is not None
    }


def laurence_donor_contract(
    arena: ArenaContract,
    allocation: LaurenceDonorAllocation = DEFAULT_LAURENCE_ALLOCATION,
) -> dict:
    _require_allocation(allocation)
    retired = _retired_controllers(arena)
    exact_preserved = [arena.completion_event]
    if arena.co_op_entry_event not in retired:
        exact_preserved.append(arena.co_op_entry_event)
    copied = (
        (LAURENCE_HEALTH_EVENT, arena.health_bar_event),
        (LAURENCE_CAMERA_EVENT, arena.lockcam_event),
        (LAURENCE_LIMB_EVENT, allocation.limbs_event),
        (LAURENCE_HITMASK_EVENT, allocation.hitmask_event),
    )
    contract = {
        "format": "bb-laurence-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "laurence",
        "allocation": asdict(allocation),
        "preserved_destination_events": exact_preserved,
        "adapted_destination_events": [
            arena.activation_event,
            arena.health_bar_event,
            arena.music_event,
            arena.lockcam_event,
        ],
        "source_owned_not_copied": [
            LAURENCE_COMPLETION,
            LAURENCE_PRE_ENTRY_EVENT,
            LAURENCE_ENTRY_EVENT,
            13401853,
            13404850,
            13404851,
            LAURENCE_MUSIC_EVENT,
            13404855,
            13404856,
            13404857,
        ],
        "source_event_hashes": {
            str(event_id): digest for event_id, digest in LAURENCE_SOURCE_HASHES.items()
        },
        "copied_source_events": [
            {
                "source_event": source_event,
                "destination_event": destination_event,
                "expected_source_sha256": LAURENCE_SOURCE_HASHES[source_event],
            }
            for source_event, destination_event in copied
        ],
        "attachments": [
            {
                "source_event": LAURENCE_LIMB_EVENT,
                "destination_event": allocation.limbs_event,
                "initializer_count": 5,
            },
            {
                "source_event": LAURENCE_HITMASK_EVENT,
                "destination_event": allocation.hitmask_event,
                "initializer_count": 1,
            },
        ],
        "entry_animation": {
            "animation_id": LAURENCE_ENTRY_ANIMATION,
            "source_event": LAURENCE_ENTRY_EVENT,
            "source_sha256": LAURENCE_SOURCE_HASHES[LAURENCE_ENTRY_EVENT],
        },
        "retired_destination_controllers": sorted(retired),
        "destination_owned_health_telemetry": {
            "event": arena.health_bar_event,
            "instructions": ["CreatePlaylog", "StartTimeMeasurement"],
            "reason": "destination completion owns the matching measurement lifecycle",
        },
    }
    if arena.key == MARIA_ARENA_CONTRACT.key:
        contract["readiness_adapter"] = {
            "destination_event": arena.activation_event,
            "host_sequence": [
                f"ChangeCharacterEnableState({arena.actor}, Enabled)",
                f"ForceAnimationPlayback({arena.actor}, {LAURENCE_ENTRY_ANIMATION})",
                f"SetEventFlag({arena.start_flag}, ON)",
            ],
            "health_wait_flag": arena.activation_event,
            "preserved_co_op_restore_event": arena.co_op_entry_event,
            "pre_trigger_protection": "destination actor remains disabled",
        }
        contract["destination_notification_guard"] = {
            "flag": 13504810,
            "source_guard_replaced": LAURENCE_HEALTH_INITIALIZED_FLAG,
            "fog_helper_initializer_event": 13504730,
            "reason": "Maria fog/helper and health must share one notification flag",
        }
    return contract


def patch_laurence_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    allocation: LaurenceDonorAllocation = DEFAULT_LAURENCE_ALLOCATION,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, LAURENCE_SOURCE_HASHES, "Laurence donor")
    if donor[LAURENCE_ENTRY_EVENT].count(
            f"ForceAnimationPlayback({LAURENCE_ACTOR}, "
            f"{LAURENCE_ENTRY_ANIMATION}, false, false, false);") != 1:
        raise ValueError("Laurence donor lacks its pinned entry animation witness")
    _require_allocation(allocation)
    if set(allocation.values()) & _numeric_literals(destination):
        raise ValueError("Laurence allocation collides with destination literal")

    readiness_flag = (
        arena.activation_event
        if arena.key == MARIA_ARENA_CONTRACT.key
        else arena.start_flag
    )
    health_initialized_flag = (
        13504810
        if arena.key == MARIA_ARENA_CONTRACT.key
        else allocation.health_initialized_flag
    )
    health = _numbers(donor[LAURENCE_HEALTH_EVENT], {
        LAURENCE_HEALTH_EVENT: arena.health_bar_event,
        LAURENCE_ACTOR: arena.actor,
        LAURENCE_COMPLETION: arena.completion_event,
        LAURENCE_START_FLAG: readiness_flag,
        LAURENCE_HEALTH_INITIALIZED_FLAG: health_initialized_flag,
    })
    health = _destination_health_telemetry(health, original[arena.health_bar_event])
    if arena.key == MARIA_ARENA_CONTRACT.key:
        health = _replace_once(
            health,
            f"    SetCharacterAIState({arena.actor}, Enabled);\n",
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    SetCharacterAIState({arena.actor}, Enabled);\n",
            "Maria pre-combat invincibility clear",
        )
    camera = _numbers(donor[LAURENCE_CAMERA_EVENT], {
        LAURENCE_CAMERA_EVENT: arena.lockcam_event,
        LAURENCE_ACTOR: arena.actor,
        LAURENCE_COMPLETION: arena.completion_event,
    })
    source_camera = "SetLockcamSlotNumber(34, 0,"
    destination_camera = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if camera.count(source_camera) != 2:
        raise ValueError("Laurence lockcam lacks the exact two-call source witness")
    camera = camera.replace(source_camera, destination_camera)
    limbs = _numbers(donor[LAURENCE_LIMB_EVENT], {
        LAURENCE_LIMB_EVENT: allocation.limbs_event,
        LAURENCE_ACTOR: arena.actor,
        LAURENCE_COMPLETION: arena.completion_event,
    })
    hitmask = _numbers(donor[LAURENCE_HITMASK_EVENT], {
        LAURENCE_HITMASK_EVENT: allocation.hitmask_event,
        LAURENCE_ACTOR: arena.actor,
    })

    retired = _retired_controllers(arena)
    edits = {event_id: _noop(original[event_id]) for event_id in retired}
    edits.update({
        0: _constructor(arena, original[0], donor[0], allocation),
        arena.activation_event: _adapt_activation(
            arena, original[arena.activation_event], allocation
        ),
        arena.health_bar_event: health,
        arena.music_event: _destination_music(arena, original[arena.music_event]),
        arena.lockcam_event: camera,
    })
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + limbs
        + "\n\n"
        + hitmask
        + "\n"
    )
    output = event_blocks(result)
    expected_ids = set(original) | {allocation.limbs_event, allocation.hitmask_event}
    if set(output) != expected_ids:
        raise ValueError("Laurence donor adapter changed an unexpected event identity")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"Laurence donor adapter changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Laurence donor adapter changed destination completion/progression")
    return result


def native_plan_laurence_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: LaurenceDonorAllocation = DEFAULT_LAURENCE_ALLOCATION,
) -> dict:
    _require_allocation(allocation)
    destinations = [
        slot for slot in slots
        if slot.entity_id == arena.actor and slot.archetype == arena.archetype
    ]
    sources = [
        slot for slot in slots
        if slot.entity_id == LAURENCE_ACTOR and slot.archetype == LAURENCE_ARCHETYPE
    ]
    if (
        len(destinations) != arena.destination_count
        or len(sources) != 1
        or sources[0].map_name != "m34_00_00_00"
        or sources[0].part_name != "c4500_0000"
        or sources[0].talk_id != 0
        or any(slot.talk_id != 0 or slot.archetype.chara_init_id != 0
               for slot in destinations)
    ):
        raise ValueError(
            f"Laurence/{arena.key} plan requires every exact original destination "
            "state and the pinned c4500_0000 source"
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
        "boss_contract": laurence_donor_contract(arena, allocation),
        "primary_init_source_bindings": [{
            "source_event_file": "event/" + LAURENCE_EVENT_FILE,
            "source_map": source.map_name,
            "source_part": source.part_name,
            "source_entity_id": source.entity_id,
            "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "destination_map": slot.map_name,
            "destination_part": slot.part_name,
            "destination_entity_id": slot.entity_id,
            "destination_original_talk_id": slot.talk_id,
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
