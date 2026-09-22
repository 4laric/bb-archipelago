"""Pinned full Celestial Emissary combat in Rom's Byrgenwerth arena.

Rom's terminal, blood-moon progression, fog and player-fall controllers remain
destination-owned. Celestial Emissary's small/giant/wave/support graph is
materialized through the reviewed native addition schema; Rom's spider and
teleport controllers are inert. Runtime arena geometry remains unobserved.
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
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from . import celestial_paarl_contract as ce
from .ebrietas_rom_contract import (
    ARENA_HASHES,
    ROM_ARCHETYPE,
    ROM_SOURCE,
    ROM_STATES,
    ROM_CORE_PINS,
    ROM_SPIDER_PINS,
    SPIDER_ARCHETYPE,
)
from .rom_ebrietas_contract import DONOR_ALTERNATES as ROM_ALTERNATES

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
CE_SOURCE = ce.CE_SOURCE
SOURCE_STATES = ce.SOURCE_STATES
PRIMARY = 3200800
PROJECT_MIN, PROJECT_MAX = 12994300, 12994399
GIANT = 982000
WAVES = tuple(range(982001, 982008))
SUPPORT = (982008, 982009)
HELPERS = (GIANT, *WAVES, *SUPPORT)
REGION_ENTITIES = tuple(range(982010, 982021))
GENERATOR_ENTITIES = tuple(range(982021, 982028))
GENERATOR_EVENT_IDS = tuple(range(982028, 982035))


@dataclass(frozen=True)
class CelestialRomIds:
    generator_cleanup: int = 12994300
    giant_command: int = 12994301
    giant_ai: int = 12994302
    giant_home: int = 12994303
    giant_phase: int = 12994304
    support_warp: int = 12994305
    support_phase: int = 12994306
    giant_choreography: int = 12994307
    giant_death_bridge: int = 12994308
    wave_home: int = 12994309
    lifecycle_cleanup: int = 12994310
    music_flag: int = 12994390
    evidence: str = "Celestial/Rom allocation v1; original EMEVD and MSBB corpus scan"

    def events(self) -> tuple[int, ...]:
        return (
            self.generator_cleanup,
            self.giant_command,
            self.giant_ai,
            self.giant_home,
            self.giant_phase,
            self.support_warp,
            self.support_phase,
            self.giant_choreography,
            self.giant_death_bridge,
            self.wave_home,
            self.lifecycle_cleanup,
        )


DEFAULT_IDS = CelestialRomIds()


# Exact source-to-reviewed-destination identity translation.  This is applied
# only after the donor helpers validate their own source closure.
def _translate(ids: CelestialRomIds) -> dict[int, int]:
    m = {
        2300810: PRIMARY,
        980600: GIANT,
        12301700: 13201800,
        12301702: 13201802,
        12301703: 13201803,
        12304700: 13204800,
        12304701: 13204801,
        12304702: 13204802,
        12304703: 13204803,
        12304704: 13204804,
        2303812: 3203802,
        2303813: 3203803,
        2300010: 3200010,
        2302812: 3202801,
        2302811: 3202801,
        12992790: ids.music_flag,
        12992700: ids.generator_cleanup,
        12992701: ids.giant_command,
        12992702: ids.giant_ai,
        12992703: ids.giant_home,
        12992704: ids.giant_phase,
        12992705: ids.support_warp,
        12992706: ids.support_phase,
        12992707: ids.giant_choreography,
        12992708: ids.giant_death_bridge,
        12992709: ids.wave_home,
        12992710: ids.lifecycle_cleanup,
    }
    m.update({980600 + i: 982000 + i for i in range(28)})
    return m


def _remap(text: str, m: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda x: str(m.get(int(x[0]), int(x[0]))), text
    )


def _verify(
    text: str, pins: Mapping[int, str], role: str, alts: Mapping[int, str] | None = None
) -> dict[int, str]:
    b = event_blocks(text)
    for e, d in pins.items():
        actual = hashlib.sha256(b.get(e, "").encode()).hexdigest()
        allowed = {d} | ({alts[e]} if alts and e in alts else set())
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {e}")
    return b


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Celestial/Rom expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for e in reversed(parse_events(source)):
        if e.event_id in edits:
            lines[e.first_line - 1 : e.last_line] = edits[e.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _end(block: str) -> str:
    return ce._end_event(block)


@cache
def _original_literals() -> set[int]:
    values = {
        int(x)
        for b in read_prefix(BUNDLE, "event/").values()
        for x in re.findall(r"(?<![\w])-?\d+(?![\w])", b.decode("utf-8-sig"))
    }
    # Native additions collide with Part, Region, Generator and Event IDs, not
    # merely EMEVD literals.  Scan every numeric mined-MSBB field as the
    # committed plan's reproducible original-data boundary.
    for body in read_prefix(BUNDLE, "mined/").values():
        values.update(
            int(x)
            for x in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return values


def _validate(ids: CelestialRomIds, destination: str) -> None:
    events = ids.events()
    project = (*events, ids.music_flag)
    helpers = (*HELPERS, *REGION_ENTITIES, *GENERATOR_ENTITIES, *GENERATOR_EVENT_IDS)
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    original = _original_literals()
    if (
        len(project) != len(set(project))
        or any(not PROJECT_MIN <= x <= PROJECT_MAX for x in project)
        or len(helpers) != len(set(helpers))
        or any(not 982000 <= x <= 982099 for x in helpers)
        or set(project).intersection(original | local)
        or set(helpers).intersection(original | local | set(project))
        or not ids.evidence.strip()
    ):
        raise ValueError(
            "Celestial/Rom allocation collides with original 129943xx/982000-range values"
        )


def _bridge(ids: CelestialRomIds) -> str:
    return f"""$Event({ids.giant_death_bridge}, Default, function() {{
    EndIf(EventFlag(13201800));
    WaitFor(CharacterDead({GIANT}));
    EndIf(EventFlag(13201800));
    ForceCharacterDeath({PRIMARY}, false);
}});"""


def _cleanup(ids: CelestialRomIds) -> str:
    spiders = "".join(
        f"    SetCharacterAIState({3200200+i}, Disabled);\n    ChangeCharacterEnableState({3200200+i}, Disabled);\n"
        for i in range(30)
    )
    gens = "".join(
        f"    DeactivateGenerator({x}, Disabled);\n" for x in GENERATOR_ENTITIES
    )
    actors = "".join(
        f"    SetCharacterImmortality({x}, Disabled);\n    SetCharacterAIState({x}, Disabled);\n    ChangeCharacterEnableState({x}, Disabled);\n    ForceCharacterDeath({x}, false);\n"
        for x in HELPERS
    )
    return (
        f"""$Event({ids.lifecycle_cleanup}, Default, function() {{
{spiders}    WaitFor(EventFlag(13201800));
{gens}{actors}"""
        + "".join(f"    ForceCharacterDeath({3200200+i}, false);\n" for i in range(30))
        + "});"
    )


def patch_celestial_emissary_at_rom(
    destination: str, donor_source: str, ids: CelestialRomIds = DEFAULT_IDS
) -> str:
    arena = _verify(destination, ARENA_HASHES, "Rom arena", ROM_ALTERNATES)
    donor = ce._verify(donor_source, ce.SOURCE_HASHES, "Celestial donor")
    _validate(ids, destination)
    # Reuse the reviewed donor-only conversion first, then translate every
    # resulting destination operand into the independently pinned Rom arena.
    base = ce.DEFAULT_IDS
    t = _translate(ids)
    cm = ce._mapping(base)
    transplant = (
        (ids.generator_cleanup, 12424770, 8),
        (ids.giant_command, 12424780, 1),
        (ids.giant_ai, 12424784, 1),
        (ids.giant_home, 12424785, 2),
        (ids.wave_home, 12424787, 2),
        (ids.giant_phase, 12424790, 1),
        (ids.support_warp, 12424791, 1),
        (ids.support_phase, 12424792, 2),
        (ids.giant_choreography, 12424795, 1),
    )
    initializers = []
    for dest, src, count in transplant:
        rows = ce._calls(donor[0], src, dest, count)
        initializers.extend(_remap(ce._remap(x, cm), t) for x in rows)
    initializers += [
        f"    $InitializeEvent(0, {ids.giant_death_bridge});",
        f"    $InitializeEvent(0, {ids.lifecycle_cleanup});",
    ]
    activation = _remap(ce._activation(donor[12421702], base), t)
    health = _remap(ce._health(donor[12424702], base), t)
    music = _remap(ce._music(donor[12424703], base), t)
    camera = _remap(ce._camera(donor[12424704], base), t).replace(
        "SetLockcamSlotNumber(23, 0,", "SetLockcamSlotNumber(32, 0,"
    )
    anchor = "    $InitializeEvent(0, 13204810);"
    constructor = _replace_once(
        arena[0],
        anchor,
        anchor + "\n" + "\n".join(initializers),
        "Rom constructor anchor",
    )
    edits = {
        0: constructor,
        13201802: activation,
        13204802: health,
        13204803: music,
        13204804: camera,
        13204000: _end(arena[13204000]),
        13204050: _end(arena[13204050]),
        13204730: _end(arena[13204730]),
        13204807: _end(arena[13204807]),
        13204808: _end(arena[13204808]),
        13204809: _end(arena[13204809]),
        13204810: _end(arena[13204810]),
    }
    for dest, src, _ in transplant:
        edits[dest] = _remap(ce._remap(donor[src], cm), t)
    edits[ids.giant_death_bridge] = _bridge(ids)
    edits[ids.lifecycle_cleanup] = _cleanup(ids)
    out = (
        _replace_events(
            destination, {k: v for k, v in edits.items() if k in arena}
        ).rstrip()
        + "\n\n"
        + "\n\n".join(edits[x] for x in ids.events())
        + "\n"
    )
    blocks = event_blocks(out)
    if set(blocks) != set(arena).union(ids.events()):
        raise ValueError("Celestial/Rom changed event identities")
    for e, b in arena.items():
        if e not in edits and blocks[e] != b:
            raise ValueError(f"Celestial/Rom changed unrelated Rom event {e}")
    for e in (
        13201800,
        13201801,
        13201803,
        13201804,
        13204805,
        13204820,
        13204821,
        13204830,
        13204831,
        13204832,
        13204833,
        13204834,
    ):
        if blocks[e] != arena[e]:
            raise ValueError(
                "Celestial/Rom changed Rom terminal or blood-moon progression"
            )
    if (
        blocks[13204803].count("InArea(10000, 3202801)") != 2
        or "InArea(10000, 3202812)" in blocks[13204803]
    ):
        raise ValueError("Celestial/Rom music must use the original Rom combat region")
    copied = "\n".join(
        blocks[e] for e in (13201802, 13204802, 13204803, 13204804, *ids.events())
    )
    if re.search(r"(?<!\d)(?:124\d{5}|242\d{4}|270\d{4}|280\d{4})(?!\d)", copied):
        raise ValueError("Celestial/Rom copied combat retains donor-map literals")
    return out


def _require(
    slots: Sequence[Slot], entity: int, arch: Archetype, map_name: str
) -> Slot:
    r = [
        x
        for x in slots
        if x.entity_id == entity and x.archetype == arch and x.map_name == map_name
    ]
    if len(r) != 1 or r[0].dummy or r[0].talk_id:
        raise ValueError(
            f"Celestial/Rom placement provenance missing {entity} in {map_name}"
        )
    return r[0]


def native_plan_celestial_at_rom(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: CelestialRomIds = DEFAULT_IDS,
) -> dict:
    donor = read_blob(BUNDLE, CE_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, ROM_SOURCE).decode("utf-8-sig")
    ce._verify(donor, ce.SOURCE_HASHES, "Celestial donor")
    _verify(arena, ARENA_HASHES, "Rom arena", ROM_ALTERNATES)
    _validate(ids, arena)
    sources = [
        _require(slots, ce.SOURCE_PRIMARY, ce.PRIMARY_ARCHETYPE, s)
        for s in SOURCE_STATES
    ]
    targets = [_require(slots, PRIMARY, ROM_ARCHETYPE, s) for s in ROM_STATES]
    spiders = {
        state: [
            _require(slots, 3200200 + index, SPIDER_ARCHETYPE, state)
            for index in range(30)
        ]
        for state in ROM_STATES
    }
    swap = Swap(
        targets[0].logical_key,
        [x.key for x in targets],
        {x.key: x.archetype for x in targets},
        ROM_ARCHETYPE,
        ce.PRIMARY_ARCHETYPE,
        warnings=[
            "experimental Celestial Emissary-at-Rom contract; runtime geometry and generated-wave behavior unobserved"
        ],
        destinations={
            x.key: {
                "map_name": x.map_name,
                "entity_id": x.entity_id,
                "x": x.x,
                "y": x.y,
                "z": x.z,
            }
            for x in targets
        },
    )
    changes, skips = plan_scaling(
        [swap], targets, dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Celestial/Rom primary normalization is ambiguous")
    # Start from the reviewed full donor plan, then replace only independently
    # witnessed destination-map anchors and allocations.
    additions = []
    regions = []
    generators = []
    bindings = []
    for index, state in enumerate(ROM_STATES):
        src = SOURCE_STATES[index]
        target = targets[index]
        src_anchor = sources[index]
        bindings.append(
            {
                "source_map": src,
                "source_part": src_anchor.part_name,
                "source_entity_id": ce.SOURCE_PRIMARY,
                "source_archetype": asdict(ce.PRIMARY_ARCHETYPE),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": ce.ACTOR_PINS[src][0],
                },
                "source_initialization": {
                    "talk_id": 0,
                    "unk_t18": -1,
                    "init_anim_id": -1,
                    "damage_anim_id": -1,
                },
                "destination_map": state,
                "destination_part": target.part_name,
                "destination_entity_id": PRIMARY,
                "destination_original_talk_id": target.talk_id,
            }
        )
        for n, (source_entity, source_part, _, dest_part, arch) in enumerate(
            ce.SOURCE_ACTORS, 1
        ):
            additions.append(
                {
                    "source_map": src,
                    "source_part": source_part,
                    "source_anchor_part": src_anchor.part_name,
                    "source_entity_id": source_entity,
                    "source_archetype": asdict(arch),
                    "source_part_kind": "enemy",
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": ce.ACTOR_PINS[src][n],
                        "anchor_sha256": ce.ACTOR_PINS[src][0],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "destination_map": state,
                    "destination_anchor_part": target.part_name,
                    "destination_part": dest_part,
                    "destination_entity_id": HELPERS[n - 1],
                    "allocation_evidence": ids.evidence,
                }
            )
        for n, (name, entity, dest_name) in enumerate(ce.REGION_SPECS):
            regions.append(
                {
                    "source_map": src,
                    "source_region": name,
                    "source_entity_id": entity,
                    "source_provenance": {
                        "format": "bb-boss-region-pin-v1",
                        "region_sha256": ce.REGION_PINS[src][n],
                    },
                    "source_anchor_part": src_anchor.part_name,
                    "source_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": ce.ACTOR_PINS[src][0],
                    },
                    "destination_map": state,
                    "destination_region": dest_name,
                    "destination_entity_id": REGION_ENTITIES[n],
                    "destination_anchor_part": target.part_name,
                    "destination_anchor_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": ROM_CORE_PINS[state],
                    },
                }
            )
        for n, (name, event, entity, part) in enumerate(ce.GENERATOR_SPECS):
            generators.append(
                {
                    "source_map": src,
                    "source_event": name,
                    "source_event_id": event,
                    "source_entity_id": entity,
                    "source_fingerprint": ce.GENERATOR_PINS[src][n],
                    "destination_map": state,
                    "destination_event": f"ap_ce_generator_{n+1}",
                    "destination_event_id": GENERATOR_EVENT_IDS[n],
                    "destination_entity_id": GENERATOR_ENTITIES[n],
                    "destination_part_name": None,
                    "destination_region_name": None,
                    "spawn_part_map": {part: ce.SOURCE_ACTORS[n + 1][3]},
                    "spawn_point_map": {name: ce.REGION_SPECS[n][2]},
                }
            )
    retained_spiders = [
        {
            "map": state,
            "part": row.part_name,
            "entity_id": row.entity_id,
            "archetype": asdict(row.archetype),
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": ROM_SPIDER_PINS[state][index],
            },
            "source_initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": "disable before Celestial combat and force-kill after destination completion",
        }
        for state in ROM_STATES
        for index, row in enumerate(spiders[state])
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "rom<-celestial-emissary"},
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "primary_init_source_bindings": bindings,
        "boss_contract": {
            "format": "bb-celestial-rom-contract-v1",
            "arena": "rom",
            "donor": "celestial-emissary",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(ce.SOURCE_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                13201800,
                13201801,
                13201803,
                13201804,
                13204805,
                13204820,
                13204821,
                13204830,
                13204831,
                13204832,
                13204833,
                13204834,
            ],
            "retired_destination_controllers": [
                13204000,
                13204050,
                13204730,
                13204807,
                13204808,
                13204809,
                13204810,
            ],
            "retained_destination_helpers": retained_spiders,
            "geometry_risk": "source flower-field regions are anchor-relative; their fit in the lake arena is static-only/unobserved",
            "destination_operand_policy": {
                "source_entry_region": 2422815,
                "source_music_region": 2422812,
                "destination_region": 3202801,
                "evidence": "original m32 event13204803 uses InArea(10000,3202801) to gate Rom boss music; both donor combat-area operands deliberately map to that existing destination combat region",
            },
        },
        "boss_actor_scaling_requirements": [
            {
                "destination_map": x["destination_map"],
                "destination_part": x["destination_part"],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": x["source_archetype"]["npc_param_id"],
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for x in additions
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
