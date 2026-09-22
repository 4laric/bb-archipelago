"""Pinned Living Failures combat overlay for Lady Maria's arena.

Both encounters live in ``m35_00_00_00``.  The event adapter retains Maria's
terminal, cutscene, fog and progression while giving the six Living Failures
actors a separately allocated controller graph.  The native plan relocates
the source spawn regions, generators and MapSFX around Maria's pinned anchor.
Runtime arena fit remains unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob

from .boss_canary import event_blocks
from .living_failures_laurence_contract import (
    BODY_FOUR,
    BODY_FOUR_ARCHETYPE,
    BODY_ONE,
    BODY_ONE_ARCHETYPE,
    BODY_THREE,
    BODY_THREE_ARCHETYPE,
    BODY_TWO,
    BODY_TWO_ARCHETYPE,
    BUNDLE,
    DONOR_HASHES,
    DONOR_SOURCE,
    GENERATOR_PINS,
    PART_PINS,
    PROXY,
    PROXY_ARCHETYPE,
    REGION_PINS,
    SFX_PINS,
    SUPPORT,
    SUPPORT_ARCHETYPE,
    _calls,
    _end_event,
    _original_literals,
    _remap,
    _replace_events,
    _replace_once,
    _verify,
)
from .maria_contract import MARIA_PACKAGE, MARIA_PATCH_EXPECTED
from .model import Slot, Swap
from .scaling import plan_scaling

ARENA_SOURCE = "event/m35_00_00_00.emevd.dcx.js"
MARIA = 3500800
COMPLETION = 13501800
MARIA_PIN = "4c8e1f5185a8026aca281a0402ee06fe1c60c361043609b31f178b0b974ef906"
# Original m35 MSBB enemy c4520_0002 (entity 3500800) binds this collision.
MARIA_COLLISION = "h000060"

EVENT_MIN, EVENT_MAX = 12992400, 12992499
GENERATOR_ENTITY_IDS = (980405, 980406, 980407, 980408)
GENERATOR_EVENT_IDS = (980409, 980410, 980411, 980412)
SFX_ENTITY_IDS = (980413, 980414, 980415, 980416, 980417)
SFX_EVENT_IDS = (980418, 980419, 980420, 980421, 980422)
FFX_SHA256 = "fd656c4a23d3a45202e7d0a5aec1b4f3bea95f71d96af3d1b4b181bcf24b931e"


@dataclass(frozen=True)
class LivingFailuresMariaIds:
    player_effect: int = 12992400
    wave_selection: int = 12992401
    wave_commands: int = 12992402
    wave_animation: int = 12992403
    death_cleanup: int = 12992404
    generator_schedule: int = 12992405
    combat_tracker: int = 12992406
    combat_counter: int = 12992407
    generator_controller: int = 12992408
    support_controller: int = 12992409
    wave_reset: int = 12992410
    lifecycle_cleanup: int = 12992411
    phase_music_flag: int = 12992420
    generator_enable_flag: int = 12992421
    generator_phase_flag: int = 12992422
    wave_flags_start: int = 12992423
    wave_flags_end: int = 12992428
    scheduler_active_flag: int = 12992429
    combat_count_value: int = 12992430
    support_count_value: int = 12992433
    proxy_entity: int = 980400
    body_two_entity: int = 980401
    body_three_entity: int = 980402
    body_four_entity: int = 980403
    support_entity: int = 980404
    evidence: str = (
        "Living Failures/Maria allocation v1; full EMEVD and MSBB operand scan"
    )

    def event_values(self) -> tuple[int, ...]:
        return (
            self.player_effect,
            self.wave_selection,
            self.wave_commands,
            self.wave_animation,
            self.death_cleanup,
            self.generator_schedule,
            self.combat_tracker,
            self.combat_counter,
            self.generator_controller,
            self.support_controller,
            self.wave_reset,
            self.lifecycle_cleanup,
        )

    def added_entities(self) -> tuple[int, ...]:
        return (
            self.proxy_entity,
            self.body_two_entity,
            self.body_three_entity,
            self.body_four_entity,
            self.support_entity,
            *GENERATOR_ENTITY_IDS,
            *GENERATOR_EVENT_IDS,
            *SFX_ENTITY_IDS,
            *SFX_EVENT_IDS,
        )


DEFAULT_IDS = LivingFailuresMariaIds()


def _verify_maria(blocks: Mapping[int, str]) -> None:
    for event, digest in MARIA_PACKAGE.expected.items():
        allowed = {digest}
        if event in MARIA_PATCH_EXPECTED:
            allowed.add(MARIA_PATCH_EXPECTED[event])
        actual = blocks.get(event, "")
        if hashlib.sha256(actual.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original Maria arena event {event}")


def _validate_ids(ids: LivingFailuresMariaIds, destination: str = "") -> None:
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    events = ids.event_values()
    project_values = (
        *events,
        ids.phase_music_flag,
        ids.generator_enable_flag,
        ids.generator_phase_flag,
        *range(ids.wave_flags_start, ids.wave_flags_end + 1),
        ids.scheduler_active_flag,
        *range(ids.combat_count_value, ids.combat_count_value + 3),
        *range(ids.support_count_value, ids.support_count_value + 3),
    )
    values = (*project_values, *ids.added_entities())
    if (
        len(set(values)) != len(values)
        or any(not EVENT_MIN <= value <= EVENT_MAX for value in project_values)
        or any(value <= 0 for value in ids.added_entities())
        or set(values).intersection(local | _original_literals())
        or not ids.evidence.strip()
    ):
        raise ValueError(
            "Living Failures/Maria allocation collides with original operands or MSBB entities"
        )


def _mapping(ids: LivingFailuresMariaIds) -> dict[int, int]:
    return {
        PROXY: ids.proxy_entity,
        BODY_ONE: MARIA,
        BODY_TWO: ids.body_two_entity,
        BODY_THREE: ids.body_three_entity,
        BODY_FOUR: ids.body_four_entity,
        SUPPORT: ids.support_entity,
        13501850: COMPLETION,
        13504852: 13504802,
        13504853: 13504803,
        13504854: 13504804,
        13504858: 13504808,
        13504859: 13504809,
        13504860: 13504810,
        13504865: ids.player_effect,
        13504866: ids.generator_enable_flag,
        13504868: ids.generator_phase_flag,
        13504869: ids.scheduler_active_flag,
        13504870: ids.phase_music_flag,
        13504873: ids.wave_flags_start,
        13504874: ids.wave_flags_start + 1,
        13504875: ids.wave_flags_start + 2,
        13504876: ids.wave_flags_start + 3,
        13504877: ids.wave_flags_start + 4,
        13504878: ids.wave_flags_end,
        13504880: ids.wave_selection,
        13504881: ids.wave_commands,
        13504885: ids.wave_animation,
        13504890: ids.wave_reset,
        13504895: ids.death_cleanup,
        13505655: ids.generator_schedule,
        13505656: ids.combat_tracker,
        13505661: ids.combat_counter,
        13505662: ids.generator_controller,
        13505668: ids.generator_phase_flag,
        13505669: ids.scheduler_active_flag,
        13505680: ids.support_controller,
        13505690: ids.combat_count_value,
        13505694: ids.support_count_value,
        3502812: 3502802,
        3503812: 3503802,
        3503813: 3503803,
        3503814: GENERATOR_ENTITY_IDS[0],
        3503815: GENERATOR_ENTITY_IDS[1],
        3503816: GENERATOR_ENTITY_IDS[2],
        3503817: GENERATOR_ENTITY_IDS[3],
        3503850: SFX_ENTITY_IDS[0],
        3503851: SFX_ENTITY_IDS[1],
        3503852: SFX_ENTITY_IDS[2],
        3503853: SFX_ENTITY_IDS[3],
        3503854: SFX_ENTITY_IDS[4],
    }


def _constructor(arena_zero: str, donor_zero: str, ids: LivingFailuresMariaIds) -> str:
    groups = (
        (13504865, 1),
        (13504880, 1),
        (13504881, 1),
        (13504885, 2),
        (13504890, 4),
        (13504895, 4),
        (13505655, 1),
        (13505656, 4),
        (13505661, 1),
        (13505662, 1),
        (13505680, 1),
    )
    initializers = [
        _remap(line, _mapping(ids))
        for event, count in groups
        for line in _calls(donor_zero, event, count)
    ]
    initializers.append(f"    $InitializeEvent(0, {ids.lifecycle_cleanup});")
    anchor = "    $InitializeEvent(0, 13504822);"
    return _replace_once(
        arena_zero,
        anchor,
        anchor + "\n" + "\n".join(initializers),
        "Maria constructor insertion anchor",
    )


def _music(source: str, ids: LivingFailuresMariaIds) -> str:
    result = _remap(source, _mapping(ids))
    return _replace_once(
        result,
        f"    SetMapSoundState({GENERATOR_ENTITY_IDS[0]}, Disabled);\n",
        "",
        "Living Failures third music slot",
    )


def patch_living_failures_at_maria(
    destination: str,
    donor_source: str,
    ids: LivingFailuresMariaIds = DEFAULT_IDS,
) -> str:
    """Patch one selected m35 source while preserving Maria progression."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify_maria(arena)
    _verify(donor, DONOR_HASHES, "Living Failures donor")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)

    entry = _replace_once(
        arena[13501801],
        "    ChangeCharacterEnableState(3500800, Disabled);\n",
        "    ForceAnimationPlayback(3500800, 9000, true, false, false);\n"
        "    ChangeCharacterEnableState(3500800, Disabled);\n",
        "Living Failures pre-entry animation",
    )
    entry = _replace_once(
        entry,
        "    ChangeCharacterEnableState(3500800, Enabled);\n",
        "    ChangeCharacterEnableState(3500800, Enabled);\n"
        "    ForceAnimationPlayback(3500800, 9060, false, false, false);\n"
        "    RequestCharacterAIReplan(3500800);\n",
        "Living Failures wake animation",
    )
    donor_events = {
        ids.player_effect: 13504865,
        ids.wave_selection: 13504880,
        ids.wave_commands: 13504881,
        ids.wave_animation: 13504885,
        ids.death_cleanup: 13504895,
        ids.generator_schedule: 13505655,
        ids.combat_tracker: 13505656,
        ids.combat_counter: 13505661,
        ids.generator_controller: 13505662,
        ids.support_controller: 13505680,
        ids.wave_reset: 13504890,
    }
    cleanup = f"""$Event({ids.lifecycle_cleanup}, Default, function() {{
    WaitFor(EventFlag({COMPLETION}));
    ChangeCharacterEnableState({ids.proxy_entity}, Disabled);
    ForceCharacterDeath({ids.proxy_entity}, false);
    ChangeCharacterEnableState({ids.body_two_entity}, Disabled);
    ForceCharacterDeath({ids.body_two_entity}, false);
    ChangeCharacterEnableState({ids.body_three_entity}, Disabled);
    ForceCharacterDeath({ids.body_three_entity}, false);
    ChangeCharacterEnableState({ids.body_four_entity}, Disabled);
    ForceCharacterDeath({ids.body_four_entity}, false);
}});"""
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        13501801: entry,
        13504802: _remap(donor[13504852], mapping),
        13504803: _music(donor[13504853], ids),
        13504804: _remap(donor[13504854], mapping),
        13504822: _end_event(arena[13504822]),
        **{
            target: _remap(donor[source], mapping)
            for target, source in donor_events.items()
        },
        ids.lifecycle_cleanup: cleanup,
    }
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.event_values())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.event_values()):
        raise ValueError("Living Failures/Maria changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(
                f"Living Failures/Maria changed unrelated arena event {event}"
            )
    for event in (13501800, 13501807, 13504800, 13504801, 13504805):
        if output[event] != arena[event]:
            raise ValueError("Living Failures/Maria changed destination progression")
    donor_only = set(mapping).difference(mapping.values())
    copied = "\n".join(
        output[event] for event in (13504802, 13504803, 13504804, *ids.event_values())
    )
    retained = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", copied)))
    if retained.intersection(donor_only):
        raise ValueError("Living Failures/Maria copied combat retains donor literals")
    return result


def _require(slots: Sequence[Slot], entity: int, archetype, map_name: str) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and slot.map_name == map_name
    ]
    if len(found) != 1 or found[0].dummy:
        raise ValueError(
            f"Living Failures/Maria requires one pinned actor {entity} in {map_name}"
        )
    return found[0]


def _actor_addition(source: Slot, target: Slot, entity: int, part: str, ids) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_anchor_part": "c4030_0000",
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_part_kind": "enemy",
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": PART_PINS[source.entity_id],
            "anchor_sha256": PART_PINS[BODY_ONE],
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
        },
        "destination_map": target.map_name,
        "destination_anchor_part": target.part_name,
        "destination_part": part,
        "destination_entity_id": entity,
        "allocation_evidence": ids.evidence,
    }


def _regions(target: Slot) -> list[dict]:
    names = {
        "Event_ボス1_患者B_ジェネレートポイント1": "ap_lfm_spawn_1",
        "Event_ボス1_患者B_ジェネレートポイント2": "ap_lfm_spawn_2",
        "Event_ボス1_患者B_ジェネレートポイント3": "ap_lfm_spawn_3",
        "Event_ボス1_患者B_ジェネレートポイント4": "ap_lfm_spawn_4",
        "SFX_患者B宇宙作成": "ap_lfm_universe_sfx",
    }
    return [
        {
            "source_map": "m35_00_00_00",
            "source_region": source,
            "source_entity_id": -1,
            "source_provenance": {
                "format": "bb-boss-region-pin-v1",
                "region_sha256": REGION_PINS[source],
            },
            "source_anchor_part": "c4030_0000",
            "source_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": PART_PINS[BODY_ONE],
            },
            "destination_map": target.map_name,
            "destination_region": destination,
            "destination_entity_id": -1,
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": MARIA_PIN,
            },
        }
        for source, destination in names.items()
    ]


def _generators(target: Slot) -> list[dict]:
    parts = (
        target.part_name,
        "ap_lfm_body_two",
        "ap_lfm_body_three",
        "ap_lfm_body_four",
    )
    regions = ("ap_lfm_spawn_2", "ap_lfm_spawn_3", "ap_lfm_spawn_4", "ap_lfm_spawn_1")
    return [
        {
            "source_map": "m35_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity,
            "source_fingerprint": fingerprint,
            "destination_map": target.map_name,
            "destination_event": f"ap_lfm_generator_{index + 1}",
            "destination_event_id": GENERATOR_EVENT_IDS[index],
            "destination_entity_id": GENERATOR_ENTITY_IDS[index],
            "destination_part_name": MARIA_COLLISION,
            "destination_region_name": None,
            "spawn_part_map": {source_part: parts[index]},
            "spawn_point_map": {source_region: regions[index]},
        }
        for index, (
            source_entity,
            source_event_id,
            fingerprint,
            source_name,
            source_region,
            source_part,
        ) in enumerate(GENERATOR_PINS)
    ]


def _sfx(target: Slot) -> list[dict]:
    return [
        {
            "source_map": "m35_00_00_00",
            "source_event": source_name,
            "source_event_id": source_event_id,
            "source_entity_id": source_entity_id,
            "source_provenance": {
                "format": "bb-boss-sfx-pin-v1",
                "event_sha256": event_sha256,
            },
            "source_anchor_part": "c4030_0000",
            "source_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": PART_PINS[BODY_ONE],
            },
            "destination_map": target.map_name,
            "destination_event": f"ap_lfm_universe_sfx_{index + 1}",
            "destination_event_id": SFX_EVENT_IDS[index],
            "destination_entity_id": SFX_ENTITY_IDS[index],
            "destination_part_name": MARIA_COLLISION,
            "destination_region_name": "ap_lfm_universe_sfx",
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": MARIA_PIN,
            },
            "effect_id": effect_id,
            "start_disabled": False,
        }
        for index, (
            source_name,
            source_event_id,
            source_entity_id,
            effect_id,
            event_sha256,
        ) in enumerate(SFX_PINS)
    ]


def native_plan_living_failures_at_maria(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LivingFailuresMariaIds = DEFAULT_IDS,
) -> dict:
    arena = read_blob(BUNDLE, ARENA_SOURCE).decode("utf-8-sig")
    donor = read_blob(BUNDLE, DONOR_SOURCE).decode("utf-8-sig")
    _verify_maria(event_blocks(arena))
    _verify(event_blocks(donor), DONOR_HASHES, "Living Failures donor")
    _validate_ids(ids, arena)
    primary = _require(slots, BODY_ONE, BODY_ONE_ARCHETYPE, "m35_00_00_00")
    target = _require(slots, MARIA, MARIA_PACKAGE.archetype, "m35_00_00_00")
    helpers = (
        (
            _require(slots, PROXY, PROXY_ARCHETYPE, target.map_name),
            ids.proxy_entity,
            "ap_lfm_proxy",
        ),
        (
            _require(slots, BODY_TWO, BODY_TWO_ARCHETYPE, target.map_name),
            ids.body_two_entity,
            "ap_lfm_body_two",
        ),
        (
            _require(slots, BODY_THREE, BODY_THREE_ARCHETYPE, target.map_name),
            ids.body_three_entity,
            "ap_lfm_body_three",
        ),
        (
            _require(slots, BODY_FOUR, BODY_FOUR_ARCHETYPE, target.map_name),
            ids.body_four_entity,
            "ap_lfm_body_four",
        ),
        (
            _require(slots, SUPPORT, SUPPORT_ARCHETYPE, target.map_name),
            ids.support_entity,
            "ap_lfm_support",
        ),
    )
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        primary.archetype,
        warnings=["Living Failures-at-Maria has unobserved runtime arena fit"],
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
        raise ValueError("Living Failures/Maria primary normalization is ambiguous")
    additions = [
        _actor_addition(source, target, entity, part, ids)
        for source, entity, part in helpers
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_actor_additions": additions,
        "boss_region_additions": _regions(target),
        "boss_generator_additions": _generators(target),
        "boss_sfx_additions": _sfx(target),
        "boss_ffx_merges": [
            {
                "source_file": "frpg_sfxbnd_m35.ffxbnd.dcx",
                "source_sha256": FFX_SHA256,
                "destination_file": "frpg_sfxbnd_m35.ffxbnd.dcx",
                "destination_sha256": FFX_SHA256,
                "required_effect_ids": [640320, 640321, 640322, 640323, 640324],
                "policy": "preserve_destination_union_source_v1",
            }
        ],
        "primary_init_source_bindings": [
            {
                "source_map": primary.map_name,
                "source_part": primary.part_name,
                "source_entity_id": primary.entity_id,
                "source_archetype": asdict(primary.archetype),
                "source_talk_id": primary.talk_id,
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": PART_PINS[BODY_ONE],
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
                "destination_part": addition["destination_part"],
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": addition["source_archetype"]["npc_param_id"],
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for addition in additions
        ],
        "boss_contract": {
            "format": "bb-living-failures-maria-contract-v1",
            "arena": "lady-maria",
            "donor": "living-failures",
            "status": "planned",
            "writer_status": "pending_builder_integration_and_same_bank_receipt",
            "runtime_status": "unobserved arena fit and in-game behavior",
            "logical_encounter_count": 1,
            "physical_actor_count": 6,
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [
                13501800,
                13501807,
                13504800,
                13504801,
                13504805,
            ],
            "terminal_policy": "retain byte-identical Maria CharacterDead(3500800) terminal; donor cleanup kills the primary after aggregate proxy reaches zero",
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(MARIA_PACKAGE.expected),
            "sfx_policy": "relocate five source MapSFX records to a cloned Maria-anchored region",
            "ffx_merge_policy": "same-bank pinned preserve_destination_union_source_v1 receipt; imports zero entries",
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


def living_failures_maria_helper_scaling_parents(
    plan: Mapping,
) -> dict[tuple[str, str], str]:
    return {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in plan.get("boss_actor_scaling_requirements", [])
    }
