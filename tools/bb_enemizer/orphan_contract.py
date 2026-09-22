"""Evidence-pinned experimental Orphan of Kos combat at Cleric Beast.

The contract ports only the static combat graph: referred HP/bar setup, the
half-health form handoff, and the phase-driven support actor.  Cleric Beast
continues to own entry, fog, rewards, completion and progression.  It has not
been validated in a game session.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .inventory import load_slots
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ORPHAN_EVENT_SOURCE = "event/m36_00_00_00.emevd.dcx.js"
CLERIC_EVENT_SOURCE = "event/m24_01_00_00.emevd.dcx.js"
CLERIC = 2410800
ORPHAN_CORE = 3600800
ORPHAN_PHASE = 3600801
ORPHAN_SUPPORT = 3600803
CLERIC_ARCHETYPE = Archetype("c5000", 500241, 500241, 0)
CORE_ARCHETYPE = Archetype("c4540", 454000, 454000, 0)
PHASE_ARCHETYPE = Archetype("c4541", 454100, 454100, 0)
SUPPORT_ARCHETYPE = Archetype("c4543", 454300, 454300, 0)
PROJECT_PHASE_ENTITY = 980003
PROJECT_SUPPORT_ENTITY = 980004
PROJECT_EVENT_MIN = 12990600
PROJECT_EVENT_MAX = 12990699

# Each body is verified before emitting or patching a plan.  These pin the
# original CUSA03173 AppVer 01.09 source, not a decompiler round-trip.
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
# The original binary decompiled by pinned DarkScript 3.6.3 has two known,
# source-reviewed differences from the compact bundled text: constructor
# arguments in unrelated 13605900 calls, and the original 13604802 proximity /
# update-rate fix.  Accept only these exact alternate bodies and retain their
# installed behavior when patching.
SOURCE_ALTERNATE_HASHES = {
    0: "d9c76c6c7fcd7efe7eb641d470519cd217d70561ec8a81962f5248a76e316cb7",
    13604802: "54cb28efcdc5dbf46afd69ebfa6155d8635a61770e8f2375c6be127a8fb44004",
}
DESTINATION_HASHES = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    12411700: "32fd5783fae1fcd587800a13729ad608926b9f59b958a29992393b0c486780c9",
    12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
    12414703: "115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14",
    12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
    12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
    12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
    12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
    12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
}


@dataclass(frozen=True)
class NativeActorPin:
    """Exact original-MSB part/anchor and initialization evidence."""

    part_sha256: str
    anchor_sha256: str
    talk_id: int
    unk_t18: int
    init_anim_id: int
    damage_anim_id: int


@dataclass(frozen=True)
class OrphanIds:
    """Explicit project-owned IDs; this contract never derives map prefixes."""

    phase_entity_id: int
    support_entity_id: int
    combat_ready_flag: int
    phase_event_id: int
    support_event_id: int
    player_effect_event_id: int
    phase_camera_event_id: int
    terminal_bridge_event_id: int
    phase_destination_part: str
    support_destination_part: str
    evidence: str


@dataclass(frozen=True)
class OrphanConstruction:
    actor_additions: tuple[dict, ...]
    primary_initialization: tuple[dict, ...]
    changed_events: tuple[dict, ...]
    added_events: tuple[dict, ...]
    event_zero_initializers: tuple[dict, ...]
    terminal_predicates: tuple[dict, ...]


def _source() -> str:
    return read_blob(BUNDLE, ORPHAN_EVENT_SOURCE).decode("utf-8-sig")


def _verify(text: str, expected: Mapping[int, str], label: str, *, source_alternates: bool = False) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in expected.items():
        actual = hashlib.sha256(blocks[event_id].encode()).hexdigest() if event_id in blocks else None
        allowed = (digest, SOURCE_ALTERNATE_HASHES.get(event_id)) if source_alternates else (digest,)
        if actual not in allowed:
            raise ValueError(f"unsupported original {label} event {event_id}")
    return blocks


def _native_pin(pin: NativeActorPin, *, anchored: bool) -> dict:
    values = (pin.part_sha256, pin.anchor_sha256)
    if any(len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value) for value in values):
        raise ValueError("Orphan native actor pin requires lowercase SHA256 values")
    provenance = {"format": "bb-boss-actor-pin-v1", "part_sha256": pin.part_sha256}
    result = {
        "source_provenance": provenance,
        "source_initialization": {"talk_id": pin.talk_id, "unk_t18": pin.unk_t18,
                                  "init_anim_id": pin.init_anim_id, "damage_anim_id": pin.damage_anim_id},
    }
    if anchored:
        provenance["anchor_sha256"] = pin.anchor_sha256
        result["source_part_kind"] = "enemy"
    return result


def _globally_used_numbers() -> tuple[set[int], set[int]]:
    events: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        events.update(int(token) for token in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
    rows = read_blob(BUNDLE, "mined/msb_enemies.tsv").decode("utf-8-sig").splitlines()[1:]
    actors = {int(columns[3]) for row in rows if (columns := row.split("\t"))[3].lstrip("-").isdigit()}
    return events, actors


def _require(slots: Sequence[Slot], entity_id: int, archetype: Archetype, map_name: str | None = None) -> list[Slot]:
    matches = sorted((slot for slot in slots if slot.entity_id == entity_id and (map_name is None or slot.map_name == map_name)),
                     key=lambda slot: slot.key)
    if not matches or any(slot.dummy or slot.archetype != archetype for slot in matches):
        raise ValueError(f"unsupported Orphan placement provenance for {entity_id}")
    return matches


def _validate_ids(ids: OrphanIds) -> None:
    if ids.phase_entity_id != PROJECT_PHASE_ENTITY or ids.support_entity_id != PROJECT_SUPPORT_ENTITY:
        raise ValueError("Orphan contract requires the reviewed project actor IDs 980003 and 980004")
    if not ids.evidence.strip() or not ids.phase_destination_part.strip() or not ids.support_destination_part.strip():
        raise ValueError("Orphan contract requires non-empty allocation evidence and destination part names")
    if ids.phase_destination_part == ids.support_destination_part:
        raise ValueError("Orphan combat additions require distinct destination part names")
    events = (ids.phase_event_id, ids.support_event_id, ids.player_effect_event_id,
              ids.phase_camera_event_id, ids.terminal_bridge_event_id)
    reserved = (ids.combat_ready_flag, *events)
    if len(set(reserved)) != len(reserved) or any(not isinstance(value, int) or not PROJECT_EVENT_MIN <= value <= PROJECT_EVENT_MAX for value in reserved):
        raise ValueError("Orphan added event IDs must be unique project-owned 129906xx values")
    operands, actors = _globally_used_numbers()
    if {ids.phase_entity_id, ids.support_entity_id}.intersection(operands | actors):
        raise ValueError("Orphan project actor ID collides with bundled MSB actor or EMEVD corpus")
    if set(reserved).intersection(operands | actors):
        raise ValueError("Orphan added event ID collides with bundled MSB actor or EMEVD corpus")


def construction_request(slots: Sequence[Slot], ids: OrphanIds,
                         native_pins: Mapping[str, NativeActorPin]) -> OrphanConstruction:
    """Return evidence-pinned source/destination requirements without writing files."""
    donor = _verify(_source(), SOURCE_HASHES, "Orphan donor")
    _verify(read_blob(BUNDLE, CLERIC_EVENT_SOURCE).decode("utf-8-sig"), DESTINATION_HASHES, "Cleric arena")
    _validate_ids(ids)
    clerics = _require(slots, CLERIC, CLERIC_ARCHETYPE)
    core = _require(slots, ORPHAN_CORE, CORE_ARCHETYPE, "m36_00_00_00")
    phase = _require(slots, ORPHAN_PHASE, PHASE_ARCHETYPE, "m36_00_00_00")
    support = _require(slots, ORPHAN_SUPPORT, SUPPORT_ARCHETYPE, "m36_00_00_00")
    if not (len(core) == len(phase) == len(support) == 1):
        raise ValueError("Orphan requires one exact source core, phase and support placement")
    required_pins = {"core", "phase", "support"}
    if set(native_pins) != required_pins:
        raise ValueError("Orphan contract requires exact core, phase and support source pins")
    core_pin, phase_pin, support_pin = (native_pins[name] for name in ("core", "phase", "support"))
    # This validates all hashes before a builder can carry them forward.
    core_native = _native_pin(core_pin, anchored=False)
    phase_native = _native_pin(phase_pin, anchored=True)
    support_native = _native_pin(support_pin, anchored=True)
    remap = {
        ORPHAN_CORE: CLERIC, ORPHAN_PHASE: ids.phase_entity_id, ORPHAN_SUPPORT: ids.support_entity_id,
        13601800: 12411700, 13604802: 12414702, 13604803: 12414703, 13604804: 12414704,
        13604820: ids.phase_event_id, 13604830: ids.support_event_id,
        13604840: ids.player_effect_event_id, 13604850: ids.phase_camera_event_id,
        13604812: ids.combat_ready_flag, 13604809: 12414701,
        3603802: 2413802, 3603803: 2413803, 3602802: 2412802, 3600010: 2410010,
    }
    additions: list[dict] = []
    for target in clerics:
        for source, archetype, pin, destination_part, destination_id in (
            (phase[0], PHASE_ARCHETYPE, phase_native, ids.phase_destination_part, ids.phase_entity_id),
            (support[0], SUPPORT_ARCHETYPE, support_native, ids.support_destination_part, ids.support_entity_id),
        ):
            record = {
                "source_map": source.map_name, "source_part": source.part_name,
                "source_anchor_part": core[0].part_name, "source_entity_id": source.entity_id,
                "source_archetype": asdict(archetype), "destination_map": target.map_name,
                "destination_anchor_part": target.part_name, "destination_part": destination_part,
                "destination_entity_id": destination_id, "allocation_evidence": ids.evidence,
            }
            record.update(pin)
            additions.append(record)
    primary = []
    for target in clerics:
        binding = {
            "source_map": core[0].map_name, "source_part": core[0].part_name,
            "source_entity_id": core[0].entity_id, "source_archetype": asdict(CORE_ARCHETYPE),
            "destination_map": target.map_name, "destination_part": target.part_name,
            "destination_entity_id": target.entity_id,
        }
        binding.update(core_native)
        primary.append(binding)
    def recipe(source_event: int, destination_event: int) -> dict:
        return {"source_event_id": source_event, "destination_event_id": destination_event,
                "source_sha256": SOURCE_HASHES[source_event], "literal_remap": dict(remap)}
    return OrphanConstruction(
        actor_additions=tuple(additions), primary_initialization=tuple(primary),
        changed_events=tuple(recipe(source, target) for source, target in (
            (13604802, 12414702), (13604803, 12414703), (13604804, 12414704))),
        added_events=(recipe(13604820, ids.phase_event_id), recipe(13604830, ids.support_event_id),
                      recipe(13604840, ids.player_effect_event_id), recipe(13604850, ids.phase_camera_event_id),
                      {"source_event_id": None, "destination_event_id": ids.terminal_bridge_event_id,
                       "kind": "terminal_bridge", "source_terminal_event": 13601800,
                       "source_sha256": SOURCE_HASHES[13601800]}),
        event_zero_initializers=tuple(
            {"source_event_id": source, "destination_event_id": target,
             "source_event_zero_sha256": SOURCE_HASHES[0]}
            for source, target in ((13604820, ids.phase_event_id), (13604830, ids.support_event_id),
                                   (13604840, ids.player_effect_event_id), (13604850, ids.phase_camera_event_id)))
            + ({"source_event_id": None, "destination_event_id": ids.terminal_bridge_event_id,
                "kind": "terminal_bridge", "source_event_zero_sha256": SOURCE_HASHES[0]},),
        terminal_predicates=({"event_id": 12411700, "original_actor": CLERIC,
                              "bridge_event_id": ids.terminal_bridge_event_id},),
    )


def plan_orphan_at_cleric(slots: Sequence[Slot], ids: OrphanIds,
                           native_pins: Mapping[str, NativeActorPin]) -> dict:
    request = construction_request(slots, ids, native_pins)
    return {
        "format": "bb-orphan-cleric-plan-v1", "arena": "cleric-beast", "donor": "orphan-of-kos",
        "status": "planned", "runtime_status": "unobserved", "writer_status": "not_written",
        "boss_actor_additions": list(request.actor_additions),
        "primary_init_source_bindings": list(request.primary_initialization),
        "event_patch": {"changed_events": list(request.changed_events), "added_events": list(request.added_events),
                        "event_zero_initializers": list(request.event_zero_initializers),
                        "terminal_predicates": list(request.terminal_predicates),
                        "completion_adapter": {"required": True, "bridge_event_id": ids.terminal_bridge_event_id,
                            "destination_completion_event": 12411700,
                            "preserve": ("banner", "fog", "rewards", "progression_flags", "destination_handle_boss_defeat"),
                            "source_witness_event": 13601800, "source_witness_sha256": SOURCE_HASHES[13601800]}},
    }


def native_plan_orphan_at_cleric(slots: Sequence[Slot], npcs: Mapping[int, dict], effects: Mapping[int, dict],
                                  ids: OrphanIds, native_pins: Mapping[str, NativeActorPin], seed: str) -> dict:
    fragment = plan_orphan_at_cleric(slots, ids, native_pins)
    clerics = _require(slots, CLERIC, CLERIC_ARCHETYPE)
    swap = Swap(clerics[0].logical_key, [slot.key for slot in clerics],
                {slot.key: slot.archetype for slot in clerics}, CLERIC_ARCHETYPE, CORE_ARCHETYPE,
                warnings=["experimental Orphan contract; runtime entry, phase, support and AP completion require validation"],
                destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                         "x": slot.x, "y": slot.y, "z": slot.z} for slot in clerics})
    changes, skips = plan_scaling([swap], list(clerics), dict(npcs), dict(effects), boss_tiers=True)
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Orphan primary swap has an ambiguous normalization plan")
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed, "swap_count": 1,
        "swaps": [swap.json()], "options": {"experimental_boss_contract": "cleric-beast<-orphan-of-kos"},
        "boss_contract": fragment, "boss_actor_additions": fragment["boss_actor_additions"],
        "primary_init_source_bindings": fragment["primary_init_source_bindings"],
        "orphan_event_patch": fragment["event_patch"],
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Orphan contract expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])", lambda match: str(values.get(int(match[0]), int(match[0]))), text)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        "unused_" + item.strip() for item in match[1].split(",") if item.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def patch_orphan_at_cleric(destination: str, donor_source: str, ids: OrphanIds) -> str:
    """Patch combat only, retaining Cleric's entry and terminal progression.

    Source cutscene, fog/action objects, arena regions other than the explicitly
    mapped destination music region, rewards, and post-fight warp events are
    deliberately absent.  The bridge replaces only the terminal death wait.
    """
    donor = _verify(donor_source, SOURCE_HASHES, "Orphan donor", source_alternates=True)
    original = _verify(destination, DESTINATION_HASHES, "Cleric arena")
    _validate_ids(ids)
    added = (ids.phase_event_id, ids.support_event_id, ids.player_effect_event_id,
             ids.phase_camera_event_id, ids.terminal_bridge_event_id)
    if set(original).intersection(added):
        raise ValueError("Orphan added event ID collides with destination EMEVD")
    remap = {ORPHAN_CORE: CLERIC, ORPHAN_PHASE: ids.phase_entity_id, ORPHAN_SUPPORT: ids.support_entity_id,
             13601800: 12411700, 13604802: 12414702, 13604803: 12414703, 13604804: 12414704,
             13604820: ids.phase_event_id, 13604830: ids.support_event_id,
             13604840: ids.player_effect_event_id, 13604850: ids.phase_camera_event_id,
             13604812: ids.combat_ready_flag, 13604809: 12414701,
             3603802: 2413802, 3603803: 2413803, 3602802: 2412802, 3600010: 2410010}
    health = _remap(donor[13604802], remap)
    health = _replace_once(health, "WaitFor(EventFlag(13604808));",
                           "WaitFor(EventFlag(12414700) || EventFlag(12415400));", "destination entry predicate")
    health = _replace_once(health,
        "            if (!EventFlag(13604810)) {\n                IssueBossRoomEntryNotification(0);\n            }",
        "            IssueBossRoomEntryNotification(0);", "source notification flag")
    health = _replace_once(health, "    SetEventFlag(13604810, ON);\n", "", "source notification state")
    health = _replace_once(health, "    SetEventFlag(13604808, ON);\n", "", "source cutscene entry state")
    music = _remap(donor[13604803], remap)
    camera = _remap(donor[13604804], remap)
    # These are typed lockcam map/subarea substitutions, not a broad rewrite
    # of literal 34 or 36 (which could be valid in another operand role).
    for old, new, label in (("SetLockcamSlotNumber(34, 0, 1)", "SetLockcamSlotNumber(24, 1, 1)", "source primary lockcam"),
                            ("SetLockcamSlotNumber(36, 0, 0)", "SetLockcamSlotNumber(24, 1, 0)", "source clear lockcam")):
        if camera.count(old) != 2:
            raise ValueError(f"Orphan contract expected two {label} instructions")
        camera = camera.replace(old, new)
    old_wait = "    WaitFor(CharacterDead(2410800));\n"
    new_wait = f"    WaitFor(EventFlag({ids.terminal_bridge_event_id}));\n"
    edits = {
        12414702: health, 12414703: music, 12414704: camera,
        12414707: _end_event(original[12414707]), 12414708: _end_event(original[12414708]),
        12414710: _end_event(original[12414710]), 12414720: _end_event(original[12414720]),
        12411702: _replace_once(original[12411702],
                                 "    ForceAnimationPlayback(2410800, 3028, false, false, false);\n", "",
                                 "Cleric-only entry animation"),
        12411700: _replace_once(original[12411700], old_wait, new_wait, "destination terminal death predicate"),
    }
    initializers = "\n".join(f"    $InitializeEvent(0, {event_id});" for event_id in added)
    edits[0] = _replace_once(original[0], "    $InitializeEvent(0, 12411803);",
                             "    $InitializeEvent(0, 12411803);\n" + initializers,
                             "Orphan event-zero initializer insertion")
    edits[ids.phase_event_id] = _remap(donor[13604820], remap)
    edits[ids.support_event_id] = _remap(donor[13604830], remap)
    edits[ids.player_effect_event_id] = _remap(donor[13604840], remap)
    phase_camera = _remap(donor[13604850], remap)
    if phase_camera.count("SetLockcamSlotNumber(36, 0,") != 2:
        raise ValueError("Orphan contract expected two source phase lockcam instructions")
    edits[ids.phase_camera_event_id] = phase_camera.replace("SetLockcamSlotNumber(36, 0,", "SetLockcamSlotNumber(24, 1,")
    bridge = ids.terminal_bridge_event_id
    edits[bridge] = f'''$Event({bridge}, Default, function() {{
    if (ThisEvent()) {{
        ChangeCharacterEnableState({ids.phase_entity_id}, Disabled);
        ForceCharacterDeath({ids.phase_entity_id}, false);
        ChangeCharacterEnableState({ids.support_entity_id}, Disabled);
        ForceCharacterDeath({ids.support_entity_id}, false);
        EndEvent();
    }}
    WaitFor(EventFlag({ids.combat_ready_flag}));
    coreDead = CharacterDead({CLERIC});
    phaseDead = CharacterDead({ids.phase_entity_id});
    WaitFor(coreDead || phaseDead);
    ForceCharacterDeath({CLERIC}, false);
    SetEventFlag({bridge}, ON);
    WaitFor(EventFlag(12411700));
    ChangeCharacterEnableState({ids.phase_entity_id}, Disabled);
    ForceCharacterDeath({ids.phase_entity_id}, false);
    ChangeCharacterEnableState({ids.support_entity_id}, Disabled);
    ForceCharacterDeath({ids.support_entity_id}, false);
}});'''
    result = _replace_events(destination, {event: block for event, block in edits.items() if event in original})
    result += "\n" + "\n".join(edits[event] for event in added) + "\n"
    output = event_blocks(result)
    expected_ids = set(original).union(added)
    if set(output) != expected_ids:
        raise ValueError(f"Orphan patch changed event identity outside declared additions: "
                         f"missing={sorted(expected_ids - set(output))} extra={sorted(set(output) - expected_ids)}")
    for event_id, block in original.items():
        if event_id not in edits and block != output[event_id]:
            raise ValueError(f"Orphan patch touched unrelated destination event {event_id}")
    if output[12411700] != _replace_once(original[12411700], old_wait, new_wait, "terminal verification"):
        raise ValueError("Orphan patch changed destination terminal beyond its death predicate")
    return result
