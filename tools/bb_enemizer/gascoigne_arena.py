"""Pinned Cleric Beast combat overlay for Father Gascoigne's arena.

Gascoigne's OR-death terminal, cutscene, fog, rewards and progression remain
destination-owned.  The human actor becomes Cleric Beast; the unused beast
actor is disabled but deliberately remains alive until *after* the original
terminal completes, because killing it early satisfies the destination OR
predicate and would award an immediate victory.

This is an offline construction contract.  Arena fit and runtime behavior are
not established by source/compile validation.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob, read_prefix

from .boss_canary import event_blocks
from .boss_contracts import CLERIC_ARENA, CLERIC_PACKAGE
from .bosses import parse_events
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

BUNDLE = Path(__file__).resolve().parents[2] / "research" / "bb_inputs.db"
EVENT_FILE = "m24_01_00_00.emevd.dcx.js"
MAP_PREFIX = "m24_01_"
GASCOIGNE_HUMAN = 2410810
GASCOIGNE_BEAST = 2410811
GASCOIGNE_ARCHETYPE = Archetype("c2710", 271000, 271000, 0)


@dataclass(frozen=True)
class ClericGascoigneIds:
    """Explicit project-owned event identities for copied Cleric routines."""

    phase: int
    cloth_phase: int
    limbs: int
    cloth: int
    beast_cleanup: int

    def values(self) -> tuple[int, ...]:
        return self.phase, self.cloth_phase, self.limbs, self.cloth, self.beast_cleanup


# The terminal and entry/cutscene are pins, not candidates for a generic
# completion adapter.  Every body that moves or is suppressed is also pinned.
GASCOIGNE_ARENA_HASHES = {
    0: "329450dd4b8ae967cdaf56f5ab65556bb0a453e8f8374d79328848dff72cf89c",
    # The committed corpus and the effective installed patch differ only in
    # this terminal body. Both exact pins are accepted; the adapter retains
    # the selected body byte-for-byte.
    12411800: ("b1a11b96d57174d9b9636387fa25c631ca8a1469e55297a602e9c58875c204a0",
              "c6eb236fba9e48406dd9088747c3d54bc054784718a67305da498934c2c98b9c"),
    12411802: "f803bd5dfa427d7e8e80ed46fe4f346973ad5c9ae090d481c005d4bff10eba78",
    12414802: "3a8b68b527fc00ad30fc5561c9a64f881ee9708db2d506dd04d986458e6f17a2",
    12414803: "a6b50e5c86a3b2471166de37c25da11361053e96065b263c7220913f79399150",
    12414804: "039705347b21101bf2d6309ee55595559ff21f4a6a4be4e7cd6bc622783586c7",
    12414807: "7f72ec81a9ce98a3e41792eace02ad700a0420e9b2dfabc009b4641927c3de1e",
    12414808: "60c1f7f7ecbdf2f5cd1e0654f928a1cfcf36abd795523c3c766c4c95290fff15",
    12414809: "54c7fe426f39a828b938c14d6201fa53d9ab4b7f4e83c0d382b33c92d256a938",
}
CLERIC_SOURCE_EVENTS = (12414707, 12414708, 12414710, 12414720)


def _verify(blocks: Mapping[int, str], expected: Mapping[int, str | tuple[str, ...]], role: str) -> None:
    for event_id, digest in expected.items():
        body = blocks.get(event_id)
        allowed = (digest,) if isinstance(digest, str) else digest
        if body is None or hashlib.sha256(body.encode()).hexdigest() not in allowed:
            raise ValueError(f"unsupported original {role} event {event_id}")


def _replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Gascoigne arena contract expected one {label}")
    return text.replace(old, new, 1)


def _end_event(block: str) -> str:
    declaration = block.splitlines()[0]
    declaration = re.sub(r"function\(([^)]*)\)", lambda match: "function(" + ", ".join(
        value.strip() if value.strip().startswith("unused_") else "unused_" + value.strip()
        for value in match[1].split(",") if value.strip()) + ")", declaration)
    return declaration + "\n    EndEvent();\n});"


def _replace_events(source: str, edits: Mapping[int, str]) -> str:
    lines = source.splitlines()
    for event in reversed(parse_events(source)):
        if event.event_id in edits:
            lines[event.first_line - 1:event.last_line] = edits[event.event_id].splitlines()
    return "\n".join(lines) + "\n"


def _remap_cleric(block: str, source_event: int, destination_event: int) -> str:
    """Map only Cleric actor/completion/event identifiers in copied combat code."""
    remap = {CLERIC_PACKAGE.actor: GASCOIGNE_HUMAN,
             CLERIC_PACKAGE.completion_event: 12411800,
             source_event: destination_event}
    return re.sub(r"(?<![\w])-?\d+(?![\w])",
                  lambda match: str(remap.get(int(match[0]), int(match[0]))), block)


def _all_original_numbers() -> set[int]:
    values: set[int] = set()
    for body in read_prefix(BUNDLE, "event/").values():
        values.update(int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])",
                                                         body.decode("utf-8-sig")))
    return values


def _require_ids(ids: ClericGascoigneIds, destination: str) -> None:
    values = ids.values()
    if any(value <= 0 for value in values) or len(set(values)) != len(values):
        raise ValueError("Cleric/Gascoigne IDs must be unique positive project-owned IDs")
    local = {int(value) for value in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if set(values) & local:
        raise ValueError("Cleric/Gascoigne ID collides with original Gascoigne literal")
    if set(values) & _all_original_numbers():
        raise ValueError("Cleric/Gascoigne ID collides with original EMEVD corpus")


def _cleric_initializers(event_zero: str, ids: ClericGascoigneIds) -> list[str]:
    mapping = {12414707: ids.phase, 12414708: ids.cloth_phase,
               12414710: ids.limbs, 12414720: ids.cloth}
    calls: list[str] = []
    for line in event_zero.splitlines():
        match = re.match(r"(\s*\$InitializeEvent\([^,]+,\s*)(12414707|12414708|12414710|12414720)(.*)", line)
        if match:
            calls.append(match[1] + str(mapping[int(match[2])]) + match[3])
    if len(calls) != 12 or sum("12414710" in line for line in event_zero.splitlines()) != 5 \
            or sum("12414720" in line for line in event_zero.splitlines()) != 5:
        raise ValueError("Cleric Event(0) lacks exact twelve initializer witnesses")
    return calls


def _gascoigne_health() -> str:
    """Exact single-actor replacement for Gascoigne's paired health routine."""
    return '''$Event(12414802, Default, function() {
    EndIf(EventFlag(12411800));
    SetCharacterAIState(2410810, Disabled);
    SetCharacterHPBarDisplay(2410810, Disabled);
    if (!ThisEvent()) {
        WaitFor(EventFlag(12414800));
        if (!HasMultiplayerState(MultiplayerState.Client)) {
            if (!EventFlag(12414223)) {
                IssueBossRoomEntryNotification(0);
            }
            SetNetworkUpdateAuthority(2410810, AuthorityLevel.Forced);
        }
    }
L0:
    SetEventFlag(12414223, ON);
    SetEventFlag(12414800, ON);
    GotoIf(L1, NumberOfCoopClients() == 0);
    GotoIf(L2, NumberOfCoopClients() == 1);
    GotoIf(L3, NumberOfCoopClients() == 2);
L1:
    Goto(L4);
L2:
    SetSpEffect(2410810, 7500, true);
    WaitFixedTimeFrames(1);
    AdaptHpchangingSpEffectToNPCPartOfTarget(2410810);
    Goto(L4);
L3:
    SetSpEffect(2410810, 7501, true);
    WaitFixedTimeFrames(1);
    AdaptHpchangingSpEffectToNPCPartOfTarget(2410810);
    Goto(L4);
L4:
    SetCharacterAIState(2410810, Enabled);
    DisplayBossHealthBar(Enabled, 2410810, 0, 500000);
    CreatePlaylog(80);
    StartTimeMeasurement(2410010, 96, Enabled);
});'''


def _beast_cleanup(ids: ClericGascoigneIds) -> str:
    """Disable the unused phase actor without satisfying Gascoigne's OR death."""
    return f'''$Event({ids.beast_cleanup}, Restart, function() {{
    ChangeCharacterEnableState(2410811, Disabled);
    EndIf(EventFlag(12411800));
    WaitFor(EventFlag(12411800));
    ChangeCharacterEnableState(2410811, Disabled);
    ForceCharacterDeath(2410811, false);
}});'''


def patch_cleric_at_gascoigne(destination: str, cleric_source: str,
                              ids: ClericGascoigneIds) -> str:
    """Attach Cleric combat to Gascoigne's untouched OR-death progression."""
    arena, donor = event_blocks(destination), event_blocks(cleric_source)
    _verify(arena, GASCOIGNE_ARENA_HASHES, "Gascoigne arena")
    _verify(donor, {event: CLERIC_PACKAGE.expected[event] for event in (0, *CLERIC_SOURCE_EVENTS)},
            "Cleric donor")
    _require_ids(ids, destination)
    calls = _cleric_initializers(donor[0], ids)
    anchor = "    $InitializeEvent(0, 12414809);"
    constructor = _replace_once(arena[0], anchor,
                                anchor + "\n" + "\n".join(calls)
                                + f"\n    $InitializeEvent(0, {ids.beast_cleanup});",
                                "Gascoigne phase initializer anchor")
    music = _replace_once(arena[12414803], "flagArea2 &= EventFlag(12414807);",
                          "flagArea2 &= CharacterHasEventMessage(2410810, 100);",
                          "Cleric phase music trigger")
    mapping = {12414707: ids.phase, 12414708: ids.cloth_phase,
               12414710: ids.limbs, 12414720: ids.cloth}
    edits: dict[int, str] = {
        0: constructor,
        12414802: _gascoigne_health(),
        12414803: music,
        12414807: _end_event(arena[12414807]),
        12414808: _end_event(arena[12414808]),
        12414809: _end_event(arena[12414809]),
    }
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(
        _remap_cleric(donor[source], source, target) for source, target in mapping.items()) \
        + "\n\n" + _beast_cleanup(ids) + "\n"
    output = event_blocks(result)
    added = set(ids.values())
    if set(output) != set(arena) | added:
        raise ValueError("Cleric/Gascoigne adapter changed unexpected event identities")
    for event_id, original in arena.items():
        if event_id not in edits and output[event_id] != original:
            raise ValueError(f"Cleric/Gascoigne adapter changed unrelated arena event {event_id}")
    if output[12411800] != arena[12411800] or output[12411802] != arena[12411802]:
        raise ValueError("Cleric/Gascoigne adapter changed terminal or cutscene progression")
    return result


def native_plan_cleric_at_gascoigne(slots: Sequence[Slot], npcs: Mapping[int, dict],
                                    effects: Mapping[int, dict], ids: ClericGascoigneIds,
                                    seed: str) -> dict:
    """Plan a primary Cleric tuple import over the existing Gascoigne human."""
    cleric = [slot for slot in slots if slot.entity_id == CLERIC_PACKAGE.actor
              and slot.archetype == CLERIC_PACKAGE.archetype and slot.map_name.startswith(MAP_PREFIX)]
    human = [slot for slot in slots if slot.entity_id == GASCOIGNE_HUMAN
             and slot.archetype == GASCOIGNE_ARCHETYPE and slot.map_name.startswith(MAP_PREFIX)]
    if (len(cleric) != 3 or len(human) != 3 or any(slot.talk_id != 0 for slot in cleric)
            or any(slot.talk_id != 241330 for slot in human)):
        raise ValueError("Cleric/Gascoigne plan requires all pinned Cleric and human map states")
    cleric_by_map = {slot.map_name: slot for slot in cleric}
    if set(cleric_by_map) != {slot.map_name for slot in human}:
        raise ValueError("Cleric/Gascoigne source and destination state sets differ")
    target = human[0]
    swap = Swap(target.logical_key, [slot.key for slot in human],
                {slot.key: slot.archetype for slot in human}, target.archetype,
                CLERIC_PACKAGE.archetype, destinations={slot.key: {
                    "map_name": slot.map_name, "entity_id": slot.entity_id,
                    "x": slot.x, "y": slot.y, "z": slot.z,
                } for slot in human})
    changes, skips = plan_scaling([swap], human, dict(npcs), dict(effects), boss_tiers=True)
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            "format": "bb-cleric-gascoigne-contract-v1", "arena": "father-gascoigne",
            "donor": "cleric-beast", "attachment_event_ids": asdict(ids),
            "preserved_destination_events": [12411800, 12411802],
            "runtime_status": "unobserved arena fit",
        },
        "primary_init_source_bindings": [{
            "source_map": cleric_by_map[slot.map_name].map_name,
            "source_part": cleric_by_map[slot.map_name].part_name,
            "source_entity_id": CLERIC_PACKAGE.actor,
            "source_archetype": asdict(CLERIC_PACKAGE.archetype),
            "source_talk_id": 0,
            "destination_map": slot.map_name, "destination_part": slot.part_name,
            "destination_entity_id": slot.entity_id,
            "destination_original_talk_id": slot.talk_id,
            "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
        } for slot in sorted(human, key=lambda item: item.map_name)],
        "scaling": {
            "enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
            "change_count": len(changes), "changes": [change.json() for change in changes],
            "skip_count": len(skips), "skips": skips,
        },
    }
