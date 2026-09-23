"""Reusable source-pinned Martyr Logarius destination arena."""
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
    AMYGDALA_PACKAGE, BSB_PACKAGE, PACKAGES, ArenaContract, Archetype,
    CombatPackage, EventAttachment, MusicPhaseSignal, actor_addition_requirements,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m25_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m25_00_"
DESTINATION_MAP = "m25_00_00_00"
PRIMARY, SWORD, OWNER = 2500800, 2500801, 2500802
PRIMARY_ARCHETYPE = Archetype("c2320", 232000, 232000, 0)
SWORD_ARCHETYPE = Archetype("c2321", 232100, 232100, 0)
OWNER_ARCHETYPE = Archetype("c9010", 232000, 232000, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12995400, 12995401, 12995402, 12995403, 12995404)
DONOR_OWNER_CLEANUP_EVENT = 12995405
ACTIVATION_EVENT = 12995406
CLIENT_RESTORE_EVENT = 12995407
HELPER_LIFECYCLE_EVENT = 12995408
BULLET_OWNER_ENTITY = 982900
DESTINATION_PINS = {
    PRIMARY: "7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011",
    SWORD: "fc114097901492ce96524c9265c04a6c2606b3b825336723adb52c9064475b1d",
    OWNER: "7bd8e95bd08d4bfe30801d088983025c6c1593885dfc97cabff3ecc89c5c4984",
}
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

LOGARIUS_HASHES: dict[int, str] = {
    0: "f906cc00fd41625d4e479a9f0e261e6344708b7ea2728f850cb328efbf39a9ed",
    12501800: "8e7a5e07c7e871cbb44982c80436874fdf451d3c80c68af2969e15f78c6129bd",
    12501801: "752c098d59f5b3c00482b78f1ecbaa771d7fa084bef22e9e490784bfc5725797",
    12501802: "91d992106cdd9de1298ea848def19f816af24302f50dbf56f67cf5f5932c2e71",
    12501803: "c7e28f999f30a6198d27a76ecbad530de1cd5b2899a50f91516892ab11416e2c",
    12504802: "a8819ae3d0e70e0ea1d5e0e9f662b9e19e7fcb4b07b160f6a84b2249413cc625",
    12504803: "edee08431133d70220856551eb1b4518e7e8898c80fcbde9448a81537e9a7e0a",
    12504804: "d64bb9fa786b4cf26dae37451b8ca76de2a42bbff3bed4d47ce70ca28d32db42",
    12504805: "1b07e41f954c785e112ea6dff7cc76f8d8b1dbbe243c42f15b31d8ace95f09a7",
    12504806: "dba1f97eec52c6f56df35f2f53813470690d7b83ffba3fd313459130cceae775",
    12504807: "9a3943748bcb8301baaf7978ea59899fc0cdd7318a15f6fb50c57be73f94157a",
    12504808: "fb6738bfefc7c4fb69af7def1f54386d186058b6a1b284a07e74004610e9f1fa",
    12504810: "247053c43384e582535e4d4c26497797719d3d0e1b01026a425fd7f2efc9b6ec",
    12504811: "25b151f4961f4832b989524527f8db3584b798e83c9c064b16fc83358578a39a",
}

LOGARIUS_ARENA_CONTRACT = ArenaContract(
    key="martyr-logarius", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=PRIMARY, archetype=PRIMARY_ARCHETYPE, destination_count=1,
    completion_event=12501800, start_flag=12504800,
    health_bar_event=12504802, health_bar_label=232000,
    activation_event=12501802, music_event=12504803,
    phase_music_message=None, lockcam_event=12504804,
    lockcam_map=25, lockcam_subarea=0, phase_slots=(),
    co_op_entry_event=12504811, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=12504808, expected=LOGARIUS_HASHES,
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=(12504806, 12504807, 12504808),
    activation_profile="normalized-cinematic",
)

@dataclass(frozen=True)
class LogariusArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    donor_owner_cleanup_event: int = DONOR_OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    client_restore_event: int = CLIENT_RESTORE_EVENT
    helper_lifecycle_event: int = HELPER_LIFECYCLE_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY
    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.donor_owner_cleanup_event,
                self.activation_event, self.client_restore_event,
                self.helper_lifecycle_event,
                self.bullet_owner_entity)

DEFAULT_IDS = LogariusArenaIds()

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

def _validate_ids(ids: LogariusArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Logarius arena IDs must be unique positive project IDs")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Logarius arena IDs collide with original inputs: {sorted(collisions)}")

def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"

def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Logarius arena expected one {label}")
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
                 virtual_targets: Mapping[int, int], ids: LogariusArenaIds) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 12504808);"
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
                  _initializer(0, ids.client_restore_event, ()),
                  _initializer(0, ids.helper_lifecycle_event, ())))
    if donor.virtual_entities:
        lines.append(_initializer(0, ids.donor_owner_cleanup_event, ()))
    return _replace_once(result, anchor, anchor + "\n" + "\n".join(lines), "constructor anchor")

def _telemetry(block: str, owner: str) -> str:
    match = re.search(r"(?m)^    CreatePlaylog\([^\n]+\);\n    StartTimeMeasurement\([^\n]+\);", block)
    if match is None or len(re.findall(r"CreatePlaylog\(", block)) != 1:
        raise ValueError(f"{owner} health lacks unique telemetry")
    return match[0]

def _health(destination: str, source: str, donor: CombatPackage, ready_event: int) -> str:
    result = _remap(source, {donor.actor: PRIMARY, donor.completion_event: 12501800,
                             donor.start_flag: 12504800,
                             donor.health_bar_event: 12504802})
    authority = re.search(r"(?m)^\s*SetNetworkUpdateAuthority\(2500800, AuthorityLevel\.(?:Forced|Normal)\);$", result)
    if authority is None:
        raise ValueError(f"{donor.key} health lacks authority witness")
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    start = result.rfind(client, 0, authority.start())
    line_start = result.rfind("\n", 0, start) + 1
    indent = result[line_start:start]
    close = result.find("\n" + indent + "}", authority.end())
    if start < 0 or close < 0:
        raise ValueError(f"{donor.key} health lacks client branch")
    replacement = (f"{indent}{client}\n{indent}    if (!EventFlag(12504223)) {{\n"
                   f"{indent}        IssueBossRoomEntryNotification(0);\n{indent}    }}\n"
                   f"{indent}    {authority[0].strip()}\n{indent}}}")
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
                            lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));", result, count=1)
    if count == 0:
        result = _replace_once(result, "    WaitFor(EventFlag(12504800));",
                               f"    WaitFor(EventFlag({ready_event}));", "health readiness")
    result = _replace_once(result, "    SetEventFlag(12504800, ON);",
                           "    SetEventFlag(12504800, ON);\n    SetEventFlag(12504223, ON);",
                           "room notification ownership")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Logarius"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result

def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")

def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 12504800
    prefix = f"$Event({event_id}, Default, function() {{\n    EndIf(EventFlag(12501800));\n    EndIf(ThisEvent());\n"
    suffix = "\n});"
    profile = donor.activation_profile
    if profile == "host-entry-animation":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);",))
        body = f"    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7001, false, false, false);"
    elif profile == "protected-radius-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, true, false, false);", "WaitFixedTimeFrames(70);"))
        body = f"    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif profile == "gravity-warp-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 3028, false, false, false);", "WaitFixedTimeFrames(110);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterMaphits({actor}, true);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 3028, false, false, false);\n    WaitFixedTimeFrames(110);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterMaphits({actor}, false);"
    elif profile == "object-gated-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, false, false, false);", f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, false, false, false);\n    ForceAnimationPlayback({actor}, 7001, false, false, false);"
    elif profile == "protected-area-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7003, true, false, false);", "WaitFixedTimeFrames(160);"))
        body = f"    SetCharacterMaphits({actor}, true);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7003, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7006, false, false, false);\n    WaitFixedTimeFrames(30);\n    ForceAnimationPlayback({actor}, 7002, false, false, false);\n    WaitFixedTimeFrames(160);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterInvincibility({actor}, Disabled);\n    SetCharacterMaphits({actor}, false);"
    elif profile == "first-damage-wake":
        _witnesses(source, donor, (f"SetCharacterImmortality({donor.actor}, Enabled);", f"HasDamageType({donor.actor}, 10000, DamageType.Unspecified)"))
        body = f"    ForceAnimationPlayback({actor}, 7001, true, false, false);\n    SetCharacterImmortality({actor}, Enabled);\n    SetSpEffect({actor}, 5647, false);\n    WaitFor(EventFlag({flag}));\n    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({actor}, 7000, false, true, false);\n    SetCharacterImmortality({actor}, Disabled);\n    ClearSpEffect({actor}, 5647);"
    else:
        raise ValueError(f"Logarius arena lacks readiness adapter for {donor.key}/{profile}")
    return prefix + body + suffix

def _signal_condition(donor: CombatPackage, blocks: Mapping[int, str], targets: Mapping[int, int]) -> str:
    signal = donor.music_phase_signals[0]
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
    return _replace_once(block, "spFlagArea &= CharacterHasSpEffect(2500800, 5633);",
                         f"spFlagArea &= {condition};", "first music boundary")

CAMERA_EVENTS = {"blood-starved-beast": 12304804}

def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {event_id: 12504804, donor.actor: PRIMARY,
               donor.completion_event: 12501800, donor.start_flag: 12504800}
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 12504801
    result = _remap(source, mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(\d+, \d+,",
                            "SetLockcamSlotNumber(25, 0,", result)
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    return result

def _helper_lifecycle(ids: LogariusArenaIds) -> str:
    return f"""$Event({ids.helper_lifecycle_event}, Restart, function() {{
    SetCharacterAIState(2500801, Disabled);
    SetCharacterHPBarDisplay(2500801, Disabled);
    SetCharacterImmortality(2500801, Enabled);
    ChangeCharacterEnableState(2500801, Disabled);
    SetCharacterAIState(2500802, Disabled);
    SetCharacterHPBarDisplay(2500802, Disabled);
    ChangeCharacterEnableState(2500802, Disabled);
    GotoIf(L0, EventFlag(12501800));
    WaitFor(EventFlag(12501800));
L0:
    SetCharacterImmortality(2500801, Disabled);
    ForceCharacterDeath(2500801, false);
    ForceCharacterDeath(2500802, false);
}});"""

def _owner_cleanup(ids: LogariusArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12501800));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""

CLIENT_EVENTS = {
    "blood-starved-beast": (12301803, "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c"),
    "darkbeast-paarl": (12301703, "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653"),
    "cleric-beast": (12411703, "f4982068db5c19d893ac320045e14491832a5722d1fd89a8038ef4cb8b372ce9"),
    "vicar-amelia": (12401804, "85aa59f873b275cb390675f4f2ef13e4f7b3f00935274a2ce43c23b75070da59"),
    "amygdala": (13301803, "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9"),
    "ebrietas": (12421803, "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152"),
}

def _client_restore(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source_id, digest = CLIENT_EVENTS[donor.key]
    source = blocks.get(source_id)
    if source is None or hashlib.sha256(source.encode()).hexdigest() != digest:
        raise ValueError(f"{donor.key} client restore differs from pinned source")
    return _remap(source, {source_id: event_id, donor.actor: PRIMARY,
                           donor.start_flag: 12504800,
                           donor.activation_event: 12501802})

def _entry(block: str) -> str:
    return _replace_once(block,
        "    if (!ThisEventSlot()) {\n        ForceAnimationPlayback(2500800, 7000, false, false, false);\n    }\n",
        "", "Logarius model entrance animation")

def logarius_arena_contract(donor: CombatPackage, ids: LogariusArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-logarius-arena-contract-v1", "status": "experimental",
        "arena": "martyr-logarius", "donor": donor.key, "allocation": asdict(ids),
        "preserved_destination_events": [12501800, 12501801, 12501803,
            12504805, 12504810, 12504811],
        "adapted_destination_events": [12501802, 12504802, 12504803, 12504804],
        "retired_destination_controllers": [12504806, 12504807, 12504808],
        "retained_destination_helpers": [SWORD, OWNER],
        "readiness_adapter": {"source_event": donor.activation_event,
            "profile": donor.activation_profile, "destination_event": ids.activation_event,
            "trigger": "EventFlag(12504800)"},
        "client_restore_event": ids.client_restore_event,
        "helper_lifecycle_event": ids.helper_lifecycle_event,
        "music_policy": "donor-first-phase-boundary-drives-destination-final-track",
        "attachments": [{"source_event": item.source_event,
                         "destination_event": ids.attachment_events[index]}
                        for index, item in enumerate(attachments)],
        "runtime_status": "unobserved",
    }

def patch_portable_donor_at_logarius(destination: str, donor: CombatPackage,
                                       donor_source: str,
                                       ids: LogariusArenaIds = DEFAULT_IDS) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, LOGARIUS_HASHES, "Logarius arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    if hashlib.sha256(source[0].encode()).hexdigest() != SOURCE_ZERO_HASHES[donor.key]:
        raise ValueError(f"{donor.key} Event(0) differs from pinned constructor source")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Logarius attachment capacity")
    targets = {item.source_event: ids.attachment_events[index]
               for index, item in enumerate(attachments)}
    virtual = {item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities}
    mapping = {donor.actor: PRIMARY, donor.completion_event: 12501800,
               donor.start_flag: 12504800, **targets, **virtual}
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        12501802: _entry(arena[12501802]),
        12504802: _health(arena[12504802], source[donor.health_bar_event], donor, ids.activation_event),
        12504803: _music(arena[12504803], donor, source, targets),
        12504804: _camera(donor, source),
        12504806: _noop(arena[12504806]),
        12504807: _noop(arena[12504807]),
        12504808: _noop(arena[12504808]),
    }
    additions.extend((_activation(donor, source, ids.activation_event),
                      _client_restore(donor, source, ids.client_restore_event),
                      _helper_lifecycle(ids)))
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    expected = set(arena) | set(targets.values()) | {
        ids.activation_event, ids.client_restore_event, ids.helper_lifecycle_event}
    if donor.virtual_entities:
        expected.add(ids.donor_owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("Logarius adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Logarius adapter changed unrelated event {event_id}")
    return result

def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]

def _source_primary(slots: Sequence[Slot], donor: CombatPackage) -> Slot:
    candidates = [slot for slot in slots if slot.entity_id == donor.actor and slot.archetype == donor.archetype]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    binding = dict(donor.primary_state_bindings).get("00")
    if binding is None or binding not in by_state:
        raise ValueError(f"{donor.key} lacks explicit Logarius source-state binding")
    return by_state[binding]

def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Logarius donor source state lacks reviewed native evidence")
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

def native_plan_portable_donor_at_logarius(donor: CombatPackage, slots: Sequence[Slot],
        npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
        ids: LogariusArenaIds = DEFAULT_IDS) -> dict:
    _validate_ids(ids, "")
    targets = [slot for slot in slots if slot.map_name == DESTINATION_MAP]
    primaries = [slot for slot in targets if slot.entity_id == PRIMARY and slot.archetype == PRIMARY_ARCHETYPE]
    helpers = [slot for slot in targets if slot.entity_id in (SWORD, OWNER)]
    if (len(primaries) != 1 or len(helpers) != 2 or primaries[0].talk_id
            or {slot.archetype for slot in helpers} != {SWORD_ARCHETYPE, OWNER_ARCHETYPE}):
        raise ValueError("Logarius destination roster differs from reviewed native source")
    target, source_primary = primaries[0], _source_primary(slots, donor)
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype},
        target.archetype, donor.archetype, destinations={target.key: {
            "map_name": target.map_name, "entity_id": target.entity_id,
            "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    plan = {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"martyr-logarius<-{donor.key}"},
        "boss_contract": logarius_arena_contract(donor, ids),
        "primary_init_source_bindings": [_binding(source_primary, target)],
        "scaling": {"enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect", "change_count": len(changes),
            "changes": [change.json() for change in changes], "skip_count": len(skips), "skips": skips}}
    plan["boss_contract"]["retained_destination_helpers"] = [{
        "map": slot.map_name, "part": slot.part_name, "entity_id": slot.entity_id,
        "archetype": asdict(slot.archetype),
        "source_provenance": {"format": "bb-boss-actor-pin-v1",
                              "part_sha256": DESTINATION_PINS[slot.entity_id]},
        "source_initialization": {"talk_id": 0, "unk_t18": -1,
                                  "init_anim_id": -1, "damage_anim_id": -1},
        "policy": "hidden inert destination helper until exact event 12501800 completes",
    } for slot in helpers]
    requirements = actor_addition_requirements(LOGARIUS_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan

def portable_logarius_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if donor.music_phase_signals and len(attachments) <= len(ATTACHMENT_EVENTS) and len(donor.virtual_entities) <= 1:
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)
