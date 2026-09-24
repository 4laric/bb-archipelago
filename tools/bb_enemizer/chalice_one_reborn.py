"""Beast-Possessed Soul at One Reborn, retaining the original proxy terminal.

The m29 source supplies the physical actor and its initialization. One Reborn
still owns entrance, co-op, fog, completion, rewards and shared-map events.
The displaced body/support controllers are retired; a small bridge kills the
offstage original proxy only after the replacement dies.
"""
from __future__ import annotations

import re
from dataclasses import asdict, replace
from typing import Mapping, Sequence

from tools.bb_inputs import read_blob

from . import rom_ebrietas_contract as rom
from . import rom_one_reborn_contract as one
from .boss_canary import event_blocks
from .boss_contracts import CLERIC_ARENA
from .chalice_beast_donors import (
    BEAST_POSSESSED_SOUL as DONOR, SOURCE_INITIALIZATION, _source_blocks,
)
from .encounter_recipes import EncounterRecipe
from .model import Slot, Swap
from .scaling import plan_scaling

BRIDGE = 12997050
ARENA = replace(
    CLERIC_ARENA, key="the-one-reborn", event_file="m28_00_00_00.emevd.dcx.js",
    map_prefix="m28_00_", actor=one.PRIMARY, archetype=one.ARCHETYPE,
    destination_count=2, completion_event=12801800, start_flag=12804800,
    health_bar_event=12804802, health_bar_label=507000,
    activation_event=12801802, music_event=12804803,
    phase_music_message=300, lockcam_event=12804804, lockcam_map=28,
    lockcam_subarea=0, phase_slots=one.RETIRED_EVENTS, expected=one.ARENA_HASHES,
)
PRESERVED = (12801800, 12801801, 12804805, 12804880, 12804881, 12804882, 12804883)


def _health(original: str) -> str:
    if "DisplayBossHealthBar(Enabled, 2800803, 0, 507000);" not in original:
        raise ValueError("One Reborn health-bar witness drifted")
    return """$Event(12804802, Default, function() {
    EndIf(EventFlag(12801800));
    SetCharacterAIState(2800800, Disabled);
    SetCharacterHPBarDisplay(2800800, Disabled);
    SetCharacterInvincibility(2800800, Enabled);
    SetCharacterAIState(2800803, Disabled);
    SetCharacterHPBarDisplay(2800803, Disabled);
    SetCharacterGravity(2800803, Disabled);
    SetCharacterInvincibility(2800803, Enabled);
    if (!ThisEvent()) {
        WaitFor(EventFlag(12804800));
        if (!HasMultiplayerState(MultiplayerState.Client)) {
            if (!EventFlag(12804223)) {
                IssueBossRoomEntryNotification(0);
            }
            SetNetworkUpdateAuthority(2800800, AuthorityLevel.Forced);
        }
    }
L0:
    SetEventFlag(12804223, ON);
    SetEventFlag(12804800, ON);
    GotoIf(L1, NumberOfCoopClients() == 0);
    GotoIf(L2, NumberOfCoopClients() == 1);
    GotoIf(L3, NumberOfCoopClients() == 2);
L1:
    Goto(L4);
L2:
    SetSpEffect(2800800, 7500, true);
    Goto(L4);
L3:
    SetSpEffect(2800800, 7501, true);
    Goto(L4);
L4:
    SetCharacterAIState(2800800, Enabled);
    SetCharacterInvincibility(2800800, Disabled);
    DisplayBossHealthBar(Enabled, 2800800, 0, 750000);
    SetNetworkUpdateRate(2800800, true, CharacterUpdateFrequency.AlwaysUpdate);
    CreatePlaylog(238);
    StartTimeMeasurement(2800010, 254, Enabled);
});"""


def _music(original: str) -> str:
    witness = "        chrFlagArea &= CharacterHasEventMessage(2800800, 300);"
    if original.count(witness) != 1:
        raise ValueError("One Reborn phase music witness drifted")
    # The original m29_01_13_09 constructor binds the pinned common music
    # event 12906810, whose exact phase message is 500 for this actor.
    return original.replace(witness,
                            "        chrFlagArea &= CharacterHasEventMessage(2800800, 500);", 1)


def _bridge() -> str:
    cleanup = "\n".join(
        f"    ChangeCharacterEnableState({entity}, Disabled);\n"
        f"    SetCharacterAIState({entity}, Disabled);\n"
        f"    SetCharacterHPBarDisplay({entity}, Disabled);"
        for entity in one.RETAINED
    )
    return f"""$Event({BRIDGE}, Default, function() {{
{cleanup}
    EndIf(EventFlag(12801800));
    SetCharacterGravity(2800803, Disabled);
    SetCharacterInvincibility(2800803, Enabled);
    WaitFor(CharacterDead(2800800));
    SetCharacterInvincibility(2800803, Disabled);
    ForceCharacterDeath(2800803, false);
}});"""


def patch_one_reborn(destination: str, donor_source: str) -> str:
    original = rom._verify(destination, one.ARENA_HASHES, "One Reborn arena")
    _source_blocks(donor_source, DONOR)
    if (BRIDGE in original or BRIDGE in rom._original_ids() or
            re.search(r"(?<!\d)12997050(?!\d)", destination)):
        raise ValueError("One Reborn chalice bridge ID collision")
    constructor = rom._replace_once(
        original[0], "    $InitializeEvent(0, 12804871);",
        f"    $InitializeEvent(0, 12804871);\n    $InitializeEvent(0, {BRIDGE});",
        "One Reborn bridge constructor anchor")
    edits = {
        0: constructor, 12804802: _health(original[12804802]),
        12804803: _music(original[12804803]),
        **{event: rom._end_event(original[event]) for event in one.RETIRED_EVENTS},
    }
    for event in (12801802, 12801803):
        edits[event] = rom._replace_once(
            original[event], "    ChangeCharacterEnableState(2800801, Enabled);\n",
            "", "displaced second-body activation")
    output = rom._replace_events(destination, edits).rstrip() + "\n\n" + _bridge() + "\n"
    blocks = event_blocks(output)
    if set(blocks) != set(original) | {BRIDGE}:
        raise ValueError("One Reborn chalice changed event identities")
    for event, body in original.items():
        if event not in edits and blocks[event] != body:
            raise ValueError(f"One Reborn chalice changed unrelated event {event}")
    for event in PRESERVED:
        if blocks[event] != original[event]:
            raise ValueError(f"One Reborn chalice changed protected event {event}")
    return output


def native_plan(slots: Sequence[Slot], npcs: Mapping[int, dict],
                effects: Mapping[int, dict], seed: str) -> dict:
    arena = read_blob(one.BUNDLE, one.ARENA_SOURCE).decode("utf-8-sig")
    source = read_blob(one.BUNDLE, "event/m29.emevd.dcx.js").decode("utf-8-sig")
    rom._verify(arena, one.ARENA_HASHES, "One Reborn arena")
    _source_blocks(source, DONOR)
    if BRIDGE in event_blocks(arena) or BRIDGE in rom._original_ids():
        raise ValueError("One Reborn chalice bridge ID collision")
    sources = [row for row in slots if row.map_name == DONOR.source_map and
               row.part_name == DONOR.source_part and row.entity_id == DONOR.source_entity and
               row.archetype == DONOR.source_archetype and not row.dummy and not row.talk_id]
    if len(sources) != 1:
        raise ValueError("One Reborn chalice requires exact Beast-Possessed Soul source actor")
    targets = sorted((row for row in slots if row.entity_id == one.PRIMARY and
                      row.map_name in one.STATES and row.archetype == one.ARCHETYPE),
                     key=lambda row: row.map_name)
    if (len(targets) != 2 or {row.map_name for row in targets} != set(one.STATES) or
            len({row.logical_key for row in targets}) != 1 or
            any(row.dummy or row.talk_id or row.collision_name != "h000100" for row in targets)):
        raise ValueError("One Reborn chalice needs both exact destination states")
    by_identity = {(row.map_name, row.entity_id): row for row in slots}
    retained = []
    for state in one.STATES:
        for entity in (one.PRIMARY, *one.RETAINED):
            row = by_identity.get((state, entity))
            witness = one.ACTOR_WITNESSES[state][entity]
            if (row is None or row.part_name != witness["part"] or
                    asdict(row.archetype) != witness["archetype"] or row.dummy or row.talk_id):
                raise ValueError("One Reborn chalice retained actor roster drift")
            if entity != one.PRIMARY:
                retained.append({
                    "map": state, "part": row.part_name, "entity_id": entity,
                    "archetype": asdict(row.archetype),
                    "source_provenance": rom._pin(witness["sha256"]),
                    "source_initialization": witness["initialization"],
                    "policy": "disabled; original proxy killed after replacement death",
                })
    swap = Swap(targets[0].logical_key, [row.key for row in targets],
                {row.key: row.archetype for row in targets}, one.ARCHETYPE,
                DONOR.source_archetype,
                warnings=["One Reborn chalice arena fit and runtime effects unobserved"],
                destinations={row.key: {"map_name": row.map_name,
                                         "entity_id": row.entity_id,
                                         "x": row.x, "y": row.y, "z": row.z}
                              for row in targets})
    changes, skips = plan_scaling([swap], targets, dict(npcs), dict(effects), boss_tiers=True)
    bindings = [{
        "source_event_file": "event/" + DONOR.event_file,
        "source_map": sources[0].map_name, "source_part": sources[0].part_name,
        "source_entity_id": sources[0].entity_id,
        "source_archetype": asdict(sources[0].archetype), "source_talk_id": sources[0].talk_id,
        "source_provenance": rom._pin(DONOR.source_part_sha256),
        "source_initialization": dict(SOURCE_INITIALIZATION),
        "destination_map": row.map_name, "destination_part": row.part_name,
        "destination_entity_id": row.entity_id,
        "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"],
    } for row in targets]
    return {
        "format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
        "swap_count": 1, "swaps": [swap.json()],
        "primary_init_source_bindings": bindings,
        "boss_contract": {
            "arena": ARENA.key, "donor": DONOR.key, "family": DONOR.family,
            "combat_owner": "m29-donor", "progression_owner": "destination-arena",
            "source_event_file": "event/" + DONOR.event_file,
            "source_map": DONOR.source_map, "source_map_sha256": DONOR.source_map_sha256,
            "source_constructor_sha256": DONOR.source_constructor_sha256,
            "source_handlers": [],
            "model_assets": [{"path": path, "sha256": sha} for path, sha in DONOR.model_assets],
            "retained_destination_helpers": retained,
            "arena_hash_pins": dict(one.ARENA_HASHES),
            "preserved_destination_events": list(PRESERVED),
            "retired_events": list(one.RETIRED_EVENTS),
            "added_event_ids": [BRIDGE],
            "terminal_policy": "original proxy terminal; death bridge after donor death",
            "validation_status": "static-contract-only",
        },
        "scaling": {"enabled": bool(changes),
                    "mechanism": "inferred_static_npc_clone_sp_effect",
                    "change_count": len(changes), "changes": [change.json() for change in changes],
                    "skip_count": len(skips), "skips": skips},
    }


def recipes() -> tuple[EncounterRecipe, ...]:
    return (EncounterRecipe(ARENA, DONOR, "chalice-one-reborn:source-combat",
                            patch_one_reborn, native_plan, lambda slots: []),)
