"""Pinned Ludwig combat adapter for Orphan's two-body destination terminal.

The event patch and native plan are static construction evidence.  They have
not been exercised in a running game.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .bsb_orphan_contract import ARENA as ORPHAN_ARENA_HASHES
from .bsb_orphan_contract import ARENA_ALTERNATES as ORPHAN_ARENA_ALTERNATES
from .ludwig_contract import EVENTS as LUDWIG_EVENTS
from .ludwig_contract import P1, P2, SOURCE_HASHES as LUDWIG_SOURCE_HASHES
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling


BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
LUDWIG_SOURCE = "event/m34_00_00_00.emevd.dcx.js"
ORPHAN_SOURCE = "event/m36_00_00_00.emevd.dcx.js"

LUDWIG_ONE = 3400800
LUDWIG_TWO = 3400801
ORPHAN_CORE = 3600800
ORPHAN_PHASE = 3600801
ORPHAN_SHADOW = 3600802
ORPHAN_SUPPORT = 3600803
ORPHAN_CORE_ARCHETYPE = Archetype("c4540", 454000, 454000, 0)
ORPHAN_PHASE_ARCHETYPE = Archetype("c4541", 454100, 454100, 0)

MIN_ID = 12991400
MAX_ID = 12991499

# Exact DarkScript 3.6.3 output for the installed source has a witnessed
# AlwaysUpdate change on the hidden phase actor.  It is a source variant, not
# a new behavior invented by this adapter.
LUDWIG_SOURCE_ALTERNATES = {
    13404802: "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab"
}


@dataclass(frozen=True)
class LudwigOrphanIds:
    """Project-owned event identities; no actor entity is allocated."""

    event_ids: Mapping[int, int]
    cleanup_event: int

    def values(self) -> tuple[int, ...]:
        return (*self.event_ids.values(), self.cleanup_event)


DEFAULT_IDS = LudwigOrphanIds(
    {event: 12991420 + index for index, event in enumerate(LUDWIG_EVENTS)},
    12991430,
)


def _verify(
    blocks: Mapping[int, str],
    pins: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> None:
    for event, digest in pins.items():
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        alternate = (alternates or {}).get(event)
        allowed = (digest,) if alternate is None else (digest, alternate)
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Ludwig/Orphan expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _end(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            item.strip()
            if item.strip().startswith("unused_")
            else "unused_" + item.strip()
            for item in match[1].split(",")
            if item.strip()
        )
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


def _all_literals() -> set[int]:
    output = set()
    for body in read_prefix(BUNDLE, "event/").values():
        output.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return output


def _validate_ids(ids: LudwigOrphanIds, destination: str) -> None:
    if set(ids.event_ids) != set(LUDWIG_EVENTS):
        raise ValueError("Ludwig/Orphan requires every declared combat event")
    values = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(values)) != len(values)
        or any(value < MIN_ID or value > MAX_ID for value in values)
        or set(values).intersection(local | _all_literals())
    ):
        raise ValueError("Ludwig/Orphan ID collides with an original EMEVD literal")


def _normal_constructor(zero: str) -> str:
    start = "    if (!EventFlag(13400999)) {\n        $InitializeEvent(0, 13404824);"
    if start not in zero:
        raise ValueError("Ludwig Event(0) normal phase initializer witness drift")
    return zero.split(start, 1)[1].split("    } else {", 1)[0]


def _calls(zero: str, event: int, count: int) -> list[str]:
    calls = [
        line
        for line in zero.splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)
    ]
    if len(calls) != count:
        raise ValueError(
            f"Ludwig Event(0) lacks {count} initializer witnesses for {event}"
        )
    return calls


def _normal_phase_graph(
    donor: Mapping[int, str], ids: LudwigOrphanIds, mapping: Mapping[int, int]
) -> tuple[list[str], list[str]]:
    normal = _normal_constructor(donor[0])
    initializers: list[str] = []
    events: list[str] = []
    for event in LUDWIG_EVENTS:
        constructor = normal if event in (13404830, 13404835, 13404841) else donor[0]
        count = 3 if event == 13404830 else 1
        initializers.extend(
            "    " + _remap(line.strip(), mapping)
            for line in _calls(constructor, event, count)
        )
        body = donor[event]
        if event in (13404820, 13404821, 13404822, 13404823):
            body, changes = re.subn(
                r"\(\(EventFlag\(13400999\) && HPRatio\(3400800\) < [0-9.]+\)\s*"
                r"\|\| \(!EventFlag\(13400999\) && HPRatio\(3400800\) < ([0-9.]+)\)\)",
                r"(HPRatio(3400800) < \1)",
                body,
            )
            if changes != 1:
                raise ValueError("Ludwig normal phase threshold witness drift")
        elif event == 13404824:
            body = _replace_once(
                body, "    SetEventFlag(9180, ON);\n", "", "source cutscene flag"
            )
        elif event == 13404825:
            first = body.index("    if (!HasMultiplayerState(MultiplayerState.Multiplayer)) {")
            last = body.index(
                "    DisplayBossHealthBar(Disabled, 3400800, 0, 451000);", first
            )
            body = body[:first] + body[last:]
            body = _replace_once(
                body, "    SetEventFlag(9180, OFF);\n", "", "source cutscene flag"
            )
            body = _replace_once(
                body,
                "    ChangeCharacterEnableState(3400800, Disabled);\n"
                "    SetNetworkUpdateRate(3400801,",
                "    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Character, "
                "3400800, -1, 3400800);\n"
                "    ChangeCharacterEnableState(3400801, Enabled);\n"
                "    ChangeCharacterEnableState(3400800, Disabled);\n"
                "    SetNetworkUpdateRate(3400801,",
                "destination phase placement",
            )
            for instruction in (
                "    CharacterWarpRequest(3400800, TargetEntityType.Area, 3402900, -1);\n",
                "    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Area, "
                "3402806, -1, 3400800);\n",
            ):
                body = _replace_once(body, instruction, "", "source arena warp")
        events.append(_remap(body, mapping))
    return initializers, events


def _health(donor: str, mapping: Mapping[int, int]) -> str:
    result = _replace_once(
        donor,
        "    if (EventFlag(13400999)) {\n"
        "        SetSpEffect(3400800, 8040, false);\n"
        "        SetSpEffect(3400801, 8040, false);\n"
        "    }\n",
        "",
        "source-only normal branch condition",
    )
    result = _replace_once(
        result,
        "    SetCharacterAIState(3400801, Disabled);\n",
        "    SetCharacterAIState(3400801, Disabled);\n"
        "    ChangeCharacterEnableState(3400801, Disabled);\n"
        "    SetCharacterAIState(3600803, Disabled);\n"
        "    SetCharacterHPBarDisplay(3600803, Disabled);\n"
        "    ChangeCharacterEnableState(3600803, Disabled);\n",
        "destination phase/support initial state",
    )
    result = _replace_once(
        result,
        "L4:\n    if (!EventFlag(13404825)) {",
        "L4:\n    if (EventFlag(13404825)) {\n"
        "        ChangeCharacterEnableState(3400801, Enabled);\n"
        "    }\n"
        "    if (!EventFlag(13404825)) {",
        "saved phase actor visibility",
    )
    return _remap(result, mapping)


def _camera(donor: str, mapping: Mapping[int, int]) -> str:
    result = _remap(donor, mapping)
    # These are typed source-camera operands.  The phase actor lives in m36,
    # so neither active nor clear operations may retain Ludwig's m34 binding.
    for old, new, label in (
        (
            "SetLockcamSlotNumber(34, 0, 1)",
            "SetLockcamSlotNumber(36, 0, 1)",
            "destination camera active binding",
        ),
        (
            "SetLockcamSlotNumber(34, 0, 0)",
            "SetLockcamSlotNumber(36, 0, 0)",
            "destination camera clear binding",
        ),
    ):
        result = _replace_once(result, old, new, label)
    if "SetLockcamSlotNumber(34," in result:
        raise ValueError("Ludwig/Orphan retained a source camera map binding")
    return result


def _cleanup(ids: LudwigOrphanIds) -> str:
    return f"""$Event({ids.cleanup_event}, Default, function() {{
    WaitFor(EventFlag(13601800));
    ChangeCharacterEnableState(3600800, Disabled);
    ForceCharacterDeath(3600800, false);
    ChangeCharacterEnableState(3600801, Disabled);
    ForceCharacterDeath(3600801, false);
    ChangeCharacterEnableState(3600803, Disabled);
    ForceCharacterDeath(3600803, false);
}});"""


def patch_ludwig_at_orphan(
    destination: str, donor_source: str, ids: LudwigOrphanIds = DEFAULT_IDS
) -> str:
    """Install normal Ludwig combat while preserving Orphan completion/AP events."""
    arena = event_blocks(destination)
    donor = event_blocks(donor_source)
    _verify(arena, ORPHAN_ARENA_HASHES, "Orphan arena", ORPHAN_ARENA_ALTERNATES)
    _verify(donor, LUDWIG_SOURCE_HASHES, "Ludwig donor", LUDWIG_SOURCE_ALTERNATES)
    _validate_ids(ids, destination)

    mapping = {
        LUDWIG_ONE: ORPHAN_CORE,
        LUDWIG_TWO: ORPHAN_PHASE,
        9471: 13601800,
        13401800: 13601800,
        13404802: 13604802,
        13404803: 13604803,
        13404804: 13604804,
        13404808: 13604808,
        13404809: 13604809,
        13404810: 13604810,
        3403802: 3603802,
        3403803: 3603803,
        3402802: 3602802,
        3400010: 9360010,
        **ids.event_ids,
    }
    initializers, copied = _normal_phase_graph(donor, ids, mapping)
    copied_by_source = dict(zip(LUDWIG_EVENTS, copied))
    if "$InitializeEvent(0, 13604804);" in arena[0]:
        raise ValueError("unexpected Orphan camera initializer")
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 13604850);",
        "    $InitializeEvent(0, 13604850);\n"
        "    $InitializeEvent(0, 13604804);\n"
        + "\n".join(initializers)
        + f"\n    $InitializeEvent(0, {ids.cleanup_event});",
        "Orphan combat initializer anchor",
    )
    edits = {
        0: constructor,
        13604802: _health(donor[13404802], mapping),
        13604803: _remap(donor[13404803], mapping),
        13604804: _camera(donor[13404804], mapping),
        13604820: _end(arena[13604820]),
        13604830: _end(arena[13604830]),
        13604840: _end(arena[13604840]),
        13604850: _end(arena[13604850]),
        **{
            ids.event_ids[source_event]: copied_by_source[source_event]
            for source_event in LUDWIG_EVENTS
        },
        ids.cleanup_event: _cleanup(ids),
    }
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    ).rstrip()
    result += "\n\n" + "\n\n".join(
        edits[event] for event in (*ids.event_ids.values(), ids.cleanup_event)
    ) + "\n"
    output = event_blocks(result)
    expected = set(arena).union(ids.values())
    if set(output) != expected:
        raise ValueError("Ludwig/Orphan changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Ludwig/Orphan changed unrelated arena event {event}")
    for event in (13601800, 13601801, 13601802, 13601803):
        if output[event] != arena[event]:
            raise ValueError("Ludwig/Orphan changed terminal or post-fight progression")
    return result


def _require_slot(
    slots: Sequence[Slot], entity_id: int, archetype: Archetype, map_name: str, role: str
) -> Slot:
    matches = [
        slot
        for slot in slots
        if slot.entity_id == entity_id
        and slot.archetype == archetype
        and slot.map_name == map_name
    ]
    if len(matches) != 1:
        raise ValueError(f"Ludwig/Orphan requires one pinned {role}")
    return matches[0]


def _swap(destination: Slot, donor: Archetype) -> Swap:
    return Swap(
        destination.logical_key,
        [destination.key],
        {destination.key: destination.archetype},
        destination.archetype,
        donor,
        warnings=["experimental Ludwig-at-Orphan contract; runtime behavior unobserved"],
        destinations={
            destination.key: {
                "map_name": destination.map_name,
                "entity_id": destination.entity_id,
                "x": destination.x,
                "y": destination.y,
                "z": destination.z,
            }
        },
    )


def _binding(source: Slot, destination: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "destination_map": destination.map_name,
        "destination_part": destination.part_name,
        "destination_entity_id": destination.entity_id,
        "destination_original_talk_id": destination.talk_id,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
        ],
    }


def native_plan_ludwig_at_orphan(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LudwigOrphanIds = DEFAULT_IDS,
) -> dict:
    """Build two normal primary swaps; the original Orphan OR terminal remains."""
    _validate_ids(ids, "")
    source_one = _require_slot(slots, LUDWIG_ONE, P1, "m34_00_00_00", "Ludwig phase one")
    source_two = _require_slot(slots, LUDWIG_TWO, P2, "m34_00_00_00", "Ludwig phase two")
    target_one = _require_slot(
        slots, ORPHAN_CORE, ORPHAN_CORE_ARCHETYPE, "m36_00_00_00", "Orphan core"
    )
    target_two = _require_slot(
        slots, ORPHAN_PHASE, ORPHAN_PHASE_ARCHETYPE, "m36_00_00_00", "Orphan phase"
    )
    swaps = [_swap(target_one, P1), _swap(target_two, P2)]
    changes, skips = plan_scaling(
        swaps, [target_one, target_two], dict(npcs), dict(effects), boss_tiers=True
    )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": len(swaps),
        "swaps": [swap.json() for swap in swaps],
        "boss_contract": {
            "format": "bb-ludwig-orphan-contract-v1",
            "arena": "orphan-of-kos",
            "donor": "ludwig",
            "encounter_count": 1,
            "logical_swap_count": len(swaps),
            "physical_swap_count": sum(len(swap.destination_keys) for swap in swaps),
            "attachment_event_ids": {
                "event_ids": dict(ids.event_ids),
                "cleanup_event": ids.cleanup_event,
            },
            "runtime_status": "unobserved",
            "source_variant": "normal-two-phase",
            "terminal_policy": "preserve original 13601800 OR predicate",
            "phase_policy": "second original destination primary remains disabled alive until Ludwig transition",
            "preserved_destination_events": [13601800, 13601801, 13601802, 13601803],
            "shadow_actor": ORPHAN_SHADOW,
        },
        "primary_init_source_bindings": [
            _binding(source_one, target_one),
            _binding(source_two, target_two),
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
