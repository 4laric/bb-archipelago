"""Reusable source-pinned Orphan of Kos destination arena."""
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
EVENT_FILE = "m36_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m36_00_"
DESTINATION_MAP = "m36_00_00_00"
PRIMARY, PHASE, SHADOW, SUPPORT = 3600800, 3600801, 3600802, 3600803
PRIMARY_ARCHETYPE = Archetype("c4540", 454000, 454000, 0)
PHASE_ARCHETYPE = Archetype("c4541", 454100, 454100, 0)
SHADOW_ARCHETYPE = Archetype("c4550", 455000, 1, 0)
SUPPORT_ARCHETYPE = Archetype("c4543", 454300, 454300, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12995700, 12995701, 12995702, 12995703, 12995704)
ACTIVATION_EVENT = 12995705
CLIENT_RESTORE_EVENT = 12995706
HELPER_LIFECYCLE_EVENT = 12995707
DONOR_OWNER_CLEANUP_EVENT = 12995708
BULLET_OWNER_ENTITY = 983200
DESTINATION_PINS = {
    PRIMARY: "35eb4a762d39a03f2b99e8407adc8e0fd73d55f01cb84462a15cbb53cd58e2e1",
    PHASE: "770be2af7c4bc6ca097b2bdb3644b13796a16cf271653e504632efb5befc6f36",
    SHADOW: "f06bcba0d8e2318bfb89c91d755e002b66a8a06a0cb209cbbba63f13bd5a2496",
    SUPPORT: "4561475addb4ed1a4f1e085153b03c8c3ba58907e89bf979bc64b2e0804c1dce",
}
DESTINATION_MSB_SHA256 = "d347fba3304de0e10dceae4a89588d5e8cfd4a2507fda39cf2eace880c043cf7"
DESTINATION_FFX_SHA256 = "6b3a7971712d29fb16a4eec322254447dba1d8add16e4311d03ae9b24e34be73"
DESTINATION_REGION_PINS = {
    3602800: "433bf48c6c33b48e816a81225c69a33617b7476bec5e0859ba4d737d230aa687",
    3602801: "e20d473979ecd09ff97b08d84b0729874066b26a48dece86a3663ded1e85eb5c",
    3602802: "77ad92eca3b1fd9e3cf43a44e120ea20517b64210acf0c148f8e58131a21b68a",
    3602805: "7ca6042bfc250711dccfa12bdde21c56bc905b26513131f53480df9ce155d2ae",
}
DESTINATION_OBJECT_SFX_PINS = {
    3601800: "474e78e99d616aafde742fd4e5d21f7a7a5b3e2d372d83e4791985a4f0caacb8",
    3601802: "5ffac170550fa0a72a1f04bbbc2bb7ae1e390ae6005d29e9fd55c46543edcde1",
    3601810: "5dadef92702a971ba58cee6d71ea3dff581130e556d4cc5af0ac8686d25e0325",
    3601811: "be85a68e2976a85bbd4ebe9874cbacc853c040a44b6481fcc454eea7dc8e9ea8",
    3603800: "1fc6c871b2af841bed0bb5fb0d8942331c8acf02bafc84ebd2d67dfd78fe90dc",
    3603860: "50cf9c11efadd80cea64a88a75e13e36d16a9a0f859def2ff3e645aa6f7353bf",
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

ORPHAN_HASHES: dict[int, str | tuple[str, ...]] = {
    0: ("a6c55dfa6a26dbb4d086f2eb73a12d3956a1dec570699dfbc6c63d0f51fb54b3",
        "d9c76c6c7fcd7efe7eb641d470519cd217d70561ec8a81962f5248a76e316cb7"),
    13601800: "5423c79a2613f564aecbc24658b5b30152c08acb21ede1e817a15abeb5c66c38",
    13601801: "a1e52549f15c53a6e55e4aeafb2f21cf863e1a267d58b9121695241118f2de78",
    13601802: ("e2396aaa1c6e9082e71baa1689195eb8c4afbb79870aec7ba85532fd8c053476",
                 "db7835c85dcca96716065d5b2106299bcb821db64c506fb931dc3dae0e0de757"),
    13601803: "43c5a2c33491090c42c2efa1913c15aadd1208c9ad1440502b7c36876a273593",
    13601804: "0601ad13294eaf870feb6241d19ceae172b8d4b1de8c622ee15309adda1eb45e",
    13604800: "d8efed8f21a583997c86a38b91bde6ca110890b9c5ec3a524307fe2fa2544774",
    13604801: "4bcad3d039946f79a7fb0463c4b3355b0b8d1cab30c3f0c8dfda35922e992fe6",
    13604802: ("8d7b309380f51d2933c573d286cee4ecdb4dc2797376c16dead9078df7f28fb9",
                 "54cb28efcdc5dbf46afd69ebfa6155d8635a61770e8f2375c6be127a8fb44004"),
    13604803: "f6754136d8003799fd8c001053980bb67f25b033108b690852d0b0aedd128e72",
    13604804: "1360cbaab6065617a103ca2668dc2e601b10ea73bb97099a59055ad48f074d4e",
    13604805: "0c4495a2403778481467bef908cb72ff5c7cea94f50d25a1ee6e66ea8aa50cdc",
    13604806: "c8316c6a44dc69fd7a19c04b5c8714c57371fc44169d9f4b6a44e6353584a122",
    13604807: "da7cd4adeef45b2cedb4bad61c2873feea4f8a36444c4e369a220e52a4586ea2",
    13604811: "e0f345bcfb403b076c099ed8763c59cf8348bc7bc1de3cb55892f5d57e00c108",
    13604820: "81c25057e062e5cf3d4728af2ba34359bc8b7c75ee28ded6ea7eb8519decd443",
    13604830: "fcec0fd932510a899f0e1a31433ee06438f56f0e0ec27b0ae5e24dc539de57ec",
    13604840: "027beee553830c6635d9452f708c0bcb95ca95fb53239bd6e12d5e764c32f75c",
    13604850: "de7acf9de30e70460a229e9f489b52eb00ab51289317a6b81d80382a67e6ddf1",
}

ORPHAN_ARENA_CONTRACT = ArenaContract(
    key="orphan-of-kos", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=PRIMARY, archetype=PRIMARY_ARCHETYPE, destination_count=1,
    completion_event=13601800, start_flag=13604808,
    health_bar_event=13604802, health_bar_label=454000,
    activation_event=13601801, music_event=13604803,
    phase_music_message=None, lockcam_event=13604804,
    lockcam_map=36, lockcam_subarea=0, phase_slots=(),
    co_op_entry_event=13601804, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=13601804, expected=ORPHAN_HASHES,
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=(13604820, 13604830, 13604840, 13604850),
    activation_profile="normalized-cinematic",
)

@dataclass(frozen=True)
class OrphanArenaIds:
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

DEFAULT_IDS = OrphanArenaIds()

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

def _validate_ids(ids: OrphanArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Orphan arena IDs must be unique positive project IDs")
    event_ids = {*ids.attachment_events, ids.activation_event,
                 ids.client_restore_event, ids.helper_lifecycle_event,
                 ids.donor_owner_cleanup_event}
    if event_ids != set(range(12995700, 12995709)) or ids.bullet_owner_entity != 983200:
        raise ValueError("Orphan arena requires the exact reviewed narrow allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Orphan arena IDs collide with original inputs: {sorted(collisions)}")

def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"

def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Orphan arena expected one {label}")
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
                 virtual_targets: Mapping[int, int], ids: OrphanArenaIds) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 13601804);"
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
                  _initializer(0, ids.helper_lifecycle_event, ()),
                  _initializer(0, 13604804, ())))
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
    result = _remap(source, {donor.actor: PRIMARY, donor.completion_event: 13601800,
                             donor.start_flag: 13604808,
                             donor.health_bar_event: 13604802})
    authority = re.search(r"(?m)^\s*SetNetworkUpdateAuthority\(3600800, AuthorityLevel\.(?:Forced|Normal)\);$", result)
    if authority is None:
        raise ValueError(f"{donor.key} health lacks authority witness")
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    start = result.rfind(client, 0, authority.start())
    line_start = result.rfind("\n", 0, start) + 1
    indent = result[line_start:start]
    close = result.find("\n" + indent + "}", authority.end())
    if start < 0 or close < 0:
        raise ValueError(f"{donor.key} health lacks client branch")
    replacement = (f"{indent}{client}\n{indent}    if (!EventFlag(13604810)) {{\n"
                   f"{indent}        IssueBossRoomEntryNotification(0);\n{indent}    }}\n"
                   f"{indent}    {authority[0].strip()}\n{indent}}}")
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
                            lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));", result, count=1)
    if count == 0:
        result = _replace_once(result, "    WaitFor(EventFlag(13604808));",
                               f"    WaitFor(EventFlag({ready_event}));", "health readiness")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(result, "    SetEventFlag(13604808, ON);",
                           "    SetEventFlag(13604808, ON);\n"
                           "    SetEventFlag(13604810, ON);\n"
                           "    SetEventFlag(13604812, ON);",
                           "room notification ownership")
    # Event completion persists across a failed attempt. Event(0) resets the
    # readiness flag each load; this second wait also gates saved health.
    result = _replace_once(
        result, "L0:\n    SetEventFlag(13604808, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n"
        "    SetEventFlag(13604808, ON);",
        "saved-health readiness",
    )
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Orphan"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result

def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")

def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 13604808
    prefix = f"$Event({event_id}, Default, function() {{\n    EndIf(EventFlag(13601800));\n    EndIf(ThisEvent());\n"
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
        raise ValueError(f"Orphan arena lacks readiness adapter for {donor.key}/{profile}")
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
    return _replace_once(block, "flagArea2 &= EventFlag(13604820);",
                         f"flagArea2 &= {condition};", "destination music boundary")

CAMERA_EVENTS = {"blood-starved-beast": 12304804}

def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {event_id: 13604804, donor.actor: PRIMARY,
               donor.completion_event: 13601800, donor.start_flag: 13604808}
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 13604809
    result = _remap(source, mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(\d+, \d+,",
                            "SetLockcamSlotNumber(36, 0,", result)
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = "    EndIf(EventFlag(13601800));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(result, header, header + guard,
                               "destination camera completion guard")
    return result

def _helper_lifecycle(ids: OrphanArenaIds) -> str:
    return f"""$Event({ids.helper_lifecycle_event}, Restart, function() {{
    SetCharacterAIState(3600801, Disabled);
    SetCharacterHPBarDisplay(3600801, Disabled);
    SetCharacterInvincibility(3600801, Enabled);
    ChangeCharacterEnableState(3600801, Disabled);
    SetCharacterAIState(3600803, Disabled);
    SetCharacterHPBarDisplay(3600803, Disabled);
    ChangeCharacterEnableState(3600803, Disabled);
    GotoIf(L0, EventFlag(13601800));
    WaitFor(EventFlag(13601800));
L0:
    SetCharacterInvincibility(3600801, Disabled);
    ChangeCharacterEnableState(3600801, Disabled);
    ForceCharacterDeath(3600801, false);
    ChangeCharacterEnableState(3600803, Disabled);
    ForceCharacterDeath(3600803, false);
}});"""

def _owner_cleanup(ids: OrphanArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(13601800));
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
                           donor.start_flag: 13604808,
                           donor.activation_event: 13601801})

def orphan_arena_contract(donor: CombatPackage, ids: OrphanArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-orphan-arena-contract-v1", "status": "experimental",
        "arena": "orphan-of-kos", "donor": donor.key, "allocation": asdict(ids),
        "preserved_destination_events": [13601800, 13601801, 13601802,
            13601803, 13601804, 13604800, 13604801, 13604805,
            13604806, 13604807, 13604811],
        "adapted_destination_events": [13604802, 13604803, 13604804],
        "retired_destination_controllers": [13604820, 13604830,
                                               13604840, 13604850],
        "retained_destination_helpers": [PHASE, SUPPORT],
        "progression_owned_actor": SHADOW,
        "destination_native_evidence": {
            "msb_sha256": DESTINATION_MSB_SHA256,
            "ffx_bank": "frpg_sfxbnd_m36.ffxbnd.dcx",
            "ffx_sha256": DESTINATION_FFX_SHA256,
            "region_pins": dict(DESTINATION_REGION_PINS),
            "object_sfx_pins": dict(DESTINATION_OBJECT_SFX_PINS),
        },
        "readiness_adapter": {"source_event": donor.activation_event,
            "profile": donor.activation_profile, "destination_event": ids.activation_event,
            "trigger": "EventFlag(13604808)", "reset_each_load": True},
        "client_restore_event": ids.client_restore_event,
        "helper_lifecycle_event": ids.helper_lifecycle_event,
        "music_policy": "donor-final-declared-boundary-drives-destination-final-track",
        "attachments": [{"source_event": item.source_event,
                         "destination_event": ids.attachment_events[index]}
                        for index, item in enumerate(attachments)],
        "runtime_status": "unobserved",
    }

def patch_portable_donor_at_orphan(destination: str, donor: CombatPackage,
                                       donor_source: str,
                                       ids: OrphanArenaIds = DEFAULT_IDS) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ORPHAN_HASHES, "Orphan arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    if hashlib.sha256(source[0].encode()).hexdigest() != SOURCE_ZERO_HASHES[donor.key]:
        raise ValueError(f"{donor.key} Event(0) differs from pinned constructor source")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Orphan attachment capacity")
    targets = {item.source_event: ids.attachment_events[index]
               for index, item in enumerate(attachments)}
    virtual = {item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities}
    mapping = {donor.actor: PRIMARY, donor.completion_event: 13601800,
               donor.start_flag: 13604808, **targets, **virtual}
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        13604802: _health(arena[13604802], source[donor.health_bar_event], donor, ids.activation_event),
        13604803: _music(arena[13604803], donor, source, targets),
        13604804: _camera(donor, source),
        13604820: _noop(arena[13604820]),
        13604830: _noop(arena[13604830]),
        13604840: _noop(arena[13604840]),
        13604850: _noop(arena[13604850]),
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
        raise ValueError("Orphan adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Orphan adapter changed unrelated event {event_id}")
    return result

def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]

def _source_primary(slots: Sequence[Slot], donor: CombatPackage) -> Slot:
    candidates = [slot for slot in slots if slot.entity_id == donor.actor and slot.archetype == donor.archetype]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    binding = dict(donor.primary_state_bindings).get("00")
    if binding is None or binding not in by_state:
        raise ValueError(f"{donor.key} lacks explicit Orphan source-state binding")
    return by_state[binding]

def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Orphan donor source state lacks reviewed native evidence")
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

def native_plan_portable_donor_at_orphan(donor: CombatPackage, slots: Sequence[Slot],
        npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
        ids: OrphanArenaIds = DEFAULT_IDS) -> dict:
    _validate_ids(ids, "")
    targets = [slot for slot in slots if slot.map_name == DESTINATION_MAP]
    primaries = [slot for slot in targets if slot.entity_id == PRIMARY and slot.archetype == PRIMARY_ARCHETYPE]
    helpers = [slot for slot in targets if slot.entity_id in (PHASE, SHADOW, SUPPORT)]
    if (len(primaries) != 1 or len(helpers) != 3 or primaries[0].talk_id
            or {slot.archetype for slot in helpers}
            != {PHASE_ARCHETYPE, SHADOW_ARCHETYPE, SUPPORT_ARCHETYPE}):
        raise ValueError("Orphan destination roster differs from reviewed native source")
    target, source_primary = primaries[0], _source_primary(slots, donor)
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype},
        target.archetype, donor.archetype, destinations={target.key: {
            "map_name": target.map_name, "entity_id": target.entity_id,
            "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    plan = {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"orphan-of-kos<-{donor.key}"},
        "boss_contract": orphan_arena_contract(donor, ids),
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
        "policy": ("progression-owned post-boss actor; never touched by combat adapter"
                   if slot.entity_id == SHADOW else
                   "hidden inert destination helper until exact event 13601800 completes"),
    } for slot in helpers]
    requirements = actor_addition_requirements(ORPHAN_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan

def portable_orphan_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if donor.music_phase_signals and len(attachments) <= len(ATTACHMENT_EVENTS) and len(donor.virtual_entities) <= 1:
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)


