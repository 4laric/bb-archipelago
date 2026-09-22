"""Evidence-pinned Logarius combat in Mergo's Wet Nurse arena.

Wet Nurse's original terminal, rewards, camera, fog/cutscene flow, and map-sound
slots remain destination-owned. Logarius uses direct health; a source-reviewed
bridge kills Wet Nurse's existing offstage proxy only after Logarius dies.
Static source evidence only; runtime behavior remains unobserved.
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
LOGARIUS_SOURCE = "event/m25_00_00_00.emevd.dcx.js"
WET_NURSE_SOURCE = "event/m26_00_00_00.emevd.dcx.js"
LOGARIUS_CORE, LOGARIUS_SWORD, LOGARIUS_EFFECT = 2500800, 2500801, 2500802
WET_CORE, WET_SUPPORT, WET_PROXY = 2600800, 2600801, 2600802
LOGARIUS_ARCHETYPE = Archetype("c2320", 232000, 232000, 0)
SWORD_ARCHETYPE = Archetype("c2321", 232100, 232100, 0)
EFFECT_ARCHETYPE = Archetype("c9010", 232000, 232000, 0)
WET_ARCHETYPE = Archetype("c5510", 551000, 551000, 0)

PROJECT_MIN, PROJECT_MAX = 12992600, 12992699
SOURCE_HASHES = {
    0: "f906cc00fd41625d4e479a9f0e261e6344708b7ea2728f850cb328efbf39a9ed",
    12501800: "8e7a5e07c7e871cbb44982c80436874fdf451d3c80c68af2969e15f78c6129bd",
    12504802: "a8819ae3d0e70e0ea1d5e0e9f662b9e19e7fcb4b07b160f6a84b2249413cc625",
    12504806: "dba1f97eec52c6f56df35f2f53813470690d7b83ffba3fd313459130cceae775",
    12504807: "9a3943748bcb8301baaf7978ea59899fc0cdd7318a15f6fb50c57be73f94157a",
    12504808: "fb6738bfefc7c4fb69af7def1f54386d186058b6a1b284a07e74004610e9f1fa",
}
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
class ActorPin:
    part_sha256: str
    talk_id: int = 0
    unk_t18: int = -1
    init_anim_id: int = -1
    damage_anim_id: int = -1
    anchor_sha256: str | None = None


CORE_PIN = ActorPin("7c8b12caf0fe7db72697966c66efa71900bd6c869b27521bfae694078e783011")
SWORD_PIN = ActorPin(
    "fc114097901492ce96524c9265c04a6c2606b3b825336723adb52c9064475b1d",
    anchor_sha256=CORE_PIN.part_sha256,
)
EFFECT_PIN = ActorPin(
    "7bd8e95bd08d4bfe30801d088983025c6c1593885dfc97cabff3ecc89c5c4984",
    anchor_sha256=CORE_PIN.part_sha256,
)
WET_PINS = {
    WET_CORE: "8ec99e63d52ac0ada984adabd723cce20900448cce7c041522cf90ac4b98faac",
    WET_SUPPORT: "01f71e6d7cc177feca59a4290ea3972aa2ace57dca81913aee136f4cc1b24bf8",
    WET_PROXY: "089c3c9baa7b41536b5dc68f02208b1b2287bf2aeac64c1c0135a089882400b3",
}


@dataclass(frozen=True)
class LogariusWetIds:
    sword_entity: int = 980500
    effect_entity: int = 980501
    sword_event: int = 12992600
    aura_event: int = 12992601
    phase_cleanup_event: int = 12992602
    proxy_bridge_event: int = 12992603
    helper_cleanup_event: int = 12992604

    def event_ids(self) -> tuple[int, ...]:
        return (
            self.sword_event,
            self.aura_event,
            self.phase_cleanup_event,
            self.proxy_bridge_event,
            self.helper_cleanup_event,
        )

    def helper_ids(self) -> tuple[int, int]:
        return self.sword_entity, self.effect_entity


DEFAULT_IDS = LogariusWetIds()


def _verify(text: str, pins: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        if (
            event not in blocks
            or hashlib.sha256(blocks[event].encode()).hexdigest() != digest
        ):
            raise ValueError(f"unsupported original {role} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Logarius/Wet Nurse expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(mapping.get(int(match[0]), int(match[0]))),
        text,
    )


def _end_event(block: str) -> str:
    head = re.sub(
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
        block.splitlines()[0],
    )
    return head + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


def _all_original_numbers() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return values


def _validate_ids(ids: LogariusWetIds, destination: str) -> None:
    events, helpers, original = (
        ids.event_ids(),
        ids.helper_ids(),
        _all_original_numbers(),
    )
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(events) != len(set(events))
        or any(not PROJECT_MIN <= value <= PROJECT_MAX for value in events)
        or set(events) & (local | original)
    ):
        raise ValueError(
            "Logarius/Wet Nurse event IDs must be collision-free project-owned 129926xx values"
        )
    if (
        len(helpers) != len(set(helpers))
        or any(not 980500 <= value <= 980599 for value in helpers)
        or set(helpers) & (local | original | set(events))
    ):
        raise ValueError(
            "Logarius/Wet Nurse helper IDs must be collision-free reserved 980500-range values"
        )


def _mapping(ids: LogariusWetIds) -> dict[int, int]:
    return {
        LOGARIUS_CORE: WET_CORE,
        LOGARIUS_SWORD: ids.sword_entity,
        LOGARIUS_EFFECT: ids.effect_entity,
        12501800: 12601800,
        12504223: 12604732,
        12504800: 12604800,
        12504802: 12604802,
        12504806: ids.sword_event,
        12504807: ids.aura_event,
        12504808: ids.phase_cleanup_event,
    }


def _initializer(
    event_zero: str, source_event: int, destination_event: int, count: int
) -> list[str]:
    found = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(found) != count:
        raise ValueError(
            f"Logarius Event(0) lacks {count} initializer witnesses for {source_event}"
        )
    return [_remap(line, {source_event: destination_event}) for line in found]


def patch_logarius_at_wet_nurse(
    destination: str, donor_source: str, ids: LogariusWetIds = DEFAULT_IDS
) -> str:
    """Port the Logarius direct-health closure while retaining Wet Nurse's terminal."""
    original, donor = _verify(destination, ARENA_HASHES, "Wet Nurse arena"), _verify(
        donor_source, SOURCE_HASHES, "Logarius donor"
    )
    _validate_ids(ids, destination)
    if set(ids.event_ids()) & set(original):
        raise ValueError(
            "Logarius/Wet Nurse added event ID collides with destination EMEVD"
        )
    remap = _mapping(ids)
    health = _remap(donor[12504802], remap)
    health = _replace_once(
        health, "CreatePlaylog(82);", "CreatePlaylog(88);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2500010, 98, Enabled);",
        "StartTimeMeasurement(2600010, 104, Enabled);",
        "destination time measurement",
    )
    health = _replace_once(
        health,
        "            SetNetworkUpdateAuthority(2600800, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(980500, AuthorityLevel.Forced);",
        "            SetNetworkUpdateAuthority(2600800, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(980500, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(2600801, AuthorityLevel.Forced);\n            SetNetworkUpdateAuthority(2600802, AuthorityLevel.Forced);",
        "retained Wet Nurse helper authority",
    )
    health = _replace_once(
        health,
        "    SetCharacterHPBarDisplay(2600800, Disabled);",
        "    SetCharacterHPBarDisplay(2600800, Disabled);\n    SetCharacterAIState(2600801, Disabled);\n    ChangeCharacterEnableState(2600801, Disabled);\n    SetCharacterHPBarDisplay(2600801, Disabled);\n    SetCharacterAIState(2600802, Disabled);\n    SetCharacterHPBarDisplay(2600802, Disabled);\n    SetCharacterGravity(2600802, Disabled);",
        "retained Wet Nurse helper setup",
    )
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
    aura, phase = _remap(donor[12504807], remap), _remap(donor[12504808], remap)
    music = _replace_once(
        original[12604803],
        "WaitFor(HPRatio(2600802) < 0.7);",
        "WaitFor(CharacterHasSpEffect(2600800, 5633));",
        "Logarius phase music trigger",
    )
    init = []
    for source, target, count in (
        (12504806, ids.sword_event, 2),
        (12504807, ids.aura_event, 1),
        (12504808, ids.phase_cleanup_event, 1),
    ):
        init.extend(_initializer(donor[0], source, target, count))
    init.extend(
        (
            f"    $InitializeEvent(0, {ids.proxy_bridge_event});",
            f"    $InitializeEvent(0, {ids.helper_cleanup_event});",
        )
    )
    constructor = _replace_once(
        original[0],
        "    $InitializeEvent(0, 12604840);",
        "    $InitializeEvent(0, 12604840);\n" + "\n".join(init),
        "controller initializer anchor",
    )
    bridge = f"""$Event({ids.proxy_bridge_event}, Default, function() {{
    EndIf(EventFlag(12601800));
    WaitFor(CharacterDead(2600800));
    EndIf(EventFlag(12601800));
    ForceCharacterDeath(2600802, false);
}});"""
    lifecycle = f"""$Event({ids.helper_cleanup_event}, Default, function() {{
    if (!ThisEvent()) {{
        WaitFor(EventFlag(12601800));
    }}
    ChangeCharacterEnableState({ids.sword_entity}, Disabled);
    ForceCharacterDeath({ids.sword_entity}, false);
    ChangeCharacterEnableState({ids.effect_entity}, Disabled);
    ForceCharacterDeath({ids.effect_entity}, false);
}});"""
    edits = {
        0: constructor,
        12604802: health,
        12604803: music,
        12604810: _end_event(original[12604810]),
        12604815: _end_event(original[12604815]),
        12604820: _end_event(original[12604820]),
        12604830: _end_event(original[12604830]),
        12604840: _end_event(original[12604840]),
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join((sword, aura, phase, bridge, lifecycle))
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(original) | set(ids.event_ids()):
        raise ValueError("Logarius/Wet Nurse patch changed event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(
                f"Logarius/Wet Nurse changed unrelated destination event {event}"
            )
    for event in (12601800, 12601801, 12601802, 12601803, 12604804, 12604806):
        if output[event] != original[event]:
            raise ValueError(
                "Logarius/Wet Nurse changed terminal, progression, opaque camera, or retained support setup"
            )
    copied = "\n".join(
        output[event]
        for event in (
            12604802,
            12604803,
            ids.sword_event,
            ids.aura_event,
            ids.phase_cleanup_event,
        )
    )
    if re.search(r"(?<!\d)(?:125|250)\d+(?!\d)", copied):
        raise ValueError(
            "Logarius/Wet Nurse copied combat body retains donor-map literal"
        )
    if (
        "CreateBulletOwner(980501)" not in output[12604802]
        or "DisplayBossHealthBar(Enabled, 2600800, 0, 232000)" not in output[12604802]
    ):
        raise ValueError("Logarius/Wet Nurse lost direct health or pinned bullet owner")
    return result


def _require(
    slots: Sequence[Slot],
    entity: int,
    archetype: Archetype,
    map_name: str | None = None,
) -> list[Slot]:
    found = sorted(
        (
            slot
            for slot in slots
            if slot.entity_id == entity
            and slot.archetype == archetype
            and (map_name is None or slot.map_name == map_name)
        ),
        key=lambda slot: slot.key,
    )
    if not found or any(slot.dummy or slot.talk_id for slot in found):
        raise ValueError(f"Logarius/Wet Nurse requires pinned ordinary actor {entity}")
    return found


def _pin(pin: ActorPin, anchor: bool = False) -> dict:
    if len(pin.part_sha256) != 64 or (anchor and pin.anchor_sha256 is None):
        raise ValueError("Logarius/Wet Nurse actor provenance pin is incomplete")
    provenance = {"format": "bb-boss-actor-pin-v1", "part_sha256": pin.part_sha256}
    if anchor:
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


def native_plan_logarius_at_wet_nurse(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: LogariusWetIds = DEFAULT_IDS,
) -> dict:
    donor = read_blob(BUNDLE, LOGARIUS_SOURCE).decode("utf-8-sig")
    arena = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
    _verify(donor, SOURCE_HASHES, "Logarius donor")
    _verify(arena, ARENA_HASHES, "Wet Nurse arena")
    _validate_ids(ids, arena)
    core, sword, effect = (
        _require(slots, LOGARIUS_CORE, LOGARIUS_ARCHETYPE, "m25_00_00_00"),
        _require(slots, LOGARIUS_SWORD, SWORD_ARCHETYPE, "m25_00_00_00"),
        _require(slots, LOGARIUS_EFFECT, EFFECT_ARCHETYPE, "m25_00_00_00"),
    )
    target, support, proxy = (
        _require(slots, WET_CORE, WET_ARCHETYPE, "m26_00_00_00"),
        _require(slots, WET_SUPPORT, WET_ARCHETYPE, "m26_00_00_00"),
        _require(slots, WET_PROXY, WET_ARCHETYPE, "m26_00_00_00"),
    )
    if (
        len(core) != 1
        or len(sword) != 1
        or len(effect) != 1
        or len(target) != 1
        or len(support) != 1
        or len(proxy) != 1
    ):
        raise ValueError(
            "Logarius/Wet Nurse requires exact three-actor source and destination roster"
        )
    swap = Swap(
        target[0].logical_key,
        [target[0].key],
        {target[0].key: target[0].archetype},
        WET_ARCHETYPE,
        LOGARIUS_ARCHETYPE,
        warnings=[
            "experimental Logarius-at-Wet-Nurse contract; terminal proxy bridge, sword ownership, and arena fit are runtime-unobserved"
        ],
        destinations={
            target[0].key: {
                "map_name": target[0].map_name,
                "entity_id": target[0].entity_id,
                "x": target[0].x,
                "y": target[0].y,
                "z": target[0].z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], target, dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "Logarius/Wet Nurse primary swap has an ambiguous normalization plan"
        )
    additions = []
    for source, archetype, pin, name, entity in (
        (
            sword[0],
            SWORD_ARCHETYPE,
            SWORD_PIN,
            "ap_logarius_wet_sword",
            ids.sword_entity,
        ),
        (
            effect[0],
            EFFECT_ARCHETYPE,
            EFFECT_PIN,
            "ap_logarius_wet_effect_owner",
            ids.effect_entity,
        ),
    ):
        row = {
            "source_map": source.map_name,
            "source_part": source.part_name,
            "source_anchor_part": core[0].part_name,
            "source_entity_id": source.entity_id,
            "source_archetype": asdict(archetype),
            "source_part_kind": "enemy",
            "destination_map": target[0].map_name,
            "destination_anchor_part": target[0].part_name,
            "destination_part": name,
            "destination_entity_id": entity,
            "allocation_evidence": "project-reserved Logarius helper ID; native writer checks Part/Region/Event collisions",
        }
        row.update(_pin(pin, True))
        additions.append(row)
    primary = {
        "source_map": core[0].map_name,
        "source_part": core[0].part_name,
        "source_entity_id": core[0].entity_id,
        "source_archetype": asdict(LOGARIUS_ARCHETYPE),
        "destination_map": target[0].map_name,
        "destination_part": target[0].part_name,
        "destination_entity_id": target[0].entity_id,
    }
    primary.update(_pin(CORE_PIN))
    remap = _mapping(ids)
    source_added = (
        (12504806, ids.sword_event),
        (12504807, ids.aura_event),
        (12504808, ids.phase_cleanup_event),
    )
    retained = [
        {
            "map": slot.map_name,
            "part": slot.part_name,
            "entity_id": slot.entity_id,
            "archetype": asdict(slot.archetype),
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": WET_PINS[slot.entity_id],
            },
            "source_initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": policy,
        }
        for slot, policy in (
            (support[0], "disabled until native terminal cleanup"),
            (proxy[0], "AI/bar hidden until Logarius death bridge"),
        )
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "mergos-wet-nurse<-martyr-logarius"},
        "boss_actor_additions": additions,
        "primary_init_source_bindings": [primary],
        "boss_contract": {
            "format": "bb-logarius-wet-nurse-contract-v1",
            "arena": "mergos-wet-nurse",
            "donor": "martyr-logarius",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(SOURCE_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "preserved_destination_events": [
                12601800,
                12601801,
                12601802,
                12601803,
                12604804,
                12604806,
            ],
            "opaque_actor_policy": "retain destination terminal and camera literal 2600803 unchanged; do not materialize it",
            "retained_destination_helpers": retained,
            "destination_music_policy": "retain Wet Nurse map-sound slots and region, substitute pinned Logarius 5633 phase trigger",
            "event_patch": {
                "changed_events": [
                    {
                        "destination_event_id": 12604802,
                        "source_event_id": 12504802,
                        "source_sha256": SOURCE_HASHES[12504802],
                    },
                    {
                        "destination_event_id": 12604803,
                        "source_event_id": None,
                        "kind": "destination_music_trigger",
                    },
                    *[
                        {
                            "destination_event_id": event,
                            "source_event_id": None,
                            "kind": "suppress_native_wet_controller",
                        }
                        for event in (12604810, 12604815, 12604820, 12604830, 12604840)
                    ],
                ],
                "added_events": [
                    {
                        "source_event_id": source,
                        "destination_event_id": dest,
                        "source_sha256": SOURCE_HASHES[source],
                        "literal_remap": remap,
                    }
                    for source, dest in source_added
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": event,
                        "kind": "destination_proxy_or_helper_bridge",
                    }
                    for event in (ids.proxy_bridge_event, ids.helper_cleanup_event)
                ],
            },
        },
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target[0].map_name,
                "destination_part": name,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": npc,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
            for name, npc in (
                ("ap_logarius_wet_sword", 232100),
                ("ap_logarius_wet_effect_owner", 232000),
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
