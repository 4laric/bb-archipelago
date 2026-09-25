"""Reusable source-pinned Gehrman destination arena."""
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
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m21_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m21_00_"
DESTINATION_MAP = "m21_00_00_00"
PRIMARY, DIALOGUE, EVENT_TARGET = 2100800, 2100600, 2100801
PRIMARY_ARCHETYPE = Archetype("c8050", 805000, 805000, 0)
DIALOGUE_ARCHETYPE = Archetype("c8040", 804000, 1, 0)
EVENT_TARGET_ARCHETYPE = Archetype("c9010", 901010, 1, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12996100, 12996101, 12996102, 12996103, 12996104)
ACTIVATION_EVENT = 12996105
DONOR_OWNER_CLEANUP_EVENT = 12996106
HEALTH_INITIALIZED_FLAG = 12996107
BULLET_OWNER_ENTITY = 983600
DESTINATION_PINS = {
    PRIMARY: "1c42091a9cacab2c22f7bc0056deafca140095a619fd1c68716158257427abc0",
    DIALOGUE: "d9be272b8f83aeb9bd50a25acd5fbbf066501df824837f26830f72d685310474",
    EVENT_TARGET: "87508ce80a4eccf3c5637e7db80b080791f6ce1e8e7ffa2ab41c3bcb7e958352",
}
DESTINATION_MSB_SHA256 = "d9f1142ed6d67233b8333f948f2d84f7fe80111005ddd77487a7dac8438a23a1"
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

GEHRMAN_HASHES: dict[int, str | tuple[str, ...]] = {
    0: "fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26",
    12101800: "f67934f4823c8c82c7675612ce4ae9f3c989b8c5426efc1c7e398f124938edb9",
    12101801: "45c3159338362eaf22fc16492d4fc7fe40199f8d1fa732a177bbe4b03376e9de",
    12101802: "9cb093d3e0aee513b4e2500b0b0a9a1e658c039b52e497eafa596a8752ccd26f",
    12101803: "f1c1eb3fe8f7b12e79d031a5c9ddce547ae594220e50c5bf57b28bbde3574f9a",
    12104802: "bb30fd6ca62dc57db799c576e84be78be221eb761ca6350da0197452f0bee570",
    12104803: "159ec5935e3770580344462a984ae2322ce8e367e996abe428d98856a66d1ce7",
    12104804: "13744977311646856c93a3cecc6b3067ae98d9fe804bd75236bda4ab1622a4c8",
    12104805: "6fa7028ee554109d2a7277f73a158a5ec6814cc2c2ea275441c34a195bed972a",
    12104807: "982f550c29fffaed7203de03d2bc1740b45c92f9ccfede0f249f0696ad00adab",
    12104808: "357e7c711dc72e7316a1ecf4f3ea6d0a07453e31cbdf6a1cb6f99e3b1b2e596d",
    12104810: "d9654c210761e048760fed745d265a2ae8d2cda9403379cb5d8138e7cffc426b",
    12104811: "a9fa751dd4e88d78210723fb787048038dd990cea43679c9c272eed87b37a43c",
}

GEHRMAN_ARENA_CONTRACT = ArenaContract(
    key="gehrman", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=PRIMARY, archetype=PRIMARY_ARCHETYPE, destination_count=1,
    completion_event=12101800, start_flag=12104800,
    health_bar_event=12104802, health_bar_label=804000,
    activation_event=12101802, music_event=12104803,
    phase_music_message=None, lockcam_event=12104804,
    lockcam_map=21, lockcam_subarea=0, phase_slots=(),
    co_op_entry_event=12101803, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=12101803, expected=GEHRMAN_HASHES,
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=(12104807, 12104808),
    activation_profile="normalized-cinematic",
)

@dataclass(frozen=True)
class GehrmanArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    donor_owner_cleanup_event: int = DONOR_OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    health_initialized_flag: int = HEALTH_INITIALIZED_FLAG
    bullet_owner_entity: int = BULLET_OWNER_ENTITY
    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.activation_event,
                self.donor_owner_cleanup_event, self.health_initialized_flag,
                self.bullet_owner_entity)

DEFAULT_IDS = GehrmanArenaIds()

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

def _validate_ids(ids: GehrmanArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Gehrman arena IDs must be unique positive project IDs")
    event_ids = {*ids.attachment_events, ids.activation_event,
                 ids.donor_owner_cleanup_event}
    if (event_ids != set(range(12996100, 12996107))
            or ids.health_initialized_flag != 12996107
            or ids.bullet_owner_entity != 983600):
        raise ValueError("Gehrman arena requires the exact reviewed narrow allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Gehrman arena IDs collide with original inputs: {sorted(collisions)}")

def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"

def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gehrman arena expected one {label}")
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
                 virtual_targets: Mapping[int, int], ids: GehrmanArenaIds) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 12101803);"
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
    lines.append(_initializer(0, ids.activation_event, ()))
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

def _health(destination: str, source: str, donor: CombatPackage,
            ready_event: int, health_initialized_flag: int) -> str:
    result = _remap(source, {donor.actor: PRIMARY, donor.completion_event: 12101800,
                             donor.start_flag: 12104800,
                             donor.health_bar_event: 12104802})
    authority = re.search(
        r"(?m)^\s*SetNetworkUpdateAuthority\(2100800, AuthorityLevel\.(?:Forced|Normal)\);$",
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
    replacement = (
        f"{indent}{client}\n"
        f"{indent}    if (!EventFlag({health_initialized_flag})) {{\n"
        f"{indent}        IssueBossRoomEntryNotification(0);\n"
        f"{indent}        SetEventFlag({health_initialized_flag}, ON);\n"
        f"{indent}    }}\n"
        f"{indent}    {authority[0].strip()}\n{indent}}}"
    )
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
                            lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));", result, count=1)
    if count == 0:
        result = _replace_once(result, "    WaitFor(EventFlag(12104800));",
                               f"    WaitFor(EventFlag({ready_event}));", "health readiness")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    # Event completion persists across a failed attempt. Event(0) resets the
    # readiness flag each load; this second wait also gates saved health.
    result = _replace_once(
        result, "L0:\n    SetEventFlag(12104800, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n"
        "    SetEventFlag(12104800, ON);",
        "saved-health readiness",
    )
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Gehrman"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result

def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")

def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 12104800
    prefix = (f"$Event({event_id}, Default, function() {{\n"
              "    EndIf(EventFlag(12101800));\n"
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
        raise ValueError(f"Gehrman arena lacks readiness adapter for {donor.key}/{profile}")
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
    return _replace_once(block, "chrFlagArea &= CharacterHasEventMessage(2100800, 100);",
                         f"chrFlagArea &= {condition};", "destination music boundary")

CAMERA_EVENTS = {"blood-starved-beast": 12304804}

def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {event_id: 12104804, donor.actor: PRIMARY,
               donor.completion_event: 12101800, donor.start_flag: 12104800}
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 12104801
    result = _remap(source, mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(\d+, \d+,",
                            "SetLockcamSlotNumber(21, 0,", result)
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = "    EndIf(EventFlag(12101800));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(result, header, header + guard,
                               "destination camera completion guard")
    return result

def _owner_cleanup(ids: GehrmanArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12101800));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""

def gehrman_arena_contract(donor: CombatPackage, ids: GehrmanArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-gehrman-arena-contract-v1", "status": "experimental",
        "arena": "gehrman", "donor": donor.key, "allocation": asdict(ids),
        "preserved_destination_events": [12101800, 12101801, 12101802,
            12101803, 12104805, 12104810, 12104811, 12101850,
            12101852, 12101853],
        "adapted_destination_events": [12104802, 12104803, 12104804],
        "retired_destination_controllers": [12104807, 12104808],
        "retained_destination_helpers": [DIALOGUE, EVENT_TARGET],
        "destination_native_evidence": {
            "msb_sha256": DESTINATION_MSB_SHA256,
        },
        "readiness_adapter": {"source_event": donor.activation_event,
            "profile": donor.activation_profile, "destination_event": ids.activation_event,
            "trigger": "EventFlag(12104800)", "reset_each_load": True},
        "entry_policy": {"event": 12101802, "trigger_flag": 72100131,
            "warp_region": 2102808,
            "cinematic_rewrite_owner": "boss_entrances.skip_replacement_entrance"},
        "client_restore_event": 12101803,
        "music_policy": "donor-final-declared-boundary-drives-destination-final-track",
        "attachments": [{"source_event": item.source_event,
                         "destination_event": ids.attachment_events[index]}
                        for index, item in enumerate(attachments)],
        "runtime_status": "unobserved",
    }

def patch_portable_donor_at_gehrman(destination: str, donor: CombatPackage,
                                       donor_source: str,
                                       ids: GehrmanArenaIds = DEFAULT_IDS) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, GEHRMAN_HASHES, "Gehrman arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    if hashlib.sha256(source[0].encode()).hexdigest() != SOURCE_ZERO_HASHES[donor.key]:
        raise ValueError(f"{donor.key} Event(0) differs from pinned constructor source")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Gehrman attachment capacity")
    targets = {item.source_event: ids.attachment_events[index]
               for index, item in enumerate(attachments)}
    virtual = {item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities}
    mapping = {donor.actor: PRIMARY, donor.completion_event: 12101800,
               donor.start_flag: 12104800, **targets, **virtual}
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        12104802: _health(arena[12104802], source[donor.health_bar_event], donor,
                          ids.activation_event, ids.health_initialized_flag),
        12104803: _music(arena[12104803], donor, source, targets),
        12104804: _camera(donor, source),
        12104807: _noop(arena[12104807]),
        12104808: _noop(arena[12104808]),
    }
    additions.append(_activation(donor, source, ids.activation_event))
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    expected = set(arena) | set(targets.values()) | {ids.activation_event}
    if donor.virtual_entities:
        expected.add(ids.donor_owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("Gehrman adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Gehrman adapter changed unrelated event {event_id}")
    return result

def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]

def _source_primary(slots: Sequence[Slot], donor: CombatPackage) -> Slot:
    candidates = [slot for slot in slots if slot.entity_id == donor.actor and slot.archetype == donor.archetype]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    binding = dict(donor.primary_state_bindings).get("00")
    if binding is None or binding not in by_state:
        raise ValueError(f"{donor.key} lacks explicit Gehrman source-state binding")
    return by_state[binding]

def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Gehrman donor source state lacks reviewed native evidence")
    return {"source_map": source.map_name, "source_part": source.part_name,
        "source_entity_id": source.entity_id, "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": pin},
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": target.map_name,
        "destination_part": target.part_name, "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                   "damage_anim_id", "provenance"]}

def native_plan_portable_donor_at_gehrman(donor: CombatPackage, slots: Sequence[Slot],
        npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
        ids: GehrmanArenaIds = DEFAULT_IDS) -> dict:
    _validate_ids(ids, "")
    targets = [slot for slot in slots if slot.map_name == DESTINATION_MAP]
    primaries = [slot for slot in targets if slot.entity_id == PRIMARY and slot.archetype == PRIMARY_ARCHETYPE]
    retained = [slot for slot in targets if slot.entity_id in (DIALOGUE, EVENT_TARGET)]
    if (len(primaries) != 1 or len(retained) != 2 or primaries[0].talk_id != 210306
            or {slot.archetype for slot in retained}
            != {DIALOGUE_ARCHETYPE, EVENT_TARGET_ARCHETYPE}):
        raise ValueError("Gehrman destination roster differs from reviewed native source")
    target, source_primary = primaries[0], _source_primary(slots, donor)
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype},
        target.archetype, donor.archetype, destinations={target.key: {
            "map_name": target.map_name, "entity_id": target.entity_id,
            "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    plan = {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"gehrman<-{donor.key}"},
        "boss_contract": gehrman_arena_contract(donor, ids),
        "primary_init_source_bindings": [_binding(source_primary, target)],
        "scaling": {"enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect", "change_count": len(changes),
            "changes": [change.json() for change in changes], "skip_count": len(skips), "skips": skips}}
    initializations = {
        DIALOGUE: {"talk_id": 210305, "unk_t18": -1,
                   "init_anim_id": -1, "damage_anim_id": -1},
        EVENT_TARGET: dict(SOURCE_INITIALIZATION),
    }
    plan["boss_contract"]["retained_destination_helpers"] = [{
        "map": slot.map_name, "part": slot.part_name, "entity_id": slot.entity_id,
        "archetype": asdict(slot.archetype),
        "source_provenance": {"format": "bb-boss-actor-pin-v1",
                              "part_sha256": DESTINATION_PINS[slot.entity_id]},
        "source_initialization": initializations[slot.entity_id],
        "policy": ("dialogue/progression actor preserved byte-for-byte"
                   if slot.entity_id == DIALOGUE else
                   "offstage original event target retained; transplanted health has no linkage"),
    } for slot in retained]
    requirements = actor_addition_requirements(GEHRMAN_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan

def portable_gehrman_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if donor.music_phase_signals and len(attachments) <= len(ATTACHMENT_EVENTS) and len(donor.virtual_entities) <= 1:
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)
