"""Pinned Gascoigne combat graph with a field-level destination terminal adapter.

This module does not modify the active general boss contract implementation.
It records the exact two-actor donor graph and emits a reviewed construction
request only when callers provide explicit, collision-free project-owned IDs.
The source patch uses an added bridge event and changes only the destination
terminal's single death wait; all destination progression instructions remain.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .boss_canary import event_blocks
from .bosses import parse_events
from .inventory import load_slots
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling
from tools.bb_inputs import read_blob, read_prefix

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_SOURCE = "event/m24_01_00_00.emevd.dcx.js"
MAP_PREFIX = "m24_01_"
CLERIC_ENTITY = 2410800
GASCOIGNE_HUMAN = 2410810
GASCOIGNE_BEAST = 2410811
HUMAN_PART = "c2710_0000"
BEAST_PART = "c2720_0000"
CLERIC_PART = "c5000_0000"
CLERIC_ARCHETYPE = Archetype("c5000", 500241, 500241, 0)
HUMAN_ARCHETYPE = Archetype("c2710", 271000, 271000, 0)
BEAST_ARCHETYPE = Archetype("c2720", 272000, 272000, 0)

# These are source bodies that define the donor's phase graph. They are not
# guessed from event-ID prefixes and are rechecked before every plan emission.
SOURCE_HASHES = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    12411800: "b1a11b96d57174d9b9636387fa25c631ca8a1469e55297a602e9c58875c204a0",
    12414802: "3a8b68b527fc00ad30fc5561c9a64f881ee9708db2d506dd04d986458e6f17a2",
    12414803: "a6b50e5c86a3b2471166de37c25da11361053e96065b263c7220913f79399150",
    12414804: "039705347b21101bf2d6309ee55595559ff21f4a6a4be4e7cd6bc622783586c7",
    12414807: "7f72ec81a9ce98a3e41792eace02ad700a0420e9b2dfabc009b4641927c3de1e",
    12414808: "60c1f7f7ecbdf2f5cd1e0654f928a1cfcf36abd795523c3c766c4c95290fff15",
    12414809: "54c7fe426f39a828b938c14d6201fa53d9ab4b7f4e83c0d382b33c92d256a938",
}
PHASE_EVENTS = (12414807, 12414808, 12414809)
REPLACED_EVENTS = {12414802: 12414702, 12414803: 12414703, 12414804: 12414704}
BACKED_EVENT_FLAG_GROUP = 12414
DESTINATION_HASHES = {
    12411700: "32fd5783fae1fcd587800a13729ad608926b9f59b958a29992393b0c486780c9",
    12411702: "702380b92bd2632ce4ff9527009f8c7209fffff89297bc38d8fb8d108655eaff",
    12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
    12414703: "115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14",
    12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
    12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
    12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
    12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
    12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
}


@dataclass(frozen=True)
class ProjectOwnedIds:
    """Caller-selected IDs; this module never derives them from a map prefix."""

    beast_entity_id: int
    phase_event_ids: Mapping[int, int]
    terminal_bridge_event_id: int
    destination_part: str
    evidence: str


@dataclass(frozen=True)
class NativeActorPin:
    """Exact source-MSB evidence emitted by ``--boss-actor-pins``.

    The bundled corpus intentionally contains mined slot facts rather than map
    binaries, so these values must come from the operator's original effective
    map. Accepting a blank or malformed pin would make a later native addition
    look reviewed without actually binding it to that map.
    """

    part_sha256: str
    anchor_sha256: str
    talk_id: int
    unk_t18: int
    init_anim_id: int
    damage_anim_id: int


@dataclass(frozen=True)
class GascoigneConstruction:
    """Reviewed request shape for the future multi-actor contract adapter."""

    human_entity_id: int
    beast_entity_id: int
    actor_additions: tuple[dict, ...]
    changed_events: tuple[dict, ...]
    added_events: tuple[dict, ...]
    event_zero_initializers: tuple[dict, ...]
    completion_adapter: dict
    terminal_predicates: tuple[dict, ...]


def _source() -> str:
    return read_blob(BUNDLE, EVENT_SOURCE).decode("utf-8-sig")


def _native_pin(pin: NativeActorPin) -> dict:
    hashes = (pin.part_sha256, pin.anchor_sha256)
    if any(len(value) != 64 or any(char not in "0123456789abcdef" for char in value) for value in hashes):
        raise ValueError("Gascoigne native actor pin requires lowercase SHA256 values")
    return {
        "source_part_kind": "enemy",
        "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": pin.part_sha256,
                              "anchor_sha256": pin.anchor_sha256},
        "source_initialization": {"talk_id": pin.talk_id, "unk_t18": pin.unk_t18,
                                  "init_anim_id": pin.init_anim_id, "damage_anim_id": pin.damage_anim_id},
    }


def _verify_source(source: str) -> dict[int, str]:
    blocks = event_blocks(source)
    for event_id, expected in SOURCE_HASHES.items():
        block = blocks.get(event_id)
        if block is None or hashlib.sha256(block.encode()).hexdigest() != expected:
            raise ValueError(f"unsupported original Gascoigne event {event_id}")
    return blocks


def _verify_destination(source: str) -> dict[int, str]:
    blocks = event_blocks(source)
    for event_id, expected in DESTINATION_HASHES.items():
        block = blocks.get(event_id)
        if block is None or hashlib.sha256(block.encode()).hexdigest() != expected:
            raise ValueError(f"unsupported original Cleric event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, role: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gascoigne contract expected one {role}")
    return text.replace(old, new, 1)


def _remap(text: str, remap: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])", lambda match: str(remap.get(int(match[0]), int(match[0]))), text)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        "unused_" + item.strip() for item in match[1].split(",") if item.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _globally_used_numbers() -> tuple[set[int], set[int]]:
    """All static EMEVD operands and every mined MSB actor ID, not one map band."""
    events = set()
    for body in read_prefix(BUNDLE, "event/").values():
        text = body.decode("utf-8-sig", errors="strict")
        events.update(int(token) for token in re.findall(r"(?<![\w])-?\d+(?![\w])", text))
    actor_rows = read_blob(BUNDLE, "mined/msb_enemies.tsv").decode("utf-8-sig").splitlines()[1:]
    actors = {int(row.split("\t")[3]) for row in actor_rows if row.split("\t")[3].lstrip("-").isdigit()}
    return events, actors


def _validate_event_allocation(all_event_ids: Sequence[int], role: str) -> None:
    """Require the runtime-probed m24_01 flag group for persistent helpers.

    Event IDs can compile even when their flag group has no backing storage.
    Gascoigne's phase routines use ``ThisEvent`` and the terminal adapter waits
    on its helper event flag, so a collision-free number alone is insufficient.
    Group 12414 is destination-native and 12414780--12414783 were read as
    backed and clear in a live client probe before being selected.
    """
    if any(event_id // 1000 != BACKED_EVENT_FLAG_GROUP for event_id in all_event_ids):
        raise ValueError(f"Gascoigne {role} event IDs require backed event-flag group 12414")


def _slots_by_entity(slots: Sequence[Slot], entity: int) -> list[Slot]:
    return sorted((slot for slot in slots if slot.map_name.startswith(MAP_PREFIX) and slot.entity_id == entity),
                  key=lambda slot: slot.key)


def _require_placement(slots: Sequence[Slot], entity: int, archetype: Archetype) -> list[Slot]:
    result = _slots_by_entity(slots, entity)
    if not result or any(slot.dummy or slot.archetype != archetype for slot in result):
        raise ValueError(f"unsupported Gascoigne placement provenance for {entity}")
    return result


def construction_request(slots: Sequence[Slot], allocation: ProjectOwnedIds,
                         native_pins: Mapping[str, NativeActorPin]) -> GascoigneConstruction:
    """Return exact, collision-checked data; refuse to allocate IDs implicitly.

    The returned terminal metadata permits only the reviewed destination
    death-wait substitution; the native writer validates that exception.
    """
    source = _source()
    _verify_source(source)
    _verify_destination(source)
    clerics = _require_placement(slots, CLERIC_ENTITY, CLERIC_ARCHETYPE)
    humans = _require_placement(slots, GASCOIGNE_HUMAN, HUMAN_ARCHETYPE)
    beasts = _require_placement(slots, GASCOIGNE_BEAST, BEAST_ARCHETYPE)
    if not allocation.evidence.strip() or not allocation.destination_part.strip():
        raise ValueError("Gascoigne allocation requires non-empty ownership evidence and destination part")
    if allocation.beast_entity_id <= 0:
        raise ValueError("Gascoigne beast entity ID must be positive")
    event_operands, msb_actor_ids = _globally_used_numbers()
    if allocation.beast_entity_id in msb_actor_ids or allocation.beast_entity_id in event_operands:
        raise ValueError("Gascoigne beast entity ID collides with the bundled MSB actor or EMEVD corpus")
    if set(allocation.phase_event_ids) != set(PHASE_EVENTS):
        raise ValueError("Gascoigne allocation must bind every declared phase event")
    phase_ids = tuple(allocation.phase_event_ids[event] for event in PHASE_EVENTS)
    all_event_ids = phase_ids + (allocation.terminal_bridge_event_id,)
    if any(not isinstance(event, int) or event < 0 for event in all_event_ids) or len(set(all_event_ids)) != len(all_event_ids):
        raise ValueError("Gascoigne phase event IDs must be unique non-negative integers")
    _validate_event_allocation(all_event_ids, "construction")
    if event_operands.union(msb_actor_ids).intersection(all_event_ids):
        raise ValueError("Gascoigne added event ID collides with a bundled EMEVD operand")

    # All alternate states carry the same logical placement. The primary swap
    # changes Cleric's existing actor into the human form. The beast is dormant
    # until its phase event warps it onto the human, so it must begin at the
    # destination anchor instead of preserving its unsafe source-map offset.
    clerics_by_map = {slot.map_name: slot for slot in clerics}
    humans_by_map = {slot.map_name: slot for slot in humans}
    beasts_by_map = {slot.map_name: slot for slot in beasts}
    required_maps = set(clerics_by_map)
    if set(native_pins) != required_maps or set(humans_by_map) != required_maps or set(beasts_by_map) != required_maps:
        raise ValueError("Gascoigne actor additions require one exact source pin for every destination map state")
    additions = []
    for map_name in sorted(required_maps):
        addition = {
            "source_map": map_name,
            "source_part": BEAST_PART,
            "source_anchor_part": HUMAN_PART,
            "source_entity_id": GASCOIGNE_BEAST,
            "source_archetype": asdict(BEAST_ARCHETYPE),
            "destination_map": map_name,
            "destination_anchor_part": clerics_by_map[map_name].part_name,
            "destination_part": allocation.destination_part,
            "destination_entity_id": allocation.beast_entity_id,
            "placement_policy": "destination-anchor",
            "allocation_evidence": allocation.evidence,
        }
        addition.update(_native_pin(native_pins[map_name]))
        additions.append(addition)
    # Source event 0 explicitly initializes these three routines; the future
    # adapter must add their new initializers to destination event 0 and pin its
    # compiler output. No heuristic event discovery is permitted.
    remap = {
        GASCOIGNE_HUMAN: CLERIC_ENTITY,
        GASCOIGNE_BEAST: allocation.beast_entity_id,
        12411800: 12411700,
        12414800: 12414700,
        12414801: 12414701,
        **allocation.phase_event_ids,
    }
    def recipe(source_event: int) -> dict:
        return {"source_event_id": source_event,
                "destination_event_id": allocation.phase_event_ids[source_event],
                "source_sha256": SOURCE_HASHES[source_event], "literal_remap": dict(remap)}
    return GascoigneConstruction(
        human_entity_id=CLERIC_ENTITY, beast_entity_id=allocation.beast_entity_id,
        actor_additions=tuple(additions),
        changed_events=tuple({"source_event_id": source, "destination_event_id": destination,
                              "source_sha256": SOURCE_HASHES[source], "literal_remap": dict(remap)}
                             for source, destination in REPLACED_EVENTS.items()),
        added_events=tuple(recipe(event) for event in PHASE_EVENTS) + ({
            "source_event_id": None, "destination_event_id": allocation.terminal_bridge_event_id,
            "kind": "terminal_bridge", "destination_completion_event": 12411700,
        },),
        event_zero_initializers=tuple({"source_event_id": event,
                                       "destination_event_id": allocation.phase_event_ids[event],
                                       "source_event_zero_sha256": SOURCE_HASHES[0]} for event in PHASE_EVENTS)
        + ({"source_event_id": None, "destination_event_id": allocation.terminal_bridge_event_id,
            "kind": "terminal_bridge", "source_event_zero_sha256": SOURCE_HASHES[0]},),
        completion_adapter={
            "required": True,
            "bridge_event_id": allocation.terminal_bridge_event_id,
            "destination_completion_event": 12411700,
            "preserve": ("banner", "fog", "rewards", "progression_flags", "destination_handle_boss_defeat"),
            "replace_death_predicate_with": {
                "human_entity_id": CLERIC_ENTITY,
                "beast_entity_id": allocation.beast_entity_id,
                "reason": "Gascoigne phase disables the human before beast death",
            },
            "source_witness_event": 12411800,
            "source_witness_sha256": SOURCE_HASHES[12411800],
            "terminal_predicates": ({"event_id": 12411700, "original_actor": CLERIC_ENTITY,
                                     "bridge_event_id": allocation.terminal_bridge_event_id},),
        },
        terminal_predicates=({"event_id": 12411700, "original_actor": CLERIC_ENTITY,
                              "bridge_event_id": allocation.terminal_bridge_event_id},),
    )


def plan_gascoigne_at_cleric(slots: Sequence[Slot], allocation: ProjectOwnedIds,
                             native_pins: Mapping[str, NativeActorPin]) -> dict:
    """Builder-facing plan fragment for ``--arena cleric-beast --donor father-gascoigne``.

    The caller compiles :func:`patch_gascoigne_at_cleric` and passes this
    fragment's terminal predicates to the reviewed event manifest. It must not
    use a generic map-only route: the actor additions and terminal bridge are
    required together.
    """
    request = construction_request(slots, allocation, native_pins)
    return {
        "format": "bb-gascoigne-cleric-plan-v1",
        "arena": "cleric-beast",
        "donor": "father-gascoigne",
        "status": "planned",
        "writer_status": "not_written",
        "boss_actor_additions": list(request.actor_additions),
        "event_patch": {
            "changed_events": list(request.changed_events),
            "added_events": list(request.added_events),
            "event_zero_initializers": list(request.event_zero_initializers),
            "terminal_predicates": list(request.terminal_predicates),
            "completion_adapter": request.completion_adapter,
        },
        "primary_swap": {
            "source": asdict(CLERIC_ARCHETYPE), "target": asdict(HUMAN_ARCHETYPE),
            "entity_id": CLERIC_ENTITY,
        },
    }


def native_plan_gascoigne_at_cleric(slots: Sequence[Slot], npcs: Mapping[int, dict], effects: Mapping[int, dict],
                                    allocation: ProjectOwnedIds,
                                    native_pins: Mapping[str, NativeActorPin], seed: str) -> dict:
    """Return the standard native map/scaling shape plus the Gascoigne addenda."""
    fragment = plan_gascoigne_at_cleric(slots, allocation, native_pins)
    destinations = _require_placement(slots, CLERIC_ENTITY, CLERIC_ARCHETYPE)
    swap = Swap(
        destinations[0].logical_key, [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations}, CLERIC_ARCHETYPE, HUMAN_ARCHETYPE,
        warnings=["experimental Gascoigne contract; runtime entrance, phase and AP completion require validation"],
        destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                 "x": slot.x, "y": slot.y, "z": slot.z} for slot in destinations},
    )
    changes, skips = plan_scaling([swap], list(destinations), dict(npcs), dict(effects), boss_tiers=True)
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Gascoigne primary swap has an ambiguous normalization plan")
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed, "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "cleric-beast<-father-gascoigne"},
        "boss_contract": fragment,
        "boss_actor_additions": fragment["boss_actor_additions"],
        "gascoigne_event_patch": fragment["event_patch"],
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def grounded_cleric_entry(original: str) -> str:
    """Keep the replacement at Cleric's native combat placement, not its leap origin.

    Region 2412831 belongs to the c5000 entrance leap. Removing that model's
    root-motion animation while retaining its warp strands a replacement away
    from the native c5000 MSB combat position. Entry conditions and progression
    stay destination-owned; no replacement animation is guessed here.
    """
    result = _replace_once(
        original,
        "    IssueShortWarpRequest(2410800, TargetEntityType.Area, 2412831, -1);\n",
        "", "Cleric leap-origin warp")
    result = _replace_once(
        result, "    ForceAnimationPlayback(2410800, 3028, false, false, false);\n",
        "", "Cleric leap animation")
    return _replace_once(result, "    WaitFixedTimeFrames(110);",
                         "    WaitFixedTimeFrames(1);", "Cleric leap duration")


def patch_gascoigne_at_cleric(destination: str, allocation: ProjectOwnedIds) -> str:
    """Produce the reviewed source patch for Gascoigne's two-actor graph.

    This changes Cleric's terminal only at its one death wait: the destination
    event still owns every banner, fog, delay, reward, flag and HandleBossDefeat
    instruction. The bridge event owns the OR predicate and reload cleanup.
    """
    source = _source()
    donor, original = _verify_source(source), _verify_destination(destination)
    phase_ids = tuple(allocation.phase_event_ids[event] for event in PHASE_EVENTS)
    all_added = phase_ids + (allocation.terminal_bridge_event_id,)
    if set(allocation.phase_event_ids) != set(PHASE_EVENTS) or len(set(all_added)) != len(all_added):
        raise ValueError("Gascoigne patch requires unique explicit phase and bridge event IDs")
    if set(original).intersection(all_added) or any(event < 0 for event in all_added):
        raise ValueError("Gascoigne patch added event ID collides with destination EMEVD")
    _validate_event_allocation(all_added, "patch")
    if allocation.beast_entity_id <= 0:
        raise ValueError("Gascoigne patch requires a positive beast entity ID")
    remap = {GASCOIGNE_HUMAN: CLERIC_ENTITY, GASCOIGNE_BEAST: allocation.beast_entity_id,
             12411800: 12411700, 12414800: 12414700, 12414801: 12414701,
             **REPLACED_EVENTS,
             **allocation.phase_event_ids}
    edits = {}
    # Source 12414802 supplies co-op scaling and the referred-damage pair, but
    # Cleric owns its entry OR flag and its unconditional room notification.
    health = _remap(donor[12414802], remap)
    health = _replace_once(health, "        WaitFor(EventFlag(12414700));",
                           "        WaitFor(EventFlag(12414700) || EventFlag(12415400));",
                           "Cleric alternate entry flag")
    health = _replace_once(health,
                           "            if (!EventFlag(12414223)) {\n                IssueBossRoomEntryNotification(0);\n            }\n            SetNetworkUpdateAuthority(2410800, AuthorityLevel.Forced);",
                           "            IssueBossRoomEntryNotification(0);\n            SetNetworkUpdateAuthority(2410800, AuthorityLevel.Forced);",
                           "Gascoigne notification flag")
    health = _replace_once(health, "    SetEventFlag(12414223, ON);\n", "",
                           "Gascoigne start notification flag")
    health = _replace_once(
        health,
        f"L4:\n    CreateReferredDamagePair({CLERIC_ENTITY}, {allocation.beast_entity_id});",
        f"L4:\n    SetCharacterInvincibility({allocation.beast_entity_id}, Disabled);\n"
        f"    CreateReferredDamagePair({CLERIC_ENTITY}, {allocation.beast_entity_id});",
        "pre-link beast vulnerability",
    )
    edits[12414702] = health
    # Keep Cleric's arena-owned music regions/sounds; its phase trigger becomes
    # the declared Gascoigne transformation event.
    edits[12414703] = _replace_once(
        original[12414703], "CharacterHasEventMessage(2410800, 100)",
        f"EventFlag({allocation.phase_event_ids[12414807]})", "destination music phase trigger")
    edits[12414704] = _remap(donor[12414804], remap)
    for event in (12414707, 12414708, 12414710, 12414720):
        edits[event] = _end_event(original[event])
    edits[12411702] = grounded_cleric_entry(original[12411702])
    old_wait = "    WaitFor(CharacterDead(2410800));\n"
    new_wait = f"    WaitFor(EventFlag({allocation.terminal_bridge_event_id}));\n"
    edits[12411700] = _replace_once(original[12411700], old_wait, new_wait, "destination terminal death predicate")
    initializers = "\n".join(
        f"    $InitializeEvent(0, {event_id});" for event_id in (*phase_ids, allocation.terminal_bridge_event_id))
    edits[0] = _replace_once(original[0], "    $InitializeEvent(0, 12411803);",
                             "    $InitializeEvent(0, 12411803);\n" + initializers,
                             "Gascoigne event-zero initializer insertion")
    for source_event, destination_event in allocation.phase_event_ids.items():
        phase = _remap(donor[source_event], remap)
        if source_event == 12414807:
            phase = _replace_once(
                phase,
                f"        ChangeCharacterEnableState({CLERIC_ENTITY}, Disabled);\n"
                "        EndEvent();\n",
                f"        ChangeCharacterEnableState({CLERIC_ENTITY}, Disabled);\n"
                f"        ChangeCharacterEnableState({allocation.beast_entity_id}, Enabled);\n"
                f"        SetCharacterInvincibility({allocation.beast_entity_id}, Disabled);\n"
                f"        SetCharacterGravity({allocation.beast_entity_id}, Enabled);\n"
                "        EndEvent();\n",
                "completed-phase beast restoration",
            )
            phase = _replace_once(
                phase,
                f"    SetCharacterGravity({allocation.beast_entity_id}, Disabled);\n",
                f"    ChangeCharacterEnableState({allocation.beast_entity_id}, Disabled);\n"
                f"    SetCharacterInvincibility({allocation.beast_entity_id}, Enabled);\n"
                f"    SetCharacterAIState({allocation.beast_entity_id}, Disabled);\n"
                f"    SetCharacterHPBarDisplay({allocation.beast_entity_id}, Disabled);\n"
                f"    SetCharacterGravity({allocation.beast_entity_id}, Disabled);\n",
                "pre-phase beast isolation",
            )
            phase = _replace_once(
                phase,
                f"    SetCharacterGravity({allocation.beast_entity_id}, Enabled);\n"
                f"    SetNetworkUpdateRate({allocation.beast_entity_id}, true, CharacterUpdateFrequency.AlwaysUpdate);\n"
                f"    WarpCharacterAndCopyFloor({allocation.beast_entity_id}, TargetEntityType.Character, "
                f"{CLERIC_ENTITY}, 203, {CLERIC_ENTITY});\n",
                f"    WarpCharacterAndCopyFloor({allocation.beast_entity_id}, TargetEntityType.Character, "
                f"{CLERIC_ENTITY}, 203, {CLERIC_ENTITY});\n"
                f"    ChangeCharacterEnableState({allocation.beast_entity_id}, Enabled);\n"
                f"    SetCharacterInvincibility({allocation.beast_entity_id}, Disabled);\n"
                f"    SetCharacterGravity({allocation.beast_entity_id}, Enabled);\n"
                f"    SetNetworkUpdateRate({allocation.beast_entity_id}, true, CharacterUpdateFrequency.AlwaysUpdate);\n",
                "post-warp beast activation",
            )
            phase = _replace_once(phase,
                                  "    EndIf(EventFlag(9337));\n    $InitializeEvent(0, 9350, 1);\n    SetEventFlag(9337, ON);\n",
                                  "", "Gascoigne phase insight/progression tail")
        edits[destination_event] = phase
    bridge = allocation.terminal_bridge_event_id
    edits[bridge] = f'''$Event({bridge}, Default, function() {{
    if (ThisEvent()) {{
        ChangeCharacterEnableState({allocation.beast_entity_id}, Disabled);
        ForceCharacterDeath({allocation.beast_entity_id}, false);
        EndEvent();
    }}
    humanDead = CharacterDead({CLERIC_ENTITY});
    beastPhase = EventFlag({allocation.phase_event_ids[12414807]});
    beastDead = CharacterDead({allocation.beast_entity_id});
    WaitFor(humanDead || (beastPhase && beastDead));
    SetEventFlag({bridge}, ON);
    WaitFor(EventFlag(12411700));
    ChangeCharacterEnableState({allocation.beast_entity_id}, Disabled);
    ForceCharacterDeath({allocation.beast_entity_id}, false);
}});'''
    # Existing bodies are replaced in place; newly declared routines are
    # appended in reviewed order because they have no original line span.
    result = _replace_events(destination, {event: block for event, block in edits.items() if event in original})
    result += "\n" + "\n".join(edits[event] for event in (*phase_ids, bridge)) + "\n"
    output = event_blocks(result)
    if set(output) != set(original).union(all_added):
        raise ValueError("Gascoigne patch changed event identity outside declared additions")
    for event_id, block in original.items():
        if event_id not in edits and block != output[event_id]:
            raise ValueError(f"Gascoigne patch touched unrelated event {event_id}")
    # The protected terminal is only its explicitly reviewed wait substitution.
    expected_terminal = _replace_once(original[12411700], old_wait, new_wait, "terminal verification")
    if output[12411700] != expected_terminal:
        raise ValueError("Gascoigne patch changed destination terminal beyond its death predicate")
    return result
