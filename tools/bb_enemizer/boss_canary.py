"""Experimental BSB-at-Cleric encounter adapter, CUSA03173 AppVer 01.09.

The event IDs and operands below come from the original bundled EMEVD.
The adapter reuses destination-owned model events; it allocates no new flags.
Runtime entrance, phases, arena fit and AP completion still need a canary.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict

from .bosses import parse_events
from .model import Archetype, Swap
from .scaling import plan_scaling

ADAPTER = "bsb-at-cleric-v1"
DESTINATION_EVENT_FILE = "m24_01_00_00.emevd.dcx"
DONOR_EVENT_FILE = "m23_00_00_00.emevd.dcx"
COMPLETION_EVENT = 12411700
DESTINATION_ENTITY = 2410800
DONOR_ENTITY = 2300800
# SHA256 of LF-normalized event declarations/bodies from the original corpus;
# also matched linked DarkScript3 3.6.3 decompilation of the owner's binaries.
EXPECTED = {
    12411701: "ce9e3a27e03bd6a68e1806bb208399ebdebed99aec3dad7b9903df5bce5bf1cf",
    12411702: "702380b92bd2632ce4ff9527009f8c7209fffff89297bc38d8fb8d108655eaff",
    12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
    12414703: "115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14",
    12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
    12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
    12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
    12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
    12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
    12304807: "7e9c22292f41da758876cceffe70b61ad51cf0f86e7b5e250e3c8514f179d780",
    12304808: "8ccea02a7829f43788cf77ec24ea5b524643f9ab6d55681f492f1afa588e31f5",
}
CHANGED_EVENTS = sorted(key for key in EXPECTED if str(key).startswith("124"))


def event_blocks(text: str) -> dict[int, str]:
    lines = text.splitlines()
    events = parse_events(text)
    if len({e.event_id for e in events}) != len(events):
        raise ValueError("duplicate event definition")
    return {e.event_id: "\n".join(lines[e.first_line - 1:e.last_line]) for e in events}


def _once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("adapter expected exactly one instruction: " + old)
    return text.replace(old, new, 1)


def patch_event_source(destination: str, donor: str) -> str:
    original, source = event_blocks(destination), event_blocks(donor)
    for event_id, expected in EXPECTED.items():
        block = (source if event_id < 12400000 else original).get(event_id, "")
        if hashlib.sha256(block.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"unsupported original boss event {event_id}")
    edits = {event_id: original[event_id] for event_id in CHANGED_EVENTS}
    edits[12411701] = _once(edits[12411701], "500099999", "0")  # donor death cue
    entry = edits[12411702]
    for instruction in (
        "    SetCharacterGravity(2410800, Disabled);\n",
        "    SetCharacterMaphits(2410800, true);\n",
        "    IssueShortWarpRequest(2410800, TargetEntityType.Area, 2412831, -1);\n",
        "    WaitFixedTimeFrames(110);\n",
    ):
        entry = _once(entry, instruction, "")
    edits[12411702] = _once(entry, "ForceAnimationPlayback(2410800, 3028,", "ForceAnimationPlayback(2410800, 7001,")
    edits[12414702] = _once(edits[12414702], "DisplayBossHealthBar(Enabled, 2410800, 0, 500000)",
                            "DisplayBossHealthBar(Enabled, 2410800, 0, 209000)")
    edits[12414703] = _once(edits[12414703], "CharacterHasEventMessage(2410800, 100)", "EventFlag(12414707)")
    edits[12414704] = "$Event(12414704, Default, function() {\n    SetNetworkSyncState(Disabled);\n    SetLockcamSlotNumber(24, 1, 0);\n    EndEvent();\n});"
    remap = {2300800: 2410800, 12301800: 12411700, 12304807: 12414707, 12304808: 12414708}
    for before, after in ((12304807, 12414707), (12304808, 12414708)):
        edits[after] = re.sub(r"(?<![\w])-?\d+(?![\w])", lambda m: str(remap.get(int(m[0]), int(m[0]))), source[before])
    for event_id in (12414710, 12414720):
        declaration = edits[event_id].splitlines()[0]
        declaration = re.sub(r"function\(([^)]*)\)", lambda m: "function(" + ", ".join(
            "unused_" + name.strip() for name in m[1].split(",")
        ) + ")", declaration)
        edits[event_id] = declaration + "\n    EndEvent();\n});"
    lines = destination.splitlines()
    for event in reversed(parse_events(destination)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    result = "\n".join(lines) + "\n"
    output = event_blocks(result)
    if original.keys() != output.keys():
        raise ValueError("boss adapter changed event identity set")
    for event_id in original:
        if event_id not in edits and original[event_id] != output[event_id]:
            raise ValueError(f"boss adapter touched unrelated event {event_id}")
    if output[COMPLETION_EVENT] != original[COMPLETION_EVENT]:
        raise ValueError("boss adapter changed destination progression event")
    return result


def plan_canary(slots, npcs, effects) -> dict:
    destinations = sorted((slot for slot in slots if slot.entity_id == DESTINATION_ENTITY
                           and slot.map_name.startswith("m24_01_")), key=lambda slot: slot.key)
    donors = [slot for slot in slots if slot.entity_id == DONOR_ENTITY and slot.map_name.startswith("m23_00_")]
    expected_source = Archetype("c5000", 500241, 500241, 0)
    expected_donor = Archetype("c2090", 209000, 209000, 0)
    if len(destinations) != 3 or not donors or any(s.archetype != expected_source for s in destinations) or any(s.archetype != expected_donor for s in donors):
        raise ValueError("unsupported boss placement provenance")
    if len({s.logical_key for s in destinations}) != 1 or any(s.dummy or s.talk_id or s.archetype.chara_init_id for s in destinations + donors):
        raise ValueError("boss adapter requires ordinary non-talk-bound actor placements")
    swap = Swap(destinations[0].logical_key, [s.key for s in destinations],
                {s.key: s.archetype for s in destinations}, expected_source, expected_donor,
                warnings=["experimental boss adapter; entrance, phases and AP completion require live validation"],
                destinations={s.key: {"map_name": s.map_name, "entity_id": s.entity_id,
                                     "x": s.x, "y": s.y, "z": s.z} for s in destinations})
    changes, skips = plan_scaling([swap], destinations, npcs, effects)
    if len(changes) != 1 or skips:
        raise ValueError("boss canary requires an applicable normalization clone")
    return {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": ADAPTER,
            "swap_count": 1, "swaps": [swap.json()], "options": {"experimental_boss_adapter": ADAPTER},
            "boss_adapter": ADAPTER, "required_event_overlay": "dvdroot_ps4/event/" + DESTINATION_EVENT_FILE,
            "scaling": {"enabled": True, "mechanism": "inferred_static_npc_clone_sp_effect",
                        "change_count": 1, "changes": [asdict(change) for change in changes], "skip_count": 0, "skips": []}}
