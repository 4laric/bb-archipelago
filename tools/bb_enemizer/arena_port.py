"""Small composition seam between portable combat and special boss arenas.

An :class:`ArenaPort` names the destination state which combat may replace.
Constructor insertion and event-body retirement are deliberately independent:
some arenas use a preserved entry/co-op event as the insertion anchor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .boss_canary import event_blocks, parse_events
from .boss_contracts import ArenaContract
from .boss_entrances import skip_replacement_entrance
from .gehrman_arena_contract import (
    DESTINATION_MSB_SHA256 as GEHRMAN_MSB_SHA256,
    DESTINATION_PINS as GEHRMAN_PINS,
    DIALOGUE as GEHRMAN_DIALOGUE,
    EVENT_TARGET as GEHRMAN_EVENT_TARGET,
    GEHRMAN_ARENA_CONTRACT,
)
from .gehrman_micolash_contract import CHASE_EVENTS, MICOLASH_PIN
from .micolash_arena_contract import (
    DESTINATION_MSB_SHA256 as MICOLASH_MSB_SHA256,
    MICOLASH_ARENA_CONTRACT,
)
from .moon_arena_contract import (
    DESTINATION_MSB_SHA256 as MOON_MSB_SHA256,
    DESTINATION_PINS as MOON_PINS,
    MOON_ARENA_CONTRACT,
)


@dataclass(frozen=True)
class ConstructorInsertion:
    """An exact existing Event(0) call after which new calls may be inserted."""

    event_id: int
    slot: int = 0
    arguments: tuple[str, ...] = ()

    def statement(self) -> str:
        suffix = ", " + ", ".join(self.arguments) if self.arguments else ""
        return f"    $InitializeEvent({self.slot}, {self.event_id}{suffix});"


@dataclass(frozen=True)
class RetainedNativeActor:
    entity_id: int
    part_sha256: str
    talk_id: int
    policy: str


@dataclass(frozen=True)
class ArenaPort:
    """Pinned destination capabilities consumed by a portable donor."""

    arena: ArenaContract
    destination_map: str
    destination_msb_sha256: str
    primary_part_sha256: str
    primary_talk_id: int
    constructor: ConstructorInsertion
    retired_events: tuple[int, ...]
    protected_events: tuple[int, ...]
    music_phase_witness: str
    retirement_mode: str = "end"
    retained_native_actors: tuple[RetainedNativeActor, ...] = ()
    terminal_bridge_event: int | None = None
    terminal_release_flag: int | None = None
    placement_policy: str = "destination-native-position"


@dataclass(frozen=True)
class PortableCombatFragments:
    """Donor-produced changes merged by the destination-owned composer."""

    replacements: Mapping[int, str]
    additions: Mapping[int, str]
    initializers: tuple[str, ...]
    constructor_resets: tuple[int, ...] = ()


def _retired_body(block: str, mode: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function(" + ", ".join(
            value.strip() if value.strip().startswith("unused_")
            else "unused_" + value.strip()
            for value in match[1].split(",") if value.strip()
        ) + ")",
        declaration,
    )
    if mode == "end":
        return declaration + "\n    EndEvent();\n});"
    if mode == "permanent-wait":
        # Micolash terminal logic observes ThisEvent for one chase controller.
        return declaration + "\n    WaitFor(InArea(10000, 0));\n    EndEvent();\n});"
    raise ValueError(f"unknown arena retirement mode {mode}")


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def compose_arena_port(destination: str, port: ArenaPort,
                       fragments: PortableCombatFragments) -> str:
    """Compose declared fragments while enforcing the port's ownership lines."""
    original = event_blocks(destination)
    replacement_ids = set(fragments.replacements)
    addition_ids = set(fragments.additions)
    retired_ids = set(port.retired_events)
    if replacement_ids - set(original):
        raise ValueError("portable fragments replace an absent destination event")
    if addition_ids & set(original) or addition_ids & replacement_ids:
        raise ValueError("portable fragment event identities overlap")
    if retired_ids - set(original):
        raise ValueError("arena port retires an absent destination event")
    if retired_ids & set(port.protected_events):
        raise ValueError("arena port retires a protected destination event")

    anchor = port.constructor.statement()
    constructor = original[0]
    if constructor.count(anchor) != 1:
        raise ValueError(f"{port.arena.key} lacks its exact constructor anchor")
    if not fragments.initializers:
        raise ValueError("portable combat has no constructor initializers")
    constructor = constructor.replace(
        anchor, anchor + "\n" + "\n".join(fragments.initializers), 1
    )
    if fragments.constructor_resets:
        if (any(flag <= 0 for flag in fragments.constructor_resets)
                or len(set(fragments.constructor_resets)) != len(fragments.constructor_resets)):
            raise ValueError("portable combat has invalid constructor reset flags")
        header = constructor.splitlines()[0] + "\n"
        resets = "".join(
            f"    SetEventFlag({flag}, OFF);\n"
            for flag in fragments.constructor_resets
        )
        if constructor.count(header) != 1:
            raise ValueError("arena constructor header is ambiguous")
        constructor = constructor.replace(header, header + resets, 1)
    edits = {
        event_id: _retired_body(original[event_id], port.retirement_mode)
        for event_id in retired_ids
    }
    edits.update(fragments.replacements)
    edits[0] = constructor
    result = _replace_events(destination, edits).rstrip()
    if fragments.additions:
        result += "\n\n" + "\n\n".join(fragments.additions.values())
    result += "\n"
    result = skip_replacement_entrance(port.arena.key, destination, result)

    output = event_blocks(result)
    if set(output) != set(original) | addition_ids:
        raise ValueError("arena-port composition changed unexpected event identities")
    allowed = set(edits) | {port.arena.activation_event}
    for event_id, body in original.items():
        if event_id not in allowed and output[event_id] != body:
            raise ValueError(f"arena-port composition changed unrelated event {event_id}")
    for event_id in port.protected_events:
        if output[event_id] != original[event_id]:
            raise ValueError(f"arena-port composition changed protected event {event_id}")
    return result


def primary_death_terminal_bridge(port: ArenaPort) -> str:
    """Open a destination-owned terminal flag only after its primary dies."""
    if port.terminal_bridge_event is None or port.terminal_release_flag is None:
        raise ValueError("arena port has no terminal bridge allocation")
    return f"""$Event({port.terminal_bridge_event}, Default, function() {{
    EndIf(EventFlag({port.arena.completion_event}));
    SetEventFlag({port.terminal_release_flag}, OFF);
    WaitFor(CharacterDead({port.arena.actor}));
    SetEventFlag({port.terminal_release_flag}, ON);
}});"""


GEHRMAN_PORT = ArenaPort(
    arena=GEHRMAN_ARENA_CONTRACT,
    destination_map="m21_00_00_00",
    destination_msb_sha256=GEHRMAN_MSB_SHA256,
    primary_part_sha256=GEHRMAN_PINS[2100800],
    primary_talk_id=210306,
    constructor=ConstructorInsertion(12101803),
    retired_events=(12104807, 12104808),
    protected_events=(12101800, 12101801, 12101803, 12104805, 12104810,
                      12104811, 12101850, 12101853),
    music_phase_witness="CharacterHasEventMessage(2100800, 100)",
    retained_native_actors=(
        RetainedNativeActor(
            GEHRMAN_DIALOGUE, GEHRMAN_PINS[GEHRMAN_DIALOGUE], 210305,
            "dialogue/progression actor preserved byte-for-byte",
        ),
        RetainedNativeActor(
            GEHRMAN_EVENT_TARGET, GEHRMAN_PINS[GEHRMAN_EVENT_TARGET], 0,
            "offstage destination event target preserved byte-for-byte",
        ),
    ),
)

MOON_PORT = ArenaPort(
    arena=MOON_ARENA_CONTRACT,
    destination_map="m21_00_00_00",
    destination_msb_sha256=MOON_MSB_SHA256,
    primary_part_sha256=MOON_PINS[2100810],
    primary_talk_id=0,
    constructor=ConstructorInsertion(12104870),
    retired_events=(12104860, 12104870),
    protected_events=(12101850, 12101853, 12104855, 12104880, 12104881),
    music_phase_witness="CharacterHasEventMessage(2100810, 500)",
    retained_native_actors=(
        RetainedNativeActor(
            2100800, MOON_PINS[2100800], 210306,
            "Gehrman sibling retained for Moon entry and final progression",
        ),
        RetainedNativeActor(
            2100801, MOON_PINS[2100801], 0,
            "Gehrman event-target sibling retained for final progression",
        ),
    ),
)

MICOLASH_PORT = ArenaPort(
    arena=MICOLASH_ARENA_CONTRACT,
    destination_map="m26_00_00_00",
    destination_msb_sha256=MICOLASH_MSB_SHA256,
    primary_part_sha256=MICOLASH_PIN,
    primary_talk_id=260311,
    constructor=ConstructorInsertion(12604855),
    retired_events=tuple(CHASE_EVENTS),
    protected_events=(12601850, 12601854, 12601855, 12604855, 12604860, 12604861),
    music_phase_witness="EventFlag(72600300)",
    retirement_mode="permanent-wait",
    terminal_bridge_event=12996800,
    terminal_release_flag=72600301,
    placement_policy="original-initial-area-direct-fight",
)

MARIA_CROSS_ARENA_PORTS = (GEHRMAN_PORT, MOON_PORT, MICOLASH_PORT)
