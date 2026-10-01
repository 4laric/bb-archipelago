"""Pinned Chalice humanoids at Gascoigne, with his beast kept inert."""
from dataclasses import asdict

from . import chalice_humanoid_donors as humanoid
from . import gascoigne_arena_contract as gascoigne
from .boss_canary import event_blocks
from .boss_entrances import skip_replacement_entrance
from .encounter_recipes import EncounterRecipe
from .model import Swap, slot_placement
from .scaling import plan_scaling

ARENA = gascoigne.GASCOIGNE_ARENA_CONTRACT


def patch_chalice_at_gascoigne(destination, donor, common_source):
    original, common = event_blocks(destination), event_blocks(common_source)
    gascoigne._verify(original, gascoigne.GASCOIGNE_HASHES, "Gascoigne arena")
    gascoigne._verify(common, humanoid.COMMON_EVENT_PINS, "Chalice common source")
    gascoigne._validate_ids(gascoigne.DEFAULT_IDS, destination)
    health = humanoid._health(ARENA, donor, common[12906806], original[ARENA.health_bar_event])
    health = gascoigne._replace_once(health, "        WaitFor(EventFlag(12414800));",
        f"        WaitFor(EventFlag({gascoigne.ACTIVATION_EVENT}));", "source readiness")
    health = gascoigne._replace_once(health, "            IssueBossRoomEntryNotification(0);",
        "            if (!EventFlag(12414223)) {\n"
        "                IssueBossRoomEntryNotification(0);\n"
        "            }\n            SetEventFlag(12414223, ON);", "notification guard")
    music = gascoigne._replace_once(original[ARENA.music_event], "EventFlag(12414807)",
        "CharacterHasEventMessage(2410810, 500)", "source phase music")
    # Retire both authored navigation slots; their commands target Gascoigne's
    # human/beast AI and must never be sent to a transplanted Chalice actor.
    constructor = original[0]
    for literal in (
            "    $InitializeEvent(0, 12415238, 2412820, 2410810, 2412821, 2412824, 2412822);\n",
            "    $InitializeEvent(1, 12415238, 2412820, 2410811, 2412821, 2412824, 2412822);\n"):
        constructor = gascoigne._replace_once(constructor, literal, "", "navigation initializer")
    anchor = "    $InitializeEvent(0, 12414809);"
    constructor = gascoigne._replace_once(constructor, anchor, anchor +
        f"\n    $InitializeEvent(0, {gascoigne.ACTIVATION_EVENT});"
        f"\n    $InitializeEvent(0, {gascoigne.PROXY_CLEANUP_EVENT});", "constructor anchor")
    wake = (f"    ForceAnimationPlayback(2410810, {donor.wake_animation}, false, false, false);\n"
            if donor.wake_animation is not None else "")
    readiness = f"""$Event({gascoigne.ACTIVATION_EVENT}, Default, function() {{
    EndIf(EventFlag(12411800));
    SetCharacterAIState(2410810, Disabled);
    WaitFor(EventFlag(12414800) || EventFlag(12411800));
    EndIf(EventFlag(12411800));
    ChangeCharacterEnableState(2410810, Enabled);
{wake}}});"""
    edits = {0: constructor, ARENA.health_bar_event: health,
             ARENA.music_event: music, ARENA.lockcam_event: gascoigne._camera(original[ARENA.lockcam_event]),
             **{event: gascoigne._noop(original[event]) for event in (12414807, 12414808, 12414809)}}
    result = gascoigne._replace_events(destination, edits).rstrip() + "\n\n" + readiness + "\n\n" + gascoigne._proxy_cleanup(gascoigne.DEFAULT_IDS) + "\n"
    result = skip_replacement_entrance(ARENA.key, destination, result)
    after = event_blocks(result)
    allowed = {*edits, ARENA.activation_event, gascoigne.ACTIVATION_EVENT, gascoigne.PROXY_CLEANUP_EVENT}
    if set(after) != set(original) | {gascoigne.ACTIVATION_EVENT, gascoigne.PROXY_CLEANUP_EVENT}:
        raise ValueError("Chalice/Gascoigne changed event identities")
    for event, body in original.items():
        if event not in allowed and after[event] != body:
            raise ValueError("Chalice/Gascoigne changed unrelated progression")
    return result


def native_plan_chalice_at_gascoigne(donor, slots, npcs, effects, seed):
    humans = gascoigne._slots(slots, gascoigne.HUMAN, gascoigne.HUMAN_ARCHETYPE,
                              set(gascoigne.MAP_STATES), "human")
    proxies = gascoigne._slots(slots, gascoigne.BEAST_PROXY, gascoigne.BEAST_ARCHETYPE,
                               set(gascoigne.MAP_STATES), "beast proxy")
    sources = [row for row in slots if row.map_name == donor.map_name and row.part_name == donor.part_name
               and row.entity_id == donor.actor and row.archetype == donor.archetype and not row.dummy]
    if len(sources) != 1 or sources[0].talk_id or any(row.talk_id != 241330 for row in humans) or any(row.talk_id for row in proxies):
        raise ValueError("Chalice/Gascoigne source or destination actor drift")
    source, target = sources[0], humans[0]
    swap = Swap(target.logical_key, [row.key for row in humans],
                {row.key: row.archetype for row in humans}, target.archetype, source.archetype,
                destinations={row.key: slot_placement(row) for row in humans})
    changes, skips = plan_scaling([swap], humans, dict(npcs), dict(effects), boss_tiers=True)
    return {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
            "swap_count": 1, "swaps": [swap.json()],
            "primary_init_source_bindings": [{
                "source_event_file": "event/" + donor.event_file,
                "source_map": source.map_name, "source_part": source.part_name,
                "source_entity_id": source.entity_id, "source_archetype": asdict(source.archetype),
                "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": donor.part_sha256},
                "source_initialization": dict(humanoid.SOURCE_INITIALIZATION),
                "destination_map": row.map_name, "destination_part": row.part_name,
                "destination_entity_id": row.entity_id, "destination_original_talk_id": row.talk_id,
                "required_native_fields": ["talk_id", "unk_t18", "init_anim_id", "damage_anim_id", "provenance"]}
                for row in humans],
            "boss_contract": {"format": "bb-chalice-gascoigne-contract-v1", "arena": ARENA.key,
                "donor": donor.key, "runtime_status": "unobserved",
                "preserved_destination_events": [ARENA.completion_event, ARENA.co_op_entry_event],
                "source_map_event_zero_sha256": donor.map_event_zero_sha256,
                "source_map_initializers": [donor.health_initializer, donor.music_initializer, donor.wake_initializer],
                "retained_destination_helpers": [{
                    "map": row.map_name, "part": row.part_name, "entity_id": row.entity_id,
                    "archetype": asdict(row.archetype),
                    "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": gascoigne.BEAST_PINS[row.map_name]},
                    "source_initialization": {"talk_id": 0, "unk_t18": -1, "init_anim_id": -1, "damage_anim_id": -1},
                    "policy": "hidden invincible terminal proxy until exact event 12411800 completes"}
                    for row in proxies]},
            "scaling": {"enabled": bool(changes), "mechanism": "inferred_static_npc_clone_sp_effect",
                        "change_count": len(changes), "changes": [row.json() for row in changes],
                        "skip_count": len(skips), "skips": skips}}


def recipes():
    for donor in humanoid.DONORS.values():
        yield EncounterRecipe(arena=ARENA, donor=donor, adapter="chalice-gascoigne:source-combat",
            _patch=lambda destination, common, d=donor: patch_chalice_at_gascoigne(destination, d, common),
            _native_plan=lambda slots, npcs, effects, seed, d=donor:
                native_plan_chalice_at_gascoigne(d, slots, npcs, effects, seed),
            _actor_requirements=lambda slots: [])
