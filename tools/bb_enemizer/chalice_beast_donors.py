"""Source-pinned m29 beast donors for opt-in boss encounter recipes.

Only combat handlers are carried across maps. The destination owns its fog,
entry, completion, rewards, and co-op lifecycle. The three per-map m29 Event(0)
tables are pinned as binary evidence; their dungeon entry events are not copied.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence

from .boss_canary import event_blocks
from .boss_contracts import ARENAS, ArenaContract
from .encounter_recipes import EncounterRecipe
from .gascoigne_donor import (
    CO_OP_RESTORE_EVENTS, _adapt_activation, _noop, _replace_events, _retired,
    _original_ids,
)
from .model import Archetype, Slot, Swap
from .scaling import plan_scaling

EVENT_FILE = "m29.emevd.dcx.js"
SOURCE_EVENT_SHA256 = {
    12906831: "2b038edc35550328154fea9685124f23e6f1a34987498088837735f81ad3d5be",
    12906833: "3579d78166500a963d66bf40baeb9dea3980fc7add0943e383a29782299bb740",
    12906835: "b7341fc767b5b4e07d30be8b9b9f65cbeac414bf896ffff65414add16900509c",
    12906837: "46ad86d463042a9c60fe49013422a47d1471388104473e8f870bc7182da92f3c",
    12906839: "621929f3645ec7c8fd15d8ff5d6bacb81275c0d659b78de0f4eace59236aefce",
    12906841: "2edca5d2805ba7646b9beea236f6d7ec2725905088d7afa3ae5c885822987ca6",
    12906843: "3726620e8b27c65ec101ede178ad7792ebfcd90f452f838b55cf805a5e305408",
    12906845: "b07adaa94bf283eca69bd83de27dd9b98e80cfd85fab3ff9b82a287a603c8e00",
    12906847: "c6e3a8252e9cebc444f8d82b109c982a0035f1cfd9ae8023441c2af9ca192e4c",
    12906849: "cae0940c72a7cfa023386336d92b397169baf2779fae780b98b15e3b96ef067f",
}
SOURCE_WITNESS_SHA256 = {
    12906806: "f508ee03fbf412e0827cc2433172f06f909bded3304babdb0ecc05a46e846d70",
    12906810: "8adc0ff9c8501b35d7e7b6b2d9fa067f27f4977a42311555349d304e96a019dd",
    12906818: "de931fc6e381396e073b146db1a013f1234796484d44fc69f23a224f98ff9161",
}


@dataclass(frozen=True)
class ChaliceBeastDonor:
    key: str
    family: str
    source_map: str
    source_part: str
    source_archetype: Archetype
    source_part_sha256: str
    source_map_sha256: str
    source_constructor_sha256: str
    health_bar_label: int
    source_handlers: tuple[int, ...]
    model_assets: tuple[tuple[str, str], ...]
    source_entity: int = 2900100
    event_file: str = EVENT_FILE


WATCHDOG = ChaliceBeastDonor(
    "watchdog-of-the-old-lords", "watchdog", "m29_01_11_00", "c5010_0000",
    Archetype("c5010", 10501006, 501000, 0),
    "f36e1a699c754c114cdb7906aee0266cbd20a500772dd5dbf1117cff098533a0",
    "48d67ce5a7dcda2684ee4b58067aeed247397cfd6d2d4db0163bb76611e1e540",
    "cf51a1c669ad7b8fa1b55c6da4f4c6ec89addd71299b7ff7a41d77e4157ce79b",
    501000, (12906841, 12906843, 12906845, 12906847, 12906849),
    (("chr/c5010.chrbnd.dcx", "5c08d0a6420aaf32386f9ff4a33a73903e2d2e8503a8fd1df567fc60df1c6b3b"),
     ("chr/c5010.anibnd.dcx", "040cc1c1744b034b2fe679e87a4b6c1981df80e2426db5eb47d6504d8ee54e9c")),
)
ABHORRENT = ChaliceBeastDonor(
    "abhorrent-beast", "abhorrent-beast", "m29_01_13_00", "c5040_0000",
    Archetype("c5040", 10504006, 504000, 0),
    "58b5e37060c5cd0bec151fc536430f2cbe84fd76f357b0214940336eded47b08",
    "033f9afec3b4198e6ae8048c9a0f651cd8a7d782caddc42ae97464014c8412c2",
    "ac026adf8272925cc8e179eb1dba41f8ad6e126749789c2460245d3d2789c0f1",
    504010, (12906831, 12906833, 12906835, 12906837, 12906839),
    (("chr/c5040.chrbnd.dcx", "1b59b674893c5e1588678b650c41cf644fab0f3e48a8589325216f09a3a07cdb"),
     ("chr/c5040.anibnd.dcx", "3db6447cacec1fe8fe56e0b11f2acd3668ed9f5f6c04d9de3a9ec8ed04f79ca7")),
)
BEAST_POSSESSED_SOUL = ChaliceBeastDonor(
    "beast-possessed-soul", "beast-possessed-soul", "m29_01_13_09", "c7500_0000",
    Archetype("c7500", 10750090, 750090, 0),
    "423d640abaf0c164429451a5c68f6751f46e329b1c99c9c453cb71143865a09e",
    "ef84db20bac9cfa235816f8c09f299d7685ca93f89a2480c2def7a5848c483d6",
    "6ee4bab3144432761de896c013f2b608d1e0d2c74ec7ecf1ef228c6bd86f698b",
    750000, (),
    (("chr/c7500.chrbnd.dcx", "823cc003de4b5d32863db46f7958dad0e38e728c593540fb76589338f5bdd225"),
     ("chr/c7500.anibnd.dcx", "ac50117b2128f436e1afcd0ce63b9df0e59bfbfaf0cec6a973521e6896033b68")),
)
DONORS = (WATCHDOG, ABHORRENT, BEAST_POSSESSED_SOUL)
SUPPORTED_ARENAS = ARENAS
SOURCE_INITIALIZATION = {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1}
# Five distinct source limb controllers per family. Source Event(0) passes
# (2900100, 1, 1) through (2900100, 5, 5) in the pinned per-map constructors.
ATTACHMENT_IDS = {
    WATCHDOG.key: (12997200, 12997201, 12997202, 12997203, 12997204),
    ABHORRENT.key: (12997210, 12997211, 12997212, 12997213, 12997214),
}


def _source_blocks(source: str, donor: ChaliceBeastDonor) -> dict[int, str]:
    blocks = event_blocks(source)
    for event in (*SOURCE_WITNESS_SHA256, *donor.source_handlers):
        body = blocks.get(event)
        expected = SOURCE_EVENT_SHA256.get(event, SOURCE_WITNESS_SHA256.get(event))
        # Original DarkScript decompilation inserts blank separator lines;
        # the committed input bundle removes them but preserves instructions.
        normalized = "\n".join(line for line in body.splitlines() if line.strip()) if body else ""
        if body is None or hashlib.sha256(normalized.encode()).hexdigest() != expected:
            raise ValueError(f"{donor.key} m29 combat handler {event} drifted")
    return blocks


def _one_phase_music(body: str, arena: ArenaContract) -> str:
    # m29's limb routines signal message 300, but never Cleric's phase 100.
    # Retain the destination's start/fog/music gate and its first track.
    if arena.key != "cleric-beast":
        raise ValueError(f"{arena.key} single-phase music requires a reviewed route")
    marker = "        EnableBossMapSound(2413802, Enabled);"
    prefix, found, _ = body.partition(marker)
    if not found or body.count(marker) != 1:
        raise ValueError("Cleric first-track music witness drifted")
    return (prefix + marker + f"\n        WaitFor(EventFlag({arena.completion_event}));"
            "\n        EndEvent();\n    }\nL0:\n    EndEvent();\n});")


def _event_as(body: str, old: int, new: int) -> str:
    declaration = f"$Event({old},"
    if body.count(declaration) != 1:
        raise ValueError(f"m29 handler {old} declaration drifted")
    return body.replace(declaration, f"$Event({new},", 1)


def _validate_ids(destination: str, donor: ChaliceBeastDonor) -> None:
    ids = ATTACHMENT_IDS.get(donor.key, ())
    local = {int(number) for number in re.findall(r"(?<![\w])-?\d+(?![\w])", destination)}
    if any(not 12997200 <= number <= 12997299 for number in ids) or set(ids) & (_original_ids() | local):
        raise ValueError("chalice beast combat event ID collides with original corpus")


def patch_chalice_beast(arena: ArenaContract, donor: ChaliceBeastDonor,
                        destination: str, donor_source: str) -> str:
    # The Cleric route is the conservative minimum while other arena entries
    # await per-arena music/entry review. No generic map-prefix substitution.
    if arena.key != "cleric-beast" or donor not in DONORS:
        raise ValueError("unsupported chalice beast route")
    original = event_blocks(destination)
    for event, expected in arena.expected.items():
        body = original.get(event)
        if body is None or hashlib.sha256(body.encode()).hexdigest() != expected:
            raise ValueError(f"{arena.key} event {event} drifted")
    source = _source_blocks(donor_source, donor)
    _validate_ids(destination, donor)
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    edits[arena.activation_event] = _adapt_activation(arena, original[arena.activation_event])
    edits[arena.music_event] = _one_phase_music(original[arena.music_event], arena)
    old_label = f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {arena.health_bar_label});"
    new_label = f"DisplayBossHealthBar(Enabled, {arena.actor}, 0, {donor.health_bar_label});"
    if original[arena.health_bar_event].count(old_label) != 1:
        raise ValueError("Cleric health label witness drifted")
    edits[arena.health_bar_event] = original[arena.health_bar_event].replace(old_label, new_label)
    additions: list[str] = []
    if donor.source_handlers:
        constructor = original[0]
        anchor = f"    $InitializeEvent(0, {arena.health_bar_event});"
        if constructor.count(anchor) != 1:
            raise ValueError("Cleric health constructor anchor drifted")
        calls = []
        for index, (source_id, target_id) in enumerate(zip(donor.source_handlers, ATTACHMENT_IDS[donor.key], strict=True)):
            additions.append(_event_as(source[source_id], source_id, target_id))
            calls.append(f"    $InitializeEvent(0, {target_id}, {arena.actor}, {index + 1}, {index + 1});")
        edits[0] = constructor.replace(anchor, anchor + "\n" + "\n".join(calls), 1)
    result = _replace_events(destination, edits).rstrip()
    if additions:
        result += "\n\n" + "\n\n".join(additions)
    result += "\n"
    output = event_blocks(result)
    if set(output) != set(original) | set(ATTACHMENT_IDS.get(donor.key, ())):
        raise ValueError("chalice beast adapter changed unexpected event identities")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError(f"chalice beast adapter changed unrelated event {event}")
    for event in (arena.completion_event, CO_OP_RESTORE_EVENTS[arena.key]):
        if output[event] != original[event]:
            raise ValueError(f"chalice beast adapter changed protected event {event}")
    return result


def native_plan_chalice_beast(arena: ArenaContract, donor: ChaliceBeastDonor,
                              slots: Sequence[Slot], npcs: Mapping[int, dict],
                              effects: Mapping[int, dict], seed: str) -> dict:
    if arena.key != "cleric-beast" or donor not in DONORS:
        raise ValueError("unsupported chalice beast route")
    sources = [row for row in slots if row.map_name == donor.source_map and
               row.part_name == donor.source_part and row.entity_id == donor.source_entity]
    if len(sources) != 1 or sources[0].dummy or sources[0].archetype != donor.source_archetype or sources[0].talk_id:
        raise ValueError(f"{donor.key} requires its exact original m29 actor")
    source = sources[0]
    destinations = sorted((row for row in slots if row.entity_id == arena.actor and
                           row.map_name.startswith(arena.map_prefix)), key=lambda row: row.map_name)
    if (len(destinations) != arena.destination_count or
            len({row.logical_key for row in destinations}) != 1 or
            any(row.dummy or row.archetype != arena.archetype or row.talk_id for row in destinations)):
        raise ValueError(f"{arena.key} requires every exact destination actor state")
    swap = Swap(
        destinations[0].logical_key, [row.key for row in destinations],
        {row.key: row.archetype for row in destinations},
        arena.archetype, donor.source_archetype,
        warnings=["chalice donor arena fit and runtime effect closure are unobserved"],
        destinations={row.key: {"map_name": row.map_name, "entity_id": row.entity_id,
                                "x": row.x, "y": row.y, "z": row.z} for row in destinations},
    )
    changes, skips = plan_scaling([swap], destinations, dict(npcs), dict(effects), boss_tiers=True)
    bindings = [{
        "source_event_file": "event/" + donor.event_file,
        "source_map": source.map_name, "source_part": source.part_name,
        "source_entity_id": source.entity_id,
        "source_archetype": asdict(source.archetype), "source_talk_id": source.talk_id,
        "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": donor.source_part_sha256},
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": row.map_name, "destination_part": row.part_name,
        "destination_entity_id": row.entity_id, "destination_original_talk_id": row.talk_id,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
    } for row in destinations]
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "boss_contract": {
            "arena": arena.key, "donor": donor.key, "family": donor.family,
            "combat_owner": "m29-donor", "progression_owner": "destination-arena",
            "source_event_file": "event/" + donor.event_file,
            "source_map": donor.source_map, "source_map_sha256": donor.source_map_sha256,
            "source_constructor_sha256": donor.source_constructor_sha256,
            "source_handlers": list(donor.source_handlers),
            "model_assets": [{"path": path, "sha256": sha} for path, sha in donor.model_assets],
            "validation_status": "static-contract-only",
        },
        "primary_init_source_bindings": bindings,
        "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [row.json() for row in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def chalice_beast_recipes() -> tuple[EncounterRecipe, ...]:
    """Explicit, opt-in Cleric routes; not inserted in the reviewed 22 graph."""
    arena = next(arena for arena in SUPPORTED_ARENAS if arena.key == "cleric-beast")
    recipes = []
    for donor in DONORS:
        def patch(destination: str, source: str, *, _donor=donor) -> str:
            return patch_chalice_beast(arena, _donor, destination, source)

        def native_plan(slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict],
                        seed: str, *, _donor=donor) -> dict:
            return native_plan_chalice_beast(arena, _donor, slots, npcs, effects, seed)

        recipes.append(EncounterRecipe(
            arena, donor, "m29-chalice-beast:source-combat", patch,
            native_plan, lambda slots: [],
        ))
    return tuple(recipes)
