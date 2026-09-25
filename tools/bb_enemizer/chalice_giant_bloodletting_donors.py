"""Source-pinned chalice Giant and Bloodletting combat donors.

The m29 map-specific constructors are binary Event(0) dispatch tables.  Their
handlers live in m29.emevd.dcx.js.  Only the normal Bloodletting Beast binds
limb, roar and display-mask handlers to its primary actor; the headless actor
in m29_05_00_11 does not.  This adapter keeps destination fog, entry, health,
music, completion and progression, while retiring destination-model combat.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .boss_canary import event_blocks
from .boss_contracts import ARENAS, ArenaContract
from .encounter_recipes import EncounterRecipe
from .gascoigne_donor import (
    CO_OP_RESTORE_EVENTS, _adapt_activation, _noop, _replace_events, _retired,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

EVENT_FILE = "m29.emevd.dcx.js"
SOURCE_EVENT_SHA256 = {
    12904881: "6f1571499854a78c95441d0b622e9be44868fc6fd94110c9e6ef500a9543d93f",
    12904882: "8b101251c4ba607ce23a15c66ac070cf8bbc12f3e3a9b01c3b952fea5ebdf341",
    12904888: "0fd431be9f2c1e55767b07828f88a703c540745e9ffd12f817c9c901e1d03342",
    12904898: "7f2fda40c39acb4aa987ee2df56a17560a6f487226fe2437dba9b43e475dc092",
    12904901: "1a4be26ca9e7370da2964606585e158c4b9671e55c70e63962abf5ae8e8d629b",
    12904904: "70b8da07f7d9c099cb3693223309a25381f9e3745ff236a6cb46c222cea34293",
    12904907: "f58084906863e519780765b6dee7fc87cab81af9223be81a891c07668a7b428f",
    12904910: "58d4055381742a521b9acd355c51c08a5d106ac3fe5c053c7e89d39fc67a33c8",
    12904914: "5b365787a99a765154fd03be383933ae5aeb83e4d1f47e01e8e3cd1833643c85",
    12904915: "8d76ecb142b0e9ac2f0607c95d46c23de80e929d15dfef5950284c60f21729f4",
    12904890: "7b572f99773c1d5eff5ab2c473f82adff5d6183afc90c555d7f839287d293a62",
    12906806: "f508ee03fbf412e0827cc2433172f06f909bded3304babdb0ecc05a46e846d70",
    12906810: "8adc0ff9c8501b35d7e7b6b2d9fa067f27f4977a42311555349d304e96a019dd",
    12906818: "de931fc6e381396e073b146db1a013f1234796484d44fc69f23a224f98ff9161",
}


@dataclass(frozen=True)
class ChaliceDonor:
    key: str
    family: str
    health_label: int
    source_map: str
    source_part: str
    source_entity: int
    source_archetype: Archetype
    source_part_sha256: str
    source_map_sha256: str
    source_constructor_sha256: str
    source_initialization: Mapping[str, int]
    source_handlers: tuple[int, ...]
    model_assets: tuple[tuple[str, str], ...]
    event_file: str = EVENT_FILE


GIANT = ChaliceDonor(
    "undead-giant", "undead-giant", 313000, "m29_01_13_08", "c3130_0000", 2900100,
    Archetype("c3130", 10313090, 313090, 0),
    "806103d444e88845ab17c11cbfe40661e9bed8c401b698ac0e23a406f8fb4156",
    "d0a66852c290b34c78c0edbb872abddda345cd38c19579d80a442220b091cbac",
    "dcd1647ce988569df7ba76a7904a365a9e5161ae929c4d4a8d4c48ec45805298",
    {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1},
    (12906806, 12906810, 12906818),
    (("chr/c3130.chrbnd.dcx", "e94db9dac66b2e42ad70649c562659e53589867d7d9026fed9f1b54e33c4f65a"),
     ("chr/c3130.anibnd.dcx", "255919be3ecd7ad9943034b0a9196c59c4f225a53d31af88fbacb35d3bfa81e9")),
)
NORMAL_BLOODLETTING = ChaliceDonor(
    "bloodletting-beast", "bloodletting-beast", 509000, "m29_05_00_08", "c5090_0000", 2900102,
    Archetype("c5090", 10509006, 509000, 0),
    "8ccf48f5ac082efc5a8abd06dacb5b45c1850a626d7c8ed457942642362b0592",
    "73a99214ffac4b7889090004cb9b2c86ac95f5fa56a86d9b62c3f895c24154d2",
    "d0bb3c2733fd65267cc5027bd91993f762a6e706710f9f615f0b1b3803680a8b",
    {"talk_id": 0, "unk_t18": 0, "init_anim_id": -1, "damage_anim_id": -1},
    (12904890, 12904882, 12904888, 12904898, 12904901, 12904904, 12904907,
     12904910, 12904914, 12904915),
    (("chr/c5090.chrbnd.dcx", "9538d69824bb091e71e9039de409d4360e60c4611e4e07783b2fbf2dce091cbf"),
     ("chr/c5090.anibnd.dcx", "8751b4230d0e6f294c3d4b7df758025c6e217e24845352a2e190e38c5520995b")),
)
HEADLESS_BLOODLETTING = ChaliceDonor(
    "headless-bloodletting-beast", "bloodletting-beast", 509010, "m29_05_00_11", "c5090_0000", 2900127,
    Archetype("c5090", 10509010, 509010, 0),
    "981c9d429dc058a870a46b5e9fb58f37b420e5672f46852335b8cfef76171680",
    "8529cea39b461d489f9b46d0299af0e92bed6e0ccf4f0b425b1dbcee51340c71",
    "ec8f6ed92dc36efc0c77ad99515d53a0e0fa6b71d1d42f279f5342dcffc3cdc5",
    {"talk_id": 0, "unk_t18": 0, "init_anim_id": -1, "damage_anim_id": -1},
    (12904881, 12904882),
    NORMAL_BLOODLETTING.model_assets,
)
DONORS = (GIANT, NORMAL_BLOODLETTING, HEADLESS_BLOODLETTING)
SUPPORTED_ARENAS = ARENAS

# Original m29_05_00_08 constructor slots 87-97.  The five part IDs, HP,
# damaged/restored effects and mask bits are copied from the original calls.
LIMBS = (
    (12904898, 1, 5, 5, 100, 480, 490, 5, 10, 0),
    (12904901, 2, 6, 6, 170, 481, 491, 6, 11, 1),
    (12904904, 3, 7, 7, 170, 482, 492, 7, 12, 2),
    (12904907, 4, 8, 8, 220, 483, 493, 8, 13, 3),
    (12904910, 5, 9, 9, 220, 484, 494, 9, 14, 4),
)
ATTACHMENT_IDS = (12997000, 12997001, 12997002, 12997003,
                  12997004, 12997005, 12997006, 12997007)
PART_VALUE_FLAG = 12997040
PART_CHANGED_FLAG = 12997050


def _source_blocks(source: str, donor: ChaliceDonor) -> dict[int, str]:
    blocks = event_blocks(source)
    for event in donor.source_handlers:
        body = blocks.get(event)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != SOURCE_EVENT_SHA256[event]:
            raise ValueError(f"{donor.key} m29 handler {event} drifted")
    return blocks


def _music(arena: ArenaContract, body: str) -> str:
    if arena.phase_music_event_flag is not None:
        witness = f"EventFlag({arena.phase_music_event_flag})"
    elif arena.phase_music_message is not None:
        witness = f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})"
    else:
        raise ValueError(f"{arena.key} lacks a phase music witness")
    if body.count(witness) != 1:
        raise ValueError(f"{arena.key} phase music witness drifted")
    return body.replace(witness, f"CharacterHasEventMessage({arena.actor}, 500)", 1)


def _health(arena: ArenaContract, donor: ChaliceDonor, body: str) -> str:
    # IDs 313000/509000/509010 are exact original NPC-name FMG rows from
    # engUS/item.msgbnd.dcx (SHA256 1ddebc69611f6b6af01bed1970f4127148e9e86342ec7ec26d51fc1ceb289439).
    witness = f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label});"
    if body.count(witness) != 1:
        raise ValueError(f"{arena.key} boss-name witness drifted")
    return body.replace(witness,
                        f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_label});", 1)


def _event_as(body: str, source_id: int, target_id: int) -> str:
    old = f"$Event({source_id},"
    if body.count(old) != 1:
        raise ValueError(f"m29 event {source_id} declaration drifted")
    return body.replace(old, f"$Event({target_id},", 1)


def _normal_attachments(arena: ArenaContract, source: Mapping[int, str]) -> tuple[list[str], list[str]]:
    # The original limb counter and state flag are intentionally allocated as
    # separate project-owned flags; source dungeon flags cannot be exported.
    additions = []
    calls = []
    for index, (event, group, part, part2, hp, effect, recovery, bit, bit2, bit3) in enumerate(LIMBS):
        target = ATTACHMENT_IDS[index]
        additions.append(_event_as(source[event], event, target))
        calls.append(
            f"    $InitializeEvent(0, {target}, {arena.actor}, {PART_VALUE_FLAG}, "
            f"{PART_CHANGED_FLAG}, {arena.start_flag}, {group}, {part}, {part2}, {hp});"
        )
        calls.append(
            f"    $InitializeEvent({index}, {ATTACHMENT_IDS[6]}, {effect}, "
            f"{recovery}, {bit}, {bit2}, {bit3}, {arena.actor});"
        )
    for source_id, target_id in ((12904888, ATTACHMENT_IDS[5]),
                                 (12904914, ATTACHMENT_IDS[6]),
                                 (12904915, ATTACHMENT_IDS[7])):
        additions.append(_event_as(source[source_id], source_id, target_id))
    calls.append(f"    $InitializeEvent(0, {ATTACHMENT_IDS[5]}, {arena.actor});")
    calls.append(f"    $InitializeEvent(0, {ATTACHMENT_IDS[7]}, {arena.actor});")
    return additions, calls


def patch_chalice_donor(arena: ArenaContract, donor: ChaliceDonor,
                        destination: str, donor_source: str) -> str:
    if arena not in SUPPORTED_ARENAS or donor not in DONORS:
        raise ValueError("unsupported chalice donor route")
    original = event_blocks(destination)
    for event, expected in arena.expected.items():
        body = original.get(event)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != expected:
            raise ValueError(f"{arena.key} event {event} drifted")
    source = _source_blocks(donor_source, donor)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    edits[arena.activation_event] = _adapt_activation(arena, original[arena.activation_event])
    edits[arena.health_bar_event] = _health(arena, donor, original[arena.health_bar_event])
    edits[arena.music_event] = _music(arena, original[arena.music_event])
    additions, calls = ([], []) if donor is not NORMAL_BLOODLETTING else _normal_attachments(arena, source)
    if calls:
        constructor = original[0]
        anchor = f"    $InitializeEvent(0, {arena.health_bar_event});"
        if constructor.count(anchor) != 1:
            raise ValueError(f"{arena.key} has no unique health constructor anchor")
        edits[0] = constructor.replace(anchor, anchor + "\n" + "\n".join(calls), 1)
    result = _replace_events(destination, edits).rstrip()
    if additions:
        result += "\n\n" + "\n\n".join(additions)
    result += "\n"
    output = event_blocks(result)
    if set(output) != set(original) | (set(ATTACHMENT_IDS) if additions else set()):
        raise ValueError("chalice adapter changed unexpected event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"chalice adapter changed unrelated destination event {event}")
    for event in (arena.completion_event, CO_OP_RESTORE_EVENTS[arena.key]):
        if output[event] != original[event]:
            raise ValueError(f"chalice adapter changed protected arena event {event}")
    return result


def _source_slot(slots: Sequence[Slot], donor: ChaliceDonor) -> Slot:
    matches = [slot for slot in slots if slot.map_name == donor.source_map
               and slot.part_name == donor.source_part
               and slot.entity_id == donor.source_entity]
    if len(matches) != 1 or matches[0].dummy or matches[0].archetype != donor.source_archetype:
        raise ValueError(f"{donor.key} requires its exact original MSB actor")
    return matches[0]


def _destinations(slots: Sequence[Slot], arena: ArenaContract) -> list[Slot]:
    rows = sorted((slot for slot in slots if slot.entity_id == arena.actor
                   and slot.map_name.startswith(arena.map_prefix)), key=lambda slot: slot.map_name)
    if len(rows) != arena.destination_count or any(
        row.dummy or row.archetype != arena.archetype or row.talk_id != 0 for row in rows
    ):
        raise ValueError(f"{arena.key} requires every exact destination actor state")
    return rows


def native_plan_chalice_donor(arena: ArenaContract, donor: ChaliceDonor,
                              slots: Sequence[Slot], npcs: Mapping[int, dict],
                              effects: Mapping[int, dict], seed: str) -> dict:
    source = _source_slot(slots, donor)
    destinations = _destinations(slots, arena)
    primary = destinations[0]
    swap = Swap(
        primary.logical_key, [row.key for row in destinations],
        {row.key: row.archetype for row in destinations},
        primary.archetype, source.archetype,
        warnings=["chalice donor arena fit and runtime effect closure are unobserved"],
        destinations={row.key: {"map_name": row.map_name, "entity_id": row.entity_id,
                                "x": row.x, "y": row.y, "z": row.z} for row in destinations},
    )
    changes, skips = plan_scaling([swap], destinations, dict(npcs), dict(effects), boss_tiers=True)
    bindings = [{
        "source_event_file": "event/" + donor.event_file,
        "source_map": source.map_name, "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype),
        "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1",
                              "part_sha256": donor.source_part_sha256},
        "source_initialization": dict(donor.source_initialization),
        "destination_map": row.map_name, "destination_part": row.part_name,
        "destination_entity_id": row.entity_id,
        "destination_original_talk_id": row.talk_id,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id",
                                   "damage_anim_id", "provenance"],
    } for row in destinations]
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            "arena": arena.key, "donor": donor.key, "family": donor.family,
            "combat_owner": "m29-donor", "progression_owner": "destination-arena",
            "source_event_file": "event/" + donor.event_file,
            "source_map": donor.source_map,
            "source_map_sha256": donor.source_map_sha256,
            "source_constructor_sha256": donor.source_constructor_sha256,
            "source_handlers": list(donor.source_handlers),
            "boss_health_label": donor.health_label,
            "model_assets": [{"path": path, "sha256": sha} for path, sha in donor.model_assets],
            "normal_limb_effect_ids": list(range(480, 485)) + list(range(490, 495))
            if donor is NORMAL_BLOODLETTING else [],
            "validation_status": "static-contract-only",
        },
        "primary_init_source_bindings": bindings,
        "scaling": {"enabled": bool(changes),
                    "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [row.json() for row in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def chalice_recipes() -> tuple[EncounterRecipe, ...]:
    """Opt-in routes; callers must enforce one Bloodletting family per seed."""
    recipes = []
    for arena in SUPPORTED_ARENAS:
        for donor in DONORS:
            def patch(destination: str, source: str, *, _arena=arena, _donor=donor) -> str:
                return patch_chalice_donor(_arena, _donor, destination, source)

            def native_plan(slots: list, npcs: Mapping[int, dict],
                            effects: Mapping[int, dict], seed: str, *,
                            _arena=arena, _donor=donor) -> dict:
                return native_plan_chalice_donor(_arena, _donor, slots, npcs, effects, seed)

            recipes.append(EncounterRecipe(
                arena, donor, "m29-chalice-donor:source-combat", patch,
                native_plan, lambda slots: [],
            ))
    return tuple(recipes)
