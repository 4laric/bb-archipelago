"""Source-pinned Father Gascoigne combat in Witch of Hemwick's arena."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .amelia_witch_contract import (
    ARENA_HASHES,
    SECOND_PIN,
    WITCH_ARCHETYPE,
    WITCH_PIN,
)
from .boss_canary import event_blocks
from .bosses import parse_events
from .gascoigne_contract import (
    BEAST_ARCHETYPE,
    BEAST_PART,
    GASCOIGNE_BEAST,
    GASCOIGNE_HUMAN,
    HUMAN_ARCHETYPE,
    HUMAN_PART,
    SOURCE_HASHES,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
GASCOIGNE_SOURCE = "event/m24_01_00_00.emevd.dcx.js"
WITCH_SOURCE = "event/m22_00_00_00.emevd.dcx.js"
WITCH, SECOND = 2200800, 2200801
SECOND_ARCHETYPE = Archetype("c2100", 210020, 210021, 0)
SOURCE_MAP = "m24_01_00_00"
DESTINATION_MAP = "m22_00_00_00"
HELPER_ENTITY = 981800
HELPER_PART = "ap_gascoigne_beast"

# Original native actor evidence from --boss-actor-pins.  The human TalkID is
# deliberately verified before the destination override suppresses Cathedral
# Ward dialogue state in Hemwick.
HUMAN_PIN = "74f068dbc07cc857e64d6405ad11b4e032fcbb18db192047f6e3d74fe7eccdde"
BEAST_PIN = "19098d7da3476516f7a30723313e69c6cb21a54e035ea9623ac473bf42ebbb41"
HUMAN_INITIALIZATION = {
    "talk_id": 241330,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}
BEAST_INITIALIZATION = {
    "talk_id": 0,
    "unk_t18": -1,
    "init_anim_id": -1,
    "damage_anim_id": -1,
}


@dataclass(frozen=True)
class GascoigneWitchIds:
    phase: int = 12994000
    human_special: int = 12994001
    beast_special: int = 12994002
    death_bridge: int = 12994003
    retirement: int = 12994004
    notification_flag: int = 12994020
    beast_entity: int = HELPER_ENTITY

    def events(self) -> tuple[int, ...]:
        return (
            self.phase,
            self.human_special,
            self.beast_special,
            self.death_bridge,
            self.retirement,
        )

    def project_ids(self) -> tuple[int, ...]:
        return self.events() + (self.notification_flag,)


DEFAULT_IDS = GascoigneWitchIds()

# Pin exactly the original bodies this adapter consumes.  The donor terminal
# and music are not copied or inspected by this route.
DONOR_HASHES = {
    event: SOURCE_HASHES[event]
    for event in (0, 12414802, 12414804, 12414807, 12414808, 12414809)
}


def _verify(text: str, pins: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, digest in pins.items():
        if hashlib.sha256(blocks.get(event, "").encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gascoigne/Witch expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _end_event(block: str) -> str:
    header = re.sub(
        r"function\(([^)]*)\)",
        lambda match: "function("
        + ", ".join(
            item.strip()
            if item.strip().startswith("unused_")
            else "unused_" + item.strip()
            for item in match[1].split(",")
            if item.strip()
        )
        + ")",
        block.splitlines()[0],
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


@cache
def _original_ids() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(rb"(?<![\w])-?\d+(?![\w])", body))
        )
    rows = read_prefix(BUNDLE, "mined/")
    for row in rows["mined/msb_enemies.tsv"].decode("utf-8-sig").splitlines()[1:]:
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate_ids(ids: GascoigneWitchIds, destination: str = "") -> None:
    project = ids.project_ids()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    used = local | _original_ids()
    if (
        len(project) != len(set(project))
        or any(not 12994000 <= value <= 12994099 for value in project)
        or set(project) & used
        or ids.beast_entity != HELPER_ENTITY
        or ids.beast_entity in used
    ):
        raise ValueError(
            "Gascoigne/Witch IDs must be collision-free reserved 129940xx/9818xx values"
        )


def _mapping(ids: GascoigneWitchIds) -> dict[int, int]:
    return {
        GASCOIGNE_HUMAN: WITCH,
        GASCOIGNE_BEAST: ids.beast_entity,
        12411800: 12201800,
        12414800: 12204800,
        12414801: 12204801,
        12414802: 12204802,
        12414804: 12204804,
        12414807: ids.phase,
        12414808: ids.human_special,
        12414809: ids.beast_special,
        12414223: ids.notification_flag,
        2410010: 2200010,
    }


def _initializer(event_zero: str, source_event: int, destination_event: int) -> str:
    rows = [
        line
        for line in event_zero.splitlines()
        if re.match(
            rf"\s*\$InitializeEvent\([^,]+,\s*{source_event}(?:,|\))", line
        )
    ]
    if len(rows) != 1:
        raise ValueError(
            f"Gascoigne/Witch source Event(0) lacks initializer {source_event}"
        )
    return _remap(rows[0], {source_event: destination_event})


def patch_gascoigne_at_witch(
    destination: str, donor_source: str, ids: GascoigneWitchIds = DEFAULT_IDS
) -> str:
    arena = _verify(destination, ARENA_HASHES, "Witch arena")
    donor = _verify(donor_source, DONOR_HASHES, "Gascoigne donor")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)

    health = _remap(donor[12414802], mapping)
    health = _replace_once(
        health, "CreatePlaylog(80);", "CreatePlaylog(88);", "destination playlog"
    )
    health = _replace_once(
        health,
        "StartTimeMeasurement(2200010, 96, Enabled);",
        "StartTimeMeasurement(2200010, 104, Enabled);",
        "destination measurement",
    )
    activation = _replace_once(
        arena[12201802],
        "    if (!(PlayerInsightAmount() == 0 && CharacterType(10000, TargetType.Alive))) {\n"
        "        ForceAnimationPlayback(2200800, 3011, false, false, false);\n"
        "    }\n",
        "",
        "Witch-only insight animation",
    )
    music = _replace_once(
        arena[12204803],
        "hpFlagArea &= CharacterHPValue(2200800) == 1 || CharacterHPValue(2200801) == 1;",
        f"hpFlagArea &= EventFlag({ids.phase});",
        "Gascoigne phase music trigger",
    )
    camera = _remap(donor[12414804], mapping)
    if camera.count("SetLockcamSlotNumber(24, 1,") != 4:
        raise ValueError("Gascoigne/Witch source camera binding drift")
    camera = camera.replace(
        "SetLockcamSlotNumber(24, 1,", "SetLockcamSlotNumber(22, 0,"
    )

    source_events = (
        (12414807, ids.phase),
        (12414808, ids.human_special),
        (12414809, ids.beast_special),
    )
    initializers = [
        _initializer(donor[0], source_event, destination_event)
        for source_event, destination_event in source_events
    ]
    initializers.extend(
        (
            f"    $InitializeEvent(0, {ids.death_bridge});",
            f"    $InitializeEvent(0, {ids.retirement});",
        )
    )
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12204843);",
        "    $InitializeEvent(0, 12204843);\n" + "\n".join(initializers),
        "combat initializer anchor",
    )

    imported = {}
    for source_event, destination_event in source_events:
        body = _remap(donor[source_event], mapping)
        if source_event == 12414807:
            body = _replace_once(
                body,
                "    EndIf(EventFlag(9337));\n"
                "    $InitializeEvent(0, 9350, 1);\n"
                "    SetEventFlag(9337, ON);\n",
                "",
                "Gascoigne source progression tail",
            )
        imported[destination_event] = body

    bridge = f"""$Event({ids.death_bridge}, Default, function() {{
    EndIf(EventFlag(12201800));
    humanDead = CharacterDead(2200800);
    beastDead = CharacterDead({ids.beast_entity});
    WaitFor(humanDead || beastDead);
    ForceCharacterDeath({ids.beast_entity}, false);
    ForceCharacterDeath(2200800, false);
    ForceCharacterDeath(2200801, false);
}});"""
    retirement = f"""$Event({ids.retirement}, Default, function() {{
    ChangeCharacterEnableState(2200801, Disabled);
    SetCharacterAIState(2200801, Disabled);
    SetCharacterHPBarDisplay(2200801, Disabled);
    DeactivateGenerator(2205000, Disabled);
    DeactivateGenerator(2205001, Disabled);
    DeactivateGenerator(2205002, Disabled);
    ChangeCharacterEnableState(2200810, Disabled);
    ChangeCharacterEnableState(2200811, Disabled);
    ChangeCharacterEnableState(2200812, Disabled);
    WaitFor(EventFlag(12201800));
    ChangeCharacterEnableState({ids.beast_entity}, Disabled);
    ForceCharacterDeath({ids.beast_entity}, false);
}});"""

    edits = {
        0: constructor,
        12201802: activation,
        12204802: health,
        12204803: music,
        12204804: camera,
    }
    for event in (
        12204807,
        12204808,
        12204810,
        12204811,
        12204812,
        12204814,
        12204820,
        12204830,
        12204832,
        12204835,
        12204838,
        12204839,
        12204840,
        12204841,
        12204842,
        12204843,
    ):
        edits[event] = _end_event(arena[event])

    additions = (*imported.values(), bridge, retirement)
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.events()):
        missing = sorted(set(arena).union(ids.events()) - set(output))
        extra = sorted(set(output) - set(arena).union(ids.events()))
        raise ValueError(
            f"Gascoigne/Witch changed event identities (missing={missing}, extra={extra})"
        )
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Gascoigne/Witch changed unrelated Witch event {event}")
    for event in (12201800, 12201801, 12201803, 12201804, 12204805):
        if output[event] != arena[event]:
            raise ValueError(
                "Gascoigne/Witch changed Witch terminal, rewards, co-op, or sound cleanup"
            )
    copied = "\n".join((health, camera, *additions))
    if re.search(r"(?<!\d)(?:124|241)\d+(?!\d)", copied):
        raise ValueError("Gascoigne/Witch copied body retains donor-map literal")
    return result


def _one_slot(
    slots: Sequence[Slot], map_name: str, entity: int, archetype: Archetype, role: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.map_name == map_name
        and slot.entity_id == entity
        and slot.archetype == archetype
        and not slot.dummy
    ]
    if len(found) != 1:
        raise ValueError(f"Gascoigne/Witch requires one pinned {role}")
    return found[0]


def native_plan_gascoigne_at_witch(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: GascoigneWitchIds = DEFAULT_IDS,
) -> dict:
    donor_text = read_blob(BUNDLE, GASCOIGNE_SOURCE).decode("utf-8-sig")
    arena_text = read_blob(BUNDLE, WITCH_SOURCE).decode("utf-8-sig")
    _verify(donor_text, DONOR_HASHES, "Gascoigne donor")
    _verify(arena_text, ARENA_HASHES, "Witch arena")
    _validate_ids(ids, arena_text)
    human = _one_slot(
        slots, SOURCE_MAP, GASCOIGNE_HUMAN, HUMAN_ARCHETYPE, "Gascoigne human"
    )
    beast = _one_slot(
        slots, SOURCE_MAP, GASCOIGNE_BEAST, BEAST_ARCHETYPE, "Gascoigne beast"
    )
    target = _one_slot(slots, DESTINATION_MAP, WITCH, WITCH_ARCHETYPE, "primary Witch")
    second = _one_slot(
        slots, DESTINATION_MAP, SECOND, SECOND_ARCHETYPE, "second Witch"
    )
    if human.talk_id != 241330 or beast.talk_id or target.talk_id or second.talk_id:
        raise ValueError("Gascoigne/Witch source or destination TalkID drift")

    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        human.archetype,
        warnings=[
            "experimental Gascoigne-at-Witch contract; arena fit and runtime transformation are unobserved"
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
    addition = {
        "source_map": beast.map_name,
        "source_part": BEAST_PART,
        "source_anchor_part": HUMAN_PART,
        "source_entity_id": GASCOIGNE_BEAST,
        "source_archetype": asdict(BEAST_ARCHETYPE),
        "source_part_kind": "enemy",
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": BEAST_PIN,
            "anchor_sha256": HUMAN_PIN,
        },
        "source_initialization": dict(BEAST_INITIALIZATION),
        "destination_map": target.map_name,
        "destination_anchor_part": target.part_name,
        "destination_part": HELPER_PART,
        "destination_entity_id": ids.beast_entity,
        "allocation_evidence": "reserved Gascoigne/Witch helper; full original corpus scan",
    }
    primary = {
        "source_map": human.map_name,
        "source_part": human.part_name,
        "source_entity_id": GASCOIGNE_HUMAN,
        "source_archetype": asdict(HUMAN_ARCHETYPE),
        "source_talk_id": human.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": HUMAN_PIN,
        },
        "source_initialization": dict(HUMAN_INITIALIZATION),
        "destination_talk_id_override": 0,
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": WITCH,
        "destination_original_talk_id": target.talk_id,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
            "destination_talk_id_override",
        ],
    }
    literal_map = _mapping(ids)
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "witch-of-hemwick<-father-gascoigne"},
        "boss_actor_additions": [addition],
        "primary_init_source_bindings": [primary],
        "boss_actor_scaling_requirements": [
            {
                "destination_map": target.map_name,
                "destination_part": HELPER_PART,
                "parent_logical_key": swap.logical_key,
                "source_npc_param_id": BEAST_ARCHETYPE.npc_param_id,
                "strategy": "allocate_distinct_verified_helper_clone",
            }
        ],
        "boss_contract": {
            "format": "bb-gascoigne-witch-contract-v1",
            "arena": "witch-of-hemwick",
            "donor": "father-gascoigne",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "source_hash_pins": dict(DONOR_HASHES),
            "arena_hash_pins": dict(ARENA_HASHES),
            "source_actor_pins": {
                "human": {
                    "map": SOURCE_MAP,
                    "part": HUMAN_PART,
                    "entity_id": GASCOIGNE_HUMAN,
                    "part_sha256": HUMAN_PIN,
                    "source_initialization": dict(HUMAN_INITIALIZATION),
                },
                "beast": {
                    "map": SOURCE_MAP,
                    "part": BEAST_PART,
                    "entity_id": GASCOIGNE_BEAST,
                    "part_sha256": BEAST_PIN,
                    "anchor_sha256": HUMAN_PIN,
                    "source_initialization": dict(BEAST_INITIALIZATION),
                },
            },
            "preserved_destination_events": [
                12201800,
                12201801,
                12201803,
                12201804,
                12204805,
            ],
            "retained_destination_helpers": [
                {
                    "map": second.map_name,
                    "part": second.part_name,
                    "entity_id": SECOND,
                    "archetype": asdict(second.archetype),
                    "source_provenance": {
                        "format": "bb-boss-actor-pin-v1",
                        "part_sha256": SECOND_PIN,
                    },
                    "source_initialization": {
                        "talk_id": 0,
                        "unk_t18": -1,
                        "init_anim_id": -1,
                        "damage_anim_id": -1,
                    },
                    "policy": "hidden alive until actual Gascoigne-form death, then killed by bridge",
                }
            ],
            "terminal_policy": "preserve byte-identical two-Witch terminal; kill both terminal bodies only after human-or-beast death",
            "minion_policy": "retire all Witch revival, minion and generator controllers before combat",
            "event_literal_map": {str(key): value for key, value in literal_map.items()},
            "event_patch": {
                "changed_events": [
                    0,
                    12201802,
                    12204802,
                    12204803,
                    12204804,
                    12204807,
                    12204808,
                    12204810,
                    12204811,
                    12204812,
                    12204814,
                    12204820,
                    12204830,
                    12204832,
                    12204835,
                    12204838,
                    12204839,
                    12204840,
                    12204841,
                    12204842,
                    12204843,
                ],
                "added_events": [
                    {
                        "source_event_id": source,
                        "destination_event_id": destination,
                        "source_sha256": SOURCE_HASHES[source],
                        "literal_remap": literal_map,
                    }
                    for source, destination in (
                        (12414807, ids.phase),
                        (12414808, ids.human_special),
                        (12414809, ids.beast_special),
                    )
                ]
                + [
                    {
                        "source_event_id": None,
                        "destination_event_id": event,
                        "kind": "death_bridge_or_retirement",
                    }
                    for event in (ids.death_bridge, ids.retirement)
                ],
            },
        },
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
