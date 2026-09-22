"""Pinned Cleric Beast combat adapter for Laurence's destination arena.

The Laurence terminal, fog gate, item/key entry condition, cutscene and rewards
stay owned by m34.  Cleric combat replaces only the one-actor combat routines.
This is static source/build evidence; arena fit remains unobserved.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .boss_contracts import CLERIC_PACKAGE
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m34_00_00_00.emevd.dcx.js"
LAURENCE = 3400850
LAURENCE_ARCHETYPE = Archetype("c4500", 450000, 450000, 0)
LAURENCE_COMPLETION = 13401850
LAURENCE_START = 13404858
LAURENCE_HEALTH = 13404852
LAURENCE_MUSIC = 13404853
LAURENCE_CAMERA = 13404854

# These are all destination bodies whose role is preserved or adapted.  The
# source routine pins deliberately name every copied Cleric routine too.
LAURENCE_ARENA_HASHES = {
    0: "3772e9c2957d38bcdbc984631dab0033deaef57c1d092a8c77005cdd4d7c1d55",
    13401800: "15c6ba33b2df44b9fdc67ea470d1f32281bac11a588ba6c876de7ac85df5d8dd",
    13401850: "dc390d680718c54d8a214a4d1ed0def18b7c110df7dd19a6862b436a2dcd6b44",
    13401851: "c9bb7c19e16ebdc391bc1552e9328dd41d25bdc968701b2e1182506f940f255d",
    13404820: "2a1075a99453bacb20f94e697137fe830eb2507ffcf74699ad7707ad62671c14",
    13404821: "a650abcf1dca7030d8d39eb944ef5e3c1ba0a9665dfb4fc8f9fbf3c82280e8bf",
    13404822: "ae620a8fe09a2614d36cc0714743fac5f2e9f7bd7fb888c78fdb738910250968",
    13404823: "3fd2cc74e5e8cf9ed1da11cea82f3244c1228bc4224b1a280431a4a64b519292",
    13404824: "19b82e96f8a880da845bf09c977b9d116da91584069edb0a3f630271ae119c70",
    13404825: "b64ae6b68f0a7dc4d922328fa23659be54219fd7010465f03493a141858e16f2",
    13404852: "a55956b498c3908a0febf99daf2013e6d59eea5885a5ac837a3735f09d356470",
    13404853: "6d373eb2995d299bd4008cbc5c7fa72a0d77823ed62129af6916a4ad0235ce7a",
    13404854: "67283d0f1600a008235ffc109219ab98ee5028814738d45724c397bf4519430f",
    13404861: "7888497bc33ab25bdc668813a50cbc6a3ad44c2d6321b05fecdf4c500a297f7e",
    13404870: "237a55077776ca3b72ea95aee40b8da9655bf8f93d15315400b3d1f1eb8471be",
    13404875: "e5fb7120dd1c7759f763c39f7c04a1b01ba966dcb2ce48f9bc4f5e1331a57822",
}
CLERIC_SOURCE_EVENTS = (0, 12411700, 12411702, 12414702, 12414703, 12414704,
                        12414707, 12414708, 12414710, 12414720)
CLERIC_SOURCE_HASHES = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    12411700: "32fd5783fae1fcd587800a13729ad608926b9f59b958a29992393b0c486780c9",
    12411702: "702380b92bd2632ce4ff9527009f8c7209fffff89297bc38d8fb8d108655eaff",
    12414702: "026c305969b19114cc2f678e6d3859542442b35764b658ccfe65c3cb7fe7d422",
    12414703: "115ae8dc85c184a4dfe729eaef337b01ea0bcffc7a34ec0dde3f343dcbeb5c14",
    12414704: "ce143b924eb991b092351eb7641c7ea8349c28296209618f629b3b7c8ac02caa",
    12414707: "196e29870aae5dab2604594ce9ff0047b2ad71294fec48b6aa56c9f87465f73e",
    12414708: "2565484fb6afa230b46708bce4f42e8088d0f062fbafdb50453e078fc2fbf14d",
    12414710: "da624a8c97354a1208ce15fb1619bcb7f21aa74e89e39d22bfe4edac45c2373d",
    12414720: "1196a612c8f3b4d47e502e52fcbd848c9efe3be859b2b25e934e240c210099ea",
}
@dataclass(frozen=True)
class LaurenceClericIds:
    """Project-owned slots for Cleric phase routines in m34's shared script."""

    phase: int
    cloth_phase: int

    def values(self) -> tuple[int, int]:
        return self.phase, self.cloth_phase


DEFAULT_IDS = LaurenceClericIds(12990500, 12990501)


CLERIC_DESTINATION_EVENTS = {
    12414710: 13404870, 12414720: 13404875,
}


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str], role: str) -> None:
    for event_id, digest in expected.items():
        body = blocks.get(event_id)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != digest:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Laurence arena expected one {label}")
    return text.replace(old, new, 1)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        item.strip() if item.strip().startswith("unused_") else "unused_" + item.strip()
        for item in match[1].split(",") if item.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap_cleric(block: str, source_event: int, destination_event: int) -> str:
    mapping = {
        CLERIC_PACKAGE.actor: LAURENCE,
        CLERIC_PACKAGE.completion_event: LAURENCE_COMPLETION,
        source_event: destination_event,
    }
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(mapping.get(int(match[0]), int(match[0]))), block)


def _remap_cleric_camera(block: str) -> str:
    camera = _remap_cleric(block, 12414704, LAURENCE_CAMERA)
    old, new = "SetLockcamSlotNumber(24, 1,", "SetLockcamSlotNumber(34, 0,"
    if camera.count(old) != 2:
        raise ValueError("Laurence arena expected two Cleric camera map bindings")
    return camera.replace(old, new)


def _initializer_calls(event_zero: str, event_id: int, count: int) -> list[str]:
    calls = [line for line in event_zero.splitlines()
             if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(event_id) + r"(?:,|\))", line)]
    if len(calls) != count:
        raise ValueError(f"Cleric Event(0) lacks {count} initializer witnesses for {event_id}")
    return calls


def _remap_initializer(line: str, source_event: int, destination_event: int) -> str:
    return re.sub(r"(\$InitializeEvent\([^,]+,\s*)" + str(source_event) + r"(?=,|\))",
                  r"\g<1>" + str(destination_event), line, count=1)


def _replace_initializer_group(event_zero: str, destination_event: int,
                               replacement: Sequence[str], expected_count: int) -> str:
    lines = event_zero.splitlines()
    positions = [index for index, line in enumerate(lines)
                 if re.match(r"\s*\$InitializeEvent\([^,]+,\s*" + str(destination_event) + r"(?:,|\))", line)]
    if len(positions) != expected_count:
        raise ValueError(f"Laurence Event(0) lacks {expected_count} initializer witnesses for {destination_event}")
    first = positions[0]
    for index in reversed(positions):
        del lines[index]
    lines[first:first] = replacement
    return "\n".join(lines)


def _all_original_numbers() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])",
                                                         body.decode("utf-8-sig")))
    return values


def _require_ids(ids: LaurenceClericIds, destination: str) -> None:
    values = ids.values()
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError("Laurence/Cleric IDs must be unique positive project-owned IDs")
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if set(values) & local or set(values) & _all_original_numbers():
        raise ValueError("Laurence/Cleric ID collides with an original EMEVD literal")


def _constructor(destination_zero: str, cleric_zero: str, ids: LaurenceClericIds) -> str:
    phase = [_remap_initializer(line, 12414707, ids.phase)
             for line in _initializer_calls(cleric_zero, 12414707, 1)]
    cloth_phase = [_remap_initializer(line, 12414708, ids.cloth_phase)
                   for line in _initializer_calls(cleric_zero, 12414708, 1)]
    limbs = [_remap_initializer(line, 12414710, 13404870)
             for line in _initializer_calls(cleric_zero, 12414710, 5)]
    cloth = [_remap_initializer(line, 12414720, 13404875)
             for line in _initializer_calls(cleric_zero, 12414720, 5)]
    result = _replace_initializer_group(destination_zero, 13404870, limbs, 5)
    result = _replace_initializer_group(result, 13404875, cloth, 1)
    anchor = "    $InitializeEvent(0, 13401853);"
    return _replace_once(result, anchor, "\n".join((*phase, *cloth_phase, anchor)),
                         "Laurence post-limb initializer anchor")


def patch_cleric_at_laurence(destination: str, cleric_source: str,
                              ids: LaurenceClericIds = DEFAULT_IDS) -> str:
    """Replace Laurence combat while retaining the m34 terminal and fog flow."""
    arena, donor = event_blocks(destination), event_blocks(cleric_source)
    _verify(arena, LAURENCE_ARENA_HASHES, "Laurence arena")
    _verify(donor, CLERIC_SOURCE_HASHES, "Cleric donor")
    _require_ids(ids, destination)
    activation = _replace_once(arena[13404861],
        "    ForceAnimationPlayback(3400850, 7002, true, false, false);\n", "",
        "Laurence-only pre-entry animation")
    entry = _replace_once(arena[13401851],
        "ForceAnimationPlayback(3400850, 3029, false, false, false);",
        "ForceAnimationPlayback(3400850, 3028, false, false, false);",
        "Cleric entry animation")
    health = _replace_once(arena[LAURENCE_HEALTH],
        "DisplayBossHealthBar(Enabled, 3400850, 0, 450000)",
        "DisplayBossHealthBar(Enabled, 3400850, 0, 500000)", "Cleric health-bar label")
    music = _replace_once(arena[LAURENCE_MUSIC], "CharacterHasEventMessage(3400850, 400)",
                          "CharacterHasEventMessage(3400850, 100)", "Cleric phase music message")
    edits = {
        0: _constructor(arena[0], donor[0], ids),
        13401851: entry,
        13404861: activation,
        LAURENCE_HEALTH: health,
        LAURENCE_MUSIC: music,
        LAURENCE_CAMERA: _remap_cleric_camera(donor[12414704]),
        13404870: _remap_cleric(donor[12414710], 12414710, 13404870),
        13404875: _remap_cleric(donor[12414720], 12414720, 13404875),
    }
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join((
        _remap_cleric(donor[12414707], 12414707, ids.phase),
        _remap_cleric(donor[12414708], 12414708, ids.cloth_phase),
    )) + "\n"
    output = event_blocks(result)
    if set(output) != set(arena) | set(ids.values()):
        raise ValueError("Laurence arena contract changed event identities")
    for event_id, original in arena.items():
        if event_id not in edits and output[event_id] != original:
            raise ValueError(f"Laurence arena contract changed unrelated event {event_id}")
    if output[13401800] != arena[13401800] or output[LAURENCE_COMPLETION] != arena[LAURENCE_COMPLETION]:
        raise ValueError("Laurence arena contract changed destination completion progression")
    return result


def native_plan_cleric_at_laurence(slots: Sequence[Slot], npcs: Mapping[int, dict],
                                    effects: Mapping[int, dict], seed: str,
                                    ids: LaurenceClericIds = DEFAULT_IDS) -> dict:
    """Plan the one canonical Cleric state over Laurence's single m34 part."""
    cleric = [slot for slot in slots if slot.entity_id == CLERIC_PACKAGE.actor
              and slot.archetype == CLERIC_PACKAGE.archetype]
    laurence = [slot for slot in slots if slot.entity_id == LAURENCE
                and slot.archetype == LAURENCE_ARCHETYPE]
    expected_states = {"m24_01_00_00", "m24_01_00_01", "m24_01_00_11"}
    if (len(cleric) != 3 or len(laurence) != 1 or {slot.map_name for slot in cleric} != expected_states
            or any(slot.talk_id != 0 for slot in cleric) or laurence[0].map_name != "m34_00_00_00"):
        raise ValueError("Laurence arena requires pinned Cleric states and one Laurence destination")
    source = next(slot for slot in cleric if slot.map_name == "m24_01_00_00")
    target = laurence[0]
    swap = Swap(target.logical_key, [target.key], {target.key: target.archetype},
                target.archetype, CLERIC_PACKAGE.archetype,
                destinations={target.key: {"map_name": target.map_name, "entity_id": target.entity_id,
                                           "x": target.x, "y": target.y, "z": target.z}})
    changes, skips = plan_scaling([swap], [target], dict(npcs), dict(effects), boss_tiers=True)
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-cleric-laurence-contract-v1", "arena": "laurence", "donor": "cleric-beast",
            "preserved_destination_events": [13401800, LAURENCE_COMPLETION],
            "event_bindings": {12414707: ids.phase, 12414708: ids.cloth_phase,
                               **CLERIC_DESTINATION_EVENTS},
            "health_bar": {"event": LAURENCE_HEALTH, "label": 500000,
                           "evidence": "literal DisplayBossHealthBar operand in Cleric event 12414702"},
            "runtime_status": "unobserved arena fit",
        },
        "primary_init_source_bindings": [{
            "source_map": source.map_name, "source_part": source.part_name,
            "source_entity_id": source.entity_id, "source_archetype": asdict(source.archetype),
            "source_talk_id": source.talk_id,
            "destination_map": target.map_name, "destination_part": target.part_name,
            "destination_entity_id": target.entity_id, "destination_original_talk_id": target.talk_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
        }],
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }
