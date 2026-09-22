"""Source-pinned Shadows of Yharnam combat in Celestial Emissary's arena."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .amygdala_celestial_emissary_contract import (
    ARENA_HASHES,
    CELESTIAL_SOURCE,
    EBRIETAS_EVENTS,
    EBRIETAS_HASHES,
    GENERATORS as CE_GENERATORS,
    GIANT,
    GIANT_ARCHETYPE,
    PRIMARY,
    PRIMARY_ARCHETYPE,
    RETAINED_PINS,
    SUPPORT,
    SUPPRESSED_EVENTS,
    TERMINAL,
    WAVES,
)
from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from .shadows_orphan_contract import (
    ACTOR_PINS,
    ARCHETYPES,
    ATTACHMENTS,
    DONOR_ALTERNATES,
    DONOR_HASHES,
    GENERATOR_PINS,
    REGION_PINS,
    SHADOWS,
    SHADOWS_SOURCE,
    SNAKES,
    SOURCE_ACTORS,
)

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
SOURCE_MAP = "m27_00_00_00"
DESTINATION_MAP = "m24_02_00_00"

HELPER_ENTITIES = tuple(range(982100, 982109))
HELPER_MAP = {SHADOWS[0]: PRIMARY, **dict(zip(SOURCE_ACTORS[1:], HELPER_ENTITIES))}
PART_MAP = {
    SHADOWS[0]: "ap_shadows_body_0",
    SHADOWS[1]: "ap_shadows_body_1",
    SHADOWS[2]: "ap_shadows_body_2",
    SNAKES[0]: "ap_shadows_snake_0",
    SNAKES[1]: "ap_shadows_snake_1",
    SNAKES[2]: "ap_shadows_snake_2",
    ATTACHMENTS[0]: "ap_shadows_attachment_0",
    ATTACHMENTS[1]: "ap_shadows_attachment_1",
    ATTACHMENTS[2]: "ap_shadows_attachment_3",
    ATTACHMENTS[3]: "ap_shadows_attachment_4",
}


@dataclass(frozen=True)
class ShadowsCelestialIds:
    group_phase: int = 12994400
    summon: int = 12994401
    distance_pair: int = 12994402
    distance_all: int = 12994403
    body_phase: int = 12994404
    attachment: int = 12994405
    effect: int = 12994406
    summon_cleanup: int = 12994407
    bridge: int = 12994408
    destination_cleanup: int = 12994409
    phase_signal: int = 12994420
    generator_event_first: int = 12994460
    generator_entity_first: int = 982130
    region_entity_first: int = 982140

    def event_map(self) -> dict[int, int]:
        return {
            12704806: self.group_phase,
            12704807: self.summon,
            12704810: self.distance_pair,
            12704811: self.distance_all,
            12704812: self.body_phase,
            12704815: self.attachment,
            12704825: self.effect,
            12704830: self.summon_cleanup,
        }

    def project_events(self) -> tuple[int, ...]:
        return (*self.event_map().values(), self.bridge, self.destination_cleanup)

    def project_ids(self) -> tuple[int, ...]:
        return (*self.project_events(), self.phase_signal)


DEFAULT_IDS = ShadowsCelestialIds()


def _verify(
    text: str,
    pins: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        allowed = {digest}
        if event in (alternates or {}):
            allowed.add((alternates or {})[event])
        if hashlib.sha256(blocks.get(event, "").encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Shadows/Celestial expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _end_event(block: str) -> str:
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                item.strip()
                if item.strip().startswith("unused_")
                else "unused_" + item.strip()
            )
            for item in match[1].split(",")
            if item.strip()
        )
        + ")",
        block.splitlines()[0],
    )
    return header + "\n    EndEvent();\n});"


@cache
def _original_ids() -> set[int]:
    values = {
        int(value)
        for body in read_prefix(BUNDLE, "event/").values()
        for value in re.findall(rb"(?<![\w])-?\d+(?![\w])", body)
    }
    rows = read_prefix(BUNDLE, "mined/")["mined/msb_enemies.tsv"].decode("utf-8-sig")
    for row in rows.splitlines()[1:]:
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate_ids(ids: ShadowsCelestialIds, destination: str = "") -> None:
    events = ids.project_ids() + tuple(ids.generator_event_first + i for i in range(3))
    entities = (
        HELPER_ENTITIES
        + tuple(ids.generator_entity_first + i for i in range(3))
        + tuple(ids.region_entity_first + i for i in range(12))
    )
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    original = _original_ids()
    if (
        len(events) != len(set(events))
        or any(not 12994400 <= value <= 12994499 for value in events)
        or set(events) & (local | original)
    ):
        raise ValueError(
            "Shadows/Celestial event IDs must be collision-free 129944xx values"
        )
    if (
        len(entities) != len(set(entities))
        or any(not 982100 <= value <= 982199 for value in entities)
        or set(entities) & (local | original)
    ):
        raise ValueError(
            "Shadows/Celestial helper IDs must be collision-free 982100-982199 values"
        )


def _mapping(ids: ShadowsCelestialIds) -> dict[int, int]:
    return {
        **HELPER_MAP,
        2705001: ids.generator_entity_first,
        2705002: ids.generator_entity_first + 1,
        2705003: ids.generator_entity_first + 2,
        12701800: TERMINAL,
        12704800: 12424700,
        12704801: 12424701,
        12704802: 12424702,
        12704803: 12424703,
        12704804: 12424704,
        12704808: ids.phase_signal,
        2703802: 2423812,
        2703803: 2423813,
        2702802: 2422812,
        2700010: 2420010,
        27: 24,
        **ids.event_map(),
    }


def _initializer_rows(
    constructor: str, source_event: int, expected: int, values: Mapping[int, int]
) -> list[str]:
    rows = [
        line
        for line in constructor.splitlines()
        if re.search(rf"\$InitializeEvent\([^,]+,\s*{source_event}(?:,|\))", line)
    ]
    if len(rows) != expected:
        raise ValueError(
            f"Shadows Event(0) initializer witness drift for {source_event}"
        )
    return [_remap(row, values) for row in rows]


def _entry(client: bool = False) -> str:
    event = 12421703 if client else 12421702
    if client:
        gate = "    WaitFor(CharacterType(10000, TargetType.Alive) && EventFlag(12424700));\n    EndIf(HasMultiplayerState(MultiplayerState.Host));"
    else:
        gate = """    EndIf(EventFlag(12421700));
    EndIf(ThisEvent());
    ChangeCharacterEnableState(2420810, Disabled);
    ChangeCharacterEnableState(982100, Disabled);
    ChangeCharacterEnableState(982101, Disabled);
    WaitFor(
        !EventFlag(12421700)
            && !ThisEventSlot()
            && CharacterType(10000, TargetType.Alive)
            && InArea(10000, 2422815));"""
    return f"""$Event({event}, Default, function() {{
{gate}
    SetEventFlag(12424700, ON);
    SetEventFlag(12421702, ON);
    ChangeCharacterEnableState(2420810, Enabled);
    ChangeCharacterEnableState(982100, Enabled);
    ChangeCharacterEnableState(982101, Enabled);
}});"""


def patch_shadows_at_celestial_emissary(
    destination: str,
    donor_source: str,
    ids: ShadowsCelestialIds = DEFAULT_IDS,
) -> str:
    arena = _verify(destination, ARENA_HASHES, "Celestial arena")
    _verify(destination, EBRIETAS_HASHES, "shared Ebrietas")
    donor = _verify(donor_source, DONOR_HASHES, "Shadows donor", DONOR_ALTERNATES)
    _validate_ids(ids, destination)
    values = _mapping(ids)

    health = _remap(donor[12704802], values)
    health = _replace_once(
        health, "CreatePlaylog(82);", "CreatePlaylog(104);", "playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2420010, 98, Enabled);",
        "StartTimeMeasurement(2420010, 40, Enabled);",
        "time measurement",
    )
    music = _remap(donor[12704803], values)
    camera = _remap(donor[12704804], values)
    if camera.count("SetLockcamSlotNumber(24, 0,") != 2:
        raise ValueError("Shadows/Celestial source camera binding drift")
    camera = camera.replace(
        "SetLockcamSlotNumber(24, 0,", "SetLockcamSlotNumber(24, 2,"
    )

    counts = {
        12704806: 1,
        12704807: 3,
        12704812: 3,
        12704815: 4,
        12704825: 2,
        12704830: 3,
    }
    initializers = [
        row
        for event, count in counts.items()
        for row in _initializer_rows(donor[0], event, count, values)
    ]
    _initializer_rows(donor[0], 12704810, 0, values)
    _initializer_rows(donor[0], 12704811, 0, values)
    initializers.extend(
        (
            f"    $InitializeEvent(0, {ids.bridge});",
            f"    $InitializeEvent(0, {ids.destination_cleanup});",
        )
    )
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12424795);",
        "    $InitializeEvent(0, 12424795);\n" + "\n".join(initializers),
        "Celestial constructor anchor",
    )

    bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag({TERMINAL}));
    WaitFor(CharacterDead({PRIMARY}) && CharacterDead(982100) && CharacterDead(982101));
    SetCharacterInvincibility({GIANT}, Disabled);
    ForceCharacterDeath({GIANT}, false);
}});"""
    cleanup_actors = "\n".join(
        f"    ChangeCharacterEnableState({entity}, Disabled);\n    ForceCharacterDeath({entity}, false);"
        for entity in (*HELPER_ENTITIES, *WAVES, *SUPPORT)
    )
    cleanup = f"""$Event({ids.destination_cleanup}, Default, function() {{
    SetCharacterAIState({GIANT}, Disabled);
    SetCharacterInvincibility({GIANT}, Enabled);
    ChangeCharacterEnableState({GIANT}, Disabled);
{''.join(f'    DeactivateGenerator({entity}, Disabled);{chr(10)}' for entity in CE_GENERATORS)}{''.join(f'    SetCharacterAIState({entity}, Disabled);{chr(10)}    ChangeCharacterEnableState({entity}, Disabled);{chr(10)}' for entity in (*WAVES, *SUPPORT))}    WaitFor(EventFlag({TERMINAL}));
{cleanup_actors}
    DeactivateGenerator({ids.generator_entity_first}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 1}, Disabled);
    DeactivateGenerator({ids.generator_entity_first + 2}, Disabled);
    SetEventFlag({ids.phase_signal}, OFF);
}});"""
    copied = {new: _remap(donor[old], values) for old, new in ids.event_map().items()}
    edits = {
        0: constructor,
        12421702: _entry(False),
        12421703: _entry(True),
        12424702: health,
        12424703: music,
        12424704: camera,
        **{event: _end_event(arena[event]) for event in SUPPRESSED_EVENTS},
    }
    additions = (*copied.values(), bridge, cleanup)
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.project_events()):
        raise ValueError("Shadows/Celestial changed unexpected event identities")
    if output[TERMINAL] != arena[TERMINAL]:
        raise ValueError("Shadows/Celestial changed destination giant terminal")
    for event in (12421701, 12424705, 12424710, 12424711, *EBRIETAS_EVENTS):
        if output[event] != arena[event]:
            raise ValueError(
                f"Shadows/Celestial changed protected destination event {event}"
            )
    copied_text = "\n".join((health, music, camera, *additions))
    leftovers = sorted(set(re.findall(r"(?<!\d)(?:127|270)\d+(?!\d)", copied_text)))
    if leftovers:
        raise ValueError(
            f"Shadows/Celestial copied combat retains donor-map literals {leftovers}"
        )
    return result


def _pin(part_sha256: str, anchor_sha256: str | None = None) -> dict:
    result = {"format": "bb-boss-actor-pin-v1", "part_sha256": part_sha256}
    if anchor_sha256 is not None:
        result["anchor_sha256"] = anchor_sha256
    return result


def _initialization() -> dict:
    return {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}


def _require(
    slots: Sequence[Slot], entity: int, archetype: Archetype, map_name: str
) -> Slot:
    found = [
        slot for slot in slots if slot.entity_id == entity and slot.map_name == map_name
    ]
    if (
        len(found) != 1
        or found[0].dummy
        or found[0].talk_id
        or found[0].archetype != archetype
    ):
        raise ValueError(f"Shadows/Celestial requires pinned actor {map_name}:{entity}")
    return found[0]


def native_plan_shadows_at_celestial_emissary(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: ShadowsCelestialIds = DEFAULT_IDS,
) -> dict:
    donor_text = read_blob(BUNDLE, SHADOWS_SOURCE).decode("utf-8-sig")
    arena_text = read_blob(BUNDLE, CELESTIAL_SOURCE).decode("utf-8-sig")
    patch_shadows_at_celestial_emissary(arena_text, donor_text, ids)
    sources = {
        entity: _require(slots, entity, ARCHETYPES[entity], SOURCE_MAP)
        for entity in SOURCE_ACTORS
    }
    target = _require(slots, PRIMARY, PRIMARY_ARCHETYPE, DESTINATION_MAP)
    giant = _require(slots, GIANT, GIANT_ARCHETYPE, DESTINATION_MAP)
    destination_helpers = [
        _require(slots, entity, Archetype("c2500", 250081, 250061, 0), DESTINATION_MAP)
        for entity in WAVES
    ]
    destination_helpers.extend(
        _require(
            slots,
            entity,
            Archetype("c2571", 257100 + index, 1, 0),
            DESTINATION_MAP,
        )
        for index, entity in enumerate(SUPPORT)
    )
    primary = sources[SHADOWS[0]]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        primary.archetype,
        warnings=[
            "experimental Shadows-at-Celestial contract; runtime arena fit, formation geometry, attachments and snake summons are unobserved"
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
        raise ValueError("Shadows/Celestial primary normalization is ambiguous")

    additions = []
    for entity in SOURCE_ACTORS[1:]:
        row = sources[entity]
        additions.append(
            {
                "source_map": row.map_name,
                "source_part": row.part_name,
                "source_anchor_part": primary.part_name,
                "source_entity_id": entity,
                "source_archetype": asdict(row.archetype),
                "source_part_kind": "enemy",
                "source_provenance": _pin(ACTOR_PINS[entity], ACTOR_PINS[SHADOWS[0]]),
                "source_initialization": _initialization(),
                "destination_map": target.map_name,
                "destination_anchor_part": target.part_name,
                "destination_part": PART_MAP[entity],
                "destination_entity_id": HELPER_MAP[entity],
                "allocation_evidence": "project-reserved 982100-982199 helper range; native collision validation required",
            }
        )
    regions = [
        {
            "source_map": primary.map_name,
            "source_region": name,
            "source_entity_id": source_entity,
            "source_provenance": {
                "format": "bb-boss-region-pin-v1",
                "region_sha256": fingerprint,
            },
            "source_anchor_part": primary.part_name,
            "source_anchor_provenance": _pin(ACTOR_PINS[SHADOWS[0]]),
            "destination_map": target.map_name,
            "destination_region": f"ap_shadows_snake_spawn_{index:02d}",
            "destination_entity_id": ids.region_entity_first + index,
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": _pin(RETAINED_PINS[PRIMARY]),
        }
        for index, (name, source_entity, fingerprint) in enumerate(REGION_PINS)
    ]
    snake_parts = {
        "c5033_0003": PART_MAP[SNAKES[0]],
        "c5033_0000": PART_MAP[SNAKES[1]],
        "c5033_0001": PART_MAP[SNAKES[2]],
    }
    generators = []
    for index, (
        name,
        source_event_id,
        source_entity,
        fingerprint,
        snake_part,
    ) in enumerate(GENERATOR_PINS):
        generators.append(
            {
                "source_map": primary.map_name,
                "source_event": name,
                "source_event_id": source_event_id,
                "source_entity_id": source_entity,
                "source_fingerprint": fingerprint,
                "destination_map": target.map_name,
                "destination_event": f"ap_shadows_snake_generator_{index}",
                "destination_event_id": ids.generator_event_first + index,
                "destination_entity_id": ids.generator_entity_first + index,
                "destination_part_name": target.collision_name,
                "destination_region_name": None,
                "spawn_part_map": {snake_part: snake_parts[snake_part]},
                "spawn_point_map": {
                    REGION_PINS[index * 4 + offset][
                        0
                    ]: f"ap_shadows_snake_spawn_{index * 4 + offset:02d}"
                    for offset in range(4)
                },
            }
        )
    retained = []
    for row in (giant, *destination_helpers):
        retained.append(
            {
                "map": row.map_name,
                "part": row.part_name,
                "entity_id": row.entity_id,
                "archetype": asdict(row.archetype),
                "source_provenance": _pin(RETAINED_PINS[row.entity_id]),
                "source_initialization": _initialization(),
                "policy": (
                    "hidden alive until all three Shadows die, then killed by terminal bridge"
                    if row.entity_id == GIANT
                    else "disabled for the transplanted fight and cleaned after destination completion"
                ),
            }
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {
            "experimental_boss_contract": "celestial-emissary<-shadows-of-yharnam"
        },
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "primary_init_source_bindings": [
            {
                "source_map": primary.map_name,
                "source_part": primary.part_name,
                "source_entity_id": primary.entity_id,
                "source_archetype": asdict(primary.archetype),
                "source_talk_id": primary.talk_id,
                "source_provenance": _pin(ACTOR_PINS[SHADOWS[0]]),
                "source_initialization": _initialization(),
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
        ],
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": PART_MAP[entity],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": ARCHETYPES[entity].npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for entity in SOURCE_ACTORS[1:]
        ],
        "boss_contract": {
            "format": "bb-shadows-celestial-contract-v1",
            "arena": "celestial-emissary",
            "donor": "shadows-of-yharnam",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "source_hash_alternates": dict(DONOR_ALTERNATES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                TERMINAL,
                12421701,
                12424705,
                12424710,
                12424711,
            ],
            "preserved_ebrietas_events": list(EBRIETAS_EVENTS),
            "retained_destination_helpers": retained,
            "terminal_policy": "preserve byte-identical giant terminal; kill giant only after all three actual Shadow bodies die",
            "placement_anchor_policy": {
                "source_anchor_entity": SHADOWS[0],
                "destination_anchor_entity": PRIMARY,
                "policy": "place the source primary in the destination primary slot and preserve every helper/region offset relative to it",
                "risk": "unobserved arena bounds, floor projection, attachment behavior and snake spawn geometry",
            },
            "source_roster": {
                "combat_bodies": list(SHADOWS),
                "snake_bodies": list(SNAKES),
                "attachments": list(ATTACHMENTS),
                "generators": [2705001, 2705002, 2705003],
                "spawn_regions": [row[1] for row in REGION_PINS],
            },
            "native_requirements": {
                "actor_additions": 9,
                "region_additions": 12,
                "generator_additions": 3,
                "destination_collision": target.collision_name,
            },
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


def shadows_helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(result) != len(rows):
        raise ValueError("duplicate Shadows helper scaling destination")
    return result


helper_scaling_parents = shadows_helper_scaling_parents
