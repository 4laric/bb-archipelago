"""Source-pinned Blood-starved Beast combat at the Living Failures arena.

The visible Living Failures body becomes BSB.  The original aggregate proxy
remains disabled and alive until the BSB death bridge satisfies the untouched
Living Failures terminal.  Maria's shared m35 events remain destination state.
Static source and compiler evidence does not establish runtime behavior.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
BSB_SOURCE = "event/m23_00_00_00.emevd.dcx.js"
LIVING_FAILURES_SOURCE = "event/m35_00_00_00.emevd.dcx.js"

BSB = 2300800
BSB_ARCHETYPE = Archetype("c2090", 209000, 209000, 0)
BSB_COMPLETION = 12301800

PROXY = 3500850
PRIMARY = 3500851
RETIRED_BODIES = (3500852, 3500853, 3500854)
SUPPORT = 3500860
PRIMARY_ARCHETYPE = Archetype("c4030", 403000, 403000, 0)
PROXY_ARCHETYPE = Archetype("c4030", 403050, 1, 0)
BODY_ARCHETYPES = {
    3500852: Archetype("c4030", 403010, 403010, 0),
    3500853: Archetype("c4030", 403020, 403020, 0),
    3500854: Archetype("c4030", 403030, 403030, 0),
    SUPPORT: Archetype("c4031", 403100, 403100, 0),
}

PROJECT_MIN, PROJECT_MAX = 12991800, 12991899

DONOR_HASHES = {
    0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
    12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
    12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
    12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}

# Pins cover every edited, suppressed, or explicitly preserved Living Failures
# controller. Maria event bodies are asserted byte-for-byte after patching.
ARENA_HASHES = {
    # The installed original's DarkScript 3.6.3 output retains a reviewed
    # unrelated Event(0) normalization; both bodies are accepted verbatim.
    0: (
        "f7acdb00c7384ac586de81b0c37e7e58d08c11876c76a04a9648844f4689d0a9",
        "78d94eb81ed0b21b0f7a14aaaefc5f5ec487d28e3029e8912e6551dd71d2cf50",
    ),
    13501850: "b79df4f8ad5180202c6472759007c74447068f9235f7f488a61504d8f0ad14e5",
    13501851: "016b1ad769f7d2418e1e21b389723b3c0c2638f6a7586dbc5d22212532e6ad09",
    13501852: "da74488656dad3be9b52b2bc80572dcad0f0e425f1e3fc262ec53b1934ce62f6",
    13504850: "ee5295a138474b14c4536e5a2f565a613cb75bb626534500ade747a62d6cf1ac",
    13504851: "5ab017700ac152293cc6ac477014ffd91475e42c442127f0dee45535f38fa151",
    13504852: "2c85d01e33eeec23bed4c9bc483963fd7f955443a7ee440356c909b3d5d7791e",
    13504853: "5385ba65580ca716f6a460aa1388f94828fe21e37337c6a8ba343636bd23bd64",
    13504854: "89743ba1d4c316b756d5c0d1f9b2b88fac0cb1adea48fc9e478ff17dd7631cfc",
    13504855: "b88b59e76261a3d5e0e57e853d650c8b5ce1692c42f81d5a25462fd4ff49e824",
    13504856: "26c6142b9b0b87e0f6e07310801d88260adda6705885fe961e840a72daf47f13",
    13504857: "57a669fe93a5c6fac00bb17cd335a812d773a9b70efdf816aef6353c249ba8e9",
    13504865: "c3ab637d4af4fc24cbeedde16f099ad50f1e8c2425d4ffbc15eb9900b9faa2ce",
    13504880: "eae0b65165cb984da0c3fcbb6c9b5c41d2d6b8212b5bb08e22930a29bccf9665",
    13504881: "1f43eccdd0539ab63a6f8eed248465fbbcbfa60bff1754dd608290784d1b1aec",
    13504885: "291d0ef2d64fecc6a8cd53062b44a306a597904397d6ce38417a64487db79d83",
    13504890: "b0004862a666a1854c3aba4a8c91d9156436438230c641f135aba30c26415388",
    13504895: "f3c5fdbaf791591392fdcdf79c3c99bf9571a962016c75d6ae3040fc6dfd733a",
    13505655: "7c6514d959890ac80969f9f1a3f1398ee102e2409ddb050fb2b9cdfdae537637",
    13505656: "d39373dc11ff84ded0a4de3e246325e7f46ddf197ee71b69f1c8ea7bd3eb83b7",
    13505661: "3dca956d1a60d3e53c851b84144710923dd5d0c98c9dc87f54c7dd276b066e4a",
    13505662: "e8b466710c0de022e6f0f561a0a0689afc03f88eb16d59144a18a37bb1f7cefd",
    13505680: "3bd8f41292a02f99878b780f87b10c32d6925b7027ebd7d9a01ba41eb22015c9",
}

# These parts stay native rather than becoming unpinned numeric operands in
# the BSB health bridge. They come from --boss-actor-pins m35_00_00_00.
RETAINED_PINS = {
    PROXY: "ea596036d27313cb14f09921e698351fb97de32ce37fcab291d10f5dfcc2abbf",
    3500852: "77607d287e7e2e2e2f282f22c8b78aa634a6ba6577a1c830b27420f86e095eea",
    3500853: "706a81c500efc571356102e5adc0a8ba3e081e64e063fc7d5d5c68bbb056f366",
    3500854: "63e33c77647f60713d39de7f80b1f4dabca1b9856446843a9e9c9a69643663d4",
    SUPPORT: "5df657d5b8ea855cfd14b59cbd8a54c46ea41ebe0b8a5df7da67b6b0c3e360e8",
}
BSB_SOURCE_PINS = {
    "m23_00_00_00": "55d69ae3862270c13509c2842a52f10a036713d21e24ba3d7f2cba2d3e884891",
    "m23_00_00_01": "38ae3c392bf19848f3a0bb0b213358eb52e9f9bf327ebcaa8efc3c4a89b8b84d",
}


@dataclass(frozen=True)
class BsbLivingFailuresIds:
    phase_one: int = 12991800
    phase_two: int = 12991801
    death_to_proxy: int = 12991802
    retire_helpers: int = 12991803

    def values(self) -> tuple[int, int, int, int]:
        return self.phase_one, self.phase_two, self.death_to_proxy, self.retire_helpers


DEFAULT_IDS = BsbLivingFailuresIds()
SUPPRESSED_EVENTS = (
    13504865,
    13504880,
    13504881,
    13504885,
    13504890,
    13504895,
    13505655,
    13505656,
    13505661,
    13505662,
    13505680,
)
MARIA_EVENTS = (
    13501800,
    13501801,
    13501802,
    13501803,
    13504800,
    13504801,
    13504802,
    13504803,
    13504804,
    13504805,
    13504806,
    13504807,
    13504822,
)


def _verify(
    blocks: Mapping[int, str], hashes: Mapping[int, str | tuple[str, ...]], role: str
) -> None:
    for event, digest in hashes.items():
        allowed = (digest,) if isinstance(digest, str) else digest
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"BSB/Living Failures expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(
        r"(?<![\w])-?\d+(?![\w])",
        lambda match: str(values.get(int(match[0]), int(match[0]))),
        text,
    )


def _end_event(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(
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


@cache
def _original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    return values


def _validate_ids(ids: BsbLivingFailuresIds, destination: str = "") -> None:
    values = ids.values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    if (
        len(set(values)) != len(values)
        or any(value < PROJECT_MIN or value > PROJECT_MAX for value in values)
        or set(values).intersection(local | _original_literals())
    ):
        raise ValueError(
            "BSB/Living Failures IDs must be collision-free project-owned 129918xx values"
        )


def _initializer(event_zero: str, source_event: int, destination_event: int) -> str:
    matches = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))", line
        )
    ]
    if len(matches) != 1:
        raise ValueError(
            f"BSB Event(0) lacks one initializer witness for {source_event}"
        )
    return re.sub(
        r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
        r"\g<1>" + str(destination_event),
        matches[0],
        count=1,
    )


def _mapping(ids: BsbLivingFailuresIds) -> dict[int, int]:
    return {
        BSB: PRIMARY,
        BSB_COMPLETION: 13501850,
        12304800: 13504858,
        12304801: 13504859,
        12304802: 13504852,
        12304803: 13504853,
        12304804: 13504854,
        12304807: ids.phase_one,
        12304808: ids.phase_two,
        2302801: 3502812,
        2303802: 3503812,
        2303803: 3503813,
        2300010: 3500011,
    }


def _entry_without_failure_animation(block: str) -> str:
    result = block
    for line in (
        "    ForceAnimationPlayback(3500851, 9000, true, false, false);\n",
        "    ForceAnimationPlayback(3500851, 9060, false, false, false);\n",
        "    RequestCharacterAIReplan(3500851);\n",
    ):
        result = _replace_once(result, line, "", "Living Failures-only entry animation")
    return result


def _health(source: str, ids: BsbLivingFailuresIds) -> str:
    result = _remap(source, _mapping(ids))
    result = _replace_once(
        result,
        "    SetCharacterHPBarDisplay(3500851, Disabled);\n",
        "    SetCharacterHPBarDisplay(3500851, Disabled);\n"
        "    SetCharacterAIState(3500850, Disabled);\n"
        "    SetCharacterHPBarDisplay(3500850, Disabled);\n"
        "    SetCharacterGravity(3500850, Disabled);\n"
        + "".join(
            f"    SetCharacterAIState({actor}, Disabled);\n"
            f"    SetCharacterHPBarDisplay({actor}, Disabled);\n"
            for actor in (*RETIRED_BODIES, SUPPORT)
        ),
        "retained Living Failures helper initialization",
    )
    result = _replace_once(
        result,
        "            IssueBossRoomEntryNotification(0);\n"
        "            SetNetworkUpdateAuthority(3500851, AuthorityLevel.Forced);",
        "            if (!EventFlag(13504860)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n"
        "            SetNetworkUpdateAuthority(3500851, AuthorityLevel.Forced);\n"
        "            SetNetworkUpdateAuthority(3500850, AuthorityLevel.Forced);",
        "Living Failures entry authority",
    )
    result = _replace_once(
        result,
        "    SetEventFlag(13504858, ON);",
        "    SetEventFlag(13504860, ON);\n    SetEventFlag(13504858, ON);",
        "Living Failures battle state",
    )
    result = _replace_once(
        result, "CreatePlaylog(86);", "CreatePlaylog(136);", "Living Failures playlog"
    )
    return _replace_once(
        result,
        "StartTimeMeasurement(3500011, 102, Enabled);",
        "StartTimeMeasurement(3500011, 158, Enabled);",
        "Living Failures time measurement",
    )


def _camera(source: str) -> str:
    result = _remap(source, _mapping(DEFAULT_IDS))
    result = _replace_once(
        result,
        "    SetNetworkSyncState(Disabled);",
        "    SetNetworkSyncState(Disabled);\n    EndIf(EventFlag(13501850));",
        "completed-arena camera guard",
    )
    result = _replace_once(
        result,
        "    SetLockcamSlotNumber(23, 0, 1);",
        "    EndIf(EventFlag(13501850));\n    SetLockcamSlotNumber(23, 0, 1);",
        "camera activation completion guard",
    )
    result = _replace_once(
        result,
        "SetLockcamSlotNumber(23, 0,",
        "SetLockcamSlotNumber(35, 0,",
        "BSB camera map binding",
    )
    if "SetLockcamSlotNumber(23," in result:
        raise ValueError("BSB/Living Failures retained BSB camera map")
    return result


def _retire_helpers(ids: BsbLivingFailuresIds) -> str:
    actors = (*RETIRED_BODIES, SUPPORT)
    disable = "".join(
        f"    SetCharacterAIState({actor}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({actor}, Disabled);\n"
        f"    ChangeCharacterEnableState({actor}, Disabled);\n"
        for actor in actors
    )
    death = "".join(f"    ForceCharacterDeath({actor}, false);\n" for actor in actors)
    return f"""$Event({ids.retire_helpers}, Default, function() {{
    DeactivateGenerator(3503814, Disabled);
    DeactivateGenerator(3503815, Disabled);
    DeactivateGenerator(3503816, Disabled);
    DeactivateGenerator(3503817, Disabled);
{disable}    if (EventFlag(13501850)) {{
{death}        EndEvent();
    }}
    WaitFor(EventFlag(13501850));
{death}}});"""


def _death_bridge(ids: BsbLivingFailuresIds) -> str:
    return f"""$Event({ids.death_to_proxy}, Default, function() {{
    EndIf(EventFlag(13501850));
    WaitFor(CharacterDead(3500851));
    EndIf(EventFlag(13501850));
    ForceCharacterDeath(3500850, false);
}});"""


def patch_bsb_at_living_failures(
    destination: str,
    donor_source: str,
    ids: BsbLivingFailuresIds = DEFAULT_IDS,
) -> str:
    """Install BSB on visible body 3500851 and preserve terminal 13501850."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, ARENA_HASHES, "Living Failures arena")
    _verify(donor, DONOR_HASHES, "BSB donor")
    _validate_ids(ids, destination)
    mapping = _mapping(ids)
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 13505680);",
        "    $InitializeEvent(0, 13505680);\n"
        f"    {_initializer(donor[0], 12304807, ids.phase_one).strip()}\n"
        f"    {_initializer(donor[0], 12304808, ids.phase_two).strip()}\n"
        f"    $InitializeEvent(0, {ids.death_to_proxy});\n"
        f"    $InitializeEvent(0, {ids.retire_helpers});",
        "Living Failures combat initializer anchor",
    )
    edits = {
        0: constructor,
        13501851: _entry_without_failure_animation(arena[13501851]),
        13504852: _health(donor[12304802], ids),
        13504853: _remap(donor[12304803], mapping),
        13504854: _camera(donor[12304804]),
        **{event: _end_event(arena[event]) for event in SUPPRESSED_EVENTS},
        ids.phase_one: _remap(donor[12304807], mapping),
        ids.phase_two: _remap(donor[12304808], mapping),
        ids.death_to_proxy: _death_bridge(ids),
        ids.retire_helpers: _retire_helpers(ids),
    }
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.values())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.values()):
        raise ValueError("BSB/Living Failures changed event identities")
    for event, body in arena.items():
        if event not in edits and output[event] != body:
            raise ValueError(
                f"BSB/Living Failures changed unrelated arena event {event}"
            )
    if output[13501850] != arena[13501850]:
        raise ValueError("BSB/Living Failures changed the destination terminal")
    for event in MARIA_EVENTS:
        if output[event] != arena[event]:
            raise ValueError("BSB/Living Failures changed shared Maria progression")
    copied = "\n".join(
        output[event]
        for event in (13504852, 13504853, 13504854, ids.phase_one, ids.phase_two)
    )
    if re.search(r"(?<!\d)(?:123|230)\d+(?!\d)", copied):
        raise ValueError("BSB/Living Failures copied combat retains donor-map literals")
    return result


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
        slot.dummy or slot.archetype != archetype for slot in matches
    ):
        raise ValueError(
            f"unsupported BSB/Living Failures placement provenance for {entity}"
        )
    return matches


def _binding(source: Slot, destination: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {
            "format": "bb-boss-actor-pin-v1",
            "part_sha256": BSB_SOURCE_PINS[source.map_name],
        },
        "source_initialization": {
            "talk_id": 0,
            "unk_t18": -1,
            "init_anim_id": -1,
            "damage_anim_id": -1,
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


def native_plan_bsb_at_living_failures(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: BsbLivingFailuresIds = DEFAULT_IDS,
) -> dict:
    """Return BSB's visible-body swap and pinned disabled-native helpers."""
    arena_source = read_blob(BUNDLE, LIVING_FAILURES_SOURCE).decode("utf-8-sig")
    donor_source = read_blob(BUNDLE, BSB_SOURCE).decode("utf-8-sig")
    _verify(event_blocks(arena_source), ARENA_HASHES, "Living Failures arena")
    _verify(event_blocks(donor_source), DONOR_HASHES, "BSB donor")
    _validate_ids(ids, arena_source)
    bsb = _require(slots, BSB, BSB_ARCHETYPE)
    target = _require(slots, PRIMARY, PRIMARY_ARCHETYPE, "m35_00_00_00")
    helpers = [
        *_require(slots, PROXY, PROXY_ARCHETYPE, "m35_00_00_00"),
        *[
            slot
            for entity, archetype in BODY_ARCHETYPES.items()
            for slot in _require(slots, entity, archetype, "m35_00_00_00")
        ],
    ]
    if (
        {slot.map_name for slot in bsb} != set(BSB_SOURCE_PINS)
        or len(bsb) != 2
        or len(target) != 1
        or len(helpers) != 5
    ):
        raise ValueError(
            "BSB/Living Failures requires two BSB states and five retained m35 helpers"
        )
    source = next(slot for slot in bsb if slot.map_name == "m23_00_00_00")
    primary = target[0]
    swap = Swap(
        primary.logical_key,
        [primary.key],
        {primary.key: primary.archetype},
        primary.archetype,
        BSB_ARCHETYPE,
        warnings=[
            "experimental BSB-at-Living-Failures contract; runtime behavior unobserved"
        ],
        destinations={
            primary.key: {
                "map_name": primary.map_name,
                "entity_id": primary.entity_id,
                "x": primary.x,
                "y": primary.y,
                "z": primary.z,
            }
        },
    )
    changes, skips = plan_scaling(
        [swap], [primary], dict(npcs), dict(effects), boss_tiers=True
    )
    if len(changes) > 1 or (changes and skips):
        raise ValueError(
            "BSB/Living Failures primary swap has an ambiguous normalization plan"
        )
    retained = [
        {
            "map": slot.map_name,
            "part": slot.part_name,
            "entity_id": slot.entity_id,
            "archetype": asdict(slot.archetype),
            "source_provenance": {
                "format": "bb-boss-actor-pin-v1",
                "part_sha256": RETAINED_PINS[slot.entity_id],
            },
            "source_initialization": {
                "talk_id": 0,
                "unk_t18": -1,
                "init_anim_id": -1,
                "damage_anim_id": -1,
            },
            "policy": (
                "retain_offstage_proxy_disabled_alive_until_bsb_death_bridge"
                if slot.entity_id == PROXY
                else "retain_wave_or_support_disabled_until_destination_completion"
            ),
        }
        for slot in helpers
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-bsb-living-failures-contract-v1",
            "arena": "living-failures",
            "donor": "blood-starved-beast",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "attachment_event_ids": asdict(ids),
            "physical_swap_count": 1,
            "preserved_destination_events": [
                13501850,
                13501852,
                13504850,
                13504851,
                13504855,
                13504856,
                13504857,
            ],
            "preserved_maria_events": list(MARIA_EVENTS),
            "terminal_policy": "retain byte-identical aggregate proxy terminal; bridge BSB death to proxy only afterward",
            "retained_destination_helpers": retained,
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(DONOR_HASHES),
        },
        "primary_init_source_bindings": [_binding(source, primary)],
        "scaling": {
            "enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes),
            "changes": [change.json() for change in changes],
            "skip_count": len(skips),
            "skips": skips,
        },
    }
