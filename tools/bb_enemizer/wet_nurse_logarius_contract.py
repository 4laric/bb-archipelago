"""Evidence-pinned Mergo's Wet Nurse combat in Martyr Logarius' arena.

Cainhurst keeps its terminal, rewards, fog, and map-sound slots. The Logarius
camera controller is disabled because it depends on the retired sword helper; no
unpinned Wet Nurse camera controller is imported. The source-pinned Wet Nurse core/support/proxy health graph, warp regions and model
point are added as a reviewed construction request.  The source m26 script is
read only: its Micolash progression is never remapped or emitted.  Static
construction evidence only; runtime behaviour remains unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix
from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from . import wet_nurse_bsb_contract as wet
from . import bsb_logarius_contract as logarius

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
WET_NURSE_SOURCE = wet.WET_NURSE_SOURCE
LOGARIUS_SOURCE = logarius.LOGARIUS_SOURCE
WET_CORE, WET_SUPPORT, WET_PROXY, WET_OBJECT = (
    wet.WET_CORE,
    wet.WET_SUPPORT,
    wet.WET_PROXY,
    wet.WET_OBJECT,
)
LOGARIUS_CORE, LOGARIUS_SWORD, LOGARIUS_EFFECT_OWNER = (
    logarius.LOGARIUS_CORE,
    logarius.LOGARIUS_SWORD,
    logarius.LOGARIUS_EFFECT_OWNER,
)
WET_ARCHETYPE, LOGARIUS_ARCHETYPE = wet.WET_ARCHETYPE, logarius.LOGARIUS_ARCHETYPE
PROJECT_MIN, PROJECT_MAX = 12993800, 12993899
DONOR_HASHES = wet.DONOR_HASHES
ARENA_HASHES = logarius.ARENA_HASHES
WET_PINS, REGION_PINS, OBJECT_PIN = wet.WET_PINS, wet.REGION_PINS, wet.OBJECT_PIN
LOGARIUS_PART_PINS = logarius.LOGARIUS_PART_PINS


@dataclass(frozen=True)
class WetNurseLogariusIds:
    support_setup: int = 12993800
    core_command: int = 12993801
    route_selector: int = 12993802
    core_warp: int = 12993803
    support_emergence: int = 12993804
    proxy_death_bridge: int = 12993805
    helper_cleanup: int = 12993806
    support_entity: int = 981600
    proxy_entity: int = 981601
    warp_region_first_entity: int = 981602
    object_entity: int = 981608
    health_entered_flag: int = 12993820
    warp_flag_first: int = 12993821
    support_flag_first: int = 12993827

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.support_setup,
            self.core_command,
            self.route_selector,
            self.core_warp,
            self.support_emergence,
            self.proxy_death_bridge,
            self.helper_cleanup,
        )

    def all_project_ids(self) -> tuple[int, ...]:
        return self.event_ids() + (
            self.health_entered_flag,
            *(self.warp_flag_first + i for i in range(6)),
            *(self.support_flag_first + i for i in range(4)),
        )

    def helper_ids(self) -> tuple[int, ...]:
        return (
            self.support_entity,
            self.proxy_entity,
            *(self.warp_region_first_entity + i for i in range(6)),
            self.object_entity,
        )


DEFAULT_IDS = WetNurseLogariusIds()


def _verify(text: str, pins: Mapping[int, str], label: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        if (
            event not in blocks
            or hashlib.sha256(blocks[event].encode()).hexdigest() != digest
        ):
            raise ValueError(f"unsupported original {label} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Wet Nurse/Logarius expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])", lambda m: str(values.get(int(m[0]), int(m[0]))), text
    )


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda m: "function("
        + ", ".join(
            x.strip() if x.strip().startswith("unused_") else "unused_" + x.strip()
            for x in m[1].split(",")
            if x.strip()
        )
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _all_original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            int(x)
            for x in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return values


def _validate_ids(ids: WetNurseLogariusIds, destination: str) -> None:
    project, helpers = ids.all_project_ids(), ids.helper_ids()
    local = {int(x) for x in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    original = _all_original_literals()
    if (
        len(project) != len(set(project))
        or any(not PROJECT_MIN <= x <= PROJECT_MAX for x in project)
        or set(project) & (local | original)
    ):
        raise ValueError(
            "Wet Nurse/Logarius IDs must be collision-free project-owned 129938xx values"
        )
    if (
        len(helpers) != len(set(helpers))
        or any(not 981600 <= x <= 981699 for x in helpers)
        or set(helpers) & (local | original | set(project))
    ):
        raise ValueError(
            "Wet Nurse/Logarius helper IDs must be collision-free reserved 981600-range values"
        )


def _source_initializers(
    event_zero: str, source_event: int, expected_count: int, remap: Mapping[int, int]
) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(calls) != expected_count:
        raise ValueError(
            f"Wet Nurse Event(0) lacks {expected_count} initializer witnesses for {source_event}"
        )
    return [_remap(line, remap) for line in calls]


def _mapping(ids: WetNurseLogariusIds) -> dict[int, int]:
    mapping = {
        WET_CORE: LOGARIUS_CORE,
        WET_SUPPORT: ids.support_entity,
        WET_PROXY: ids.proxy_entity,
        WET_OBJECT: ids.object_entity,
        12601800: 12501800,
        12604800: 12504800,
        12604803: 12504803,
        12604732: ids.health_entered_flag,
        2600010: 2500010,
        12604802: 12504802,
        12604806: ids.support_setup,
        12604810: ids.core_command,
        12604820: ids.route_selector,
        12604830: ids.core_warp,
        12604840: ids.support_emergence,
    }
    mapping.update({2602830 + i: ids.warp_region_first_entity + i for i in range(6)})
    mapping.update({12605880 + i: ids.warp_flag_first + i for i in range(6)})
    mapping.update({12604841 + i: ids.support_flag_first + i for i in range(4)})
    return mapping


def patch_wet_nurse_at_logarius(
    destination: str, donor_source: str, ids: WetNurseLogariusIds = DEFAULT_IDS
) -> str:
    """Install Wet Nurse combat while preserving the Cainhurst terminal verbatim."""
    arena, donor = _verify(destination, ARENA_HASHES, "Logarius arena"), _verify(
        donor_source, DONOR_HASHES, "Wet Nurse donor"
    )
    _validate_ids(ids, destination)
    remap = _mapping(ids)
    health = _remap(donor[12604802], remap)
    health = _replace_once(
        health, "CreatePlaylog(88);", "CreatePlaylog(82);", "Cainhurst playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2500010, 104, Enabled);",
        "StartTimeMeasurement(2500010, 98, Enabled);",
        "Cainhurst time measurement",
    )
    health = _replace_once(
        health,
        f"            if (!EventFlag({ids.health_entered_flag})) {{\n                IssueBossRoomEntryNotification(0);\n            }}\n            SetNetworkUpdateAuthority(2500800, AuthorityLevel.Forced);",
        f"            if (!EventFlag({ids.health_entered_flag})) {{\n                if (!EventFlag(12504223)) {{\n                    IssueBossRoomEntryNotification(0);\n                }}\n            }}\n            SetNetworkUpdateAuthority(2500800, AuthorityLevel.Forced);",
        "Cainhurst notification",
    )
    health = _replace_once(
        health,
        f"    SetEventFlag({ids.health_entered_flag}, ON);\n    SetEventFlag(12504800, ON);",
        f"    SetEventFlag({ids.health_entered_flag}, ON);\n    SetEventFlag(12504223, ON);\n    SetEventFlag(12504800, ON);",
        "Cainhurst battle state",
    )
    imported = {
        ids.support_setup: _remap(donor[12604806], remap),
        ids.core_command: _remap(donor[12604810], remap),
        ids.route_selector: _remap(donor[12604820], remap),
        ids.core_warp: _remap(donor[12604830], remap),
        ids.support_emergence: _remap(donor[12604840], remap),
        ids.proxy_death_bridge: f"""$Event({ids.proxy_death_bridge}, Default, function() {{
    EndIf(EventFlag(12501800));
    WaitFor(HPRatio({ids.proxy_entity}) <= 0);
    EndIf(EventFlag(12501800));
    RequestCharacterAnimationReset({LOGARIUS_CORE}, Interpolation.Uninterpolated);
    RequestCharacterAnimationReset({ids.support_entity}, Interpolation.Uninterpolated);
    ForceCharacterDeath({LOGARIUS_CORE}, false);
    ForceCharacterDeath({ids.support_entity}, false);
    WaitFor(CharacterDead({LOGARIUS_CORE}));
    ClearSpEffect(10000, 5630);
}});""",
        ids.helper_cleanup: f"""$Event({ids.helper_cleanup}, Default, function() {{
    SetCharacterAIState({LOGARIUS_SWORD}, Disabled);
    SetCharacterHPBarDisplay({LOGARIUS_SWORD}, Disabled);
    SetCharacterImmortality({LOGARIUS_SWORD}, Enabled);
    ChangeCharacterEnableState({LOGARIUS_SWORD}, Disabled);
    SetCharacterAIState({LOGARIUS_EFFECT_OWNER}, Disabled);
    SetCharacterHPBarDisplay({LOGARIUS_EFFECT_OWNER}, Disabled);
    ChangeCharacterEnableState({LOGARIUS_EFFECT_OWNER}, Disabled);
    WaitFor(EventFlag(12501800));
    SetCharacterImmortality({LOGARIUS_SWORD}, Disabled);
    ForceCharacterDeath({LOGARIUS_SWORD}, false);
    ForceCharacterDeath({LOGARIUS_EFFECT_OWNER}, false);
    ChangeCharacterEnableState({ids.support_entity}, Disabled);
    ChangeCharacterEnableState({ids.proxy_entity}, Disabled);
}});""",
    }
    initializers: list[str] = []
    for event, count in (
        (12604820, 1),
        (12604830, 6),
        (12604806, 1),
        (12604810, 1),
        (12604840, 1),
    ):
        initializers.extend(_source_initializers(donor[0], event, count, remap))
    initializers.extend(
        f"    $InitializeEvent(0, {event});"
        for event in (ids.proxy_death_bridge, ids.helper_cleanup)
    )
    # The source uses two inclusive RandomlySetEventFlagInRange spans. Keep
    # their endpoints explicit: a missing endpoint changes reachable combat
    # states even when every allocated ID is unique.
    selector_witness = next(
        line for line in initializers if str(ids.route_selector) in line
    )
    if f", {ids.warp_flag_first}, {ids.warp_flag_first + 5})" not in selector_witness:
        raise ValueError("Wet Nurse/Logarius lost six-state core-warp flag range")
    support = imported[ids.support_emergence]
    if (
        f"BatchSetEventFlags({ids.support_flag_first}, {ids.support_flag_first + 3}, OFF);"
        not in support
        or f"RandomlySetEventFlagInRange({ids.support_flag_first}, {ids.support_flag_first + 3}, ON);"
        not in support
    ):
        raise ValueError("Wet Nurse/Logarius lost four-state support-spawn flag range")
    activation = _replace_once(
        arena[12501802],
        "ForceAnimationPlayback(2500800, 7000, false, false, false);",
        "ChangeCharacterEnableState(2500800, Disabled);",
        "Logarius-only entry animation",
    )
    activation = _replace_once(
        activation,
        "    SetEventFlag(12504223, ON);",
        "    ChangeCharacterEnableState(2500800, Enabled);\n    SetEventFlag(12504223, ON);",
        "Wet Nurse entry visibility",
    )
    music = _replace_once(
        arena[12504803],
        "spFlagArea &= CharacterHasSpEffect(2500800, 5633);",
        f"spFlagArea &= HPRatio({ids.proxy_entity}) < 0.7;",
        "Wet Nurse proxy phase music",
    )
    edits = {
        0: _replace_once(
            arena[0],
            "    $InitializeEvent(0, 12504808);",
            "    $InitializeEvent(0, 12504808);\n" + "\n".join(initializers),
            "project controller anchor",
        ),
        12501802: activation,
        12504802: health,
        12504803: music,
        12504804: _end_event(arena[12504804]),
        12504806: _end_event(arena[12504806]),
        12504807: _end_event(arena[12504807]),
        12504808: _end_event(arena[12504808]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(imported[x] for x in ids.event_ids())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.event_ids()):
        raise ValueError("Wet Nurse/Logarius patch changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(
                f"Wet Nurse/Logarius changed unrelated Cainhurst event {event}"
            )
    for event in (12501800, 12501801, 12501803, 12504805, 12504810, 12504811):
        if output[event] != arena[event]:
            raise ValueError(
                "Wet Nurse/Logarius changed Cainhurst terminal, reward, fog, or AP progression"
            )
    copied = "\n".join((health, *imported.values()))
    if re.search(r"(?<!\d)(?:126|260)\d+(?!\d)", copied) or "2600803" in copied:
        raise ValueError(
            "Wet Nurse/Logarius copied combat retains donor-map or opaque literals"
        )
    if not all(
        f"CreateReferredDamagePair({actor}, {ids.proxy_entity})" in health
        for actor in (LOGARIUS_CORE, ids.support_entity)
    ):
        raise ValueError("Wet Nurse/Logarius lost source proxy health graph")
    return result


def _require(
    slots: Sequence[Slot],
    entity: int,
    archetype: Archetype,
    map_name: str | None = None,
) -> list[Slot]:
    found = [
        s
        for s in slots
        if s.entity_id == entity
        and s.archetype == archetype
        and (map_name is None or s.map_name == map_name)
    ]
    if not found or any(s.dummy or s.talk_id for s in found):
        raise ValueError(f"Wet Nurse/Logarius requires pinned ordinary actor {entity}")
    return sorted(found, key=lambda s: s.key)


def _initialization(source: Slot, target: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": WET_PINS[WET_CORE],
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


def native_plan_wet_nurse_at_logarius(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: WetNurseLogariusIds = DEFAULT_IDS,
) -> dict:
    donor_text, arena_text = read_blob(BUNDLE, WET_NURSE_SOURCE).decode(
        "utf-8-sig"
    ), read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
    _verify(donor_text, DONOR_HASHES, "Wet Nurse donor")
    _verify(arena_text, ARENA_HASHES, "Logarius arena")
    _validate_ids(ids, arena_text)
    core, support, proxy = (
        _require(slots, WET_CORE, WET_ARCHETYPE, "m26_00_00_00"),
        _require(slots, WET_SUPPORT, WET_ARCHETYPE, "m26_00_00_00"),
        _require(slots, WET_PROXY, WET_ARCHETYPE, "m26_00_00_00"),
    )
    target = _require(slots, LOGARIUS_CORE, LOGARIUS_ARCHETYPE, "m25_00_00_00")
    sword = _require(slots, LOGARIUS_SWORD, logarius.SWORD_ARCHETYPE, "m25_00_00_00")
    owner = _require(
        slots, LOGARIUS_EFFECT_OWNER, logarius.EFFECT_OWNER_ARCHETYPE, "m25_00_00_00"
    )
    if (
        len(core) != 1
        or len(support) != 1
        or len(proxy) != 1
        or len(target) != 1
        or len(sword) != 1
        or len(owner) != 1
    ):
        raise ValueError(
            "Wet Nurse/Logarius requires one exact Wet Nurse and Cainhurst three-actor rosters"
        )
    target = target[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        LOGARIUS_ARCHETYPE,
        WET_ARCHETYPE,
        warnings=[
            "experimental Wet Nurse-at-Logarius contract; runtime arena fit, model-point warps, proxy terminal bridge and music are unobserved"
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
        raise ValueError("Wet Nurse/Logarius primary normalization is ambiguous")
    anchor_pin = LOGARIUS_PART_PINS[LOGARIUS_CORE].part_sha256
    additions = []
    for source, entity, part in (
        (support[0], ids.support_entity, "ap_wet_nurse_support"),
        (proxy[0], ids.proxy_entity, "ap_wet_nurse_proxy"),
    ):
        additions.append(
            {
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_anchor_part": core[0].part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_part_kind": "enemy",
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": WET_PINS[source.entity_id],
                    "anchor_sha256": WET_PINS[WET_CORE],
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
                "allocation_evidence": "project-reserved helper ID; native writer checks all Part/Region/Event collisions",
            }
        )
    regions = []
    for i, (source_entity, (name, fp)) in enumerate(REGION_PINS.items()):
        regions.append(
            {
                "source_map": core[0].map_name,
                "source_region": name,
                "source_entity_id": source_entity,
                "source_provenance": {
                    "format": "bb-boss-region-pin-v1",
                    "region_sha256": fp,
                },
                "source_anchor_part": core[0].part_name,
                "source_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": WET_PINS[WET_CORE],
                },
                "destination_map": target.map_name,
                "destination_region": f"ap_wet_nurse_warp_{i+1}",
                "destination_entity_id": ids.warp_region_first_entity + i,
                "destination_anchor_part": target.part_name,
                "destination_anchor_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": anchor_pin,
                },
            }
        )
    objects = [
        {
            "source_map": core[0].map_name,
            "source_part": "o269800_0000",
            "source_entity_id": WET_OBJECT,
            "source_provenance": {
                "format": "bb-boss-object-pin-v1",
                "part_sha256": OBJECT_PIN,
            },
            "source_anchor_part": core[0].part_name,
            "source_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": WET_PINS[WET_CORE],
            },
            "destination_map": target.map_name,
            "destination_part": "ap_wet_nurse_model_point",
            "destination_entity_id": ids.object_entity,
            "destination_anchor_part": target.part_name,
            "destination_anchor_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": anchor_pin,
            },
        }
    ]
    remap = _mapping(ids)
    source_events = (
        (12604806, ids.support_setup),
        (12604810, ids.core_command),
        (12604820, ids.route_selector),
        (12604830, ids.core_warp),
        (12604840, ids.support_emergence),
    )
    retained = []
    for slot in (sword[0], owner[0]):
        pin = LOGARIUS_PART_PINS[slot.entity_id]
        retained.append(
            {
                "map": slot.map_name,
                "part": slot.part_name,
                "entity_id": slot.entity_id,
                "archetype": asdict(slot.archetype),
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": pin.part_sha256,
                },
                "source_initialization": {
                    "talk_id": pin.talk_id,
                    "unk_t18": pin.unk_t18,
                    "init_anim_id": pin.init_anim_id,
                    "damage_anim_id": pin.damage_anim_id,
                },
                "policy": "retain_native_part_disabled_alive_until_destination_completion",
            }
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "martyr-logarius<-mergos-wet-nurse"},
        "boss_actor_additions": additions,
        "boss_region_additions": regions,
        "boss_object_additions": objects,
        "primary_init_source_bindings": [_initialization(core[0], target)],
        "boss_contract": {
            "format": "bb-wet-nurse-logarius-contract-v1",
            "arena": "martyr-logarius",
            "donor": "mergos-wet-nurse",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                12501800,
                12501801,
                12501803,
                12504805,
                12504810,
                12504811,
            ],
            "retained_destination_helpers": retained,
            "source_m26_policy": "source m26 EMEVD is read-only; Micolash events and progression are neither remapped nor emitted",
            "opaque_actor_policy": "2600803 is absent from original MSBB tables and is not materialized or copied",
            "destination_music_policy": "retain Cainhurst map-sound slots; source combat phase uses proxy-ratio transition",
            "camera_policy": "disable original 12504804 because it waits for retired native sword helper 2500801; source Wet Nurse camera 12604804 is not hash-pinned or imported",
            "event_patch": {
                "changed_events": [
                    {
                        "destination_event_id": 12501802,
                        "source_event_id": 12601802,
                        "source_sha256": DONOR_HASHES[12601802],
                        "kind": "retain_logarius_trigger_with_wet_visibility",
                    },
                    {
                        "destination_event_id": 12504802,
                        "source_event_id": 12604802,
                        "source_sha256": DONOR_HASHES[12604802],
                    },
                    {
                        "destination_event_id": 12504803,
                        "source_event_id": None,
                        "kind": "destination_music_proxy_phase",
                    },
                ],
                "added_events": [
                    {
                        "source_event_id": src,
                        "destination_event_id": dst,
                        "source_sha256": DONOR_HASHES[src],
                        "literal_remap": remap,
                    }
                    for src, dst in source_events
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": event,
                        "kind": "destination_bridge",
                    }
                    for event in (ids.proxy_death_bridge, ids.helper_cleanup)
                ],
            },
        },
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": part,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": 551000,
                "strategy": "reviewed_same_source_npc_helper_clone_required",
            }
            for part in ("ap_wet_nurse_support", "ap_wet_nurse_proxy")
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [c.json() for c in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
