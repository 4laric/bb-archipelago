"""Reusable source-pinned Ludwig destination arena."""

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
    PACKAGES,
    ArenaContract,
    Archetype,
    CombatPackage,
    EventAttachment,
    MusicPhaseSignal,
    actor_addition_requirements,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m34_00_00_00.emevd.dcx.js"
MAP_PREFIX = "m34_00_"
DESTINATION_MAP = "m34_00_00_00"
PRIMARY, PHASE = 3400800, 3400801
PRIMARY_ARCHETYPE = Archetype("c4510", 451000, 451000, 0)
PHASE_ARCHETYPE = Archetype("c4510", 451001, 451000, 0)

# Proven absent from the complete bundled original EMEVD/MSB corpus.  The
# composition builder independently scans the selected project allocations.
ATTACHMENT_EVENTS = (12995900, 12995901, 12995902, 12995903, 12995904)
ACTIVATION_EVENT = 12995905
CLIENT_RESTORE_EVENT = 12995906
HELPER_LIFECYCLE_EVENT = 12995907
DONOR_OWNER_CLEANUP_EVENT = 12995908
BULLET_OWNER_ENTITY = 983400
DESTINATION_PINS = {
    PRIMARY: "79c5c55b1660c9ca6d517e25fe5ab685bb7b6ec8e53bad5406b3433bf9c798a8",
    PHASE: "6ff68750b7bed265be44daed1a4d6522a1d4fb0563519693d2cde4035d04c296",
}
DESTINATION_MSB_SHA256 = (
    "54bc13bcd1d961825aa5abcb3170c86edee5ea68d67666427e9e02fbd977947b"
)
DESTINATION_FFX_SHA256 = (
    "c02322d8ad0e50b18e5f678f3bbfe735971e24aa4c5484f3849ace93f1dfd3b3"
)
DESTINATION_REGION_PINS = {
    3402800: "5414612f942d1cd55a33d351da60cf10732dd84600cb768f8f2b6124697dae49",
    3402801: "47e8d8445e40db5beaa80af31e6b83f8f6e818599d69aa701bbc8aa7dd389a9e",
    3402802: "c25f2b6564fa3b04ba41b29917bef3a59fcffd26bc95ffd7be8b3c65c2a0d5f0",
    3402805: "54326209e3bca79f0d904cf7558babb038398450b7f9ca7b7a55a6b6da880f7f",
    3402806: "3494f9096d34024219f1de3aea8dca447471778d61774e2e5c70d5032e5b9685",
    3402807: "2c828536156967ddf77af5a686bac7d080a1d4093f4e873af66cdf420fae8f08",
    3402900: "a1fe26f6a13aa45c90fa9b17514f43fc7287ba95950373527a7fa51558cc78e0",
}
DESTINATION_OBJECT_SFX_PINS = {
    3401800: "989aaf448fb9dba03849a6905a772b14da1ce8c62c871d766bd31dc022f07cb7",
    3403800: "8336c84adc9d9c98160f5c51a5a716d69e1d4719ef88ac96c9aad261db87cef4",
}
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

LUDWIG_HASHES: dict[int, str | tuple[str, ...]] = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401801: "512227ef549cf14ead83ae803efb7f73294b7f406abea9c940b8b49a6d5f26bd",
    13401802: "c8f0800e9c10ec30f2d5ed05cd1de7dbdf8d7e93ad2ce180ce22894294e7851b",
    13401803: "318fef613a2babaad1ec9736e5b762c9792a4c5a38ddf62d5297131e9cda25cd",
    13401804: "a1e94cd16c9b9e0a9818732e80da388a1a37b77a0d55b04f1631ba9eea0c21ff",
    13404800: "5c328a50c75d77d81f9bbf40deb6becf2d5831b9907b046a976c043717317ec9",
    13404801: "0c8133b86826f9c6e9c2cd90909dc42c9f178247811ec2e14de057e4d7325dd4",
    13404802: (
        "09b991a95b087e141b27c3e69f2d55e330bf6a8764df7eb475ebdfd9df9e5ac7",
        "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab",
    ),
    13404803: "ee69949f3bf2119d6cb051e41abfed11c5de83b306f9a9e36a6b42df182745ba",
    13404804: "8bb1209c5f08d944570b67e634223c7375b3596fe56f2c44a5712b2d04359d78",
    13404805: "aa9beccd4ded3b92fc74ea6a159782cc403508d278acd34eecb897d333053382",
    13404806: "bc38bb3b5c62d1686d4694733520dd6b345f3745d92b2a9d6339fd33bcf6c864",
    13404807: "0a2ec84d268618cf1778176c8670c6022412342dc189eaf0d7367f19b2fa05c4",
    13404811: "1555a139cea23edd1c6d8e8c71f6e828f9c1167b24271c4ea819919b99f2893f",
    13404820: "2a1075a99453bacb20f94e697137fe830eb2507ffcf74699ad7707ad62671c14",
    13404821: "a650abcf1dca7030d8d39eb944ef5e3c1ba0a9665dfb4fc8f9fbf3c82280e8bf",
    13404822: "ae620a8fe09a2614d36cc0714743fac5f2e9f7bd7fb888c78fdb738910250968",
    13404823: "3fd2cc74e5e8cf9ed1da11cea82f3244c1228bc4224b1a280431a4a64b519292",
    13404824: "19b82e96f8a880da845bf09c977b9d116da91584069edb0a3f630271ae119c70",
    13404825: "b64ae6b68f0a7dc4d922328fa23659be54219fd7010465f03493a141858e16f2",
    13404830: "e29423935a2cea0e2078da6f93030c835ac884337cfd9a832c055c13b778414f",
    13404835: "e9cafe3d4edfa21eb0c325a480ac17457d6b98d7d485cf2b542998320b07ba32",
    13404840: "3ab3d74eb2c16456051f503cb1e082f4ed769bbbf94e7570ddd4f99393bbe56b",
    13404841: "404a71c4d413e4aef35b1b9eaf683feb881acf4250724e4e5a265123d9a8a14d",
}

LUDWIG_ARENA_CONTRACT = ArenaContract(
    key="ludwig",
    event_file=EVENT_FILE,
    map_prefix=MAP_PREFIX,
    actor=PRIMARY,
    archetype=PRIMARY_ARCHETYPE,
    destination_count=1,
    completion_event=13401800,
    start_flag=13404808,
    health_bar_event=13404802,
    health_bar_label=451000,
    activation_event=13401801,
    music_event=13404803,
    phase_music_message=None,
    lockcam_event=13404804,
    lockcam_map=34,
    lockcam_subarea=0,
    phase_slots=(),
    co_op_entry_event=13401804,
    part_routine_event=None,
    cloth_routine_event=None,
    part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,),
    attachment_anchor_slot=0,
    attachment_anchor_event=13404841,
    expected=LUDWIG_HASHES,
    activation_idle_animation=None,
    music_phase_messages=(),
    retired_combat_events=(
        13404820,
        13404821,
        13404822,
        13404823,
        13404824,
        13404825,
        13404830,
        13404835,
        13404840,
        13404841,
    ),
    activation_profile="normalized-cinematic",
)


@dataclass(frozen=True)
class LudwigArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    donor_owner_cleanup_event: int = DONOR_OWNER_CLEANUP_EVENT
    activation_event: int = ACTIVATION_EVENT
    client_restore_event: int = CLIENT_RESTORE_EVENT
    helper_lifecycle_event: int = HELPER_LIFECYCLE_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (
            *self.attachment_events,
            self.donor_owner_cleanup_event,
            self.activation_event,
            self.client_restore_event,
            self.helper_lifecycle_event,
            self.bullet_owner_entity,
        )


DEFAULT_IDS = LudwigArenaIds()


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


def _validate_ids(ids: LudwigArenaIds, destination: str) -> None:
    values = ids.values()
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("Ludwig arena IDs must be unique positive project IDs")
    event_ids = {
        *ids.attachment_events,
        ids.activation_event,
        ids.client_restore_event,
        ids.helper_lifecycle_event,
        ids.donor_owner_cleanup_event,
    }
    if event_ids != set(range(12995900, 12995909)) or ids.bullet_owner_entity != 983400:
        raise ValueError("Ludwig arena requires the exact reviewed narrow allocation")
    collisions = set(values) & (_original_literals() | _numbers(destination))
    if collisions:
        raise ValueError(
            f"Ludwig arena IDs collide with original inputs: {sorted(collisions)}"
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
        raise ValueError(f"Ludwig arena expected one {label}")
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
    ids: LudwigArenaIds,
) -> str:
    result = arena_zero
    anchor = "    $InitializeEvent(0, 13404841);"
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
    lines.extend(
        (
            _initializer(0, ids.activation_event, ()),
            _initializer(0, ids.client_restore_event, ()),
            _initializer(0, ids.helper_lifecycle_event, ()),
        )
    )
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
            donor.completion_event: 13401800,
            donor.start_flag: 13404808,
            donor.health_bar_event: 13404802,
        },
    )
    authority = re.search(
        r"(?m)^\s*SetNetworkUpdateAuthority\(3400800, AuthorityLevel\.(?:Forced|Normal)\);$",
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
        f"{indent}{client}\n{indent}    if (!EventFlag(13404810)) {{\n"
        f"{indent}        IssueBossRoomEntryNotification(0);\n{indent}    }}\n"
        f"{indent}    {authority[0].strip()}\n{indent}}}"
    )
    result = (
        result[:line_start] + replacement + result[close + len("\n" + indent + "}") :]
    )
    # Bind the donor's first setup wait to the completed source wake.
    result, count = re.subn(
        r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor\([^\n]*\);",
        lambda m: m[1] + f"        WaitFor(EventFlag({ready_event}));",
        result,
        count=1,
    )
    if count == 0:
        result = _replace_once(
            result,
            "    WaitFor(EventFlag(13404808));",
            f"    WaitFor(EventFlag({ready_event}));",
            "health readiness",
        )
    foreign = set(re.findall(r"SetEventFlag\((\d+),", source)) - {str(donor.start_flag)}
    for flag in foreign:
        result = re.sub(rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?", "", result)
    result = _replace_once(
        result,
        "    SetEventFlag(13404808, ON);",
        "    SetEventFlag(13404808, ON);\n" "    SetEventFlag(13404810, ON);",
        "room notification ownership",
    )
    # Event completion persists across a failed attempt. Event(0) resets the
    # readiness flag each load; this second wait also gates saved health.
    result = _replace_once(
        result,
        "L0:\n    SetEventFlag(13404808, ON);",
        f"L0:\n    WaitFor(EventFlag({ready_event}));\n"
        "    SetEventFlag(13404808, ON);",
        "saved-health readiness",
    )
    result = _replace_once(
        result,
        _telemetry(result, donor.key),
        _telemetry(destination, "Ludwig"),
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
    source, actor, flag = blocks[donor.activation_event], PRIMARY, 13404808
    prefix = f"$Event({event_id}, Default, function() {{\n    EndIf(EventFlag(13401800));\n    EndIf(ThisEvent());\n"
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
        body = f"    ForceAnimationPlayback({actor}, 7001, true, false, false);\n    SetCharacterImmortality({actor}, Enabled);\n    SetSpEffect({actor}, 5647, false);\n    WaitFor(EventFlag({flag}));\n    WaitFor(HasDamageType({actor}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({actor}, 7000, false, true, false);\n    SetCharacterImmortality({actor}, Disabled);\n    ClearSpEffect({actor}, 5647);"
    else:
        raise ValueError(
            f"Ludwig arena lacks readiness adapter for {donor.key}/{profile}"
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
        "flagArea2 &= EventFlag(13404824);",
        f"flagArea2 &= {condition};",
        "destination music boundary",
    )


CAMERA_EVENTS = {"blood-starved-beast": 12304804}


def _camera(donor: CombatPackage, blocks: Mapping[int, str]) -> str:
    event_id = donor.lockcam_event or CAMERA_EVENTS.get(donor.key)
    if event_id is None or event_id not in blocks:
        raise ValueError(f"{donor.key} lacks pinned camera event")
    source = blocks[event_id]
    mapping = {
        event_id: 13404804,
        donor.actor: PRIMARY,
        donor.completion_event: 13401800,
        donor.start_flag: 13404808,
    }
    if donor.key == "blood-starved-beast":
        if "EventFlag(12304801)" not in source:
            raise ValueError("BSB camera lacks pinned guest-entry witness")
        mapping[12304801] = 13404809
    result = _remap(source, mapping)
    result, count = re.subn(
        r"SetLockcamSlotNumber\(\d+, \d+,", "SetLockcamSlotNumber(34, 0,", result
    )
    if count == 0:
        raise ValueError(f"{donor.key} camera lacks lockcam witness")
    guard = "    EndIf(EventFlag(13401800));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(
            result, header, header + guard, "destination camera completion guard"
        )
    return result


def _helper_lifecycle(ids: LudwigArenaIds) -> str:
    return f"""$Event({ids.helper_lifecycle_event}, Restart, function() {{
    SetCharacterAIState(3400801, Disabled);
    SetCharacterHPBarDisplay(3400801, Disabled);
    SetCharacterInvincibility(3400801, Enabled);
    ChangeCharacterEnableState(3400801, Disabled);
    GotoIf(L0, EventFlag(13401800));
    WaitFor(EventFlag(13401800));
L0:
    SetCharacterInvincibility(3400801, Disabled);
    ChangeCharacterEnableState(3400801, Disabled);
    ForceCharacterDeath(3400801, false);
}});"""


def _owner_cleanup(ids: LudwigArenaIds) -> str:
    return f"""$Event({ids.donor_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag(13401800));
    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);
    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);
    ForceCharacterDeath({ids.bullet_owner_entity}, false);
}});"""


CLIENT_EVENTS = {
    "blood-starved-beast": (
        12301803,
        "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
    ),
    "darkbeast-paarl": (
        12301703,
        "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
    ),
    "cleric-beast": (
        12411703,
        "f4982068db5c19d893ac320045e14491832a5722d1fd89a8038ef4cb8b372ce9",
    ),
    "vicar-amelia": (
        12401804,
        "85aa59f873b275cb390675f4f2ef13e4f7b3f00935274a2ce43c23b75070da59",
    ),
    "amygdala": (
        13301803,
        "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9",
    ),
    "ebrietas": (
        12421803,
        "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    ),
}


def _client_restore(
    donor: CombatPackage, blocks: Mapping[int, str], event_id: int
) -> str:
    source_id, digest = CLIENT_EVENTS[donor.key]
    source = blocks.get(source_id)
    if source is None or hashlib.sha256(source.encode()).hexdigest() != digest:
        raise ValueError(f"{donor.key} client restore differs from pinned source")
    return _remap(
        source,
        {
            source_id: event_id,
            donor.actor: PRIMARY,
            donor.start_flag: 13404808,
            donor.activation_event: 13401801,
        },
    )


def ludwig_arena_contract(
    donor: CombatPackage, ids: LudwigArenaIds = DEFAULT_IDS
) -> dict:
    attachments = _portable_attachments(donor)
    return {
        "format": "bb-ludwig-arena-contract-v1",
        "status": "experimental",
        "arena": "ludwig",
        "donor": donor.key,
        "allocation": asdict(ids),
        "preserved_destination_events": [
            13400941,
            13400942,
            13400943,
            13400944,
            13401800,
            13401801,
            13401802,
            13401803,
            13401804,
            13404800,
            13404801,
            13404805,
            13404806,
            13404807,
            13404811,
            13401850,
            13401851,
            13401853,
            13404850,
            13404851,
            13404852,
            13404853,
            13404854,
            13404855,
            13404856,
            13404857,
            13404861,
            13404870,
            13404875,
        ],
        "adapted_destination_events": [13404802, 13404803, 13404804],
        "retired_destination_controllers": list(
            LUDWIG_ARENA_CONTRACT.retired_combat_events
        ),
        "retained_destination_helpers": [PHASE],
        "destination_native_evidence": {
            "msb_sha256": DESTINATION_MSB_SHA256,
            "ffx_bank": "frpg_sfxbnd_m34.ffxbnd.dcx",
            "ffx_sha256": DESTINATION_FFX_SHA256,
            "region_pins": dict(DESTINATION_REGION_PINS),
            "object_sfx_pins": dict(DESTINATION_OBJECT_SFX_PINS),
        },
        "readiness_adapter": {
            "source_event": donor.activation_event,
            "profile": donor.activation_profile,
            "destination_event": ids.activation_event,
            "trigger": "EventFlag(13404808)",
            "reset_each_load": True,
        },
        "client_restore_event": ids.client_restore_event,
        "helper_lifecycle_event": ids.helper_lifecycle_event,
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


def patch_portable_donor_at_ludwig(
    destination: str,
    donor: CombatPackage,
    donor_source: str,
    ids: LudwigArenaIds = DEFAULT_IDS,
) -> str:
    arena, source = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, LUDWIG_HASHES, "Ludwig arena")
    _verify(source, donor.expected, f"{donor.key} donor")
    if hashlib.sha256(source[0].encode()).hexdigest() != SOURCE_ZERO_HASHES[donor.key]:
        raise ValueError(f"{donor.key} Event(0) differs from pinned constructor source")
    _validate_ids(ids, destination)
    attachments = _portable_attachments(donor)
    if len(attachments) > len(ids.attachment_events):
        raise ValueError(f"{donor.key} exceeds Ludwig attachment capacity")
    targets = {
        item.source_event: ids.attachment_events[index]
        for index, item in enumerate(attachments)
    }
    virtual = {
        item.source_entity: ids.bullet_owner_entity for item in donor.virtual_entities
    }
    mapping = {
        donor.actor: PRIMARY,
        donor.completion_event: 13401800,
        donor.start_flag: 13404808,
        **targets,
        **virtual,
    }
    additions = [_remap(source[item.source_event], mapping) for item in attachments]
    edits = {
        0: _constructor(arena[0], source[0], donor, attachments, targets, virtual, ids),
        13404802: _health(
            arena[13404802], source[donor.health_bar_event], donor, ids.activation_event
        ),
        13404803: _music(arena[13404803], donor, source, targets),
        13404804: _camera(donor, source),
        **{
            event_id: _noop(arena[event_id])
            for event_id in LUDWIG_ARENA_CONTRACT.retired_combat_events
        },
    }
    additions.extend(
        (
            _activation(donor, source, ids.activation_event),
            _client_restore(donor, source, ids.client_restore_event),
            _helper_lifecycle(ids),
        )
    )
    if donor.virtual_entities:
        additions.append(_owner_cleanup(ids))
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    expected = (
        set(arena)
        | set(targets.values())
        | {ids.activation_event, ids.client_restore_event, ids.helper_lifecycle_event}
    )
    if donor.virtual_entities:
        expected.add(ids.donor_owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("Ludwig adapter changed unexpected event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Ludwig adapter changed unrelated event {event_id}")
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
        raise ValueError(f"{donor.key} lacks explicit Ludwig source-state binding")
    return by_state[binding]


def _binding(source: Slot, target: Slot) -> dict:
    pin = SOURCE_PART_PINS.get((source.map_name, source.entity_id))
    if pin is None or source.talk_id != 0:
        raise ValueError("Ludwig donor source state lacks reviewed native evidence")
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


def native_plan_portable_donor_at_ludwig(
    donor: CombatPackage,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LudwigArenaIds = DEFAULT_IDS,
) -> dict:
    _validate_ids(ids, "")
    targets = [slot for slot in slots if slot.map_name == DESTINATION_MAP]
    primaries = [
        slot
        for slot in targets
        if slot.entity_id == PRIMARY and slot.archetype == PRIMARY_ARCHETYPE
    ]
    helpers = [slot for slot in targets if slot.entity_id == PHASE]
    if (
        len(primaries) != 1
        or len(helpers) != 1
        or primaries[0].talk_id
        or helpers[0].archetype != PHASE_ARCHETYPE
    ):
        raise ValueError(
            "Ludwig destination roster differs from reviewed native source"
        )
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
        "options": {"experimental_boss_contract": f"ludwig<-{donor.key}"},
        "boss_contract": ludwig_arena_contract(donor, ids),
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
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": "hidden inert destination helper until exact event 13401800 completes",
        }
        for slot in helpers
    ]
    requirements = actor_addition_requirements(
        LUDWIG_ARENA_CONTRACT, donor, list(slots)
    )
    if requirements:
        plan["boss_actor_addition_requirements"] = requirements
    return plan


def portable_ludwig_donors(
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
