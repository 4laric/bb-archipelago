"""Evidence-pinned Martyr Logarius combat overlay for the BSB arena.

Old Yharnam keeps its fog, music objects, reward, completion flag and AP
progression.  The adapter ports Logarius' core setup, sword lifecycle, aura
projectile and phase cleanup.  Its arena fit is inferred from static CUSA03173
AppVer 01.09 inputs and has not been observed in game.
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

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
LOGARIUS_EVENT_SOURCE = "event/m25_00_00_00.emevd.dcx.js"
BSB_EVENT_SOURCE = "event/m23_00_00_00.emevd.dcx.js"

LOGARIUS_CORE = 2500800
LOGARIUS_SWORD = 2500801
LOGARIUS_EFFECT_OWNER = 2500802
BSB_ACTOR = 2300800
PROJECT_SWORD_ENTITY = 980005
PROJECT_EFFECT_OWNER_ENTITY = 980006

LOGARIUS_ARCHETYPE = Archetype("c2320", 232000, 232000, 0)
SWORD_ARCHETYPE = Archetype("c2321", 232100, 232100, 0)
EFFECT_OWNER_ARCHETYPE = Archetype("c9010", 232000, 232000, 0)
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)

PROJECT_EVENT_MIN = 12990900
PROJECT_EVENT_MAX = 12990999

# Event bodies are hashed after UTF-8-sig decoding, matching event_blocks.
SOURCE_HASHES = {
    0: "f906cc00fd41625d4e479a9f0e261e6344708b7ea2728f850cb328efbf39a9ed",
    12501800: "8e7a5e07c7e871cbb44982c80436874fdf451d3c80c68af2969e15f78c6129bd",
    12501801: "752c098d59f5b3c00482b78f1ecbaa771d7fa084bef22e9e490784bfc5725797",
    12501802: "91d992106cdd9de1298ea848def19f816af24302f50dbf56f67cf5f5932c2e71",
    12504810: "247053c43384e582535e4d4c26497797719d3d0e1b01026a425fd7f2efc9b6ec",
    12504811: "25b151f4961f4832b989524527f8db3584b798e83c9c064b16fc83358578a39a",
    12504802: "a8819ae3d0e70e0ea1d5e0e9f662b9e19e7fcb4b07b160f6a84b2249413cc625",
    12504803: "edee08431133d70220856551eb1b4518e7e8898c80fcbde9448a81537e9a7e0a",
    12504804: "d64bb9fa786b4cf26dae37451b8ca76de2a42bbff3bed4d47ce70ca28d32db42",
    12504806: "dba1f97eec52c6f56df35f2f53813470690d7b83ffba3fd313459130cceae775",
    12504807: "9a3943748bcb8301baaf7978ea59899fc0cdd7318a15f6fb50c57be73f94157a",
    12504808: "fb6738bfefc7c4fb69af7def1f54386d186058b6a1b284a07e74004610e9f1fa",
}
DESTINATION_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12301800: "e9eed714540eab5058a6553eb5b11b28f2edcb6d4236679efaafafb9c4e8f1a4",
    12301801: "04732cb4245a537ebbb26833250f04d4164b4a22d41237977235a98726c5b9aa",
    12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
    12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
    12304810: "84fcb2de4358b760ffa82a709d50f281735cdc3585d1bb16e3772355b65cdd99",
    12304811: "8ecf40cab1c2db8ff9a3ef6a510043d5a4fa10dabb0ccd7e6f09ce31cd638681",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}


@dataclass(frozen=True)
class NativeActorPin:
    """Fingerprint and initialization read from an original user-owned MSB."""

    part_sha256: str
    talk_id: int
    unk_t18: int
    init_anim_id: int
    damage_anim_id: int
    anchor_sha256: str | None = None


# Produced by BBEnemizerWriter --boss-actor-pins over the original m25 MSB.
CORE_PIN = NativeActorPin(
    "7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011",
    0,
    -1,
    -1,
    -1,
)
SWORD_PIN = NativeActorPin(
    "fc114097901492ce96524c9265c04a6c2606b3b825336723adb52c9064475b1d",
    0,
    -1,
    -1,
    -1,
    "7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011",
)
EFFECT_OWNER_PIN = NativeActorPin(
    "7bd8e95bd08d4bfe30801d088983025c6c1593885dfc97cabff3ecc89c5c4984",
    0,
    -1,
    -1,
    -1,
    "7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011",
)


@dataclass(frozen=True)
class LogariusIds:
    sword_entity_id: int = PROJECT_SWORD_ENTITY
    effect_owner_entity_id: int = PROJECT_EFFECT_OWNER_ENTITY
    sword_event_id: int = 12990901
    aura_event_id: int = 12990902
    cleanup_event_id: int = 12990903
    lifecycle_event_id: int = 12990904
    sword_destination_part: str = "ap_logarius_sword"
    effect_owner_destination_part: str = "ap_logarius_effect_owner"
    evidence: str = (
        "BB AP Logarius-at-BSB allocation v1; full original EMEVD/MSB collision scan"
    )

    def event_ids(self) -> tuple[int, int, int, int]:
        return (
            self.sword_event_id,
            self.aura_event_id,
            self.cleanup_event_id,
            self.lifecycle_event_id,
        )


DEFAULT_IDS = LogariusIds()


def _source() -> str:
    return read_blob(BUNDLE, LOGARIUS_EVENT_SOURCE).decode("utf-8-sig")


def _verify(text: str, expected: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in expected.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Logarius/BSB expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            (
                name.strip()
                if name.strip().startswith("unused_")
                else "unused_" + name.strip()
            )
            for name in match[1].split(",")
            if name.strip()
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


def _globally_used_numbers() -> tuple[set[int], set[int]]:
    operands: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        operands.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    actor_rows = (
        read_blob(BUNDLE, "mined/msb_enemies.tsv").decode("utf-8-sig").splitlines()[1:]
    )
    actors = {
        int(columns[3])
        for row in actor_rows
        if (columns := row.split("\t"))[3].lstrip("-").isdigit()
    }
    return operands, actors


def _validate_ids(ids: LogariusIds) -> None:
    if (ids.sword_entity_id, ids.effect_owner_entity_id) != (
        PROJECT_SWORD_ENTITY,
        PROJECT_EFFECT_OWNER_ENTITY,
    ):
        raise ValueError(
            "Logarius contract requires reviewed project actor IDs 980005 and 980006"
        )
    if ids.sword_entity_id == ids.effect_owner_entity_id:
        raise ValueError(
            "Logarius sword and effect owner require distinct project actor IDs"
        )
    if (
        not ids.sword_destination_part.strip()
        or not ids.effect_owner_destination_part.strip()
        or ids.sword_destination_part == ids.effect_owner_destination_part
        or not ids.evidence.strip()
    ):
        raise ValueError(
            "Logarius allocation requires distinct destination parts and ownership evidence"
        )
    events = ids.event_ids()
    if len(set(events)) != len(events) or any(
        not isinstance(value, int)
        or not PROJECT_EVENT_MIN <= value <= PROJECT_EVENT_MAX
        for value in events
    ):
        raise ValueError(
            "Logarius event IDs must be unique project-owned 129909xx values"
        )
    operands, actors = _globally_used_numbers()
    if {ids.sword_entity_id, ids.effect_owner_entity_id}.intersection(
        operands | actors
    ):
        raise ValueError(
            "Logarius project actor ID collides with bundled MSB actor or EMEVD corpus"
        )
    if set(events).intersection(operands | actors):
        raise ValueError(
            "Logarius project event ID collides with bundled MSB actor or EMEVD corpus"
        )


def _require(
    slots: Sequence[Slot],
    entity: int,
    archetype: Archetype,
    map_name: str | None = None,
) -> list[Slot]:
    matches = sorted(
        (
            slot
            for slot in slots
            if slot.entity_id == entity
            and (map_name is None or slot.map_name == map_name)
        ),
        key=lambda slot: slot.key,
    )
    if not matches or any(
        slot.dummy or slot.talk_id or slot.archetype != archetype for slot in matches
    ):
        raise ValueError(f"unsupported Logarius/BSB placement provenance for {entity}")
    return matches


def _pin(pin: NativeActorPin, *, with_anchor: bool) -> dict:
    hashes = (pin.part_sha256,) + ((pin.anchor_sha256,) if with_anchor else ())
    if any(
        value is None
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
        for value in hashes
    ):
        raise ValueError("Logarius native actor pin requires lowercase SHA256 values")
    provenance = {"format": "bb-boss-actor-pin-v1", "part_sha256": pin.part_sha256}
    if with_anchor:
        provenance["anchor_sha256"] = pin.anchor_sha256
    return {
        "source_provenance": provenance,
        "source_initialization": {
            "talk_id": pin.talk_id,
            "unk_t18": pin.unk_t18,
            "init_anim_id": pin.init_anim_id,
            "damage_anim_id": pin.damage_anim_id,
        },
    }


def _event_remap(ids: LogariusIds) -> dict[int, int]:
    return {
        LOGARIUS_CORE: BSB_ACTOR,
        LOGARIUS_SWORD: ids.sword_entity_id,
        LOGARIUS_EFFECT_OWNER: ids.effect_owner_entity_id,
        12501800: 12301800,
        12504800: 12304800,
        12504802: 12304802,
        12504804: 12304804,
        12504806: ids.sword_event_id,
        12504807: ids.aura_event_id,
        12504808: ids.cleanup_event_id,
    }


def patch_logarius_at_bsb(
    destination: str, donor_source: str, ids: LogariusIds = DEFAULT_IDS
) -> str:
    """Patch the statically reviewed Logarius combat closure into Old Yharnam."""
    donor = _verify(donor_source, SOURCE_HASHES, "Logarius donor")
    original = _verify(destination, DESTINATION_HASHES, "BSB arena")
    _validate_ids(ids)
    if set(ids.event_ids()).intersection(original):
        raise ValueError("Logarius added event ID collides with destination EMEVD")
    remap = _event_remap(ids)

    health = donor[12504802]
    health = _replace_once(
        health,
        "            if (!EventFlag(12504223)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }",
        "            IssueBossRoomEntryNotification(0);",
        "source notification flag",
    )
    health = _replace_once(
        health, "    SetEventFlag(12504223, ON);\n", "", "source notification state"
    )
    health = _replace_once(
        health, "CreatePlaylog(82);", "CreatePlaylog(86);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2500010, 98, Enabled);",
        "StartTimeMeasurement(2300010, 102, Enabled);",
        "destination time measurement",
    )
    health = _remap(health, remap)

    camera = _remap(donor[12504804], remap)
    lockcam = "SetLockcamSlotNumber(25, 0,"
    if camera.count(lockcam) != 2:
        raise ValueError("Logarius/BSB expected two destination lockcam bindings")
    camera = camera.replace(lockcam, "SetLockcamSlotNumber(23, 0,")
    sword = _remap(donor[12504806], remap)
    sword = _replace_once(
        sword,
        "    StartTimeMeasurement(2501000, 116, Enabled);\n",
        "",
        "source sword measurement start",
    )
    sword = _replace_once(
        sword, "    EndTimeMeasurement(2501000);\n", "", "source sword measurement end"
    )
    aura = _remap(donor[12504807], remap)
    cleanup = _remap(donor[12504808], remap)

    activation = _replace_once(
        original[12301802],
        "ForceAnimationPlayback(2300800, 7001, false, false, false);",
        "ForceAnimationPlayback(2300800, 7000, false, false, false);",
        "Logarius entry animation",
    )
    music = _replace_once(
        original[12304803],
        "flagArea2 &= EventFlag(12304808);",
        "flagArea2 &= CharacterHasSpEffect(2300800, 5633);",
        "Logarius phase music trigger",
    )
    added_initializers = "\n".join(
        (
            f"    $InitializeEvent(0, {ids.sword_event_id});",
            f"    $InitializeEvent(0, {ids.sword_event_id});",
            f"    $InitializeEvent(0, {ids.aura_event_id});",
            f"    $InitializeEvent(0, {ids.cleanup_event_id});",
            f"    $InitializeEvent(0, {ids.lifecycle_event_id});",
        )
    )
    constructor = _replace_once(
        original[0],
        "    $InitializeEvent(0, 12304808);",
        "    $InitializeEvent(0, 12304808);\n" + added_initializers,
        "Logarius combat initializer anchor",
    )
    edits = {
        0: constructor,
        12301802: activation,
        12304802: health,
        12304803: music,
        12304804: camera,
        12304807: _end_event(original[12304807]),
        12304808: _end_event(original[12304808]),
    }
    lifecycle = f"""$Event({ids.lifecycle_event_id}, Default, function() {{
    if (!ThisEvent()) {{
        WaitFor(EventFlag(12301800));
    }}
    ChangeCharacterEnableState({ids.sword_entity_id}, Disabled);
    ForceCharacterDeath({ids.sword_entity_id}, false);
    ChangeCharacterEnableState({ids.effect_owner_entity_id}, Disabled);
    ForceCharacterDeath({ids.effect_owner_entity_id}, false);
}});"""
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((sword, aura, cleanup, lifecycle))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original).union(ids.event_ids()):
        raise ValueError("Logarius/BSB patch changed event identities")
    for event_id, body in original.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Logarius/BSB patch changed unrelated event {event_id}")
    if output[12301800] != original[12301800]:
        raise ValueError(
            "Logarius/BSB patch changed destination completion progression"
        )
    copied = "\n".join(
        output[event]
        for event in (
            12304802,
            12304804,
            ids.sword_event_id,
            ids.aura_event_id,
            ids.cleanup_event_id,
        )
    )
    if re.search(r"(?<!\d)(?:125|250)\d+(?!\d)", copied):
        raise ValueError("Logarius/BSB copied combat body retains a donor-map literal")
    return result


def native_plan_logarius_at_bsb(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LogariusIds = DEFAULT_IDS,
) -> dict:
    """Return the native primary swap and exact sword-part addition records."""
    _verify(_source(), SOURCE_HASHES, "Logarius donor")
    _verify(
        read_blob(BUNDLE, BSB_EVENT_SOURCE).decode("utf-8-sig"),
        DESTINATION_HASHES,
        "BSB arena",
    )
    _validate_ids(ids)
    destinations = _require(slots, BSB_ACTOR, BSB_ARCHETYPE)
    core = _require(slots, LOGARIUS_CORE, LOGARIUS_ARCHETYPE, "m25_00_00_00")
    sword = _require(slots, LOGARIUS_SWORD, SWORD_ARCHETYPE, "m25_00_00_00")
    effect_owner = _require(
        slots, LOGARIUS_EFFECT_OWNER, EFFECT_OWNER_ARCHETYPE, "m25_00_00_00"
    )
    if (
        len(destinations) != 2
        or {slot.map_name for slot in destinations} != {"m23_00_00_00", "m23_00_00_01"}
        or len(core) != 1
        or len(sword) != 1
        or len(effect_owner) != 1
    ):
        raise ValueError(
            "Logarius/BSB requires two BSB states and one exact three-actor source roster"
        )
    core_native = _pin(CORE_PIN, with_anchor=False)
    sword_native = _pin(SWORD_PIN, with_anchor=True)
    effect_owner_native = _pin(EFFECT_OWNER_PIN, with_anchor=True)

    swap = Swap(
        destinations[0].logical_key,
        [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        BSB_ARCHETYPE,
        LOGARIUS_ARCHETYPE,
        warnings=[
            "experimental Logarius contract; arena fit, sword ownership and AP completion require runtime validation"
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
        [swap], list(destinations), dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError("Logarius primary swap has an ambiguous normalization plan")

    additions = []
    primary = []
    for target in destinations:
        for source, archetype, native, destination_part, destination_entity in (
            (
                sword[0],
                SWORD_ARCHETYPE,
                sword_native,
                ids.sword_destination_part,
                ids.sword_entity_id,
            ),
            (
                effect_owner[0],
                EFFECT_OWNER_ARCHETYPE,
                effect_owner_native,
                ids.effect_owner_destination_part,
                ids.effect_owner_entity_id,
            ),
        ):
            addition = {
                "source_map": source.map_name,
                "source_part": source.part_name,
                "source_anchor_part": core[0].part_name,
                "source_entity_id": source.entity_id,
                "source_archetype": asdict(archetype),
                "source_part_kind": "enemy",
                "destination_map": target.map_name,
                "destination_anchor_part": target.part_name,
                "destination_part": destination_part,
                "destination_entity_id": destination_entity,
                "allocation_evidence": ids.evidence,
            }
            addition.update(native)
            additions.append(addition)
        binding = {
            "source_map": core[0].map_name,
            "source_part": core[0].part_name,
            "source_entity_id": core[0].entity_id,
            "source_archetype": asdict(LOGARIUS_ARCHETYPE),
            "destination_map": target.map_name,
            "destination_part": target.part_name,
            "destination_entity_id": target.entity_id,
        }
        binding.update(core_native)
        primary.append(binding)

    event_recipes = [
        {
            "source_event_id": source_event,
            "destination_event_id": destination_event,
            "source_sha256": SOURCE_HASHES[source_event],
            "literal_remap": _event_remap(ids),
        }
        for source_event, destination_event in (
            (12504802, 12304802),
            (12504804, 12304804),
            (12504806, ids.sword_event_id),
            (12504807, ids.aura_event_id),
            (12504808, ids.cleanup_event_id),
        )
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {
            "experimental_boss_contract": "blood-starved-beast<-martyr-logarius"
        },
        "boss_contract": {
            "format": "bb-logarius-bsb-contract-v1",
            "arena": "blood-starved-beast",
            "donor": "martyr-logarius",
            "status": "planned",
            "runtime_status": "unobserved",
            "writer_status": "not_integrated",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(SOURCE_HASHES),
            "arena_hash_pins": dict(DESTINATION_HASHES),
            "preserved_destination_events": [
                12301800,
                12301801,
                12301803,
                12304810,
                12304811,
            ],
            "source_actor_event_review": {
                "12501800": "destination terminal 12301800 plus project sword lifecycle cleanup",
                "12501801": "destination death-sound event 12301801",
                "12501802": "destination entry event 12301802 with donor animation 7000",
                "12504810": "destination host fog event 12304810",
                "12504811": "destination co-op fog event 12304811",
                "12504802": "copied combat setup into 12304802",
                "12504803": "destination music event 12304803 with donor sp-effect trigger",
                "12504804": "copied camera behavior into 12304804",
                "12504806": f"copied sword lifecycle into {ids.sword_event_id}",
                "12504807": f"copied aura projectile into {ids.aura_event_id}",
                "12504808": f"copied phase cleanup into {ids.cleanup_event_id}",
            },
            "effect_owner_adapter": {
                "source_entity_id": LOGARIUS_EFFECT_OWNER,
                "destination_entity_id": ids.effect_owner_entity_id,
                "strategy": "materialize_original_c9010_actor",
                "projectile": 223200590,
                "attachment_target": BSB_ACTOR,
                "attachment_slot": 6,
                "evidence_status": "original_native_part_pinned_runtime_unobserved",
            },
            "event_patch": {
                "changed_events": event_recipes[:2],
                "added_events": event_recipes[2:]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": ids.lifecycle_event_id,
                        "kind": "destination_helper_cleanup",
                        "source_terminal_event": 12501800,
                        "source_sha256": SOURCE_HASHES[12501800],
                    }
                ],
                "event_zero_initializers": [
                    {
                        "source_event_id": source,
                        "destination_event_id": target,
                        "count": count,
                        "source_event_zero_sha256": SOURCE_HASHES[0],
                    }
                    for source, target, count in (
                        (12504806, ids.sword_event_id, 2),
                        (12504807, ids.aura_event_id, 1),
                        (12504808, ids.cleanup_event_id, 1),
                    )
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": ids.lifecycle_event_id,
                        "count": 1,
                        "kind": "destination_helper_cleanup",
                        "source_event_zero_sha256": SOURCE_HASHES[0],
                    }
                ],
            },
        },
        "boss_actor_additions": additions,
        "primary_init_source_bindings": primary,
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": destination_part,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": source_npc,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for target in destinations
            for destination_part, source_npc in (
                (ids.sword_destination_part, SWORD_ARCHETYPE.npc_param_id),
                (
                    ids.effect_owner_destination_part,
                    EFFECT_OWNER_ARCHETYPE.npc_param_id,
                ),
            )
        ],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }


def helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    """Shape Logarius requirements for allocate_actor_scaling after combining."""
    rows = plan.get("boss_actor_scaling_requirements", ())
    parents = {
        (row["destination_map"], row["destination_part"]): row["parent_logical_key"]
        for row in rows
    }
    if len(parents) != len(rows):
        raise ValueError("duplicate Logarius helper scaling destination")
    return parents
