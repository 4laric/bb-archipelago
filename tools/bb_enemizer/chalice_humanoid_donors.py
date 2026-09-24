"""Source-pinned Chalice humanoid donors for six base arenas and Lady Maria.

The three selected m29 maps initialize the same generic boss routines from
``m29.emevd``. Their map-specific Event(0) calls are pinned below, while the
actor's original NpcParam, ThinkParam, and MSB initialization are transferred
by the native writer. The 500 message driving phase music is actor-owned; none
of these maps initializes the generic half-health AI-command event 12904888.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .boss_canary import event_blocks
from .boss_contracts import ARENAS, ArenaContract, CLERIC_ARENA
from .boss_entrances import skip_replacement_entrance
from .gascoigne_donor import CO_OP_RESTORE_EVENTS, _retired
from .maria_donor import _activation_without_destination_animations
from .maria_contract import MARIA_ARENA, MARIA_PACKAGE
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

COMMON_EVENT_FILE = "m29.emevd.dcx.js"
COMMON_EVENT_PINS = {
    12906806: "f508ee03fbf412e0827cc2433172f06f909bded3304babdb0ecc05a46e846d70",
    12906810: "8adc0ff9c8501b35d7e7b6b2d9fa067f27f4977a42311555349d304e96a019dd",
    12906818: "de931fc6e381396e073b146db1a013f1234796484d44fc69f23a224f98ff9161",
    12901697: "877aeceb56254641390d8499c156ab774184522f2fce56e493fc12573f1c0320",
}
SOURCE_INITIALIZATION = {
    "talk_id": 0, "unk_t18": 0, "init_anim_id": -1, "damage_anim_id": -1,
}
MARIA_HUMANOID_ARENA = ArenaContract(
    key=MARIA_PACKAGE.key, event_file=MARIA_PACKAGE.event_file,
    map_prefix=MARIA_PACKAGE.map_prefix, actor=MARIA_PACKAGE.actor,
    archetype=MARIA_PACKAGE.archetype, destination_count=1,
    completion_event=MARIA_ARENA.completion_event,
    start_flag=MARIA_ARENA.encounter_start_flag,
    health_bar_event=MARIA_ARENA.health_event,
    health_bar_label=MARIA_PACKAGE.health_bar_label,
    activation_event=MARIA_ARENA.cutscene_entry_event,
    music_event=MARIA_ARENA.music_event,
    phase_music_message=100,
    lockcam_event=MARIA_ARENA.lockcam_event,
    lockcam_map=35, lockcam_subarea=0,
    phase_slots=(MARIA_ARENA.phase_cleanup_event,),
    co_op_entry_event=MARIA_ARENA.co_op_restore_event,
    part_routine_event=None, cloth_routine_event=None,
    part_slots=(), attachment_event_ids=(), virtual_entity_ids=(),
    attachment_anchor_slot=None, attachment_anchor_event=None,
    expected=MARIA_PACKAGE.expected,
    music_phase_messages=(100, 300),
)
SUPPORTED_BASE_ARENAS = ARENAS
SUPPORTED_SPECIAL_ARENAS = (MARIA_HUMANOID_ARENA,)
SUPPORTED_HUMANOID_ARENAS = (*SUPPORTED_BASE_ARENAS, *SUPPORTED_SPECIAL_ARENAS)


@dataclass(frozen=True)
class ChaliceHumanoidDonor:
    key: str
    map_name: str
    part_name: str
    actor: int
    archetype: Archetype
    health_name_id: int
    completion_flag: int
    start_flag: int
    health_started_flag: int
    part_sha256: str
    map_event_zero_sha256: str
    # Exact generic routine calls witnessed in the selected map Event(0).
    health_initializer: str
    music_initializer: str
    wake_initializer: str
    wake_animation: int | None
    event_file: str = COMMON_EVENT_FILE


DONORS = {
    "pthumerian-descendant": ChaliceHumanoidDonor(
        "pthumerian-descendant", "m29_50_90_00", "c3050_0000", 2900100,
        Archetype("c3050", 10305006, 305000, 0), 305001,
        12901800, 12905504, 12905506,
        "ece20f217a216c1c94334282104673cf3041ff1b569c51a44fd29af3417bc224",
        "12fea30fbbc0bb5e9f524289598e814ac11164ec1bd0514d462f4d4bf79d1ed5",
        "$InitializeEvent(0, 12906806, 2900100, 305001, 12901800, 12905504, 12905506);",
        "$InitializeEvent(0, 12906810, 2900100, 2903049, 2903048, 2903050, 12901800, 12905506, 12905505);",
        "$InitializeEvent(0, 12901697, 2900100, 2903051, 7000, 7001, 12901800, 12905504, 12900530, 12900006);",
        7001,
    ),
    "pthumerian-elder": ChaliceHumanoidDonor(
        "pthumerian-elder", "m29_31_90_00", "c3050_0000", 2900109,
        Archetype("c3050", 210305016, 305010, 0), 305002,
        12901802, 12905513, 12905515,
        "1435c26e3caec4e5a5482de073d2e23d7633d6d24f7da433e29c60bf392bf523",
        "67bd1b403e2fb2ff908e39aea4c1f0be88f51b0b66d8783230b58a1c43b6f3e4",
        "$InitializeEvent(1, 12906806, 2900109, 305002, 12901802, 12905513, 12905515);",
        "$InitializeEvent(1, 12906810, 2900109, 2903063, 2903062, 2903064, 12901802, 12905515, 12905514);",
        "$InitializeEvent(0, 12901697, 2900109, 2903071, 7000, 7001, 12901802, 12905513, 12900540, 12900016);",
        7001,
    ),
    "keeper-of-old-lords": ChaliceHumanoidDonor(
        "keeper-of-old-lords", "m29_40_90_00", "c2160_0000", 2900100,
        Archetype("c2160", 10216090, 216090, 0), 216000,
        12901800, 12905504, 12905506,
        "73ee2864d9cb9bc8ceab1c9e0a1400f84bf5c88c5354aa79f97f77fa7563528a",
        "093b156424bc238d1197f79765f830c5f3b37dd3d176432aec36a3f23c08dacd",
        "$InitializeEvent(0, 12906806, 2900100, 216000, 12901800, 12905504, 12905506);",
        "$InitializeEvent(0, 12906810, 2900100, 2903062, 2903061, 2903063, 12901800, 12905506, 12905505);",
        "$InitializeEvent(0, 12901701, 2900100, 2903064, 12901800, 12905504, 12900541, 12900009);",
        None,
    ),
}


def validate_source_map_witness(donor: ChaliceHumanoidDonor, map_source: str) -> None:
    """Validate the per-map constructor when original m29 game data is supplied."""
    source = event_blocks(map_source)
    block = source.get(0, "")
    if hashlib.sha256(block.encode()).hexdigest() != donor.map_event_zero_sha256:
        raise ValueError(f"{donor.key} map Event(0) drifted")
    for line in (donor.health_initializer, donor.music_initializer, donor.wake_initializer):
        if block.count(line) != 1:
            raise ValueError(f"{donor.key} map initializer drifted")
    if "12904888" in block:
        raise ValueError(f"{donor.key} has an unported EMEVD phase controller")


def _verify(arena: ArenaContract, destination: str, donor_source: str) -> tuple[dict[int, str], dict[int, str]]:
    if arena not in SUPPORTED_HUMANOID_ARENAS:
        raise ValueError("Chalice humanoid donor requires a reviewed base arena")
    original, common = event_blocks(destination), event_blocks(donor_source)
    for event_id, expected in arena.expected.items():
        if event_id not in original or hashlib.sha256(original[event_id].encode()).hexdigest() != expected:
            raise ValueError(f"{arena.key} event {event_id} drifted")
    for event_id, expected in COMMON_EVENT_PINS.items():
        if event_id not in common or hashlib.sha256(common[event_id].encode()).hexdigest() != expected:
            raise ValueError(f"m29 donor event {event_id} drifted")
    return original, common


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Chalice donor expected one {label}")
    return source.replace(old, new, 1)


def _noop(block: str) -> str:
    header = block.split("{\n", 1)[0]
    header = re.sub(r"function\(([^)]*)\)", lambda m: "function(" + ", ".join(
        (name if name.startswith("unused") else "unused_" + name)
        for name in (part.strip() for part in m[1].split(",")) if name
    ) + ")", header, count=1)
    return header + "{\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    from .bosses import parse_events

    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _health(arena: ArenaContract, donor: ChaliceHumanoidDonor, generic: str,
            destination: str) -> str:
    block = generic.replace(
        "$Event(12906806, Default, function(chrEntityId, nameId, eventFlagId, eventFlagId2, eventFlagId3) {",
        f"$Event({arena.health_bar_event}, Default, function() {{", 1,
    )
    block = _replace_once(block, "ThisEventSlot()", "ThisEvent()", "health event slot")
    for source, target in (
        ("chrEntityId", str(arena.actor)), ("nameId", str(donor.health_name_id)),
        ("eventFlagId3", str(arena.health_bar_event)),
        ("eventFlagId2", str(arena.start_flag)),
        ("eventFlagId", str(arena.completion_event)),
    ):
        block = re.sub(rf"\b{re.escape(source)}\b", target, block)
    # Dungeon globals and dungeon completion timing do not belong to the
    # surface arena. Preserve its own telemetry while transplanting the generic
    # health/AI/co-op lifecycle and the selected source's name identifier.
    for line in ("            SetEventFlag(12907230, OFF);\n",
                 "            SetEventFlag(12907231, OFF);\n"):
        block = _replace_once(block, line, "", "dungeon-only flag")
    telemetry = [line for line in destination.splitlines()
                 if line.strip().startswith(("CreatePlaylog(", "StartTimeMeasurement("))]
    if (len(telemetry) != 2 or not telemetry[0].strip().startswith("CreatePlaylog(")
            or not telemetry[1].strip().startswith("StartTimeMeasurement(")):
        raise ValueError(f"{arena.key} health telemetry drifted")
    block, count = re.subn(
        r"    CreatePlaylog\(1260\);\n(?:    if \(\d+ == 1290180[0-3]\) \{\n"
        r"        StartTimeMeasurement\([^\n]+\);\n    \}\n){4}",
        "\n".join(telemetry) + "\n", block,
    )
    if count != 1:
        raise ValueError("m29 health telemetry drifted")
    return block


def _activation(arena: ArenaContract, donor: ChaliceHumanoidDonor, original: str) -> str:
    if arena == CLERIC_ARENA:
        result = original
        for instruction in (
            f"    SetCharacterGravity({arena.actor}, Disabled);\n",
            f"    SetCharacterMaphits({arena.actor}, true);\n",
            f"    ForceAnimationPlayback({arena.actor}, 3028, false, false, false);\n",
            "    WaitFixedTimeFrames(110);\n",
            f"    SetCharacterGravity({arena.actor}, Enabled);\n",
            f"    SetCharacterMaphits({arena.actor}, false);\n",
        ):
            result = _replace_once(result, instruction, "", "Cleric-only entrance state")
    elif arena == MARIA_HUMANOID_ARENA:
        # Maria's first entry is a cutscene-triggered warp, with no native
        # c4520 animation in this event. The separate entrance policy removes
        # the cinematic while retaining its warp and arena-start flag.
        result = original
    else:
        result = _activation_without_destination_animations(arena, original)
    if donor.wake_animation is not None:
        result = _replace_once(
            result, f"    SetEventFlag({arena.start_flag}, ON);\n",
            f"    ForceAnimationPlayback({arena.actor}, {donor.wake_animation}, false, false, false);\n"
            f"    SetEventFlag({arena.start_flag}, ON);\n",
            "donor wake animation before arena start",
        )
    return result


def _music(arena: ArenaContract, original: str, generic: str) -> str:
    if arena == MARIA_HUMANOID_ARENA:
        # Maria owns three sound tracks and two c4520-specific phase messages.
        # The m29 map scripts witness one actor message-500 transition; reuse
        # the common m29 two-track body at Maria's pinned map sounds/room area.
        # The third track remains disabled and Maria's completion cleanup stays.
        block = generic.replace(
            "$Event(12906810, Default, function(chrEntityId, areaEntityId, entityId, entityId2, eventFlagId, eventFlagId2, eventFlagId3) {",
            f"$Event({arena.music_event}, Default, function() {{", 1,
        )
        block = _replace_once(block, "ThisEventSlot()", "ThisEvent()", "m29 music slot")
        for source, target in (
            ("chrEntityId", arena.actor), ("areaEntityId", 3502802),
            ("entityId2", 3503803), ("entityId", 3503802),
            ("eventFlagId3", MARIA_ARENA.co_op_entered_flag),
            ("eventFlagId2", arena.health_bar_event),
            ("eventFlagId", arena.completion_event),
        ):
            block = re.sub(rf"\b{source}\b", str(target), block)
        block = _replace_once(block,
            "    SetMapSoundState(3503803, Disabled);\n",
            "    SetMapSoundState(3503803, Disabled);\n"
            "    SetMapSoundState(3503804, Disabled);\n"
            "    DeleteMapSFX(3503501, false);\n",
            "Maria third track and phase effect shutdown")
        if (original.count("CharacterHasEventMessage(3500800, 100)") != 1
                or original.count("CharacterHasEventMessage(3500800, 300)") != 1):
            raise ValueError("Maria two-phase music witness drifted")
        return block
    if arena.phase_music_event_flag is not None:
        witness = f"EventFlag({arena.phase_music_event_flag})"
    elif arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        raise ValueError(f"{arena.key} has no reviewed phase-music boundary")
    return _replace_once(original, witness,
                         f"CharacterHasEventMessage({arena.actor}, 500)",
                         "actor-owned phase music message")


def patch_chalice_humanoid_donor(arena: ArenaContract, donor: ChaliceHumanoidDonor,
                                 destination: str, donor_source: str) -> str:
    """Retain destination progression; install m29 health and native-AI phase."""
    original, common = _verify(arena, destination, donor_source)
    retired = ({MARIA_ARENA.phase_cleanup_event} if arena == MARIA_HUMANOID_ARENA
               else _retired(arena))
    edits = {event_id: _noop(original[event_id]) for event_id in retired}
    edits.update({
        arena.activation_event: _activation(arena, donor, original[arena.activation_event]),
        arena.health_bar_event: _health(arena, donor, common[12906806], original[arena.health_bar_event]),
        arena.music_event: _music(arena, original[arena.music_event], common[12906810]),
    })
    result = skip_replacement_entrance(
        arena.key, destination, _replace_events(destination, edits)
    )
    output = event_blocks(result)
    if set(output) != set(original):
        raise ValueError("Chalice donor changed destination event identities")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"Chalice donor changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Chalice donor changed arena progression")
    co_op = (MARIA_ARENA.co_op_restore_event if arena == MARIA_HUMANOID_ARENA
             else CO_OP_RESTORE_EVENTS[arena.key])
    if output[co_op] != original[co_op]:
        raise ValueError("Chalice donor changed destination guest entry")
    return result


def native_plan_chalice_humanoid_donor(
    arena: ArenaContract, donor: ChaliceHumanoidDonor, slots: Sequence[Slot],
    npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
) -> dict:
    """Bind every destination map state to one exact source actor/initialization."""
    if arena not in SUPPORTED_HUMANOID_ARENAS:
        raise ValueError("Chalice humanoid donor requires a reviewed base arena")
    destinations = [slot for slot in slots if slot.entity_id == arena.actor
                    and slot.archetype == arena.archetype]
    sources = [slot for slot in slots if slot.map_name == donor.map_name
               and slot.part_name == donor.part_name and slot.entity_id == donor.actor
               and slot.archetype == donor.archetype]
    if (len(destinations) != arena.destination_count or len(sources) != 1
            or len({slot.map_name for slot in destinations}) != arena.destination_count
            or sources[0].talk_id != 0
            or any(slot.talk_id or slot.archetype.chara_init_id for slot in destinations)):
        raise ValueError("Chalice plan requires every arena state and one exact m29 source actor")
    source, target = sources[0], destinations[0]
    swap = Swap(
        target.logical_key, [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        target.archetype, source.archetype,
        destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                "x": slot.x, "y": slot.y, "z": slot.z}
                      for slot in destinations},
    )
    changes, skips = plan_scaling([swap], destinations, dict(npcs), dict(effects), boss_tiers=True)
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-chalice-humanoid-donor-v1", "status": "static-contract-only",
            "arena": arena.key, "donor": donor.key,
            "source_map_event_zero_sha256": donor.map_event_zero_sha256,
            "source_map_initializers": [donor.health_initializer,
                                        donor.music_initializer, donor.wake_initializer],
            "health_name_id": donor.health_name_id,
            "phase_music_message": 500,
            "phase_owner": "source-native-ai-tae",
            "entry_animation": donor.wake_animation,
            "preserved_destination_events": [arena.completion_event,
                                             (MARIA_ARENA.co_op_restore_event
                                              if arena == MARIA_HUMANOID_ARENA
                                              else CO_OP_RESTORE_EVENTS[arena.key]),
                                             arena.lockcam_event],
            "retired_destination_controllers": sorted(
                {MARIA_ARENA.phase_cleanup_event} if arena == MARIA_HUMANOID_ARENA
                else _retired(arena)),
        },
        "primary_init_source_bindings": [{
            "source_event_file": "event/" + donor.event_file,
            "source_map": source.map_name, "source_part": source.part_name,
            "source_entity_id": source.entity_id,
            "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "source_provenance": {"format": "bb-boss-actor-pin-v1",
                                  "part_sha256": donor.part_sha256},
            "source_initialization": dict(SOURCE_INITIALIZATION),
            "destination_map": slot.map_name,
            "destination_part": slot.part_name,
            "destination_entity_id": slot.entity_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                       "damage_anim_id", "provenance"],
        } for slot in destinations],
        "scaling": {"enabled": bool(changes),
                    "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes),
                    "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
