"""Evidence-pinned Darkbeast Paarl combat in Wet Nurse's destination arena.

Wet Nurse's entry cutscene, co-op ingress, music bank, completion and rewards
remain destination-owned.  The byte-identical terminal still observes its
offstage proxy; a bridge releases it only after the transplanted Paarl dies.
Runtime arena behavior remains unobserved.
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
from .bsb_wet_nurse_contract import (
    ARENA_HASHES,
    WET_NURSE_PART_PINS,
)
from .model import Archetype, Slot, Swap
from .paarl_logarius_contract import DONOR_HASHES, PAARL_SOURCE_PINS, NativePartPin
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
PAARL_SOURCE = "event/m23_00_00_00.emevd.dcx.js"
WET_NURSE_SOURCE = "event/m26_00_00_00.emevd.dcx.js"

PAARL = 2300810
WET_NURSE_CORE = 2600800
WET_NURSE_SUPPORT = 2600801
WET_NURSE_PROXY = 2600802
PAARL_ARCHETYPE = Archetype("c5080", 508000, 508000, 0)
WET_NURSE_ARCHETYPE = Archetype("c5510", 551000, 551000, 0)

PROJECT_EVENT_MIN = 12993900
PROJECT_EVENT_MAX = 12993999


@dataclass(frozen=True)
class PaarlWetNurseIds:
    phase: int = 12993900
    limb: int = 12993901
    death_to_proxy: int = 12993902
    helper_cleanup: int = 12993903

    def values(self) -> tuple[int, int, int, int]:
        return self.phase, self.limb, self.death_to_proxy, self.helper_cleanup


DEFAULT_IDS = PaarlWetNurseIds()


def _verify(text: str, hashes: Mapping[int, str], label: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event_id, digest in hashes.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event_id}")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Paarl/Wet Nurse expected one {label}")
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


@cache
def _all_original_literals() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(
            int(value)
            for value in re.findall(r"(?<![\w])-?\d+(?![\w])", body.decode("utf-8-sig"))
        )
    return values


def _validate_ids(ids: PaarlWetNurseIds, destination: str) -> None:
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
            "Paarl/Wet Nurse IDs must be collision-free project-owned 129939xx values"
        )


def _initializer_rows(
    event_zero: str, source_event: int, destination_event: int, expected: int
) -> list[str]:
    calls = [
        line
        for line in event_zero.splitlines()
        if re.match(
            r"\s*\$InitializeEvent\([^,]+,\s*" + str(source_event) + r"(?:,|\))",
            line,
        )
    ]
    if len(calls) != expected:
        raise ValueError(
            f"Paarl Event(0) requires {expected} initializer witness(es) for {source_event}"
        )
    return [
        re.sub(
            r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
            r"\g<1>" + str(destination_event),
            call,
            count=1,
        )
        for call in calls
    ]


def _mapping(ids: PaarlWetNurseIds) -> dict[int, int]:
    return {
        PAARL: WET_NURSE_CORE,
        12301700: 12601800,
        12304700: 12604800,
        12304701: 12604801,
        12304702: 12604802,
        12304704: 12604804,
        12304707: ids.phase,
        12304715: ids.limb,
        2300010: 2600010,
        23: 26,
    }


def patch_paarl_at_wet_nurse(
    destination: str,
    donor_source: str,
    ids: PaarlWetNurseIds = DEFAULT_IDS,
) -> str:
    """Install Paarl combat while retaining Wet Nurse's native terminal."""
    arena = _verify(destination, ARENA_HASHES, "Wet Nurse arena")
    donor = _verify(donor_source, DONOR_HASHES, "Paarl donor")
    _validate_ids(ids, destination)
    if set(ids.values()).intersection(arena):
        raise ValueError("Paarl/Wet Nurse added event ID collides with destination")
    remap = _mapping(ids)

    health = _remap(donor[12304702], remap)
    health = _replace_once(
        health,
        "    SetCharacterHPBarDisplay(2600800, Disabled);",
        "    SetCharacterHPBarDisplay(2600800, Disabled);\n"
        "    SetCharacterAIState(2600801, Disabled);\n"
        "    ChangeCharacterEnableState(2600801, Disabled);\n"
        "    SetCharacterHPBarDisplay(2600801, Disabled);\n"
        "    SetCharacterAIState(2600802, Disabled);\n"
        "    ChangeCharacterEnableState(2600802, Disabled);\n"
        "    SetCharacterHPBarDisplay(2600802, Disabled);\n"
        "    SetCharacterGravity(2600802, Disabled);\n"
        "    SetCharacterInvincibility(2600802, Enabled);",
        "retained support and proxy initialization",
    )
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
        "destination notification guard",
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

    activation = _replace_once(
        arena[12601802],
        "    ChangeCharacterEnableState(2600800, Disabled);",
        "    ChangeCharacterEnableState(2600800, Disabled);\n"
        "    SetCharacterInvincibility(2600800, Enabled);\n"
        "    ForceAnimationPlayback(2600800, 7000, true, false, false);",
        "Paarl pre-entry state",
    )
    activation = _replace_once(
        activation,
        "    SetObjectInvulnerability(2601856, Disabled);\n"
        "    ReproduceObjectDestruction(2601856, 1);\n"
        "    SetEventFlag(12604800, ON);",
        "    SetObjectInvulnerability(2601856, Disabled);\n"
        "    ReproduceObjectDestruction(2601856, 1);\n"
        "    ForceAnimationPlayback(2600800, 7001, false, false, false);\n"
        "    WaitFixedTimeFrames(70);\n"
        "    SetCharacterInvincibility(2600800, Disabled);\n"
        "    SetEventFlag(12604800, ON);",
        "Paarl wake-up sequence",
    )

    # Wet Nurse's BGM and map bank remain authoritative.  Only its phase
    # predicate follows the active transplanted actor instead of the inert
    # terminal proxy.
    music = _replace_once(
        arena[12604803],
        "        WaitFor(HPRatio(2600802) < 0.7);",
        "        WaitFor(HPRatio(2600800) < 0.7);",
        "destination music phase predicate",
    )
    camera = _remap(donor[12304704], remap)
    phase = _remap(donor[12304707], remap)
    limb = _remap(donor[12304715], remap)

    constructor_rows = [
        *_initializer_rows(donor[0], 12304707, ids.phase, 1),
        *_initializer_rows(donor[0], 12304715, ids.limb, 5),
        f"    $InitializeEvent(0, {ids.death_to_proxy});",
        f"    $InitializeEvent(0, {ids.helper_cleanup});",
    ]
    constructor = _replace_once(
        arena[0],
        "    $InitializeEvent(0, 12604840);",
        "    $InitializeEvent(0, 12604840);\n" + "\n".join(constructor_rows),
        "project controller anchor",
    )
    bridge = f"""$Event({ids.death_to_proxy}, Default, function() {{
    EndIf(EventFlag(12601800));
    WaitFor(CharacterDead(2600800));
    EndIf(EventFlag(12601800));
    SetCharacterInvincibility(2600802, Disabled);
    ForceCharacterDeath(2600802, false);
}});"""
    cleanup = f"""$Event({ids.helper_cleanup}, Default, function() {{
    SetCharacterAIState(2600801, Disabled);
    SetCharacterHPBarDisplay(2600801, Disabled);
    ChangeCharacterEnableState(2600801, Disabled);
    SetCharacterAIState(2600802, Disabled);
    SetCharacterHPBarDisplay(2600802, Disabled);
    SetCharacterGravity(2600802, Disabled);
    SetCharacterInvincibility(2600802, Enabled);
    ChangeCharacterEnableState(2600802, Disabled);
    WaitFor(EventFlag(12601800));
    SetCharacterInvincibility(2600802, Disabled);
}});"""
    edits = {
        0: constructor,
        12601802: activation,
        12604802: health,
        12604803: music,
        12604804: camera,
        12604806: _end_event(arena[12604806]),
        12604810: _end_event(arena[12604810]),
        12604815: _end_event(arena[12604815]),
        12604820: _end_event(arena[12604820]),
        12604830: _end_event(arena[12604830]),
        12604840: _end_event(arena[12604840]),
    }
    added = {
        ids.phase: phase,
        ids.limb: limb,
        ids.death_to_proxy: bridge,
        ids.helper_cleanup: cleanup,
    }
    result = (
        _replace_events(destination, edits).rstrip()
        + "\n\n"
        + "\n\n".join(added[event] for event in ids.values())
        + "\n"
    )
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.values()):
        raise ValueError("Paarl/Wet Nurse changed event identities")
    for event_id, body in arena.items():
        if event_id not in edits and output[event_id] != body:
            raise ValueError(f"Paarl/Wet Nurse changed unrelated event {event_id}")
    if output[12601800] != arena[12601800]:
        raise ValueError("Paarl/Wet Nurse changed protected destination terminal")
    for event_id in (12601801, 12601803, 12604805):
        if output[event_id] != arena[event_id]:
            raise ValueError(
                "Paarl/Wet Nurse changed destination death sound, co-op or cleanup"
            )
    for event_id in (12604806, 12604810, 12604815, 12604820, 12604830, 12604840):
        if output[event_id].splitlines()[1] != "    EndEvent();":
            raise ValueError("Paarl/Wet Nurse retained a Wet Nurse combat helper")
    constructor_output = output[0]
    expected_counts = {
        ids.phase: 1,
        ids.limb: 5,
        ids.death_to_proxy: 1,
        ids.helper_cleanup: 1,
    }
    for event_id, expected in expected_counts.items():
        actual = len(
            re.findall(
                r"\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))",
                constructor_output,
            )
        )
        if actual != expected:
            raise ValueError(
                f"Paarl/Wet Nurse controller {event_id} initializer count drift"
            )
    copied = "\n".join(
        output[event_id] for event_id in (12604802, 12604804, ids.phase, ids.limb)
    )
    if re.search(r"(?<!\d)(?:123\d{5}|230\d{4})(?!\d)", copied):
        raise ValueError("Paarl/Wet Nurse retained a donor-map literal")
    if "CreateReferredDamagePair" in output[12604802]:
        raise ValueError("Paarl/Wet Nurse retained proxy health sharing")
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
        raise ValueError(
            f"unsupported Paarl/Wet Nurse placement provenance for {entity}"
        )
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


def native_plan_paarl_at_wet_nurse(
    slots: Sequence[Slot],
    npcs: Mapping[int, dict],
    effects: Mapping[int, dict],
    seed: str,
    ids: PaarlWetNurseIds = DEFAULT_IDS,
) -> dict:
    bundled_arena = read_blob(BUNDLE, WET_NURSE_SOURCE).decode("utf-8-sig")
    bundled_donor = read_blob(BUNDLE, PAARL_SOURCE).decode("utf-8-sig")
    patch_paarl_at_wet_nurse(bundled_arena, bundled_donor, ids)
    sources = _require(slots, PAARL, PAARL_ARCHETYPE)
    core = _require(slots, WET_NURSE_CORE, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    support = _require(slots, WET_NURSE_SUPPORT, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    proxy = _require(slots, WET_NURSE_PROXY, WET_NURSE_ARCHETYPE, "m26_00_00_00")
    if (
        len(sources) != 2
        or {slot.map_name for slot in sources} != set(PAARL_SOURCE_PINS)
        or len(core) != 1
        or len(support) != 1
        or len(proxy) != 1
    ):
        raise ValueError(
            "Paarl/Wet Nurse requires two exact Paarl states and three native destination actors"
        )
    source = next(slot for slot in sources if slot.map_name == "m23_00_00_00")
    target = core[0]
    swap = Swap(
        target.logical_key,
        [target.key],
        {target.key: target.archetype},
        target.archetype,
        PAARL_ARCHETYPE,
        warnings=[
            "experimental Paarl-at-Wet-Nurse contract; runtime terminal bridge behavior is unobserved"
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
        raise ValueError("Paarl/Wet Nurse primary normalization is ambiguous")
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
                    "retain_native_phase_clone_hidden_until_destination_completion"
                    if slot.entity_id == WET_NURSE_SUPPORT
                    else "retain_native_proxy_hidden_invincible_until_paarl_death_bridge"
                ),
            }
        )
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": "mergos-wet-nurse<-darkbeast-paarl"},
        "primary_init_source_bindings": [
            _native_binding(source, target, PAARL_SOURCE_PINS[source.map_name])
        ],
        "boss_contract": {
            "format": "bb-paarl-wet-nurse-contract-v1",
            "arena": "mergos-wet-nurse",
            "donor": "darkbeast-paarl",
            "status": "planned",
            "writer_status": "not_integrated",
            "runtime_status": "unobserved",
            "event_ids": asdict(ids),
            "preserved_destination_events": [
                12601800,
                12601801,
                12601803,
                12604805,
            ],
            "destination_owned_controllers": {
                "entry": 12601802,
                "coop": 12601803,
                "music": 12604803,
                "music_cleanup": 12604805,
            },
            "retired_wet_nurse_helpers": [
                12604806,
                12604810,
                12604815,
                12604820,
                12604830,
                12604840,
            ],
            "retained_destination_helpers": retained,
            "terminal_policy": "byte-identical 12601800 observes proxy2600802; proxy is released only after CharacterDead2600800",
            "source_actor_event_closure": {
                "12301702": "invincibility and 7000-to-7001 wake sequence woven into destination entry",
                "12301703": "superseded by preserved destination co-op ingress",
                "12304702": "Paarl health, co-op scaling and health bar copied",
                "12304703": "superseded by destination music and sound bank; phase predicate follows active Paarl",
                "12304704": "Paarl proximity camera copied onto map26 lockcam",
                "12304707": "Paarl phase controller copied",
                "12304715": "all five Paarl limb slots copied",
            },
            "source_state_pins": {
                name: {
                    "part_sha256": pin.part_sha256,
                    "source_initialization": {
                        "talk_id": pin.talk_id,
                        "unk_t18": pin.unk_t18,
                        "init_anim_id": pin.init_anim_id,
                        "damage_anim_id": pin.damage_anim_id,
                    },
                }
                for name, pin in PAARL_SOURCE_PINS.items()
            },
            "arena_hash_pins": dict(ARENA_HASHES),
            "donor_hash_pins": dict(DONOR_HASHES),
            "helper_entity_reservation": "981700-981799 reserved; no added actor is required by this single-body donor",
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
