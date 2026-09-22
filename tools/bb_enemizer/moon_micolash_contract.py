"""Evidence-pinned Moon Presence combat in Micolash's arena.

Micolash's terminal, rewards, Wet Nurse-related map progression, and fog remain
destination-owned. Moon Presence combat replaces only direct-fight controllers;
the chase graph is held inert so it cannot re-enable destination Micolash AI.
Runtime behaviour is unobserved.
"""

from __future__ import annotations
import hashlib, re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence
from tools.bb_inputs import read_blob, read_prefix
from .boss_canary import event_blocks
from .bosses import parse_events
from .final_boss_contracts import MOON_PACKAGE, PINS as MOON_HASHES
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from .gehrman_micolash_contract import ARENA_HASHES, CHASE_EVENTS, MICOLASH_PIN

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
DONOR_SOURCE = "event/m21_00_00_00.emevd.dcx.js"
ARENA_SOURCE = "event/m26_00_00_00.emevd.dcx.js"
MOON, MICOLASH = 2100810, 2600850
COMPLETION = 12601850
MOON_ARCHETYPE = Archetype("c5400", 540000, 540000, 0)
MICOLASH_ARCHETYPE = Archetype("c0000", 6380, 6380, 0)
MOON_PIN = "fb6b3c45b1c16ec4aa7bc8ff6cb2107caa06f98a4e6c26bd7f0d3064f84f4e67"


@dataclass(frozen=True)
class MoonMicolashIds:
    limb_controller: int = 12994200
    player_immortality: int = 12994201
    terminal_bridge: int = 12994202
    evidence: str = "Moon/Micolash allocation v1; full original EMEVD and MSBB scan"

    def events(self) -> tuple[int, ...]:
        return (self.limb_controller, self.player_immortality, self.terminal_bridge)


DEFAULT_IDS = MoonMicolashIds()


def _verify(blocks: Mapping[int, str], pins: Mapping[int, str], role: str) -> None:
    for event, digest in pins.items():
        if hashlib.sha256(blocks.get(event, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Moon/Micolash expected one {label}")
    return text.replace(old, new, 1)


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
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _rename(
    block: str, source_event: int, destination_event: int, values: Mapping[int, int]
) -> str:
    remapped = _remap(block, values)
    return _replace_once(
        remapped,
        f"$Event({values.get(source_event, source_event)},",
        f"$Event({destination_event},",
        "attachment header",
    )


def _inert(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join("unused_" + x.strip() for x in m[1].split(",") if x.strip())
        + ")",
        header,
    )
    return header + "\n    WaitFor(InArea(10000, 0));\n    EndEvent();\n});"


@cache
def _original_literals() -> set[int]:
    out = set()
    for body in read_prefix(BUNDLE, "event/").values():
        out.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return out


def _validate(ids: MoonMicolashIds, destination: str) -> None:
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(ids.events())) != len(ids.events())
        or any(not 12994200 <= x <= 12994299 for x in ids.events())
        or set(ids.events()) & (local | _original_literals())
        or not ids.evidence.strip()
    ):
        raise ValueError("Moon/Micolash allocation collides with original inputs")


def _mapping(ids: MoonMicolashIds) -> dict[int, int]:
    return {
        MOON: MICOLASH,
        12101850: COMPLETION,
        12104850: 12604850,
        12104852: 12604852,
        12104853: 12604853,
        12104854: 12604854,
        12104860: ids.limb_controller,
        12104870: ids.player_immortality,
        2100011: 2601010,
    }


def patch_moon_at_micolash(
    destination: str, donor_source: str, ids: MoonMicolashIds = DEFAULT_IDS
) -> str:
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Micolash arena")
    _verify(donor, MOON_HASHES, "Moon Presence donor")
    _validate(ids, destination)
    m = _mapping(ids)
    health = _remap(donor[12104852], m)
    health = _replace_once(
        health, "CreatePlaylog(128);", "CreatePlaylog(88);", "Micolash playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2601010, 146, Enabled);",
        "StartTimeMeasurement(2601010, 232, Enabled);",
        "Micolash time measurement",
    )
    music = _replace_once(
        arena[12604853],
        "        WaitFor(EventFlag(72600300));",
        "        WaitFor(CharacterHasEventMessage(2600850, 500));",
        "Moon phase music",
    )
    lockcam = _rename(donor[12104854], 12104854, 12604854, m)
    if lockcam.count("SetLockcamSlotNumber(21, 0,") != 2:
        raise ValueError("Moon/Micolash expected two Mensis lockcam instructions")
    lockcam = lockcam.replace(
        "SetLockcamSlotNumber(21, 0,", "SetLockcamSlotNumber(26, 0,"
    )
    limb = _rename(donor[12104860], 12104860, ids.limb_controller, m)
    immunity = _rename(donor[12104870], 12104870, ids.player_immortality, m)
    bridge = f"""$Event({ids.terminal_bridge}, Default, function() {{
    EndIf(EventFlag({COMPLETION}));
    SetEventFlag(72600301, OFF);
    WaitFor(CharacterDead({MICOLASH}));
    SetEventFlag(72600301, ON);
}});"""
    limb_initializers = []
    for line in donor[0].splitlines():
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*12104860(?:,|\))", line):
            limb_initializers.append(
                _remap(line, {MOON: MICOLASH, 12104860: ids.limb_controller})
            )
    if len(limb_initializers) != 5:
        raise ValueError("Moon Event(0) lacks five limb initializer witnesses")
    immune = [
        line
        for line in donor[0].splitlines()
        if re.match(r"\s*\$InitializeEvent\([^,]+,\s*12104870(?:,|\))", line)
    ]
    if len(immune) != 1:
        raise ValueError(
            "Moon Event(0) lacks one player-immortality initializer witness"
        )
    init = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12604855);",
        "    $InitializeEvent(0, 12604855);\n"
        + "\n".join(limb_initializers)
        + "\n"
        + _remap(immune[0], {MOON: MICOLASH, 12104870: ids.player_immortality})
        + f"\n    $InitializeEvent(0, {ids.terminal_bridge});",
        "Micolash controller anchor",
    )
    edits = {
        0: init,
        12604852: health,
        12604853: music,
        12604854: lockcam,
        **{x: _inert(arena[x]) for x in CHASE_EVENTS},
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((limb, immunity, bridge))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.events()):
        raise ValueError("Moon/Micolash changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Moon/Micolash changed unrelated Mensis event {event}")
    for event in (12601850, 12601852, 12601854, 12601855, 12604855, 12604860, 12604861):
        if output[event] != arena[event]:
            raise ValueError(
                "Moon/Micolash changed Micolash terminal, rewards, or shared Wet progression"
            )
    copied = "\n".join(output[x] for x in (12604852, 12604854, *ids.events()))
    if re.search(r"(?<!\d)(?:121|210)\d+(?!\d)", copied):
        raise ValueError("Moon/Micolash retains donor-map literals")
    return result


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, talk: int
) -> Slot:
    found = [x for x in slots if x.entity_id == entity and x.archetype == archetype]
    if len(found) != 1 or found[0].dummy or found[0].talk_id != talk:
        raise ValueError(f"Moon/Micolash requires pinned actor {entity}")
    return found[0]


def native_plan_moon_at_micolash(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: MoonMicolashIds = DEFAULT_IDS,
) -> dict:
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    _verify(event_blocks(arena), ARENA_HASHES, "Micolash arena")
    _verify(event_blocks(donor), MOON_HASHES, "Moon Presence donor")
    _validate(ids, arena)
    source = _require(slots, MOON, MOON_ARCHETYPE, 0)
    target = _require(slots, MICOLASH, MICOLASH_ARCHETYPE, 260311)
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        source.archetype,
        warnings=[
            "experimental Moon Presence-at-Micolash contract; runtime direct-combat behavior requires validation"
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
        raise ValueError("Moon/Micolash primary normalization is ambiguous")
    binding = {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": MOON_PIN,
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "destination_talk_id_override": 0,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
            "destination_talk_id_override",
        ],
    }
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "micolash<-moon-presence"},
        "primary_init_source_bindings": [binding],
        "boss_contract": {
            "format": "bb-moon-micolash-contract-v1",
            "arena": "micolash",
            "donor": "moon-presence",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "preserved_destination_events": [
                12601850,
                12601852,
                12601854,
                12601855,
                12604855,
                12604860,
                12604861,
            ],
            "terminal_policy": "retain byte-identical Micolash terminal; bridge writes talk-owned 72600301 only after donor death",
            "disabled_destination_chase_events": list(CHASE_EVENTS),
            "source_hash_pins": dict(MOON_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
