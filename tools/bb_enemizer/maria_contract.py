"""Pinned Lady Maria encounter contract and guarded Cleric adapter.

This module deliberately stays outside ``boss_contracts`` while the registry is
being changed.  It uses the same immutable CombatPackage/EventAttachment types
so the registry can import it once its append-only attachment interface is
settled.

Facts are extracted from CUSA03173 AppVer 01.09 in ``research/bb_inputs.db``.
The one unplaced health-routine event target (3500801) is represented as a
blocking binding, never synthesized from its numeric prefix.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping

from .boss_contracts import (
    CLERIC_ARENA,
    CLERIC_PACKAGE,
    CombatPackage,
    EventAttachment,
    PartBinding,
    event_blocks,
)
from .model import Archetype

MARIA_EVENT_FILE = "m35_00_00_00.emevd.dcx.js"
MARIA_ACTOR = 3500800
MARIA_EVENT_TARGET = 3500801


@dataclass(frozen=True)
class MariaArenaState:
    """Maria-specific arena/progression state which must not become donor state."""

    completion_event: int = 13501800
    cutscene_entry_event: int = 13501801
    co_op_restore_event: int = 13501807
    host_fog_event: int = 13504800
    guest_fog_event: int = 13504801
    health_event: int = 13504802
    music_event: int = 13504803
    lockcam_event: int = 13504804
    music_cleanup_event: int = 13504805
    client_fog_gravity_events: tuple[int, int] = (13504806, 13504807)
    phase_cleanup_event: int = 13504822
    completion_flag: int = 13501800
    encounter_start_flag: int = 13504808
    co_op_entered_flag: int = 13504809
    health_started_flag: int = 13504810
    phase_two_music_flag: int = 13504811
    event_target: int = MARIA_EVENT_TARGET
    cutscene_id: int = 35000010
    source_reward_flags: tuple[int, ...] = (6675, 3510, 3511, 3512, 3513, 3515, 3516, 3517, 3518)


MARIA_ARENA = MariaArenaState()

# 13504822 is Maria's only portable event-side combat dependency: message 20
# clears SpEffect 5526 and restarts.  Its initializer is witnessed verbatim in
# Maria Event(0), allowing an append-only recipient to copy it into an owned ID.
MARIA_PACKAGE = CombatPackage(
    key="lady-maria",
    event_file=MARIA_EVENT_FILE,
    map_prefix="m35_00_",
    actor=MARIA_ACTOR,
    archetype=Archetype("c4520", 452000, 452000, 0),
    completion_event=MARIA_ARENA.completion_event,
    start_flag=MARIA_ARENA.encounter_start_flag,
    activation_event=MARIA_ARENA.cutscene_entry_event,
    health_bar_event=MARIA_ARENA.health_event,
    health_bar_label=452000,
    phase_events=(MARIA_ARENA.phase_cleanup_event,),
    co_op_entry_event=MARIA_ARENA.co_op_restore_event,
    lockcam_event=MARIA_ARENA.lockcam_event,
    phase_music_message=100,
    part_routine_event=None,
    part_bindings=(),
    attachments=(EventAttachment(MARIA_ARENA.phase_cleanup_event, (PartBinding(0, ()),)),),
    virtual_entities=(),
    # Maria is enabled after 35000010; the source has no ForceAnimationPlayback
    # witness.  A recipient must remove its model-specific entry animation.
    entry_animation=None,
    lockcam_map=35,
    lockcam_subarea=0,
    expected={
        0: "f7acdb00c7384ac586de81b0c37e7e58d08c11876c76a04a9648844f4689d0a9",
        13501800: "7f29c5859db8ce643bc2ea80de1d4f2aead1c3980ab541164fdea26e2dd7ecbb",
        13501801: "0fb99b1b7c02f3fb5ff2d4990ad8a6a24982278077675d19ef675f4df767fc31",
        13501807: "1c352ec3c5fcd6b866d0880e88d2c693d865d78d5ef3915e20582e5169b0278c",
        13504800: "0c16b7ed8927c1853f144448b24f62ef1db0c5e8933ec2fc5ae77a4f6943cbc5",
        13504801: "377fbaa566e636915997d1f9f5f6dd7c3ee7f9de38e550d97ba9d7f0a3b18009",
        13504802: "871698fb8a14efbabfd0c8c4c767aea22091a3ef07eb6ab8b09d801dcd5f1e56",
        13504803: "4b68b33578063025a63792c05c886b4c9afc63404b65acfb3a80efbc83d83239",
        13504804: "92ddb9a166bfa7dfc90589a6c9e1eca5b9ee1a19c513986d5e965e1565913434",
        13504805: "9e1f7ce48cce6f1a6884c6eb0ff51240e5612019e72110ab45d8a2862fed06f7",
        13504806: "da283ea791eedd9c8614b0fc0ffe2f47df9605e2db5974ba1f383fa4544b51c4",
        13504807: "92732e46e029f2972e87f0c79bdb760122a1e550b399d32d8c8b850951dfb11f",
        13504822: "1a9e8c3cbd4fa43e745ea21632ae4e7927fc1976d4b15ce1d53426af9abd0ce6",
    },
)


@dataclass(frozen=True)
class MariaClericAttachmentIds:
    """Caller-allocated ID for Maria's appended phase-cleanup event.

    The ID is accepted only after a whole-script numeric collision scan.  It is
    intentionally not derived from either map's numeric prefix.
    """

    phase_cleanup_event: int


@dataclass(frozen=True)
class MariaTargetBinding:
    """A verified destination counterpart for Maria's 3500801 event target.

    Static inputs prove that the source health event uses 3500801, but provide
    no MSB placement or source relation for it.  The native writer must supply
    a separately pinned materialization/binding before Maria is selectable.
    """

    source_target: int
    destination_target: int
    provenance: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.source_target != MARIA_EVENT_TARGET:
            raise ValueError("Maria target binding must name source target 3500801")
        if not self.provenance:
            raise ValueError("Maria target binding needs source provenance")


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        actual = blocks.get(event_id)
        if actual is None:
            raise ValueError(f"{role} lacks pinned event {event_id}")
        if hashlib.sha256(actual.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label} is not a unique pinned instruction")
    return text.replace(old, new, 1)


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    # Event parser supplies stable inclusive one-based line spans.
    from .boss_canary import parse_events
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def maria_at_cleric_plan(ids: MariaClericAttachmentIds) -> dict:
    """Describe the required, still-gated Maria -> Cleric attachment."""
    return {
        "format": "bb-maria-contract-v1",
        "status": "blocked-until-event-target-binding",
        "arena": CLERIC_ARENA.key,
        "donor": MARIA_PACKAGE.key,
        "preserved_destination_events": [CLERIC_ARENA.completion_event, CLERIC_ARENA.co_op_entry_event],
        "source_owned_not_copied": [MARIA_ARENA.completion_event, MARIA_ARENA.cutscene_entry_event,
                                      MARIA_ARENA.co_op_restore_event, MARIA_ARENA.host_fog_event,
                                      MARIA_ARENA.guest_fog_event, *MARIA_ARENA.source_reward_flags],
        "attachments": [{"source_event": MARIA_ARENA.phase_cleanup_event,
                         "destination_event": ids.phase_cleanup_event,
                         "initializers": [asdict(x) for x in MARIA_PACKAGE.attachments[0].initializers]}],
        "unresolved": {"source_event_target": MARIA_EVENT_TARGET,
                       "witness": "SetCharacterEventTarget(3500800, 3500801) in 13504802",
                       "reason": "no bundled mined MSB enemy/region placement or other event reference"},
    }


def cleric_at_maria_plan() -> dict:
    """Describe the inverse: Maria terminal/cutscene remain local and untouched."""
    return {
        "format": "bb-maria-contract-v1",
        "status": "requires-append-only-arena-attachment-interface",
        "arena": "lady-maria",
        "donor": CLERIC_PACKAGE.key,
        "preserved_destination_events": [MARIA_ARENA.completion_event, MARIA_ARENA.cutscene_entry_event,
                                           MARIA_ARENA.co_op_restore_event, MARIA_ARENA.host_fog_event,
                                           MARIA_ARENA.guest_fog_event, MARIA_ARENA.health_event,
                                           MARIA_ARENA.music_event, MARIA_ARENA.lockcam_event,
                                           MARIA_ARENA.music_cleanup_event],
        "reason": "generic ArenaContract currently replaces an existing Event(0) anchor; Maria needs append-only initializers for Cleric attachments",
    }


def patch_maria_at_cleric(destination: str, donor_source: str,
                           ids: MariaClericAttachmentIds,
                           target_binding: MariaTargetBinding | None = None) -> str:
    """Build the known Maria/Cleric event overlay, or refuse without 3500801.

    The target binding is intentionally required before any output is emitted:
    omitting Maria's SetCharacterEventTarget relation would silently alter her
    combat AI.  This function is the registry hook once native materialization
    provides the verified binding.
    """
    if target_binding is None:
        raise ValueError("Lady Maria requires a verified binding for unresolved event target 3500801")
    arena, donor = event_blocks(destination), event_blocks(donor_source)
    _verify(arena, CLERIC_ARENA.expected, "Cleric arena")
    _verify(donor, MARIA_PACKAGE.expected, "Lady Maria donor")
    literals = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if ids.phase_cleanup_event in literals:
        raise ValueError("Maria phase-cleanup event ID collides with original Cleric literal")
    # Maria's source uses a cutscene to enable her; no source animation is
    # witnessed. Preserve Cleric geometry/timing but remove only its c5000-only
    # ForceAnimationPlayback instruction.
    activation = _replace_once(arena[CLERIC_ARENA.activation_event],
        "    ForceAnimationPlayback(2410800, 3028, false, false, false);\n", "",
        "Cleric-only entry animation")
    health = _replace_once(arena[CLERIC_ARENA.health_bar_event],
        "DisplayBossHealthBar(Enabled, 2410800, 0, 500000)",
        "DisplayBossHealthBar(Enabled, 2410800, 0, 452000)", "Maria health-bar label")
    health = _replace_once(health, "    SetCharacterAIState(2410800, Enabled);\n",
        "    SetCharacterAIState(2410800, Enabled);\n"
        f"    SetCharacterEventTarget(2410800, {target_binding.destination_target});\n",
        "Maria event-target binding")
    # Source 13504804's 8/10 camera radii are portable; only map/subarea and
    # actor/completion references are adapted to Cleric's declared arena.
    lockcam = donor[MARIA_ARENA.lockcam_event]
    lockcam = lockcam.replace("3500800", "2410800").replace("13501800", "12411700")
    lockcam = lockcam.replace("SetLockcamSlotNumber(35, 0,", "SetLockcamSlotNumber(24, 1,")
    lockcam = lockcam.replace("$Event(13504804,", "$Event(12414704,")
    cleanup = donor[MARIA_ARENA.phase_cleanup_event]
    cleanup = cleanup.replace("3500800", "2410800").replace("13501800", "12411700")
    cleanup = cleanup.replace("$Event(13504822,", f"$Event({ids.phase_cleanup_event},")
    edits = {
        CLERIC_ARENA.activation_event: activation,
        CLERIC_ARENA.health_bar_event: health,
        CLERIC_ARENA.lockcam_event: lockcam,
        12414707: "$Event(12414707, Default, function() {\n    EndEvent();\n});",
        12414708: "$Event(12414708, Default, function() {\n    EndEvent();\n});",
        0: _replace_once(arena[0], "    $InitializeEvent(0, 12414708);",
                         "    $InitializeEvent(0, 12414708);\n"
                         f"    $InitializeEvent(0, {ids.phase_cleanup_event});",
                         "Cleric phase initializer anchor"),
    }
    result = _replace_events(destination, edits).rstrip() + "\n\n" + cleanup + "\n"
    output = event_blocks(result)
    if set(output) != set(arena) | {ids.phase_cleanup_event}:
        raise ValueError("Maria adapter changed unexpected Cleric event identity")
    if output[CLERIC_ARENA.completion_event] != arena[CLERIC_ARENA.completion_event]:
        raise ValueError("Maria adapter changed Cleric completion/progression")
    return result
