"""Reusable source-pinned Celestial Emissary destination arena.

The selected donor replaces the original small emissary at entity 2420810.
Celestial Emissary's c2570 giant remains hidden as the exact original terminal
subject: only confirmed death of the donor body kills it.  The native wave and
generator graph is retired without changing the shared Ebrietas encounter.

Arena geometry and gameplay remain unobserved.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from . import celestial_paarl_contract as ce
from .boss_canary import event_blocks, parse_events
from .boss_contracts import (
    PACKAGES,
    ArenaContract,
    Archetype,
    CombatPackage,
    EventAttachment,
    PartBinding,
    actor_addition_requirements,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m24_02_00_00.emevd.dcx.js"
MAP_PREFIX = "m24_02_"
MAP_STATES = ("m24_02_00_00", "m24_02_00_01")
PRIMARY = 2420810
GIANT = 2420811
PRIMARY_ARCHETYPE = Archetype("c2500", 250080, 250060, 0)
GIANT_ARCHETYPE = Archetype("c2570", 257010, 257010, 0)
WAVE_ARCHETYPE = Archetype("c2500", 250081, 250061, 0)
SUPPORT_ARCHETYPES = (
    Archetype("c2571", 257100, 1, 0),
    Archetype("c2571", 257101, 1, 0),
)
WAVES = (2420711, 2420712, 2420713, 2420716, 2420717, 2420719, 2420720)
SUPPORT = (2420750, 2420751)
GENERATORS = (2423711, 2423712, 2423713, 2423716, 2423717, 2423719, 2423720)
TERMINAL = 12421700
START_FLAG = 12424700
HEALTH_EVENT = 12424702
MUSIC_EVENT = 12424703
CAMERA_EVENT = 12424704

# Proven absent from the bundled original EMEVD/MSB corpus.  The composition
# builder independently scans selected project allocations.
ATTACHMENT_EVENTS = (12996900, 12996901, 12996902, 12996903, 12996904)
ACTIVATION_EVENT = 12996905
TERMINAL_BRIDGE_EVENT = 12996906
DESTINATION_CLEANUP_EVENT = 12996907
OWNER_CLEANUP_EVENT = 12996908
BULLET_OWNER_ENTITY = 984300

SUPPRESSED_EVENTS = (
    12424770, 12424780, 12424784, 12424785, 12424787,
    12424790, 12424791, 12424792, 12424795,
)

ARENA_HASHES: dict[int, str] = {
    0: "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
    12421700: "483357a45d27cb2f9df9212f1daf7f10119c4d35ad849e4d179f0dd9e34d2794",
    12421701: "74cf39dcaa359da0c26e3e97a3ea8f890f6eab39a6c0f42b9cc61bb128c3929d",
    12421702: "e5832b29e358dfe905ab5d47a0c23a84283f9b645dddecaf9a0e7e7ff56ed726",
    12421703: "bb9efdf0969275401f21b29c03ec6cb310a753c98c439f56c12738ebc16b44b0",
    12424702: "b95fb234bbd7f7f9696b5352703a0efb8f965fdafde6860489b2e017fe7ccb4b",
    12424703: "a73cb1fa43c1017779bc8c9c97fd6cfd51726dccdc4bf865dd8096b86b81a3c4",
    12424704: "3d91994d955c589fc9591706094ee3495f2cfadbe0c42081d19055f936b33301",
    12424705: "421cfaba876dca84f5ffeeb1e0c6c90cb8a4b70d07c62fde3452718e6c704da7",
    12424710: "d57762fba3f94d49bd9d510303765e9260adc1e75b4521269013b663b32d3ccd",
    12424711: "bcc2c705b0b096bdaab5e8abfbb8a4fa6f209bc8c78b3736aaed152bab434151",
    12424770: "0c3ad0e5b83f271b42caf897500cdd3327d2a7a383e729502d4085af9de191df",
    12424780: "58292f49f2c2bd4f192fee328efde8df50cf316bbe8a1c276ae3dbee85d32352",
    12424784: "e4ddde103a86fdfa89d4c7b741de7fb3289572f09141930f3deaf1329771ad60",
    12424785: "0dde9aa805e67a42f8105d18523be600fcc71aeca5de67455391ce6a034a21ea",
    12424787: "b08453f27d5cab1fa0b9caa19f92c6a50a55c1f7659fe0541118990e0355406c",
    12424790: "0c2c830c5dda5c32fbc108aa9ece339d2c65fe08156c229de8bc998bdfe3dd9a",
    12424791: "1f4a365ca7d7f959da65d08223b0f3562023ac20a704943f020d3c8e4bf76f43",
    12424792: "074453574579340828f22913794084de74be8b5fbaafa60d5c4483c34d0c05d8",
    12424795: "a69637947e83355022e5b883e1ce25bd6744e471beb8d2da54de8acbea6af417",
}

# The second boss in m24_02 is a composition boundary.  Every one of these
# blocks must remain byte-identical.
EBRIETAS_HASHES = {
    12421800: "7cb7c78833c5ef60a5599d35c22964e87b75f980c3165e139d7c28fc8a1bd34b",
    12421801: "2b01b305ae68b5d9e67407c316ed1a902f182124022987b9e258b527fb67f97f",
    12421802: "9bc79c8e55c2a2c9793a90070de1f76c35a46ebd98c2c79176b2fcc02ae8adc4",
    12421803: "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    12424802: "effdc8bf4ca63c0371f209afbd388d0c682793bc2efaf258675e871bcae21ad2",
    12424803: "a487e349f0a416298a26fb93c87c0c57fd7211e7da3da8938d37b6e909130966",
    12424804: "9324596b40c1d5a8ec57a11c71eab66105a1550a81cdcacd4432a86ec366ea74",
    12424805: "e5cd1832606baf9b45afa6e5acb1f12c3e34cb52c26a86a687a0d65022f152eb",
    12424810: "593b24830019a78d0d17d10df4808d26d50b2ab3c2a0b07bff678974b28d5729",
    12424811: "2c98ff8ebff5a7fc0c83dcd11e62cd255e587b9de534d2868d3ef08047987618",
    12424812: "b6e8cf0d6ca0a2afe743f9251730d15833be4f8a1c143e83ee9ce13dbb55256f",
    12424813: "640ca6bac740fe18404ee8f78f3e71bd6608f8914f3044bae018d9781f5e5e8d",
    12424870: "4fac0ea46041effd27d59b41752ef9758ba1c6021647ef9831f87de11e5564ba",
    12424871: "50091165e085e178edd4641859d7af08032e2dc4c1be99e7d3631ecbaa07abbc",
    12424980: "cebf5265578c05b598b8c2f9d2c524c852a32e48facb4856db1426185f098cb1",
    12424990: "0b8bf3929d610e3938673ca58072126cbde658e3aa75911c958a1b7e7f43a700",
}
EBRIETAS_EVENTS = tuple(EBRIETAS_HASHES)

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

CELESTIAL_ARENA_CONTRACT = ArenaContract(
    key="celestial-emissary", event_file=EVENT_FILE, map_prefix=MAP_PREFIX,
    actor=PRIMARY, archetype=PRIMARY_ARCHETYPE, destination_count=2,
    completion_event=TERMINAL, start_flag=START_FLAG,
    health_bar_event=HEALTH_EVENT, health_bar_label=257000,
    activation_event=12421702, music_event=MUSIC_EVENT,
    phase_music_message=None, lockcam_event=CAMERA_EVENT,
    lockcam_map=24, lockcam_subarea=2, phase_slots=(),
    co_op_entry_event=12421703, part_routine_event=None,
    cloth_routine_event=None, part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,), attachment_anchor_slot=0,
    attachment_anchor_event=12424795, expected=ARENA_HASHES,
    activation_idle_animation=None, music_phase_messages=(),
    retired_combat_events=SUPPRESSED_EVENTS,
    activation_profile="normalized-cinematic",
)


@dataclass(frozen=True)
class CelestialArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    activation_event: int = ACTIVATION_EVENT
    terminal_bridge_event: int = TERMINAL_BRIDGE_EVENT
    destination_cleanup_event: int = DESTINATION_CLEANUP_EVENT
    owner_cleanup_event: int = OWNER_CLEANUP_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (*self.attachment_events, self.activation_event,
                self.terminal_bridge_event, self.destination_cleanup_event,
                self.owner_cleanup_event, self.bullet_owner_entity)


DEFAULT_IDS = CelestialArenaIds()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _validate_ids(ids: CelestialArenaIds, destination: str) -> None:
    values = ids.values()
    events = {*ids.attachment_events, ids.activation_event,
              ids.terminal_bridge_event, ids.destination_cleanup_event,
              ids.owner_cleanup_event}
    if (len(values) != len(set(values))
            or events != set(range(12996900, 12996909))
            or ids.bullet_owner_entity != 984300):
        raise ValueError("Celestial arena requires the exact reviewed 12996900-08/984300 allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(f"Celestial arena IDs collide with original inputs: {sorted(collisions)}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Celestial arena expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(values.get(int(match[0]), int(match[0]))), text)


def _initializer(slot: int, event_id: int, arguments: tuple[str, ...]) -> str:
    return f"    $InitializeEvent({slot}, {event_id}" + (
        ", " + ", ".join(arguments) if arguments else "") + ");"


def _portable_attachments(donor: CombatPackage) -> tuple[EventAttachment, ...]:
    if donor.attachments:
        return donor.attachments
    if donor.part_routine_event is not None:
        if len(donor.phase_events) != 1 or not donor.part_bindings:
            raise ValueError(f"{donor.key} lacks an appendable phase/body shape")
        return (EventAttachment(donor.phase_events[0], (PartBinding(0, ()),)),
                EventAttachment(donor.part_routine_event, donor.part_bindings))
    if not donor.phase_events:
        raise ValueError(f"{donor.key} lacks source combat attachments")
    return tuple(EventAttachment(event_id, (PartBinding(0, ()),))
                 for event_id in donor.phase_events)


def _inert(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function(" + ", ".join(
            value.strip() if value.strip().startswith("unused_")
            else "unused_" + value.strip()
            for value in match[1].split(",") if value.strip()) + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


def _constructor(arena_zero: str, donor_zero: str, donor: CombatPackage,
                 attachments: Sequence[EventAttachment], targets: Mapping[int, int],
                 virtual_targets: Mapping[int, int], ids: CelestialArenaIds) -> str:
    lines: list[str] = []
    for attachment in attachments:
        for binding in attachment.initializers:
            witness = _initializer(binding.slot, attachment.source_event, binding.arguments)
            if donor_zero.count(witness) != 1:
                raise ValueError(f"{donor.key} Event(0) lacks unique attachment initializer")
            args = tuple(str(_remap(arg, {donor.actor: PRIMARY, **virtual_targets}))
                         for arg in binding.arguments)
            lines.append(_initializer(binding.slot, targets[attachment.source_event], args))
    for binding in donor.virtual_entities:
        witness = f"    {binding.initializer}({binding.source_entity});"
        if donor_zero.count(witness) != 1:
            raise ValueError(f"{donor.key} Event(0) lacks unique virtual-owner witness")
        lines.append(f"    {binding.initializer}({virtual_targets[binding.source_entity]});")
    lines.extend((_initializer(0, ids.activation_event, ()),
                  _initializer(0, ids.terminal_bridge_event, ()),
                  _initializer(0, ids.destination_cleanup_event, ())))
    if donor.virtual_entities:
        lines.append(_initializer(0, ids.owner_cleanup_event, ()))
    anchor = "    $InitializeEvent(0, 12424795);"
    result = _replace_once(arena_zero, anchor, anchor + "\n" + "\n".join(lines),
                           "constructor anchor")
    header = result.splitlines()[0] + "\n"
    return _replace_once(result, header,
                         header + f"    SetEventFlag({ids.activation_event}, OFF);\n",
                         "constructor readiness reset")


def _entry_host() -> str:
    return f"""$Event(12421702, Default, function() {{
    EndIf(EventFlag({TERMINAL}));
    EndIf(ThisEvent());
    ChangeCharacterEnableState({PRIMARY}, Disabled);
    WaitFor(!EventFlag({TERMINAL}) && !ThisEventSlot() && CharacterType(10000, TargetType.Alive) && InArea(10000, 2422815));
    IssueBossRoomEntryNotification(0);
    SetEventFlag({START_FLAG}, ON);
    SetEventFlag(12421702, ON);
}});"""


def _entry_guest() -> str:
    return f"""$Event(12421703, Default, function() {{
    WaitFor(CharacterType(10000, TargetType.Alive) && EventFlag({START_FLAG}));
    EndIf(HasMultiplayerState(MultiplayerState.Host));
    SetEventFlag({START_FLAG}, ON);
    SetEventFlag(12421702, ON);
}});"""


def _telemetry(block: str, owner: str) -> str:
    match = re.search(r"(?m)^    CreatePlaylog\([^\n]+\);\n    StartTimeMeasurement\([^\n]+\);", block)
    if match is None or len(re.findall(r"CreatePlaylog\(", block)) != 1:
        raise ValueError(f"{owner} health lacks unique telemetry")
    return match[0]


def _health(destination: str, source: str, donor: CombatPackage,
            ready_event: int) -> str:
    result = _remap(source, {
        donor.actor: PRIMARY, donor.completion_event: TERMINAL,
        donor.start_flag: START_FLAG, donor.health_bar_event: HEALTH_EVENT,
    })
    authority = re.search(
        rf"(?m)^\s*SetNetworkUpdateAuthority\({PRIMARY}, AuthorityLevel\.(?:Forced|Normal)\);$",
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
    replacement = f"{indent}{client}\n{indent}    {authority[0].strip()}\n{indent}}}"
    result = result[:line_start] + replacement + result[close + len("\n" + indent + "}"):]
    result, count = re.subn(
        r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
        lambda match: match[1] + f"        WaitFor(EventFlag({ready_event}));",
        result, count=1,
    )
    if count == 0:
        result = _replace_once(result, f"    WaitFor(EventFlag({START_FLAG}));",
                               f"    WaitFor(EventFlag({ready_event}));",
                               "health readiness")
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(
        result, f"L0:\n    SetEventFlag({START_FLAG}, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n    SetEventFlag({START_FLAG}, ON);",
        "saved-health readiness",
    )
    result = _replace_once(result, _telemetry(result, donor.key),
                           _telemetry(destination, "Celestial"), "telemetry")
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    helper_state = (
        f"    SetCharacterAIState({GIANT}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({GIANT}, Disabled);\n"
        f"    SetCharacterGravity({GIANT}, Disabled);\n" + "".join(
            f"    SetCharacterAIState({actor}, Disabled);\n"
            f"    SetCharacterHPBarDisplay({actor}, Disabled);\n"
            for actor in (*WAVES, *SUPPORT)
        )
    )
    result = _replace_once(
        result, f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);\n",
        f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);\n" + helper_state,
        "destination helper initialization",
    )
    return result


def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(f"{donor.key} activation lacks unique source witness {value}")


def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, START_FLAG
    prefix = (f"$Event({event_id}, Default, function() {{\n"
              f"    EndIf(EventFlag({TERMINAL}));\n"
              "    EndIf(ThisEvent());\n"
              f"    SetCharacterInvincibility({actor}, Enabled);\n")
    if donor.activation_profile == "host-entry-animation":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);",))
        body = (f"    WaitFor(EventFlag({flag}));\n"
                f"    ChangeCharacterEnableState({actor}, Enabled);\n"
                f"    ForceAnimationPlayback({actor}, 7001, false, false, false);\n"
                f"    SetCharacterInvincibility({actor}, Disabled);")
    elif donor.activation_profile == "protected-radius-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, true, false, false);", "WaitFixedTimeFrames(70);"))
        body = f"    ForceAnimationPlayback({actor}, 7000, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif donor.activation_profile == "gravity-warp-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 3028, false, false, false);", "WaitFixedTimeFrames(110);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterMaphits({actor}, true);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 3028, false, false, false);\n    WaitFixedTimeFrames(110);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterMaphits({actor}, false);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif donor.activation_profile == "object-gated-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7000, false, false, false);", f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);"))
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, false, false, false);\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif donor.activation_profile == "protected-area-wake":
        _witnesses(source, donor, (f"ForceAnimationPlayback({donor.actor}, 7003, true, false, false);", "WaitFixedTimeFrames(160);"))
        body = f"    SetCharacterMaphits({actor}, true);\n    SetCharacterGravity({actor}, Disabled);\n    ForceAnimationPlayback({actor}, 7003, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7006, false, false, false);\n    WaitFixedTimeFrames(30);\n    ForceAnimationPlayback({actor}, 7002, false, false, false);\n    WaitFixedTimeFrames(160);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterInvincibility({actor}, Disabled);\n    SetCharacterMaphits({actor}, false);"
    elif donor.activation_profile == "first-damage-wake":
        _witnesses(source, donor, (f"SetCharacterImmortality({donor.actor}, Enabled);", f"HasDamageType({donor.actor}, 10000, DamageType.Unspecified)"))
        body = f"    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7001, true, false, false);\n    SetCharacterImmortality({actor}, Enabled);\n    SetSpEffect({actor}, 5647, false);\n    WaitFor(EventFlag({flag}));\n    SetCharacterInvincibility({actor}, Disabled);\n    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({actor}, 7000, false, true, false);\n    SetCharacterImmortality({actor}, Disabled);\n    ClearSpEffect({actor}, 5647);"
    else:
        raise ValueError(f"Celestial arena lacks readiness adapter for {donor.key}/{donor.activation_profile}")
    return prefix + body + "\n});"


def _signal_condition(donor: CombatPackage, blocks: Mapping[int, str],
                      targets: Mapping[int, int]) -> str:
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


def _music(block: str, donor: CombatPackage, donor_blocks: Mapping[int, str],
           targets: Mapping[int, int]) -> str:
    return _replace_once(block, "        WaitFor(EventFlag(12424790));",
                         f"        WaitFor({_signal_condition(donor, donor_blocks, targets)});",
                         "phase music boundary")


CAMERA_EVENTS = {"blood-starved-beast": 12304804}


def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    mapping = {event_id: CAMERA_EVENT, donor.actor: PRIMARY,
               donor.completion_event: TERMINAL, donor.start_flag: START_FLAG}
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in blocks[event_id]:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 12424701
    result = _remap(blocks[event_id], mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(\d+, \d+,",
                            "SetLockcamSlotNumber(24, 2,", result)
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = f"    EndIf(EventFlag({TERMINAL}));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(result, header, header + guard,
                               "destination camera completion guard")
    return result


def _terminal_bridge(ids: CelestialArenaIds) -> str:
    return f"""$Event({ids.terminal_bridge_event}, Default, function() {{
    EndIf(EventFlag({TERMINAL}));
    WaitFor(CharacterDead({PRIMARY}));
    EndIf(EventFlag({TERMINAL}));
    ForceCharacterDeath({GIANT}, false);
}});"""


def _destination_cleanup(ids: CelestialArenaIds) -> str:
    generators = "".join(
        f"    DeactivateGenerator({entity}, Disabled);\n" for entity in GENERATORS)
    actors = "".join(
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);\n"
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        for entity in (*WAVES, *SUPPORT)
    )
    deaths = "".join(
        f"    ForceCharacterDeath({entity}, false);\n" for entity in (*WAVES, *SUPPORT)
    )
    return f"""$Event({ids.destination_cleanup_event}, Default, function() {{
{generators}    SetCharacterAIState({GIANT}, Disabled);
    SetCharacterHPBarDisplay({GIANT}, Disabled);
    SetCharacterGravity({GIANT}, Disabled);
{actors}    if (EventFlag({TERMINAL})) {{
{deaths}        EndEvent();
    }}
    WaitFor(EventFlag({TERMINAL}));
{deaths}}});"""


def _owner_cleanup(ids: CelestialArenaIds) -> str:
    return f"""$Event({ids.owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag({TERMINAL}));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""


def celestial_arena_contract(donor: CombatPackage,
                             ids: CelestialArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    targets = dict(zip((row.source_event for row in attachments), ids.attachment_events))
    return {
        "format": "bb-celestial-arena-contract-v1",
        "arena": "celestial-emissary", "donor": donor.key,
        "status": "planned", "writer_status": "not_integrated",
        "runtime_status": "unobserved",
        "placement_policy": "replace-original-small-emissary-at-native-spawn",
        "attachments": [
            {"source_event": row.source_event,
             "destination_event": targets[row.source_event]}
            for row in attachments
        ],
        "activation_event": ids.activation_event,
        "terminal_bridge_event": ids.terminal_bridge_event,
        "destination_cleanup_event": ids.destination_cleanup_event,
        "owner_cleanup_event": ids.owner_cleanup_event if donor.virtual_entities else None,
        "preserved_destination_events": [TERMINAL, 12421701, 12424705,
                                         12424710, 12424711, *EBRIETAS_EVENTS],
        "adapted_destination_events": [12421702, 12421703, HEALTH_EVENT,
                                       MUSIC_EVENT, CAMERA_EVENT,
                                       *SUPPRESSED_EVENTS],
        "terminal_policy": "byte-identical terminal; hidden original giant dies only after actual donor death",
        "disabled_destination_wave_events": list(SUPPRESSED_EVENTS),
        "source_hash_pins": dict(donor.expected),
        "arena_hash_pins": dict(ARENA_HASHES),
        "destination_native_evidence": {
            "maps": list(MAP_STATES),
            "primary_entity": PRIMARY,
            "primary_part_sha256": {
                state: ce.ACTOR_PINS[state][0] for state in MAP_STATES
            },
            "retained_actor_pins": {
                state: list(ce.ACTOR_PINS[state][1:]) for state in MAP_STATES
            },
            "retired_generator_pins": {
                state: list(ce.GENERATOR_PINS[state]) for state in MAP_STATES
            },
            "arena_region_pins": {
                state: list(ce.REGION_PINS[state]) for state in MAP_STATES
            },
        },
    }


def patch_portable_donor_at_celestial_emissary(
    destination: str,
    donor: CombatPackage,
    donor_source: str,
    ids: CelestialArenaIds = DEFAULT_IDS,
) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Celestial arena")
    _verify(arena, EBRIETAS_HASHES, "shared Ebrietas")
    _verify(source, donor.expected, f"{donor.key} donor")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Celestial attachment capacity")
    targets = dict(zip((row.source_event for row in attachments), ids.attachment_events))
    virtual_targets = dict(zip((row.source_entity for row in donor.virtual_entities),
                               (ids.bullet_owner_entity,)))
    if len(virtual_targets) != len(donor.virtual_entities):
        raise ValueError(f"{donor.key} exceeds Celestial virtual-entity capacity")
    remap = {
        donor.actor: PRIMARY, donor.completion_event: TERMINAL,
        donor.start_flag: START_FLAG, donor.health_bar_event: HEALTH_EVENT,
        **targets, **virtual_targets,
    }
    additions = {
        targets[row.source_event]: _remap(source[row.source_event], remap)
        for row in attachments
    }
    additions[ids.activation_event] = _activation(donor, source, ids.activation_event)
    additions[ids.terminal_bridge_event] = _terminal_bridge(ids)
    additions[ids.destination_cleanup_event] = _destination_cleanup(ids)
    if donor.virtual_entities:
        additions[ids.owner_cleanup_event] = _owner_cleanup(ids)
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets,
                        virtual_targets, ids),
        12421702: _entry_host(),
        12421703: _entry_guest(),
        HEALTH_EVENT: _health(arena[HEALTH_EVENT], source[donor.health_bar_event],
                              donor, ids.activation_event),
        MUSIC_EVENT: _music(arena[MUSIC_EVENT], donor, source, targets),
        CAMERA_EVENT: _camera(donor, source),
        **{event_id: _inert(arena[event_id]) for event_id in SUPPRESSED_EVENTS},
    }
    result = (_replace_events(destination, edits).rstrip() + "\n\n" +
              "\n\n".join(additions[event_id] for event_id in additions) + "\n")
    output = event_blocks(result)
    if set(output) != set(arena) | set(additions):
        raise ValueError("Celestial arena changed unexpected event identities")
    for event_id, original in arena.items():
        if event_id not in edits and output[event_id] != original:
            raise ValueError(f"Celestial arena touched unrelated event {event_id}")
    if output[TERMINAL] != arena[TERMINAL]:
        raise ValueError("Celestial arena changed destination terminal")
    for event_id in EBRIETAS_EVENTS:
        if output[event_id] != arena[event_id]:
            raise ValueError(f"Celestial arena changed shared Ebrietas event {event_id}")
    copied = "\n".join(output[event_id] for event_id in
                       (12421702, 12421703, HEALTH_EVENT, CAMERA_EVENT, *additions))
    donor_prefix = donor.actor // 100000
    if donor_prefix != 24 and re.search(
            rf"(?<!\d){donor_prefix}\d{{5,6}}(?!\d)", copied):
        raise ValueError(f"{donor.key} Celestial transplant retains donor-map literals")
    return result


def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]


def _exact_slots(slots: Sequence[Slot], entity: int, archetype: Archetype,
                 label: str) -> list[Slot]:
    found = sorted(
        (slot for slot in slots if slot.entity_id == entity
         and slot.archetype == archetype and slot.map_name in MAP_STATES),
        key=lambda slot: slot.map_name,
    )
    if (len(found) != len(MAP_STATES)
            or {slot.map_name for slot in found} != set(MAP_STATES)
            or any(slot.dummy for slot in found)):
        raise ValueError(f"Celestial arena lacks exact two-state {label} closure")
    return found


def _source_by_state(slots: Sequence[Slot], donor: CombatPackage) -> dict[str, Slot]:
    candidates = [slot for slot in slots if slot.entity_id == donor.actor
                  and slot.archetype == donor.archetype]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    declared = dict(donor.primary_state_bindings)
    result: dict[str, Slot] = {}
    for destination_state in ("00", "01"):
        source_state = declared.get(destination_state)
        if source_state is None or source_state not in by_state:
            raise ValueError(f"{donor.key} lacks pinned source state for {destination_state}")
        result[destination_state] = by_state[source_state]
    return result


def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Celestial donor source state lacks reviewed native evidence")
    return {
        "source_map": source.map_name, "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1",
                              "part_sha256": pin},
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                   "damage_anim_id", "provenance"],
    }


def _retained(slots: Sequence[Slot]) -> list[dict]:
    specs = [(GIANT, GIANT_ARCHETYPE, "hidden terminal subject")]
    specs.extend((entity, WAVE_ARCHETYPE, "disabled original wave") for entity in WAVES)
    specs.extend((entity, SUPPORT_ARCHETYPES[index], "disabled original support")
                 for index, entity in enumerate(SUPPORT))
    rows: list[dict] = []
    for part_index, (entity, archetype, policy) in enumerate(specs, start=1):
        for slot in _exact_slots(slots, entity, archetype, str(entity)):
            rows.append({
                "map": slot.map_name, "part": slot.part_name,
                "entity_id": slot.entity_id, "archetype": asdict(slot.archetype),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": ce.ACTOR_PINS[slot.map_name][part_index],
                },
                "source_initialization": dict(SOURCE_INITIALIZATION),
                "policy": policy,
            })
    return rows


def native_plan_portable_donor_at_celestial_emissary(
    donor: CombatPackage,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: CelestialArenaIds = DEFAULT_IDS,
) -> dict:
    _validate_ids(ids, "")
    targets = _exact_slots(slots, PRIMARY, PRIMARY_ARCHETYPE, "primary")
    if any(slot.talk_id for slot in targets):
        raise ValueError("Celestial destination primary TalkID witness drift")
    sources = _source_by_state(slots, donor)
    target = targets[0]
    swap = Swap(
        target.logical_key, [slot.key for slot in targets],
        {slot.key: slot.archetype for slot in targets},
        target.archetype, donor.archetype,
        warnings=["runtime arena geometry and donor wake remain unobserved"],
        destinations={
            slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                       "x": slot.x, "y": slot.y, "z": slot.z}
            for slot in targets
        },
    )
    changes, skips = plan_scaling([swap], targets, dict(npcs), dict(effects),
                                  boss_tiers=True)
    if len(changes) > len(targets) or (changes and skips):
        raise ValueError(f"Celestial arena has ambiguous {donor.key} normalization")
    contract = celestial_arena_contract(donor, ids)
    contract["retained_destination_helpers"] = _retained(slots)
    plan = {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract":
                    f"celestial-emissary<-{donor.key}"},
        "boss_contract": contract,
        "primary_init_source_bindings": [
            _binding(sources[_state(destination.map_name)], destination)
            for destination in targets
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips), "skips": skips,
        },
    }
    requirements = actor_addition_requirements(
        CELESTIAL_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        if len(requirements) != 2 or donor.key != "ebrietas":
            raise ValueError(f"Celestial arena has unsupported {donor.key} actor additions")
        for requirement in requirements:
            requirement["destination_entity_id"] = ids.bullet_owner_entity
            requirement["destination_anchor_part"] = next(
                slot.part_name for slot in targets
                if slot.map_name == requirement["destination_map"])
        plan["boss_actor_addition_requirements"] = requirements
    return plan


def portable_celestial_donors(
    packages: Sequence[CombatPackage] = PACKAGES,
) -> tuple[CombatPackage, ...]:
    result = tuple(packages)
    for donor in result:
        attachments = _portable_attachments(donor)
        if (not donor.expected or not donor.music_phase_signals
                or donor.activation_event not in donor.expected
                or len(attachments) > len(ATTACHMENT_EVENTS)
                or len(donor.virtual_entities) > 1):
            raise ValueError(f"{donor.key} lacks a complete portable combat contract")
    return result
