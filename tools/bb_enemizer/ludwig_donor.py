"""Reusable, source-pinned normal Ludwig combat for the base arenas.

This preserves Ludwig's two-form combat graph while leaving each arena's
terminal, rewards, fog, co-op entry, sounds, and telemetry in charge.  The
source phase cutscene and m34 placement regions are replaced by an actor-to-
actor floor copy.  Runtime arena geometry remains unobserved.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_prefix

from .boss_canary import event_blocks, parse_events
from .boss_contracts import (
    AMELIA_ARENA, AMYGDALA_ARENA, BSB_ARENA, CLERIC_ARENA,
    EBRIETAS_ARENA, PAARL_ARENA, ArenaContract,
)
from .ludwig_contract import EVENTS, P1, P2, SOURCE_HASHES
from .model import Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m34_00_00_00.emevd.dcx.js"
PHASE_ONE, PHASE_TWO = 3400800, 3400801
ARENAS = (CLERIC_ARENA, BSB_ARENA, PAARL_ARENA, AMELIA_ARENA,
          AMYGDALA_ARENA, EBRIETAS_ARENA)
CO_OP_RESTORE_EVENTS = {
    "cleric-beast": 12411703,
    "blood-starved-beast": 12301803,
    "darkbeast-paarl": 12301703,
    "vicar-amelia": 12401804,
    "amygdala": 13301803,
    "ebrietas": 12421803,
}
SOURCE_ALTERNATES = {
    13404802: "02a77d3081f5fa336ec6db647099ef975dd7bca6f38da26b9d6176564ff814ab",
}
PART_PINS = {
    PHASE_ONE: "79c5c55b1660c9ca6d517e25fe5ab685bb7b6ec8e53bad5406b3433bf9c798a8",
    PHASE_TWO: "6ff68750b7bed265be44daed1a4d6522a1d4fb0563519693d2cde4035d04c296",
}
SOURCE_PARTS = {PHASE_ONE: "c4510_0000", PHASE_TWO: "c4510_0002"}
SOURCE_INITIALIZATION = {
    "talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1,
}
SOURCE_EVENT_SHA256 = "630e354e45a85665651e15e4a50d79fc1462d925e2dbdb07d02ceccff20ff1bb"
SOURCE_FFX_FILE = "frpg_sfxbnd_m34.ffxbnd.dcx"
SOURCE_FFX_SHA256 = "c02322d8ad0e50b18e5f678f3bbfe735971e24aa4c5484f3849ace93f1dfd3b3"
LUDWIG_EFFECT = 645114
# Event 13404840 emits the same source-pinned effect sixteen times.  This is
# a visual cadence in the normal phase transition, so the native FFX contract
# must bind the complete witnessed sequence rather than collapse it to one.
LUDWIG_EFFECT_OCCURRENCE_COUNT = 16
DESTINATION_FFX = {
    "cleric-beast": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
    "blood-starved-beast": ("frpg_sfxbnd_m23.ffxbnd.dcx", "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec"),
    "darkbeast-paarl": ("frpg_sfxbnd_m23.ffxbnd.dcx", "b92037c5ae58ac81e5e59f7b9596966faf65ea56bf1b9ea9913045097213cfec"),
    "vicar-amelia": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
    "amygdala": ("frpg_sfxbnd_m33.ffxbnd.dcx", "850e8354601f85e59166aaeceb0dea48018fd21afbad005f78b7732fc3889a29"),
    "ebrietas": ("frpg_sfxbnd_m24.ffxbnd.dcx", "56103cdfe6b3f9298a32fc515be67c6117f555ae69cb87a8cbbb8bcba2abac99"),
}


@dataclass(frozen=True)
class LudwigDonorAllocation:
    phase_20: int = 12995800
    phase_21: int = 12995801
    phase_22: int = 12995802
    phase_23: int = 12995803
    phase_24: int = 12995804
    phase_25: int = 12995805
    limb_event: int = 12995806
    phase_two_low_health: int = 12995807
    player_warp_event: int = 12995808
    phase_two_reset: int = 12995809
    readiness_event: int = 12995810
    terminal_bridge_event: int = 12995811
    notification_flag: int = 12995812
    phase_entity: int = 983300

    def event_ids(self) -> dict[int, int]:
        return dict(zip(EVENTS, self.values()[:10]))

    def values(self) -> tuple[int, ...]:
        return (self.phase_20, self.phase_21, self.phase_22, self.phase_23,
                self.phase_24, self.phase_25, self.limb_event,
                self.phase_two_low_health, self.player_warp_event,
                self.phase_two_reset, self.readiness_event,
                self.terminal_bridge_event, self.notification_flag,
                self.phase_entity)


DEFAULT_ALLOCATION = LudwigDonorAllocation()


def _literals(text: str) -> set[int]:
    return {int(x) for x in re.findall(r"(?<![\w])-?\d+(?![\w])", text)}


@cache
def _original_literals() -> frozenset[int]:
    values: set[int] = set()
    for prefix in ("event/", "mined/"):
        for blob in read_prefix(BUNDLE, prefix).values():
            values.update(_literals(blob.decode("utf-8-sig")))
    return frozenset(values)


def _validate(allocation: LudwigDonorAllocation, destination: str = "") -> None:
    values = allocation.values()
    if (len(values) != len(set(values)) or any(value <= 0 for value in values)
            or set(values) & (_original_literals() | _literals(destination))):
        raise ValueError("Ludwig donor allocation collides with original inputs")


def _verify(blocks: Mapping[int, str], expected: Mapping[int, object], role: str,
            alternates: Mapping[int, str] | None = None) -> None:
    for event_id, expected_value in expected.items():
        actual = hashlib.sha256(blocks.get(event_id, "").encode()).hexdigest()
        allowed = ({expected_value} if isinstance(expected_value, str)
                   else set(expected_value))
        if alternates and event_id in alternates:
            allowed.add(alternates[event_id])
        if actual not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Ludwig donor expected one {label}")
    return text.replace(old, new, 1)


def _remap(text: str, mapping: Mapping[int, int]) -> str:
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda m: str(mapping.get(int(m[0]), int(m[0]))), text)


def _noop(block: str) -> str:
    header = block.splitlines()[0]
    header = re.sub(r"function\(([^)]*)\)", lambda m: "function(" + ", ".join(
        x.strip() if x.strip().startswith("unused_") else "unused_" + x.strip()
        for x in m[1].split(",") if x.strip()) + ")", header)
    return header + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _retired(arena: ArenaContract) -> set[int]:
    return {x for x in (*arena.phase_slots, arena.part_routine_event,
                        arena.cloth_routine_event, arena.attachment_anchor_event,
                        *arena.retired_combat_events) if x is not None}


def _telemetry(source: str, destination: str) -> str:
    result = source
    for name in ("CreatePlaylog", "StartTimeMeasurement"):
        old = [line for line in source.splitlines()
               if line.strip().startswith(name + "(")]
        new = [line for line in destination.splitlines()
               if line.strip().startswith(name + "(")]
        if len(old) != 1 or len(new) != 1:
            raise ValueError(f"Ludwig telemetry lacks unique {name}")
        result = _replace_once(result, old[0], new[0], "destination telemetry")
    return result


def _notification_flag(destination_health: str,
                       allocation: LudwigDonorAllocation) -> int:
    match = re.search(
        r"if \(!EventFlag\((\d+)\)\) \{\n\s+IssueBossRoomEntryNotification\(0\);",
        destination_health,
    )
    return int(match[1]) if match else allocation.notification_flag


def _mark_existing_entry_notification(block: str, flag: int) -> str:
    witness = "        IssueBossRoomEntryNotification(0);\n"
    if block.count(witness) > 1:
        raise ValueError("destination entry notification witness is not unique")
    return block.replace(witness, witness + f"        SetEventFlag({flag}, ON);\n", 1)


def _activation(arena: ArenaContract, block: str) -> str:
    result, count = re.subn(
        rf"^    ForceAnimationPlayback\({arena.actor}, [^\n]+\);\n", "", block,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise ValueError(f"{arena.key} activation lacks destination animation")
    # Preserve protection and the original trigger. Remove only model-specific
    # wake choreography; readiness repeats the authored safe end state.
    if f"    SetCharacterInvincibility({arena.actor}, Enabled);\n" in result:
        if f"    SetCharacterMaphits({arena.actor}, true);\n" in result:
            for line in (f"    SetCharacterMaphits({arena.actor}, true);\n",
                         f"    SetCharacterMaphits({arena.actor}, false);\n",
                         f"    SetCharacterGravity({arena.actor}, Disabled);\n",
                         f"    SetCharacterGravity({arena.actor}, Enabled);\n",
                         "    WaitFixedTimeFrames(30);\n",
                         "    WaitFixedTimeFrames(160);\n"):
                result = _replace_once(result, line, "", "model entry state")
        else:
            result = _replace_once(result, "    WaitFixedTimeFrames(70);\n", "",
                                   "model entry delay")
    if f"    SetCharacterImmortality({arena.actor}, Enabled);\n" in result:
        for line in (f"    SetSpEffect({arena.actor}, 5647, false);\n",
                     f"    ClearSpEffect({arena.actor}, 5647);\n"):
            result = _replace_once(result, line, "", "model entry effect")
    return result


def _music(arena: ArenaContract, block: str, phase_flag: int) -> str:
    if arena.phase_music_message is None:
        return _replace_once(block, f"EventFlag({arena.part_routine_event})",
                             f"EventFlag({phase_flag})", "music phase flag")
    return _replace_once(
        block, f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})",
        f"EventFlag({phase_flag})", "music phase message",
    )


def _normal_constructor(zero: str) -> str:
    witness = "    if (!EventFlag(13400999)) {\n        $InitializeEvent(0, 13404824);"
    if witness not in zero:
        raise ValueError("Ludwig normal constructor witness drift")
    return zero.split(witness, 1)[1].split("    } else {", 1)[0]


def _calls(zero: str, event: int, count: int) -> list[str]:
    found = [line for line in zero.splitlines()
             if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event) + r"(?:,|\))", line)]
    if len(found) != count:
        raise ValueError(f"Ludwig initializer witness drift for {event}")
    return found


def _phase_graph(donor: Mapping[int, str], mapping: Mapping[int, int]) -> tuple[list[str], list[str]]:
    normal = _normal_constructor(donor[0])
    initializers: list[str] = []
    bodies: list[str] = []
    for event in EVENTS:
        constructor = normal if event in (13404830, 13404835, 13404841) else donor[0]
        count = 3 if event == 13404830 else 1
        initializers.extend("    " + _remap(line.strip(), mapping)
                            for line in _calls(constructor, event, count))
        body = donor[event]
        if event in (13404820, 13404821, 13404822, 13404823):
            body, changed = re.subn(
                r"\(\(EventFlag\(13400999\) && HPRatio\(3400800\) < [0-9.]+\)\s*"
                r"\|\| \(!EventFlag\(13400999\) && HPRatio\(3400800\) < ([0-9.]+)\)\)",
                r"(HPRatio(3400800) < \1)", body,
            )
            if changed != 1:
                raise ValueError("Ludwig normal phase threshold witness drift")
        elif event == 13404824:
            body = _replace_once(body, "    SetEventFlag(9180, ON);\n", "",
                                 "source phase cutscene flag")
        elif event == 13404825:
            first = body.index("    if (!HasMultiplayerState(MultiplayerState.Multiplayer)) {")
            last = body.index("    DisplayBossHealthBar(Disabled, 3400800, 0, 451000);", first)
            body = body[:first] + body[last:]
            body = _replace_once(body, "    SetEventFlag(9180, OFF);\n", "",
                                 "source phase cutscene flag")
            body = _replace_once(
                body,
                "    ChangeCharacterEnableState(3400800, Disabled);\n"
                "    SetNetworkUpdateRate(3400801,",
                "    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Character, "
                "3400800, -1, 3400800);\n"
                "    ChangeCharacterEnableState(3400801, Enabled);\n"
                "    ChangeCharacterEnableState(3400800, Disabled);\n"
                "    SetNetworkUpdateRate(3400801,",
                "destination phase placement",
            )
            for line in (
                "    CharacterWarpRequest(3400800, TargetEntityType.Area, 3402900, -1);\n",
                "    WarpCharacterAndCopyFloor(3400801, TargetEntityType.Area, 3402806, -1, 3400800);\n",
            ):
                body = _replace_once(body, line, "", "source arena warp")
        bodies.append(_remap(body, mapping))
    return initializers, bodies


def _readiness(arena: ArenaContract, allocation: LudwigDonorAllocation) -> str:
    restore = {
        "cleric-beast": [
            f"    ChangeCharacterEnableState({arena.actor}, Enabled);",
            f"    SetCharacterGravity({arena.actor}, Enabled);",
            f"    SetCharacterMaphits({arena.actor}, false);",
        ],
        "blood-starved-beast": [],
        "darkbeast-paarl": [f"    SetCharacterInvincibility({arena.actor}, Disabled);"],
        "vicar-amelia": [f"    ChangeCharacterEnableState({arena.actor}, Enabled);"],
        "amygdala": [
            f"    SetCharacterGravity({arena.actor}, Enabled);",
            f"    SetCharacterInvincibility({arena.actor}, Disabled);",
            f"    SetCharacterMaphits({arena.actor}, false);",
        ],
        "ebrietas": [f"    SetCharacterImmortality({arena.actor}, Disabled);"],
    }[arena.key]
    lines = [f"$Event({allocation.readiness_event}, Default, function() {{",
             f"    EndIf(EventFlag({arena.completion_event}));",
             f"    WaitFor(EventFlag({arena.start_flag}));", *restore, "});"]
    return "\n".join(lines)


def _constructor(arena: ArenaContract, block: str,
                 allocation: LudwigDonorAllocation,
                 source_initializers: Sequence[str]) -> str:
    anchors = [f"    $InitializeEvent(0, {event});"
               for event in reversed(arena.phase_slots)
               if block.count(f"    $InitializeEvent(0, {event});") == 1]
    if not anchors:
        raise ValueError(f"{arena.key} lacks initializer anchor")
    calls = [*source_initializers,
             f"    $InitializeEvent(0, {allocation.readiness_event});",
             f"    $InitializeEvent(0, {allocation.terminal_bridge_event});"]
    result = _replace_once(block, anchors[0], anchors[0] + "\n" + "\n".join(calls),
                           "destination constructor anchor")
    return _replace_once(result, result.splitlines()[0] + "\n",
                         result.splitlines()[0] + "\n"
                         f"    SetEventFlag({allocation.readiness_event}, OFF);\n",
                         "constructor header")


def _health(source: str, destination: str, mapping: Mapping[int, int],
            allocation: LudwigDonorAllocation) -> str:
    result = _replace_once(
        source,
        "    if (EventFlag(13400999)) {\n"
        "        SetSpEffect(3400800, 8040, false);\n"
        "        SetSpEffect(3400801, 8040, false);\n"
        "    }\n", "", "alternate source health",
    )
    result = _replace_once(
        result, "    SetCharacterAIState(3400801, Disabled);\n",
        "    SetCharacterAIState(3400801, Disabled);\n"
        "    ChangeCharacterEnableState(3400801, Disabled);\n",
        "phase-two initial state",
    )
    result = _replace_once(
        result, "L0:\n    SetEventFlag(13404810, ON);",
        f"L0:\n    WaitFor(EventFlag({allocation.readiness_event}));\n"
        "    SetEventFlag(13404810, ON);", "saved-health readiness gate",
    )
    result = _replace_once(
        result, "L4:\n    if (!EventFlag(13404825)) {",
        "L4:\n    if (EventFlag(13404825)) {\n"
        "        ChangeCharacterEnableState(3400801, Enabled);\n"
        "    }\n"
        "    if (!EventFlag(13404825)) {", "saved phase visibility",
    )
    return _telemetry(_remap(result, mapping), destination)


def _camera(source: str, mapping: Mapping[int, int], arena: ArenaContract) -> str:
    result = _remap(source, mapping)
    result, count = re.subn(r"SetLockcamSlotNumber\(34, 0,",
                            f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},",
                            result)
    if count == 0:
        raise ValueError("Ludwig camera lacks source lockcam witness")
    return result


def _bridge(arena: ArenaContract, allocation: LudwigDonorAllocation) -> str:
    return f"""$Event({allocation.terminal_bridge_event}, Default, function() {{
    if (EventFlag({arena.completion_event}) || ThisEvent()) {{
        ChangeCharacterEnableState({allocation.phase_entity}, Disabled);
        ForceCharacterDeath({allocation.phase_entity}, false);
        EndEvent();
    }}
L0:
    WaitFor(EventFlag({allocation.readiness_event}));
    coreDead = CharacterDead({arena.actor});
    phaseDead = CharacterDead({allocation.phase_entity});
    WaitFor(coreDead || phaseDead);
    ForceCharacterDeath({arena.actor}, false);
    WaitFor(EventFlag({arena.completion_event}));
    ChangeCharacterEnableState({allocation.phase_entity}, Disabled);
    ForceCharacterDeath({allocation.phase_entity}, false);
}});"""


def _mapping(arena: ArenaContract, allocation: LudwigDonorAllocation,
             notification: int) -> dict[int, int]:
    return {
        PHASE_ONE: arena.actor, PHASE_TWO: allocation.phase_entity,
        9471: arena.completion_event, 13401800: arena.completion_event,
        13404802: arena.health_bar_event, 13404803: arena.music_event,
        13404804: arena.lockcam_event, 13404808: allocation.readiness_event,
        13404809: arena.start_flag + 1, 13404810: notification,
        **allocation.event_ids(),
    }


def ludwig_donor_contract(arena: ArenaContract,
                          allocation: LudwigDonorAllocation = DEFAULT_ALLOCATION) -> dict:
    _validate(allocation)
    return {
        "format": "bb-ludwig-donor-contract-v1", "status": "experimental",
        "arena": arena.key, "donor": "ludwig", "allocation": asdict(allocation),
        "source_variant": "normal-two-phase",
        "preserved_destination_events": [arena.completion_event,
                                          CO_OP_RESTORE_EVENTS[arena.key]],
        "adapted_destination_events": [arena.activation_event, arena.health_bar_event,
                                       arena.music_event, arena.lockcam_event],
        "retired_destination_controllers": sorted(_retired(arena)),
        "copied_source_events": [
            {"source_event": source, "destination_event": target,
             "expected_source_sha256": SOURCE_HASHES[source],
             "allowed_source_sha256s": sorted({SOURCE_HASHES[source], *(
                 () if source not in SOURCE_ALTERNATES
                 else (SOURCE_ALTERNATES[source],))})}
            for source, target in ((13404802, arena.health_bar_event),
                                   (13404804, arena.lockcam_event),
                                   *allocation.event_ids().items())
        ],
        "destination_owned_health_telemetry": {
            "event": arena.health_bar_event,
            "instructions": ["CreatePlaylog", "StartTimeMeasurement"],
        },
        "phase_transition": (
            "source combat boundary retained; source cinematic and m34 regions replaced "
            "by phase-two actor-to-primary floor copy"),
        "terminal_policy": "phase-one-or-phase-two death bridges into exact destination terminal",
        "ffx_evidence": {"source_event": 13404840, "effect_id": LUDWIG_EFFECT},
        "asset_dependency_gap": (
            "AI/TAE/behavior-driven assets remain unproven by parsed original inputs; "
            "explicit EMEVD FXR 645114 is merged"),
        "runtime_status": "unobserved",
    }


def patch_ludwig_donor(arena: ArenaContract, destination: str, donor_source: str,
                       allocation: LudwigDonorAllocation = DEFAULT_ALLOCATION) -> str:
    original, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(original, arena.expected, f"{arena.key} arena")
    _verify(donor, SOURCE_HASHES, "Ludwig donor", SOURCE_ALTERNATES)
    _validate(allocation, destination)
    notification = _notification_flag(original[arena.health_bar_event], allocation)
    mapping = _mapping(arena, allocation, notification)
    initializers, source_bodies = _phase_graph(donor, mapping)
    copied = dict(zip(EVENTS, source_bodies))
    activation = _activation(arena, original[arena.activation_event])
    if notification == allocation.notification_flag:
        activation = _mark_existing_entry_notification(activation, notification)
    edits = {event: _noop(original[event]) for event in _retired(arena)}
    edits.update({
        0: _constructor(arena, original[0], allocation, initializers),
        arena.activation_event: activation,
        arena.health_bar_event: _health(donor[13404802],
                                        original[arena.health_bar_event], mapping,
                                        allocation),
        arena.music_event: _music(arena, original[arena.music_event],
                                  allocation.phase_24),
        arena.lockcam_event: _camera(donor[13404804], mapping, arena),
    })
    additions = [*(copied[event] for event in EVENTS),
                 _readiness(arena, allocation), _bridge(arena, allocation)]
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions) + "\n"
    output = event_blocks(result)
    added = {*allocation.event_ids().values(), allocation.readiness_event,
             allocation.terminal_bridge_event}
    if set(output) != set(original) | added:
        raise ValueError("Ludwig donor changed unexpected event identities")
    for event_id, block in original.items():
        if event_id not in edits and output[event_id] != block:
            raise ValueError(f"Ludwig donor changed unrelated event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("Ludwig donor changed destination progression")
    return result


def _source(slots: Sequence[Slot], entity: int) -> Slot:
    archetype = P1 if entity == PHASE_ONE else P2
    found = [slot for slot in slots if slot.map_name == "m34_00_00_00"
             and slot.entity_id == entity and slot.archetype == archetype
             and slot.part_name == SOURCE_PARTS[entity]]
    if len(found) != 1 or found[0].talk_id:
        raise ValueError(f"Ludwig lacks exact source actor {entity}")
    return found[0]


def _native(source: Slot, *, anchored: bool = False) -> dict:
    provenance = {"format": "bb-boss-actor-pin-v1",
                  "part_sha256": PART_PINS[source.entity_id]}
    if anchored:
        provenance["anchor_sha256"] = PART_PINS[PHASE_ONE]
    result = {"source_provenance": provenance,
              "source_initialization": dict(SOURCE_INITIALIZATION)}
    if anchored:
        result["source_part_kind"] = "enemy"
    return result


def native_plan_ludwig_donor(arena: ArenaContract, slots: Sequence[Slot],
        npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str,
        allocation: LudwigDonorAllocation = DEFAULT_ALLOCATION) -> dict:
    _validate(allocation)
    destinations = sorted([slot for slot in slots if slot.entity_id == arena.actor
                           and slot.archetype == arena.archetype],
                          key=lambda slot: slot.map_name)
    if len(destinations) != arena.destination_count:
        raise ValueError(f"Ludwig/{arena.key} lacks destination state closure")
    one, two = _source(slots, PHASE_ONE), _source(slots, PHASE_TWO)
    swap = Swap(destinations[0].logical_key, [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations},
        destinations[0].archetype, P1,
        destinations={slot.key: {"map_name": slot.map_name,
            "entity_id": slot.entity_id, "x": slot.x, "y": slot.y, "z": slot.z}
            for slot in destinations})
    changes, skips = plan_scaling([swap], destinations, dict(npcs), dict(effects),
                                  boss_tiers=True)
    primary, additions, requirements = [], [], []
    for target in destinations:
        primary.append({
            "source_map": one.map_name, "source_event_file": "event/" + EVENT_FILE,
            "source_part": one.part_name, "source_entity_id": one.entity_id,
            "source_archetype": asdict(one.archetype), "source_talk_id": 0,
            "destination_map": target.map_name, "destination_part": target.part_name,
            "destination_entity_id": target.entity_id,
            "destination_original_talk_id": target.talk_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                       "damage_anim_id", "provenance"],
            **_native(one),
        })
        additions.append({
            "source_map": two.map_name, "source_event_file": "event/" + EVENT_FILE,
            "source_part": two.part_name, "source_anchor_part": one.part_name,
            "source_entity_id": two.entity_id, "source_archetype": asdict(two.archetype),
            "destination_map": target.map_name,
            "destination_anchor_part": target.part_name,
            "destination_part": "ap_ludwig_phase_two",
            "destination_entity_id": allocation.phase_entity,
            "allocation_evidence": "Ludwig reusable donor allocation v1; original and project ledger scan",
            "required_native_fields": ["source_provenance", "source_initialization"],
            **_native(two, anchored=True),
        })
        requirements.append({
            "destination_map": target.map_name,
            "destination_part": "ap_ludwig_phase_two",
            "parent_logical_key": swap.logical_key,
            "source_npc_param_id": P2.npc_param_id,
            "strategy": "allocate_distinct_verified_helper_clone",
        })
    ffx_file, ffx_hash = DESTINATION_FFX[arena.key]
    destination_event = arena.event_file.removesuffix(".js")
    contract = ludwig_donor_contract(arena, allocation)
    contract["helper_scaling_parent"] = {
        f"{row['destination_map']}:{row['destination_part']}": destinations[0].logical_key
        for row in additions
    }
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-ludwig"},
        "boss_contract": contract,
        "primary_init_source_bindings": primary,
        "boss_actor_additions": additions,
        "boss_actor_scaling_requirements": requirements,
        "boss_emevd_ffx_requirements": [{
            "format": "bb-boss-emevd-ffx-requirement-v1",
            "source_map": "m34_00_00_00", "destination_map": destinations[0].map_name,
            "source_event_file": "m34_00_00_00.emevd.dcx",
            "source_event_sha256": SOURCE_EVENT_SHA256,
            "source_event_id": 13404840,
            "destination_event_file": destination_event,
            "destination_event_id": allocation.player_warp_event,
            "effect_id": LUDWIG_EFFECT,
            "occurrence_count": LUDWIG_EFFECT_OCCURRENCE_COUNT,
        }],
        "boss_ffx_merges": [{
            "source_file": SOURCE_FFX_FILE, "source_sha256": SOURCE_FFX_SHA256,
            "destination_file": ffx_file, "destination_sha256": ffx_hash,
            "required_effect_ids": [LUDWIG_EFFECT],
            "policy": "preserve_destination_union_source_v1",
        }],
        "scaling": {"enabled": bool(changes),
            "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes), "changes": [x.json() for x in changes],
            "skip_count": len(skips), "skips": skips},
    }


def portable_ludwig_arenas(
        arenas: Sequence[ArenaContract] = ARENAS) -> tuple[ArenaContract, ...]:
    return tuple(arena for arena in arenas if arena.phase_slots)
