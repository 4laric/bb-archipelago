"""Reusable source-pinned Father Gascoigne combat donor for base arenas.

The donor preserves the original human/beast referred-damage pair, transformation
and music-box reactions.  Receiving arenas retain their own entry, fog, terminal,
co-op and music-reload infrastructure; their model-specific combat controllers are
retired before the imported two-actor graph begins.  Entrance cinematics are not
copied here (the central cinematic policy owns that separate concern).
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
from .boss_contracts import ARENAS, ArenaContract
from .bosses import parse_events
from .gascoigne_contract import (
    BEAST_ARCHETYPE, BEAST_PART, GASCOIGNE_BEAST, GASCOIGNE_HUMAN,
    HUMAN_ARCHETYPE, HUMAN_PART, SOURCE_HASHES,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
GASCOIGNE_EVENT_SOURCE = "event/m24_01_00_00.emevd.dcx.js"
SUPPORTED_GASCOIGNE_ARENAS = ARENAS
CO_OP_RESTORE_EVENTS = {
    "cleric-beast": 12411703,
    "blood-starved-beast": 12301803,
    "darkbeast-paarl": 12301703,
    "vicar-amelia": 12401804,
    "amygdala": 13301803,
    "ebrietas": 12421803,
}

# DarkScript's installed-original form differs only in the untouched terminal
# body (its observed hash is retained as a strict alternative, not normalized).
SOURCE_ALTERNATES = {12411800: ("c6eb236fba9e48406dd9088747c3d54bc054784718a67305da498934c2c98b9c",)}

# Exact original-effective MSB evidence from --boss-actor-pins.  The source
# state is selected explicitly; it is never inferred from a numeric suffix.
HUMAN_PINS = {
    "00": "74f068dbc07cc857e64d6405ad11b4e032fcbb18db192047f6e3d74fe7eccdde",
    "01": "d982e3d23e1d18ad968e9d6a99308922a448f834933b920009e59f221c2bf455",
    "11": "a6a9de184da5e881cec46759af5d49779af99960c9b6d781eacf913f9f3f8e02",
}
BEAST_PINS = {
    "00": "19098d7da3476516f7a30723313e69c6cb21a54e035ea9623ac473bf42ebbb41",
    "01": "8e69e51cc3aa02368933c62bd0ee9c602e711a41f8d7246697019900f46483c5",
    "11": "e497ae7a9554cc8c43b7caf9a4764fc90b3914ffb38ccecdbf191cc650c57ba8",
}
HUMAN_INITIALIZATION = {"talk_id": 241330, "unk_t18": -1,
                        "init_anim_id": -1, "damage_anim_id": -1}
BEAST_INITIALIZATION = {"talk_id": 0, "unk_t18": -1,
                        "init_anim_id": -1, "damage_anim_id": -1}

# Explicitly reviewed destination-state selections.  The data happens to use
# matching labels where they exist, but code must consume this table rather
# than treating a suffix match as a semantic rule.
GASCOIGNE_STATE_BINDINGS = {
    "cleric-beast": (("00", "00"), ("01", "01"), ("11", "11")),
    "blood-starved-beast": (("00", "00"), ("01", "01")),
    "darkbeast-paarl": (("00", "00"), ("01", "01")),
    "vicar-amelia": (("00", "00"), ("01", "01")),
    "amygdala": (("00", "00"),),
    "ebrietas": (("00", "00"), ("01", "01")),
}


@dataclass(frozen=True)
class GascoigneDonorIds:
    beast_entity: int = 983100
    phase_event: int = 12995600
    human_special_event: int = 12995601
    beast_special_event: int = 12995602
    terminal_bridge_event: int = 12995603
    cleanup_event: int = 12995604
    notification_flag: int = 12995605
    readiness_event: int = 12995606
    beast_part: str = "ap_gascoigne_beast"
    evidence: str = ("reserved 12995600-12995699 / 983100-983199; absent from "
                     "original event+mined corpus and reviewed NEXT allocations")

    def event_ids(self) -> tuple[int, ...]:
        return (self.phase_event, self.human_special_event, self.beast_special_event,
                self.terminal_bridge_event, self.cleanup_event, self.readiness_event)

    def numeric_ids(self) -> tuple[int, ...]:
        return (self.beast_entity, self.phase_event, self.human_special_event,
                self.beast_special_event, self.terminal_bridge_event,
                self.cleanup_event, self.notification_flag, self.readiness_event)


DEFAULT_GASCOIGNE_IDS = GascoigneDonorIds()


def _verify(text: str, pins: Mapping[int, str], role: str) -> dict[int, str]:
    blocks = event_blocks(text)
    for event, expected in pins.items():
        actual = blocks.get(event)
        allowed = {expected, *SOURCE_ALTERNATES.get(event, ())} if role == "Gascoigne donor" else {expected}
        if actual is None or hashlib.sha256(actual.encode()).hexdigest() not in allowed:
            raise ValueError(f"{role} event {event} drifted from its reviewed source")
    return blocks


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gascoigne donor expected one {label}")
    return text.replace(old, new)


def _remap(text: str, values: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])(-?\d+)(?![\w])",
                  lambda match: str(values.get(int(match.group(1)), int(match.group(1)))), text)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _noop(block: str) -> str:
    head, separator, _ = block.partition("{\n")
    if not separator:
        raise ValueError("Gascoigne donor cannot retire malformed destination event")
    # DarkScript requires unused named event parameters to identify themselves.
    # Keeping the signature preserves Event(0)'s ABI while making retirement a
    # real no-op for both Default and Restart routines.
    def unused(match: re.Match[str]) -> str:
        names = [name.strip() for name in match.group(1).split(",") if name.strip()]
        return "function(" + ", ".join(
            name if name.startswith("unused") else "unused_" + name for name in names
        ) + ")"
    head, count = re.subn(r"function\(([^)]*)\)", unused, head, count=1)
    if count != 1:
        raise ValueError("Gascoigne donor cannot retain destination event signature")
    return head + "{\n    EndEvent();\n});"


@cache
def _original_ids() -> set[int]:
    ids: set[int] = set()
    for prefix in ("event/", "mined/"):
        for body in read_prefix(BUNDLE, prefix).values():
            ids.update(int(value) for value in re.findall(rb"(?<![\w])-?\d+(?![\w])", body))
    return ids


def _validate_ids(ids: GascoigneDonorIds, destination: str = "") -> None:
    project = ids.numeric_ids()
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if (len(project) != len(set(project))
            or not all(12995600 <= event <= 12995699 for event in ids.event_ids())
            or not 12995600 <= ids.notification_flag <= 12995699
            or not 983100 <= ids.beast_entity <= 983199
            or set(project) & (_original_ids() | local)
            or not ids.beast_part.strip() or not ids.evidence.strip()):
        raise ValueError("Gascoigne donor IDs require reserved, collision-free authored evidence")


def _state(map_name: str) -> str:
    match = re.fullmatch(r"m24_01_00_(00|01|11)", map_name.removesuffix(".msb"))
    if match is None:
        raise ValueError(f"unsupported Gascoigne source map state {map_name}")
    return match.group(1)


def _require(slots: Sequence[Slot], entity: int, archetype: Archetype,
             map_name: str | None = None) -> list[Slot]:
    rows = sorted((slot for slot in slots if slot.entity_id == entity
                   and (map_name is None or slot.map_name.removesuffix(".msb") == map_name)),
                  key=lambda slot: slot.key)
    if not rows or any(slot.dummy or slot.archetype != archetype for slot in rows):
        raise ValueError(f"Gascoigne donor lacks exact actor provenance for {entity}")
    return rows


def _notification_flag(arena: ArenaContract, ids: GascoigneDonorIds) -> int:
    return 12404223 if arena.key == "vicar-amelia" else ids.notification_flag


def _mapping(arena: ArenaContract, ids: GascoigneDonorIds) -> dict[int, int]:
    return {
        GASCOIGNE_HUMAN: arena.actor, GASCOIGNE_BEAST: ids.beast_entity,
        12411800: arena.completion_event, 12414800: ids.readiness_event,
        12414802: arena.health_bar_event, 12414804: arena.lockcam_event,
        12414807: ids.phase_event, 12414808: ids.human_special_event,
        12414809: ids.beast_special_event, 12414223: _notification_flag(arena, ids),
    }


def _destination_telemetry(source: str, destination: str) -> str:
    result = source
    for instruction in ("CreatePlaylog", "StartTimeMeasurement"):
        old = [line for line in source.splitlines() if line.strip().startswith(instruction + "(")]
        new = [line for line in destination.splitlines() if line.strip().startswith(instruction + "(")]
        if len(old) != 1 or len(new) != 1:
            raise ValueError(f"Gascoigne health lacks unique {instruction} telemetry witness")
        result = _replace_once(result, old[0], new[0], f"destination {instruction}")
    return result


def _retired(arena: ArenaContract) -> set[int]:
    retired = {event for event in (*arena.phase_slots, arena.part_routine_event,
                                arena.cloth_routine_event, arena.attachment_anchor_event,
                                *arena.retired_combat_events) if event is not None}
    # ArenaContract's historical Cleric field names its cloth routine.  The
    # real co-op restoration is 12411703; use the source-reviewed map instead
    # of preserving the c5000-only 12414708 controller.
    retired.discard(CO_OP_RESTORE_EVENTS[arena.key])
    return retired


def _adapt_activation(arena: ArenaContract, body: str) -> str:
    # Destination fog/start and its pre-entry protection remain source-backed
    # arena behavior.  The destination model animation is the only nonportable
    # choreography; Gascoigne's transition has no standalone equivalent here.
    pattern = re.compile(rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", re.MULTILINE)
    result, count = pattern.subn("", body)
    if count == 0:
        raise ValueError(f"{arena.key} activation lacks a reviewed model animation")
    return result


def _adapt_music(arena: ArenaContract, body: str, ids: GascoigneDonorIds) -> str:
    if arena.phase_music_event_flag is not None:
        witness = f"EventFlag({arena.phase_music_event_flag})"
    elif arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        raise ValueError(f"{arena.key} lacks a phase-music witness")
    return _replace_once(body, witness, f"EventFlag({ids.phase_event})", "destination phase music")


def _initializer(donor_zero: str, source_event: int, destination_event: int) -> str:
    rows = [line for line in donor_zero.splitlines()
            if re.match(rf"\s*\$InitializeEvent\([^,]+,\s*{source_event}(?:,|\))", line)]
    if len(rows) != 1:
        raise ValueError(f"Gascoigne source constructor lacks initializer {source_event}")
    return _remap(rows[0], {source_event: destination_event})


def _constructor(arena: ArenaContract, destination_zero: str, donor_zero: str,
                 ids: GascoigneDonorIds) -> str:
    retired = _retired(arena)
    retained = [line for line in destination_zero.splitlines()
                if not any(re.match(rf"\s*\$InitializeEvent\([^,]+,\s*{event}(?:,|\))", line)
                               for event in retired)]
    text = "\n".join(retained)
    calls = [_initializer(donor_zero, source, target) for source, target in (
        (12414807, ids.phase_event), (12414808, ids.human_special_event),
        (12414809, ids.beast_special_event))]
    calls.extend((f"    $InitializeEvent(0, {ids.terminal_bridge_event});",
                  f"    $InitializeEvent(0, {ids.cleanup_event});",
                  f"    $InitializeEvent(0, {ids.readiness_event});"))
    anchor = f"    $InitializeEvent(0, {arena.activation_event});"
    text = _replace_once(text, anchor, anchor + "\n" + "\n".join(calls),
                         "destination activation initializer")
    header = text.splitlines()[0] + "\n"
    return _replace_once(text, header,
                         header + f"    SetEventFlag({ids.readiness_event}, OFF);\n",
                         "destination constructor header")


def _readiness(arena: ArenaContract, ids: GascoigneDonorIds) -> str:
    restore = {
        "cleric-beast": (
            f"    ChangeCharacterEnableState({arena.actor}, Enabled);",
            f"    SetCharacterGravity({arena.actor}, Enabled);",
            f"    SetCharacterMaphits({arena.actor}, false);",
        ),
        "blood-starved-beast": (),
        "darkbeast-paarl": (
            f"    SetCharacterInvincibility({arena.actor}, Disabled);",
        ),
        "vicar-amelia": (
            f"    ChangeCharacterEnableState({arena.actor}, Enabled);",
        ),
        "amygdala": (
            f"    SetCharacterGravity({arena.actor}, Enabled);",
            f"    SetCharacterInvincibility({arena.actor}, Disabled);",
            f"    SetCharacterMaphits({arena.actor}, false);",
        ),
        "ebrietas": (
            f"    SetCharacterImmortality({arena.actor}, Disabled);",
        ),
    }[arena.key]
    return "\n".join((
        f"$Event({ids.readiness_event}, Default, function() {{",
        f"    EndIf(EventFlag({arena.completion_event}));",
        f"    WaitFor(EventFlag({arena.start_flag}));",
        *restore,
        "});",
    ))


def gascoigne_donor_contract(arena: ArenaContract,
                              ids: GascoigneDonorIds = DEFAULT_GASCOIGNE_IDS) -> dict:
    _validate_ids(ids)
    return {
        "format": "bb-gascoigne-donor-contract-v1", "status": "experimental",
        "arena": arena.key, "donor": "father-gascoigne", "allocation": asdict(ids),
        "source_hash_pins": dict(SOURCE_HASHES),
        "source_hash_alternates": {str(event): list(values)
                                   for event, values in SOURCE_ALTERNATES.items()},
        "source_actor_pins": {"human": dict(HUMAN_PINS), "beast": dict(BEAST_PINS)},
        "preserved_destination_events": [arena.completion_event,
                                          CO_OP_RESTORE_EVENTS[arena.key]],
        "adapted_destination_events": [arena.activation_event, arena.health_bar_event,
                                         arena.music_event, arena.lockcam_event],
        "retired_destination_controllers": sorted(_retired(arena)),
        "terminal_policy": "destination terminal remains byte-identical; beast death bridges to primary",
        "runtime_status": "unobserved",
    }


def patch_gascoigne_donor(arena: ArenaContract, destination: str, donor_source: str,
                           ids: GascoigneDonorIds = DEFAULT_GASCOIGNE_IDS) -> str:
    original = _verify(destination, arena.expected, f"{arena.key} arena")
    donor = _verify(donor_source, SOURCE_HASHES, "Gascoigne donor")
    _validate_ids(ids, destination)
    mapping = _mapping(arena, ids)
    health = _destination_telemetry(_remap(donor[12414802], mapping),
                                    original[arena.health_bar_event])
    health = _replace_once(
        health,
        f"L0:\n    SetEventFlag({_notification_flag(arena, ids)}, ON);",
        f"L0:\n    WaitFor(EventFlag({ids.readiness_event}));\n"
        f"    SetEventFlag({_notification_flag(arena, ids)}, ON);",
        "saved-health readiness gate",
    )
    camera = _remap(donor[12414804], mapping)
    source_camera = "SetLockcamSlotNumber(24, 1,"
    target_camera = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if camera.count(source_camera) != 4:
        raise ValueError("Gascoigne camera lacks all four human/beast source bindings")
    camera = camera.replace(source_camera, target_camera)
    imports: dict[int, str] = {}
    for source, target in ((12414807, ids.phase_event), (12414808, ids.human_special_event),
                           (12414809, ids.beast_special_event)):
        block = _remap(donor[source], mapping)
        if source == 12414807:
            block = _replace_once(block,
                "    EndIf(EventFlag(9337));\n    $InitializeEvent(0, 9350, 1);\n    SetEventFlag(9337, ON);\n",
                "", "Gascoigne progression tail")
            block = _replace_once(block,
                f"    SetCharacterGravity({ids.beast_entity}, Enabled);\n",
                f"    ChangeCharacterEnableState({ids.beast_entity}, Enabled);\n"
                f"    SetCharacterInvincibility({ids.beast_entity}, Disabled);\n"
                f"    SetCharacterGravity({ids.beast_entity}, Enabled);\n", "beast materialization")
        imports[target] = block
    bridge = f'''$Event({ids.terminal_bridge_event}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    humanDead = CharacterDead({arena.actor});
    beastDead = CharacterDead({ids.beast_entity});
    WaitFor(humanDead || beastDead);
    ForceCharacterDeath({arena.actor}, false);
}});'''
    cleanup = f'''$Event({ids.cleanup_event}, Default, function() {{
    GotoIf(L0, EventFlag({arena.completion_event}));
    if (EventFlag({ids.phase_event})) {{
        ChangeCharacterEnableState({ids.beast_entity}, Enabled);
        SetCharacterInvincibility({ids.beast_entity}, Disabled);
        SetCharacterGravity({ids.beast_entity}, Enabled);
        EndEvent();
    }}
    ChangeCharacterEnableState({ids.beast_entity}, Disabled);
    SetCharacterAIState({ids.beast_entity}, Disabled);
    SetCharacterHPBarDisplay({ids.beast_entity}, Disabled);
    SetCharacterInvincibility({ids.beast_entity}, Enabled);
    WaitFor(EventFlag({arena.completion_event}));
L0:
    SetCharacterInvincibility({ids.beast_entity}, Disabled);
    ForceCharacterDeath({ids.beast_entity}, false);
}});'''
    readiness = _readiness(arena, ids)
    edits = {event: _noop(original[event]) for event in _retired(arena)}
    edits.update({
        0: _constructor(arena, original[0], donor[0], ids),
        arena.activation_event: _adapt_activation(arena, original[arena.activation_event]),
        arena.health_bar_event: health,
        arena.music_event: _adapt_music(arena, original[arena.music_event], ids),
        arena.lockcam_event: camera,
    })
    result = (_replace_events(destination, edits).rstrip() + "\n\n"
              + "\n\n".join((*imports.values(), bridge, cleanup, readiness)) + "\n")
    output = event_blocks(result)
    if set(output) != set(original) | set(ids.event_ids()):
        raise ValueError("Gascoigne donor changed unexpected event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"Gascoigne donor changed unrelated {arena.key} event {event}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Gascoigne donor changed destination terminal/progression")
    co_op = CO_OP_RESTORE_EVENTS[arena.key]
    if output[co_op] != original[co_op]:
        raise ValueError("Gascoigne donor changed destination co-op entry")
    copied = "\n".join(output[event] for event in (
        arena.health_bar_event, arena.lockcam_event, *ids.event_ids()))
    if re.search(r"(?<!\d)(?:124148|241081|9337|9350)(?!\d)", copied):
        raise ValueError("Gascoigne donor retains source progression or map literals")
    return result


def _pin(part_sha256: str, initialization: Mapping[str, int], anchor_sha256: str | None = None) -> dict:
    provenance = {"format": "bb-boss-actor-pin-v1", "part_sha256": part_sha256}
    if anchor_sha256 is not None:
        provenance["anchor_sha256"] = anchor_sha256
    return {"source_provenance": provenance, "source_initialization": dict(initialization)}


def native_plan_gascoigne_donor(arena: ArenaContract, slots: Sequence[Slot],
                                 npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
                                 ids: GascoigneDonorIds = DEFAULT_GASCOIGNE_IDS) -> dict:
    _verify(read_blob(BUNDLE, GASCOIGNE_EVENT_SOURCE).decode("utf-8-sig"), SOURCE_HASHES,
            "Gascoigne donor")
    _validate_ids(ids)
    targets = _require(slots, arena.actor, arena.archetype)
    humans = _require(slots, GASCOIGNE_HUMAN, HUMAN_ARCHETYPE)
    beasts = _require(slots, GASCOIGNE_BEAST, BEAST_ARCHETYPE)
    by_state = {_state(slot.map_name): slot for slot in humans}
    beast_by_state = {_state(slot.map_name): slot for slot in beasts}
    if (len(targets) != arena.destination_count or set(by_state) != set(HUMAN_PINS)
            or set(beast_by_state) != set(BEAST_PINS)):
        raise ValueError(f"Gascoigne/{arena.key} lacks exact source or destination state evidence")
    swap = Swap(targets[0].logical_key, [slot.key for slot in targets],
                {slot.key: slot.archetype for slot in targets}, arena.archetype, HUMAN_ARCHETYPE,
                destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                          "x": slot.x, "y": slot.y, "z": slot.z} for slot in targets})
    changes, skips = plan_scaling([swap], targets, dict(npcs), dict(effects), boss_tiers=True)
    additions, primary, scaling = [], [], []
    for target in targets:
        # Base state bindings are authored on the arena contract.  This accepts
        # canonical source state 00 for a destination 11 only when the arena
        # explicitly declares that correspondence.
        target_state = target.map_name.removesuffix(".msb").rsplit("_", 1)[-1]
        bindings = dict(GASCOIGNE_STATE_BINDINGS[arena.key])
        source_state = bindings.get(target_state)
        if source_state not in by_state or source_state not in beast_by_state:
            raise ValueError(f"{arena.key} lacks an authored Gascoigne source-state binding")
        human, beast = by_state[source_state], beast_by_state[source_state]
        if human.talk_id != 241330 or beast.talk_id != 0:
            raise ValueError("Gascoigne source initialization drift")
        addition = {"source_map": beast.map_name, "source_part": BEAST_PART,
                    "source_anchor_part": HUMAN_PART, "source_entity_id": GASCOIGNE_BEAST,
                    "source_archetype": asdict(BEAST_ARCHETYPE), "source_part_kind": "enemy",
                    "destination_map": target.map_name, "destination_anchor_part": target.part_name,
                    "destination_part": ids.beast_part, "destination_entity_id": ids.beast_entity,
                    "allocation_evidence": ids.evidence}
        addition.update(_pin(BEAST_PINS[source_state], BEAST_INITIALIZATION, HUMAN_PINS[source_state]))
        additions.append(addition)
        binding = {"source_map": human.map_name, "source_part": HUMAN_PART,
                   "source_entity_id": GASCOIGNE_HUMAN, "source_archetype": asdict(HUMAN_ARCHETYPE),
                   "source_talk_id": human.talk_id, "destination_map": target.map_name,
                   "destination_part": target.part_name, "destination_entity_id": target.entity_id,
                   "destination_original_talk_id": target.talk_id,
                   "destination_talk_id_override": 0,
                   "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id",
                                              "provenance", "destination_talk_id_override"]}
        binding.update(_pin(HUMAN_PINS[source_state], HUMAN_INITIALIZATION))
        primary.append(binding)
        scaling.append({"destination_map": target.map_name, "destination_part": ids.beast_part,
                        "parent_logical_key": swap.logical_key,
                        "source_npc_param_id": BEAST_ARCHETYPE.npc_param_id,
                        "strategy": "allocate_distinct_verified_helper_clone"})
    return {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
            "swap_count": 1, "swaps": [swap.json()], "boss_contract": gascoigne_donor_contract(arena, ids),
            "boss_actor_additions": additions, "primary_init_source_bindings": primary,
            "boss_actor_scaling_requirements": scaling,
            "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                        "change_count": len(changes), "changes": [change.json() for change in changes],
                        "skip_count": len(skips), "skips": skips}}


def helper_scaling_parents(plan: Mapping) -> dict[tuple[str, str], str]:
    rows = plan.get("boss_actor_scaling_requirements", ())
    result = {(row["destination_map"], row["destination_part"]): row["parent_logical_key"] for row in rows}
    if len(result) != len(rows):
        raise ValueError("duplicate Gascoigne helper scaling destination")
    return result
