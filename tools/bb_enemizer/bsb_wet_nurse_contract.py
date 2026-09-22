"""Evidence-pinned BSB combat in Mergo's Wet Nurse destination arena.

The native Wet Nurse terminal remains authoritative: it observes its existing
offstage proxy ``2600802`` and retains its opaque ``2600803`` operand.  BSB has
direct health, so a reviewed bridge kills that proxy only after BSB actually
dies.  Runtime behavior remains unobserved.
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
WET_NURSE_SOURCE = "event/m26_00_00_00.emevd.dcx.js"

BSB = 2300800
WET_NURSE_CORE = 2600800
WET_NURSE_SUPPORT = 2600801
WET_NURSE_PROXY = 2600802
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
WET_NURSE_ARCHETYPE = Archetype("c5510", 551000, 551000, 0)

PROJECT_EVENT_MIN = 12991600
PROJECT_EVENT_MAX = 12991699

# Exact source event bodies decompiled from the committed user-input bundle.
DONOR_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}

# The destination pins cover every changed body and the opaque-terminal
# boundary. Other untouched destination events are checked byte-for-byte after
# patching.
ARENA_HASHES = {
    0: "bead3d1536484484169804138a1649d272cba5793b92b73179c6046c48aad1a0",
    12601800: "7dc6ddd943ac9e73c9b64e7fc4f6014db733573b39102f25ea905b3c1f36e291",
    12601801: "24fc8eac277a24b1447edc594c6fe14dfd406a8c4ee20ff9cb4a24e1bfd7b75f",
    12601802: "52825c64ffb75fcaf36996c80617c618c58182e0f0b34b74f7f5dc33dcf64864",
    12601803: "6c248a79ee0473faab7ffcb083c74d7395e9ad30fddddb5efad198bbfd8db06f",
    12604802: "09f0500c2acc77660cba27ac95235805b5410e652171616e9f07f3b2f401ae5f",
    12604803: "398aca1f47084e02f0d84294bd86de6c1ea857628d2e20a538974468b5660396",
    12604804: "c5a35148c3c7a4b94be4d11608b4ee97f0b79d08fca37fd7dfd15495d1107e4b",
    12604806: "abb36c87f40649e655c35dec16d046f58dc1c79b5e9aba3a456b58f51437dbae",
    12604810: "15e07a67e931dee231546741125aa97edeb8148b70ae4c975b1da2b75ec59277",
    12604815: "abcbb89ce93449ced754f1b5ce7733182a52eebe1fc14581c259b7d3e53124a7",
    12604820: "033223280a6c9ae639d560a796a9a172d2f8eb5fe40339e19040a52d4f87159e",
    12604830: "4440653d16d290874d8e396c8ceb581a78d0a6990388f0e1f94888e671ba4c2b",
    12604840: "f7f166e1072f4217a0ba93afb13fc8158def71c21f29d8b1c4810d97c5f5fed9",
}


@dataclass(frozen=True)
class NativePartPin:
    part_sha256: str
    talk_id: int
    unk_t18: int
    init_anim_id: int
    damage_anim_id: int


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
WET_NURSE_PART_PINS = {
    WET_NURSE_SUPPORT: NativePartPin(
        "01f71e6d7cc177feca59a4290ea3972aa2ace57dca81913aee136f4cc1b24bf8",
        0,
        -1,
        -1,
        -1,
    ),
    WET_NURSE_PROXY: NativePartPin(
        "089c3c9baa7b41536b5dc68f02208b1b2287bf2aeac64c1c0135a089882400b3",
        0,
        -1,
        -1,
        -1,
    ),
}


@dataclass(frozen=True)
class BsbWetNurseIds:
    phase_one: int = 12991600
    phase_two: int = 12991601
    death_to_proxy: int = 12991602

    def values(self) -> tuple[int, int, int]:
        return self.phase_one, self.phase_two, self.death_to_proxy


DEFAULT_IDS = BsbWetNurseIds()


def _verify(text: str, hashes: Mapping[int, str], label: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in hashes.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"BSB/Wet Nurse expected one {label}")
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


def _validate_ids(ids: BsbWetNurseIds, destination: str) -> None:
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
            "BSB/Wet Nurse IDs must be collision-free project-owned 129916xx values"
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


def _mapping(ids: BsbWetNurseIds) -> dict[int, int]:
    return {
        BSB: WET_NURSE_CORE,
        12301800: 12601800,
        12304800: 12604800,
        12304801: 12604801,
        12304802: 12604802,
        12304803: 12604803,
        12304807: ids.phase_one,
        12304808: ids.phase_two,
        2302801: 2602801,
        2303802: 2603802,
        2303803: 2603803,
        2300010: 2600010,
    }


def patch_bsb_at_wet_nurse(
    destination: str, donor_source: str, ids: BsbWetNurseIds = DEFAULT_IDS
) -> str:
    """Install direct BSB combat while preserving the native proxy terminal."""
    arena = _verify(destination, ARENA_HASHES, "Wet Nurse arena")
    donor = _verify(donor_source, DONOR_HASHES, "BSB donor")
    _validate_ids(ids, destination)
    if set(ids.values()).intersection(arena):
        raise ValueError("BSB/Wet Nurse added event ID collides with destination EMEVD")
    remap = _mapping(ids)

    health = _remap(donor[12304802], remap)
    health = _replace_once(
        health,
        "            IssueBossRoomEntryNotification(0);\n"
        "            SetNetworkUpdateAuthority(2600800, AuthorityLevel.Forced);",
        "            if (!EventFlag(12604732)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n"
        "            SetNetworkUpdateAuthority(2600800, AuthorityLevel.Forced);\n"
        "            SetNetworkUpdateAuthority(2600801, AuthorityLevel.Forced);\n"
        "            SetNetworkUpdateAuthority(2600802, AuthorityLevel.Forced);",
        "destination entry notification guard",
    )
    health = _replace_once(
        health,
        "    SetCharacterHPBarDisplay(2600800, Disabled);",
        "    SetCharacterHPBarDisplay(2600800, Disabled);\n"
        "    SetCharacterAIState(2600801, Disabled);\n"
        "    ChangeCharacterEnableState(2600801, Disabled);\n"
        "    SetCharacterHPBarDisplay(2600801, Disabled);\n"
        "    SetCharacterAIState(2600802, Disabled);\n"
        "    SetCharacterHPBarDisplay(2600802, Disabled);\n"
        "    SetCharacterGravity(2600802, Disabled);",
        "retained support/proxy initialization",
    )
    health = _replace_once(
        health,
        "    SetEventFlag(12604800, ON);",
        "    SetEventFlag(12604732, ON);\n    SetEventFlag(12604800, ON);",
        "destination battle state",
    )
    health = _replace_once(
        health, "CreatePlaylog(86);", "CreatePlaylog(88);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2600010, 102, Enabled);",
        "StartTimeMeasurement(2600010, 104, Enabled);",
        "destination time measurement",
    )
    music = _remap(donor[12304803], remap)
    phase_one = _remap(donor[12304807], remap)
    phase_two = _remap(donor[12304808], remap)

    bridge = f"""$Event({ids.death_to_proxy}, Default, function() {{
    EndIf(EventFlag(12601800));
    WaitFor(CharacterDead(2600800));
    EndIf(EventFlag(12601800));
    ForceCharacterDeath(2600802, false);
}});"""
    init = "\n".join(
        (
            "    " + _initializer(donor[0], 12304807, ids.phase_one).strip(),
            "    " + _initializer(donor[0], 12304808, ids.phase_two).strip(),
            f"    $InitializeEvent(0, {ids.death_to_proxy});",
        )
    )
    edits = {
        0: _replace_once(
            arena[0],
            "    $InitializeEvent(0, 12604840);",
            "    $InitializeEvent(0, 12604840);\n" + init,
            "project controller anchor",
        ),
        12604802: health,
        12604803: music,
        # 12604804 is deliberately left byte-for-byte: it uses opaque 2600803.
        12604810: _end_event(arena[12604810]),
        12604815: _end_event(arena[12604815]),
        12604820: _end_event(arena[12604820]),
        12604830: _end_event(arena[12604830]),
        12604840: _end_event(arena[12604840]),
        ids.phase_one: phase_one,
        ids.phase_two: phase_two,
        ids.death_to_proxy: bridge,
    }
    result = (
        _replace_events(
            destination,
            {event: body for event, body in edits.items() if event in arena},
        ).rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.values())
        + "\n"
    )
    out = event_blocks(result)
    if set(out) != set(arena) | set(ids.values()):
        raise ValueError("BSB/Wet Nurse changed event identities")
    for event, body in arena.items():
        if event not in edits and out[event] != body:
            raise ValueError(f"BSB/Wet Nurse changed unrelated arena event {event}")
    if out[12601800] != arena[12601800] or out[12604804] != arena[12604804]:
        raise ValueError("BSB/Wet Nurse changed opaque terminal or camera")
    if (
        "CreateReferredDamagePair" in out[12604802]
        or "SetCharacterImmortality(2600800" in out[12604802]
    ):
        raise ValueError("BSB/Wet Nurse retained incompatible proxy health setup")
    for event in (12604810, 12604815, 12604820, 12604830, 12604840):
        if out[event].splitlines()[1] != "    EndEvent();":
            raise ValueError(
                "BSB/Wet Nurse left a native core/support combat controller active"
            )
    copied = "\n".join(
        out[event] for event in (12604802, 12604803, ids.phase_one, ids.phase_two)
    )
    if re.search(r"(?<!\d)(?:123|230)\d+(?!\d)", copied):
        raise ValueError("BSB/Wet Nurse copied combat body retains a donor-map literal")
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
        raise ValueError(f"unsupported BSB/Wet Nurse placement provenance for {entity}")
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


def native_plan_bsb_at_wet_nurse(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: BsbWetNurseIds = DEFAULT_IDS,
) -> dict:
    """Return the one BSB primary swap and pins for its native retained helpers."""
    bundled_arena = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
    _verify(bundled_arena, ARENA_HASHES, "Wet Nurse arena")
    _verify(
        read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig"), DONOR_HASHES, "BSB donor"
    )
    _validate_ids(ids, bundled_arena)
    sources = _require(slots, BSB, BSB_ARCHETYPE)
    core = _require(slots, WET_NURSE_CORE, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    support = _require(slots, WET_NURSE_SUPPORT, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    proxy = _require(slots, WET_NURSE_PROXY, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    if (
        {slot.map_name for slot in sources} != set(BSB_SOURCE_PINS)
        or len(sources) != 2
        or len(core) != 1
        or len(support) != 1
        or len(proxy) != 1
    ):
        raise ValueError(
            "BSB/Wet Nurse requires two exact BSB states and its three native actors"
        )
    source, target = (
        next(slot for slot in sources if slot.map_name == "m23_00_00_00"),
        core[0],
    )
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        BSB_ARCHETYPE,
        warnings=[
            "experimental BSB-at-Wet-Nurse contract; runtime terminal bridge behavior unobserved"
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
            "BSB/Wet Nurse primary swap has an ambiguous normalization plan"
        )
    retained = []
    for slot in (support[0], proxy[0]):
        pin = WET_NURSE_PART_PINS[slot.entity_id]
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
                "policy": (
                    "retain_native_part_disabled_alive_until_destination_completion"
                    if slot.entity_id == WET_NURSE_SUPPORT
                    else "retain_native_offstage_proxy_disabled_until_bsb_death_bridge"
                ),
            }
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {
            "experimental_boss_contract": "mergos-wet-nurse<-blood-starved-beast"
        },
        "boss_contract": {
            "format": "bb-bsb-wet-nurse-contract-v1",
            "arena": "mergos-wet-nurse",
            "donor": "blood-starved-beast",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [
                12601800,
                12601801,
                12601802,
                12601803,
                12604804,
                12604806,
            ],
            "opaque_external_reference": {
                "entity_id": 2600803,
                "events": [12601800, 12604804],
                "policy": "preserve_literal_unchanged",
            },
            "retained_destination_helpers": retained,
            "helper_policy": "support remains disabled; offstage proxy stays AI/bar hidden until BSB death bridge",
            "terminal_policy": "native 12601800 remains byte-identical and observes only proxy 2600802",
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
