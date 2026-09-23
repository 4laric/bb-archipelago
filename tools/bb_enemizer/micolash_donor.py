"""Reusable, source-pinned Micolash direct-combat donor for base arenas.

The receiving arena retains its entry trigger, fog, camera, music geometry,
terminal, rewards, and progression.  Micolash retains NPC/Think 6380 and the
complete original health/network/co-op setup, but enters ordinary combat from
full health.  Mensis chase, mirrors, cage geometry, dialogue, and Talk state
are deliberately excluded.  Static construction and compilation are proven;
runtime navigation and character-asset closure remain unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import ARENAS, ArenaContract
from .maria_donor import _activation_without_destination_animations
from .micolash_moon_contract import DONOR_HASHES, MICOLASH_ARCHETYPE, MICOLASH_PIN
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m26_00_00_00.emevd.dcx.js"
SOURCE_MAP = "m26_00_00_00"
MICOLASH = 2600850
SOURCE_PART = "c0000_0005"
SOURCE_TALK_ID = 260311
SOURCE_INITIALIZATION = {
    "talk_id": SOURCE_TALK_ID,
    "unk_t18": 6380,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
TALK_SOURCE_SHA256 = "afb70280a2420792066af1f6602c2202576d649d891609662e8e53303af2c56b"
AI_BINDER_SHA256 = "08d8f72ba3701bbabeea4bda471fff40817f21bcce9599bd76ed479b050e69bc"
AI_GOAL_SHA256 = {
    "006380_battle.lua": "a97cc3d77ad479fd80a322c177c1c5f3b2d0771cc65f13f8bb5f0074f715f6c3",
    "006380_logic.lua": "e6e68d54547e3e776e2bb8aa841dc61aeaf1688c6b5ab6b63b2731b071e06422",
}
CHARACTER_ARCHIVE_SHA256 = (
    "2ef1b29323c635dca1828b823a957dc7770967d7642b458bad7365375bcd32cb"
)
SOURCE_HASHES = {
    **DONOR_HASHES,
    12604854: "99021f5ff8f2aa2738f277b7cc42f8573673ce6cfbb786237772af751d9e5a54",
}

CO_OP_RESTORE = {
    "cleric-beast": (
        12411703,
        "f4982068db5c19d893ac320045e14491832a5722d1fd89a8038ef4cb8b372ce9",
    ),
    "blood-starved-beast": (
        12301803,
        "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
    ),
    "darkbeast-paarl": (
        12301703,
        "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
    ),
    "vicar-amelia": (
        12401804,
        "85aa59f873b275cb390675f4f2ef13e4f7b3f00935274a2ce43c23b75070da59",
    ),
    "amygdala": (
        13301803,
        "7613c67c60f7fd94fe8152c96887113aabaeee5cc728f79bd3c2fcfd2bfb0dd9",
    ),
    "ebrietas": (
        12421803,
        "dcbbafd95ebeebce5ddd63d637fc07b93bff8f52c33b77665e0ca21e6d649152",
    ),
}


@dataclass(frozen=True)
class MicolashDonorIds:
    readiness_event: int = 12996500
    phase_event: int = 12996501
    phase_marker_flag: int = 12996502
    notification_flag: int = 12996503

    def values(self) -> tuple[int, ...]:
        return (
            self.readiness_event,
            self.phase_event,
            self.phase_marker_flag,
            self.notification_flag,
        )


DEFAULT_IDS = MicolashDonorIds()


def _numbers(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numbers(body.decode("utf-8-sig")))
    return frozenset(values)


def _validate(ids: MicolashDonorIds, destination: str = "") -> None:
    if ids.values() != tuple(range(12996500, 12996504)):
        raise ValueError("Micolash donor requires the exact reviewed allocation")
    if set(ids.values()) & (_original_literals() | _numbers(destination)):
        raise ValueError("Micolash donor allocation collides with original inputs")


def _verify(
    blocks: Mapping[int, str], expected: Mapping[int, str], role: str
) -> None:
    for event_id, digest in expected.items():
        actual = hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest()
        if actual != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Micolash donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        text,
    )


def _noop(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
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
        declaration,
    )
    return declaration + "\n    EndEvent();\n});"


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
            *arena.retired_combat_events,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
        )
        if event is not None
    }


def _telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line
            for line in source.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        destination_lines = [
            line
            for line in destination.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(f"Micolash donor telemetry lacks unique {instruction}")
        result = _replace_once(
            result, source_lines[0], destination_lines[0], "destination telemetry"
        )
    return result


def _mark_entry_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _mapping(arena: ArenaContract, ids: MicolashDonorIds) -> dict[int, int]:
    return {
        MICOLASH: arena.actor,
        12601850: arena.completion_event,
        12604850: arena.start_flag,
        12604852: arena.health_bar_event,
        12604731: ids.notification_flag,
    }


def _health(
    arena: ArenaContract,
    source: str,
    destination: str,
    ids: MicolashDonorIds,
) -> str:
    result = _remap(source, _mapping(arena, ids))
    result = _replace_once(
        result,
        f"    SetCharacterHPBarDisplay({arena.actor}, Disabled);\n",
        f"    SetCharacterHPBarDisplay({arena.actor}, Disabled);\n"
        f"    SetCharacterInvincibility({arena.actor}, Enabled);\n",
        "pre-entry protection",
    )
    result = _replace_once(
        result,
        f"        WaitFor(EventFlag({arena.start_flag}));",
        f"        WaitFor(EventFlag({ids.readiness_event}));",
        "fresh readiness wait",
    )
    result = _replace_once(
        result,
        f"L0:\n    SetEventFlag({ids.notification_flag}, ON);",
        f"L0:\n    WaitFor(EventFlag({ids.readiness_event}));\n"
        f"    SetEventFlag({ids.notification_flag}, ON);",
        "saved readiness wait",
    )
    result = _replace_once(
        result,
        f"    SetCharacterAIState({arena.actor}, Enabled);",
        f"    SetCharacterInvincibility({arena.actor}, Disabled);\n"
        f"    SetCharacterAIState({arena.actor}, Enabled);",
        "combat protection release",
    )
    result = _replace_once(
        result,
        f"    DisplayBossHealthBar(Enabled, {arena.actor}, 0, 899000);",
        f"    DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label});",
        "destination health label",
    )
    result = _replace_once(
        result,
        f"    SetDistanceLimitForConversationStateProcessing({arena.actor}, 100);\n",
        "",
        "Mensis conversation processing",
    )
    result = _replace_once(
        result,
        f"    RequestCharacterAICommand({arena.actor}, 10, 0);",
        f"    RequestCharacterAICommand({arena.actor}, -1, 0);\n"
        f"    RequestCharacterAIReplan({arena.actor});",
        "chase command release",
    )
    return _telemetry(result, destination)


def _readiness(arena: ArenaContract, ids: MicolashDonorIds) -> str:
    return f"""$Event({ids.readiness_event}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    SetCharacterAIState({arena.actor}, Disabled);
    SetCharacterInvincibility({arena.actor}, Enabled);
    WaitFor(EventFlag({arena.start_flag}));
    RequestCharacterAICommand({arena.actor}, -1, 0);
    RequestCharacterAIReplan({arena.actor});
    SetEventFlag({ids.readiness_event}, ON);
}});"""


def _phase(arena: ArenaContract, ids: MicolashDonorIds) -> str:
    return f"""$Event({ids.phase_event}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    WaitFor(
        EventFlag({ids.readiness_event})
            && EventFlag({arena.health_bar_event})
            && HPRatio({arena.actor}) <= 0.5);
    SetEventFlag({ids.phase_marker_flag}, ON);
    RequestCharacterAICommand({arena.actor}, -1, 0);
    RequestCharacterAIReplan({arena.actor});
}});"""


def _music(arena: ArenaContract, block: str, ids: MicolashDonorIds) -> str:
    replacement = f"EventFlag({ids.phase_marker_flag})"
    if arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        event_flag = arena.phase_music_event_flag or arena.part_routine_event
        if event_flag is None:
            raise ValueError(f"{arena.key} has no declared music phase boundary")
        witness = f"EventFlag({event_flag})"
    return _replace_once(block, witness, replacement, "destination music boundary")


def _constructor(
    arena: ArenaContract, block: str, ids: MicolashDonorIds
) -> str:
    result = _replace_once(
        block,
        block.splitlines()[0] + "\n",
        block.splitlines()[0]
        + "\n"
        + f"    SetEventFlag({ids.readiness_event}, OFF);\n"
        + f"    SetEventFlag({ids.phase_event}, OFF);\n"
        + f"    SetEventFlag({ids.phase_marker_flag}, OFF);\n",
        "constructor readiness reset",
    )
    anchors = [
        f"    $InitializeEvent(0, {event});"
        for event in reversed(arena.phase_slots)
        if result.count(f"    $InitializeEvent(0, {event});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} lacks a constructor anchor")
    calls = (
        f"    $InitializeEvent(0, {ids.readiness_event});\n"
        f"    $InitializeEvent(0, {ids.phase_event});"
    )
    return _replace_once(
        result, anchors[0], anchors[0] + "\n" + calls, "constructor anchor"
    )


def micolash_donor_contract(
    arena: ArenaContract, ids: MicolashDonorIds = DEFAULT_IDS
) -> dict:
    _validate(ids)
    co_op_event, co_op_hash = CO_OP_RESTORE[arena.key]
    return {
        "format": "bb-micolash-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "micolash",
        "allocation": asdict(ids),
        "transition_policy": (
            "continuous direct combat from full health; at half health retain "
            "ordinary AI command -1 and replan without chase/dialogue/warp pause"
        ),
        "preserved_destination_events": [
            arena.completion_event,
            arena.lockcam_event,
            co_op_event,
        ],
        "destination_co_op_restore": {
            "event": co_op_event,
            "expected_sha256": co_op_hash,
        },
        "adapted_destination_events": [
            arena.activation_event,
            arena.health_bar_event,
            arena.music_event,
        ],
        "retired_destination_controllers": sorted(_retired(arena)),
        "copied_source_events": [
            {
                "source_event": 12604852,
                "destination_event": arena.health_bar_event,
                "expected_source_sha256": SOURCE_HASHES[12604852],
            }
        ],
        "source_combat_witnesses_not_copied": {
            str(event): SOURCE_HASHES[event]
            for event in (
                12604853,
                12604854,
                12604856,
                12604877,
                12604879,
                12604980,
            )
        },
        "source_owned_not_copied": [
            12601850,
            12604853,
            12604854,
            12604856,
            12604870,
            12604877,
            12604878,
            12604879,
            12604880,
            12604888,
            12604889,
            12604930,
            12604931,
            12604960,
            12604970,
            12604980,
            12604985,
            12604986,
        ],
        "ai_source_evidence": {
            "npc_think_id": 6380,
            "binder_sha256": AI_BINDER_SHA256,
            "goal_sha256": AI_GOAL_SHA256,
        },
        "talk_source_evidence": {
            "talk_id": SOURCE_TALK_ID,
            "sha256": TALK_SOURCE_SHA256,
            "transplanted": False,
            "destination_override": 0,
        },
        "character_asset_evidence": {
            "archive_sha256": CHARACTER_ARCHIVE_SHA256,
            "executed_tae_entries": "unproven",
            "recursive_effect_delivery": "not-validated",
            "coverage_scope": "source archive availability is not execution proof",
        },
        "terminal_policy": (
            "destination primary real death; unchanged destination terminal owns progression"
        ),
        "runtime_status": "unobserved",
    }


def patch_micolash_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    ids: MicolashDonorIds = DEFAULT_IDS,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, SOURCE_HASHES, "Micolash donor")
    co_op_event, co_op_hash = CO_OP_RESTORE[arena.key]
    if hashlib.sha256(original.get(co_op_event, "").encode()).hexdigest() != co_op_hash:
        raise ValueError(f"unsupported original {arena.key} co-op restore event")
    _validate(ids, destination)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    activation = _activation_without_destination_animations(
        arena, original[arena.activation_event]
    )
    activation = _mark_entry_notification(activation, ids.notification_flag)
    edits.update(
        {
            0: _constructor(arena, original[0], ids),
            arena.activation_event: activation,
            arena.health_bar_event: _health(
                arena,
                donor[12604852],
                original[arena.health_bar_event],
                ids,
            ),
            arena.music_event: _music(arena, original[arena.music_event], ids),
        }
    )
    additions = [_readiness(arena, ids), _phase(arena, ids)]
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | {ids.readiness_event, ids.phase_event}:
        raise ValueError("Micolash donor changed unexpected event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Micolash donor changed unrelated event {event_id}")
    for event_id in (arena.completion_event, arena.lockcam_event, co_op_event):
        if output[event_id] != original[event_id]:
            raise ValueError(
                f"Micolash donor changed protected destination event {event_id}"
            )
    combat = output[arena.health_bar_event] + output[ids.phase_event]
    forbidden = (
        "RequestCharacterAICommand(%d, 10" % arena.actor,
        "SetDistanceLimitForConversationStateProcessing",
        "726003",
        "126049",
        "26020",
    )
    if any(value in combat for value in forbidden):
        raise ValueError("Micolash donor retained Mensis chase or Talk state")
    return result


def _source_actor(slots: Sequence[Slot]) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == SOURCE_MAP
        and slot.entity_id == MICOLASH
        and slot.part_name == SOURCE_PART
        and slot.archetype == MICOLASH_ARCHETYPE
    ]
    if len(found) != 1 or found[0].talk_id != SOURCE_TALK_ID or found[0].dummy:
        raise ValueError("Micolash donor lacks exact source actor")
    return found[0]


def native_plan_micolash_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: MicolashDonorIds = DEFAULT_IDS,
) -> dict:
    _validate(ids)
    destinations = sorted(
        [
            slot
            for slot in slots
            if slot.entity_id == arena.actor and slot.archetype == arena.archetype
        ],
        key=lambda slot: slot.map_name,
    )
    if len(destinations) != arena.destination_count:
        raise ValueError(f"Micolash/{arena.key} lacks destination state closure")
    source = _source_actor(slots)
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype,
        MICOLASH_ARCHETYPE,
        warnings=[
            "runtime direct-combat navigation and complete character assets are unvalidated"
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
    bindings = []
    for target in destinations:
        bindings.append(
            {
                "source_map": source.map_name,
                "source_event_file": "event/" + EVENT_FILE,
                "source_part": source.part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype),
                "source_talk_id": source.talk_id,
                "source_provenance": {
                    "format": "bb-boss-actor-pin-v1",
                    "part_sha256": MICOLASH_PIN,
                },
                "source_initialization": dict(SOURCE_INITIALIZATION),
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
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-micolash"},
        "boss_contract": micolash_donor_contract(arena, ids),
        "primary_init_source_bindings": bindings,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def portable_micolash_arenas(
    arenas: Sequence[ArenaContract] = ARENAS,
) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
