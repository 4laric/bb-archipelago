"""Reusable source-pinned Maria destination arena for portable combat packages.

Maria progression, fog, co-op entry, and terminal events remain destination-owned.
The cinematic normalizer owns only the player warp/cutscene in event 13501801.
This module installs the donor's source-backed readiness lifecycle in a separate
project event, keyed to Maria's post-entry flag, so combat does not become
damageable or AI-active before its donor wake sequence completes.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import (
    AMYGDALA_PACKAGE,
    BSB_PACKAGE,
    EBRIETAS_PACKAGE,
    PACKAGES,
    ArenaContract,
    Archetype,
    CombatPackage,
    EventAttachment,
    MusicPhaseSignal,
    PartBinding,
    actor_addition_requirements,
    primary_initialization_requirements,
)
from .maria_contract import MARIA_EVENT_FILE, MARIA_PACKAGE, MARIA_PATCH_EXPECTED
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"

# These values are absent from the complete bundled original EMEVD/MSB corpus
# and from the current project allocation ledger.  The builder repeats its
# whole-composition collision scan before accepting them.
ATTACHMENT_EVENTS = (12995000, 12995001, 12995002, 12995003, 12995004)
OWNER_CLEANUP_EVENT = 12995005
ACTIVATION_EVENT = 12995006
BULLET_OWNER_ENTITY = 982500


MARIA_ARENA_CONTRACT = ArenaContract(
    key="lady-maria",
    event_file=MARIA_EVENT_FILE,
    map_prefix="m35_00_",
    actor=3500800,
    archetype=Archetype("c4520", 452000, 452000, 0),
    destination_count=1,
    completion_event=13501800,
    start_flag=13504808,
    health_bar_event=13504802,
    health_bar_label=452000,
    activation_event=13501801,
    music_event=13504803,
    phase_music_message=100,
    lockcam_event=13504804,
    lockcam_map=35,
    lockcam_subarea=0,
    phase_slots=(),
    co_op_entry_event=13501807,
    # Maria has no replaceable body routine.  Its message-20 cleanup controller
    # is an explicit retirement and the unique Event(0) replacement anchor.
    part_routine_event=None,
    cloth_routine_event=None,
    part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,),
    attachment_anchor_slot=0,
    attachment_anchor_event=13504822,
    expected=MARIA_PACKAGE.expected,
    activation_idle_animation=None,
    music_phase_messages=(100, 300),
    retired_combat_events=(13504822,),
    activation_profile="normalized-cinematic",
)


@dataclass(frozen=True)
class MariaArenaIds:
    """Project-owned additions used by one selected portable donor."""

    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    owner_cleanup_event: int = OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.owner_cleanup_event,
                self.activation_event, self.bullet_owner_entity)


DEFAULT_IDS = MariaArenaIds()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _verify_maria(blocks: Mapping[int, str]) -> None:
    for event_id, digest in MARIA_ARENA_CONTRACT.expected.items():
        block = blocks.get(event_id)
        if block is None:
            raise ValueError(f"Maria arena lacks pinned event {event_id}")
        allowed = {digest}
        if event_id in MARIA_PATCH_EXPECTED:
            allowed.add(MARIA_PATCH_EXPECTED[event_id])
        if hashlib.sha256(block.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original Maria arena event {event_id}")


def _verify_donor(blocks: Mapping[int, str], donor: CombatPackage) -> None:
    for event_id, digest in donor.expected.items():
        if hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {donor.key} donor event {event_id}")


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function(" + ", ".join(
            name.strip() if name.strip().startswith("unused_") else "unused_" + name.strip()
            for name in match[1].split(",") if name.strip()
        ) + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Maria arena expected one {label}")
    return text.replace(old, new, 1)


def _remap(block: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        block,
    )


def _initializer(slot: int, event_id: int, arguments: tuple[str, ...]) -> str:
    return "    $InitializeEvent(" + ", ".join((str(slot), str(event_id), *arguments)) + ");"


def _portable_attachments(donor: CombatPackage) -> tuple[EventAttachment, ...]:
    """Derive importable combat bodies from package structure, not arena pairs."""
    if donor.attachments:
        return donor.attachments
    if donor.part_routine_event is not None:
        if len(donor.phase_events) != 1 or not donor.part_bindings:
            raise ValueError(f"{donor.key} lacks an appendable phase/body shape")
        return (
            EventAttachment(donor.phase_events[0], (PartBinding(0, ()),)),
            EventAttachment(donor.part_routine_event, donor.part_bindings),
        )
    if not donor.phase_events:
        raise ValueError(f"{donor.key} lacks source combat attachments")
    return tuple(EventAttachment(event_id, (PartBinding(0, ()),))
                 for event_id in donor.phase_events)


def _validate_ids(ids: MariaArenaIds, destination: str) -> None:
    if len(ids.attachment_events) != 5:
        raise ValueError("Maria arena requires five attachment event IDs")
    values = ids.values()
    if (any(value <= 0 for value in values) or len(set(values)) != len(values)
            or set(values).intersection(_original_literals() | _numbers(destination))):
        raise ValueError("Maria arena allocation collides with original corpus")


def _validate_signal(donor: CombatPackage, signal: MusicPhaseSignal,
                     donor_blocks: Mapping[int, str], targets: Mapping[int, int]) -> None:
    block = donor_blocks.get(signal.source_event)
    if block is None:
        raise ValueError(f"{donor.key} music signal lacks its source event")
    if signal.kind == "event_flag":
        if signal.message is not None or signal.source_event not in targets:
            raise ValueError(f"{donor.key} event-flag signal is not an imported combat event")
        return
    if signal.kind == "message" and signal.message is not None:
        witness = f"CharacterHasEventMessage({donor.actor}, {signal.message})"
        if witness in block:
            return
    raise ValueError(f"{donor.key} music signal lacks a pinned source witness")


def _signal_condition(donor: CombatPackage, signal: MusicPhaseSignal,
                      targets: Mapping[int, int]) -> str:
    if signal.kind == "event_flag":
        return f"EventFlag({targets[signal.source_event]})"
    assert signal.message is not None
    return f"CharacterHasEventMessage({MARIA_ARENA_CONTRACT.actor}, {signal.message})"


def _music(block: str, donor: CombatPackage, donor_blocks: Mapping[int, str],
           targets: Mapping[int, int]) -> str:
    signals = donor.music_phase_signals
    if len(signals) not in (1, 2):
        raise ValueError(f"{donor.key} does not declare one or two Maria music signals")
    for signal in signals:
        _validate_signal(donor, signal, donor_blocks, targets)
    first = "        chrFlagArea &= CharacterHasEventMessage(3500800, 100);\n"
    second = "        chrFlagArea2 &= CharacterHasEventMessage(3500800, 300);\n"
    if len(signals) == 2:
        block = _replace_once(
            block, first,
            f"        chrFlagArea &= {_signal_condition(donor, signals[0], targets)};\n",
            "Maria first music gate",
        )
        return _replace_once(
            block, second,
            f"        chrFlagArea2 &= {_signal_condition(donor, signals[1], targets)};\n",
            "Maria second music gate",
        )

    # A one-boundary donor cannot honestly synthesize Maria's second combat
    # phase.  Reuse the source-backed opening predicate, retain all destination
    # completion/co-op/area/SFX operations, and move directly to Maria's final
    # track at that single boundary.
    block = _replace_once(
        block, first,
        f"        chrFlagArea &= {_signal_condition(donor, signals[0], targets)};\n",
        "Maria one-phase music gate",
    )
    l0 = block.find("L0:\n")
    gate = block.find(second)
    l1 = block.find("L1:\n", gate)
    if l0 < 0 or gate < l0 or l1 < gate or block.count("L0:\n") != 1:
        raise ValueError("Maria music lacks the pinned two-stage transition structure")
    direct = block[l0:gate].replace("chrFlagArea2", "chrFlagArea")
    direct = _replace_once(
        direct,
        "    EnableBossMapSound(3503803, Enabled);\n",
        "    EnableBossMapSound(3503804, Enabled);\n",
        "Maria intermediate music enable",
    )
    if "    SetEventFlag(13504811, ON);\n" not in direct:
        raise ValueError("Maria music lacks its destination phase/SFX marker")
    # Keep Maria's outer L1 branch.  It is the original active-fight reload
    # recovery: after ThisEvent it rebuilds the area/co-op predicate and
    # restores the final track.  The second donor phase no longer exists, so
    # the original message-300 wait becomes the destination phase marker set
    # by the one source-backed boundary above.
    return (
        block[:l0]
        + direct
        + "        chrFlagArea2 &= EventFlag(13504811);\n    }\n"
        + block[l1:]
    )


def _constructor(arena_zero: str, donor_zero: str, donor: CombatPackage,
                 attachments: Sequence[EventAttachment], targets: Mapping[int, int],
                 virtual_targets: Mapping[int, int], activation_event: int,
                 owner_cleanup_event: int | None) -> str:
    calls: list[str] = [_initializer(0, activation_event, ())]
    for attachment in attachments:
        for binding in attachment.initializers:
            witness = _initializer(binding.slot, attachment.source_event, binding.arguments)
            if donor_zero.count(witness) != 1:
                raise ValueError(f"{donor.key} Event(0) lacks a unique initializer witness")
            calls.append(_initializer(binding.slot, targets[attachment.source_event], binding.arguments))
    for binding in donor.virtual_entities:
        witness = f"    {binding.initializer}({binding.source_entity});"
        if donor_zero.count(witness) != 1:
            raise ValueError(f"{donor.key} Event(0) lacks a unique virtual-owner witness")
        calls.append(f"    {binding.initializer}({virtual_targets[binding.source_entity]});")
    if owner_cleanup_event is not None:
        calls.append(_initializer(0, owner_cleanup_event, ()))
    anchor = "    $InitializeEvent(0, 13504822);"
    return _replace_once(arena_zero, anchor, "\n".join(calls), "Maria cleanup initializer")


def _telemetry(block: str, owner: str) -> str:
    match = re.search(
        r"(?m)^    CreatePlaylog\(\d+\);\n"
        r"    StartTimeMeasurement\(\d+, \d+, Enabled\);$",
        block,
    )
    if match is None:
        raise ValueError(f"{owner} health lacks one playlog/time witness")
    return match[0]


def _event_flags(block: str) -> set[int]:
    """All EMEVD event-flag operands, including writes.

    A read-only scan misses ``SetEventFlag(id, ON)`` and can let a donor-map
    notification flag leak into a destination health controller.
    """
    return {
        int(value)
        for value in re.findall(r"\b(?:EventFlag|SetEventFlag)\((\d+)(?:\)|,)", block)
    }


def _maria_notification(block: str, donor: CombatPackage) -> str:
    """Keep donor network authority but make room-entry state Maria-owned."""
    actor = MARIA_ARENA_CONTRACT.actor
    authority = re.search(
        rf"(?m)^(?P<indent>[ \t]*)(?P<line>SetNetworkUpdateAuthority\({actor}, "
        r"AuthorityLevel\.(?:Forced|Normal)\);)$",
        block,
    )
    if authority is None:
        raise ValueError(f"{donor.key} health lacks one source network-authority witness")
    if len(re.findall(r"SetNetworkUpdateAuthority\(", block)) != 1:
        raise ValueError(f"{donor.key} health has ambiguous network-authority witnesses")
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    client_start = block.rfind(client, 0, authority.start())
    if client_start < 0:
        raise ValueError(f"{donor.key} health lacks a client notification branch")
    line_start = block.rfind("\n", 0, client_start) + 1
    indent = block[line_start:client_start]
    close = block.find("\n" + indent + "}", authority.end())
    if close < 0:
        raise ValueError(f"{donor.key} health lacks a closed client notification branch")
    replacement = (
        f"{indent}if (!HasMultiplayerState(MultiplayerState.Client)) {{\n"
        f"{indent}    if (!EventFlag(13504810)) {{\n"
        f"{indent}        IssueBossRoomEntryNotification(0);\n"
        f"{indent}    }}\n"
        f"{indent}    {authority['line']}\n"
        f"{indent}}}"
    )
    return block[:line_start] + replacement + block[close + len("\n" + indent + "}"):]


def _health(destination: str, donor_block: str, donor: CombatPackage,
            activation_event: int) -> str:
    """Use the donor's complete health/co-op lifecycle with Maria telemetry.

    The donor owns forced/normal authority, co-op HP effect arguments, and any
    post-enable combat animation.  Maria retains only its local playlog and
    time-measurement identities.  This intentionally avoids a label-only swap.
    """
    result = _remap(donor_block, {
        donor.actor: MARIA_ARENA_CONTRACT.actor,
        donor.completion_event: MARIA_ARENA_CONTRACT.completion_event,
        donor.start_flag: MARIA_ARENA_CONTRACT.start_flag,
        donor.health_bar_event: MARIA_ARENA_CONTRACT.health_bar_event,
    })
    result = _maria_notification(result, donor)
    # Donor health bodies sometimes offer a second source-arena entry flag.
    # Maria has one reviewed entry boundary, so replace the first ``WaitFor``
    # inside its ``!ThisEvent`` setup rather than carrying an unbound source
    # flag across maps.
    result, replacements = re.subn(
        r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
        lambda match: match[1] + f"        WaitFor(EventFlag({activation_event}));",
        result,
        count=1,
    )
    if replacements == 0:
        # Amygdala's original health controller has no ``ThisEvent`` branch;
        # its sole start-flag wait is still the exact readiness boundary to
        # replace after its source flag is mapped to Maria's start flag.
        result = _replace_once(
            result,
            f"    WaitFor(EventFlag({MARIA_ARENA_CONTRACT.start_flag}));",
            f"    WaitFor(EventFlag({activation_event}));",
            "Maria unconditional donor-readiness gate",
        )
    elif replacements != 1:
        raise ValueError("Maria donor health has ambiguous entry readiness waits")
    result = _replace_once(
        result,
        f"    SetEventFlag({MARIA_ARENA_CONTRACT.start_flag}, ON);",
        f"    SetEventFlag({MARIA_ARENA_CONTRACT.start_flag}, ON);\n"
        "    SetEventFlag(13504810, ON);",
        "Maria room-entry state",
    )
    foreign_flags = _event_flags(donor_block) - {donor.completion_event, donor.start_flag}
    for flag in foreign_flags:
        result, removed = re.subn(
            rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result,
        )
        if removed > 1:
            raise ValueError(f"{donor.key} health has repeated foreign flag writes {flag}")
    donor_telemetry = _telemetry(result, donor.key)
    result = _replace_once(
        result,
        donor_telemetry,
        _telemetry(destination, "Maria"),
        "destination telemetry replacement",
    )
    # Maria's original health lifecycle clears the entrance protection before
    # handing combat to AI.  Donor health bodies do not all carry that line,
    # so retain the destination operation after the donor readiness gate and
    # immediately before its source-owned AI-enable operation.
    result = _replace_once(
        result,
        f"    SetCharacterAIState({MARIA_ARENA_CONTRACT.actor}, Enabled);",
        f"    SetCharacterInvincibility({MARIA_ARENA_CONTRACT.actor}, Disabled);\n"
        f"    SetCharacterAIState({MARIA_ARENA_CONTRACT.actor}, Enabled);",
        "Maria post-readiness invincibility clear",
    )
    retained = foreign_flags.intersection(_event_flags(result))
    if retained:
        raise ValueError(f"{donor.key} health retained foreign local flags {sorted(retained)}")
    return result


def _source_witnesses(block: str, donor: CombatPackage, witnesses: Sequence[str]) -> None:
    for witness in witnesses:
        if block.count(witness) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {witness}")


def _activation(donor: CombatPackage, donor_blocks: Mapping[int, str], event_id: int) -> str:
    """Adapt a donor's original wake lifecycle to Maria's completed entry.

    Maria owns the player/cinematic trigger.  The source's former area, radius,
    or damage trigger is therefore replaced by its already-pinned post-entry
    flag.  Every copied combat-state operation is witnessed in the donor's
    original activation event.  Maria's health event waits for this event,
    keeping AI and the health bar disabled through the wake sequence.
    """
    source = donor_blocks[donor.activation_event]
    actor = MARIA_ARENA_CONTRACT.actor
    start = MARIA_ARENA_CONTRACT.start_flag
    prefix = f"""$Event({event_id}, Default, function() {{
    EndIf(EventFlag(13501800));
    EndIf(ThisEvent());
"""
    suffix = "\n});"
    profile = donor.activation_profile
    if profile == "host-entry-animation":
        _source_witnesses(source, donor, (
            "ForceAnimationPlayback(2300800, 7001, false, false, false);",
        ))
        return prefix + f"""    WaitFor(EventFlag({start}));
    ForceAnimationPlayback({actor}, 7001, false, false, false);""" + suffix
    if profile == "protected-radius-wake":
        _source_witnesses(source, donor, (
            "SetCharacterInvincibility(2300810, Enabled);",
            "ForceAnimationPlayback(2300810, 7000, true, false, false);",
            "ForceAnimationPlayback(2300810, 7001, false, false, false);",
            "WaitFixedTimeFrames(70);",
            "SetCharacterInvincibility(2300810, Disabled);",
        ))
        return prefix + f"""    SetCharacterInvincibility({actor}, Enabled);
    ForceAnimationPlayback({actor}, 7000, true, false, false);
    WaitFor(EventFlag({start}));
    ForceAnimationPlayback({actor}, 7001, false, false, false);
    WaitFixedTimeFrames(70);
    SetCharacterInvincibility({actor}, Disabled);""" + suffix
    if profile == "gravity-warp-wake":
        _source_witnesses(source, donor, (
            "ChangeCharacterEnableState(2410800, Disabled);",
            "SetCharacterGravity(2410800, Disabled);",
            "SetCharacterMaphits(2410800, true);",
            "ForceAnimationPlayback(2410800, 3028, false, false, false);",
            "WaitFixedTimeFrames(110);",
            "SetCharacterGravity(2410800, Enabled);",
            "SetCharacterMaphits(2410800, false);",
        ))
        return prefix + f"""    ChangeCharacterEnableState({actor}, Disabled);
    SetCharacterGravity({actor}, Disabled);
    SetCharacterMaphits({actor}, true);
    WaitFor(EventFlag({start}));
    ChangeCharacterEnableState({actor}, Enabled);
    ForceAnimationPlayback({actor}, 3028, false, false, false);
    WaitFixedTimeFrames(110);
    SetCharacterGravity({actor}, Enabled);
    SetCharacterMaphits({actor}, false);""" + suffix
    if profile == "object-gated-wake":
        _source_witnesses(source, donor, (
            "ChangeCharacterEnableState(2400800, Disabled);",
            "ForceAnimationPlayback(2400800, 7000, false, false, false);",
            "ForceAnimationPlayback(2400800, 7001, false, false, false);",
        ))
        return prefix + f"""    ChangeCharacterEnableState({actor}, Disabled);
    WaitFor(EventFlag({start}));
    ChangeCharacterEnableState({actor}, Enabled);
    ForceAnimationPlayback({actor}, 7000, false, false, false);
    ForceAnimationPlayback({actor}, 7001, false, false, false);""" + suffix
    if profile == "protected-area-wake":
        _source_witnesses(source, donor, (
            "SetCharacterMaphits(3300800, true);",
            "SetCharacterGravity(3300800, Disabled);",
            "SetCharacterInvincibility(3300800, Enabled);",
            "ForceAnimationPlayback(3300800, 7003, true, false, false);",
            "ForceAnimationPlayback(3300800, 7006, false, false, false);",
            "WaitFixedTimeFrames(30);",
            "ForceAnimationPlayback(3300800, 7002, false, false, false);",
            "WaitFixedTimeFrames(160);",
            "SetCharacterGravity(3300800, Enabled);",
            "SetCharacterInvincibility(3300800, Disabled);",
            "SetCharacterMaphits(3300800, false);",
        ))
        return prefix + f"""    SetCharacterMaphits({actor}, true);
    SetCharacterGravity({actor}, Disabled);
    SetCharacterInvincibility({actor}, Enabled);
    ForceAnimationPlayback({actor}, 7003, true, false, false);
    WaitFor(EventFlag({start}));
    ForceAnimationPlayback({actor}, 7006, false, false, false);
    WaitFixedTimeFrames(30);
    ForceAnimationPlayback({actor}, 7002, false, false, false);
    WaitFixedTimeFrames(160);
    SetCharacterGravity({actor}, Enabled);
    SetCharacterInvincibility({actor}, Disabled);
    SetCharacterMaphits({actor}, false);""" + suffix
    if profile == "first-damage-wake":
        _source_witnesses(source, donor, (
            "ForceAnimationPlayback(2420800, 7001, true, false, false);",
            "SetCharacterImmortality(2420800, Enabled);",
            "SetSpEffect(2420800, 5647, false);",
            "HasDamageType(2420800, 10000, DamageType.Unspecified)",
            "ForceAnimationPlayback(2420800, 7000, false, true, false);",
            "SetCharacterImmortality(2420800, Disabled);",
            "ClearSpEffect(2420800, 5647);",
        ))
        return prefix + f"""    ForceAnimationPlayback({actor}, 7001, true, false, false);
    SetCharacterImmortality({actor}, Enabled);
    SetSpEffect({actor}, 5647, false);
    WaitFor(EventFlag({start}));
    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));
    ForceAnimationPlayback({actor}, 7000, false, true, false);
    SetCharacterImmortality({actor}, Disabled);
    ClearSpEffect({actor}, 5647);""" + suffix
    raise ValueError(f"Maria arena has no readiness adapter for {donor.key}/{profile}")


def _owner_cleanup(ids: MariaArenaIds) -> str:
    return f"""$Event({ids.owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(13501800));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""


def maria_arena_contract(donor: CombatPackage, ids: MariaArenaIds = DEFAULT_IDS) -> dict:
    """Describe the reusable target boundary for a selected portable donor."""
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Maria's five declared attachment IDs")
    helper_cleanup = bool(donor.virtual_entities)
    added_events = [ids.activation_event]
    if helper_cleanup:
        added_events.append(ids.owner_cleanup_event)
    return {
        "format": "bb-maria-arena-contract-v1",
        "status": "experimental",
        "arena": MARIA_ARENA_CONTRACT.key,
        "donor": donor.key,
        "allocation": asdict(ids),
        "preserved_destination_events": [13501800, 13501801, 13501807, 13504800, 13504801, 13504805, 13504806, 13504807],
        "retired_destination_controllers": list(MARIA_ARENA_CONTRACT.retired_combat_events),
        "readiness_adapter": {
            "source_event": donor.activation_event,
            "profile": donor.activation_profile,
            "destination_event": ids.activation_event,
            "trigger": f"EventFlag({MARIA_ARENA_CONTRACT.start_flag})",
            "camera_policy": "destination-m35-geometry",
            "source_lockcam_event": donor.lockcam_event,
        },
        "removed_destination_reference": {
            "event": 13504802,
            "literal": 3500801,
            "witness": "SetCharacterEventTarget(3500800, 3500801)",
        },
        "music_policy": "two-boundary donors map both Maria gates; one-boundary donors move opening directly to final Maria track",
        "attachments": [
            {"source_event": attachment.source_event, "destination_event": ids.attachment_events[index],
             "initializers": [asdict(binding) for binding in attachment.initializers]}
            for index, attachment in enumerate(attachments)
        ],
        "added_event_ids": added_events,
        "helper_cleanup": ids.owner_cleanup_event if helper_cleanup else None,
        "runtime_status": "unobserved",
    }


def patch_portable_donor_at_maria(destination: str, donor: CombatPackage, donor_source: str,
                                   ids: MariaArenaIds = DEFAULT_IDS) -> str:
    """Install one base CombatPackage while retaining Maria-owned progression."""
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_maria(original)
    _verify_donor(donor_blocks, donor)
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Maria's attachment capacity")
    targets = {attachment.source_event: ids.attachment_events[index]
               for index, attachment in enumerate(attachments)}
    virtual_targets = {binding.source_entity: ids.bullet_owner_entity
                       for binding in donor.virtual_entities}
    if len(virtual_targets) > len(MARIA_ARENA_CONTRACT.virtual_entity_ids):
        raise ValueError(f"{donor.key} exceeds Maria's virtual-entity capacity")
    mapping = {
        donor.actor: MARIA_ARENA_CONTRACT.actor,
        donor.completion_event: MARIA_ARENA_CONTRACT.completion_event,
        donor.start_flag: MARIA_ARENA_CONTRACT.start_flag,
        **targets,
        **virtual_targets,
    }
    additions = [_remap(donor_blocks[attachment.source_event], mapping)
                 for attachment in attachments]
    edits = {
        0: _constructor(original[0], donor_blocks[0], donor, attachments, targets,
                        virtual_targets, ids.activation_event,
                        ids.owner_cleanup_event if donor.virtual_entities else None),
        13504802: _health(original[13504802], donor_blocks[donor.health_bar_event], donor,
                           ids.activation_event),
        13504803: _music(original[13504803], donor, donor_blocks, targets),
        13504822: _noop(original[13504822]),
    }
    additions.append(_activation(donor, donor_blocks, ids.activation_event))
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    expected_ids = set(original).union(targets.values(), {ids.activation_event})
    if donor.virtual_entities:
        expected_ids.add(ids.owner_cleanup_event)
    if set(output) != expected_ids:
        raise ValueError(
            "Maria arena changed unexpected event identities: "
            f"extra={sorted(set(output) - expected_ids)} "
            f"missing={sorted(expected_ids - set(output))}"
        )
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Maria arena changed unrelated destination event {event_id}")
    if output[13501800] != original[13501800]:
        raise ValueError("Maria arena changed completion/progression")
    if output[13501801] != original[13501801] or output[13501807] != original[13501807]:
        raise ValueError("Maria arena changed entrance/cinematic ownership")
    return result


def native_plan_portable_donor_at_maria(donor: CombatPackage, slots: Sequence[Slot],
                                         npcs: Mapping[int, dict], effects: Mapping[int, dict],
                                         seed: str, ids: MariaArenaIds = DEFAULT_IDS) -> dict:
    """Build native map/scaling requirements without registering Maria globally."""
    _validate_ids(ids, "")
    destinations = [slot for slot in slots if slot.entity_id == MARIA_ARENA_CONTRACT.actor
                    and slot.archetype == MARIA_ARENA_CONTRACT.archetype]
    donors = [slot for slot in slots if slot.entity_id == donor.actor
              and slot.archetype == donor.archetype and slot.map_name.endswith("_00")]
    if (len(destinations) != 1 or len(donors) != 1 or destinations[0].dummy
            or destinations[0].talk_id or destinations[0].archetype.chara_init_id):
        raise ValueError(f"Maria/{donor.key} requires one pinned ordinary source and destination")
    target = destinations[0]
    swap = Swap(
        target.logical_key, [target.key], {target.key: target.archetype}, target.archetype,
        donor.archetype, destinations={target.key: {"map_name": target.map_name,
        "entity_id": target.entity_id, "x": target.x, "y": target.y, "z": target.z}},
    )
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    plan = {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"lady-maria<-{donor.key}"},
        "boss_contract": maria_arena_contract(donor, ids),
        "primary_init_source_bindings": primary_initialization_requirements(
            MARIA_ARENA_CONTRACT, donor, list(slots)),
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
    requirements = actor_addition_requirements(MARIA_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan


def portable_maria_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    """Return packages structurally eligible for Maria; Maria itself is excluded."""
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if (donor.music_phase_signals and len(attachments) <= len(ATTACHMENT_EVENTS)
                    and len(donor.virtual_entities) <= 1):
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)
