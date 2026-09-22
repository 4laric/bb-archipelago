"""Micolash direct combat at Gehrman, retaining the Dream's progression."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from tools.bb_inputs import read_blob
from .boss_canary import event_blocks
from .final_boss_contracts import GEHRMAN, GEHRMAN_PACKAGE, PINS
from .micolash_moon_contract import (
    ARENA_SOURCE,
    BUNDLE,
    DONOR_SOURCE,
    DONOR_HASHES,
    _end_event,
    _original_literals,
    _replace_events,
    _replace_once,
    _require,
    _verify,
    direct_combat_health,
    primary_native_plan,
)


@dataclass(frozen=True)
class MicolashGehrmanIds:
    phase_state: int = 12994100
    phase_marker: int = 12994120


DEFAULT_IDS = MicolashGehrmanIds()


def _validate(ids, destination):
    values = tuple(asdict(ids).values())
    used = _original_literals() | set(
        map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination))
    )
    if (
        len(set(values)) != len(values)
        or any(not 12994100 <= value <= 12994199 for value in values)
        or set(values) & used
    ):
        raise ValueError(
            "Micolash/Gehrman requires collision-free 129941xx allocations"
        )


def patch_micolash_at_gehrman(destination, donor_source, ids=DEFAULT_IDS):
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, PINS, "Gehrman arena")
    _verify(donor, DONOR_HASHES, "Micolash donor")
    _validate(ids, destination)
    health = direct_combat_health(
        donor[12604852],
        actor=GEHRMAN,
        completion=12101800,
        start_flag=12104800,
        coop_flag=12104801,
        health_event=12104802,
        time_event=2100010,
        playlog=64,
        measurement=80,
    )
    # Gehrman's original entry protection remains around the donor health setup.
    health = _replace_once(
        health,
        "    SetCharacterHPBarDisplay(2100800, Disabled);",
        "    SetCharacterHPBarDisplay(2100800, Disabled);\n"
        "    SetCharacterInvincibility(2100800, Enabled);",
        "entry protection",
    )
    health = _replace_once(
        health,
        "    DisplayBossHealthBar(Enabled, 2100800, 0, 899000);",
        "    DisplayBossHealthBar(Enabled, 2100800, 0, 899000);\n"
        "    SetCharacterInvincibility(2100800, Disabled);",
        "combat vulnerability",
    )
    music = _replace_once(
        arena[12104803],
        "CharacterHasEventMessage(2100800, 100)",
        f"EventFlag({ids.phase_marker})",
        "half-health music phase",
    )
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12104808);",
        "    $InitializeEvent(0, 12104808);\n"
        f"    $InitializeEvent(0, {ids.phase_state});",
        "Gehrman combat initializer",
    )
    phase = f"""$Event({ids.phase_state}, Default, function() {{
    EndIf(EventFlag(12101800));
    if (!ThisEvent()) {{
        SetEventFlag({ids.phase_marker}, OFF);
        WaitFor(EventFlag(12104802) && HPRatio(2100800) <= 0.5);
    }}
L0:
    SetEventFlag({ids.phase_marker}, ON);
    RequestCharacterAICommand(2100800, -1, 0);
    RequestCharacterAIReplan(2100800);
}});"""
    edits = {
        0: constructor,
        12104802: health,
        12104803: music,
        12104807: _end_event(arena[12104807]),
        12104808: _end_event(arena[12104808]),
    }
    result = _replace_events(destination, edits).rstrip() + "\n\n" + phase + "\n"
    after = event_blocks(result)
    if set(after) != set(arena) | {ids.phase_state}:
        raise ValueError("Micolash/Gehrman changed unexpected event identities")
    for event, original in arena.items():
        if event not in edits and after[event] != original:
            raise ValueError(f"Micolash/Gehrman changed unrelated event {event}")
    if re.search(r"(?<!\d)(?:126|260)\d+(?!\d)", health + phase):
        raise ValueError("Micolash/Gehrman retains Mensis state")
    return result


def native_plan_micolash_at_gehrman(slots, npcs, effects, seed, ids=DEFAULT_IDS):
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    patch_micolash_at_gehrman(arena, donor, ids)
    target = _require(slots, GEHRMAN, GEHRMAN_PACKAGE.archetype, 210306)
    return primary_native_plan(
        slots,
        npcs,
        effects,
        seed,
        target,
        {
            "format": "bb-micolash-gehrman-contract-v1",
            "arena": "gehrman",
            "donor": "micolash",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(PINS),
            "preserved_destination_events": [
                50,
                12100800,
                12101800,
                12101802,
                12104804,
                12104805,
                12101850,
                12101852,
            ],
            "terminal_policy": "Gehrman terminal, cutscene, rewards and final progression remain byte-identical",
            "combat_policy": "same pinned Micolash direct-combat release and local half-health marker as Moon adapter; no chase/dialogue/progression flags imported",
            "helper_policy": "retain original Dream helpers unchanged for shared-map composition; Micolash imports no helper reference",
            "placement_policy": "original Gehrman combat position; no labyrinth geometry",
        },
    )
