"""Pinned Orphan of Kos combat at Father Gascoigne's two-body arena.

The emitted patch and native plan are offline construction evidence.  Runtime
entrance, arena fit, combat, and completion behavior remain unobserved.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks
from .bosses import parse_events
from .gascoigne_arena import GASCOIGNE_ARENA_HASHES
from .model import Archetype, Slot, Swap
from .orphan_contract import SOURCE_ALTERNATE_HASHES, SOURCE_HASHES as ORPHAN_HASHES
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
ORPHAN_SOURCE = "event/m36_00_00_00.emevd.dcx.js"
GASCOIGNE_SOURCE = "event/m24_01_00_00.emevd.dcx.js"
MAP_STATES = ("m24_01_00_00", "m24_01_00_01", "m24_01_00_11")

ORPHAN_CORE, ORPHAN_PHASE, ORPHAN_SUPPORT = 3600800, 3600801, 3600803
GASCOIGNE_HUMAN, GASCOIGNE_BEAST = 2410810, 2410811
CORE = Archetype("c4540", 454000, 454000, 0)
PHASE = Archetype("c4541", 454100, 454100, 0)
SUPPORT = Archetype("c4543", 454300, 454300, 0)
HUMAN = Archetype("c2710", 271000, 271000, 0)
BEAST = Archetype("c2720", 272000, 272000, 0)

EVENT_MIN, EVENT_MAX = 12991700, 12991799
SUPPORT_ENTITY = 980007
SUPPORT_PART = "ap_orphan_support"

# Gascoigne's death cue is independent from the protected OR terminal.  Pin
# it too, because the adapter promises not to touch either actor's aftermath.
GASCOIGNE_PINS = {
    **GASCOIGNE_ARENA_HASHES,
    12411801: "ba2c1d24b517fe59049626335841912c3ee5ae505aca6abf2956a560eb5b4eaf",
}


@dataclass(frozen=True)
class OrphanGascoigneIds:
    combat_ready_flag: int
    phase_event: int
    support_event: int
    player_effect_event: int
    phase_camera_event: int
    cleanup_event: int
    support_entity: int = SUPPORT_ENTITY
    support_part: str = SUPPORT_PART
    evidence: str = (
        "Orphan/Gascoigne support allocation v1; full original actor and operand scan"
    )

    def event_values(self) -> tuple[int, ...]:
        return (
            self.combat_ready_flag,
            self.phase_event,
            self.support_event,
            self.player_effect_event,
            self.phase_camera_event,
            self.cleanup_event,
        )

    def added_events(self) -> tuple[int, ...]:
        return (
            self.phase_event,
            self.support_event,
            self.player_effect_event,
            self.phase_camera_event,
            self.cleanup_event,
        )


DEFAULT_IDS = OrphanGascoigneIds(
    12991700, 12991720, 12991730, 12991740, 12991750, 12991760
)


def _verify(
    blocks: Mapping[int, str],
    pins: Mapping[int, str | tuple[str, ...]],
    role: str,
    alternates: Mapping[int, str] | None = None,
) -> None:
    for event, digest in pins.items():
        expected = (digest,) if isinstance(digest, str) else digest
        alternate = (alternates or {}).get(event)
        allowed = (*expected, alternate) if alternate is not None else expected
        actual = hashlib.sha256(blocks.get(event, "").encode()).hexdigest()
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Orphan/Gascoigne expected one {label}")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1 : event.last_line] = edits[
                event.event_id
            ].splitlines()
    return "\n".join(lines) + "\n"


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
                item.strip()
                if item.strip().startswith("unused_")
                else "unused_" + item.strip()
            )
            for item in match[1].split(",")
            if item.strip()
        )
        + ")",
        header,
    )
    return header + "\n    EndEvent();\n});"


@cache
def _original_ids() -> set[int]:
    values = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig")))
        )
    rows = read_prefix(BUNDLE, "mined/")
    enemy_rows = (
        rows.get("mined/msb_enemies.tsv", b"").decode("utf-8-sig").splitlines()[1:]
    )
    for row in enemy_rows:
        columns = row.split("\t")
        if len(columns) > 3 and columns[3].lstrip("-").isdigit():
            values.add(int(columns[3]))
    return values


def _validate_ids(ids: OrphanGascoigneIds, destination: str = "") -> None:
    events = ids.event_values()
    local = set(map(int, re.findall(r"(?<![\w])-?\d+(?![\w])", destination)))
    original_ids = _original_ids()
    if (
        len(set(events)) != len(events)
        or any(event < EVENT_MIN or event > EVENT_MAX for event in events)
        or ids.support_entity != SUPPORT_ENTITY
        or ids.support_part != SUPPORT_PART
        or not ids.evidence.strip()
        or set(events).intersection(local | original_ids)
        or ids.support_entity in original_ids
    ):
        raise ValueError(
            "Orphan/Gascoigne ID collides with an original actor or EMEVD literal"
        )


def _mapping(ids: OrphanGascoigneIds) -> dict[int, int]:
    return {
        ORPHAN_CORE: GASCOIGNE_HUMAN,
        ORPHAN_PHASE: GASCOIGNE_BEAST,
        ORPHAN_SUPPORT: ids.support_entity,
        13601800: 12411800,
        13604802: 12414802,
        13604803: 12414803,
        13604804: 12414804,
        13604808: 12414800,
        13604809: 12414801,
        13604810: 12414223,
        13604812: ids.combat_ready_flag,
        13604820: ids.phase_event,
        13604830: ids.support_event,
        13604840: ids.player_effect_event,
        13604850: ids.phase_camera_event,
        3603802: 2413812,
        3603803: 2413813,
        3602802: 2412812,
        3600010: 2410010,
    }


def _health(source: str, mapping: Mapping[int, int]) -> str:
    result = _replace_once(
        source,
        "    SetCharacterAIState(3600801, Disabled);\n",
        "    SetCharacterAIState(3600801, Disabled);\n"
        "    ChangeCharacterEnableState(3600801, Disabled);\n"
        "    SetCharacterAIState(3600803, Disabled);\n"
        "    SetCharacterHPBarDisplay(3600803, Disabled);\n"
        "    ChangeCharacterEnableState(3600803, Disabled);\n",
        "phase/support initial state",
    )
    result = _replace_once(
        result,
        "L5:\n    if (!EventFlag(13604820)) {",
        "L5:\n    if (EventFlag(13604820)) {\n"
        "        ChangeCharacterEnableState(3600801, Enabled);\n"
        "    }\n"
        "    if (!EventFlag(13604820)) {",
        "saved phase visibility",
    )
    return _remap(result, mapping)


def _phase(source: str, mapping: Mapping[int, int]) -> str:
    result = _replace_once(
        source,
        "    ChangeCharacterEnableState(3600800, Disabled);\n"
        "    SetCharacterGravity(3600801, Enabled);",
        "    ChangeCharacterEnableState(3600800, Disabled);\n"
        "    ChangeCharacterEnableState(3600801, Enabled);\n"
        "    SetCharacterGravity(3600801, Enabled);",
        "phase actor enable",
    )
    return _remap(result, mapping)


def _support(source: str, mapping: Mapping[int, int], ids: OrphanGascoigneIds) -> str:
    result = _replace_once(
        source,
        "    WaitFor(CharacterHasEventMessage(3600801, 100));\n"
        "    RequestCharacterAICommand(3600803, 10, 0);",
        "    WaitFor(CharacterHasEventMessage(3600801, 100));\n"
        "    ChangeCharacterEnableState(3600803, Enabled);\n"
        "    SetCharacterAIState(3600803, Enabled);\n"
        "    RequestCharacterAICommand(3600803, 10, 0);",
        "support helper enable",
    )
    return _remap(result, mapping)


def _camera(source: str, mapping: Mapping[int, int]) -> str:
    result = _remap(source, mapping)
    for old, new, label in (
        (
            "SetLockcamSlotNumber(34, 0, 1)",
            "SetLockcamSlotNumber(24, 1, 1)",
            "active lockcam",
        ),
        (
            "SetLockcamSlotNumber(36, 0, 0)",
            "SetLockcamSlotNumber(24, 1, 0)",
            "clear lockcam",
        ),
    ):
        if result.count(old) != 2:
            raise ValueError(f"Orphan/Gascoigne expected two source {label} calls")
        result = result.replace(old, new)
    if "SetLockcamSlotNumber(34," in result or "SetLockcamSlotNumber(36," in result:
        raise ValueError("Orphan/Gascoigne retained a source camera map binding")
    return result


def _cleanup(ids: OrphanGascoigneIds) -> str:
    return f"""$Event({ids.cleanup_event}, Default, function() {{
    WaitFor(EventFlag(12411800));
    ChangeCharacterEnableState(2410810, Disabled);
    ForceCharacterDeath(2410810, false);
    ChangeCharacterEnableState(2410811, Disabled);
    ForceCharacterDeath(2410811, false);
    ChangeCharacterEnableState({ids.support_entity}, Disabled);
    ForceCharacterDeath({ids.support_entity}, false);
}});"""


def patch_orphan_at_gascoigne(
    destination: str, donor_source: str, ids: OrphanGascoigneIds = DEFAULT_IDS
) -> str:
    """Keep Gascoigne's terminal/cutscene while transplanting Orphan combat."""
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, GASCOIGNE_PINS, "Gascoigne arena")
    _verify(donor, ORPHAN_HASHES, "Orphan donor", SOURCE_ALTERNATE_HASHES)
    _validate_ids(ids, destination)
    mapping = _mapping(ids)
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12414809);",
        "    $InitializeEvent(0, 12414809);\n"
        + "\n".join(
            f"    $InitializeEvent(0, {event});" for event in ids.added_events()
        ),
        "Orphan initializer anchor",
    )
    edits = {
        0: constructor,
        12414802: _health(donor[13604802], mapping),
        12414803: _remap(donor[13604803], mapping),
        12414804: _camera(donor[13604804], mapping),
        12414807: _end_event(arena[12414807]),
        12414808: _end_event(arena[12414808]),
        12414809: _end_event(arena[12414809]),
        ids.phase_event: _phase(donor[13604820], mapping),
        ids.support_event: _support(donor[13604830], mapping, ids),
        ids.player_effect_event: _remap(donor[13604840], mapping),
        ids.phase_camera_event: _remap(donor[13604850], mapping).replace(
            "SetLockcamSlotNumber(36, 0,", "SetLockcamSlotNumber(24, 1,"
        ),
        ids.cleanup_event: _cleanup(ids),
    }
    phase_camera = edits[ids.phase_camera_event]
    if (
        phase_camera.count("SetLockcamSlotNumber(24, 1,") != 2
        or "SetLockcamSlotNumber(36," in phase_camera
    ):
        raise ValueError("Orphan/Gascoigne phase camera binding drift")
    result = _replace_events(
        destination, {event: body for event, body in edits.items() if event in arena}
    )
    result = (
        result.rstrip()
        + "\n\n"
        + "\n\n".join(edits[event] for event in ids.added_events())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena).union(ids.added_events()):
        raise ValueError("Orphan/Gascoigne changed event identities")
    for event, original in arena.items():
        if event not in edits and output[event] != original:
            raise ValueError(f"Orphan/Gascoigne changed unrelated arena event {event}")
    for event in (12411800, 12411801, 12411802):
        if output[event] != arena[event]:
            raise ValueError(
                "Orphan/Gascoigne changed terminal or cutscene progression"
            )
    return result


def _slots(
    slots: Sequence[Slot], entity: int, archetype: Archetype, maps: set[str], role: str
) -> list[Slot]:
    found = sorted(
        [
            slot
            for slot in slots
            if slot.entity_id == entity
            and slot.archetype == archetype
            and slot.map_name in maps
        ],
        key=lambda slot: slot.map_name,
    )
    if len(found) != len(maps) or {slot.map_name for slot in found} != maps:
        raise ValueError(
            f"Orphan/Gascoigne requires one pinned {role} in every map state"
        )
    return found


def _source_slot(
    slots: Sequence[Slot], entity: int, archetype: Archetype, role: str
) -> Slot:
    found = [
        slot
        for slot in slots
        if slot.entity_id == entity
        and slot.archetype == archetype
        and slot.map_name == "m36_00_00_00"
    ]
    if len(found) != 1:
        raise ValueError(f"Orphan/Gascoigne requires one pinned Orphan {role}")
    return found[0]


def _swap(targets: Sequence[Slot], donor: Archetype) -> Swap:
    first = targets[0]
    return Swap(
        first.logical_key,
        [target.key for target in targets],
        {target.key: target.archetype for target in targets},
        first.archetype,
        donor,
        warnings=[
            "experimental Orphan-at-Gascoigne contract; runtime behavior unobserved"
        ],
        destinations={
            target.key: {
                "map_name": target.map_name,
                "entity_id": target.entity_id,
                "x": target.x,
                "y": target.y,
                "z": target.z,
            }
            for target in targets
        },
    )


def _binding(source: Slot, target: Slot) -> dict:
    return {
        "source_map": source.map_name,
        "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "destination_map": target.map_name,
        "destination_part": target.part_name,
        "destination_entity_id": target.entity_id,
        "destination_original_talk_id": target.talk_id,
        "required_native_fields": [
            "talk_id",
            "unk_t18",
            "init_anim_id",
            "damage_anim_id",
            "provenance",
        ],
    }


def native_plan_orphan_at_gascoigne(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: OrphanGascoigneIds = DEFAULT_IDS,
) -> dict:
    """Plan two original primaries and the one source-pinned Orphan support clone."""
    _validate_ids(ids)
    states = set(MAP_STATES)
    core = _source_slot(slots, ORPHAN_CORE, CORE, "core")
    phase = _source_slot(slots, ORPHAN_PHASE, PHASE, "phase")
    support = _source_slot(slots, ORPHAN_SUPPORT, SUPPORT, "support")
    humans = _slots(slots, GASCOIGNE_HUMAN, HUMAN, states, "Gascoigne human")
    beasts = _slots(slots, GASCOIGNE_BEAST, BEAST, states, "Gascoigne beast")
    if any(target.talk_id != 241330 for target in humans) or any(
        target.talk_id != 0 for target in beasts
    ):
        raise ValueError("Orphan/Gascoigne destination talk witnesses drift")
    swaps = [_swap(humans, CORE), _swap(beasts, PHASE)]
    changes, skips = plan_scaling(
        swaps, [*humans, *beasts], dict(npcs), dict(effects), boss_tiers=True
    )
    additions = [
        {
            "source_map": support.map_name,
            "source_part": support.part_name,
            "source_anchor_part": core.part_name,
            "source_entity_id": support.entity_id,
            "source_archetype": asdict(support.archetype),
            "source_talk_id": support.talk_id,
            "destination_map": target.map_name,
            "destination_anchor_part": target.part_name,
            "destination_part": ids.support_part,
            "destination_entity_id": ids.support_entity,
            "allocation_evidence": ids.evidence,
            "required_native_fields": ["source_provenance", "source_initialization"],
        }
        for target in humans
    ]
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": len(swaps),
        "swaps": [swap.json() for swap in swaps],
        "boss_actor_additions": additions,
        "primary_init_source_bindings": [
            *[_binding(core, target) for target in humans],
            *[_binding(phase, target) for target in beasts],
        ],
        "boss_contract": {
            "format": "bb-orphan-gascoigne-contract-v1",
            "arena": "father-gascoigne",
            "donor": "orphan-of-kos",
            "encounter_count": 1,
            "logical_swap_count": 2,
            "physical_swap_count": sum(len(swap.destination_keys) for swap in swaps),
            "attachment_event_ids": asdict(ids),
            "runtime_status": "unobserved",
            "preserved_destination_events": [12411800, 12411801, 12411802],
            "terminal_policy": "preserve original 12411800 OR predicate",
            "helper_scaling_parent": {
                f"{target.map_name}:{ids.support_part}": humans[0].logical_key
                for target in humans
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
