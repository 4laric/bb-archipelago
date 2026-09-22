"""Pinned Laurence combat at the Living Failures encounter.

Laurence replaces the visible Living Failures body.  The disabled aggregate
proxy remains the only completion/reward owner and is killed after Laurence's
actual death.  The source m34 script also owns Ludwig; it is read-only input
and the adapter copies only the pinned Laurence health, camera, limb and
hitmask bodies into project-owned event IDs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .bsb_living_failures_contract import (
    ARENA_HASHES,
    BODY_ARCHETYPES,
    PRIMARY,
    PRIMARY_ARCHETYPE,
    PROXY,
    PROXY_ARCHETYPE,
    RETAINED_PINS,
    SUPPORT,
    _end_event,
    _replace_once,
    _verify as _verify_failures,
)
from .laurence_contract import LAURENCE, PINS as LAURENCE_HASHES
from .ludwig_contract import SOURCE_HASHES as LUDWIG_SOURCE_HASHES
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
LAURENCE_SOURCE = "event/m34_00_00_00.emevd.dcx.js"
LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)
LAURENCE_SOURCE_PIN = "cdf84241072ed9304f89d145ca746572548edf26bcd5c80e571d3237e0e7a12c"
PROJECT_MIN, PROJECT_MAX = 12993700, 12993799
RETIRED_BODIES = (3500852, 3500853, 3500854)
SUPPRESSED_EVENTS = (
    13504865,
    13504880,
    13504881,
    13504885,
    13504890,
    13504895,
    13505655,
    13505656,
    13505661,
    13505662,
    13505680,
)


@dataclass(frozen=True)
class LaurenceLivingFailuresIds:
    """Project-owned copies of five Laurence limbs and phase hitmask."""

    limbs: int = 12993700
    hitmask: int = 12993701
    death_to_proxy: int = 12993702
    retire_helpers: int = 12993703

    def values(self) -> tuple[int, int, int, int]:
        return self.limbs, self.hitmask, self.death_to_proxy, self.retire_helpers


DEFAULT_IDS = LaurenceLivingFailuresIds()
LUDWIG_SOURCE_ALTERNATES = {
    # Installed CUSA03173 source updates Ludwig's hidden form every frame.
    # It is a reviewed source-only variant; no part of this body is copied.
    13404802: "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab"
}


def _verify_laurence_source(blocks: Mapping[int, str]) -> None:
    """Pin both encounters in m34 before selecting Laurence-only bodies."""
    _verify_failures(blocks, LAURENCE_HASHES, "Laurence donor")
    pins = dict(LUDWIG_SOURCE_HASHES)
    pins[13404802] = (pins[13404802], LUDWIG_SOURCE_ALTERNATES[13404802])
    _verify_failures(blocks, pins, "collocated Ludwig source")


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


@cache
def _original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return values


def _validate_ids(ids: LaurenceLivingFailuresIds, destination: str) -> None:
    values = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(values) != len(set(values))
        or any(value < PROJECT_MIN or value > PROJECT_MAX for value in values)
        or set(values).intersection(local | _original_literals())
    ):
        raise ValueError(
            "Laurence/Living Failures IDs must be collision-free project-owned 129937xx values"
        )


def _mapping(ids: LaurenceLivingFailuresIds) -> dict[int, int]:
    return {
        LAURENCE: PRIMARY,
        13401850: 13501850,
        13404858: 13504858,
        13404860: 13504860,
        13404852: 13504852,
        13404854: 13504854,
        13404870: ids.limbs,
        13404875: ids.hitmask,
        3400030: 3500011,
    }


def _entry_without_failure_animation(block: str) -> str:
    result = block
    for line in (
        "    ForceAnimationPlayback(3500851, 9000, true, false, false);\n",
        "    ForceAnimationPlayback(3500851, 9060, false, false, false);\n",
        "    RequestCharacterAIReplan(3500851);\n",
    ):
        result = _replace_once(result, line, "", "Living Failures-only entry animation")
    return result


def _health(source: str, ids: LaurenceLivingFailuresIds) -> str:
    result = _remap(source, _mapping(ids))
    helpers = (PROXY, *RETIRED_BODIES, SUPPORT)
    return _replace_once(
        result,
        "    SetCharacterHPBarDisplay(3500851, Disabled);\n",
        "    SetCharacterHPBarDisplay(3500851, Disabled);\n"
        + "".join(
            f"    SetCharacterAIState({actor}, Disabled);\n"
            f"    SetCharacterHPBarDisplay({actor}, Disabled);\n"
            for actor in helpers
        )
        + f"    SetCharacterGravity({PROXY}, Disabled);\n",
        "retained Living Failures helper initialization",
    )


def _music(block: str) -> str:
    result = _replace_once(
        block,
        "    EndIf(EventFlag(13501800));",
        "    EndIf(EventFlag(13501850));",
        "Living Failures completion guard",
    )
    return _replace_once(
        result,
        "        flagArea2 &= EventFlag(13504870);",
        "        flagArea2 &= CharacterHasEventMessage(3500851, 400);",
        "Laurence phase music witness",
    )


def _camera(source: str, ids: LaurenceLivingFailuresIds) -> str:
    result = _remap(source, _mapping(ids))
    source_map = "SetLockcamSlotNumber(34, 0,"
    if result.count(source_map) != 2:
        raise ValueError("Laurence camera lacks the exact two map bindings")
    result = result.replace(source_map, "SetLockcamSlotNumber(35, 0,")
    if "SetLockcamSlotNumber(34," in result:
        raise ValueError("Laurence/Living Failures retained donor camera map")
    return result


def _calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))", line
        )
    ]
    if len(calls) != count:
        raise ValueError(
            f"Laurence Event(0) lacks {count} initializer witnesses for {event_id}"
        )
    return calls


def _constructor(
    arena_zero: str, donor_zero: str, ids: LaurenceLivingFailuresIds
) -> str:
    limbs = [_remap(line, _mapping(ids)) for line in _calls(donor_zero, 13404870, 5)]
    hitmask = [_remap(line, _mapping(ids)) for line in _calls(donor_zero, 13404875, 1)]
    anchor = "    $InitializeEvent(0, 13505680);"
    if arena_zero.count(anchor) != 1:
        raise ValueError("Living Failures Event(0) lacks the combat initializer anchor")
    return _replace_once(
        arena_zero,
        anchor,
        anchor
        + "\n"
        + "\n".join((*limbs, *hitmask))
        + f"\n    $InitializeEvent(0, {ids.death_to_proxy});"
        + f"\n    $InitializeEvent(0, {ids.retire_helpers});",
        "Living Failures combat initializer anchor",
    )


def _retire_helpers(ids: LaurenceLivingFailuresIds) -> str:
    actors = (*RETIRED_BODIES, SUPPORT)
    disabled = "".join(
        f"    SetCharacterAIState({actor}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({actor}, Disabled);\n"
        f"    ChangeCharacterEnableState({actor}, Disabled);\n"
        for actor in actors
    )
    deaths = "".join(f"    ForceCharacterDeath({actor}, false);\n" for actor in actors)
    return f"""$Event({ids.retire_helpers}, Default, function() {{
    DeactivateGenerator(3503814, Disabled);
    DeactivateGenerator(3503815, Disabled);
    DeactivateGenerator(3503816, Disabled);
    DeactivateGenerator(3503817, Disabled);
{disabled}    if (EventFlag(13501850)) {{
{deaths}        EndEvent();
    }}
    WaitFor(EventFlag(13501850));
{deaths}}});"""


def _death_bridge(ids: LaurenceLivingFailuresIds) -> str:
    return f"""$Event({ids.death_to_proxy}, Default, function() {{
    EndIf(EventFlag(13501850));
    WaitFor(CharacterDead(3500851));
    EndIf(EventFlag(13501850));
    ForceCharacterDeath(3500850, false);
}});"""


def patch_laurence_at_living_failures(
    destination: str,
    donor_source: str,
    ids: LaurenceLivingFailuresIds = DEFAULT_IDS,
) -> str:
    """Install Laurence's full direct-combat graph on visible body 3500851."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify_failures(arena, ARENA_HASHES, "Living Failures arena")
    _verify_laurence_source(donor)
    _validate_ids(ids, destination)
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        13501851: _entry_without_failure_animation(arena[13501851]),
        13504852: _health(donor[13404852], ids),
        13504853: _music(arena[13504853]),
        13504854: _camera(donor[13404854], ids),
        **{event: _end_event(arena[event]) for event in SUPPRESSED_EVENTS},
        ids.limbs: _remap(donor[13404870], _mapping(ids)),
        ids.hitmask: _remap(donor[13404875], _mapping(ids)),
        ids.death_to_proxy: _death_bridge(ids),
        ids.retire_helpers: _retire_helpers(ids),
    }
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.values())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.values()):
        raise ValueError("Laurence/Living Failures changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(
                f"Laurence/Living Failures changed unrelated Living Failures event {event}"
            )
    if output[13501850] != arena[13501850]:
        raise ValueError(
            "Laurence/Living Failures changed the Living Failures terminal"
        )
    copied = "\n".join(
        output[event] for event in (13504852, 13504853, 13504854, *ids.values())
    )
    if re.search(r"(?<!\d)(?:3400850|13401850|13404858|13404860)(?!\d)", copied):
        raise ValueError(
            "Laurence/Living Failures copied combat retains donor encounter literals"
        )
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and slot.map_name == map_name
    ]
    if len(found) != 1 or found[0].dummy:
        raise ValueError(
            f"Laurence/Living Failures requires one pinned actor {entity} in {map_name}"
        )
    return found[0]


def _binding(source: Slot, destination: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": LAURENCE_SOURCE_PIN,
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
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


def native_plan_laurence_at_living_failures(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LaurenceLivingFailuresIds = DEFAULT_IDS,
) -> dict:
    """Return the primary swap and all source-pinned retained m35 helpers."""
    failures = read_blob(BUNDLE, "event/m35_00_00_00.emevd.dcx.js").decode("utf-8-sig")
    donor = read_blob(BUNDLE, LAURENCE_SOURCE).decode("utf-8-sig")
    _verify_failures(event_blocks(failures), ARENA_HASHES, "Living Failures arena")
    _verify_laurence_source(event_blocks(donor))
    _validate_ids(ids, failures)
    source = _require(slots, LAURENCE, LAURENCE_ARCHETYPE, "m34_00_00_00")
    target = _require(slots, PRIMARY, PRIMARY_ARCHETYPE, "m35_00_00_00")
    helpers = [
        _require(slots, PROXY, PROXY_ARCHETYPE, target.map_name),
        *[
            _require(slots, entity, archetype, target.map_name)
            for entity, archetype in BODY_ARCHETYPES.items()
        ],
    ]
    if len(helpers) != 5:
        raise ValueError("Laurence/Living Failures requires five retained m35 helpers")
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        source.archetype,
        warnings=[
            "experimental Laurence-at-Living-Failures contract; runtime behavior unobserved"
        ],
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
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Laurence/Living Failures primary swap has ambiguous normalization"
        )
    retained = [
        {
            "map": slot.map_name,
            "part": slot.part_name,
            "entity_id": slot.entity_id,
            "archetype": asdict(slot.archetype),
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": RETAINED_PINS[slot.entity_id],
            },
            "source_initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": (
                "retain_offstage_proxy_disabled_alive_until_laurence_death_bridge"
                if slot.entity_id == PROXY
                else "retain_wave_or_support_disabled_until_destination_completion"
            ),
        }
        for slot in helpers
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "primary_init_source_bindings": [_binding(source, target)],
        "boss_contract": {
            "format": "bb-laurence-living-failures-contract-v1",
            "arena": "living-failures",
            "donor": "laurence",
            "status": "planned",
            "writer_status": "pending_builder_integration",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "helper_id_range": [981500, 981599],
            "actor_additions": [],
            "preserved_destination_events": [
                13501850,
                13501852,
                13504850,
                13504851,
                13504855,
                13504856,
                13504857,
            ],
            "terminal_policy": "retain byte-identical aggregate proxy terminal; bridge Laurence death to proxy only afterward",
            "retained_destination_helpers": retained,
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(LAURENCE_HASHES),
            "source_ludwig_policy": "m34 source is read-only; no Ludwig event, actor, terminal, or initializer is copied",
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
