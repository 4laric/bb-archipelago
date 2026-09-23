"""Reusable source-pinned Micolash destination arena.

The replacement combat stays at Micolash's original initial spawn, inside the
original fight and music volumes.  Micolash's chase, teleport, room, talk and
Ezstate controllers remain initialized but wait forever without setting their
``ThisEvent`` flags.  This preserves the destination terminal and post-boss
flag graph while replacing the chase with the donor's complete combat package.

The direct-fight geometry and navigation fit is source-backed but not runtime
observed.
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
    PACKAGES, ArenaContract, Archetype, CombatPackage, EventAttachment,
    actor_addition_requirements,
)
from .gehrman_micolash_contract import ARENA_HASHES, CHASE_EVENTS, MICOLASH_PIN
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m26_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m26_00_"
DESTINATION_MAP = "m26_00_00_00"
PRIMARY = 2600850
PRIMARY_ARCHETYPE = Archetype("c0000", 6380, 6380, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12996300, 12996301, 12996302, 12996303, 12996304)
ACTIVATION_EVENT = 12996305
TERMINAL_BRIDGE_EVENT = 12996306
DONOR_OWNER_CLEANUP_EVENT = 12996307
BULLET_OWNER_ENTITY = 983800
DESTINATION_MSB_SHA256 = "af32f7e1038cfd52dbf3b9f073ac1f25f47422230a4cfad3d35d62517d825919"
SOURCE_PART_PINS = {
    ("m23_00_00_00", 2300800): "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
    ("m23_00_00_01", 2300800): "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
    ("m23_00_00_00", 2300810): "cac704506e58dfd3f2c57113d919fafe0a70d01b7a40b869deffa3c6e22cc0a2",
    ("m23_00_00_01", 2300810): "6c8a693b9c846922a1113726ec69a11b47973c5e367a94757ad82d3fbf3081ee",
    ("m24_01_00_00", 2410800): "0225c170ffac0c48d69f996e361b83c5490069e4a75fdc6b19328458f2fd3848",
    ("m24_01_00_01", 2410800): "34c019e726003bf86523ef384e74c2fb050c4d7d82ab8012ddfc8ba42d6f0940",
    ("m24_01_00_11", 2410800): "a8ca2f725b4e7d1c823912bbb0131a17dfba84d50f0c2713b820db78bc8722b3",
    ("m24_00_00_00", 2400800): "99f32c1296938362bd6d5abbcc073f6179fd9173f18a3a5076391d37ff88c35e",
    ("m24_00_00_01", 2400800): "ba04891b13b4fff5ad61eebf53c4715c89ef70e9599025d4335cb558b808a4e5",
    ("m33_00_00_00", 3300800): "4d66ca60f567e2f0ba0ffcc43fb45c5666265fd9649952cc3828185f0ef1bc39",
    ("m24_02_00_00", 2420800): "5f6ed3a557a24f54151a77bc3de15ce5f8d8645d6ad5cafc94fe4449b91ce5c2",
    ("m24_02_00_01", 2420800): "6e96e026cb750d840a621e27ec07658b9953c62b061c79ca8d5b95227c87dcbb",
}
SOURCE_INITIALIZATION = {"talk_id": 0, "unk_t18": -1,
                         "init_anim_id": -1, "damage_anim_id": -1}
SOURCE_ZERO_HASHES = {
    "blood-starved-beast": "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    "darkbeast-paarl": "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    "cleric-beast": "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    "vicar-amelia": "31936ed53ff8d095dcae5257c6d36e321a55bc8cd53ed564a1510363a9a04e27",
    "amygdala": "b86f288c46fc74ddc81530e62437d9497c5a63ec09488c068211d85f4054f934",
    "ebrietas": "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
}

MICOLASH_ARENA_CONTRACT = ArenaContract(
    key="micolash", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=PRIMARY, archetype=PRIMARY_ARCHETYPE, destination_count=1,
    completion_event=12601850, start_flag=12604850,
    health_bar_event=12604852, health_bar_label=899000,
    activation_event=12601852, music_event=12604853,
    phase_music_message=None, lockcam_event=12604854,
    lockcam_map=26, lockcam_subarea=0, phase_slots=(),
    co_op_entry_event=12601855, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=12604855, expected=ARENA_HASHES,
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=CHASE_EVENTS,
    activation_profile="normalized-cinematic",
)


@dataclass(frozen=True)
class MicolashArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    activation_event: int = ACTIVATION_EVENT
    terminal_bridge_event: int = TERMINAL_BRIDGE_EVENT
    donor_owner_cleanup_event: int = DONOR_OWNER_CLEANUP_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.activation_event,
                self.terminal_bridge_event, self.donor_owner_cleanup_event,
                self.bullet_owner_entity)


DEFAULT_IDS = MicolashArenaIds()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str | tuple[str, ...]], role: str) -> None:
    for event_id, digests in expected.items():
        body = blocks.get(event_id)
        allowed = (digests,) if isinstance(digests, str) else digests
        if body is None or hashlib.sha256(body.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _validate_ids(ids: MicolashArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Micolash arena IDs must be unique positive project IDs")
    event_ids = {*ids.attachment_events, ids.activation_event,
                 ids.terminal_bridge_event, ids.donor_owner_cleanup_event}
    if event_ids != set(range(12996300, 12996308)) or ids.bullet_owner_entity != 983800:
        raise ValueError("Micolash arena requires the exact reviewed narrow allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Micolash arena IDs collide with original inputs: {sorted(collisions)}")


def _inert(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    # Region 0 is the original permanent-wait idiom.  It leaves ThisEvent
    # unset, including 12604879 which destination post-boss logic observes.
    return declaration + "\n    WaitFor(InArea(10000, 0));\n    EndEvent();\n});"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Micolash arena expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap(block: str, mapping: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(mapping.get(int(match[0]), int(match[0]))), block)


def _initializer(slot: int, event_id: int, arguments: tuple[str, ...]) -> str:
    return f"    $InitializeEvent({slot}, {event_id}" + (", " + ", ".join(arguments) if arguments else "") + ");"


def _portable_attachments(donor: CombatPackage) -> tuple[EventAttachment, ...]:
    if donor.attachments:
        return donor.attachments
    if donor.part_routine_event is not None:
        if len(donor.phase_events) != 1 or not donor.part_bindings:
            raise ValueError(f"{donor.key} lacks an appendable phase/body shape")
        from .boss_contracts import PartBinding
        return (EventAttachment(donor.phase_events[0], (PartBinding(0, ()),)),
                EventAttachment(donor.part_routine_event, donor.part_bindings))
    if not donor.phase_events:
        raise ValueError(f"{donor.key} lacks source combat attachments")
    from .boss_contracts import PartBinding
    return tuple(EventAttachment(event_id, (PartBinding(0, ()),))
                 for event_id in donor.phase_events)


def _constructor(arena_zero: str, donor_zero: str, donor: CombatPackage,
                 attachments: Sequence[EventAttachment], targets: Mapping[int, int],
                 virtual_targets: Mapping[int, int], ids: MicolashArenaIds) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 12604855);"
    lines: list[str] = []
    for attachment in attachments:
        target = targets[attachment.source_event]
        for binding in attachment.initializers:
            witness = _initializer(binding.slot, attachment.source_event, binding.arguments)
            if donor_zero.count(witness) != 1:
                raise ValueError(f"{donor.key} Event(0) lacks unique attachment initializer")
            args = tuple(str(_remap(arg, {donor.actor: PRIMARY, **virtual_targets}))
                         for arg in binding.arguments)
            lines.append(_initializer(binding.slot, target, args))
    for binding in donor.virtual_entities:
        witness = f"    {binding.initializer}({binding.source_entity});"
        if donor_zero.count(witness) != 1:
            raise ValueError(f"{donor.key} Event(0) lacks unique virtual-owner witness")
        lines.append(f"    {binding.initializer}({virtual_targets[binding.source_entity]});")
    lines.extend((_initializer(0, ids.activation_event, ()),
                  _initializer(0, ids.terminal_bridge_event, ())))
    if donor.virtual_entities:
        lines.append(_initializer(0, ids.donor_owner_cleanup_event, ()))
    result = _replace_once(result, anchor, anchor + "\n" + "\n".join(lines),
                           "constructor anchor")
    header = result.splitlines()[0] + "\n"
    return _replace_once(
        result, header,
        header + f"    SetEventFlag({ids.activation_event}, OFF);\n",
        "constructor readiness reset",
    )


def _telemetry(block: str, owner: str) -> str:
    match = re.search(r"(?m)^    CreatePlaylog\([^\n]+\);\n    StartTimeMeasurement\([^\n]+\);", block)
    if match is None or len(re.findall(r"CreatePlaylog\(", block)) != 1:
        raise ValueError(f"{owner} health lacks unique telemetry")
    return match[0]


def _health(destination: str, source: str, donor: CombatPackage, ready_event: int) -> str:
    result = _remap(source, {donor.actor: PRIMARY, donor.completion_event: 12601850,
                             donor.start_flag: 12604850,
                             donor.health_bar_event: 12604852})
    authority = re.search(
        r"(?m)^\s*SetNetworkUpdateAuthority\(2600850, AuthorityLevel\.(?:Forced|Normal)\);$",
        result,
    )
    if authority is None:
        raise ValueError(f"{donor.key} health lacks authority witness")
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    start = result.rfind(client, 0, authority.start())
    line_start = result.rfind("\n", 0, start) + 1
    indent = result[line_start:start]
    close = result.find("\n" + indent + "}", authority.end())
    if start < 0 or close < 0:
        raise ValueError(f"{donor.key} health lacks client branch")
    # Entry 12601852 owns the room notification before setting the start flag.
    replacement = (f"{indent}{client}\n"
                   f"{indent}    {authority[0].strip()}\n{indent}}}")
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    result, count = re.subn(r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
                            lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));", result, count=1)
    if count == 0:
        result = _replace_once(result, "    WaitFor(EventFlag(12604850));",
                               f"    WaitFor(EventFlag({ready_event}));", "health readiness")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(
        result, "L0:\n    SetEventFlag(12604850, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n"
        "    SetEventFlag(12604850, ON);",
        "saved-health readiness",
    )
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Micolash"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result


def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")


def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 12604850
    prefix = (f"$Event({event_id}, Default, function() {{\n"
              "    EndIf(EventFlag(12601850));\n"
              "    EndIf(ThisEvent());\n"
              f"    SetCharacterInvincibility({actor}, Enabled);\n")
    suffix = "\n});"
    profile = donor.activation_profile
    if profile == "host-entry-animation":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);",))
        body = (f"    WaitFor(EventFlag({flag}));\n"
                f"    ForceAnimationPlayback({actor}, 7001, false, false, false);\n"
                f"    SetCharacterInvincibility({actor}, Disabled);")
    elif profile == "protected-radius-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, true, false, false);", "WaitFixedTimeFrames(70);"))
        body = f"    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif profile == "gravity-warp-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 3028, false, false, false);", "WaitFixedTimeFrames(110);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterMaphits({actor}, true);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 3028, false, false, false);\n    WaitFixedTimeFrames(110);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterMaphits({actor}, false);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif profile == "object-gated-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, false, false, false);", f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, false, false, false);\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif profile == "protected-area-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7003, true, false, false);", "WaitFixedTimeFrames(160);"))
        body = f"    SetCharacterMaphits({actor}, true);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7003, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7006, false, false, false);\n    WaitFixedTimeFrames(30);\n    ForceAnimationPlayback({actor}, 7002, false, false, false);\n    WaitFixedTimeFrames(160);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterInvincibility({actor}, Disabled);\n    SetCharacterMaphits({actor}, false);"
    elif profile == "first-damage-wake":
        _witnesses(source, donor, (f"SetCharacterImmortality({donor.actor}, Enabled);", f"HasDamageType({donor.actor}, 10000, DamageType.Unspecified)"))
        body = f"    ForceAnimationPlayback({actor}, 7001, true, false, false);\n    SetCharacterImmortality({actor}, Enabled);\n    SetSpEffect({actor}, 5647, false);\n    WaitFor(EventFlag({flag}));\n    SetCharacterInvincibility({actor}, Disabled);\n    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({actor}, 7000, false, true, false);\n    SetCharacterImmortality({actor}, Disabled);\n    ClearSpEffect({actor}, 5647);"
    else:
        raise ValueError(f"Micolash arena lacks readiness adapter for {donor.key}/{profile}")
    return prefix + body + suffix


def _signal_condition(donor: CombatPackage, blocks: Mapping[int, str], targets: Mapping[int, int]) -> str:
    signal = donor.music_phase_signals[-1]
    source = blocks[signal.source_event]
    if signal.kind == "message" and signal.message is not None:
        witness = f"CharacterHasEventMessage({donor.actor}, {signal.message})"
        if witness not in source:
            raise ValueError(f"{donor.key} lacks final music message witness")
        return f"CharacterHasEventMessage({PRIMARY}, {signal.message})"
    if signal.kind == "event_flag" and signal.source_event in targets:
        return f"EventFlag({targets[signal.source_event]})"
    raise ValueError(f"{donor.key} final music boundary is not portable")


def _music(block: str, donor: CombatPackage, donor_blocks: Mapping[int, str], targets: Mapping[int, int]) -> str:
    condition = _signal_condition(donor, donor_blocks, targets)
    return _replace_once(block, "        WaitFor(EventFlag(72600300));",
                         f"        WaitFor({condition});", "phase music boundary")


CAMERA_EVENTS = {"blood-starved-beast": 12304804}


def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {event_id: 12604854, donor.actor: PRIMARY,
               donor.completion_event: 12601850, donor.start_flag: 12604850}
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 12604851
    result = _remap(source, mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(\d+, \d+,",
                            "SetLockcamSlotNumber(26, 0,", result)
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = "    EndIf(EventFlag(12601850));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(result, header, header + guard,
                               "destination camera completion guard")
    return result


def _terminal_bridge(ids: MicolashArenaIds) -> str:
    return f"""$Event({ids.terminal_bridge_event}, Default, function() {{
    EndIf(EventFlag(12601850));
    SetEventFlag(72600301, OFF);
    WaitFor(CharacterDead({PRIMARY}));
    SetEventFlag(72600301, ON);
}});"""


def _owner_cleanup(ids: MicolashArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12601850));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""


def micolash_arena_contract(donor: CombatPackage, ids: MicolashArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    targets = dict(zip((row.source_event for row in attachments), ids.attachment_events))
    return {
        "format": "bb-micolash-arena-contract-v1",
        "arena": "micolash", "donor": donor.key,
        "status": "planned", "writer_status": "not_integrated",
        "runtime_status": "unobserved",
        "placement_policy": "original-initial-area-direct-fight",
        "placement_evidence": "actor2600850 at (176.82,1037.98,-37.82) inside original fight/music volumes2602851/2602852",
        "attachments": [{"source_event": row.source_event,
                         "destination_event": targets[row.source_event]}
                        for row in attachments],
        "activation_event": ids.activation_event,
        "terminal_bridge_event": ids.terminal_bridge_event,
        "preserved_destination_events": [12601850, 12601852, 12601854,
                                         12601855, 12604855, 12604860,
                                         12604861],
        "adapted_destination_events": [12604852, 12604853, 12604854,
                                       *CHASE_EVENTS],
        "terminal_policy": "byte-identical terminal; bridge opens talk-owned72600301 only after actual donor death",
        "disabled_destination_chase_events": list(CHASE_EVENTS),
        "source_hash_pins": dict(donor.expected),
        "arena_hash_pins": dict(ARENA_HASHES),
        "destination_native_evidence": {
            "map": DESTINATION_MAP, "msb_sha256": DESTINATION_MSB_SHA256,
            "primary_entity": PRIMARY, "primary_part_sha256": MICOLASH_PIN,
            "original_talk_id": 260311,
        },
    }


def patch_portable_donor_at_micolash(destination: str, donor: CombatPackage,
                                     donor_source: str,
                                     ids: MicolashArenaIds = DEFAULT_IDS) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Micolash arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Micolash attachment capacity")
    targets = dict(zip((row.source_event for row in attachments), ids.attachment_events))
    virtual_targets = dict(zip((row.source_entity for row in donor.virtual_entities),
                               (ids.bullet_owner_entity,)))
    if len(virtual_targets) != len(donor.virtual_entities):
        raise ValueError(f"{donor.key} exceeds Micolash virtual-entity capacity")
    remap = {donor.actor: PRIMARY, donor.completion_event: 12601850,
             donor.start_flag: 12604850, donor.health_bar_event: 12604852,
             **targets, **virtual_targets}
    additions: dict[int, str] = {}
    for row in attachments:
        additions[targets[row.source_event]] = _remap(source[row.source_event], remap)
    additions[ids.activation_event] = _activation(donor, source, ids.activation_event)
    additions[ids.terminal_bridge_event] = _terminal_bridge(ids)
    if donor.virtual_entities:
        additions[ids.donor_owner_cleanup_event] = _owner_cleanup(ids)
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets,
                        virtual_targets, ids),
        12604852: _health(arena[12604852], source[donor.health_bar_event],
                          donor, ids.activation_event),
        12604853: _music(arena[12604853], donor, source, targets),
        12604854: _camera(donor, source),
        **{event_id: _inert(arena[event_id]) for event_id in CHASE_EVENTS},
    }
    result = (_replace_events(destination, edits).rstrip() + "\n\n" +
              "\n\n".join(additions[event_id] for event_id in additions) + "\n")
    output = event_blocks(result)
    if set(output) != set(arena) | set(additions):
        raise ValueError("Micolash arena changed unexpected event identities")
    for event_id, original in arena.items():
        if event_id not in edits and output[event_id] != original:
            raise ValueError(f"Micolash arena touched unrelated event {event_id}")
    for event_id in (12601850, 12601852, 12601854, 12601855,
                     12604855, 12604860, 12604861):
        if output[event_id] != arena[event_id]:
            raise ValueError(f"Micolash arena changed progression event {event_id}")
    copied = "\n".join(output[event_id] for event_id in
                       (12604852, 12604854, *additions))
    donor_prefix = donor.actor // 100000
    if donor_prefix != 26 and re.search(rf"(?<!\d){donor_prefix}\d{{5,6}}(?!\d)", copied):
        raise ValueError(f"{donor.key} Micolash transplant retains donor-map literals")
    return result


def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]


def _source_primary(slots: Sequence[Slot], donor: CombatPackage) -> Slot:
    found = [slot for slot in slots if slot.entity_id == donor.actor
             and slot.map_name.startswith(donor.map_prefix)
             and slot.archetype == donor.archetype]
    if not found or len({slot.logical_key for slot in found}) != 1:
        raise ValueError(f"Micolash arena lacks pinned {donor.key} source primary")
    return sorted(found, key=lambda slot: slot.key)[0]


def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None:
        raise ValueError(f"Micolash arena lacks authored source pin for {source.key}")
    return {
        "source_map": source.map_name, "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype), "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": pin},
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": target.map_name, "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "destination_talk_id_override": 0,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                   "damage_anim_id", "provenance",
                                   "destination_talk_id_override"],
    }


def native_plan_portable_donor_at_micolash(donor: CombatPackage,
                                            slots: Sequence[Slot],
                                            npcs: Mapping[int, dict],
                                            effects: Mapping[int, dict],
                                            seed: str,
                                            ids: MicolashArenaIds = DEFAULT_IDS) -> dict:
    target_rows = [slot for slot in slots if slot.entity_id == PRIMARY
                   and slot.map_name == DESTINATION_MAP
                   and slot.archetype == PRIMARY_ARCHETYPE]
    if len(target_rows) != 1 or target_rows[0].dummy or target_rows[0].talk_id != 260311:
        raise ValueError("Micolash arena requires pinned original primary")
    target, source = target_rows[0], _source_primary(slots, donor)
    if source.dummy or source.talk_id != 0:
        raise ValueError(f"Micolash arena requires ordinary {donor.key} source primary")
    swap = Swap(
        target.logical_key, [target.key], {target.key: target.archetype},
        target.archetype, source.archetype,
        warnings=["runtime initial-area geometry/navigation fit remains unobserved"],
        destinations={target.key: {"map_name": target.map_name,
                                  "entity_id": target.entity_id,
                                  "x": target.x, "y": target.y, "z": target.z}},
    )
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects),
                                  boss_tiers=True)
    if len(changes) > 1 or (changes and skips):
        raise ValueError(f"Micolash arena has ambiguous {donor.key} normalization")
    requirements = actor_addition_requirements(MICOLASH_ARENA_CONTRACT, donor, slots)
    if requirements:
        if len(requirements) != 1 or donor.key != "ebrietas":
            raise ValueError(f"Micolash arena has unsupported {donor.key} actor additions")
        requirements[0]["destination_entity_id"] = ids.bullet_owner_entity
        requirements[0]["destination_map"] = DESTINATION_MAP
        requirements[0]["destination_anchor_part"] = target.part_name
    contract = micolash_arena_contract(donor, ids)
    contract["retained_destination_helpers"] = []
    plan = {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"micolash<-{donor.key}"},
        "boss_contract": contract,
        "primary_init_source_bindings": [_binding(source, target)],
        "scaling": {"enabled": bool(changes),
                    "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes),
                    "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan


def portable_micolash_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    result = tuple(packages)
    for donor in result:
        if (not donor.expected or not donor.music_phase_signals
                or donor.activation_event not in donor.expected):
            raise ValueError(f"{donor.key} lacks a complete portable combat contract")
    return result
