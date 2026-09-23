"""Reusable source-pinned Orphan of Kos combat donor for base arenas."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import (
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    BSB_ARENA,
    CLERIC_ARENA,
    EBRIETAS_ARENA,
    PAARL_ARENA,
    ArenaContract,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m36_00_00_00.emevd.dcx.js"
CORE, PHASE, SUPPORT = 3600800, 3600801, 3600803
CORE_ARCHETYPE = Archetype("c4540", 454000, 454000, 0)
PHASE_ARCHETYPE = Archetype("c4541", 454100, 454100, 0)
SUPPORT_ARCHETYPE = Archetype("c4543", 454300, 454300, 0)
ARENAS = (
    CLERIC_ARENA,
    BSB_ARENA,
    PAARL_ARENA,
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    EBRIETAS_ARENA,
)
CO_OP_RESTORE_EVENTS = {
    "cleric-beast": 12411703,
    "blood-starved-beast": 12301803,
    "darkbeast-paarl": 12301703,
    "vicar-amelia": 12401804,
    "amygdala": 13301803,
    "ebrietas": 12421803,
}

SOURCE_HASHES = {
    0: "a6c55dfa6a26dbb4d086f2eb73a12d3956a1dec570699dfbc6c63d0f51fb54b3",
    13601800: "5423c79a2613f564aecbc24658b5b30152c08acb21ede1e817a15abeb5c66c38",
    13604802: "8d7b309380f51d2933c573d286cee4ecdb4dc2797376c16dead9078df7f28fb9",
    13604803: "f6754136d8003799fd8c001053980bb67f25b033108b690852d0b0aedd128e72",
    13604804: "1360cbaab6065617a103ca2668dc2e601b10ea73bb97099a59055ad48f074d4e",
    13604820: "81c25057e062e5cf3d4728af2ba34359bc8b7c75ee28ded6ea7eb8519decd443",
    13604830: "fcec0fd932510a899f0e1a31433ee06438f56f0e0ec27b0ae5e24dc539de57ec",
    13604840: "027beee553830c6635d9452f708c0bcb95ca95fb53239bd6e12d5e764c32f75c",
    13604850: "de7acf9de30e70460a229e9f489b52eb00ab51289317a6b81d80382a67e6ddf1",
}
SOURCE_ALTERNATES = {
    0: "d9c76c6c7fcd7efe7eb641d470519cd217d70561ec8a81962f5248a76e316cb7",
    13604802: "54cb28efcdc5dbf46afd69ebfa6155d8635a61770e8f2375c6be127a8fb44004",
}
PART_PINS = {
    CORE: "35eb4a762d39a03f2b99e8407adc8e0fd73d55f01cb84462a15cbb53cd58e2e1",
    PHASE: "770be2af7c4bc6ca097b2bdb3644b13796a16cf271653e504632efb5befc6f36",
    SUPPORT: "4561475addb4ed1a4f1e085153b03c8c3ba58907e89bf979bc64b2e0804c1dce",
}
SOURCE_PARTS = {CORE: "c4540_0000", PHASE: "c4541_0000", SUPPORT: "c4543_0000"}
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}


@dataclass(frozen=True)
class OrphanDonorAllocation:
    phase_event: int = 12995500
    support_event: int = 12995501
    player_effect_event: int = 12995502
    phase_camera_event: int = 12995503
    terminal_bridge_event: int = 12995504
    combat_ready_flag: int = 12995505
    notification_flag: int = 12995506
    phase_entity: int = 983000
    support_entity: int = 983001

    def values(self) -> tuple[int, ...]:
        return (
            self.phase_event,
            self.support_event,
            self.player_effect_event,
            self.phase_camera_event,
            self.terminal_bridge_event,
            self.combat_ready_flag,
            self.notification_flag,
            self.phase_entity,
            self.support_entity,
        )


DEFAULT_ALLOCATION = OrphanDonorAllocation()


def _literals(text: str) -> set[int]:
    return {int(x) for x in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for blob in read_prefix(BUNDLE, prefix).values():
            values.update(_literals(blob.decode("utf-8-sig")))
    return frozenset(values)


def _validate(allocation: OrphanDonorAllocation, destination: str = "") -> None:
    values = allocation.values()
    if (
        len(values) != len(set(values))
        or any(value <= 0 for value in values)
        or set(values) & (_original_literals() | _literals(destination))
    ):
        raise ValueError("Orphan donor allocation collides with original inputs")


def _verify(
    blocks: Mapping[int, str],
    expected: Mapping[int, str],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> None:
    for event_id, digest in expected.items():
        actual = hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest()
        allowed = {digest}
        if alternates and event_id in alternates:
            allowed.add(alternates[event_id])
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Orphan donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda m: str(mapping.get(int(m[0]), int(m[0]))),
        text,
    )


def _noop(block: str) -> str:
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


def _retired(arena: ArenaContract) -> set[int]:
    return {
        x
        for x in (
            *arena.phase_slots,
            arena.part_routine_event,
            arena.cloth_routine_event,
            arena.attachment_anchor_event,
        )
        if x is not None
    }


def _telemetry(source: str, destination: str) -> str:
    result = source
    for name in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line for line in source.splitlines() if line.strip().startswith(name + "(")
        ]
        dest_lines = [
            line
            for line in destination.splitlines()
            if line.strip().startswith(name + "(")
        ]
        if len(source_lines) != 1 or len(dest_lines) != 1:
            raise ValueError(f"Orphan telemetry lacks unique {name}")
        result = _replace_once(
            result, source_lines[0], dest_lines[0], "destination telemetry"
        )
    return result


def _notification_flag(
    destination_health: str, allocation: OrphanDonorAllocation
) -> int:
    match = re.search(
        r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification\(0\);",
        destination_health,
    )
    if match is None:
        # Some original health bodies notify unconditionally; use a project
        # flag while preserving their destination entry notification.
        return allocation.notification_flag
    return int(match[1])


def _mark_existing_entry_notification(block: str, notification_flag: int) -> str:
    """Make copied health share an already-issued destination notification."""
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(
        witness,
        witness + f"        SetEventFlag({notification_flag}, ON);\n",
        1,
    )


def _activation(arena: ArenaContract, block: str) -> str:
    pattern = re.compile(
        rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", re.MULTILINE
    )
    result, count = pattern.subn("", block)
    if count == 0:
        raise ValueError(f"{arena.key} activation lacks destination animation")
    if f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result:
        if f"    SetCharacterMaphits({arena.actor}, true);\n" in result:
            for line in (
                f"    SetCharacterMaphits({arena.actor}, true);\n",
                f"    SetCharacterMaphits({arena.actor}, false);\n",
                f"    SetCharacterGravity({arena.actor}, Disabled);\n",
                f"    SetCharacterGravity({arena.actor}, Enabled);\n",
                "    WaitFixedTimeFrames(30);\n",
                "    WaitFixedTimeFrames(160);\n",
            ):
                result = _replace_once(result, line, "", "model entry state")
        else:
            result = _replace_once(
                result, "    WaitFixedTimeFrames(70);\n", "", "model entry delay"
            )
    if f"    SetCharacterImmortality({arena.actor}, Enabled);\n" in result:
        for line in (
            f"    SetSpEffect({arena.actor}, 5647, false);\n",
            f"    ClearSpEffect({arena.actor}, 5647);\n",
        ):
            result = _replace_once(result, line, "", "model entry effect")
    return result


def _music(arena: ArenaContract, block: str, phase_event: int) -> str:
    replacement = f"EventFlag({phase_event})"
    if arena.phase_music_message is None:
        return _replace_once(
            block,
            f"EventFlag({arena.part_routine_event})",
            replacement,
            "destination music phase flag",
        )
    witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    return _replace_once(block, witness, replacement, "destination music phase message")


def _constructor(
    arena: ArenaContract, block: str, allocation: OrphanDonorAllocation
) -> str:
    anchors = [
        f"    $InitializeEvent(0, {event});"
        for event in reversed(arena.phase_slots)
        if block.count(f"    $InitializeEvent(0, {event});") == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} lacks initializer anchor")
    calls = "\n".join(
        f"    $InitializeEvent(0, {event});"
        for event in (
            allocation.phase_event,
            allocation.support_event,
            allocation.player_effect_event,
            allocation.phase_camera_event,
            allocation.terminal_bridge_event,
        )
    )
    return _replace_once(
        block, anchors[0], anchors[0] + "\n" + calls, "destination constructor anchor"
    )


def _mapping(
    arena: ArenaContract, allocation: OrphanDonorAllocation, notification_flag: int
) -> dict[int, int]:
    return {
        CORE: arena.actor,
        PHASE: allocation.phase_entity,
        SUPPORT: allocation.support_entity,
        13601800: arena.completion_event,
        13604802: arena.health_bar_event,
        13604803: arena.music_event,
        13604804: arena.lockcam_event,
        13604808: arena.start_flag,
        13604810: notification_flag,
        13604812: allocation.combat_ready_flag,
        13604820: allocation.phase_event,
        13604830: allocation.support_event,
        13604840: allocation.player_effect_event,
        13604850: allocation.phase_camera_event,
    }


def _health(
    arena: ArenaContract, source: str, destination: str, mapping: Mapping[int, int]
) -> str:
    result = _replace_once(
        source,
        "    SetCharacterAIState(3600801, Disabled);\n",
        "    SetCharacterAIState(3600801, Disabled);\n"
        "    ChangeCharacterEnableState(3600801, Disabled);\n"
        "    SetCharacterAIState(3600803, Disabled);\n"
        "    SetCharacterHPBarDisplay(3600803, Disabled);\n"
        "    ChangeCharacterEnableState(3600803, Disabled);\n",
        "phase/support startup",
    )
    result = _replace_once(
        result,
        "L5:\n    if (!EventFlag(13604820)) {",
        "L5:\n    if (EventFlag(13604820)) {\n"
        "        ChangeCharacterEnableState(3600801, Enabled);\n"
        "    }\n"
        "    if (!EventFlag(13604820)) {",
        "saved phase visibility",
    )
    result = _remap(result, mapping)
    return _telemetry(result, destination)


def _phase(source: str, mapping: Mapping[int, int]) -> str:
    source = _replace_once(
        source,
        "    ChangeCharacterEnableState(3600800, Disabled);\n"
        "    SetCharacterGravity(3600801, Enabled);",
        "    ChangeCharacterEnableState(3600800, Disabled);\n"
        "    ChangeCharacterEnableState(3600801, Enabled);\n"
        "    SetCharacterGravity(3600801, Enabled);",
        "phase enable",
    )
    return _remap(source, mapping)


def _support(source: str, mapping: Mapping[int, int]) -> str:
    source = _replace_once(
        source,
        "    WaitFor(CharacterHasEventMessage(3600801, 100));\n"
        "    RequestCharacterAICommand(3600803, 10, 0);",
        "    WaitFor(CharacterHasEventMessage(3600801, 100));\n"
        "    ChangeCharacterEnableState(3600803, Enabled);\n"
        "    SetCharacterAIState(3600803, Enabled);\n"
        "    RequestCharacterAICommand(3600803, 10, 0);",
        "support enable",
    )
    return _remap(source, mapping)


def _camera(
    source: str, mapping: Mapping[int, int], arena: ArenaContract, event_id: int
) -> str:
    result = _remap(source, {**mapping, 13604804: event_id})
    result, count = re.subn(
        r"SetLockcamSlotNumber\((?:34|36), 0,",
        f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
        result,
    )
    if count == 0:
        raise ValueError("Orphan camera lacks source lockcam witnesses")
    return result


def _bridge(arena: ArenaContract, allocation: OrphanDonorAllocation) -> str:
    return f"""$Event({allocation.terminal_bridge_event}, Default, function() {{
    if (EventFlag({arena.completion_event}) || ThisEvent()) {{
        ChangeCharacterEnableState({allocation.phase_entity}, Disabled);
        ForceCharacterDeath({allocation.phase_entity}, false);
        ChangeCharacterEnableState({allocation.support_entity}, Disabled);
        ForceCharacterDeath({allocation.support_entity}, false);
        EndEvent();
    }}
L0:
    WaitFor(EventFlag({allocation.combat_ready_flag}));
    coreDead = CharacterDead({arena.actor});
    phaseDead = CharacterDead({allocation.phase_entity});
    WaitFor(coreDead || phaseDead);
    ForceCharacterDeath({arena.actor}, false);
    WaitFor(EventFlag({arena.completion_event}));
    ChangeCharacterEnableState({allocation.phase_entity}, Disabled);
    ForceCharacterDeath({allocation.phase_entity}, false);
    ChangeCharacterEnableState({allocation.support_entity}, Disabled);
    ForceCharacterDeath({allocation.support_entity}, false);
}});"""


def orphan_donor_contract(
    arena: ArenaContract, allocation: OrphanDonorAllocation = DEFAULT_ALLOCATION
) -> dict:
    _validate(allocation)
    return {
        "format": "bb-orphan-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": "orphan-of-kos",
        "allocation": asdict(allocation),
        "preserved_destination_events": [
            arena.completion_event,
            CO_OP_RESTORE_EVENTS[arena.key],
        ],
        "adapted_destination_events": [
            arena.activation_event,
            arena.health_bar_event,
            arena.music_event,
            arena.lockcam_event,
        ],
        "retired_destination_controllers": sorted(_retired(arena)),
        "copied_source_events": [
            {
                "source_event": source,
                "destination_event": target,
                "expected_source_sha256": SOURCE_HASHES[source],
                "allowed_source_sha256s": sorted(
                    {
                        SOURCE_HASHES[source],
                        *(
                            ()
                            if source not in SOURCE_ALTERNATES
                            else (SOURCE_ALTERNATES[source],)
                        ),
                    }
                ),
            }
            for source, target in (
                (13604802, arena.health_bar_event),
                (13604804, arena.lockcam_event),
                (13604820, allocation.phase_event),
                (13604830, allocation.support_event),
                (13604840, allocation.player_effect_event),
                (13604850, allocation.phase_camera_event),
            )
        ],
        "destination_owned_health_telemetry": {
            "event": arena.health_bar_event,
            "instructions": ["CreatePlaylog", "StartTimeMeasurement"],
        },
        "source_owned_not_copied": [
            13601800,
            13601801,
            13604800,
            13604801,
            13604811,
            3600802,
            3601800,
            3601801,
            3602800,
            3602801,
            3602805,
        ],
        "asset_dependency_gap": (
            "No typed EMEVD FXR witness exists; character-driven AI/TAE/behavior/"
            "bullet/FXR closure remains unproven by current original inputs"
        ),
        "terminal_policy": "core-or-phase death bridges to destination primary; progression remains exact",
        "runtime_status": "unobserved",
    }


def patch_orphan_donor(
    arena: ArenaContract,
    destination: str,
    donor_source: str,
    allocation: OrphanDonorAllocation = DEFAULT_ALLOCATION,
) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, SOURCE_HASHES, "Orphan donor", SOURCE_ALTERNATES)
    _validate(allocation, destination)
    notification = _notification_flag(original[arena.health_bar_event], allocation)
    mapping = _mapping(arena, allocation, notification)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    activation = _activation(arena, original[arena.activation_event])
    if notification == allocation.notification_flag:
        activation = _mark_existing_entry_notification(activation, notification)
    edits.update(
        {
            0: _constructor(arena, original[0], allocation),
            arena.activation_event: activation,
            arena.health_bar_event: _health(
                arena, donor[13604802], original[arena.health_bar_event], mapping
            ),
            arena.music_event: _music(
                arena, original[arena.music_event], allocation.phase_event
            ),
            arena.lockcam_event: _camera(
                donor[13604804], mapping, arena, arena.lockcam_event
            ),
        }
    )
    additions = [
        _phase(donor[13604820], mapping),
        _support(donor[13604830], mapping),
        _remap(donor[13604840], mapping),
        _camera(donor[13604850], mapping, arena, allocation.phase_camera_event),
        _bridge(arena, allocation),
    ]
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    added = {
        allocation.phase_event,
        allocation.support_event,
        allocation.player_effect_event,
        allocation.phase_camera_event,
        allocation.terminal_bridge_event,
    }
    if set(output) != set(original) | added:
        raise ValueError("Orphan donor changed unexpected event identities")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"Orphan donor changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Orphan donor changed destination progression")
    return result


def _source(slots: Sequence[Slot], entity: int, archetype: Archetype) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == "m36_00_00_00"
        and slot.entity_id == entity
        and slot.archetype == archetype
        and slot.part_name == SOURCE_PARTS[entity]
    ]
    if len(found) != 1 or found[0].talk_id:
        raise ValueError(f"Orphan lacks exact source actor {entity}")
    return found[0]


def _native(source: Slot, *, anchored: bool = False) -> dict:
    provenance = {
        "format": "bb-boss-actor-pin-v1",
        "part_sha256": PART_PINS[source.entity_id],
    }
    if anchored:
        provenance["anchor_sha256"] = PART_PINS[CORE]
    result = {
        "source_provenance": provenance,
        "source_initialization": dict(SOURCE_INITIALIZATION),
    }
    if anchored:
        result["source_part_kind"] = "enemy"
    return result


def native_plan_orphan_donor(
    arena: ArenaContract,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: OrphanDonorAllocation = DEFAULT_ALLOCATION,
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
        raise ValueError(f"Orphan/{arena.key} lacks destination state closure")
    core = _source(slots, CORE, CORE_ARCHETYPE)
    phase = _source(slots, PHASE, PHASE_ARCHETYPE)
    support = _source(slots, SUPPORT, SUPPORT_ARCHETYPE)
    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype,
        CORE_ARCHETYPE,
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
    primary = []
    additions = []
    for target in destinations:
        row = {
            "source_map": core.map_name,
            "source_part": core.part_name,
            "source_event_file": "event/" + EVENT_FILE,
            "source_entity_id": core.entity_id,
            "source_archetype": asdict(core.archetype),
            "source_talk_id": 0,
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
            **_native(core),
        }
        primary.append(row)
        for source, entity, part in (
            (phase, allocation.phase_entity, "ap_orphan_phase"),
            (support, allocation.support_entity, "ap_orphan_support"),
        ):
            additions.append(
                {
                    "source_map": source.map_name,
                    "source_event_file": "event/" + EVENT_FILE,
                    "source_part": source.part_name,
                    "source_anchor_part": core.part_name,
                    "source_entity_id": source.entity_id,
                    "source_archetype": asdict(source.archetype),
                    "destination_map": target.map_name,
                    "destination_anchor_part": target.part_name,
                    "destination_part": part,
                    "destination_entity_id": entity,
                    "allocation_evidence": "Orphan reusable donor allocation v1; original corpus and project ledger scan",
                    "required_native_fields": [
                        "source_provenance",
                        "source_initialization",
                    ],
                    **_native(source, anchored=True),
                }
            )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-orphan-of-kos"},
        "boss_contract": {
            **orphan_donor_contract(arena, allocation),
            "helper_scaling_parent": {
                f"{row['destination_map']}:{row['destination_part']}": destinations[
                    0
                ].logical_key
                for row in additions
            },
        },
        "primary_init_source_bindings": primary,
        "boss_actor_additions": additions,
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [x.json() for x in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def portable_orphan_arenas(
    arenas: Sequence[ArenaContract] = ARENAS,
) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
