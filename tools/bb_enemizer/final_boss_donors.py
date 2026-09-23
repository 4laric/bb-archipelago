"""Reusable source-pinned Gehrman and Moon Presence combat donors.

The receiving arena owns entry geometry, fog, music objects, telemetry,
completion, rewards, and progression.  These adapters copy the original m21
combat controllers only.  Character TAE roots are documented but their effect
asset delivery remains incomplete, so this module makes no runtime claim.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_contracts import (
    AMELIA_ARENA,
    AMYGDALA_ARENA,
    BSB_ARENA,
    CLERIC_ARENA,
    EBRIETAS_ARENA,
    PAARL_ARENA,
    ArenaContract,
    CombatPackage,
)
from .final_boss_contracts import GEHRMAN_PACKAGE, MOON_PACKAGE
from .maria_contract import _noop, _replace_events, _replace_once, _verify, event_blocks
from .maria_donor import _activation_without_destination_animations
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
SUPPORTED_FINAL_BOSS_ARENAS = (
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
GEHRMAN_OWNER = 2100801
GEHRMAN_OWNER_ARCHETYPE = Archetype("c9010", 901010, 1, 0)
GEHRMAN_PRIMARY_PIN = "1c42091a9cacab2c22f7bc0056deafca140095a619fd1c68716158257427abc0"
GEHRMAN_OWNER_PIN = "87508ce80a4eccf3c5637e7db80b080791f6ce1e8e7ffa2ab41c3bcb7e958352"
MOON_PRIMARY_PIN = "fb6b3c45b1c16ec4aa7bc8ff6cb2107caa06f98a4e6c26bd7f0d3064f84f4e67"
SOURCE_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
GEHRMAN_INITIALIZATION = {**SOURCE_INITIALIZATION, "talk_id": 210306}
GEHRMAN_SOURCE_PINS = {
    0: "fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26",
    12104802: "bb30fd6ca62dc57db799c576e84be78be221eb761ca6350da0197452f0bee570",
    12104804: "13744977311646856c93a3cecc6b3067ae98d9fe804bd75236bda4ab1622a4c8",
    12104807: "982f550c29fffaed7203de03d2bc1740b45c92f9ccfede0f249f0696ad00adab",
    12104808: "357e7c711dc72e7316a1ecf4f3ea6d0a07453e31cbdf6a1cb6f99e3b1b2e596d",
}
MOON_SOURCE_PINS = {
    0: "fa40b334c1c2f7972b424b1332d9d23d4ed68c2c120f463c194431e46533df26",
    12104852: "a4022f49059e7bc5cb6a076481065f8418a885876121ec9a8f731120ccfe395e",
    12104854: "32ebde44a49a6b7a58b9ab4bc6b84e3187e8d3fb5721ef6ab19bab853ba65fe4",
    12104860: "5b91d32d18d586cd20510e5157b5ca35b7783efe137e6120dfd2c60d62cd6af9",
    12104870: "dc32a765534443ea5b41c0d1646f0d658417d29c359357cfb6daf1d00d483ad6",
}


@dataclass(frozen=True)
class PhysicalAuxiliary:
    source_entity: int
    source_part: str
    source_archetype: Archetype
    source_pin: str
    source_initialization: Mapping[str, int]
    destination_part: str


@dataclass(frozen=True)
class FinalBossDonor:
    package: CombatPackage
    source_pins: Mapping[int, str]
    physical_auxiliaries: tuple[PhysicalAuxiliary, ...]
    music_message: int
    source_owned_not_copied: tuple[int, ...]

    @property
    def key(self) -> str:
        return self.package.key

    @property
    def event_file(self) -> str:
        return self.package.event_file


GEHRMAN_DONOR = FinalBossDonor(
    GEHRMAN_PACKAGE,
    GEHRMAN_SOURCE_PINS,
    (
        PhysicalAuxiliary(
            GEHRMAN_OWNER,
            "c9010_0004",
            GEHRMAN_OWNER_ARCHETYPE,
            GEHRMAN_OWNER_PIN,
            SOURCE_INITIALIZATION,
            "ap_gehrman_event_target",
        ),
    ),
    100,
    (12100146, 12101800, 12101802, 12101803, 12104803, 12104805),
)
MOON_DONOR = FinalBossDonor(
    MOON_PACKAGE,
    MOON_SOURCE_PINS,
    (),
    500,
    (12101850, 12101852, 12101853, 12104853, 12104855),
)


@dataclass(frozen=True)
class FinalBossAllocation:
    gehrman_phase_event: int = 12996000
    gehrman_effect_cleanup_event: int = 12996001
    gehrman_owner_cleanup_event: int = 12996002
    gehrman_health_initialized_flag: int = 12996003
    moon_limb_event: int = 12996004
    moon_player_protection_event: int = 12996005
    moon_health_initialized_flag: int = 12996006
    gehrman_owner_entity: int = 983500

    def values(self) -> tuple[int, ...]:
        return (
            self.gehrman_phase_event,
            self.gehrman_effect_cleanup_event,
            self.gehrman_owner_cleanup_event,
            self.gehrman_health_initialized_flag,
            self.moon_limb_event,
            self.moon_player_protection_event,
            self.moon_health_initialized_flag,
            self.gehrman_owner_entity,
        )


DEFAULT_FINAL_BOSS_ALLOCATION = FinalBossAllocation()


def portable_final_boss_donors() -> tuple[FinalBossDonor, ...]:
    return (GEHRMAN_DONOR, MOON_DONOR)


def _numeric_literals(text: str) -> set[int]:
    return {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_game_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            values.update(_numeric_literals(body.decode("utf-8-sig")))
    return frozenset(values)


def validate_final_boss_allocation(
    allocation: FinalBossAllocation, original_sources: Iterable[str] = ()
) -> None:
    values = allocation.values()
    expected = (*range(12996000, 12996007), 983500)
    if values != expected:
        raise ValueError(
            "final-boss donors require the exact reviewed narrow allocation"
        )
    if len(values) != len(set(values)) or any(value <= 0 for value in values):
        raise ValueError("final-boss donor allocation must be unique and positive")
    collisions = set(values) & _original_game_literals()
    for source in original_sources:
        collisions.update(set(values) & _numeric_literals(source))
    if collisions:
        raise ValueError(
            f"final-boss donor allocation collides with original inputs: {sorted(collisions)}"
        )


def _numbers(text: str, replacements: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(replacements.get(int(match[0]), int(match[0]))),
        text,
    )


def _events_for(
    donor: FinalBossDonor, allocation: FinalBossAllocation
) -> tuple[tuple[int, int], ...]:
    if donor is GEHRMAN_DONOR:
        return (
            (12104807, allocation.gehrman_phase_event),
            (12104808, allocation.gehrman_effect_cleanup_event),
        )
    if donor is MOON_DONOR:
        return (
            (12104860, allocation.moon_limb_event),
            (12104870, allocation.moon_player_protection_event),
        )
    raise ValueError("unsupported final-boss donor object")


def _health_flag(donor: FinalBossDonor, allocation: FinalBossAllocation) -> int:
    if donor is GEHRMAN_DONOR:
        return allocation.gehrman_health_initialized_flag
    if donor is MOON_DONOR:
        return allocation.moon_health_initialized_flag
    raise ValueError("unsupported final-boss donor object")


def _mark_existing_entry_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    count = block.count(witness)
    if count > 1:
        raise ValueError("destination entry notification witness is not unique")
    if count == 0:
        return block
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _destination_health_telemetry(source_health: str, destination_health: str) -> str:
    result = source_health
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        source_lines = [
            line
            for line in source_health.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        destination_lines = [
            line
            for line in destination_health.splitlines()
            if line.strip().startswith(instruction + "(")
        ]
        if len(source_lines) != 1 or len(destination_lines) != 1:
            raise ValueError(
                f"health telemetry requires one source and destination {instruction} witness"
            )
        result = _replace_once(
            result,
            source_lines[0],
            destination_lines[0],
            f"destination-owned health {instruction}",
        )
    return result


def _health(
    arena: ArenaContract,
    donor: FinalBossDonor,
    source: str,
    destination: str,
    allocation: FinalBossAllocation,
) -> str:
    package = donor.package
    flag = _health_flag(donor, allocation)
    mapping = {
        package.health_bar_event: arena.health_bar_event,
        package.actor: arena.actor,
        package.completion_event: arena.completion_event,
        package.start_flag: arena.start_flag,
    }
    if donor is GEHRMAN_DONOR:
        mapping[GEHRMAN_OWNER] = allocation.gehrman_owner_entity
    result = _numbers(source, mapping)
    notification = "            IssueBossRoomEntryNotification(0);"
    result = _replace_once(
        result,
        notification,
        f"            if (!EventFlag({flag})) {{\n"
        f"                IssueBossRoomEntryNotification(0);\n"
        f"            }}",
        "source room-entry notification",
    )
    start = f"    SetEventFlag({arena.start_flag}, ON);"
    result = _replace_once(
        result,
        start,
        start + f"\n    SetEventFlag({flag}, ON);",
        "source health initialization",
    )
    return _destination_health_telemetry(result, destination)


def _destination_music(arena: ArenaContract, block: str, message: int) -> str:
    replacement = f"CharacterHasEventMessage({arena.actor}, {message})"
    if arena.phase_music_message is None:
        event_flag = arena.phase_music_event_flag or arena.part_routine_event
        if event_flag is None:
            raise ValueError(f"{arena.key} music has no declared phase boundary")
        return _replace_once(
            block,
            f"EventFlag({event_flag})",
            replacement,
            "destination music phase flag",
        )
    witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    if block.count(witness) != 1:
        raise ValueError(f"{arena.key} music lacks its declared phase-message witness")
    return block if witness == replacement else block.replace(witness, replacement, 1)


def _lockcam(arena: ArenaContract, donor: FinalBossDonor, source: str) -> str:
    package = donor.package
    result = _numbers(
        source,
        {
            package.lockcam_event: arena.lockcam_event,
            package.actor: arena.actor,
            package.completion_event: arena.completion_event,
        },
    )
    old = f"SetLockcamSlotNumber({package.lockcam_map}, {package.lockcam_subarea},"
    new = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if result.count(old) != 2:
        raise ValueError(f"{donor.key} lockcam lacks its exact two-call witness")
    result = result.replace(old, new)
    guard = f"    EndIf(EventFlag({arena.completion_event}));\n"
    if guard not in result:
        header = result.splitlines()[0] + "\n"
        result = _replace_once(
            result, header, header + guard, "camera completion guard"
        )
    return result


def _initializer_line(slot: int, event: int, arguments: Sequence[str]) -> str:
    tail = "" if not arguments else ", " + ", ".join(arguments)
    return f"    $InitializeEvent({slot}, {event}{tail});"


def _constructor(
    arena: ArenaContract,
    donor: FinalBossDonor,
    destination_zero: str,
    donor_zero: str,
    allocation: FinalBossAllocation,
) -> str:
    targets = dict(_events_for(donor, allocation))
    calls: list[str] = []
    for attachment in donor.package.attachments:
        for binding in attachment.initializers:
            witness = _initializer_line(
                binding.slot, attachment.source_event, binding.arguments
            )
            if donor_zero.count(witness) != 1:
                raise ValueError(
                    f"{donor.key} Event(0) lacks unique initializer {witness.strip()}"
                )
            calls.append(
                _initializer_line(
                    binding.slot, targets[attachment.source_event], binding.arguments
                )
            )
    if donor is GEHRMAN_DONOR:
        calls.append(_initializer_line(0, allocation.gehrman_owner_cleanup_event, ()))
    anchors = [
        _initializer_line(0, event, ())
        for event in reversed(arena.phase_slots)
        if destination_zero.count(_initializer_line(0, event, ())) == 1
    ]
    if not anchors:
        raise ValueError(f"{arena.key} has no unique phase initializer anchor")
    anchor = anchors[0]
    return _replace_once(
        destination_zero,
        anchor,
        anchor + "\n" + "\n".join(calls),
        "final-boss attachment initializer anchor",
    )


def _attachment_bodies(
    arena: ArenaContract,
    donor: FinalBossDonor,
    blocks: Mapping[int, str],
    allocation: FinalBossAllocation,
) -> list[str]:
    targets = dict(_events_for(donor, allocation))
    mapping = {
        donor.package.actor: arena.actor,
        donor.package.completion_event: arena.completion_event,
        **targets,
    }
    if donor is GEHRMAN_DONOR:
        mapping[GEHRMAN_OWNER] = allocation.gehrman_owner_entity
    bodies = [
        _numbers(blocks[attachment.source_event], mapping)
        for attachment in donor.package.attachments
    ]
    if donor is MOON_DONOR:
        # Source 12104870 loops without a terminal guard.  The imported event
        # must not restart player-state work on a completed destination load.
        header = bodies[1].splitlines()[0] + "\n"
        guard = f"    EndIf(EventFlag({arena.completion_event}));\n"
        bodies[1] = _replace_once(
            bodies[1], header, header + guard, "Moon completion guard"
        )
    return bodies


def _owner_cleanup(arena: ArenaContract, allocation: FinalBossAllocation) -> str:
    return f"""$Event({allocation.gehrman_owner_cleanup_event}, Default, function() {{
    WaitFor(EventFlag({arena.completion_event}));
    ChangeCharacterEnableState({allocation.gehrman_owner_entity}, Disabled);
    SetCharacterAIState({allocation.gehrman_owner_entity}, Disabled);
    SetCharacterHPBarDisplay({allocation.gehrman_owner_entity}, Disabled);
    ForceCharacterDeath({allocation.gehrman_owner_entity}, false);
}});"""


def _retired_events(arena: ArenaContract) -> set[int]:
    retired = {
        *arena.phase_slots,
        *arena.retired_combat_events,
        *(() if arena.part_routine_event is None else (arena.part_routine_event,)),
        *(() if arena.cloth_routine_event is None else (arena.cloth_routine_event,)),
        *(
            ()
            if arena.attachment_anchor_event is None
            else (arena.attachment_anchor_event,)
        ),
    }
    # Cleric's old schema labels a cloth controller as its co-op event.  The
    # real, source-pinned client restore event is 12411703.  Use the explicit
    # map for all arenas so combat-controller retirement cannot consume a
    # client lifecycle routine.
    retired.discard(CO_OP_RESTORE_EVENTS[arena.key])
    return retired


def final_boss_donor_contract(
    arena: ArenaContract,
    donor: FinalBossDonor,
    allocation: FinalBossAllocation = DEFAULT_FINAL_BOSS_ALLOCATION,
) -> dict:
    validate_final_boss_allocation(allocation)
    copied = _events_for(donor, allocation)
    auxiliary = []
    if donor is GEHRMAN_DONOR:
        auxiliary.append(
            {
                "source_entity": GEHRMAN_OWNER,
                "destination_entity": allocation.gehrman_owner_entity,
                "source_part": "c9010_0004",
                "policy": "physical source-pinned event target; no invented EMEVD initializer",
            }
        )
    return {
        "format": "bb-final-boss-donor-contract-v1",
        "status": "experimental",
        "arena": arena.key,
        "donor": donor.key,
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
        "copied_source_events": [
            {
                "source_event": source_event,
                "destination_event": target_event,
                "expected_source_sha256": donor.source_pins[source_event],
            }
            for source_event, target_event in copied
        ],
        "source_owned_not_copied": list(donor.source_owned_not_copied),
        "retired_destination_controllers": sorted(_retired_events(arena)),
        "physical_auxiliaries": auxiliary,
        "music_policy": f"destination final track follows donor message {donor.music_message}",
        "destination_owned_health_telemetry": [
            "CreatePlaylog",
            "StartTimeMeasurement",
        ],
        "entrance_policy": "destination set-piece retained; destination-model animations removed; global replacement cinematic policy applies later",
        "asset_delivery": {
            "status": "incomplete",
            "evidence": "source character archive and typed TAE roots are pinned separately; recursive FXR/model/texture delivery is unresolved",
            "production_recipe_ready": False,
        },
        "runtime_status": "unobserved",
    }


def patch_final_boss_donor(
    arena: ArenaContract,
    donor: FinalBossDonor,
    destination: str,
    donor_source: str,
    allocation: FinalBossAllocation = DEFAULT_FINAL_BOSS_ALLOCATION,
) -> str:
    """Install one final-boss combat package without moving source progression."""
    if arena not in SUPPORTED_FINAL_BOSS_ARENAS:
        raise ValueError(f"unsupported final-boss destination arena {arena.key}")
    if donor not in portable_final_boss_donors():
        raise ValueError("unsupported final-boss donor object")
    original, source = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(source, dict(donor.source_pins), f"{donor.key} donor")
    validate_final_boss_allocation(allocation, (destination,))
    flag = _health_flag(donor, allocation)
    activation = _activation_without_destination_animations(
        arena, original[arena.activation_event]
    )
    activation = _mark_existing_entry_notification(activation, flag)
    edits = {event: _noop(original[event]) for event in _retired_events(arena)}
    edits.update(
        {
            0: _constructor(arena, donor, original[0], source[0], allocation),
            arena.activation_event: activation,
            arena.health_bar_event: _health(
                arena,
                donor,
                source[donor.package.health_bar_event],
                original[arena.health_bar_event],
                allocation,
            ),
            arena.music_event: _destination_music(
                arena, original[arena.music_event], donor.music_message
            ),
            arena.lockcam_event: _lockcam(
                arena, donor, source[donor.package.lockcam_event]
            ),
        }
    )
    additions = _attachment_bodies(arena, donor, source, allocation)
    if donor is GEHRMAN_DONOR:
        additions.append(_owner_cleanup(arena, allocation))
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(additions)
        + "\n"
    )
    output = event_blocks(result)
    expected = set(original) | {target for _, target in _events_for(donor, allocation)}
    if donor is GEHRMAN_DONOR:
        expected.add(allocation.gehrman_owner_cleanup_event)
    if set(output) != expected:
        raise ValueError("final-boss donor adapter changed unexpected event identities")
    for event, block in original.items():
        if event not in edits and output[event] != block:
            raise ValueError(
                f"final-boss donor adapter changed unrelated event {event}"
            )
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("final-boss donor adapter changed destination progression")
    return result


def _source_slot(slots: Sequence[Slot], donor: FinalBossDonor) -> Slot:
    matches = [
        slot
        for slot in slots
        if slot.map_name == "m21_00_00_00"
        and slot.entity_id == donor.package.actor
        and slot.archetype == donor.package.archetype
    ]
    expected_talk = 210306 if donor is GEHRMAN_DONOR else 0
    if len(matches) != 1 or matches[0].dummy or matches[0].talk_id != expected_talk:
        raise ValueError(f"{donor.key} requires its exact original primary part")
    return matches[0]


def _destination_slots(slots: Sequence[Slot], arena: ArenaContract) -> list[Slot]:
    result = [
        slot
        for slot in slots
        if slot.entity_id == arena.actor
        and slot.map_name.startswith(arena.map_prefix)
        and slot.archetype == arena.archetype
    ]
    if len(result) != arena.destination_count or any(
        slot.talk_id != 0 for slot in result
    ):
        raise ValueError(f"{arena.key} requires every exact original destination state")
    return sorted(result, key=lambda slot: slot.map_name)


def final_boss_actor_requirements(
    arena: ArenaContract,
    donor: FinalBossDonor,
    slots: Sequence[Slot],
    allocation: FinalBossAllocation = DEFAULT_FINAL_BOSS_ALLOCATION,
) -> list[dict]:
    validate_final_boss_allocation(allocation)
    if donor is MOON_DONOR:
        return []
    if donor is not GEHRMAN_DONOR:
        raise ValueError("unsupported final-boss donor object")
    destinations = _destination_slots(slots, arena)
    owners = [
        slot
        for slot in slots
        if slot.map_name == "m21_00_00_00"
        and slot.entity_id == GEHRMAN_OWNER
        and slot.part_name == "c9010_0004"
        and slot.archetype == GEHRMAN_OWNER_ARCHETYPE
    ]
    if len(owners) != 1 or owners[0].dummy or owners[0].talk_id != 0:
        raise ValueError("Gehrman requires its exact original event-target actor")
    owner = owners[0]
    return [
        {
            "source_map": owner.map_name,
            "source_event_file": "event/" + donor.event_file,
            "source_part": owner.part_name,
            "source_anchor_part": owner.part_name,
            "source_entity_id": owner.entity_id,
            "source_archetype": asdict(owner.archetype),
            "source_part_kind": "enemy",
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": GEHRMAN_OWNER_PIN,
                "anchor_sha256": GEHRMAN_OWNER_PIN,
            },
            "source_initialization": dict(SOURCE_INITIALIZATION),
            "destination_map": target.map_name,
            "destination_anchor_part": target.part_name,
            "destination_part": "ap_gehrman_event_target",
            "destination_entity_id": allocation.gehrman_owner_entity,
            "allocation_evidence": "final-boss reusable donor allocation v1; full bundled EMEVD/MSBB scan",
            "required_native_fields": [
                "source_provenance",
                "source_initialization",
            ],
        }
        for target in destinations
    ]


def native_plan_final_boss_donor(
    arena: ArenaContract,
    donor: FinalBossDonor,
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    allocation: FinalBossAllocation = DEFAULT_FINAL_BOSS_ALLOCATION,
) -> dict:
    """Build the actor/scaling plan; effect-asset delivery remains a hard gap."""
    validate_final_boss_allocation(allocation)
    source = _source_slot(slots, donor)
    destinations = _destination_slots(slots, arena)
    target = destinations[0]
    swap = Swap(
        target.logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        target.archetype,
        source.archetype,
        warnings=[
            "final-boss character effect delivery and runtime arena fit remain unvalidated"
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
    initialization = (
        GEHRMAN_INITIALIZATION if donor is GEHRMAN_DONOR else SOURCE_INITIALIZATION
    )
    primary_pin = GEHRMAN_PRIMARY_PIN if donor is GEHRMAN_DONOR else MOON_PRIMARY_PIN
    bindings = []
    for destination in destinations:
        binding = {
            "source_event_file": "event/" + donor.event_file,
            "source_map": source.map_name,
            "source_part": source.part_name,
            "source_entity_id": source.entity_id,
            "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": primary_pin,
            },
            "source_initialization": dict(initialization),
            "destination_map": destination.map_name,
            "destination_part": destination.part_name,
            "destination_entity_id": destination.entity_id,
            "destination_original_talk_id": destination.talk_id,
            "required_native_fields": [
                "talk_id",
                "unk_t18",
                "init_anim_id",
                "damage_anim_id",
                "provenance",
            ],
        }
        if donor is GEHRMAN_DONOR:
            binding["destination_talk_id_override"] = 0
            binding["required_native_fields"].append("destination_talk_id_override")
        bindings.append(binding)
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": final_boss_donor_contract(arena, donor, allocation),
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
