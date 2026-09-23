"""Reusable source-pinned Moon Presence destination arena."""

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
EVENT_FILE = "m21_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m21_00_"
DESTINATION_MAP = "m21_00_00_00"
PRIMARY = 2100810
PRIMARY_ARCHETYPE = Archetype("c5400", 540000, 540000, 0)

# Disjoint from the reviewed Gehrman destination's 129961xx/983600 range.
# The builder repeats its whole-composition collision scan before accepting it.
ATTACHMENT_EVENTS = (12996200, 12996201, 12996202, 12996203, 12996204)
ACTIVATION_EVENT = 12996205
DONOR_OWNER_CLEANUP_EVENT = 12996206
BULLET_OWNER_ENTITY = 983700
DESTINATION_PINS = {
    PRIMARY: "fb6b3c45b1c16ec4aa7bc8ff6cb2107caa06f98a4e6c26bd7f0d3064f84f4e67",
    2100800: "1c42091a9cacab2c22f7bc0056deafca140095a619fd1c68716158257427abc0",
    2100801: "87508ce80a4eccf3c5637e7db80b080791f6ce1e8e7ffa2ab41c3bcb7e958352",
}
DESTINATION_MSB_SHA256 = (
    "d9f1142ed6d67233b8333f948f2d84f7fe80111005ddd77487a7dac8438a23a1"
)
DESTINATION_FFX_SHA256 = (
    "ac9c86d74fe048b694f8b63940ae404404de6b78184d01d613362b3774258825"
)
SOURCE_PART_PINS = {
    (
        "m23_00_00_00",
        2300800,
    ): "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
    (
        "m23_00_00_01",
        2300800,
    ): "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
    (
        "m23_00_00_00",
        2300810,
    ): "cac704506e58dfd3f2c57113d919fafe0a70d01b7a40b869deffa3c6e22cc0a2",
    (
        "m23_00_00_01",
        2300810,
    ): "6c8a693b9c846922a1113726ec69a11b47973c5e367a94757ad82d3fbf3081ee",
    (
        "m24_01_00_00",
        2410800,
    ): "0225c170ffac0c48d69f996e361b83c5490069e4a75fdc6b19328458f2fd3848",
    (
        "m24_01_00_01",
        2410800,
    ): "34c019e726003bf86523ef384e74c2fb050c4d7d82ab8012ddfc8ba42d6f0940",
    (
        "m24_01_00_11",
        2410800,
    ): "a8ca2f725b4e7d1c823912bbb0131a17dfba84d50f0c2713b820db78bc8722b3",
    (
        "m24_00_00_00",
        2400800,
    ): "99f32c1296938362bd6d5abbcc073f6179fd9173f18a3a5076391d37ff88c35e",
    (
        "m24_00_00_01",
        2400800,
    ): "ba04891b13b4fff5ad61eebf53c4715c89ef70e9599025d4335cb558b808a4e5",
    (
        "m33_00_00_00",
        3300800,
    ): "4d66ca60f567e2f0ba0ffcc43fb45c5666265fd9649952cc3828185f0ef1bc39",
    (
        "m24_02_00_00",
        2420800,
    ): "5f6ed3a557a24f54151a77bc3de15ce5f8d8645d6ad5cafc94fe4449b91ce5c2",
    (
        "m24_02_00_01",
        2420800,
    ): "6e96e026cb750d840a621e27ec07658b9953c62b061c79ca8d5b95227c87dcbb",
}
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
SOURCE_ZERO_HASHES = {
    "blood-starved-beast": "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    "darkbeast-paarl": "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    "cleric-beast": "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    "vicar-amelia": "31936ed53ff8d095dcae5257c6d36e321a55bc8cd53ed564a1510363a9a04e27",
    "amygdala": "b86f288c46fc74ddc81530e62437d9497c5a63ec09488c068211d85f4054f934",
    "ebrietas": "cda0f114ad3f96b4b93fda3b81ac6d6ed5808bdb0be3f6d16e8225733e729dde",
}

MOON_HASHES: dict[int, str] = {
    0: "fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26",
    12101850: "ae1a5ecc4c0d2149f20d20a414cb8e374db9de618aa264ec226d48bedc738fdb",
    12101852: "0bde50f079f63078dd127d785f34e8ebdd8fce5cdaf44f5f5581fb69c01df3fb",
    12101853: "0af3db4f4d7710d985b8ba674edfab6f39eabc18607485974b22df59f295d425",
    12104852: "a4022f49059e7bc5cb6a076481065f8418a885876121ec9a8f731120ccfe395e",
    12104853: "38b0df8eb0fb98bdf5e9e5f2c752f5220ffe23b35e5645e53eebad46e42adce4",
    12104854: "32ebde44a49a6b7a58b9ab4bc6b84e3187e8d3fb5721ef6ab19bab853ba65fe4",
    12104855: "99b339663849ea8bc818155aa85dfded02f8a7c6ebf7b04360f40b071749815b",
    12104860: "5b91d32d18d586cd20510e5157b5ca35b7783efe137e6120dfd2c60d62cd6af9",
    12104870: "dc32a765534443ea5b41c0d1646f0d658417d29c359357cfb6daf1d00d483ad6",
    12104880: "fbfdd70867fed1b5d6dee2578293197c03c816b09e3ca09cbbb4f8edd6244586",
    12104881: "a65ecfd5d47cac05b47888ffb460ea96d2d9e88b97d981a1e006e3a4292c2c4d",
}

MOON_ARENA_CONTRACT = ArenaContract(
    key="moon-presence",
    event_file=EVENT_FILE,
    map_prefix=MAP_PREFIX,
    actor=PRIMARY,
    archetype=PRIMARY_ARCHETYPE,
    destination_count=1,
    completion_event=12101850,
    start_flag=12104850,
    health_bar_event=12104852,
    health_bar_label=540000,
    activation_event=12101852,
    music_event=12104853,
    phase_music_message=500,
    lockcam_event=12104854,
    lockcam_map=21,
    lockcam_subarea=0,
    phase_slots=(12104860, 12104870),
    co_op_entry_event=12101853,
    part_routine_event=12104860,
    cloth_routine_event=None,
    part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,),
    attachment_anchor_slot=0,
    attachment_anchor_event=12104870,
    expected=MOON_HASHES,
    activation_idle_animation=None,
    music_phase_messages=(500,),
    retired_combat_events=(12104860, 12104870),
    activation_profile="normalized-cinematic",
)


@dataclass(frozen=True)
class MoonArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    donor_owner_cleanup_event: int = DONOR_OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (
            *self.attachment_events,
            self.donor_owner_cleanup_event,
            self.activation_event,
            self.bullet_owner_entity,
        )


DEFAULT_IDS = MoonArenaIds()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _verify(
    blocks: Mapping[int, str], expected: Mapping[int, str | tuple[str, ...]], role: str
) -> None:
    for event_id, digests in expected.items():
        body = blocks.get(event_id)
        allowed = (digests,) if isinstance(digests, str) else digests
        if body is None or hashlib.sha256(body.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _validate_ids(ids: MoonArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Moon arena IDs must be unique positive project IDs")
    event_ids = {
        *ids.attachment_events,
        ids.activation_event,
        ids.donor_owner_cleanup_event,
    }
    if event_ids != set(range(12996200, 12996207)) or ids.bullet_owner_entity != 983700:
        raise ValueError("Moon arena requires the exact reviewed narrow allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(
            f"Moon arena IDs collide with original inputs: {sorted(collisions)}"
        )


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                value.strip()
                if value.strip().startswith("unused_")
                else "unused_" + value.strip()
            )
            for value in match[1].split(",")
            if value.strip()
        )
        + ")",
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Moon arena expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(block: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        block,
    )


def _initializer(slot: int, event_id: int, arguments: tuple[str, ...]) -> str:
    return (
        f"    $InitializeEvent({slot}, {event_id}"
        + (", " + ", ".join(arguments) if arguments else "")
        + ");"
    )


def _portable_attachments(donor: CombatPackage) -> tuple[EventAttachment, ...]:
    if donor.attachments:
        return donor.attachments
    if donor.part_routine_event is not None:
        if len(donor.phase_events) != 1 or not donor.part_bindings:
            raise ValueError(f"{donor.key} lacks an appendable phase/body shape")
        from .boss_contracts import PartBinding

        return (
            EventAttachment(donor.phase_events[0], (PartBinding(0, ()),)),
            EventAttachment(donor.part_routine_event, donor.part_bindings),
        )
    if not donor.phase_events:
        raise ValueError(f"{donor.key} lacks source combat attachments")
    from .boss_contracts import PartBinding

    return tuple(
        EventAttachment(event_id, (PartBinding(0, ()),))
        for event_id in donor.phase_events
    )


def _constructor(
    arena_zero: str,
    donor_zero: str,
    donor: CombatPackage,
    attachments: Sequence[EventAttachment],
    targets: Mapping[int, int],
    virtual_targets: Mapping[int, int],
    ids: MoonArenaIds,
) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 12104870);"
    lines: list[str] = []
    for attachment in attachments:
        target = targets[attachment.source_event]
        for binding in attachment.initializers:
            witness = _initializer(
                binding.slot, attachment.source_event, binding.arguments
            )
            if donor_zero.count(witness) != 1:
                raise ValueError(
                    f"{donor.key} Event(0) lacks unique attachment initializer"
                )
            args = tuple(
                str(_remap(arg, {donor.actor: PRIMARY, **virtual_targets}))
                for arg in binding.arguments
            )
            lines.append(_initializer(binding.slot, target, args))
    for binding in donor.virtual_entities:
        witness = f"    {binding.initializer}({binding.source_entity});"
        if donor_zero.count(witness) != 1:
            raise ValueError(f"{donor.key} Event(0) lacks unique virtual-owner witness")
        lines.append(
            f"    {binding.initializer}({virtual_targets[binding.source_entity]});"
        )
    lines.append(_initializer(0, ids.activation_event, ()))
    if donor.virtual_entities:
        lines.append(_initializer(0, ids.donor_owner_cleanup_event, ()))
    result = _replace_once(
        result, anchor, anchor + "\n" + "\n".join(lines), "constructor anchor"
    )
    header = result.splitlines()[0] + "\n"
    return _replace_once(
        result,
        header,
        header + f"    SetEventFlag({ids.activation_event}, OFF);\n",
        "constructor readiness reset",
    )


def _telemetry(block: str, owner: str) -> str:
    match = re.search(
        r"(?m)^    CreatePlaylog\([^\n]+\);\n    StartTimeMeasurement\([^\n]+\);", block
    )
    if match is None or len(re.findall(r"CreatePlaylog\(", block)) != 1:
        raise ValueError(f"{owner} health lacks unique telemetry")
    return match[0]


def _health(
    destination: str, source: str, donor: CombatPackage, ready_event: int
) -> str:
    result = _remap(
        source,
        {
            donor.actor: PRIMARY,
            donor.completion_event: 12101850,
            donor.start_flag: 12104850,
            donor.health_bar_event: 12104852,
        },
    )
    result = _replace_once(
        result,
        f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);",
        f"    SetCharacterHPBarDisplay({PRIMARY}, Disabled);\n"
        f"    SetCharacterInvincibility({PRIMARY}, Enabled);",
        "destination pre-entry invincibility",
    )
    authority = re.search(
        r"SetNetworkUpdateAuthority\(2100810, AuthorityLevel\.(?:Forced|Normal)\)",
        result,
    )
    if authority is None:
        raise ValueError(f"{donor.key} health lacks authority witness")
    # Entry notification belongs to the destination lifecycle.  Retain the
    # donor's source-witnessed authority level, but remove donor arena guards
    # such as Amelia's 12404223 notification flag.
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    start = result.rfind(client, 0, authority.start())
    line_start = result.rfind("\n", 0, start) + 1
    indent = result[line_start:start]
    close = result.find("\n" + indent + "}", authority.end())
    if start < 0 or close < 0:
        raise ValueError(f"{donor.key} health lacks client branch")
    replacement = (
        f"{indent}{client}\n"
        f"{indent}    IssueBossRoomEntryNotification(0);\n"
        f"{indent}    {authority[0]};\n"
        f"{indent}}}"
    )
    result = (
        result[:line_start] + replacement + result[close + len("\n" + indent + "}") :]
    )
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(
        r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
        lambda match: match[1] + f"        WaitFor(EventFlag({ready_event}));",
        result,
        count=1,
    )
    if count == 0:
        result = _replace_once(
            result,
            "    WaitFor(EventFlag(12104850));",
            f"    WaitFor(EventFlag({ready_event}));",
            "health readiness",
        )
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    # Event completion persists across a failed attempt. Event(0) resets the
    # readiness flag each load; this second wait also gates saved health.
    result = _replace_once(
        result,
        "L0:\n    SetEventFlag(12104850, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n"
        "    SetEventFlag(12104850, ON);",
        "saved-health readiness",
    )
    result = _replace_once(
        result,
        f"    SetCharacterAIState({PRIMARY}, Enabled);",
        f"    SetCharacterInvincibility({PRIMARY}, Disabled);\n"
        f"    SetCharacterAIState({PRIMARY}, Enabled);",
        "destination post-wake invincibility clear",
    )
    result = _replace_once(
        result,
        _telemetry(result, donor.key),
        _telemetry(destination, "Moon"),
        "telemetry",
    )
    result = re.sub(r"(?m)^    CreateReferredDamagePair\([^\n]+\);\n?", "", result)
    return result


def _witnesses(source: str, donor: CombatPackage, values: Sequence[str]) -> None:
    for value in values:
        if source.count(value) != 1:
            raise ValueError(
                f"{donor.key} activation lacks unique source witness {value}"
            )


def _activation(donor: CombatPackage, blocks: Mapping[int, str], event_id: int) -> str:
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 12104850
    prefix = (
        f"$Event({event_id}, Default, function() {{\n"
        "    EndIf(EventFlag(12101850));\n"
        "    EndIf(ThisEvent());\n"
    )
    suffix = "\n});"
    profile = donor.activation_profile
    if profile == "host-entry-animation":
        _witnesses(
            source,
            donor,
            (f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);",),
        )
        body = f"    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7001, false, false, false);"
    elif profile == "protected-radius-wake":
        _witnesses(
            source,
            donor,
            (
                f"ForceAnimationPlayback({donor.actor}, 7000, true, false, false);",
                "WaitFixedTimeFrames(70);",
            ),
        )
        body = f"    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7001, false, false, false);\n    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility({actor}, Disabled);"
    elif profile == "gravity-warp-wake":
        _witnesses(
            source,
            donor,
            (
                f"ForceAnimationPlayback({donor.actor}, 3028, false, false, false);",
                "WaitFixedTimeFrames(110);",
            ),
        )
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterMaphits({actor}, true);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 3028, false, false, false);\n    WaitFixedTimeFrames(110);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterMaphits({actor}, false);"
    elif profile == "object-gated-wake":
        _witnesses(
            source,
            donor,
            (
                f"ForceAnimationPlayback({donor.actor}, 7000, false, false, false);",
                f"ForceAnimationPlayback({donor.actor}, 7001, false, false, false);",
            ),
        )
        body = f"    ChangeCharacterEnableState({actor}, Disabled);\n    WaitFor(EventFlag({flag}));\n    ChangeCharacterEnableState({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7000, false, false, false);\n    ForceAnimationPlayback({actor}, 7001, false, false, false);"
    elif profile == "protected-area-wake":
        _witnesses(
            source,
            donor,
            (
                f"ForceAnimationPlayback({donor.actor}, 7003, true, false, false);",
                "WaitFixedTimeFrames(160);",
            ),
        )
        body = f"    SetCharacterMaphits({actor}, true);\n    SetCharacterGravity({actor}, Disabled);\n    SetCharacterInvincibility({actor}, Enabled);\n    ForceAnimationPlayback({actor}, 7003, true, false, false);\n    WaitFor(EventFlag({flag}));\n    ForceAnimationPlayback({actor}, 7006, false, false, false);\n    WaitFixedTimeFrames(30);\n    ForceAnimationPlayback({actor}, 7002, false, false, false);\n    WaitFixedTimeFrames(160);\n    SetCharacterGravity({actor}, Enabled);\n    SetCharacterInvincibility({actor}, Disabled);\n    SetCharacterMaphits({actor}, false);"
    elif profile == "first-damage-wake":
        _witnesses(
            source,
            donor,
            (
                f"SetCharacterImmortality({donor.actor}, Enabled);",
                f"HasDamageType({donor.actor}, 10000, DamageType.Unspecified)",
            ),
        )
        body = f"    ForceAnimationPlayback({actor}, 7001, true, false, false);\n    SetCharacterImmortality({actor}, Enabled);\n    SetSpEffect({actor}, 5647, false);\n    WaitFor(EventFlag({flag}));\n    SetCharacterInvincibility({actor}, Disabled);\n    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({actor}, 7000, false, true, false);\n    SetCharacterImmortality({actor}, Disabled);\n    ClearSpEffect({actor}, 5647);"
    else:
        raise ValueError(
            f"Moon arena lacks readiness adapter for {donor.key}/{profile}"
        )
    return prefix + body + suffix


def _signal_condition(
    donor: CombatPackage, blocks: Mapping[int, str], targets: Mapping[int, int]
) -> str:
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


def _music(
    block: str,
    donor: CombatPackage,
    donor_blocks: Mapping[int, str],
    targets: Mapping[int, int],
) -> str:
    condition = _signal_condition(donor, donor_blocks, targets)
    return _replace_once(
        block,
        "WaitFor(CharacterHasEventMessage(2100810, 500));",
        f"WaitFor({condition});",
        "destination music boundary",
    )


CAMERA_EVENTS = {"blood-starved-beast": 12304804}


def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {
        event_id: 12104854,
        donor.actor: PRIMARY,
        donor.completion_event: 12101850,
        donor.start_flag: 12104850,
    }
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 12104851
    result = _remap(source, mapping)
    result, count = re.subn(
        r"SetLockcamSlotNumber\(\d+, \d+,", "SetLockcamSlotNumber(21, 0,", result
    )
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = "    EndIf(EventFlag(12101850));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(
            result, header, header + guard, "destination camera completion guard"
        )
    return result


def _owner_cleanup(ids: MoonArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12101850));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""


def moon_arena_contract(donor: CombatPackage, ids: MoonArenaIds = DEFAULT_IDS) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-moon-arena-contract-v1",
        "status": "experimental",
        "arena": "moon-presence",
        "donor": donor.key,
        "allocation": asdict(ids),
        "preserved_destination_events": [
            12101850,
            12101852,
            12101853,
            12104855,
            12104880,
            12104881,
        ],
        "adapted_destination_events": [12104852, 12104853, 12104854],
        "retired_destination_controllers": [12104860, 12104870],
        "retained_sibling_actors": [2100800, 2100801],
        "destination_native_evidence": {
            "msb_sha256": DESTINATION_MSB_SHA256,
            "ffx_bank": "frpg_sfxbnd_m21.ffxbnd.dcx",
            "ffx_sha256": DESTINATION_FFX_SHA256,
        },
        "readiness_adapter": {
            "source_event": donor.activation_event,
            "profile": donor.activation_profile,
            "destination_event": ids.activation_event,
            "trigger": "EventFlag(12104850)",
            "reset_each_load": True,
        },
        "client_restore_event": 12101853,
        "entrance_policy": "preserve Gehrman completion/9900/arena predicates and object transitions; central policy replaces only the cinematic with the original 2102809 short warp",
        "music_policy": "donor-final-declared-boundary-drives-destination-final-track",
        "attachments": [
            {
                "source_event": item.source_event,
                "destination_event": ids.attachment_events[index],
            }
            for index, item in enumerate(attachments)
        ],
        "runtime_status": "unobserved",
    }


def patch_portable_donor_at_moon(
    destination: str,
    donor: CombatPackage,
    donor_source: str,
    ids: MoonArenaIds = DEFAULT_IDS,
) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, MOON_HASHES, "Moon arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    if hashlib.sha256(source[0].encode()).hexdigest() != SOURCE_ZERO_HASHES[donor.key]:
        raise ValueError(f"{donor.key} Event(0) differs from pinned constructor source")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Moon attachment capacity")
    targets = {
        item.source_event: ids.attachment_events[index]
        for index, item in enumerate(attachments)
    }
    virtual = {
        item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities
    }
    mapping = {
        donor.actor: PRIMARY,
        donor.completion_event: 12101850,
        donor.start_flag: 12104850,
        **targets,
        **virtual,
    }
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        12104852: _health(
            arena[12104852],
            source[donor.health_bar_event],
            donor,
            ids.activation_event,
        ),
        12104853: _music(arena[12104853], donor, source, targets),
        12104854: _camera(donor, source),
        12104860: _noop(arena[12104860]),
        12104870: _noop(arena[12104870]),
    }
    additions.append(_activation(donor, source, ids.activation_event))
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    expected = set(arena) | set(targets.values()) | {ids.activation_event}
    if donor.virtual_entities:
        expected.add(ids.donor_owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("Moon adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Moon adapter changed unrelated event {event_id}")
    for event_id in (12101850, 12101852, 12101853, 12104855):
        if output[event_id] != arena[event_id]:
            raise ValueError(
                f"Moon adapter changed protected destination event {event_id}"
            )
    return result


def _state(map_name: str) -> str:
    return map_name.rsplit("_", 1)[-1]


def _source_primary(slots: Sequence[Slot], donor: CombatPackage) -> Slot:
    candidates = [
        slot
        for slot in slots
        if slot.entity_id == donor.actor and slot.archetype == donor.archetype
    ]
    by_state = {_state(slot.map_name): slot for slot in candidates}
    binding = dict(donor.primary_state_bindings).get("00")
    if binding is None or binding not in by_state:
        raise ValueError(f"{donor.key} lacks explicit Moon source-state binding")
    return by_state[binding]


def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Moon donor source state lacks reviewed native evidence")
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": pin},
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
        ],
    }


def native_plan_portable_donor_at_moon(
    donor: CombatPackage,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: MoonArenaIds = DEFAULT_IDS,
) -> dict:
    _validate_ids(ids, "")
    targets = [slot for slot in slots if slot.map_name == DESTINATION_MAP]
    primaries = [
        slot
        for slot in targets
        if slot.entity_id == PRIMARY and slot.archetype == PRIMARY_ARCHETYPE
    ]
    siblings = [slot for slot in targets if slot.entity_id in (2100800, 2100801)]
    if (
        len(primaries) != 1
        or len(siblings) != 2
        or primaries[0].talk_id
        or {slot.entity_id for slot in siblings} != {2100800, 2100801}
    ):
        raise ValueError("Moon destination roster differs from reviewed native source")
    target, source_primary = primaries[0], _source_primary(slots, donor)
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        donor.archetype,
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [target], dict(npcs), dict(effects), boss_tiers=True
    )
    plan = {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"moon-presence<-{donor.key}"},
        "boss_contract": moon_arena_contract(donor, ids),
        "primary_init_source_bindings": [_binding(source_primary, target)],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
    plan["boss_contract"]["retained_destination_helpers"] = [
        {
            "map": slot.map_name,
            "part": slot.part_name,
            "entity_id": slot.entity_id,
            "archetype": asdict(slot.archetype),
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": DESTINATION_PINS[slot.entity_id],
            },
            "source_initialization": {
                "talk_id": 210306 if slot.entity_id == 2100800 else 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": "Gehrman sibling actor retained for Moon entry prerequisites and final progression",
        }
        for slot in siblings
    ]
    requirements = actor_addition_requirements(MOON_ARENA_CONTRACT, donor, list(slots))
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan


def portable_moon_donors(
    packages: Sequence[CombatPackage] = PACKAGES,
) -> tuple[CombatPackage, ...]:
    eligible = []
    for donor in packages:
        try:
            attachments = _portable_attachments(donor)
            if (
                donor.music_phase_signals
                and len(attachments) <= len(ATTACHMENT_EVENTS)
                and len(donor.virtual_entities) <= 1
            ):
                eligible.append(donor)
        except ValueError:
            continue
    return tuple(eligible)
