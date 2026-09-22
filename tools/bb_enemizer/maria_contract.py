"""Pinned Lady Maria encounter contract and guarded Cleric adapter.

This module deliberately stays outside ``boss_contracts`` while the registry is
being changed.  It uses the same immutable CombatPackage/EventAttachment types
so the registry can import it once its append-only attachment interface is
settled.

Facts are extracted from CUSA03173 AppVer 01.09 in ``research/bb_inputs.db``.
The one unplaced health-routine event target (3500801) is retained as an opaque
literal, with native source/destination absence checks and unobserved status.
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
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

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
class OpaqueExternalReference:
    """Literal preserved without spawning or destination remapping."""
    original_source_id: int
    event_id: int
    witness: str
    evidence_status: str = "inferred"
    runtime_status: str = "unobserved"


MARIA_EVENT_TARGET_REFERENCE = OpaqueExternalReference(
    3500801, 13504802, "SetCharacterEventTarget(3500800, 3500801)")

# Original installed CUSA03173 01.09 patch-layer witnesses. The research bundle
# contains an earlier m35 script. Only these two pinned blocks differ among
# the encounter inputs: Event(0) has unrelated NPC/lift fixes, and health uses
# Forced network authority. Adapters retain the selected source's other text.
MARIA_PATCH_EXPECTED = {
    0: '78d94eb81ed0b21b0f7a14aaaefc5f5ec487d28e3029e8912e6551dd71d2cf50',
    13504802: '5f82a5c49dce37f57f43d2a0ca0542ddc336d8c387cd9bd735f84a2574561dbc',
}


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        actual = blocks.get(event_id)
        if actual is None:
            raise ValueError(f"{role} lacks pinned event {event_id}")
        allowed = {digest}
        if expected is MARIA_PACKAGE.expected and event_id in MARIA_PATCH_EXPECTED:
            allowed.add(MARIA_PATCH_EXPECTED[event_id])
        if hashlib.sha256(actual.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"{label} is not a unique pinned instruction")
    return text.replace(old, new, 1)


def _noop(block: str) -> str:
    """Keep the original event signature so existing initializers still compile."""
    declaration = block[:block.index("{") + 1]
    declaration = re.sub(r'function\(([^)]*)\)', lambda match: 'function(' + ', '.join(
        'unused_' + name.strip() for name in match[1].split(',') if name.strip()) + ')', declaration)
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    # Event parser supplies stable inclusive one-based line spans.
    from .boss_canary import parse_events
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def maria_at_cleric_plan(ids: MariaClericAttachmentIds) -> dict:
    """Describe the experimental Maria -> Cleric attachment."""
    return {
        "format": "bb-maria-contract-v1",
        "status": "experimental",
        "arena": CLERIC_ARENA.key,
        "donor": MARIA_PACKAGE.key,
        "preserved_destination_events": [CLERIC_ARENA.completion_event, CLERIC_ARENA.co_op_entry_event],
        "source_owned_not_copied": [MARIA_ARENA.completion_event, MARIA_ARENA.cutscene_entry_event,
                                      MARIA_ARENA.co_op_restore_event, MARIA_ARENA.host_fog_event,
                                      MARIA_ARENA.guest_fog_event, *MARIA_ARENA.source_reward_flags],
        "attachments": [{"source_event": MARIA_ARENA.phase_cleanup_event,
                         "destination_event": ids.phase_cleanup_event,
                         "initializers": [asdict(x) for x in MARIA_PACKAGE.attachments[0].initializers]}],
        "opaque_external_references": [asdict(MARIA_EVENT_TARGET_REFERENCE)],
        "behavioral_unknown": "3500801 is preserved as an opaque source literal; static effect unobserved",
    }


def cleric_at_maria_plan() -> dict:
    """Describe the inverse: Maria terminal/cutscene remain local and untouched."""
    return {
        "format": "bb-maria-contract-v1",
        "status": "experimental",
        "arena": "lady-maria",
        "donor": CLERIC_PACKAGE.key,
        "preserved_destination_events": [MARIA_ARENA.completion_event, MARIA_ARENA.cutscene_entry_event,
                                           MARIA_ARENA.co_op_restore_event, MARIA_ARENA.host_fog_event,
                                           MARIA_ARENA.guest_fog_event,
                                           MARIA_ARENA.music_event,
                                           MARIA_ARENA.music_cleanup_event],
        "runtime_status": "unobserved",
        "attachments": "Cleric phase, cloth, five limb and five cleanup initializers",
    }


def patch_maria_at_cleric(destination: str, donor_source: str,
                           ids: MariaClericAttachmentIds) -> str:
    """Build experimental Maria/Cleric overlay, retaining opaque 3500801."""
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
        "    SetCharacterEventTarget(2410800, 3500801);\n",
        "opaque Maria event target")
    # Source 13504804's 8/10 camera radii are portable; only map/subarea and
    # actor/completion references are adapted to Cleric's declared arena.
    lockcam = donor[MARIA_ARENA.lockcam_event]
    lockcam = lockcam.replace("3500800", "2410800").replace("13501800", "12411700")
    lockcam = lockcam.replace("SetLockcamSlotNumber(35, 0,", "SetLockcamSlotNumber(24, 1,")
    lockcam = lockcam.replace("$Event(13504804,", "$Event(12414704,")
    cleanup = donor[MARIA_ARENA.phase_cleanup_event]
    cleanup = cleanup.replace("3500800", "2410800").replace("13501800", "12411700")
    cleanup = cleanup.replace("$Event(13504822,", f"$Event({ids.phase_cleanup_event},")
    if arena[0].count("    $InitializeEvent(0, 12414710") != 1 or arena[0].count("    $InitializeEvent(0, 12414720") != 1:
        raise ValueError("Cleric Event(0) limb/cloth initializer witness drift")
    edits = {
        CLERIC_ARENA.activation_event: activation,
        CLERIC_ARENA.health_bar_event: health,
        CLERIC_ARENA.lockcam_event: lockcam,
        12414707: _noop(arena[12414707]),
        12414708: _noop(arena[12414708]),
        12414710: _noop(arena[12414710]),
        12414720: _noop(arena[12414720]),
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


@dataclass(frozen=True)
class ClericMariaAttachmentIds:
    phase: int
    cloth: int
    limbs: int
    limb_cleanup: int


def patch_cleric_at_maria(destination: str, cleric_source: str, ids: ClericMariaAttachmentIds) -> str:
    """Attach Cleric combat while retaining Maria terminal/cutscene/progression."""
    arena, donor = event_blocks(destination), event_blocks(cleric_source)
    _verify(arena, MARIA_PACKAGE.expected, "Maria arena")
    _verify(donor, CLERIC_PACKAGE.expected, "Cleric donor")
    values = {int(x) for x in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    mapping = {12414707: ids.phase, 12414708: ids.cloth, 12414710: ids.limbs, 12414720: ids.limb_cleanup}
    if len(set(mapping.values())) != 4 or values.intersection(mapping.values()):
        raise ValueError("Cleric/Maria attachment ID collides with Maria original literal")
    calls = []
    for line in donor[0].splitlines():
        matched = re.match(r"(\s*\$InitializeEvent\([^,]+,\s*)(12414707|12414708|12414710|12414720)(.*)", line)
        if matched:
            calls.append(matched[1] + str(mapping[int(matched[2])]) + matched[3])
    if len(calls) != 12 or sum("12414710" in x for x in donor[0].splitlines()) != 5 or sum("12414720" in x for x in donor[0].splitlines()) != 5:
        raise ValueError("Cleric Event(0) lacks exact twelve attachment initializer witnesses")
    def remap(block: str, old: int, new: int) -> str:
        return re.sub(r"(?<![\w])-?\d+(?![\w])", lambda m: str({2410800:3500800,12411700:13501800,old:new}.get(int(m[0]),int(m[0]))), block).replace(f"$Event({old},",f"$Event({new},")
    health = _replace_once(arena[13504802], "DisplayBossHealthBar(Enabled, 3500800, 0, 452000)",
                           "DisplayBossHealthBar(Enabled, 3500800, 0, 500000)", "Cleric health label")
    health = _replace_once(health, "    SetCharacterEventTarget(3500800, 3500801);\n", "", "Maria-only event target")
    lockcam = remap(donor[12414704], 12414704, 13504804).replace("SetLockcamSlotNumber(24, 1,", "SetLockcamSlotNumber(35, 0,")
    init = _replace_once(arena[0], "    $InitializeEvent(0, 13504822);",
                         "    $InitializeEvent(0, 13504822);\n" + "\n".join(calls), "Maria append anchor")
    edits={0:init,13504802:health,13504804:lockcam,13504822:_noop(arena[13504822])}
    out=_replace_events(destination,edits).rstrip()+"\n\n"+"\n\n".join(remap(donor[e],e,n) for e,n in mapping.items())+"\n"
    result=event_blocks(out)
    if result[13501800]!=arena[13501800] or result[13501801]!=arena[13501801]:
        raise ValueError("Cleric-at-Maria changed Maria terminal/cutscene")
    return out


def native_plan_maria_at_cleric(slots: list[Slot], npcs: Mapping[int, dict], effects: Mapping[int, dict], ids: MariaClericAttachmentIds, seed: str) -> dict:
    cleric=[s for s in slots if s.entity_id==2410800 and s.archetype==CLERIC_ARENA.archetype]
    maria=[s for s in slots if s.entity_id==3500800 and s.archetype==MARIA_PACKAGE.archetype]
    if len(cleric) != 3 or len(maria) != 1 or any(slot.talk_id != 0 or slot.archetype.chara_init_id != 0 for slot in cleric):
        raise ValueError("Maria plan requires all three exact original Cleric states and one Maria part")
    target,source=cleric[0],maria[0]
    swap=Swap(target.logical_key,[slot.key for slot in cleric],{slot.key:slot.archetype for slot in cleric},target.archetype,source.archetype,destinations={slot.key:{"map_name":slot.map_name,"entity_id":slot.entity_id,"x":slot.x,"y":slot.y,"z":slot.z} for slot in cleric})
    changes,skips=plan_scaling([swap],cleric,dict(npcs),dict(effects))
    return {"format":"bb-enemizer-plan-v2","dry_run":True,"seed":seed,"swap_count":1,"swaps":[swap.json()],"boss_contract":maria_at_cleric_plan(ids),"primary_init_source_bindings":[{"source_map":source.map_name,"source_part":source.part_name,"source_entity_id":source.entity_id,"source_archetype":asdict(source.archetype),"source_talk_id":source.talk_id,"destination_map":slot.map_name,"destination_part":slot.part_name,"destination_entity_id":slot.entity_id,"required_native_fields":["talk_id","unk_t18","init_anim_id","damage_anim_id","provenance"]} for slot in cleric],"scaling":{"enabled":bool(changes),"mechanism":"inferred_static_npc_clone_sp_effect","change_count":len(changes),"changes":[x.json() for x in changes],"skip_count":len(skips),"skips":skips}}



def native_plan_cleric_at_maria(slots: list[Slot], npcs: Mapping[int, dict], effects: Mapping[int, dict],
                                ids: ClericMariaAttachmentIds, seed: str) -> dict:
    """v2 native plan for Cleric combat in Maria's progression-owned arena."""
    maria = [s for s in slots if s.entity_id == 3500800 and s.archetype == MARIA_PACKAGE.archetype]
    cleric = [s for s in slots if s.entity_id == 2410800 and s.archetype == CLERIC_ARENA.archetype]
    if len(maria) != 1 or len(cleric) != 3 or any(slot.talk_id != 0 or slot.archetype.chara_init_id != 0 for slot in cleric):
        raise ValueError("Cleric/Maria plan requires exact Maria and all three original Cleric states")
    target, source = maria[0], next(slot for slot in cleric if slot.map_name == "m24_01_00_00")
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype}, target.archetype,
                source.archetype, destinations={target.key: {"map_name": target.map_name,
                "entity_id": target.entity_id, "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects))
    return {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed, "swap_count": 1,
            "swaps": [swap.json()],
            "boss_contract": {"format": "bb-maria-contract-v1", "arena": "lady-maria",
                              "donor": "cleric-beast", "patch": "cleric-at-maria",
                              "attachment_event_ids": asdict(ids),
                              "preserved_destination_events": [13501800, 13501801, 13501807],
                              "source_initialization": "native writer must populate exact original-MSB pin"},
            "primary_init_source_bindings": [{"source_event_file": "event/m24_01_00_00.emevd.dcx.js", "source_map": source.map_name,
                "source_part": source.part_name, "source_entity_id": source.entity_id,
                "source_archetype": asdict(source.archetype), "source_talk_id": source.talk_id,
                "destination_map": target.map_name, "destination_part": target.part_name,
                "destination_entity_id": target.entity_id,
                "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"]}],
            "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                "change_count": len(changes), "changes": [c.json() for c in changes],
                "skip_count": len(skips), "skips": skips}}
