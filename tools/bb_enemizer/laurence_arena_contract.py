"""Source-pinned Laurence arena adapter for the six portable base combat packages.

The adapter changes only Laurence's 3400850 encounter family.  Ludwig's 3400800/
3400801 events remain outside its edit set because both bosses share m34.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
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
    primary_initialization_requirements,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ATTACHMENT_EVENTS = (12995200, 12995201, 12995202, 12995203, 12995204)
OWNER_CLEANUP_EVENT = 12995205
READINESS_EVENT = 12995206
BULLET_OWNER_ENTITY = 982700

EXPECTED = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13401851: "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
    13401853: "c34731a06e8cacbec558610668b60c0be8646079e70a52997047a729085db0f0",
    13404850: "8a9150872345a8ce6e8e2f8be8bef234c84d5294c8dbb6074d361b031019e9f4",
    13404851: "3697777dafa1624393090874701ba5f93e5a1937ba16f91f996013b69b272bb9",
    13404852: "a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",
    13404853: "6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",
    13404854: "67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",
    13404861: "7888497bc33ab25bdc668813a50cbc6a3ad44c2d6321b05fecdf4c500a297f7e",
    13404870: "237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",
    13404875: "e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",
}
LAURENCE_ARENA_CONTRACT = ArenaContract(
    key="laurence",
    event_file="m34_00_00_00.emevd.dcx.js",
    map_prefix="m34_00_",
    actor=3400850,
    archetype=Archetype("c4500", 450000, 450000, 0),
    destination_count=1,
    completion_event=13401850,
    start_flag=13404858,
    health_bar_event=13404852,
    health_bar_label=450000,
    activation_event=13401851,
    music_event=13404853,
    phase_music_message=400,
    lockcam_event=13404854,
    lockcam_map=34,
    lockcam_subarea=0,
    phase_slots=(),
    co_op_entry_event=13401853,
    part_routine_event=None,
    cloth_routine_event=None,
    part_slots=(),
    attachment_event_ids=ATTACHMENT_EVENTS,
    virtual_entity_ids=(BULLET_OWNER_ENTITY,),
    attachment_anchor_slot=None,
    attachment_anchor_event=None,
    expected=EXPECTED,
    music_phase_messages=(400,),
    retired_combat_events=(13404870, 13404875),
    activation_profile="split-cinematic",
)


@dataclass(frozen=True)
class LaurenceArenaIds:
    attachment_events: tuple[int, ...] = ATTACHMENT_EVENTS
    owner_cleanup_event: int = OWNER_CLEANUP_EVENT
    readiness_event: int = READINESS_EVENT
    bullet_owner_entity: int = BULLET_OWNER_ENTITY

    def values(self) -> tuple[int, ...]:
        return (
            *self.attachment_events,
            self.owner_cleanup_event,
            self.readiness_event,
            self.bullet_owner_entity,
        )


DEFAULT_IDS = LaurenceArenaIds()


def _numbers(text: str) -> set[int]:
    return {int(x) for x in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


def _blocks(text: str):
    return event_blocks(text)


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Laurence arena expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda m: str(mapping.get(int(m[0]), int(m[0]))),
        text,
    )


def _noop(block: str, *, parameterless: bool = False) -> str:
    header = block.splitlines()[0]
    if parameterless:
        header = re.sub(r"function\([^)]*\)", "function()", header, count=1)
    return header + "\n    EndEvent();\n});"


def _initializer(slot: int, event: int, args: tuple[str, ...] = ()) -> str:
    return "    $InitializeEvent(" + ", ".join((str(slot), str(event), *args)) + ");"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], owner: str) -> None:
    for eid, digest in expected.items():
        if hashlib.sha256(blocks.get(eid, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {owner} event {eid}")


def _attachments(donor: CombatPackage) -> tuple[EventAttachment, ...]:
    if donor.attachments:
        return donor.attachments
    if (
        donor.part_routine_event is not None
        and len(donor.phase_events) == 1
        and donor.part_bindings
    ):
        return (
            EventAttachment(donor.phase_events[0], (PartBinding(0, ()),)),
            EventAttachment(donor.part_routine_event, donor.part_bindings),
        )
    if donor.phase_events:
        return tuple(
            EventAttachment(x, (PartBinding(0, ()),)) for x in donor.phase_events
        )
    raise ValueError(f"{donor.key} lacks portable combat bodies")


@lru_cache(maxsize=1)
def _original_literals() -> frozenset[int]:
    values = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values |= _numbers(body.decode("utf-8-sig"))
    return frozenset(values)


def _event_flags(block: str) -> set[int]:
    """Return both read and written EMEVD event-flag operands."""
    return {
        int(value)
        for value in re.findall(r"\b(?:EventFlag|SetEventFlag)\((\d+)(?:\)|,)", block)
    }


def _readiness(donor: CombatPackage, source: str, ids: LaurenceArenaIds) -> str:
    a = 3400850
    start = 13404858
    prefix = f"$Event({ids.readiness_event}, Default, function() {{\n    EndIf(EventFlag(13401850));\n    EndIf(ThisEvent());\n"

    def need(*w):
        for x in w:
            if source.count(x) != 1:
                raise ValueError(f"{donor.key} readiness lacks witness {x}")

    p = donor.activation_profile
    if p == "host-entry-animation":
        need("ForceAnimationPlayback(2300800, 7001, false, false, false);")
        body = f"    WaitFor(EventFlag({start}));\n    ForceAnimationPlayback({a}, 7001, false, false, false);"
    elif p == "protected-radius-wake":
        need("SetCharacterInvincibility(2300810, Enabled);", "WaitFixedTimeFrames(70);")
        body = f"    SetCharacterInvincibility({a}, Enabled);\n    ForceAnimationPlayback({a}, 7000, true, false, false);\n    WaitFor(EventFlag({start}));\n    ForceAnimationPlayback({a}, 7001, false, false, false);\n    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility({a}, Disabled);"
    elif p == "gravity-warp-wake":
        need(
            "SetCharacterGravity(2410800, Disabled);",
            "ForceAnimationPlayback(2410800, 3028, false, false, false);",
        )
        body = f"    ChangeCharacterEnableState({a}, Disabled);\n    SetCharacterGravity({a}, Disabled);\n    SetCharacterMaphits({a}, true);\n    WaitFor(EventFlag({start}));\n    ChangeCharacterEnableState({a}, Enabled);\n    ForceAnimationPlayback({a}, 3028, false, false, false);\n    WaitFixedTimeFrames(110);\n    SetCharacterGravity({a}, Enabled);\n    SetCharacterMaphits({a}, false);"
    elif p == "object-gated-wake":
        need(
            "ForceAnimationPlayback(2400800, 7000, false, false, false);",
            "ForceAnimationPlayback(2400800, 7001, false, false, false);",
        )
        body = f"    ChangeCharacterEnableState({a}, Disabled);\n    WaitFor(EventFlag({start}));\n    ChangeCharacterEnableState({a}, Enabled);\n    ForceAnimationPlayback({a}, 7000, false, false, false);\n    ForceAnimationPlayback({a}, 7001, false, false, false);"
    elif p == "protected-area-wake":
        need(
            "ForceAnimationPlayback(3300800, 7003, true, false, false);",
            "WaitFixedTimeFrames(160);",
        )
        body = f"    SetCharacterMaphits({a}, true);\n    SetCharacterGravity({a}, Disabled);\n    SetCharacterInvincibility({a}, Enabled);\n    ForceAnimationPlayback({a}, 7003, true, false, false);\n    WaitFor(EventFlag({start}));\n    ForceAnimationPlayback({a}, 7006, false, false, false);\n    WaitFixedTimeFrames(30);\n    ForceAnimationPlayback({a}, 7002, false, false, false);\n    WaitFixedTimeFrames(160);\n    SetCharacterGravity({a}, Enabled);\n    SetCharacterInvincibility({a}, Disabled);\n    SetCharacterMaphits({a}, false);"
    elif p == "first-damage-wake":
        need(
            "SetCharacterImmortality(2420800, Enabled);",
            "HasDamageType(2420800, 10000, DamageType.Unspecified)",
        )
        body = f"    ForceAnimationPlayback({a}, 7001, true, false, false);\n    SetCharacterImmortality({a}, Enabled);\n    SetSpEffect({a}, 5647, false);\n    WaitFor(EventFlag({start}));\n    WaitFor(HasDamageType({a}, 10000, DamageType.Unspecified));\n    ForceAnimationPlayback({a}, 7000, false, true, false);\n    SetCharacterImmortality({a}, Disabled);\n    ClearSpEffect({a}, 5647);"
    else:
        raise ValueError(f"unsupported Laurence readiness profile {p}")
    return prefix + body + "\n});"


def _health(
    destination: str, donor_block: str, donor: CombatPackage, ids: LaurenceArenaIds
) -> str:
    actor = LAURENCE_ARENA_CONTRACT.actor
    result = _remap(
        donor_block,
        {
            donor.actor: actor,
            donor.completion_event: LAURENCE_ARENA_CONTRACT.completion_event,
            donor.start_flag: LAURENCE_ARENA_CONTRACT.start_flag,
            donor.health_bar_event: LAURENCE_ARENA_CONTRACT.health_bar_event,
        },
    )

    # Replace the donor's entry wait with the appended, source-pinned wake
    # event.  The Laurence entry flag still records destination fog/co-op
    # progress and must not become an arbitrary donor controller flag.
    result, replacements = re.subn(
        r"(    if \(!ThisEvent\(\)\) \{\n(?:.*?\n)*?)        WaitFor[^\n]*;",
        lambda match: match[1] + f"        WaitFor(EventFlag({ids.readiness_event}));",
        result,
        count=1,
    )
    if replacements == 0:
        result = _replace_once(
            result,
            f"    WaitFor(EventFlag({LAURENCE_ARENA_CONTRACT.start_flag}));",
            f"    WaitFor(EventFlag({ids.readiness_event}));",
            "Laurence unconditional donor-readiness gate",
        )
    elif replacements != 1:
        raise ValueError("Laurence donor health has ambiguous entry readiness waits")

    authority = re.search(
        rf"(?m)^(?P<indent>[ \t]*)(?P<line>SetNetworkUpdateAuthority\({actor}, "
        r"AuthorityLevel\.(?:Forced|Normal)\);)$",
        result,
    )
    if (
        authority is None
        or len(re.findall(r"SetNetworkUpdateAuthority\(", result)) != 1
    ):
        raise ValueError(
            f"{donor.key} health lacks one source network-authority witness"
        )
    client = "if (!HasMultiplayerState(MultiplayerState.Client)) {"
    client_start = result.rfind(client, 0, authority.start())
    if client_start < 0:
        raise ValueError(f"{donor.key} health lacks a client notification branch")
    line_start = result.rfind("\n", 0, client_start) + 1
    indent = result[line_start:client_start]
    close = result.find("\n" + indent + "}", authority.end())
    if close < 0:
        raise ValueError(
            f"{donor.key} health lacks a closed client notification branch"
        )
    notification = (
        f"{indent}if (!HasMultiplayerState(MultiplayerState.Client)) {{\n"
        f"{indent}    if (!EventFlag(13404860)) {{\n"
        f"{indent}        IssueBossRoomEntryNotification(0);\n"
        f"{indent}    }}\n"
        f"{indent}    {authority['line']}\n"
        f"{indent}}}"
    )
    result = (
        result[:line_start] + notification + result[close + len("\n" + indent + "}") :]
    )

    # Donor-local notification state is not portable.  Remove its writes and
    # prove none of its reads remain after replacing the source notification
    # branch above.  Laurence's flag 13404860 is the sole room-entry witness.
    foreign_flags = _event_flags(donor_block) - {
        donor.completion_event,
        donor.start_flag,
    }
    for flag in foreign_flags:
        result, removed = re.subn(
            rf"(?m)^    SetEventFlag\({flag}, (?:ON|OFF)\);\n?",
            "",
            result,
        )
        if removed > 1:
            raise ValueError(
                f"{donor.key} health has repeated foreign flag writes {flag}"
            )

    result = _replace_once(
        result,
        f"    SetEventFlag({LAURENCE_ARENA_CONTRACT.start_flag}, ON);",
        f"    SetEventFlag({LAURENCE_ARENA_CONTRACT.start_flag}, ON);\n"
        "    SetEventFlag(13404860, ON);",
        "Laurence room-entry notification state",
    )
    telemetry = re.search(
        r"(?m)^    CreatePlaylog\(\d+\);\n    StartTimeMeasurement\(\d+, \d+, Enabled\);$",
        result,
    )
    destination_telemetry = re.search(
        r"(?m)^    CreatePlaylog\(\d+\);\n    StartTimeMeasurement\(\d+, \d+, Enabled\);$",
        destination,
    )
    if telemetry is None or destination_telemetry is None:
        raise ValueError("Laurence health telemetry witness missing")
    result = (
        result[: telemetry.start()]
        + destination_telemetry[0]
        + result[telemetry.end() :]
    )
    result = _replace_once(
        result,
        f"    SetCharacterAIState({actor}, Enabled);",
        f"    SetCharacterInvincibility({actor}, Disabled);\n"
        f"    SetCharacterAIState({actor}, Enabled);",
        "Laurence post-readiness invincibility clear",
    )
    retained = foreign_flags.intersection(_event_flags(result))
    if retained:
        raise ValueError(
            f"{donor.key} health retained foreign local flags {sorted(retained)}"
        )
    return result


def _music(
    block: str,
    donor: CombatPackage,
    donor_blocks: Mapping[int, str],
    targets: Mapping[int, int],
) -> str:
    signal = donor.music_phase_signals[0]
    if signal.kind == "event_flag":
        condition = f"EventFlag({targets[signal.source_event]})"
    else:
        if (
            signal.message is None
            or f"CharacterHasEventMessage({donor.actor}, {signal.message})"
            not in donor_blocks[signal.source_event]
        ):
            raise ValueError("music witness missing")
        condition = f"CharacterHasEventMessage(3400850, {signal.message})"
    return _replace_once(
        block,
        "        chrFlagArea &= CharacterHasEventMessage(3400850, 400);",
        f"        chrFlagArea &= {condition};",
        "Laurence phase music",
    )


def patch_portable_donor_at_laurence(
    destination: str,
    donor: CombatPackage,
    donor_source: str,
    ids: LaurenceArenaIds = DEFAULT_IDS,
) -> str:
    original, source = _blocks(destination), _blocks(donor_source)
    _verify(original, EXPECTED, "Laurence arena")
    _verify(source, donor.expected, donor.key)
    allocated = set(ids.values())
    if (
        len(ids.attachment_events) != 5
        or len(allocated) != len(ids.values())
        or allocated & (_original_literals() | _numbers(destination))
    ):
        raise ValueError("Laurence allocation collision")
    attachments = _attachments(donor)
    if len(attachments) > 5:
        raise ValueError("Laurence attachment capacity")
    targets = {
        x.source_event: ids.attachment_events[i] for i, x in enumerate(attachments)
    }
    virtual = {x.source_entity: ids.bullet_owner_entity for x in donor.virtual_entities}
    # Retire only six Laurence model-part initializer calls; Ludwig's calls/events remain untouched.
    zero = original[0]
    for slot in range(5):
        zero = _replace_once(
            zero,
            _initializer(
                slot,
                13404870,
                (
                    str(3450 + slot),
                    str(3450 + slot),
                    f"NPCPartType.Part{slot+1}",
                    str(480 + slot),
                    str(490 + slot),
                    str((60, 150, 150, 250, 250)[slot]),
                    str((8020, 8000, 8010, 8030, 8040)[slot]),
                ),
            ),
            "",
            f"Laurence limb initializer {slot}",
        )
    zero = _replace_once(
        zero, _initializer(0, 13404875), "", "Laurence hitmask initializer"
    )
    calls = [_initializer(0, ids.readiness_event)]
    for x in attachments:
        for bind in x.initializers:
            witness = _initializer(bind.slot, x.source_event, bind.arguments)
            if source[0].count(witness) != 1:
                raise ValueError("donor initializer witness missing")
            calls.append(
                _initializer(bind.slot, targets[x.source_event], bind.arguments)
            )
    for bind in donor.virtual_entities:
        if source[0].count(f"    {bind.initializer}({bind.source_entity});") != 1:
            raise ValueError("owner witness missing")
        calls.append(f"    {bind.initializer}({virtual[bind.source_entity]});")
        calls.append(_initializer(0, ids.owner_cleanup_event))
    zero = _replace_once(
        zero, "\n});", "\n" + "\n".join(calls) + "\n});", "Laurence constructor close"
    )
    pre = original[13404861]
    for line in (
        "    SetCharacterMaphits(3400850, true);\n",
        "    SetCharacterGravity(3400850, Disabled);\n",
        "    SetCharacterInvincibility(3400850, Enabled);\n",
        "    ForceAnimationPlayback(3400850, 7002, true, false, false);\n",
    ):
        pre = _replace_once(pre, line, "", "Laurence-specific pre-entry state")
    host = _replace_once(
        original[13401851],
        "        SetCharacterGravity(3400850, Enabled);\n        SetCharacterInvincibility(3400850, Disabled);\n        SetCharacterMaphits(3400850, false);\n        ForceAnimationPlayback(3400850, 3029, false, false, false);\n",
        "",
        "Laurence-specific host wake",
    )
    client = _replace_once(
        original[13401853],
        "    SetCharacterGravity(3400850, Enabled);\n    SetCharacterInvincibility(3400850, Disabled);\n    SetCharacterMaphits(3400850, false);\n",
        "",
        "Laurence-specific client wake",
    )
    edits = {
        0: zero,
        13404861: pre,
        13401851: host,
        13401853: client,
        13404852: _health(
            original[13404852], source[donor.health_bar_event], donor, ids
        ),
        13404853: _music(original[13404853], donor, source, targets),
        13404870: _noop(original[13404870], parameterless=True),
        13404875: _noop(original[13404875]),
    }
    if donor.lockcam_event is not None:
        cam = _remap(
            source[donor.lockcam_event],
            {
                donor.lockcam_event: 13404854,
                donor.actor: 3400850,
                donor.completion_event: 13401850,
            },
        )
        cam = cam.replace(
            f"SetLockcamSlotNumber({donor.lockcam_map}, {donor.lockcam_subarea},",
            "SetLockcamSlotNumber(34, 0,",
        )
        edits[13404854] = cam
    additions = [
        _remap(
            source[x.source_event],
            {
                donor.actor: 3400850,
                donor.completion_event: 13401850,
                donor.start_flag: ids.readiness_event,
                x.source_event: targets[x.source_event],
                **targets,
                **virtual,
            },
        )
        for x in attachments
    ]
    additions.append(_readiness(donor, source[donor.activation_event], ids))
    if donor.virtual_entities:
        additions.append(
            f"$Event({ids.owner_cleanup_event}, Default, function() {{\n    WaitFor(EventFlag(13401850));\n    ChangeCharacterEnableState({ids.bullet_owner_entity}, Disabled);\n    SetCharacterAIState({ids.bullet_owner_entity}, Disabled);\n    SetCharacterHPBarDisplay({ids.bullet_owner_entity}, Disabled);\n    ForceCharacterDeath({ids.bullet_owner_entity}, false);\n}});"
        )
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    out = _blocks(result)
    expected = (
        set(original)
        | set(targets.values())
        | {ids.readiness_event}
        | ({ids.owner_cleanup_event} if donor.virtual_entities else set())
    )
    if set(out) != expected:
        raise ValueError("Laurence changed unexpected event identities")
    for eid, body in original.items():
        if eid not in edits and out[eid] != body:
            raise ValueError(f"Laurence changed unrelated event {eid}")
    if out[13401850] != original[13401850]:
        raise ValueError("Laurence terminal changed")
    return result


def laurence_arena_contract(
    donor: CombatPackage, ids: LaurenceArenaIds = DEFAULT_IDS
) -> dict:
    a = _attachments(donor)
    return {
        "format": "bb-laurence-arena-contract-v1",
        "status": "experimental",
        "arena": "laurence",
        "donor": donor.key,
        "allocation": asdict(ids),
        "preserved_ludwig_events": [
            13401800,
            13404803,
            13404820,
            13404821,
            13404822,
            13404823,
            13404824,
            13404825,
            13404830,
            13404840,
        ],
        "terminal_event": 13401850,
        "readiness_event": ids.readiness_event,
        "attachments": [
            {
                "source_event": x.source_event,
                "destination_event": ids.attachment_events[i],
            }
            for i, x in enumerate(a)
        ],
        "runtime_status": "unobserved",
    }


def portable_laurence_donors(
    packages: Sequence[CombatPackage] = PACKAGES,
) -> tuple[CombatPackage, ...]:
    return tuple(
        p for p in packages if len(_attachments(p)) <= 5 and p.music_phase_signals
    )


def native_plan_portable_donor_at_laurence(
    donor: CombatPackage,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LaurenceArenaIds = DEFAULT_IDS,
) -> dict:
    target = [
        s for s in slots if s.entity_id == 3400850 and s.map_name == "m34_00_00_00"
    ]
    if len(target) != 1 or target[0].archetype != LAURENCE_ARENA_CONTRACT.archetype:
        raise ValueError("Laurence target provenance drift")
    swap = Swap(
        target[0].logical_key,
        [target[0].key],
        {target[0].key: target[0].archetype},
        target[0].archetype,
        donor.archetype,
    )
    changes, skips = plan_scaling(
        [swap], target, dict(npcs), dict(effects), boss_tiers=True
    )
    p = {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": laurence_arena_contract(donor, ids),
        "primary_init_source_bindings": primary_initialization_requirements(
            LAURENCE_ARENA_CONTRACT, donor, list(slots)
        ),
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
    r = actor_addition_requirements(LAURENCE_ARENA_CONTRACT, donor, list(slots))
    if r:
        p["boss_actor_addition_requirements"] = r
    return p
