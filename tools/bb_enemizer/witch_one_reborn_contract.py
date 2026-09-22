"""Source-pinned Witch of Hemwick pair combat in the One Reborn arena.

The One Reborn's original proxy terminal, rewards, cutscene entry, fog, and
shared-map content remain local.  The two Witches, three minions, twenty
regions, three generators, and complete source combat controller closure are
transplanted into both destination map states.  Placement keeps source
anchor-relative geometry; runtime arena fit remains unobserved.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob

from . import rom_one_reborn_contract as one
from . import witch_amygdala_contract as witch
from .boss_canary import event_blocks
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = witch.BUNDLE
WITCH_SOURCE = witch.WITCH_SOURCE
ARENA_SOURCE = one.ARENA_SOURCE
STATES = one.STATES
PRIMARY, PROXY = one.PRIMARY, one.PROXY
PROJECT_MIN, PROJECT_MAX = 12994500, 12994599
HELPER_MIN, HELPER_MAX = 982200, 982299


@dataclass(frozen=True)
class WitchOneRebornIds:
    phase: int = 12994500
    visibility: int = 12994501
    second_start: int = 12994502
    patrol: int = 12994503
    revival: int = 12994504
    warp_select: int = 12994505
    warp: int = 12994506
    post_warp: int = 12994507
    minion_count: int = 12994508
    minion_watch: int = 12994509
    summon: int = 12994510
    generator_manager: int = 12994511
    summon_one: int = 12994512
    summon_two: int = 12994513
    summon_three: int = 12994514
    minion_setup: int = 12994515
    insight: int = 12994516
    terminal_bridge: int = 12994517
    second_entity: int = 982200
    minion_first_entity: int = 982201
    warp_first_entity: int = 982210
    spawn_first_entity: int = 982220
    generator_event_first: int = 982240
    generator_entity_first: int = 982243
    visibility_flag_first: int = 12994540
    warp_flag_first: int = 12994542
    minion_status_first: int = 12994553
    generator_state_first: int = 12994556
    summon_permission_first: int = 12994558
    source_second_started_flag: int = 12994560
    insight_flag: int = 12994561
    shutdown_flag: int = 12994562
    minion_count_flag: int = 12994580

    def events(self) -> tuple[int, ...]:
        return (
            self.phase,
            self.visibility,
            self.second_start,
            self.patrol,
            self.revival,
            self.warp_select,
            self.warp,
            self.post_warp,
            self.minion_count,
            self.minion_watch,
            self.summon,
            self.generator_manager,
            self.summon_one,
            self.summon_two,
            self.summon_three,
            self.minion_setup,
            self.insight,
            self.terminal_bridge,
        )

    def project_ids(self) -> tuple[int, ...]:
        return self.events() + (
            self.visibility_flag_first,
            self.visibility_flag_first + 1,
            *(self.warp_flag_first + offset for offset in range(10)),
            *(self.minion_status_first + offset for offset in range(3)),
            self.generator_state_first,
            self.generator_state_first + 1,
            *(self.summon_permission_first + offset for offset in range(2)),
            self.source_second_started_flag,
            self.insight_flag,
            self.shutdown_flag,
            *(self.minion_count_flag + offset for offset in range(10)),
        )

    def helper_ids(self) -> tuple[int, ...]:
        return (
            self.second_entity,
            *(self.minion_first_entity + offset for offset in range(3)),
            *(self.warp_first_entity + offset for offset in range(8)),
            *(self.spawn_first_entity + offset for offset in range(12)),
            *(self.generator_event_first + offset for offset in range(3)),
            *(self.generator_entity_first + offset for offset in range(3)),
        )


DEFAULT_IDS = WitchOneRebornIds()


def _validate_ids(ids: WitchOneRebornIds, destination: str) -> None:
    project, helpers = ids.project_ids(), ids.helper_ids()
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if (
        len(project) != len(set(project))
        or any(value not in range(PROJECT_MIN, PROJECT_MAX + 1) for value in project)
        or set(project) & (local | witch._all_original_literals())
    ):
        raise ValueError(
            "Witch/One Reborn IDs must be collision-free project-owned 129945xx values"
        )
    if (
        len(helpers) != len(set(helpers))
        or any(value not in range(HELPER_MIN, HELPER_MAX + 1) for value in helpers)
        or set(helpers) & (local | witch._all_original_literals() | set(project))
    ):
        raise ValueError(
            "Witch/One Reborn helper IDs must be collision-free reserved 9822xx values"
        )


def _mapping(ids: WitchOneRebornIds) -> dict[int, int]:
    values = {
        witch.WITCH: PRIMARY,
        witch.SECOND: ids.second_entity,
        **{witch.MINIONS[index]: ids.minion_first_entity + index for index in range(3)},
        12201800: 12801800,
        12201802: 12801802,
        12201804: 12801803,
        12204800: 12804800,
        12204801: 12804801,
        12204802: 12804802,
        12204803: 12804803,
        12204804: 12804804,
        12204807: ids.phase,
        12204808: ids.visibility,
        12204810: ids.second_start,
        12204811: ids.patrol,
        12204812: ids.revival,
        12204814: ids.warp_select,
        12204820: ids.warp,
        12204830: ids.post_warp,
        12204832: ids.minion_count,
        12204835: ids.minion_watch,
        12204838: ids.summon,
        12204839: ids.generator_manager,
        12204840: ids.summon_one,
        12204841: ids.summon_two,
        12204842: ids.summon_three,
        12204843: ids.minion_setup,
        12204844: ids.insight,
        12204848: ids.visibility_flag_first,
        12204849: ids.visibility_flag_first + 1,
        **{12204850 + index: ids.warp_flag_first + index for index in range(10)},
        12204860: ids.minion_count_flag,
        **{12204870 + index: ids.minion_status_first + index for index in range(3)},
        12204875: ids.generator_state_first,
        12204876: ids.generator_state_first + 1,
        12204880: ids.summon_permission_first,
        12204881: ids.summon_permission_first + 1,
        12201810: ids.source_second_started_flag,
        12204845: ids.insight_flag,
        2202800: 2802800,
        2202801: 2802801,
        2202805: 2802805,
        2203802: 2803802,
        2203803: 2803803,
        2200010: 2800010,
        **{2205000 + index: ids.generator_entity_first + index for index in range(3)},
    }
    values.update(
        {2202810 + index: ids.warp_first_entity + index for index in range(8)}
    )
    return values


def _copied_events(ids: WitchOneRebornIds) -> tuple[tuple[int, int, int], ...]:
    return (
        (12204807, ids.phase, 1),
        (12204808, ids.visibility, 2),
        (12204810, ids.second_start, 1),
        (12204811, ids.patrol, 1),
        (12204812, ids.revival, 2),
        (12204814, ids.warp_select, 2),
        (12204820, ids.warp, 8),
        (12204830, ids.post_warp, 2),
        (12204832, ids.minion_count, 3),
        (12204835, ids.minion_watch, 3),
        (12204838, ids.summon, 1),
        (12204839, ids.generator_manager, 1),
        (12204840, ids.summon_one, 1),
        (12204841, ids.summon_two, 1),
        (12204842, ids.summon_three, 1),
        (12204843, ids.minion_setup, 1),
        (12204844, ids.insight, 1),
    )


def _actor_cleanup(actors: Sequence[int]) -> str:
    return "\n".join(
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);"
        for entity in actors
    )


def _donor_cleanup(ids: WitchOneRebornIds) -> str:
    actor_cleanup = witch._irreversible_actor_cleanup(
        (ids.second_entity, *(ids.minion_first_entity + offset for offset in range(3)))
    )
    generator_cleanup = "\n".join(
        f"    DeactivateGenerator({ids.generator_entity_first + offset}, Disabled);"
        for offset in range(3)
    )
    return actor_cleanup + "\n" + generator_cleanup


def patch_witch_at_one_reborn(
    destination: str,
    donor_source: str,
    ids: WitchOneRebornIds = DEFAULT_IDS,
) -> str:
    """Patch the shared One Reborn EMEVD after native helpers are staged."""
    arena = witch._verify(destination, one.ARENA_HASHES, "One Reborn arena")
    donor = witch._verify(donor_source, witch.DONOR_HASHES, "Witch donor")
    _validate_ids(ids, destination)
    if set(ids.events()) & set(arena):
        raise ValueError("Witch/One Reborn added event ID collides with destination")

    mapping = _mapping(ids)
    health = witch._remap(donor[12204802], mapping)
    health = witch._replace_once(
        health, "CreatePlaylog(88);", "CreatePlaylog(238);", "destination playlog"
    )
    health = witch._replace_once(
        health,
        "StartTimeMeasurement(2800010, 104, Enabled);",
        "StartTimeMeasurement(2800010, 254, Enabled);",
        "destination time measurement",
    )
    music = witch._remap(donor[12204803], mapping)
    camera = witch._remap(donor[12204804], mapping)
    if camera.count("SetLockcamSlotNumber(22, 0,") != 1:
        raise ValueError("Witch/One Reborn expected one source lockcam binding")
    camera = camera.replace(
        "SetLockcamSlotNumber(22, 0,", "SetLockcamSlotNumber(28, 0,"
    )

    copied = _copied_events(ids)
    initializers = [
        row
        for source, _, count in copied
        for row in witch._initializers(donor[0], source, count, mapping)
    ]
    initializers.append(f"    $InitializeEvent(0, {ids.terminal_bridge});")
    constructor = witch._replace_once(
        arena[0],
        "    $InitializeEvent(0, 12804871);",
        "    $InitializeEvent(0, 12804871);\n" + "\n".join(initializers),
        "combat initializer anchor",
    )

    imported = {
        destination_event: witch._remap(donor[source_event], mapping)
        for source_event, destination_event, _ in copied
    }
    minions = tuple(ids.minion_first_entity + offset for offset in range(3))
    generators = tuple(ids.generator_entity_first + offset for offset in range(3))
    imported = {
        event: witch._guard_minion_reactivation(
            body, ids.shutdown_flag, minions, generators
        )
        for event, body in imported.items()
    }
    if (
        sum(
            body.count(f"EndIf(EventFlag({ids.shutdown_flag}));")
            for body in imported.values()
        )
        != 9
    ):
        raise ValueError("Witch/One Reborn minion reactivation guard drift")
    for event in (ids.minion_setup, ids.insight):
        header = imported[event].splitlines()[0]
        imported[event] = witch._replace_once(
            imported[event],
            header + "\n",
            header + "\n    EndIf(EventFlag(12801800));\n",
            "completed-load controller guard",
        )
    retained_cleanup = _actor_cleanup(one.RETAINED)
    donor_cleanup = _donor_cleanup(ids)
    bridge = f"""$Event({ids.terminal_bridge}, Default, function() {{
{retained_cleanup}
    if (EventFlag(12801800)) {{
{donor_cleanup}
        EndEvent();
    }}
L0:
    SetCharacterGravity({PROXY}, Disabled);
    SetCharacterInvincibility({PROXY}, Enabled);
    WaitFor(CharacterDead({PRIMARY}) && CharacterDead({ids.second_entity}));
    SetEventFlag({ids.shutdown_flag}, ON);
{donor_cleanup}
    SetCharacterInvincibility({PROXY}, Disabled);
    ForceCharacterDeath({PROXY}, false);
}});"""

    edits = {
        0: constructor,
        12804802: health,
        12804803: music,
        12804804: camera,
        **{event: witch._end(arena[event]) for event in one.RETIRED_EVENTS},
    }
    for event in (12801802, 12801803):
        edits[event] = witch._replace_once(
            arena[event],
            "    ChangeCharacterEnableState(2800801, Enabled);\n",
            "",
            "displaced second-body activation",
        )

    result = (
        witch._replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((*imported.values(), bridge))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.events()):
        raise ValueError("Witch/One Reborn patch changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Witch/One Reborn changed unrelated event {event}")
    for event in (
        12801800,
        12801801,
        12804805,
        12804880,
        12804881,
        12804882,
        12804883,
    ):
        if output[event] != arena[event]:
            raise ValueError(
                "Witch/One Reborn changed destination terminal, progression, fog, or shared-map flow"
            )
    transplanted = "\n".join(
        output[event] for event in (12804802, 12804803, 12804804, *ids.events())
    )
    if re.search(r"(?<!\d)(?:122|220)\d+(?!\d)", transplanted):
        raise ValueError("Witch/One Reborn retains foreign source-map dependency")
    return result


def _require_source(slots: Sequence[Slot], entity: int, archetype) -> Slot:
    rows = [
        row
        for row in slots
        if row.map_name == "m22_00_00_00"
        and row.entity_id == entity
        and row.archetype == archetype
    ]
    if len(rows) != 1 or rows[0].dummy or rows[0].talk_id:
        raise ValueError(f"Witch/One Reborn requires pinned source actor {entity}")
    return rows[0]


def _primary_binding(source: Slot, target: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": witch.WITCH_PINS[witch.WITCH],
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
    }


def _region_additions(
    target: Slot, target_pin: str, ids: WitchOneRebornIds
) -> list[dict]:
    rows = []
    for source_id, (source_name, fingerprint) in (
        *witch.WARP_REGION_PINS.items(),
        *witch.SPAWN_REGION_PINS.items(),
    ):
        is_warp = source_id in witch.WARP_REGION_PINS
        index = source_id - (2202810 if is_warp else 2205500)
        destination_id = (
            ids.warp_first_entity if is_warp else ids.spawn_first_entity
        ) + index
        rows.append(
            {
                "source_map": "m22_00_00_00",
                "source_region": source_name,
                "source_entity_id": source_id,
                "source_provenance": {
                    "format": "bb-boss-region-pin-v1",
                    "region_sha256": fingerprint,
                },
                "source_anchor_part": "c2100_0000",
                "source_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": witch.WITCH_PINS[witch.WITCH],
                },
                "destination_map": target.map_name,
                "destination_region": (
                    f"ap_witch_one_{'warp' if is_warp else 'spawn'}_{index:02d}"
                ),
                "destination_entity_id": destination_id,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": target_pin,
                },
            }
        )
    return rows


def _generator_additions(target: Slot, ids: WitchOneRebornIds) -> list[dict]:
    minion_names = {
        f"c2050_000{index}": f"ap_witch_one_minion_{index}" for index in range(3)
    }
    spawn_map = {
        name: f"ap_witch_one_spawn_{index:02d}"
        for index, (name, _) in enumerate(witch.SPAWN_REGION_PINS.values())
    }
    return [
        {
            "source_map": "m22_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity,
            "source_fingerprint": fingerprint,
            "destination_map": target.map_name,
            "destination_event": f"ap_witch_one_generator_{index}",
            "destination_event_id": ids.generator_event_first + index,
            "destination_entity_id": ids.generator_entity_first + index,
            "destination_part_name": target.collision_name,
            "destination_region_name": None,
            "spawn_part_map": {f"c2050_000{index}": minion_names[f"c2050_000{index}"]},
            "spawn_point_map": {
                name: spawn_map[name]
                for source_id in tuple(witch.SPAWN_REGION_PINS)[
                    index * 4 : (index + 1) * 4
                ]
                for name in [witch.SPAWN_REGION_PINS[source_id][0]]
            },
        }
        for index, (
            source_name,
            source_event_id,
            source_entity,
            fingerprint,
        ) in enumerate(witch.GENERATOR_PINS)
    ]


def native_plan_witch_at_one_reborn(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: WitchOneRebornIds = DEFAULT_IDS,
) -> dict:
    """Return the two-state native construction request."""
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
    witch._verify(arena, one.ARENA_HASHES, "One Reborn arena")
    witch._verify(donor, witch.DONOR_HASHES, "Witch donor")
    _validate_ids(ids, arena)

    primary = _require_source(slots, witch.WITCH, witch.WITCH_ARCHETYPE)
    second = _require_source(slots, witch.SECOND, witch.SECOND_ARCHETYPE)
    minions = [
        _require_source(slots, entity, witch.MINION_ARCHETYPE)
        for entity in witch.MINIONS
    ]
    targets = [
        row
        for row in slots
        if row.entity_id == PRIMARY
        and row.map_name in STATES
        and row.archetype == one.ARCHETYPE
    ]
    if {row.map_name for row in targets} != set(STATES) or len(targets) != 2:
        raise ValueError("Witch/One Reborn needs both destination map states")
    targets.sort(key=lambda row: row.map_name)
    if any(
        row.dummy or row.talk_id or row.collision_name != "h000100" for row in targets
    ):
        raise ValueError("Witch/One Reborn destination primary placement drift")

    by_identity = {(row.map_name, row.entity_id): row for row in slots}
    retained = []
    for state in STATES:
        for entity in (PRIMARY, *one.RETAINED):
            row = by_identity[state, entity]
            witness = one.ACTOR_WITNESSES[state][entity]
            if (
                row.part_name != witness["part"]
                or asdict(row.archetype) != witness["archetype"]
                or row.talk_id
            ):
                raise ValueError("Witch/One Reborn retained actor roster drift")
            if entity != PRIMARY:
                retained.append(
                    {
                        "map": state,
                        "part": row.part_name,
                        "entity_id": entity,
                        "archetype": asdict(row.archetype),
                        "source_provenance": {
                            "format": "bb-boss-actor-pin-v1",
                            "part_sha256": witness["sha256"],
                        },
                        "source_initialization": witness["initialization"],
                        "policy": "disabled; original proxy killed only after both Witches die",
                    }
                )

    swap = Swap(
        targets[0].logical_key,
        [row.key for row in targets],
        {row.key: row.archetype for row in targets},
        one.ARCHETYPE,
        witch.WITCH_ARCHETYPE,
        warnings=[
            "experimental Witch pair at One Reborn; anchor-relative arena fit is unobserved"
        ],
        destinations={
            row.key: {
                "map_name": row.map_name,
                "entity_id": row.entity_id,
                "x": row.x,
                "y": row.y,
                "z": row.z,
            }
            for row in targets
        },
    )
    changes, skips = plan_scaling(
        [swap], targets, dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Witch/One Reborn primary normalization is ambiguous")

    helper_sources = [
        (second, ids.second_entity, "ap_witch_one_second"),
        *[
            (
                minion,
                ids.minion_first_entity + index,
                f"ap_witch_one_minion_{index}",
            )
            for index, minion in enumerate(minions)
        ],
    ]
    additions, bindings, regions, generators = [], [], [], []
    for target in targets:
        target_pin = one.ACTOR_WITNESSES[target.map_name][PRIMARY]["sha256"]
        bindings.append(_primary_binding(primary, target))
        for helper, destination_entity, destination_part in helper_sources:
            additions.append(
                {
                    "source_map": helper.map_name,
                    "source_part": helper.part_name,
                    "source_anchor_part": primary.part_name,
                    "source_entity_id": helper.entity_id,
                    "source_archetype": asdict(helper.archetype),
                    "source_part_kind": "enemy",
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": witch.WITCH_PINS[helper.entity_id],
                        "anchor_sha256": witch.WITCH_PINS[witch.WITCH],
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "destination_map": target.map_name,
                    "destination_anchor_part": target.part_name,
                    "destination_part": destination_part,
                    "destination_entity_id": destination_entity,
                    "allocation_evidence": "reserved 9822xx; native writer checks Part/Region/Event collisions",
                }
            )
        regions.extend(_region_additions(target, target_pin, ids))
        generators.extend(_generator_additions(target, ids))

    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "one-reborn<-witch-of-hemwick"},
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_generator_additions": generators,
        "primary_init_source_bindings": bindings,
        "boss_actor_scaling_requirements": [
            {
                "destination_map": row["destination_map"],
                "destination_part": row["destination_part"],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": row["source_archetype"]["npc_param_id"],
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for row in additions
        ],
        "boss_contract": {
            "format": "bb-witch-one-reborn-contract-v1",
            "arena": "the-one-reborn",
            "donor": "witch-of-hemwick",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(witch.DONOR_HASHES),
            "arena_hash_pins": dict(one.ARENA_HASHES),
            "retained_destination_helpers": retained,
            "preserved_destination_events": [
                12801800,
                12801801,
                12804805,
                12804880,
                12804881,
                12804882,
                12804883,
            ],
            "terminal_policy": (
                "original One Reborn proxy terminal remains byte-identical; bridge "
                "kills proxy only after both source-controlled Witches are dead"
            ),
            "geometry_policy": (
                "source-pinned Witch actors, warp regions, spawn regions, and generators "
                "retain rigid anchor-relative placement in each One Reborn map state"
            ),
            "native_requirements": {
                "actor_additions": 8,
                "region_additions": 40,
                "generator_additions": 6,
                "generator_collision": (
                    "source h000013 maps to source-witnessed destination primary collision h000100"
                ),
                "destination_anchors": [
                    {
                        "map": target.map_name,
                        "part": target.part_name,
                        "part_sha256": one.ACTOR_WITNESSES[target.map_name][PRIMARY][
                            "sha256"
                        ],
                        "collision_name": target.collision_name,
                    }
                    for target in targets
                ],
            },
            "event_patch": {
                "changed_events": [
                    12801802,
                    12801803,
                    12804802,
                    12804803,
                    12804804,
                    *one.RETIRED_EVENTS,
                ],
                "added_events": list(ids.events()),
                "source_event_remap": _mapping(ids),
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
