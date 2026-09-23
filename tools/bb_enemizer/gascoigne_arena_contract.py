"""Reusable source-pinned Father Gascoigne destination arena.

The active donor replaces the human body in all three physical map states.
Gascoigne's beast remains an inert, invincible terminal proxy until the
destination's exact terminal event has completed.  The adapter preserves the
destination's entry, fog, co-op, rewards, telemetry, and progression while
installing the donor's complete combat package and source-backed wake.
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
    AMYGDALA_PACKAGE, BSB_PACKAGE, PACKAGES, ArenaContract, Archetype,
    CombatPackage, EventAttachment, MusicPhaseSignal, actor_addition_requirements,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m24_01_00_00.emevd.dcx.js"
MAP_PREFIX = "m24_01_"
MAP_STATES = ("m24_01_00_00", "m24_01_00_01", "m24_01_00_11")
HUMAN = 2410810
BEAST_PROXY = 2410811
HUMAN_ARCHETYPE = Archetype("c2710", 271000, 271000, 0)
BEAST_ARCHETYPE = Archetype("c2720", 272000, 272000, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12995300, 12995301, 12995302, 12995303, 12995304)
OWNER_CLEANUP_EVENT = 12995305
ACTIVATION_EVENT = 12995306
PROXY_CLEANUP_EVENT = 12995307
BULLET_OWNER_ENTITY = 982800
BEAST_PINS = {
    "m24_01_00_00": "19098d7da3476516f7a30723313e69c6cb21a54e035ea9623ac473bf42ebbb41",
    "m24_01_00_01": "8e69e51cc3aa02368933c62bd0ee9c602e711a41f8d7246697019900f46483c5",
    "m24_01_00_11": "e497ae7a9554cc8c43b7caf9a4764fc90b3914ffb38ccecdbf191cc650c57ba8",
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

GASCOIGNE_HASHES: dict[int, str | tuple[str, ...]] = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    12411800: ("b1a11b96d57174d9b9636387fa25c631ca8a1469e55297a602e9c58875c204a0",
               "c6eb236fba9e48406dd9088747c3d54bc054784718a67305da498934c2c98b9c"),
    12411801: "ba2c1d24b517fe59049626335841912c3ee5ae505aca6abf2956a560eb5b4eaf",
    12411802: "f803bd5dfa427d7e8e80ed46fe4f346973ad5c9ae090d481c005d4bff10eba78",
    12411803: "0ec656f1563ee0d007df8a53e808cbb4ceb978b039f99c3f001761b0d5ea5f43",
    12414802: "3a8b68b527fc00ad30fc5561c9a64f881ee9708db2d506dd04d986458e6f17a2",
    12414803: "a6b50e5c86a3b2471166de37c25da11361053e96065b263c7220913f79399150",
    12414804: "039705347b21101bf2d6309ee55595559ff21f4a6a4be4e7cd6bc622783586c7",
    12414805: "dc0eed4db0bafb7b37deb61b74994b00f1d060d9aebea20bd883dfa3ac9c0245",
    12414807: "7f72ec81a9ce98a3e41792eace02ad700a0420e9b2dfabc009b4641927c3de1e",
    12414808: "60c1f7f7ecbdf2f5cd1e0654f928a1cfcf36abd795523c3c766c4c95290fff15",
    12414809: "54c7fe426f39a828b938c14d6201fa53d9ab4b7f4e83c0d382b33c92d256a938",
    12414810: "acbd4681a4a41c5a9bd32a70588167dc835ba7c006754c30d0af257f88e8377f",
    12414811: "852db84220420f3c06fd971058d7b9f047ed16cfaa2a89c918e6335be6ad5473",
    12414812: "f1c56683f57b2d7a8a3c8e2ccbd8e44c1637ba017b45374b06ba94cd05af4ded",
    12414813: "cc9019ea7e6400994312361ed6008d0b5f86f5488e0a9a77cdd6b10d9158c580",
    12415238: "f6726aef66b4439f467ca03cd7975dc2933bea5fe5986be18f84b77bb67c27db",
}

GASCOIGNE_ARENA_CONTRACT = ArenaContract(
    key="father-gascoigne", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=HUMAN, archetype=HUMAN_ARCHETYPE, destination_count=3,
    completion_event=12411800, start_flag=12414800,
    health_bar_event=12414802, health_bar_label=271000,
    activation_event=12411802, music_event=12414803,
    phase_music_message=None, lockcam_event=12414804,
    lockcam_map=24, lockcam_subarea=1, phase_slots=(),
    co_op_entry_event=12411803, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=12414809,
    expected={key: value if isinstance(value, str) else value[0]
              for key, value in GASCOIGNE_HASHES.items()},
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=(12414807, 12414808, 12414809),
    activation_profile="normalized-cinematic",
)

@dataclass(frozen=True)
class GascoigneArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    owner_cleanup_event: int = OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    proxy_cleanup_event: int = PROXY_CLEANUP_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY
    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.owner_cleanup_event,
                self.activation_event, self.proxy_cleanup_event,
                self.bullet_owner_entity)

DEFAULT_IDS = GascoigneArenaIds()

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

def _validate_ids(ids: GascoigneArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Gascoigne arena IDs must be unique positive project IDs")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Gascoigne arena IDs collide with original inputs: {sorted(collisions)}")

def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"

def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gascoigne arena expected one {label}")
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
                 virtual_targets: Mapping[int, int], ids: GascoigneArenaIds) -> str:
    result = arena_zero
    for literal in (
        "    $InitializeEvent(0, 12415238, 2412820, 2410810, 2412821, 2412824, 2412822);\n",
        "    $InitializeEvent(1, 12415238, 2412820, 2410811, 2412821, 2412824, 2412822);\n",
    ):
        result = _replace_once(result, literal, "", "Gascoigne navigation initializer")
    anchor = "    $InitializeEvent(0, 12414809);"
    lines: list[str] = []
    for attachment in attachments:
        target = targets[attachment.source_event]
        for binding in attachment.initializers:
            args = tuple(str(_remap(arg, {donor.actor: HUMAN, **virtual_targets}))
                         for arg in binding.arguments)
            lines.append(_initializer(binding.slot, target, args))
    lines.extend((_initializer(0, ids.activation_event, ()),
                  _initializer(0, ids.proxy_cleanup_event, ())))
    if donor.virtual_entities:
        lines.append(_initializer(0, ids.owner_cleanup_event, ()))
    return _replace_once(result, anchor, anchor + "\n" + "\n".join(lines), "constructor anchor")

def _telemetry(block: str, owner: str) -> str:
    match = re.search(r"(?m)^    CreatePlaylog\([^\n]+\);\n    StartTimeMeasurement\([^\n]+\);", block)
    if match is None or len(re.findall(r"CreatePlaylog\(", block)) != 1:
        raise ValueError(f"{owner} health lacks unique telemetry")
    return match[0]

def _health(destination: str, source: str, donor: CombatPackage, ready_event: int) -> str:
    result = _remap(source, {donor.actor: HUMAN, donor.completion_event: 12411800,
                             donor.start_flag: 12414800,
                             donor.health_bar_event: 12414802})
    authority = re.search(r"(?m)^\s*SetNetworkUpdateAuthority\(2410810, AuthorityLevel\.(?:Forced|Normal)\);$", result)
    if authority is None:
        raise ValueError(f"{donor.key} health lacks authority witness")
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    start = result.rfind(client, 0, authority.start())
    line_start = result.rfind("\n", 0, start) + 1
    indent = result[line_start:start]
    close = result.find("\n" + indent + "}", authority.end())
    if start < 0 or close < 0:
        raise ValueError(f"{donor.key} health lacks client branch")
    replacement = (f"{indent}{client}\n{indent}    if (!EventFlag(12414223)) {{\n"
                   f"{indent}        IssueBossRoomEntryNotification(0);\n{indent}    }}\n"
                   f"{indent}    {authority[0].strip()}\n{indent}}}")
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
                            lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));", result, count=1)
    if count == 0:
        result = _replace_once(result, "    WaitFor(EventFlag(12414800));",
                               f"    WaitFor(EventFlag({ready_event}));", "health readiness")
    result = _replace_once(result, "    SetEventFlag(12414800, ON);",
                           "    SetEventFlag(12414800, ON);\n    SetEventFlag(12414223, ON);",
                           "room notification ownership")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Gascoigne"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result

def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")

def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], HUMAN, 12414800
    prefix = f"$Event({event_id}, Default, function() {{\n    EndIf(EventFlag(12411800));\n    EndIf(ThisEvent());\n"
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
        raise ValueError(f"Gascoigne arena lacks readiness adapter for {donor.key}/{profile}")
    return prefix + body + suffix

def _signal_condition(donor: CombatPackage, blocks: Mapping[int, str], targets: Mapping[int, int]) -> str:
    signal = donor.music_phase_signals[-1]
    source = blocks[signal.source_event]
    if signal.kind == "message" and signal.message is not None:
        witness = f"CharacterHasEventMessage({donor.actor}, {signal.message})"
        if witness not in source:
            raise ValueError(f"{donor.key} lacks final music message witness")
        return f"CharacterHasEventMessage({HUMAN}, {signal.message})"
    if signal.kind == "event_flag" and signal.source_event in targets:
        return f"EventFlag({targets[signal.source_event]})"
    raise ValueError(f"{donor.key} final music boundary is not portable")

def _music(block: str, donor: CombatPackage, donor_blocks: Mapping[int, str], targets: Mapping[int, int]) -> str:
    condition = _signal_condition(donor, donor_blocks, targets)
    return _replace_once(block, "flagArea2 &= EventFlag(12414807);",
                         f"flagArea2 &= {condition};", "final music boundary")

def _camera(block: str) -> str:
    for witness in ("SetLockcamSlotNumber(24, 1, 1);",
                    "SetLockcamSlotNumber(24, 1, 0);",
                    "EntityInRadiusOfEntity(10000, 2410810, 5.5)"):
        if witness not in block:
            raise ValueError("Gascoigne camera lacks pinned destination geometry")
    # The original branch follows the retired human/beast transformation flag.
    # A single-primary donor always uses the human placement and the same arena
    # radii, independent of stale transformation state on a retry load.
    return """$Event(12414804, Default, function() {
    SetNetworkSyncState(Disabled);
    EndIf(EventFlag(12411800));
    WaitFor(HPRatio(2410810) > 0 && EntityInRadiusOfEntity(10000, 2410810, 5.5));
    SetLockcamSlotNumber(24, 1, 1);
    WaitFor(HPRatio(2410810) > 0 && !EntityInRadiusOfEntity(10000, 2410810, 6));
    SetLockcamSlotNumber(24, 1, 0);
    RestartEvent();
});"""

def _proxy_cleanup(ids: GascoigneArenaIds) -> str:
    return f"""$Event({ids.proxy_cleanup_event}, Restart, function() {{
    ChangeCharacterEnableState(2410811, Disabled);
    SetCharacterAIState(2410811, Disabled);
    SetCharacterHPBarDisplay(2410811, Disabled);
    SetCharacterGravity(2410811, Disabled);
    SetCharacterInvincibility(2410811, Enabled);
    GotoIf(L0, EventFlag(12411800));
    WaitFor(EventFlag(12411800));
L0:
    SetCharacterInvincibility(2410811, Disabled);
    ForceCharacterDeath(2410811, false);
}});"""

def _owner_cleanup(ids: GascoigneArenaIds) -> str:
    return f"""$Event({ids.owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12411800));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""

def gascoigne_arena_contract(donor: CombatPackage, ids: GascoigneArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-gascoigne-arena-contract-v1", "status": "experimental",
        "arena": "father-gascoigne", "donor": donor.key, "allocation": asdict(ids),
        "preserved_destination_events": [12411800, 12411801, 12411802, 12411803,
            12414805, 12414810, 12414811, 12414812, 12414813, 12415238],
        "adapted_destination_events": [12414802, 12414803, 12414804],
        "retired_destination_controllers": [12414807, 12414808, 12414809],
        "removed_navigation_initializers": 2,
        "terminal_proxy": {"entity": BEAST_PROXY, "event": ids.proxy_cleanup_event,
                           "policy": "inert-and-alive-until-destination-terminal"},
        "readiness_adapter": {"source_event": donor.activation_event,
            "profile": donor.activation_profile, "destination_event": ids.activation_event,
            "trigger": "EventFlag(12414800)"},
        "music_policy": "donor-final-phase-boundary-drives-destination-final-track",
        "attachments": [{"source_event": item.source_event,
                         "destination_event": ids.attachment_events[index]}
                        for index, item in enumerate(attachments)],
        "runtime_status": "unobserved",
    }

def patch_portable_donor_at_gascoigne(destination: str, donor: CombatPackage,
                                       donor_source: str,
                                       ids: GascoigneArenaIds = DEFAULT_IDS) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, GASCOIGNE_HASHES, "Gascoigne arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Gascoigne attachment capacity")
    targets = {item.source_event: ids.attachment_events[index]
               for index, item in enumerate(attachments)}
    virtual = {item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities}
    mapping = {donor.actor: HUMAN, donor.completion_event: 12411800,
               donor.start_flag: 12414800, **targets, **virtual}
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        12414802: _health(arena[12414802], source[donor.health_bar_event], donor, ids.activation_event),
        12414803: _music(arena[12414803], donor, source, targets),
        12414804: _camera(arena[12414804]),
        12414807: _noop(arena[12414807]),
        12414808: _noop(arena[12414808]),
        12414809: _noop(arena[12414809]),
    }
    additions.extend((_activation(donor, source, ids.activation_event), _proxy_cleanup(ids)))
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    expected = set(arena) | set(targets.values()) | {ids.activation_event, ids.proxy_cleanup_event}
    if donor.virtual_entities:
        expected.add(ids.owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("Gascoigne adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Gascoigne adapter changed unrelated event {event_id}")
    return result

def _slots(slots: Sequence[Slot], entity: int, archetype: Archetype,
           maps: set[str], label: str) -> list[Slot]:
    found = sorted((slot for slot in slots if slot.entity_id == entity and
                    slot.archetype == archetype and slot.map_name in maps), key=lambda s: s.map_name)
    if len(found) != len(maps) or {slot.map_name for slot in found} != maps or any(slot.dummy for slot in found):
        raise ValueError(f"Gascoigne/{label} lacks exact physical state closure")
    return found

def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]

def _source_by_state(slots: Sequence[Slot], donor: CombatPackage) -> dict[str, Slot]:
    candidates = [slot for slot in slots if slot.entity_id == donor.actor and slot.archetype == donor.archetype]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    result = {}
    for destination_state, source_state in donor.primary_state_bindings:
        if source_state not in by_state:
            raise ValueError(f"{donor.key} lacks pinned source state {source_state}")
        result[destination_state] = by_state[source_state]
    if set(result) != {"00", "01", "11"}:
        raise ValueError(f"{donor.key} lacks Gascoigne three-state binding")
    return result

def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Gascoigne donor source state lacks reviewed native evidence")
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

def native_plan_portable_donor_at_gascoigne(donor: CombatPackage, slots: Sequence[Slot],
        npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
        ids: GascoigneArenaIds = DEFAULT_IDS) -> dict:
    _validate_ids(ids, "")
    states = set(MAP_STATES)
    humans = _slots(slots, HUMAN, HUMAN_ARCHETYPE, states, "human")
    proxies = _slots(slots, BEAST_PROXY, BEAST_ARCHETYPE, states, "beast proxy")
    if any(slot.talk_id != 241330 for slot in humans) or any(slot.talk_id for slot in proxies):
        raise ValueError("Gascoigne destination TalkID witnesses drift")
    sources = _source_by_state(slots, donor)
    target = humans[0]
    swap = Swap(target.logical_key, [slot.key for slot in humans],
        {slot.key: slot.archetype for slot in humans}, target.archetype, donor.archetype,
        destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
            "x": slot.x, "y": slot.y, "z": slot.z} for slot in humans})
    changes, skips = plan_scaling([swap], humans, dict(npcs), dict(effects), boss_tiers=True)
    plan = {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"father-gascoigne<-{donor.key}"},
        "boss_contract": gascoigne_arena_contract(donor, ids),
        "primary_init_source_bindings": [_binding(sources[_state(target.map_name)], target) for target in humans],
        "scaling": {"enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect", "change_count": len(changes),
            "changes": [change.json() for change in changes], "skip_count": len(skips), "skips": skips}}
    plan["boss_contract"]["retained_destination_helpers"] = [{
        "map": slot.map_name, "part": slot.part_name, "entity_id": slot.entity_id,
        "archetype": asdict(slot.archetype),
        "source_provenance": {"format": "bb-boss-actor-pin-v1",
                              "part_sha256": BEAST_PINS[slot.map_name]},
        "source_initialization": {"talk_id": 0, "unk_t18": -1,
                                  "init_anim_id": -1, "damage_anim_id": -1},
        "policy": "hidden invincible terminal proxy until exact event 12411800 completes",
    } for slot in proxies]
    requirements = actor_addition_requirements(GASCOIGNE_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan

def portable_gascoigne_donors(packages: Sequence[CombatPackage] = PACKAGES) -> tuple[CombatPackage, ...]:
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if donor.music_phase_signals and len(attachments) <= len(ATTACHMENT_EVENTS) and len(donor.virtual_entities) <= 1:
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)
