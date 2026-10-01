"""Source-pinned Shadows at six base arenas, and Living Failures at four.

The existing pair adapters supply the authored actor, generator and region
rosters. Destination entry, sounds, telemetry and rewards remain local.
These routes require native construction and gameplay checks before release.
"""
from __future__ import annotations

import re
from dataclasses import asdict

from tools.bb_inputs import read_blob
from . import living_failures_laurence_contract as lf
from . import shadows_orphan_contract as shadows
from .boss_canary import event_blocks
from .boss_contracts import ARENAS
from .logarius_donor import DESTINATION_FFX
from .maria_donor import _activation_without_destination_animations
from .model import Swap, slot_placement
from .one_reborn_donor import _retired, _telemetry, _verify, _replace_events, _noop
from .scaling import plan_scaling
from .wet_nurse_donor import DESTINATION_PART_PINS

DONOR_FILES = {
    "shadows-of-yharnam": shadows.SHADOWS_SOURCE.removeprefix("event/"),
    "living-failures": lf.DONOR_SOURCE.removeprefix("event/"),
}


def portable_group_arenas(donor_key):
    if donor_key == "shadows-of-yharnam":
        return ARENAS
    if donor_key == "living-failures":
        # Native preflight proves m23 and m35 contain different bytes for
        # effect/f000626200.fxr. The full source-bank union cannot preserve
        # the destination in BSB/Paarl; do not advertise those two routes.
        return tuple(arena for arena in ARENAS if arena.key not in
                     ("blood-starved-beast", "darkbeast-paarl"))
    raise ValueError("unsupported group donor")
INITIALIZER_COUNTS = {
    "shadows-of-yharnam": {12704806: 1, 12704807: 3, 12704812: 3,
                           12704815: 4, 12704825: 2, 12704830: 3},
    "living-failures": {13504865: 1, 13504880: 1, 13504881: 1,
                        13504885: 2, 13504890: 4, 13504895: 4,
                        13505655: 1, 13505656: 4, 13505661: 1,
                        13505662: 1, 13505680: 1},
}


def _check(arena, donor_key, destination, donor_source):
    if arena not in portable_group_arenas(donor_key):
        raise ValueError("unsupported group donor route")
    original = event_blocks(destination)
    _verify(original, arena.expected, arena.key)
    if donor_key == "shadows-of-yharnam":
        donor = shadows._verify(donor_source, shadows.DONOR_HASHES,
                                "Shadows donor", shadows.DONOR_ALTERNATES)
        shadows._validate_ids(shadows.DEFAULT_IDS, destination)
    else:
        donor = event_blocks(donor_source)
        lf._verify(donor, lf.DONOR_HASHES, "Living Failures donor")
        lf._validate_ids(lf.DEFAULT_IDS, destination)
    return original, donor


def _music(arena, block, phase_flag):
    witness = (f"EventFlag({arena.phase_music_event_flag})"
               if arena.phase_music_event_flag is not None else
               f"CharacterHasEventMessage({arena.actor}, {arena.phase_music_message})")
    return lf._replace_once(block, witness, f"EventFlag({phase_flag})", "phase music")


def _mapping(arena, donor_key):
    if donor_key == "shadows-of-yharnam":
        ids = shadows.DEFAULT_IDS
        return {**shadows.HELPER_MAP, **ids.event_map(),
                2705001: ids.generator_entity_first,
                2705002: ids.generator_entity_first + 1,
                2705003: ids.generator_entity_first + 2,
                12701800: arena.completion_event, 12704800: arena.start_flag,
                12704802: arena.health_bar_event, 12704804: arena.lockcam_event}
    # Reuse the pinned wave allocation, replacing Laurence's destination
    # bindings explicitly. Sound/region/camera literals never enter this graph.
    mapping = lf._mapping(lf.DEFAULT_IDS)
    mapping.update({lf.BODY_ONE: arena.actor, 13501850: arena.completion_event,
                    13504858: arena.start_flag, 13504852: arena.health_bar_event})
    # The notification guard is owned by the destination's health event.
    mapping[13504860] = arena.health_bar_event
    return mapping


def _guard_combat(block, completion, health_event):
    """Keep imported controllers asleep until health setup, and terminal-safe."""
    header = block.splitlines()[0] + "\n"
    block = lf._replace_once(block, header, header +
        f"    EndIf(EventFlag({completion}));\n"
        f"    WaitFor(EventFlag({health_event}) || EventFlag({completion}));\n"
        f"    EndIf(EventFlag({completion}));\n", "controller entry guard")
    # A loop may have been waiting when the completion flag changed. Check
    # again at every side effect which can revive combat or affect the player.
    return re.sub(r"(?m)^(\s*)(RequestCharacterAI(?:Command|Replan)\([^;]+;|"
                  r"DeactivateGenerator\([^;]+, Enabled\);|"
                  r"ChangeCharacterEnableState\([^;]+, Enabled\);|"
                  r"SetCharacterAIState\([^;]+, Enabled\);|"
                  r"SetSpEffect\(10000,[^;]+;|SpawnMapSFX\([^;]+;)$",
                  lambda match: f"{match[1]}EndIf(EventFlag({completion}));\n{match[0]}", block)


def patch_group_donor(arena, donor_key, destination, donor_source):
    original, donor = _check(arena, donor_key, destination, donor_source)
    mapping = _mapping(arena, donor_key)
    is_shadows = donor_key == "shadows-of-yharnam"
    ids = shadows.DEFAULT_IDS if is_shadows else lf.DEFAULT_IDS
    health_source = 12704802 if is_shadows else 13504852
    health = _telemetry(lf._remap(donor[health_source], mapping),
                        original[arena.health_bar_event])
    # Restore all bodies within the health controller before their AI is
    # enabled. Do not disable LF's referred-health proxy: referred damage
    # requires its body to stay enabled even while hidden below the arena.
    bodies = (shadows.ACTIVE_PRIMARY, 981300, 981301) if is_shadows else (
        arena.actor, ids.body_two_entity, ids.body_three_entity,
        ids.body_four_entity, ids.support_entity)
    restore = "".join(f"    ChangeCharacterEnableState({entity}, Enabled);\n"
                      for entity in bodies)
    health = lf._replace_once(health, "L4:\n", "L4:\n" + restore, "body restore")
    # LF's health graph waits for entry; generator controllers retain their
    # source initialization/phase gates and receive completion guards.
    sources = tuple(ids.event_map()) if is_shadows else tuple(INITIALIZER_COUNTS[donor_key])
    additions = {mapping[event]: lf._remap(donor[event], mapping) for event in sources}
    additions = {event: _guard_combat(block, arena.completion_event, arena.health_bar_event)
                 for event, block in additions.items()}
    calls = [row for event, count in INITIALIZER_COUNTS[donor_key].items()
             for row in shadows._initializer_rows(donor[0], event, count, mapping)]
    if is_shadows:
        bridge = f"""$Event({ids.bridge}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
    WaitFor(CharacterDead({shadows.ACTIVE_PRIMARY}) && CharacterDead(981300) && CharacterDead(981301));
    SetCharacterInvincibility({arena.actor}, Disabled);
    ForceCharacterDeath({arena.actor}, false);
}});"""
        bars = "".join(f"    DisplayBossHealthBar(Disabled, {entity}, {slot}, {name});\n"
                       for entity, slot, name in ((981310, 2, 212010), (981300, 1, 212020), (981301, 0, 212030)))
        cleanup = "".join(f"    ChangeCharacterEnableState({entity}, Disabled);\n"
                          f"    ForceCharacterDeath({entity}, false);\n"
                          for entity in shadows.HELPER_ENTITIES)
        generators = "".join(f"    DeactivateGenerator({ids.generator_entity_first + i}, Disabled);\n"
                             for i in range(3))
        additions[ids.bridge] = bridge
        additions[ids.destination_cleanup] = f"""$Event({ids.destination_cleanup}, Default, function() {{
    WaitFor(EventFlag({arena.completion_event}));
{generators}{bars}{cleanup}    SetEventFlag(12704808, OFF);
}});"""
        # Disable the inert terminal proxy only after destination activation
        # has completed, so native damage-based entry predicates remain live.
        hide = "".join(f"    ChangeCharacterEnableState({entity}, Disabled);\n"
                       for entity in bodies)
        additions[ids.helper_entry] = f"""$Event({ids.helper_entry}, Default, function() {{
    EndIf(EventFlag({arena.completion_event}));
{hide}    WaitFor(EventFlag({arena.start_flag}));
    SetCharacterAIState({arena.actor}, Disabled);
    SetCharacterInvincibility({arena.actor}, Enabled);
    ChangeCharacterEnableState({arena.actor}, Disabled);
}});"""
        calls.extend(f"    $InitializeEvent(0, {event});" for event in
                     (ids.bridge, ids.destination_cleanup, ids.helper_entry))
        camera = lf._remap(donor[12704804], mapping).replace(
            "SetLockcamSlotNumber(27, 0,",
            f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},")
        phase_flag = 12704808  # Source-owned phase signal, as in the pair adapter.
    else:
        additions[ids.generator_controller], additions[ids.support_controller] = lf._terminal_safe_controllers(
            additions[ids.generator_controller], additions[ids.support_controller],
            completion=arena.completion_event, enable_flag=ids.generator_enable_flag,
            phase_flag=ids.generator_phase_flag)
        additions[ids.lifecycle_cleanup] = lf._lifecycle_cleanup(
            ids.lifecycle_cleanup, arena.completion_event, ids, lf.GENERATOR_ENTITY_IDS)
        additions[ids.lifecycle_cleanup] = lf._replace_once(
            additions[ids.lifecycle_cleanup], "\n});", "\n    ClearSpEffect(10000, 8035);\n"
            + f"    DisplayBossHealthBar(Disabled, {ids.proxy_entity}, 0, 403000);\n"
            + "".join(f"    DeleteMapSFX({entity}, true);\n" for entity in lf.SFX_ENTITY_IDS)
            + "});", "player/SFX cleanup")
        calls.append(f"    $InitializeEvent(0, {ids.lifecycle_cleanup});")
        camera = lf._remap(donor[13504854], {
            **mapping, 13504854: arena.lockcam_event}).replace(
            "SetLockcamSlotNumber(35, 0,",
            f"SetLockcamSlotNumber({arena.lockcam_map}, {arena.lockcam_subarea},")
        phase_flag = ids.phase_music_flag
    retired = _retired(arena)
    edits = {event: _noop(original[event]) for event in retired}
    anchor = next((f"    $InitializeEvent(0, {event});" for event in reversed(arena.phase_slots)
                   if original[0].count(f"    $InitializeEvent(0, {event});") == 1), None)
    if anchor is None:
        raise ValueError("group donor lacks constructor anchor")
    edits.update({0: lf._replace_once(original[0], anchor,
                                     anchor + "\n" + "\n".join(calls), "constructor"),
                  arena.activation_event: _activation_without_destination_animations(
                      arena, original[arena.activation_event]),
                  arena.health_bar_event: health, arena.lockcam_event: camera,
                  arena.music_event: _music(arena, original[arena.music_event], phase_flag)})
    result = _replace_events(destination, edits).rstrip() + "\n\n" + "\n\n".join(additions.values()) + "\n"
    output = event_blocks(result)
    if set(output) != set(original) | set(additions):
        raise ValueError("group donor event identities changed")
    for event, body in original.items():
        if event not in edits and output[event] != body:
            raise ValueError("group donor changed unrelated destination event")
    if output[arena.completion_event] != original[arena.completion_event]:
        raise ValueError("group donor changed progression")
    copied = "\n".join((health, camera, *additions.values()))
    prefix = r"(?:127|270)" if is_shadows else r"(?:135|350)"
    remaining = set(map(int, re.findall(r"(?<!\d)" + prefix + r"\d+(?!\d)", copied)))
    if remaining - ({12704808} if is_shadows else set()):
        raise ValueError(f"group donor retains source-map literals: {sorted(remaining)}")
    return result


def native_plan_group_donor(arena, donor_key, slots, npcs, effects, seed):
    destination = read_blob(lf.BUNDLE, "event/" + arena.event_file).decode("utf-8-sig")
    source = read_blob(lf.BUNDLE, "event/" + DONOR_FILES[donor_key]).decode("utf-8-sig")
    patch_group_donor(arena, donor_key, destination, source)
    targets = sorted((row for row in slots if row.map_name.startswith(arena.map_prefix)
                      and row.entity_id == arena.actor), key=lambda row: row.key)
    if len(targets) != arena.destination_count or any(
            row.dummy or row.archetype != arena.archetype for row in targets):
        raise ValueError("group donor requires every original destination state")
    is_shadows = donor_key == "shadows-of-yharnam"
    primary_entity = shadows.SHADOWS[0] if is_shadows else lf.BODY_ONE
    primary_arch = shadows.ARCHETYPES[primary_entity] if is_shadows else lf.BODY_ONE_ARCHETYPE
    primary_map = "m27_00_00_00" if is_shadows else "m35_00_00_00"
    primary = lf._require(slots, primary_entity, primary_arch, primary_map)
    swap = Swap(targets[0].logical_key, [row.key for row in targets],
                {row.key: row.archetype for row in targets}, arena.archetype, primary_arch,
                warnings=["experimental group donor; arena geometry and gameplay unobserved"],
                destinations={row.key: slot_placement(row) for row in targets})
    changes, skips = plan_scaling([swap], targets, dict(npcs), dict(effects), boss_tiers=True)
    result = {"format": "bb-enemizer-plan-v2", "dry_run": True, "seed": seed,
              "swap_count": 1, "swaps": [swap.json()],
              "boss_actor_additions": [], "boss_region_additions": [],
              "boss_generator_additions": [], "primary_init_source_bindings": [],
              "boss_actor_scaling_requirements": [],
              "boss_contract": {"format": "bb-group-donor-contract-v1", "arena": arena.key,
                                "donor": donor_key, "runtime_status": "unobserved",
                                "source_hash_pins": dict(shadows.DONOR_HASHES if is_shadows else lf.DONOR_HASHES),
                                "preserved_destination_events": [arena.completion_event]},
              "scaling": {"enabled": bool(changes),
                          "mechanism": "inferred_static_npc_clone_sp_effect",
                          "change_count": len(changes), "changes": [row.json() for row in changes],
                          "skip_count": len(skips), "skips": skips}}
    # Existing pair planners own the fully pinned native source rosters. Feed
    # real targets into those helpers below; never infer provenance from IDs.
    for target in targets:
        target_pin = DESTINATION_PART_PINS[(target.map_name, target.entity_id)]
        if is_shadows:
            template = shadows.native_plan_shadows_at_orphan(
                slots, npcs, effects, seed, _target=target, _target_pin=target_pin)
            fields = ("boss_actor_additions", "boss_region_additions", "boss_generator_additions",
                      "primary_init_source_bindings", "boss_actor_scaling_requirements")
            for field in fields:
                result[field].extend(template[field])
        else:
            helpers = ((lf.PROXY, lf.PROXY_ARCHETYPE, lf.DEFAULT_IDS.proxy_entity, "ap_lf_proxy"),
                       (lf.BODY_TWO, lf.BODY_TWO_ARCHETYPE, lf.DEFAULT_IDS.body_two_entity, "ap_lf_body_two"),
                       (lf.BODY_THREE, lf.BODY_THREE_ARCHETYPE, lf.DEFAULT_IDS.body_three_entity, "ap_lf_body_three"),
                       (lf.BODY_FOUR, lf.BODY_FOUR_ARCHETYPE, lf.DEFAULT_IDS.body_four_entity, "ap_lf_body_four"),
                       (lf.SUPPORT, lf.SUPPORT_ARCHETYPE, lf.DEFAULT_IDS.support_entity, "ap_lf_support"))
            for entity, arch, new_entity, part in helpers:
                result["boss_actor_additions"].append(lf._actor_addition(
                    lf._require(slots, entity, arch, primary_map), target, new_entity, part))
            for field, rows in (("boss_region_additions", lf._regions(target)),
                                ("boss_sfx_additions", lf._sfx(target))):
                for row in rows:
                    row["destination_anchor_provenance"]["part_sha256"] = target_pin
                    if field == "boss_sfx_additions":
                        row["destination_part_name"] = target.collision_name
                result.setdefault(field, []).extend(rows)
            generators = lf._generators(target)
            for row in generators:
                row["destination_part_name"] = target.collision_name
            result["boss_generator_additions"].extend(generators)
            result["primary_init_source_bindings"].append({
                "source_map": primary.map_name, "source_part": primary.part_name,
                "source_entity_id": primary.entity_id, "source_archetype": asdict(primary.archetype),
                "source_provenance": {"format": "bb-boss-actor-pin-v1", "part_sha256": lf.PART_PINS[lf.BODY_ONE]},
                "source_initialization": shadows._initialization(),
                "destination_map": target.map_name, "destination_part": target.part_name,
                "destination_entity_id": target.entity_id})
    if not is_shadows:
        result["boss_actor_scaling_requirements"] = [{
            "destination_map": row["destination_map"], "destination_part": row["destination_part"],
            "parent_logical_key": swap.logical_key,
            "source_npc_param_id": row["source_archetype"]["npc_param_id"],
            "strategy": "allocate_distinct_verified_helper_clone"}
            for row in result["boss_actor_additions"]]
        # MapSFX dependencies use the area's binder (unlike the explicitly
        # witnessed character roots delivered into subarea banks).
        ffx_file, ffx_hash = DESTINATION_FFX[arena.key]
        result["boss_ffx_merges"] = [{
            "source_file": "frpg_sfxbnd_m35.ffxbnd.dcx",
            "source_sha256": "fd656c4a23d3a45202e7d0a5aec1b4f3bea95f71d96af3d1b4b181bcf24b931e",
            "destination_file": ffx_file, "destination_sha256": ffx_hash,
            "required_effect_ids": [640320, 640321, 640322, 640323, 640324],
            "policy": "preserve_destination_union_source_v1"}]
    return result
