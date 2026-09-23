"""Reusable source-pinned Martyr Logarius combat donor for base arenas."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_contracts import ARENAS, ArenaContract
from .gascoigne_arena_contract import (
    BEAST_ARCHETYPE,
    BEAST_PINS,
    BEAST_PROXY,
    GASCOIGNE_ARENA_CONTRACT,
    GASCOIGNE_HASHES,
    HUMAN,
    HUMAN_ARCHETYPE,
    MAP_STATES as GASCOIGNE_MAP_STATES,
    SOURCE_INITIALIZATION as GASCOIGNE_SOURCE_INITIALIZATION,
)
from .laurence_arena_contract import LAURENCE_ARENA_CONTRACT
from .maria_arena_contract import MARIA_ARENA_CONTRACT
from .maria_contract import MARIA_PATCH_EXPECTED
from .logarius_contract import (
    BUNDLE,
    CORE_PIN,
    EFFECT_OWNER_ARCHETYPE,
    EFFECT_OWNER_PIN,
    LOGARIUS_ARCHETYPE,
    LOGARIUS_CORE,
    LOGARIUS_EFFECT_OWNER,
    LOGARIUS_EVENT_FILE_SHA256,
    LOGARIUS_EVENT_SOURCE,
    LOGARIUS_FFX_SHA256,
    LOGARIUS_SWORD,
    LOGARIUS_SWORD_EFFECT,
    SOURCE_HASHES,
    SWORD_ARCHETYPE,
    SWORD_PIN,
    NativeActorPin,
)
from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling


# The three additional arenas publish the same ArenaContract boundary as the
# base six.  They remain explicit here because their entry/proxy/controller
# structures require donor-side handling below, not a wider arena mutation.
SUPPORTED_LOGARIUS_ARENAS = (
    *ARENAS,
    MARIA_ARENA_CONTRACT,
    LAURENCE_ARENA_CONTRACT,
    GASCOIGNE_ARENA_CONTRACT,
)
LOGARIUS_ENTRY_ANIMATION = 7000
LOGARIUS_PHASE_EFFECT = 5633
LOGARIUS_SWORD_EVENT = 12504806
LOGARIUS_AURA_EVENT = 12504807
LOGARIUS_CLEANUP_EVENT = 12504808
LOGARIUS_HEALTH_EVENT = 12504802
LOGARIUS_CAMERA_EVENT = 12504804
LOGARIUS_COMPLETION = 12501800
LOGARIUS_START_FLAG = 12504800
LOGARIUS_NOTIFICATION_FLAG = 12504223


DESTINATION_FFX = {
    "cleric-beast": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
    "blood-starved-beast": ("frpg_sfxbnd_m23.ffxbnd.dcx", "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec"),
    "darkbeast-paarl": ("frpg_sfxbnd_m23.ffxbnd.dcx", "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec"),
    "vicar-amelia": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
    "amygdala": ("frpg_sfxbnd_m33.ffxbnd.dcx", "850e8354601f85e59166aaeceb0dea48018fd21afbad005f78b7732fc3889a29"),
    "ebrietas": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
    "lady-maria": ("frpg_sfxbnd_m35.ffxbnd.dcx", "fd656c4a23d3a45202e7d0a5aec1b4f3bea95f71d96af3d1b4b181bcf24b931e"),
    "laurence": ("frpg_sfxbnd_m34.ffxbnd.dcx", "c02322d8ad0e50b18e5f678f3bbfe735971e24aa4c5484f3849ace93f1dfd3b3"),
    # m24_01's three physical MSB states share its m24 area SFX binder and
    # one EMEVD file.  Do not manufacture a state-suffixed event filename.
    "father-gascoigne": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
}

DESTINATION_CO_OP = {
    "cleric-beast": (12411703, "f4982068db5c19d893ac320045e14491832a5722d1fd89a8038ef4cb8b372ce9"),
    "blood-starved-beast": (12301803, "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c"),
    "darkbeast-paarl": (12301703, "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653"),
    "vicar-amelia": (12401804, "85aa59f873b275cb390675f4f2ef13e4f7b3f00935274a2ce43c23b75070da59"),
    "amygdala": (13301803, "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9"),
    "ebrietas": (12421803, "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152"),
    "lady-maria": (13501807, "1c352ec3c5fcd6b866d0880e88d2c693d865d78d5ef3915e20582e5169b0278c"),
    "laurence": (13401853, "c34731a06e8cacbec558610668b60c0be8646079e70a52997047a729085db0f0"),
    "father-gascoigne": (12411803, "0ec656f1563ee0d007df8a53e808cbb4ceb978b039f99c3f001761b0d5ea5f43"),
}


@dataclass(frozen=True)
class LogariusDonorIds:
    sword_entity: int = 982600
    effect_owner_entity: int = 982601
    sword_event: int = 12995100
    aura_event: int = 12995101
    cleanup_event: int = 12995102
    lifecycle_event: int = 12995103
    notification_flag: int = 12995104
    readiness_flag: int = 12995105
    sword_part: str = "ap_logarius_sword"
    effect_owner_part: str = "ap_logarius_effect_owner"
    evidence: str = "BB reusable Logarius donor allocation v1; full original corpus scan"

    def event_ids(self) -> tuple[int, ...]:
        return self.sword_event, self.aura_event, self.cleanup_event, self.lifecycle_event

    def numeric_ids(self) -> tuple[int, ...]:
        return (self.sword_entity, self.effect_owner_entity, *self.event_ids(),
                self.notification_flag, self.readiness_flag)


DEFAULT_LOGARIUS_IDS = LogariusDonorIds()


def _verify(text: str, expected: Mapping[int, str | tuple[str, ...]], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in expected.items():
        body = blocks.get(event_id)
        allowed = (digest,) if isinstance(digest, str) else digest
        if body is None or hashlib.sha256(body.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Logarius donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(values.get(int(match[0]), int(match[0]))), text)


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function(" + ", ".join(
            name.strip() if name.strip().startswith("unused_") else "unused_" + name.strip()
            for name in match[1].split(",") if name.strip()) + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(int(value) for value in re.findall(
                r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
    return frozenset(values)


def _validate_ids(ids: LogariusDonorIds, destination: str = "") -> None:
    values = ids.numeric_ids()
    if (any(value <= 0 for value in values) or len(set(values)) != len(values)
            or set(values) & (_original_literals() | {
                int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)
            })):
        raise ValueError("Logarius donor allocation collides with original corpus")
    if (not ids.sword_part.strip() or not ids.effect_owner_part.strip()
            or ids.sword_part == ids.effect_owner_part or not ids.evidence.strip()):
        raise ValueError("Logarius donor requires distinct helper ownership evidence")


def _destination_telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [line for line in source.splitlines()
                        if line.strip().startswith(instruction + "(")]
        destination_lines = [line for line in destination.splitlines()
                             if line.strip().startswith(instruction + "(")]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(f"Logarius health lacks unique destination {instruction}")
        result = _replace_once(result, source_lines[0], destination_lines[0], instruction)
    return result


def _health_for_arena(arena: ArenaContract, source_health: str,
                      destination_health: str, mapping: Mapping[int, int],
                      ids: LogariusDonorIds) -> str:
    """Transplant the complete three-actor source health lifecycle safely."""
    health = _destination_telemetry(_remap(source_health, mapping), destination_health)
    if arena.key == "laurence":
        health = _replace_once(
            health,
            f"        WaitFor(EventFlag({arena.start_flag}));",
            f"        WaitFor(EventFlag({ids.readiness_flag}));",
            "Laurence restored-state readiness gate",
        )
        health = _replace_once(
            health,
            "L0:\n    SetEventFlag(13404860, ON);",
            f"L0:\n    WaitFor(EventFlag({ids.readiness_flag}));\n"
            "    SetEventFlag(13404860, ON);",
            "Laurence saved-health readiness gate",
        )
    if _destination_has_single_actor_protection(arena):
        # Maria and Laurence both protect their destination actor through the
        # entry/set-piece flow. Logarius's source controller does not clear
        # that protection, so retain the reviewed destination hand-off exactly
        # before the source-owned AI becomes live.
        health = _replace_once(
            health,
            f"    SetCharacterAIState({arena.actor}, Enabled);",
            f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
            f"    SetCharacterAIState({arena.actor}, Enabled);",
            "destination post-entry invincibility clear",
        )
    return health


def _notification_flag(arena: ArenaContract, ids: LogariusDonorIds) -> int:
    """Return the destination's reviewed room-entry flag where it has one."""
    destination_owned = {
        "vicar-amelia": 12404223,
        "lady-maria": 13504810,
        "laurence": 13404860,
        "father-gascoigne": 12414223,
    }
    return destination_owned.get(arena.key, ids.notification_flag)


def _destination_has_single_actor_protection(arena: ArenaContract) -> bool:
    return arena.key in {"lady-maria", "laurence"}


def _adapt_activation(arena: ArenaContract, block: str) -> str:
    result = block
    if f"    SetCharacterImmortality({arena.actor}, Enabled);\n" in result:
        for instruction in (
            f"    ForceAnimationPlayback({arena.actor}, 7001, true, false, false);\n",
            f"    SetSpEffect({arena.actor}, 5647, false);\n",
            f"    ClearSpEffect({arena.actor}, 5647);\n",
        ):
            result = _replace_once(result, instruction, "", "Ebrietas choreography")
        return _replace_once(
            result,
            f"    ForceAnimationPlayback({arena.actor}, 7000, false, true, false);\n",
            f"    ForceAnimationPlayback({arena.actor}, {LOGARIUS_ENTRY_ANIMATION}, false, false, false);\n",
            "Ebrietas wake animation",
        )
    if (f"    SetCharacterMaphits({arena.actor}, true);\n" in result
            and f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result):
        for instruction in (
            f"    SetCharacterMaphits({arena.actor}, true);\n",
            f"    SetCharacterGravity({arena.actor}, Disabled);\n",
            f"    ForceAnimationPlayback({arena.actor}, 7003, true, false, false);\n",
        ):
            result = _replace_once(result, instruction, "", "Amygdala choreography")
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
            f"    ForceAnimationPlayback({arena.actor}, {LOGARIUS_ENTRY_ANIMATION}, false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n"
        )
        return _replace_once(result, old, new, "Amygdala wake sequence")
    if f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result:
        result = _replace_once(
            result, f"    ForceAnimationPlayback({arena.actor}, 7000, true, false, false);\n",
            "", "Paarl dormant animation")
    pattern = re.compile(rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", re.MULTILINE)
    animations = list(pattern.finditer(result))
    if not animations:
        raise ValueError(f"{arena.key} activation lacks an animation witness")
    final = animations[-1].group(0)
    for match in reversed(animations[:-1]):
        result = result[:match.start()] + result[match.end():]
    return _replace_once(
        result, final,
        f"    ForceAnimationPlayback({arena.actor}, {LOGARIUS_ENTRY_ANIMATION}, false, false, false);\n",
        "Logarius entry animation")


def _adapt_music(arena: ArenaContract, block: str) -> str:
    """Use Logarius's sole 5633 boundary without losing destination reloads."""
    replacement = f"CharacterHasSpEffect({arena.actor}, {LOGARIUS_PHASE_EFFECT})"
    if arena.key == "lady-maria":
        first = "        chrFlagArea &= CharacterHasEventMessage(3500800, 100);\n"
        second = "        chrFlagArea2 &= CharacterHasEventMessage(3500800, 300);\n"
        block = _replace_once(block, first, f"        chrFlagArea &= {replacement};\n",
                              "Maria opening music gate")
        l0 = block.find("L0:\n")
        gate = block.find(second)
        l1 = block.find("L1:\n", gate)
        if l0 < 0 or gate < l0 or l1 < gate or block.count("L0:\n") != 1:
            raise ValueError("Maria music lacks the pinned two-stage reload structure")
        direct = block[l0:gate].replace("chrFlagArea2", "chrFlagArea")
        direct = _replace_once(
            direct,
            "    EnableBossMapSound(3503803, Enabled);\n",
            "    EnableBossMapSound(3503804, Enabled);\n",
            "Maria intermediate music enable",
        )
        if "    SetEventFlag(13504811, ON);\n" not in direct:
            raise ValueError("Maria music lacks its destination final-track marker")
        return block[:l0] + direct + "        chrFlagArea2 &= EventFlag(13504811);\n    }\n" + block[l1:]
    if arena.key == "father-gascoigne":
        return _replace_once(
            block,
            "flagArea2 &= EventFlag(12414807);",
            f"flagArea2 &= {replacement};",
            "Gascoigne final music boundary",
        )
    if arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        witness = f"EventFlag({arena.part_routine_event})"
    return _replace_once(block, witness, replacement, "destination music phase")


def _adapt_laurence_entry(blocks: Mapping[int, str],
                          ids: LogariusDonorIds) -> dict[int, str]:
    """Keep Laurence's trigger/protection/warp, but gate AI after restoration."""
    pre = _replace_once(
        blocks[13404861],
        "    ForceAnimationPlayback(3400850, 7002, true, false, false);",
        f"    ForceAnimationPlayback(3400850, {LOGARIUS_ENTRY_ANIMATION}, "
        "false, false, false);",
        "Laurence dormant animation",
    )
    pre = _replace_once(
        pre,
        "        IssueShortWarpRequest(3400850, TargetEntityType.Area, 3402853, -1);\n"
        "        EndEvent();",
        "        IssueShortWarpRequest(3400850, TargetEntityType.Area, 3402853, -1);\n"
        "        SetCharacterGravity(3400850, Enabled);\n"
        "        SetCharacterInvincibility(3400850, Disabled);\n"
        "        SetCharacterMaphits(3400850, false);\n"
        f"        SetEventFlag({ids.readiness_flag}, ON);\n"
        "        EndEvent();",
        "Laurence saved-intro restored-state boundary",
    )
    host = _replace_once(
        blocks[13401851],
        "        SetCharacterMaphits(3400850, false);\n"
        "        ForceAnimationPlayback(3400850, 3029, false, false, false);",
        "        SetCharacterMaphits(3400850, false);\n"
        f"        SetEventFlag({ids.readiness_flag}, ON);",
        "Laurence host restored-state boundary",
    )
    client = _replace_once(
        blocks[13401853],
        "    SetCharacterMaphits(3400850, false);\n"
        "    SetEventFlag(13404858, ON);",
        "    SetCharacterMaphits(3400850, false);\n"
        f"    SetEventFlag({ids.readiness_flag}, ON);\n"
        "    SetEventFlag(13404858, ON);",
        "Laurence client restored-state boundary",
    )
    return {13404861: pre, 13401851: host, 13401853: client}


def _initializer_calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [line for line in event_zero.splitlines()
             if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))", line)]
    if len(calls) != count:
        raise ValueError(f"Logarius Event(0) lacks {count} initializers for {event_id}")
    return calls


def _constructor(arena: ArenaContract, destination_zero: str, donor_zero: str,
                 ids: LogariusDonorIds) -> str:
    calls: list[str] = []
    for source, target, count in (
        (LOGARIUS_SWORD_EVENT, ids.sword_event, 2),
        (LOGARIUS_AURA_EVENT, ids.aura_event, 1),
        (LOGARIUS_CLEANUP_EVENT, ids.cleanup_event, 1),
    ):
        for line in _initializer_calls(donor_zero, source, count):
            calls.append(re.sub(
                r"(\$InitializeEvent\([^,]+,\s*)" + str(source) + r"(?=,|\))",
                r"\g<1>" + str(target), line, count=1))
    calls.append(f"    $InitializeEvent(0, {ids.lifecycle_event});")

    if arena.key == "lady-maria":
        anchor = "    $InitializeEvent(0, 13504822);"
    elif arena.key == "laurence":
        # Laurence has no phase/body anchor. Its exact co-op initializer is
        # the reviewed Event(0) boundary after the retired limb initializers.
        anchor = "    $InitializeEvent(0, 13401853);"
        header = destination_zero.splitlines()[0] + "\n"
        destination_zero = _replace_once(
            destination_zero,
            header,
            header + f"    SetEventFlag({ids.readiness_flag}, OFF);\n",
            "Laurence per-load readiness reset",
        )
    elif arena.key == "father-gascoigne":
        # Both original human/beast navigation initializers target the replaced
        # combat pair. Removing them prevents later AI commands against the
        # Logarius core or the retained terminal proxy.
        for line in (
            "    $InitializeEvent(0, 12415238, 2412820, 2410810, 2412821, 2412824, 2412822);\n",
            "    $InitializeEvent(1, 12415238, 2412820, 2410811, 2412821, 2412824, 2412822);\n",
        ):
            destination_zero = _replace_once(destination_zero, line, "", "Gascoigne navigation initializer")
        anchor = "    $InitializeEvent(0, 12414809);"
    else:
        anchors = [f"    $InitializeEvent(0, {event});" for event in reversed(arena.phase_slots)
                   if destination_zero.count(f"    $InitializeEvent(0, {event});") == 1]
        if not anchors:
            raise ValueError(f"{arena.key} lacks a unique combat initializer anchor")
        anchor = anchors[0]
    return _replace_once(destination_zero, anchor, anchor + "\n" + "\n".join(calls),
                         "destination combat initializer")


def _retired(arena: ArenaContract) -> set[int]:
    return {
        event
        for event in (
            *arena.phase_slots,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
            *arena.retired_combat_events,
        )
        if event is not None
    }


def _mapping(arena: ArenaContract, ids: LogariusDonorIds) -> dict[int, int]:
    return {
        LOGARIUS_CORE: arena.actor,
        LOGARIUS_SWORD: ids.sword_entity,
        LOGARIUS_EFFECT_OWNER: ids.effect_owner_entity,
        LOGARIUS_COMPLETION: arena.completion_event,
        LOGARIUS_START_FLAG: arena.start_flag,
        LOGARIUS_NOTIFICATION_FLAG: _notification_flag(arena, ids),
        LOGARIUS_HEALTH_EVENT: arena.health_bar_event,
        LOGARIUS_CAMERA_EVENT: arena.lockcam_event,
        LOGARIUS_SWORD_EVENT: ids.sword_event,
        LOGARIUS_AURA_EVENT: ids.aura_event,
        LOGARIUS_CLEANUP_EVENT: ids.cleanup_event,
    }


def logarius_donor_contract(arena: ArenaContract,
                            ids: LogariusDonorIds = DEFAULT_LOGARIUS_IDS) -> dict:
    _validate_ids(ids)
    co_op_event, co_op_sha256 = DESTINATION_CO_OP[arena.key]
    preserved = [arena.completion_event, co_op_event]
    adapted = [arena.health_bar_event, arena.music_event, arena.lockcam_event]
    extra: dict[str, object] = {}
    if arena.key in {"lady-maria", "laurence", "father-gascoigne"}:
        # These arenas keep their original entry/co-op flow; the donor health
        # controller waits the destination start flag rather than importing a
        # source fog or cinematic.
        preserved.append(arena.activation_event)
    if arena.key == "laurence":
        preserved.remove(arena.activation_event)
        preserved.remove(co_op_event)
        adapted.extend((arena.activation_event, co_op_event, 13404861))
        extra = {
            "readiness": {
                "flag": ids.readiness_flag,
                "policy": "set only after destination warp/gravity/invincibility/maphit restoration",
            },
        }
    if arena.key == "father-gascoigne":
        preserved.extend((12411801, 12414805, 12414810, 12414811, 12414812, 12414813, 12415238))
        extra = {
            "removed_navigation_initializers": 2,
            "terminal_proxy": {
                "entity": BEAST_PROXY,
                "policy": "inert-and-alive-until-unchanged-event-12411800-completes",
            },
        }
    else:
        adapted.append(arena.activation_event)
    return {
        "format": "bb-logarius-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "martyr-logarius",
        "allocation": asdict(ids),
        "source_hash_pins": dict(SOURCE_HASHES),
        "preserved_destination_events": sorted(set(preserved)),
        "destination_co_op_restore": {
            "event": co_op_event,
            "expected_sha256": co_op_sha256,
            "ownership": (
                "destination-adapted-readiness" if arena.key == "laurence"
                else "destination"),
        },
        "adapted_destination_events": sorted(set(adapted)),
        "retired_destination_controllers": sorted(_retired(arena)),
        "notification_guard": {
            "source_flag": LOGARIUS_NOTIFICATION_FLAG,
            "destination_flag": _notification_flag(arena, ids),
            "destination_owned": arena.key in {
                "vicar-amelia", "lady-maria", "laurence", "father-gascoigne"
            },
        },
        "helper_lifecycle": {
            "sword": ids.sword_entity,
            "effect_owner": ids.effect_owner_entity,
            "completion": arena.completion_event,
            "cleanup_event": ids.lifecycle_event,
        },
        "ffx_requirement": {
            "effect_id": LOGARIUS_SWORD_EFFECT,
            "source_event": LOGARIUS_SWORD_EVENT,
            "policy": "preserve_destination_union_source_v1",
        },
        "projectile_evidence": {
            "shoot_bullet_behavior_id": 223200590,
            "behavior_referenced_bullet_param_id": 232250,
            "bullet_param_sfx_id": -1,
            "bullet_param_is_attack_sfx": 0,
            "additional_ffx_dependency": False,
        },
        **extra,
    }


def patch_logarius_donor(arena: ArenaContract, destination: str, donor_source: str,
                         ids: LogariusDonorIds = DEFAULT_LOGARIUS_IDS) -> str:
    # Reuse the destination adapter's reviewed corpus/installed-source pins.
    # The inventory-facing ArenaContract carries only one digest per event.
    expected = GASCOIGNE_HASHES if arena.key == "father-gascoigne" else {
        event: (digest, MARIA_PATCH_EXPECTED[event])
        if arena.key == "lady-maria" and event in MARIA_PATCH_EXPECTED else digest
        for event, digest in arena.expected.items()
    }
    original = _verify(destination, expected, f"{arena.key} arena")
    donor = _verify(donor_source, SOURCE_HASHES, "Logarius donor")
    co_op_event, co_op_sha256 = DESTINATION_CO_OP[arena.key]
    if (co_op_event not in original
            or hashlib.sha256(original[co_op_event].encode()).hexdigest() != co_op_sha256):
        raise ValueError(f"unsupported original {arena.key} co-op restore event {co_op_event}")
    _validate_ids(ids, destination)
    mapping = _mapping(arena, ids)

    health = _health_for_arena(
        arena, donor[LOGARIUS_HEALTH_EVENT], original[arena.health_bar_event],
        mapping, ids)
    camera = _remap(donor[LOGARIUS_CAMERA_EVENT], mapping)
    source_camera = "SetLockcamSlotNumber(25, 0,"
    destination_camera = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if camera.count(source_camera) != 2:
        raise ValueError("Logarius camera lacks its two source bindings")
    camera = camera.replace(source_camera, destination_camera)
    sword = _remap(donor[LOGARIUS_SWORD_EVENT], mapping)
    sword = _replace_once(sword, "    StartTimeMeasurement(2501000, 116, Enabled);\n", "",
                          "source sword measurement start")
    sword = _replace_once(sword, "    EndTimeMeasurement(2501000);\n", "",
                          "source sword measurement end")
    aura = _remap(donor[LOGARIUS_AURA_EVENT], mapping)
    cleanup = _remap(donor[LOGARIUS_CLEANUP_EVENT], mapping)
    proxy_start = ""
    proxy_finish = ""
    if arena.key == "father-gascoigne":
        # 2410811 is the original beast, not a donor helper.  Keep it inert
        # until the unchanged terminal sees the Logarius core die; only then
        # release/kill it so the original completion path finishes once.
        proxy_start = f"""    ChangeCharacterEnableState({BEAST_PROXY}, Disabled);
    SetCharacterAIState({BEAST_PROXY}, Disabled);
    SetCharacterHPBarDisplay({BEAST_PROXY}, Disabled);
    SetCharacterGravity({BEAST_PROXY}, Disabled);
    SetCharacterInvincibility({BEAST_PROXY}, Enabled);
"""
        proxy_finish = f"""    SetCharacterInvincibility({BEAST_PROXY}, Disabled);
    ForceCharacterDeath({BEAST_PROXY}, false);
"""
    lifecycle = f"""$Event({ids.lifecycle_event}, Default, function() {{
{proxy_start}    if (!ThisEvent()) {{
        WaitFor(EventFlag({arena.completion_event}));
    }}
    SetCharacterAIState({ids.sword_entity}, Disabled);
    ChangeCharacterEnableState({ids.sword_entity}, Disabled);
    ForceCharacterDeath({ids.sword_entity}, false);
    SetCharacterAIState({ids.effect_owner_entity}, Disabled);
    ChangeCharacterEnableState({ids.effect_owner_entity}, Disabled);
    ForceCharacterDeath({ids.effect_owner_entity}, false);
{proxy_finish}}});"""
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    edits.update({
        0: _constructor(arena, original[0], donor[0], ids),
        arena.health_bar_event: health,
        arena.music_event: _adapt_music(arena, original[arena.music_event]),
        arena.lockcam_event: camera,
    })
    # Maria/Laurence entrance cinematics are normalized centrally and
    # Gascoigne owns a two-body cutscene/warp path.  Their exact entry/co-op
    # events remain destination-owned; health waits their reviewed start flag.
    if arena.key not in {"lady-maria", "laurence", "father-gascoigne"}:
        edits[arena.activation_event] = _adapt_activation(arena, original[arena.activation_event])
    elif arena.key == "laurence":
        edits.update(_adapt_laurence_entry(original, ids))
    result = (_replace_events(destination, edits).rstrip() + "\n\n"
              + "\n\n".join((sword, aura, cleanup, lifecycle)) + "\n")
    output = event_blocks(result)
    if set(output) != set(original) | set(ids.event_ids()):
        raise ValueError("Logarius donor changed unexpected event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Logarius donor changed unrelated event {event}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Logarius donor changed destination completion progression")
    copied = "\n".join(output[event] for event in (
        arena.health_bar_event, arena.lockcam_event, *ids.event_ids()))
    if re.search(r"(?<!\d)(?:125|250)\d+(?!\d)", copied):
        raise ValueError("Logarius donor copied a donor-map literal")
    return result


def _require(slots: Sequence[Slot], entity: int, archetype: Archetype,
             map_name: str | None = None) -> list[Slot]:
    matches = sorted((slot for slot in slots if slot.entity_id == entity
                      and (map_name is None or slot.map_name == map_name)), key=lambda slot: slot.key)
    if not matches or any(slot.dummy or slot.talk_id or slot.archetype != archetype
                          for slot in matches):
        raise ValueError(f"unsupported Logarius donor placement provenance for {entity}")
    return matches


def _native(pin: NativeActorPin, *, anchor: bool) -> dict:
    provenance = {"format": "bb-boss-actor-pin-v1", "part_sha256": pin.part_sha256}
    if anchor:
        provenance["anchor_sha256"] = pin.anchor_sha256
    return {
        "source_provenance": provenance,
        "source_initialization": {
            "talk_id": pin.talk_id, "unk_t18": pin.unk_t18,
            "init_anim_id": pin.init_anim_id, "damage_anim_id": pin.damage_anim_id,
        },
    }


def _destinations(arena: ArenaContract, slots: Sequence[Slot]) -> list[Slot]:
    if arena.key != "father-gascoigne":
        return _require(slots, arena.actor, arena.archetype)
    states = set(GASCOIGNE_MAP_STATES)
    found = sorted(
        (slot for slot in slots if slot.entity_id == HUMAN and slot.archetype == HUMAN_ARCHETYPE
         and slot.map_name in states),
        key=lambda slot: slot.map_name,
    )
    if (len(found) != len(states) or {slot.map_name for slot in found} != states
            or any(slot.dummy or slot.talk_id != 241330 for slot in found)):
        raise ValueError("Logarius/Gascoigne requires all three original human states")
    return found


def _gascoigne_terminal_proxies(slots: Sequence[Slot]) -> list[Slot]:
    states = set(GASCOIGNE_MAP_STATES)
    found = sorted(
        (slot for slot in slots if slot.entity_id == BEAST_PROXY and slot.archetype == BEAST_ARCHETYPE
         and slot.map_name in states),
        key=lambda slot: slot.map_name,
    )
    if (len(found) != len(states) or {slot.map_name for slot in found} != states
            or any(slot.dummy or slot.talk_id for slot in found)):
        raise ValueError("Logarius/Gascoigne requires all three pinned terminal proxies")
    return found


def native_plan_logarius_donor(arena: ArenaContract, slots: Sequence[Slot],
                                npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
                                ids: LogariusDonorIds = DEFAULT_LOGARIUS_IDS) -> dict:
    _verify(read_blob(BUNDLE, LOGARIUS_EVENT_SOURCE).decode("utf-8-sig"),
            SOURCE_HASHES, "Logarius donor")
    _validate_ids(ids)
    destinations = _destinations(arena, slots)
    core = _require(slots, LOGARIUS_CORE, LOGARIUS_ARCHETYPE, "m25_00_00_00")
    sword = _require(slots, LOGARIUS_SWORD, SWORD_ARCHETYPE, "m25_00_00_00")
    owner = _require(slots, LOGARIUS_EFFECT_OWNER, EFFECT_OWNER_ARCHETYPE, "m25_00_00_00")
    if (len(destinations) != arena.destination_count or len(core) != 1
            or len(sword) != 1 or len(owner) != 1):
        raise ValueError(f"Logarius/{arena.key} requires exact source and destination states")
    swap = Swap(destinations[0].logical_key, [slot.key for slot in destinations],
                {slot.key: slot.archetype for slot in destinations}, arena.archetype,
                LOGARIUS_ARCHETYPE, destinations={slot.key: {
                    "map_name": slot.map_name, "entity_id": slot.entity_id,
                    "x": slot.x, "y": slot.y, "z": slot.z} for slot in destinations})
    changes, skips = plan_scaling([swap], destinations, dict(npcs), dict(effects), boss_tiers=True)
    additions, primary, scaling = [], [], []
    for target in destinations:
        for source, archetype, pin, part, entity in (
            (sword[0], SWORD_ARCHETYPE, SWORD_PIN, ids.sword_part, ids.sword_entity),
            (owner[0], EFFECT_OWNER_ARCHETYPE, EFFECT_OWNER_PIN,
             ids.effect_owner_part, ids.effect_owner_entity),
        ):
            row = {
                "source_map": source.map_name, "source_part": source.part_name,
                "source_anchor_part": core[0].part_name, "source_entity_id": source.entity_id,
                "source_archetype": asdict(archetype), "source_part_kind": "enemy",
                "destination_map": target.map_name, "destination_anchor_part": target.part_name,
                "destination_part": part, "destination_entity_id": entity,
                "allocation_evidence": ids.evidence,
            }
            row.update(_native(pin, anchor=True)); additions.append(row)
            scaling.append({"destination_map": target.map_name, "destination_part": part,
                            "parent_logical_key": swap.logical_key,
                            "source_npc_param_id": archetype.npc_param_id,
                            "strategy": "allocate_distinct_verified_helper_clone"})
        binding = {
            "source_map": core[0].map_name, "source_part": core[0].part_name,
            "source_entity_id": core[0].entity_id, "source_archetype": asdict(LOGARIUS_ARCHETYPE),
            "destination_map": target.map_name, "destination_part": target.part_name,
            "destination_entity_id": target.entity_id,
            "destination_original_talk_id": target.talk_id,
        }
        binding.update(_native(CORE_PIN, anchor=False)); primary.append(binding)
    ffx_file, ffx_hash = DESTINATION_FFX[arena.key]
    destination_event = arena.event_file.removesuffix(".js")
    terminal_helpers = []
    if arena.key == "father-gascoigne":
        terminal_helpers = [{
            "map": slot.map_name,
            "part": slot.part_name,
            "entity_id": slot.entity_id,
            "archetype": asdict(slot.archetype),
            "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": BEAST_PINS[slot.map_name]},
            "source_initialization": dict(GASCOIGNE_SOURCE_INITIALIZATION),
            "policy": "hidden invincible terminal proxy until unchanged event 12411800 completes",
        } for slot in _gascoigne_terminal_proxies(slots)]
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            **logarius_donor_contract(arena, ids),
            **({"retained_destination_helpers": terminal_helpers} if terminal_helpers else {}),
        },
        "boss_actor_additions": additions,
        "primary_init_source_bindings": primary,
        "boss_actor_scaling_requirements": scaling,
        "boss_emevd_ffx_requirements": [{
            "format": "bb-boss-emevd-ffx-requirement-v1",
            "source_map": "m25_00_00_00", "destination_map": destinations[0].map_name,
            "source_event_file": "m25_00_00_00.emevd.dcx",
            "source_event_sha256": LOGARIUS_EVENT_FILE_SHA256,
            "source_event_id": LOGARIUS_SWORD_EVENT,
            "destination_event_file": destination_event,
            "destination_event_id": ids.sword_event, "effect_id": LOGARIUS_SWORD_EFFECT,
        }],
        "boss_ffx_merges": [{
            "source_file": "frpg_sfxbnd_m25.ffxbnd.dcx", "source_sha256": LOGARIUS_FFX_SHA256,
            "destination_file": ffx_file, "destination_sha256": ffx_hash,
            "required_effect_ids": [LOGARIUS_SWORD_EFFECT],
            "policy": "preserve_destination_union_source_v1",
        }],
        "scaling": {"enabled": bool(changes),
                    "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [row.json() for row in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {(row["destination_map"], row["destination_part"]): row["parent_logical_key"]
              for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate Logarius helper scaling destination")
    return result
