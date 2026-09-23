"""Reusable source-pinned One Reborn combat donor for base arenas."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from . import one_reborn_ebrietas_contract as one
from .boss_canary import event_blocks, parse_events
from .boss_contracts import ARENAS, ArenaContract
from .maria_donor import _activation_without_destination_animations
from .model import Slot, Swap
from .one_reborn_character_ffx import character_ffx_plan
from .scaling import plan_scaling
from .wet_nurse_donor import DESTINATION_PART_PINS

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m28_00_00_00.emevd.dcx.js"
SOURCE_STATES = one.SOURCE_STATES
CORE, BODY, CONTROLLER, PROXY = one.CORE, one.BODY, one.CONTROLLER, one.PROXY
CASTERS = one.CASTERS
ARCH = one.ARCH
SOURCE_PARTS = {
    CORE: "c5070_0000",
    BODY: "c5071_0000",
    CONTROLLER: "c5072_0000",
    PROXY: "c1050_0120",
    **{entity: f"c1050_01{suffix}" for entity, suffix in zip(CASTERS, (10, 12, 14, 15, 17, 19), strict=True)},
}
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
CO_OP_RESTORE = {
    "cleric-beast": 12411703,
    "blood-starved-beast": 12301803,
    "darkbeast-paarl": 12301703,
    "vicar-amelia": 12401804,
    "amygdala": 13301803,
    "ebrietas": 12421803,
}

CONTROLLER_SOURCES = (
    12804830,
    12804831,
    12804832,
    12804834,
    12804835,
    12804836,
    12804837,
    12804838,
)


@dataclass(frozen=True)
class OneRebornDonorAllocation:
    camera: int = 12996700
    tether: int = 12996701
    limb_guard: int = 12996702
    limb_flag: int = 12996703
    limb_first: int = 12996704
    controller_first: int = 12996711
    caster_react: int = 12996719
    caster_count: int = 12996721
    phase_one: int = 12996727
    phase_two: int = 12996728
    terminal_bridge: int = 12996729
    lifecycle_cleanup: int = 12996730
    caster_count_flag: int = 12996740
    notification_flag: int = 12996744
    helper_first: int = 984100

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.camera,
            self.tether,
            self.limb_guard,
            *range(self.limb_first, self.limb_first + 7),
            *range(self.controller_first, self.controller_first + 8),
            self.caster_react,
            self.caster_react + 1,
            *range(self.caster_count, self.caster_count + 6),
            self.phase_one,
            self.phase_two,
            self.terminal_bridge,
            self.lifecycle_cleanup,
        )

    def helper_ids(self) -> tuple[int, ...]:
        return tuple(range(self.helper_first, self.helper_first + 9))

    def values(self) -> tuple[int, ...]:
        return (
            *self.event_ids(),
            self.limb_flag,
            *range(self.caster_count_flag, self.caster_count_flag + 4),
            self.notification_flag,
            *self.helper_ids(),
        )


DEFAULT_ALLOCATION = OneRebornDonorAllocation()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for blob in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(blob.decode("utf-8-sig")))
    return frozenset(values)


def _validate(allocation: OneRebornDonorAllocation, destination: str = "") -> None:
    expected = (
        12996700,
        12996701,
        12996702,
        *range(12996704, 12996711),
        *range(12996711, 12996719),
        12996719,
        12996720,
        *range(12996721, 12996727),
        12996727,
        12996728,
        12996729,
        12996730,
        12996703,
        *range(12996740, 12996744),
        12996744,
        *range(984100, 984109),
    )
    if allocation.values() != expected:
        raise ValueError("One Reborn donor requires the exact reviewed allocation")
    if len(expected) != len(set(expected)) or set(expected) & (
        _original_literals() | _numbers(destination)
    ):
        raise ValueError("One Reborn donor allocation collides with original inputs")


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        actual = hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest()
        if actual != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"One Reborn donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        text,
    )


def _noop(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            value.strip()
            if value.strip().startswith("unused_")
            else "unused_" + value.strip()
            for value in match[1].split(",")
            if value.strip()
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


def _retired(arena: ArenaContract) -> set[int]:
    return {
        event
        for event in (
            *arena.phase_slots,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
            *arena.retired_combat_events,
        )
        if event is not None
    }


def _notification_flag(
    destination_health: str, allocation: OneRebornDonorAllocation
) -> int:
    match = re.search(
        r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification\(0\);",
        destination_health,
    )
    return allocation.notification_flag if match is None else int(match[1])


def _mark_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    if block.count(witness) > 1:
        raise ValueError("destination entry notification witness is not unique")
    if witness not in block:
        return block
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        old = [
            line
            for line in source.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        new = [
            line
            for line in destination.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(old) != 1 or len(new) != 1:
            raise ValueError(f"One Reborn telemetry lacks unique {instruction}")
        result = _replace_once(result, old[0], new[0], "destination telemetry")
    return result


def _mapping(
    arena: ArenaContract,
    allocation: OneRebornDonorAllocation,
    notification_flag: int,
) -> dict[int, int]:
    helpers = allocation.helper_ids()
    result = {
        CORE: arena.actor,
        BODY: helpers[0],
        CONTROLLER: helpers[1],
        PROXY: helpers[2],
        **{entity: helpers[index + 3] for index, entity in enumerate(CASTERS)},
        12801800: arena.completion_event,
        12801802: arena.activation_event,
        12801803: CO_OP_RESTORE[arena.key],
        12804223: notification_flag,
        12804800: arena.start_flag,
        12804802: arena.health_bar_event,
        12804804: allocation.camera,
        12804806: allocation.tether,
        12804807: allocation.limb_guard,
        12804808: allocation.limb_flag,
        12804840: allocation.caster_react,
        12804850: allocation.caster_count,
        12804860: allocation.caster_count_flag,
        12804870: allocation.phase_one,
        12804871: allocation.phase_two,
    }
    for index in range(7):
        result[12804820 + index] = allocation.limb_first + index
    for index, source in enumerate(CONTROLLER_SOURCES):
        result[source] = allocation.controller_first + index
    return result


def _activation(
    arena: ArenaContract,
    destination: str,
    body: int,
    notification_flag: int,
    fallback_flag: int,
) -> str:
    result = _activation_without_destination_animations(arena, destination)
    # The donor's real core/body are permanently immortal; damage is routed
    # into the c1050 proxy.  Ebrietas's entry originally clears immortality at
    # its damage trigger, which would bypass that source-owned health graph.
    immortality_clear = f"    SetCharacterImmortality({arena.actor}, Disabled);\n"
    expected_clears = 1 if arena.key == "ebrietas" else 0
    if result.count(immortality_clear) != expected_clears:
        raise ValueError(f"{arena.key} has unexpected entry immortality ownership")
    result = result.replace(immortality_clear, "")
    wait = result.index("    WaitFor(")
    result = (
        result[:wait]
        + f"    ChangeCharacterEnableState({body}, Disabled);\n"
        + result[wait:]
    )
    start = f"    SetEventFlag({arena.start_flag}, ON);"
    result = _replace_once(
        result,
        start,
        f"    ChangeCharacterEnableState({body}, Enabled);\n" + start,
        "host body restore",
    )
    if notification_flag == fallback_flag:
        result = _mark_notification(result, notification_flag)
    return result


def _client_restore(arena: ArenaContract, destination: str, body: int) -> str:
    start = f"    SetEventFlag({arena.start_flag}, ON);"
    return _replace_once(
        destination,
        start,
        f"    ChangeCharacterEnableState({body}, Enabled);\n" + start,
        "client body restore",
    )


def _music(arena: ArenaContract, destination: str) -> str:
    source_boundary = f"CharacterHasEventMessage({arena.actor}, 300)"
    if arena.phase_music_event_flag is not None:
        return _replace_once(
            destination,
            f"EventFlag({arena.phase_music_event_flag})",
            source_boundary,
            "destination phase music flag",
        )
    return _replace_once(
        destination,
        f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
        source_boundary,
        "destination phase music message",
    )


def _camera(
    arena: ArenaContract, source: str, mapping: Mapping[int, int], event_id: int
) -> str:
    result = _remap(source, {**mapping, 12804804: event_id})
    result = result.replace(
        "SetLockcamSlotNumber(28, 0,",
        f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
    )
    if result.count(
        f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    ) != 2:
        raise ValueError("One Reborn camera mapping lost source witnesses")
    return result


def _health(
    source: str, destination: str, mapping: Mapping[int, int]
) -> str:
    return _telemetry(_remap(source, mapping), destination)


def _copied_events(
    donor_zero: str,
    donor: Mapping[int, str],
    mapping: Mapping[int, int],
    allocation: OneRebornDonorAllocation,
) -> tuple[list[str], list[str]]:
    copies = [
        (12804804, allocation.camera),
        (12804806, allocation.tether),
        (12804807, allocation.limb_guard),
        *((12804820, allocation.limb_first + index) for index in range(7)),
        *(
            (source, allocation.controller_first + index)
            for index, source in enumerate(CONTROLLER_SOURCES)
        ),
        *((12804840, allocation.caster_react + index) for index in range(2)),
        *((12804850, allocation.caster_count + index) for index in range(6)),
        (12804870, allocation.phase_one),
        (12804871, allocation.phase_two),
    ]
    pending: dict[int, list[int]] = {}
    for source_event, destination_event in copies:
        pending.setdefault(source_event, []).append(destination_event)
    source_pattern = "|".join(str(event) for event in pending)
    initializers = []
    for line in donor_zero.splitlines():
        match = re.search(rf", ({source_pattern})(?:,|\))", line)
        if match is None:
            continue
        source_event = int(match[1])
        targets = pending[source_event]
        if not targets:
            raise ValueError(f"unexpected One Reborn initializer {source_event}")
        initializers.append(
            _remap(line, {**mapping, source_event: targets.pop(0)})
        )
    if any(targets for targets in pending.values()):
        raise ValueError("One Reborn donor lacks source constructor witnesses")
    bodies = [
        _remap(donor[source], {**mapping, source: destination})
        for source, destination in copies
    ]
    return initializers, bodies


def _bridge(arena: ArenaContract, allocation: OneRebornDonorAllocation) -> str:
    body, controller, proxy, *casters = allocation.helper_ids()
    deaths = "\n".join(
        f"    ForceCharacterDeath({entity}, false);"
        for entity in (body, controller, proxy, *casters)
    )
    return f"""$Event({allocation.terminal_bridge}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    WaitFor(HPRatio({proxy}) <= 0);
    RequestCharacterAnimationReset({arena.actor}, Interpolation.Uninterpolated);
    RequestCharacterAnimationReset({body}, Interpolation.Uninterpolated);
{deaths}
    ForceCharacterDeath({arena.actor}, false);
    WaitFor(EventFlag({arena.completion_event}));
}});"""


def _cleanup(arena: ArenaContract, allocation: OneRebornDonorAllocation) -> str:
    actors = "".join(
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);\n"
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    ForceCharacterDeath({entity}, false);\n"
        for entity in allocation.helper_ids()
    )
    return f"""$Event({allocation.lifecycle_cleanup}, Default, function() {{
    WaitFor(EventFlag({arena.completion_event}));
{actors}}});"""


def one_reborn_donor_contract(
    arena: ArenaContract,
    allocation: OneRebornDonorAllocation = DEFAULT_ALLOCATION,
) -> dict:
    _validate(allocation)
    return {
        "format": "bb-one-reborn-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "the-one-reborn",
        "allocation": asdict(allocation),
        "source_hash_pins": dict(one.DONOR_HASHES),
        "preserved_destination_events": [arena.completion_event],
        "adapted_destination_events": [
            arena.activation_event,
            CO_OP_RESTORE[arena.key],
            arena.health_bar_event,
            arena.music_event,
            arena.lockcam_event,
        ],
        "retired_destination_controllers": sorted(_retired(arena)),
        "source_roster": {
            "primary": CORE,
            "helpers": [BODY, CONTROLLER, PROXY, *CASTERS],
            "regions": [],
            "generators": [],
        },
        "terminal_policy": "proxy HP depletion bridges to destination primary death; destination progression remains exact",
        "combat_policy": "full multipart linked health, seven limbs, eight controllers, six caster counters, and both phases",
        "character_asset_policy": {
            "delivery": "pinned original m28 whole-bank union for all typed 96/100/118 direct roots",
            "recursive_fxr_dependencies": "not-validated",
            "destination_bank_precedence": "not-runtime-validated",
            "runtime_status": "unobserved",
        },
        "geometry_risk": "source-relative bell-maiden placement and navigation are runtime-unobserved",
        "runtime_status": "unobserved",
    }


def patch_one_reborn_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    allocation: OneRebornDonorAllocation = DEFAULT_ALLOCATION,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, one.DONOR_HASHES, "One Reborn donor")
    _validate(allocation, destination)
    notification = _notification_flag(original[arena.health_bar_event], allocation)
    mapping = _mapping(arena, allocation, notification)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    activation = _activation(
        arena,
        original[arena.activation_event],
        allocation.helper_ids()[0],
        notification,
        allocation.notification_flag,
    )
    initializers, imported = _copied_events(
        donor[0], donor, mapping, allocation
    )
    anchors = [
        f"    $InitializeEvent(0, {event});"
        for event in reversed(arena.phase_slots)
        if original[0].count(f"    $InitializeEvent(0, {event});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} lacks a constructor anchor")
    calls = "\n".join(
        (
            *initializers,
            f"    $InitializeEvent(0, {allocation.terminal_bridge});",
            f"    $InitializeEvent(0, {allocation.lifecycle_cleanup});",
        )
    )
    constructor = _replace_once(
        original[0],
        anchors[0],
        anchors[0] + "\n" + calls,
        "destination constructor anchor",
    )
    imported[0] = _camera(arena, donor[12804804], mapping, allocation.camera)
    edits.update(
        {
            0: constructor,
            arena.activation_event: activation,
            CO_OP_RESTORE[arena.key]: _client_restore(
                arena,
                original[CO_OP_RESTORE[arena.key]],
                allocation.helper_ids()[0],
            ),
            arena.health_bar_event: _health(
                donor[12804802], original[arena.health_bar_event], mapping
            ),
            arena.music_event: _music(arena, original[arena.music_event]),
            arena.lockcam_event: _camera(
                arena, donor[12804804], mapping, arena.lockcam_event
            ),
        }
    )
    additions = [*imported, _bridge(arena, allocation), _cleanup(arena, allocation)]
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | set(allocation.event_ids()):
        raise ValueError("One Reborn donor changed unexpected event identities")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"One Reborn donor changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("One Reborn donor changed destination progression")
    source_only = {
        12801800,
        12801802,
        12801803,
        12804223,
        12804800,
        12804802,
        12804804,
        12804806,
        12804807,
        12804808,
        12804820,
        *CONTROLLER_SOURCES,
        12804840,
        12804850,
        12804860,
        12804870,
        12804871,
        CORE,
        BODY,
        CONTROLLER,
        PROXY,
        *CASTERS,
    }
    copied = "\n".join(
        output[event]
        for event in (
            arena.activation_event,
            CO_OP_RESTORE[arena.key],
            arena.health_bar_event,
            arena.lockcam_event,
            *allocation.event_ids(),
        )
    )
    if _numbers(copied) & source_only:
        raise ValueError("One Reborn donor retains a source-map literal")
    return result


def _source_state(destination_map: str) -> str:
    return SOURCE_STATES[1] if destination_map.endswith("_01") else SOURCE_STATES[0]


def _require(
    slots: Sequence[Slot], state: str, entity: int, part: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == state
        and slot.entity_id == entity
        and slot.part_name == part
        and slot.archetype == ARCH[entity]
    ]
    if len(found) != 1 or found[0].dummy or found[0].talk_id:
        raise ValueError(f"One Reborn donor lacks exact source actor {entity} in {state}")
    return found[0]


def _pin(state: str, entity: int, anchor: bool = False) -> dict:
    result = {
        "format": "bb-boss-actor-pin-v1",
        "part_sha256": one.PINS[state][entity],
    }
    if anchor:
        result["anchor_sha256"] = one.PINS[state][CORE]
    return result


def native_plan_one_reborn_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: OneRebornDonorAllocation = DEFAULT_ALLOCATION,
) -> dict:
    _validate(allocation)
    destinations = sorted(
        [
            slot
            for slot in slots
            if slot.entity_id == arena.actor and slot.archetype == arena.archetype
        ],
        key=lambda slot: slot.map_name,
    )
    if len(destinations) != arena.destination_count:
        raise ValueError(f"One Reborn/{arena.key} lacks destination state closure")
    sources = {
        state: {
            entity: _require(slots, state, entity, SOURCE_PARTS[entity])
            for entity in (CORE, BODY, CONTROLLER, PROXY, *CASTERS)
        }
        for state in SOURCE_STATES
    }
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype,
        ARCH[CORE],
        warnings=[
            "runtime One Reborn helper geometry, navigation, and character assets are unobserved"
        ],
        destinations={
            slot.key: {
                "map_name": slot.map_name,
                "entity_id": slot.entity_id,
                "x": slot.x,
                "y": slot.y,
                "z": slot.z,
            }
            for slot in destinations
        },
    )
    changes, skips = plan_scaling(
        [swap], destinations, dict(npcs), dict(effects), boss_tiers=True
    )
    bindings, additions, scaling = [], [], []
    helper_entities = (BODY, CONTROLLER, PROXY, *CASTERS)
    helper_parts = (
        "ap_one_reborn_body",
        "ap_one_reborn_controller",
        "ap_one_reborn_proxy",
        *(f"ap_one_reborn_caster_{index}" for index in range(6)),
    )
    for target in destinations:
        state = _source_state(target.map_name)
        core = sources[state][CORE]
        if (target.map_name, target.entity_id) not in DESTINATION_PART_PINS:
            raise ValueError(f"One Reborn/{arena.key} lacks destination anchor pin")
        bindings.append(
            {
                "source_map": state,
                "source_event_file": "event/" + EVENT_FILE,
                "source_part": core.part_name,
                "source_entity_id": CORE,
                "source_archetype": asdict(ARCH[CORE]),
                "source_talk_id": 0,
                "source_provenance": _pin(state, CORE),
                "source_initialization": dict(SOURCE_INITIALIZATION),
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
        )
        for index, (entity, part) in enumerate(
            zip(helper_entities, helper_parts, strict=True)
        ):
            source = sources[state][entity]
            additions.append(
                {
                    "source_map": state,
                    "source_event_file": "event/" + EVENT_FILE,
                    "source_part": source.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": entity,
                    "source_archetype": asdict(ARCH[entity]),
                    "source_part_kind": "enemy",
                    "source_provenance": _pin(state, entity, anchor=True),
                    "source_initialization": dict(SOURCE_INITIALIZATION),
                    "destination_map": target.map_name,
                    "destination_anchor_part": target.part_name,
                    "destination_part": part,
                    "destination_entity_id": allocation.helper_ids()[index],
                    "allocation_evidence": "One Reborn reusable donor allocation v1; original/project corpus scan",
                    "required_native_fields": [
                        "source_provenance",
                        "source_initialization",
                    ],
                }
            )
            scaling.append(
                {
                    "destination_map": target.map_name,
                    "destination_part": part,
                    "parent_logical_key": swap.logical_key,
                    "source_npc_param_id": ARCH[entity].npc_param_id,
                    "strategy": (
                        "reviewed_same_source_npc_helper_clone_required"
                        if entity == PROXY
                        else "allocate_distinct_verified_helper_clone"
                    ),
                }
            )
    character_ffx = character_ffx_plan([*bindings, *additions], arena.key)
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-the-one-reborn"},
        "boss_contract": one_reborn_donor_contract(arena, allocation),
        "primary_init_source_bindings": bindings,
        "boss_actor_additions": additions,
        "boss_actor_scaling_requirements": scaling,
        **character_ffx,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def portable_one_reborn_arenas(
    arenas: Sequence[ArenaContract] = ARENAS,
) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
