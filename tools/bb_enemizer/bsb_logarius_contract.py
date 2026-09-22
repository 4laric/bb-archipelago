"""Evidence-pinned Blood-starved Beast combat in Logarius' Cainhurst arena.

Cainhurst retains entry, fog, reward, completion and AP progression.  BSB owns
the active health, music, camera and two phase controllers.  Logarius' sword
and c9010 projectile owner remain their original native Parts, disabled and
alive until destination completion performs cleanup.  Runtime behavior is
unobserved.
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
BSB_SOURCE = "event/m23_00_00_00.emevd.dcx.js"
LOGARIUS_SOURCE = "event/m25_00_00_00.emevd.dcx.js"

BSB = 2300800
LOGARIUS_CORE = 2500800
LOGARIUS_SWORD = 2500801
LOGARIUS_EFFECT_OWNER = 2500802
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
LOGARIUS_ARCHETYPE = Archetype("c2320", 232000, 232000, 0)
SWORD_ARCHETYPE = Archetype("c2321", 232100, 232100, 0)
EFFECT_OWNER_ARCHETYPE = Archetype("c9010", 232000, 232000, 0)

PROJECT_EVENT_MIN = 12991300
PROJECT_EVENT_MAX = 12991399

DONOR_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}
ARENA_HASHES = {
    0: "f906cc00fd41625d4e479a9f0e261e6344708b7ea2728f850cb328efbf39a9ed",
    12501800: "8e7a5e07c7e871cbb44982c80436874fdf451d3c80c68af2969e15f78c6129bd",
    12501801: "752c098d59f5b3c00482b78f1ecbaa771d7fa084bef22e9e490784bfc5725797",
    12501802: "91d992106cdd9de1298ea848def19f816af24302f50dbf56f67cf5f5932c2e71",
    12501803: "c7e28f999f30a6198d27a76ecbad530de1cd5b2899a50f91516892ab11416e2c",
    12504802: "a8819ae3d0e70e0ea1d5e0e9f662b9e19e7fcb4b07b160f6a84b2249413cc625",
    12504803: "edee08431133d70220856551eb1b4518e7e8898c80fcbde9448a81537e9a7e0a",
    12504804: "d64bb9fa786b4cf26dae37451b8ca76de2a42bbff3bed4d47ce70ca28d32db42",
    12504805: "1b07e41f954c785e112ea6dff7cc76f8d8b1dbbe243c42f15b31d8ace95f09a7",
    12504806: "dba1f97eec52c6f56df35f2f53813470690d7b83ffba3fd313459130cceae775",
    12504807: "9a3943748bcb8301baaf7978ea59899fc0cdd7318a15f6fb50c57be73f94157a",
    12504808: "fb6738bfefc7c4fb69af7def1f54386d186058b6a1b284a07e74004610e9f1fa",
    12504810: "247053c43384e582535e4d4c26497797719d3d0e1b01026a425fd7f2efc9b6ec",
    12504811: "25b151f4961f4832b989524527f8db3584b798e83c9c064b16fc83358578a39a",
}


@dataclass(frozen=True)
class NativePartPin:
    part_sha256: str
    talk_id: int
    unk_t18: int
    init_anim_id: int
    damage_anim_id: int


# Original-map reports produced by BBEnemizerWriter --boss-actor-pins.
BSB_SOURCE_PINS = {
    "m23_00_00_00": NativePartPin(
        "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
        0,
        -1,
        -1,
        -1,
    ),
    "m23_00_00_01": NativePartPin(
        "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
        0,
        -1,
        -1,
        -1,
    ),
}
LOGARIUS_PART_PINS = {
    LOGARIUS_CORE: NativePartPin(
        "7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011",
        0,
        -1,
        -1,
        -1,
    ),
    LOGARIUS_SWORD: NativePartPin(
        "fc114097901492ce96524c9265c04a6c2606b3b825336723adb52c9064475b1d",
        0,
        -1,
        -1,
        -1,
    ),
    LOGARIUS_EFFECT_OWNER: NativePartPin(
        "7bd8e95bd08d4bfe30801d088983025c6c1593885dfc97cabff3ecc89c5c4984",
        0,
        -1,
        -1,
        -1,
    ),
}


@dataclass(frozen=True)
class BsbLogariusIds:
    phase_one: int = 12991300
    phase_two: int = 12991301
    helper_cleanup: int = 12991302

    def values(self) -> tuple[int, int, int]:
        return self.phase_one, self.phase_two, self.helper_cleanup


DEFAULT_IDS = BsbLogariusIds()


def _verify(text: str, hashes: Mapping[int, str], label: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in hashes.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"BSB/Logarius expected one {label}")
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


def _all_original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return values


def _validate_ids(ids: BsbLogariusIds, destination: str) -> None:
    values = ids.values()
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if (
        len(set(values)) != len(values)
        or any(
            not isinstance(value, int)
            or not PROJECT_EVENT_MIN <= value <= PROJECT_EVENT_MAX
            for value in values
        )
        or set(values).intersection(local | _all_original_literals())
    ):
        raise ValueError(
            "BSB/Logarius IDs must be collision-free project-owned 129913xx values"
        )


def _initializer(event_zero: str, source_event: int, destination_event: int) -> str:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(calls) != 1:
        raise ValueError(
            f"BSB Event(0) lacks one initializer witness for {source_event}"
        )
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
        r"\g<1>" + str(destination_event),
        calls[0],
        count=1,
    )


def _mapping(ids: BsbLogariusIds) -> dict[int, int]:
    return {
        BSB: LOGARIUS_CORE,
        12301800: 12501800,
        12304800: 12504800,
        12304801: 12504801,
        12304802: 12504802,
        12304803: 12504803,
        12304804: 12504804,
        12304807: ids.phase_one,
        12304808: ids.phase_two,
        2302801: 2502802,
        2303802: 2503802,
        2303803: 2503803,
        2300010: 2500010,
    }


def patch_bsb_at_logarius(
    destination: str, donor_source: str, ids: BsbLogariusIds = DEFAULT_IDS
) -> str:
    """Install BSB combat without taking ownership of Cainhurst progression."""
    arena = _verify(destination, ARENA_HASHES, "Logarius arena")
    donor = _verify(donor_source, DONOR_HASHES, "BSB donor")
    _validate_ids(ids, destination)
    if set(ids.values()).intersection(arena):
        raise ValueError("BSB/Logarius added event ID collides with destination EMEVD")
    remap = _mapping(ids)

    health = _remap(donor[12304802], remap)
    health = _replace_once(
        health,
        "            IssueBossRoomEntryNotification(0);\n"
        "            SetNetworkUpdateAuthority(2500800, AuthorityLevel.Forced);",
        "            if (!EventFlag(12504223)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n"
        "            SetNetworkUpdateAuthority(2500800, AuthorityLevel.Forced);",
        "Cainhurst notification flag",
    )
    health = _replace_once(
        health,
        "    SetEventFlag(12504800, ON);",
        "    SetEventFlag(12504223, ON);\n    SetEventFlag(12504800, ON);",
        "Cainhurst battle state",
    )
    health = _replace_once(
        health, "CreatePlaylog(86);", "CreatePlaylog(82);", "Cainhurst playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2500010, 102, Enabled);",
        "StartTimeMeasurement(2500010, 98, Enabled);",
        "Cainhurst time measurement",
    )
    music = _remap(donor[12304803], remap)
    camera = _remap(donor[12304804], remap)
    camera = _replace_once(
        camera,
        "    SetNetworkSyncState(Disabled);\n    WaitFor(",
        "    SetNetworkSyncState(Disabled);\n"
        "    EndIf(EventFlag(12501800));\n"
        "    WaitFor(",
        "Cainhurst completed-save camera guard",
    )
    camera = _replace_once(
        camera,
        "SetLockcamSlotNumber(23, 0, 1)",
        "SetLockcamSlotNumber(25, 0, 1)",
        "Cainhurst lockcam",
    )
    phase_one = _remap(donor[12304807], remap)
    phase_two = _remap(donor[12304808], remap)
    activation = _replace_once(
        arena[12501802],
        "ForceAnimationPlayback(2500800, 7000, false, false, false);",
        "ForceAnimationPlayback(2500800, 7001, false, false, false);",
        "BSB entry animation",
    )

    initializers = "\n".join(
        (
            _initializer(donor[0], 12304807, ids.phase_one),
            _initializer(donor[0], 12304808, ids.phase_two),
            f"    $InitializeEvent(0, {ids.helper_cleanup});",
        )
    )
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12504808);",
        "    $InitializeEvent(0, 12504808);\n" + initializers,
        "BSB combat initializer anchor",
    )
    cleanup = f"""$Event({ids.helper_cleanup}, Default, function() {{
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
}});"""
    edits = {
        0: constructor,
        12501802: activation,
        12504802: health,
        12504803: music,
        12504804: camera,
        12504806: _end_event(arena[12504806]),
        12504807: _end_event(arena[12504807]),
        12504808: _end_event(arena[12504808]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((phase_one, phase_two, cleanup))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.values()):
        raise ValueError("BSB/Logarius patch changed event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"BSB/Logarius changed unrelated arena event {event_id}")
    for event_id in (12501800, 12501801, 12501803, 12504805, 12504810, 12504811):
        if output[event_id] != arena[event_id]:
            raise ValueError(
                "BSB/Logarius changed Cainhurst completion, reward or fog progression"
            )
    constructor_output = output[0]
    for event_id in (
        12504802,
        12504803,
        12504804,
        ids.phase_one,
        ids.phase_two,
        ids.helper_cleanup,
    ):
        count = len(
            re.findall(
                r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                constructor_output,
            )
        )
        if count != 1:
            raise ValueError(
                f"BSB/Logarius Event(0) must initialize active controller {event_id} once"
            )
    copied = "\n".join(
        output[event]
        for event in (12504802, 12504803, 12504804, ids.phase_one, ids.phase_two)
    )
    if re.search(r"(?<!\d)(?:123|230)\d+(?!\d)", copied):
        raise ValueError("BSB/Logarius copied combat body retains a donor-map literal")
    return result


def _require(
    slots: Sequence[Slot],
    entity: int,
    archetype: Archetype,
    map_name: str | None = None,
) -> list[Slot]:
    result = sorted(
        (
            slot
            for slot in slots
            if slot.entity_id == entity
            and (map_name is None or slot.map_name == map_name)
        ),
        key=lambda slot: slot.key,
    )
    if not result or any(
        slot.dummy or slot.talk_id or slot.archetype != archetype for slot in result
    ):
        raise ValueError(f"unsupported BSB/Logarius placement provenance for {entity}")
    return result


def _native_binding(source: Slot, destination: Slot, pin: NativePartPin) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
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


def native_plan_bsb_at_logarius(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: BsbLogariusIds = DEFAULT_IDS,
) -> dict:
    """Return one BSB primary swap while retaining pinned Cainhurst helpers."""
    bundled_arena = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
    _verify(bundled_arena, ARENA_HASHES, "Logarius arena")
    _verify(
        read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig"), DONOR_HASHES, "BSB donor"
    )
    _validate_ids(ids, bundled_arena)
    sources = _require(slots, BSB, BSB_ARCHETYPE)
    core = _require(slots, LOGARIUS_CORE, LOGARIUS_ARCHETYPE, "m25_00_00_00")
    sword = _require(slots, LOGARIUS_SWORD, SWORD_ARCHETYPE, "m25_00_00_00")
    owner = _require(
        slots, LOGARIUS_EFFECT_OWNER, EFFECT_OWNER_ARCHETYPE, "m25_00_00_00"
    )
    if (
        {slot.map_name for slot in sources} != set(BSB_SOURCE_PINS)
        or len(sources) != 2
        or len(core) != 1
        or len(sword) != 1
        or len(owner) != 1
    ):
        raise ValueError(
            "BSB/Logarius requires two exact BSB states and one three-actor Cainhurst roster"
        )
    source = next(slot for slot in sources if slot.map_name == "m23_00_00_00")
    target = core[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        LOGARIUS_ARCHETYPE,
        BSB_ARCHETYPE,
        warnings=[
            "experimental BSB-at-Logarius contract; runtime arena, helper and AP behavior require validation"
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
        raise ValueError(
            "BSB/Logarius primary swap has an ambiguous normalization plan"
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
        "options": {
            "experimental_boss_contract": "martyr-logarius<-blood-starved-beast"
        },
        "boss_contract": {
            "format": "bb-bsb-logarius-contract-v1",
            "arena": "martyr-logarius",
            "donor": "blood-starved-beast",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [
                12501800,
                12501801,
                12501803,
                12504805,
                12504810,
                12504811,
            ],
            "retained_destination_helpers": retained,
            "helper_policy": "disable alive at initialization; destination completion then disables immortality and kills",
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(DONOR_HASHES),
        },
        "primary_init_source_bindings": [
            _native_binding(source, target, BSB_SOURCE_PINS[source.map_name])
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
