"""Typed encounter contracts for independent boss donors and arenas.

The contract data is derived from the original EMEVD text in the committed
input bundle.  It does not infer a generic numeric map-prefix substitution:
every literal that moves from a donor into an arena is declared as an actor,
completion flag, encounter-start flag, event slot, or initializer binding.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import asdict, dataclass
from typing import Iterable

from . import boss_canary
from .model import Archetype, Swap
from .scaling import plan_scaling

EventBlocks = dict[int, str]


def event_blocks(text: str) -> EventBlocks:
    return boss_canary.event_blocks(text)


@dataclass(frozen=True)
class PartBinding:
    """One Event(0) call that initializes a donor's body part routine."""

    slot: int
    arguments: tuple[str, ...]


@dataclass(frozen=True)
class ArenaContract:
    key: str
    event_file: str
    map_prefix: str
    actor: int
    archetype: Archetype
    destination_count: int
    completion_event: int
    start_flag: int
    health_bar_event: int
    health_bar_label: int
    activation_event: int
    music_event: int
    lockcam_event: int
    lockcam_map: int
    lockcam_subarea: int
    phase_slots: tuple[int, ...]
    co_op_entry_event: int
    part_routine_event: int
    cloth_routine_event: int | None
    part_slots: tuple[PartBinding, ...]
    expected: dict[int, str]


@dataclass(frozen=True)
class CombatPackage:
    key: str
    event_file: str
    map_prefix: str
    actor: int
    archetype: Archetype
    completion_event: int
    start_flag: int
    activation_event: int
    health_bar_event: int
    health_bar_label: int
    phase_events: tuple[int, ...]
    co_op_entry_event: int | None
    lockcam_event: int | None
    phase_music_message: int | None
    part_routine_event: int | None
    part_bindings: tuple[PartBinding, ...]
    expected: dict[int, str]
    legacy_canary: bool = False


CLERIC_ARENA = ArenaContract(
    key="cleric-beast",
    event_file="m24_01_00_00.emevd.dcx.js",
    map_prefix="m24_01_",
    actor=2410800,
    archetype=Archetype("c5000", 500241, 500241, 0),
    destination_count=3,
    completion_event=12411700,
    start_flag=12414700,
    health_bar_event=12414702,
    health_bar_label=500000,
    activation_event=12411702,
    music_event=12414703,
    lockcam_event=12414704,
    lockcam_map=24,
    lockcam_subarea=1,
    phase_slots=(12414707, 12414708),
    co_op_entry_event=12414708,
    part_routine_event=12414710,
    cloth_routine_event=12414720,
    part_slots=(
        PartBinding(0, ("2410", "2410", "NPCPartType.Part1", "20", "480", "490", "8020")),
        PartBinding(1, ("2411", "2411", "NPCPartType.Part2", "120", "481", "491", "8000")),
        PartBinding(2, ("2412", "2412", "NPCPartType.Part3", "300", "482", "492", "8010")),
        PartBinding(3, ("2413", "2413", "NPCPartType.Part4", "200", "483", "493", "8030")),
        PartBinding(4, ("2414", "2414", "NPCPartType.Part5", "200", "484", "494", "8040")),
    ),
    expected={
        0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
        **{key: value for key, value in boss_canary.EXPECTED.items() if key >= 12400000},
    },
)

BSB_ARENA = ArenaContract(
    key="blood-starved-beast",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300800,
    archetype=Archetype("c2090", 209000, 209000, 0),
    destination_count=2,
    completion_event=12301800,
    start_flag=12304800,
    health_bar_event=12304802,
    health_bar_label=209000,
    activation_event=12301802,
    music_event=12304803,
    lockcam_event=12304804,
    lockcam_map=23,
    lockcam_subarea=0,
    phase_slots=(12304807,),
    co_op_entry_event=12301803,
    part_routine_event=12304808,
    cloth_routine_event=None,
    # The one former BSB phase initializer becomes the five explicit Paarl
    # limb initializers when its combat package is selected.
    part_slots=(PartBinding(0, ()),),
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301800: "e9eed714540eab5058a6553eb5b11b28f2edcb6d4236679efaafafb9c4e8f1a4",
        12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
        12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
        12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
        12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
        12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
        12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
        12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
    },
)

PAARL_ARENA = ArenaContract(
    key="darkbeast-paarl",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300810,
    archetype=Archetype("c5080", 508000, 508000, 0),
    destination_count=2,
    completion_event=12301700,
    start_flag=12304700,
    health_bar_event=12304702,
    health_bar_label=508000,
    activation_event=12301702,
    music_event=12304703,
    lockcam_event=12304704,
    lockcam_map=23,
    lockcam_subarea=0,
    phase_slots=(12304707, 12304715),
    co_op_entry_event=12301703,
    part_routine_event=12304715,
    cloth_routine_event=None,
    part_slots=(
        PartBinding(0, ("2300", "2300", "NPCPartType.Part1", "480", "490", "8000", "130")),
        PartBinding(1, ("2301", "2301", "NPCPartType.Part2", "481", "491", "8010", "150")),
        PartBinding(2, ("2302", "2302", "NPCPartType.Part3", "482", "492", "8030", "150")),
        PartBinding(3, ("2303", "2303", "NPCPartType.Part4", "483", "493", "8020", "200")),
        PartBinding(4, ("2304", "2304", "NPCPartType.Part5", "484", "494", "8040", "200")),
    ),
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301700: "3d8feaac026a84d0e378ba5599fa4e3b60ca424d59a88776434a2e8be0c77d3e",
        12301702: "374db59c960671a66ac7afdd712cc0576d03a554ec7ca3d74f0902799bfd517d",
        12301703: "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
        12304702: "cb57ca1efd9f78db3f35500a83581b90e3101e0d13446d398715faad7383c220",
        12304703: "e425e391e28c7dae502e70533be953a18976657b4ab3f5ba328bf4304840e825",
        12304704: "fc0d014681e349fa969f5746f3ac690ad606d48e1f1c828288547efab3dcd3b7",
        12304707: "c88383d5ab10974eaa968e06dbbd9f92e6d0ca05ae02fe38650490a24445cf3b",
        12304715: "015e8810e6bdab08aa66827c290b554890e0c45be100efe95fcf6730a00ee74e",
    },
)

BSB_PACKAGE = CombatPackage(
    key="blood-starved-beast",
    event_file=boss_canary.DONOR_EVENT_FILE + ".js",
    map_prefix="m23_00_",
    actor=2300800,
    archetype=Archetype("c2090", 209000, 209000, 0),
    completion_event=12301800,
    start_flag=12304800,
    activation_event=12301802,
    health_bar_event=12304802,
    # This is the literal final operand in DisplayBossHealthBar in 12304802.
    health_bar_label=209000,
    phase_events=(12304807, 12304808),
    co_op_entry_event=None,
    lockcam_event=None,
    phase_music_message=None,
    part_routine_event=None,
    part_bindings=(),
    expected={
        **{key: value for key, value in boss_canary.EXPECTED.items() if key < 12400000},
        12301802: "c8e1b3b8b94fe800a158228a1b177c944c90883fc45826b5060488a064ca145d",
        12301803: "62fb078e77c476dc5d9d3631843895197d9974e67a15880b5ca133dd870f299c",
        12304802: "a50f737211efc3572c1932fcab0ef6b5b0af546312412f693c0e545363c73d2b",
        12304803: "f85aeee6b625f080ef8ac7fd9859b684fcd7b0becd1aec1f2e662573bca92bf1",
        12304804: "86edb06de9efdc94365fb640741ce4d62620363a3c37ebb99d37ef2b9d3f3521",
    },
    legacy_canary=True,
)

PAARL_PACKAGE = CombatPackage(
    key="darkbeast-paarl",
    event_file="m23_00_00_00.emevd.dcx.js",
    map_prefix="m23_00_",
    actor=2300810,
    archetype=Archetype("c5080", 508000, 508000, 0),
    completion_event=12301700,
    start_flag=12304700,
    activation_event=12301702,
    health_bar_event=12304702,
    # Witnessed in source event 12304702, rather than inferred from NpcParam.
    health_bar_label=508000,
    phase_events=(12304707,),
    co_op_entry_event=12301703,
    lockcam_event=12304704,
    phase_music_message=20,
    part_routine_event=12304715,
    part_bindings=(
        PartBinding(0, ("2300", "2300", "NPCPartType.Part1", "480", "490", "8000", "130")),
        PartBinding(1, ("2301", "2301", "NPCPartType.Part2", "481", "491", "8010", "150")),
        PartBinding(2, ("2302", "2302", "NPCPartType.Part3", "482", "492", "8030", "150")),
        PartBinding(3, ("2303", "2303", "NPCPartType.Part4", "483", "493", "8020", "200")),
        PartBinding(4, ("2304", "2304", "NPCPartType.Part5", "484", "494", "8040", "200")),
    ),
    expected={
        0: "7b60f63d5c249c80db0522935bf7e5e3f2bf62d95a25a6f17896ba1ceb5854af",
        12301700: "3d8feaac026a84d0e378ba5599fa4e3b60ca424d59a88776434a2e8be0c77d3e",
        12301702: "374db59c960671a66ac7afdd712cc0576d03a554ec7ca3d74f0902799bfd517d",
        12301703: "ca968c9f60d2a495e9f3c87c77083ec5d1524b34792d646aa29a239f7f11b653",
        12304702: "cb57ca1efd9f78db3f35500a83581b90e3101e0d13446d398715faad7383c220",
        12304703: "e425e391e28c7dae502e70533be953a18976657b4ab3f5ba328bf4304840e825",
        12304704: "fc0d014681e349fa969f5746f3ac690ad606d48e1f1c828288547efab3dcd3b7",
        12304707: "c88383d5ab10974eaa968e06dbbd9f92e6d0ca05ae02fe38650490a24445cf3b",
        12304715: "015e8810e6bdab08aa66827c290b554890e0c45be100efe95fcf6730a00ee74e",
    },
)

CLERIC_PACKAGES: tuple[CombatPackage, ...] = (BSB_PACKAGE, PAARL_PACKAGE)
BSB_ARENA_PACKAGES: tuple[CombatPackage, ...] = (PAARL_PACKAGE,)
PAARL_ARENA_PACKAGES: tuple[CombatPackage, ...] = (BSB_PACKAGE,)
ARENAS: tuple[ArenaContract, ...] = (CLERIC_ARENA, BSB_ARENA, PAARL_ARENA)


def _verify_pins(label: str, blocks: EventBlocks, expected: dict[int, str]) -> None:
    for event_id, digest in expected.items():
        block = blocks.get(event_id)
        if block is None or hashlib.sha256(block.encode("utf-8")).hexdigest() != digest:
            raise ValueError(f"unsupported original {label} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"contract expected one {label}")
    return text.replace(old, new, 1)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        name.strip() if name.strip().startswith("unused_") else "unused_" + name.strip()
        for name in match[1].split(",") if name.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _remap_declared_literals(block: str, *, actor: tuple[int, int],
                             completion: tuple[int, int], event: tuple[int, int],
                             flags: tuple[tuple[int, int], ...] = ()) -> str:
    """Map only an explicitly typed donor literal inside a copied event body."""
    replacements = dict((actor, completion, event, *flags))
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(replacements.get(int(match[0]), int(match[0]))), block)


def _replace_event(source: str, edits: dict[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(boss_canary.parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _paarl_activation(arena: ArenaContract, original: str) -> str:
    """Keep the arena's trigger/fog geometry but use Paarl's native wake-up."""
    if arena is CLERIC_ARENA:
        activation = _replace_once(
            original, "    SetCharacterGravity(2410800, Disabled);\n",
            "    SetCharacterInvincibility(2410800, Enabled);\n", "Paarl pre-entry invincibility")
        activation = _replace_once(
            activation, "    SetCharacterMaphits(2410800, true);\n",
            "    ForceAnimationPlayback(2410800, 7000, true, false, false);\n", "Paarl pre-entry animation")
        activation = _replace_once(activation,
            "    IssueShortWarpRequest(2410800, TargetEntityType.Area, 2412831, -1);\n", "", "arena-only warp")
        activation = _replace_once(
            activation, "ForceAnimationPlayback(2410800, 3028,", "ForceAnimationPlayback(2410800, 7001,",
            "declared arena activation animation")
        activation = _replace_once(activation, "    WaitFixedTimeFrames(110);\n",
            "    WaitFixedTimeFrames(70);\n    SetCharacterInvincibility(2410800, Disabled);\n",
            "Paarl entry delay")
        activation = _replace_once(activation, "    SetCharacterGravity(2410800, Enabled);\n", "", "arena-only gravity reset")
        return _replace_once(activation, "    SetCharacterMaphits(2410800, false);\n", "", "arena-only maphit reset")
    if arena is BSB_ARENA:
        activation = _replace_once(original, "    WaitFor(\n",
            "    SetCharacterInvincibility(2300800, Enabled);\n"
            "    ForceAnimationPlayback(2300800, 7000, true, false, false);\n"
            "    WaitFor(\n", "Paarl pre-entry sequence")
        activation = _replace_once(activation, "    ForceAnimationPlayback(2300800, 7001, false, false, false);\n",
            "    ForceAnimationPlayback(2300800, 7001, false, false, false);\n"
            "    WaitFixedTimeFrames(70);\n"
            "    SetCharacterInvincibility(2300800, Disabled);\n", "Paarl entry delay")
        return activation
    raise ValueError(f"no Paarl activation contract for arena {arena.key}")


def _replace_part_initializers(event_zero: str, arena: ArenaContract,
                               donor: CombatPackage) -> str:
    if len(arena.part_slots) == len(donor.part_bindings):
        for source_binding, destination_binding in zip(donor.part_bindings, arena.part_slots):
            if source_binding.slot != destination_binding.slot:
                raise ValueError("body-part binding slots are not aligned")
            old = "    $InitializeEvent(" + ", ".join(
                (str(destination_binding.slot), str(arena.part_routine_event), *destination_binding.arguments)) + ");"
            new = "    $InitializeEvent(" + ", ".join(
                (str(source_binding.slot), str(arena.part_routine_event), *source_binding.arguments)) + ");"
            event_zero = _replace_once(event_zero, old, new, f"body-part initializer {source_binding.slot}")
        return event_zero
    if len(arena.part_slots) == 1 and not arena.part_slots[0].arguments:
        slot = arena.part_slots[0]
        old = f"    $InitializeEvent({slot.slot}, {arena.part_routine_event});"
        new = "\n".join("    $InitializeEvent(" + ", ".join(
            (str(binding.slot), str(arena.part_routine_event), *binding.arguments)) + ");"
            for binding in donor.part_bindings)
        return _replace_once(event_zero, old, new, "single body-part initializer")
    raise ValueError("arena and donor body-part contracts do not match")


def _remap_lockcam(block: str, arena: ArenaContract) -> str:
    """Map the two source-local camera operands, not arbitrary map literals."""
    old = "SetLockcamSlotNumber(23, 0,"
    new = f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},"
    if block.count(old) != 2:
        raise ValueError("Paarl lockcam contract expected two source camera calls")
    return block.replace(old, new)


def _paarl_patch(arena: ArenaContract, donor: CombatPackage,
                 destination: str, donor_source: str) -> str:
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if len(donor.phase_events) > len(arena.phase_slots):
        raise ValueError("arena has too few declared phase slots for donor")
    if not donor.part_bindings or donor.part_routine_event is None:
        raise ValueError("arena and donor body-part contracts do not match")

    edits: dict[int, str] = {}
    if arena is CLERIC_ARENA:
        edits[12411701] = _replace_once(original[12411701], "500099999", "0", "destination death cue")
    edits[arena.activation_event] = _paarl_activation(arena, original[arena.activation_event])
    edits[arena.health_bar_event] = _replace_once(
        original[arena.health_bar_event],
        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})", "health-bar label")
    if arena is CLERIC_ARENA:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event], "CharacterHasEventMessage(2410800, 100)",
            f"CharacterHasEventMessage(2410800, {donor.phase_music_message})", "music phase message")
    elif arena is BSB_ARENA:
        edits[arena.music_event] = _replace_once(
            original[arena.music_event], "flagArea2 &= EventFlag(12304808);",
            f"flagArea2 &= CharacterHasEventMessage({arena.actor}, {donor.phase_music_message});", "music phase trigger")
    else:
        raise ValueError(f"no Paarl music contract for arena {arena.key}")
    if donor.lockcam_event is not None:
        lockcam = _remap_declared_literals(
            donor_blocks[donor.lockcam_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(donor.lockcam_event, arena.lockcam_event))
        edits[arena.lockcam_event] = _remap_lockcam(lockcam, arena)

    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(source_event, destination_event))
    if donor.co_op_entry_event is not None:
        edits[arena.co_op_entry_event] = _remap_declared_literals(
            donor_blocks[donor.co_op_entry_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event),
            event=(donor.co_op_entry_event, arena.co_op_entry_event),
            flags=((donor.start_flag, arena.start_flag), (donor.activation_event, arena.activation_event)))
    else:
        edits[arena.co_op_entry_event] = _end_event(original[arena.co_op_entry_event])
    edits[arena.part_routine_event] = _remap_declared_literals(
        donor_blocks[donor.part_routine_event], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event),
        event=(donor.part_routine_event, arena.part_routine_event))
    if arena.cloth_routine_event is not None:
        edits[arena.cloth_routine_event] = _end_event(original[arena.cloth_routine_event])

    edits[0] = _replace_part_initializers(original[0], arena, donor)

    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("contract changed arena event identity set")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("contract changed destination completion event")
    return result


def _bsb_activation(arena: ArenaContract, original: str) -> str:
    if arena is not PAARL_ARENA:
        raise ValueError(f"no BSB activation contract for arena {arena.key}")
    for instruction in (
        "    SetCharacterInvincibility(2300810, Enabled);\n",
        "    ForceAnimationPlayback(2300810, 7000, true, false, false);\n",
        "    WaitFixedTimeFrames(70);\n",
        "    SetCharacterInvincibility(2300810, Disabled);\n",
    ):
        original = _replace_once(original, instruction, "", "Paarl-only activation instruction")
    return original


def _collapse_part_initializers(event_zero: str, arena: ArenaContract) -> str:
    """Replace five exact limb calls with BSB's one zero-argument phase call."""
    bindings = arena.part_slots
    if len(bindings) != 5:
        raise ValueError("BSB contract requires five destination limb initializers")
    for index, binding in enumerate(bindings):
        old = "    $InitializeEvent(" + ", ".join(
            (str(binding.slot), str(arena.part_routine_event), *binding.arguments)) + ");"
        new = f"    $InitializeEvent(0, {arena.part_routine_event});" if index == 0 else ""
        event_zero = _replace_once(event_zero, old, new, f"destination limb initializer {binding.slot}")
    return event_zero


def _bsb_patch(arena: ArenaContract, donor: CombatPackage,
               destination: str, donor_source: str) -> str:
    original, donor_blocks = event_blocks(destination), event_blocks(donor_source)
    _verify_pins("arena", original, arena.expected)
    _verify_pins("donor", donor_blocks, donor.expected)
    if arena is not PAARL_ARENA or donor is not BSB_PACKAGE:
        raise ValueError(f"no typed BSB adapter for {arena.key} <- {donor.key}")
    edits: dict[int, str] = {
        arena.activation_event: _bsb_activation(arena, original[arena.activation_event]),
        arena.health_bar_event: _replace_once(
            original[arena.health_bar_event],
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label})",
            f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label})", "health-bar label"),
        arena.music_event: _replace_once(
            original[arena.music_event],
            f"chrFlagArea &= CharacterHasEventMessage({arena.actor}, 20);",
            f"chrFlagArea &= EventFlag({arena.part_routine_event});", "BSB phase-two music trigger"),
    }
    for source_event, destination_event in zip(donor.phase_events, arena.phase_slots):
        edits[destination_event] = _remap_declared_literals(
            donor_blocks[source_event], actor=(donor.actor, arena.actor),
            completion=(donor.completion_event, arena.completion_event), event=(source_event, destination_event),
            flags=((12304807, arena.phase_slots[0]),))
    edits[arena.co_op_entry_event] = _remap_declared_literals(
        donor_blocks[12301803], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event), event=(12301803, arena.co_op_entry_event),
        flags=((donor.start_flag, arena.start_flag), (donor.activation_event, arena.activation_event)))
    lockcam = _remap_declared_literals(
        donor_blocks[12304804], actor=(donor.actor, arena.actor),
        completion=(donor.completion_event, arena.completion_event), event=(12304804, arena.lockcam_event),
        flags=((donor.start_flag, arena.start_flag), (12304801, 12304701)))
    edits[arena.lockcam_event] = lockcam
    edits[0] = _collapse_part_initializers(original[0], arena)
    result = _replace_event(destination, edits)
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("contract changed arena event identity set")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"contract touched unrelated arena event {event_id}")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("contract changed destination completion event")
    return result


def patch_contract_swap(arena: ArenaContract, donor: CombatPackage,
                        destination: str, donor_source: str) -> str:
    """Build one checked arena overlay from one independently declared donor."""
    if donor.legacy_canary and arena is CLERIC_ARENA:
        _verify_pins("arena", event_blocks(destination), arena.expected)
        _verify_pins("donor", event_blocks(donor_source), donor.expected)
        return boss_canary.patch_event_source(destination, donor_source)
    if arena in (CLERIC_ARENA, BSB_ARENA) and donor is PAARL_PACKAGE:
        return _paarl_patch(arena, donor, destination, donor_source)
    if arena is PAARL_ARENA and donor is BSB_PACKAGE:
        return _bsb_patch(arena, donor, destination, donor_source)
    raise ValueError(f"no typed adapter implementation for {arena.key} <- {donor.key}")


def _mapping(arena: ArenaContract, donor: CombatPackage) -> dict:
    phase_map = dict(zip(donor.phase_events, arena.phase_slots))
    return {
        "actor": {str(donor.actor): arena.actor},
        "completion_event": {str(donor.completion_event): arena.completion_event},
        "encounter_start_flag": {str(donor.start_flag): arena.start_flag},
        "phase_events": {str(source): target for source, target in phase_map.items()},
        "co_op_entry_event": None if donor.co_op_entry_event is None else {
            str(donor.co_op_entry_event): arena.co_op_entry_event,
        },
        "part_routine": None if donor.part_routine_event is None else {
            str(donor.part_routine_event): arena.part_routine_event,
        },
    }


def plan_contract_shuffle(seed: str, arena: ArenaContract = CLERIC_ARENA,
                          packages: Iterable[CombatPackage] = CLERIC_PACKAGES) -> dict:
    """Choose an arena-compatible donor deterministically, independent of legacy plans."""
    choices = sorted(tuple(packages), key=lambda package: package.key)
    if not choices:
        raise ValueError("no combat packages registered for this arena")
    donor = random.Random(f"bb-boss-contract-v1:{seed}:{arena.key}").choice(choices)
    return {
        "format": "bb-boss-contract-plan-v1",
        "dry_run": True,
        "status": "planned",
        "writer_status": "not_written",
        "seed": seed,
        "arena": arena.key,
        "donor": donor.key,
        "event_files": {"arena": arena.event_file, "donor": donor.event_file},
        "health_bar": {"event": arena.health_bar_event, "label": donor.health_bar_label,
                       "evidence": f"literal DisplayBossHealthBar operand in donor event {donor.health_bar_event}"},
        "remap": _mapping(arena, donor),
        "part_initializers": [asdict(binding) for binding in donor.part_bindings],
        "arena_hash_pins": dict(sorted(arena.expected.items())),
        "donor_hash_pins": dict(sorted(donor.expected.items())),
    }


def plan_contract_swap(arena: ArenaContract, donor: CombatPackage, slots, npcs, effects,
                       seed: str) -> dict:
    """Build the native map-swap and scaling plan for one typed contract pair.

    The event builder consumes the separate contract metadata.  This function
    intentionally emits the existing writer's ``bb-enemizer-plan-v2`` map and
    scaling shape so its map provenance checks continue to apply.
    """
    destinations = sorted(
        (slot for slot in slots if slot.entity_id == arena.actor and slot.map_name.startswith(arena.map_prefix)),
        key=lambda slot: slot.key,
    )
    donors = [slot for slot in slots if slot.entity_id == donor.actor and slot.map_name.startswith(donor.map_prefix)]
    if (len(destinations) != arena.destination_count or not donors
            or any(slot.archetype != arena.archetype for slot in destinations)
            or any(slot.archetype != donor.archetype for slot in donors)):
        raise ValueError(f"unsupported boss placement provenance for {arena.key} <- {donor.key}")
    if (len({slot.logical_key for slot in destinations}) != 1
            or any(slot.dummy or slot.talk_id or slot.archetype.chara_init_id for slot in destinations + donors)):
        raise ValueError(f"boss contract {arena.key} <- {donor.key} requires ordinary non-talk-bound placements")
    swap = Swap(
        destinations[0].logical_key, [slot.key for slot in destinations],
        {slot.key: slot.archetype for slot in destinations}, arena.archetype, donor.archetype,
        warnings=["experimental boss contract; runtime entrance, phases and AP completion require validation"],
        destinations={slot.key: {"map_name": slot.map_name, "entity_id": slot.entity_id,
                                 "x": slot.x, "y": slot.y, "z": slot.z} for slot in destinations},
    )
    changes, skips = plan_scaling([swap], destinations, npcs, effects)
    if len(changes) > 1 or (changes and skips):
        raise ValueError(f"boss contract {arena.key} <- {donor.key} has an ambiguous normalization plan")
    return {
        "format": "bb-enemizer-plan-v2",
        "dry_run": True,
        "seed": seed,
        "swap_count": 1,
        "swaps": [swap.json()],
        "options": {"experimental_boss_contract": f"{arena.key}<-{donor.key}"},
        "boss_contract": plan_contract_shuffle(seed, arena, (donor,)),
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
