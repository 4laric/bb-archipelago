"""Pinned Lady Maria combat at the Living Failures encounter.

The Living Failures aggregate proxy stays the sole completion/reward owner.
Maria replaces only the visible body, then her actual death kills that proxy.
Maria's own m35 arena events remain byte-identical because this is a shared-map
composition input.  Static source and compiler checks do not establish runtime
behaviour.
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
from .maria_contract import (
    MARIA_ARENA,
    MARIA_EVENT_TARGET,
    MARIA_EVENT_TARGET_REFERENCE,
    MARIA_PACKAGE,
    _verify as _verify_maria,
)
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
MARIA_SOURCE = "event/m35_00_00_00.emevd.dcx.js"
PROJECT_MIN, PROJECT_MAX = 12993600, 12993699
MARIA_SOURCE_PIN = "4c8e1f5185a8026aca281a0402ee06fe1c60c361043609b31f178b0b974ef906"

# The existing Living Failures controller calls and generator records are all
# suppressed; their native actors remain pinned so a builder cannot silently
# redirect a stale numeric reference to a different map part.
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
# Event(0) is shared m35 state but receives only our three appended calls. The
# Maria encounter bodies below remain exact so another same-map adapter can
# still establish its own source witnesses.
MARIA_SHARED_EVENTS = tuple(event for event in MARIA_PACKAGE.expected if event != 0)


@dataclass(frozen=True)
class MariaLivingFailuresIds:
    """Reviewed project-owned event allocation; no actor IDs are allocated."""

    phase_cleanup: int = 12993600
    death_to_proxy: int = 12993601
    retire_helpers: int = 12993602

    def values(self) -> tuple[int, int, int]:
        return self.phase_cleanup, self.death_to_proxy, self.retire_helpers


DEFAULT_IDS = MariaLivingFailuresIds()


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


def _validate_ids(ids: MariaLivingFailuresIds, destination: str) -> None:
    values = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(values) != len(set(values))
        or any(value < PROJECT_MIN or value > PROJECT_MAX for value in values)
        or set(values).intersection(local | _original_literals())
    ):
        raise ValueError(
            "Maria/Living Failures IDs must be collision-free project-owned 129936xx values"
        )


def _mapping(ids: MariaLivingFailuresIds) -> dict[int, int]:
    return {
        3500800: PRIMARY,
        13501800: 13501850,
        13504808: 13504858,
        13504810: 13504860,
        13504802: 13504852,
        13504804: 13504854,
        13504822: ids.phase_cleanup,
        3500010: 3500011,
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


def _health(source: str, ids: MariaLivingFailuresIds) -> str:
    result = _remap(source, _mapping(ids))
    helpers = (PROXY, *RETIRED_BODIES, SUPPORT)
    result = _replace_once(
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
    # Preserve Maria's direct health and phase message lifecycle while binding
    # destination diagnostics to the existing Living Failures time/playlog IDs.
    result = _replace_once(
        result, "CreatePlaylog(58);", "CreatePlaylog(136);", "Living Failures playlog"
    )
    return _replace_once(
        result,
        "StartTimeMeasurement(3500011, 74, Enabled);",
        "StartTimeMeasurement(3500011, 158, Enabled);",
        "Living Failures time measurement",
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
        "        flagArea2 &= CharacterHasEventMessage(3500851, 100);",
        "Maria phase-one music witness",
    )


def _camera(source: str, ids: MariaLivingFailuresIds) -> str:
    return _remap(source, _mapping(ids))


def _phase_cleanup(source: str, ids: MariaLivingFailuresIds) -> str:
    return _remap(source, _mapping(ids))


def _retire_helpers(ids: MariaLivingFailuresIds) -> str:
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


def _death_bridge(ids: MariaLivingFailuresIds) -> str:
    return f"""$Event({ids.death_to_proxy}, Default, function() {{
    EndIf(EventFlag(13501850));
    WaitFor(CharacterDead(3500851));
    EndIf(EventFlag(13501850));
    ForceCharacterDeath(3500850, false);
}});"""


def _constructor(block: str, ids: MariaLivingFailuresIds) -> str:
    anchor = "    $InitializeEvent(0, 13505680);"
    if block.count(anchor) != 1:
        raise ValueError("Living Failures Event(0) lacks the combat initializer anchor")
    return _replace_once(
        block,
        anchor,
        anchor
        + f"\n    $InitializeEvent(0, {ids.phase_cleanup});"
        + f"\n    $InitializeEvent(0, {ids.death_to_proxy});"
        + f"\n    $InitializeEvent(0, {ids.retire_helpers});",
        "Living Failures combat initializer anchor",
    )


def patch_maria_at_living_failures(
    destination: str,
    donor_source: str,
    ids: MariaLivingFailuresIds = DEFAULT_IDS,
) -> str:
    """Install Maria on 3500851 and retain proxy-owned completion intact."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify_failures(arena, ARENA_HASHES, "Living Failures arena")
    _verify_maria(donor, MARIA_PACKAGE.expected, "Lady Maria donor")
    _validate_ids(ids, destination)
    edits = {
        0: _constructor(arena[0], ids),
        13501851: _entry_without_failure_animation(arena[13501851]),
        13504852: _health(donor[13504802], ids),
        13504853: _music(arena[13504853]),
        13504854: _camera(donor[13504804], ids),
        **{event: _end_event(arena[event]) for event in SUPPRESSED_EVENTS},
        ids.phase_cleanup: _phase_cleanup(donor[13504822], ids),
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
        raise ValueError("Maria/Living Failures changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(
                f"Maria/Living Failures changed unrelated arena event {event}"
            )
    if output[13501850] != arena[13501850]:
        raise ValueError("Maria/Living Failures changed the Living Failures terminal")
    for event in MARIA_SHARED_EVENTS:
        if output[event] != arena[event]:
            raise ValueError("Maria/Living Failures changed shared Maria arena state")
    copied = "\n".join(
        output[event] for event in (13504852, 13504853, 13504854, *ids.values())
    )
    # 3500801 is Maria's declared opaque target, deliberately neither spawned
    # nor remapped. All other copied source encounter literals must be gone.
    foreign = {3500800, 13501800, 13504808, 13504810, 3500010}
    retained = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", copied)))
    if retained.intersection(foreign):
        raise ValueError(
            "Maria/Living Failures copied combat retains donor arena literals"
        )
    if copied.count("SetCharacterEventTarget(3500851, 3500801);") != 1:
        raise ValueError("Maria/Living Failures lost Maria opaque event-target witness")
    return result


def maria_living_failures_external_reference_requirement() -> dict:
    """Native request for the static absence-witnessed Maria target literal."""
    return {
        "format": "bb-boss-external-reference-v1",
        "entity_id": MARIA_EVENT_TARGET,
        "source_map": "m35_00_00_00",
        "destination_maps": ["m35_00_00_00"],
        "source_event_file": "m35_00_00_00.emevd.dcx",
        "source_event_id": MARIA_ARENA.health_event,
        "source_actor": 3500800,
        "destination_event_file": "m35_00_00_00.emevd.dcx",
        "destination_event_id": 13504852,
        "destination_actor": PRIMARY,
        "evidence_status": MARIA_EVENT_TARGET_REFERENCE.evidence_status,
        "runtime_status": MARIA_EVENT_TARGET_REFERENCE.runtime_status,
    }


def _require(
    slots: Sequence[Slot], entity: int, archetype, map_name: str
) -> list[Slot]:
    found = sorted(
        (
            slot
            for slot in slots
            if slot.entity_id == entity
            and slot.archetype == archetype
            and slot.map_name == map_name
        ),
        key=lambda slot: slot.key,
    )
    if len(found) != 1 or found[0].dummy:
        raise ValueError(
            f"Maria/Living Failures requires one pinned actor {entity} in {map_name}"
        )
    return found


def _binding(source: Slot, destination: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": MARIA_SOURCE_PIN,
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


def native_plan_maria_at_living_failures(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: MariaLivingFailuresIds = DEFAULT_IDS,
) -> dict:
    """Return the one pinned Maria primary swap plus disabled native helpers."""
    source_text = read_blob(BUNDLE, MARIA_SOURCE).decode("utf-8-sig")
    blocks = event_blocks(source_text)
    _verify_failures(blocks, ARENA_HASHES, "Living Failures arena")
    _verify_maria(blocks, MARIA_PACKAGE.expected, "Lady Maria donor")
    _validate_ids(ids, source_text)
    source = _require(slots, 3500800, MARIA_PACKAGE.archetype, "m35_00_00_00")[0]
    target = _require(slots, PRIMARY, PRIMARY_ARCHETYPE, "m35_00_00_00")[0]
    helpers = [
        _require(slots, PROXY, PROXY_ARCHETYPE, target.map_name)[0],
        *[
            _require(slots, entity, archetype, target.map_name)[0]
            for entity, archetype in BODY_ARCHETYPES.items()
        ],
    ]
    if len(helpers) != 5:
        raise ValueError("Maria/Living Failures requires five retained m35 helpers")
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        source.archetype,
        warnings=[
            "experimental Maria-at-Living-Failures contract; runtime behavior unobserved"
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
            "Maria/Living Failures primary swap has ambiguous normalization"
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
                "retain_offstage_proxy_disabled_alive_until_maria_death_bridge"
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
        "boss_external_references": [
            maria_living_failures_external_reference_requirement()
        ],
        "boss_contract": {
            "format": "bb-maria-living-failures-contract-v1",
            "arena": "living-failures",
            "donor": "lady-maria",
            "status": "planned",
            "writer_status": "pending_builder_integration",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "physical_swap_count": 1,
            "helper_id_range": [981400, 981499],
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
            "preserved_maria_events": list(MARIA_SHARED_EVENTS),
            "terminal_policy": "retain byte-identical aggregate proxy terminal; bridge Maria death to proxy only afterward",
            "retained_destination_helpers": retained,
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(MARIA_PACKAGE.expected),
            "opaque_external_references": [
                {
                    **asdict(MARIA_EVENT_TARGET_REFERENCE),
                    "destination_event": 13504852,
                    "destination_actor": PRIMARY,
                }
            ],
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
