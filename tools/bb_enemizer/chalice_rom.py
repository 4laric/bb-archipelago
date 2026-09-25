"""Chalice humanoids at Rom, retaining the lake entry and blood-moon sequence."""
from dataclasses import asdict, replace
import re

from . import ebrietas_rom_contract as rom
from .boss_contracts import CLERIC_ARENA
from .boss_canary import event_blocks
from .chalice_humanoid_donors import DONORS, SOURCE_INITIALIZATION, COMMON_EVENT_PINS
from .encounter_recipes import EncounterRecipe
from .model import Swap
from .scaling import plan_scaling

CLEANUP = 12997300
RETIRED = (13204000, 13204050, 13204730, 13204807, 13204808, 13204809, 13204810)
ARENA = replace(CLERIC_ARENA, key='rom', event_file='m32_00_00_00.emevd.dcx.js',
    map_prefix='m32_00_', actor=rom.ROM, archetype=rom.ROM_ARCHETYPE,
    destination_count=2, completion_event=13201800, start_flag=13204800,
    health_bar_event=13204802, health_bar_label=510000, activation_event=13201802,
    music_event=13204803, lockcam_event=13204804, lockcam_map=32, lockcam_subarea=0,
    phase_slots=RETIRED, expected=rom.ARENA_HASHES)


def patch_rom(destination, donor_source, donor):
    original = rom._verify(destination, rom.ARENA_HASHES, 'Rom arena', rom.ROM_ARENA_ALTERNATES)
    rom._verify(donor_source, COMMON_EVENT_PINS, 'chalice humanoid')
    if CLEANUP in rom._original_ids() or re.search(r'(?<!\d)12997300(?!\d)', destination):
        raise ValueError('Rom chalice cleanup ID collision')
    health = rom._replace_once(original[13204802],
        'DisplayBossHealthBar(Enabled, 3200800, 0, 510000);',
        f'DisplayBossHealthBar(Enabled, 3200800, 0, {donor.health_name_id});', 'health name')
    # Rom's source entry starts on first damage. Keep that local trigger and
    # immortality until health setup; chalice AI starts at the same boundary.
    if donor.key != 'keeper-of-old-lords':
        health = rom._replace_once(health, '    SetCharacterAIState(3200800, Enabled);',
            '    ForceAnimationPlayback(3200800, 7001, false, false, false);\n'
            '    SetCharacterAIState(3200800, Enabled);', 'humanoid wake')
    music = rom._replace_once(original[13204803],
        'CharacterHasEventMessage(3200800, 10)', 'CharacterHasEventMessage(3200800, 500)', 'phase music')
    constructor = rom._replace_once(original[0], '    $InitializeEvent(0, 13204821);',
        f'    $InitializeEvent(0, 13204821);\n    $InitializeEvent(0, {CLEANUP});', 'cleanup anchor')
    lines = [f'    ChangeCharacterEnableState({3200200+i}, Disabled);\n'
             f'    SetCharacterAIState({3200200+i}, Disabled);' for i in range(30)]
    deaths = [f'    ForceCharacterDeath({3200200+i}, false);' for i in range(30)]
    cleanup = (f'$Event({CLEANUP}, Default, function() {{\n' + '\n'.join(lines)
               + '\n    WaitFor(EventFlag(13201800));\n' + '\n'.join(deaths) + '\n});\n')
    edits = {n: rom._end_event(original[n]) for n in RETIRED}
    edits.update({0: constructor, 13204802: health, 13204803: music})
    output = rom._replace_events(destination, edits).rstrip() + '\n\n' + cleanup
    blocks = event_blocks(output)
    if set(blocks) != set(original) | {CLEANUP}:
        raise ValueError('Rom chalice event identity drift')
    for n, block in original.items():
        if n not in edits and blocks[n] != block:
            raise ValueError('Rom chalice changed unrelated destination event')
    return output


def native_plan(slots, npcs, effects, seed, donor):
    destinations = rom._require(slots, rom.ROM, rom.ROM_ARCHETYPE)
    sources = [s for s in slots if s.map_name == donor.map_name and
               s.part_name == donor.part_name and s.entity_id == donor.actor
               and s.archetype == donor.archetype and not s.dummy]
    if len(sources) != 1 or {s.map_name for s in destinations} != set(rom.ROM_STATES):
        raise ValueError('Rom chalice source or destination actor drift')
    source = sources[0]
    swap = Swap(destinations[0].logical_key, [s.key for s in destinations],
        {s.key:s.archetype for s in destinations}, rom.ROM_ARCHETYPE, donor.archetype,
        destinations={s.key:{'map_name':s.map_name,'entity_id':s.entity_id,
                             'x':s.x,'y':s.y,'z':s.z} for s in destinations})
    bindings = [{
        'source_map':source.map_name,'source_part':source.part_name,'source_entity_id':source.entity_id,
        'source_archetype':asdict(source.archetype),
        'source_provenance':rom._pin(donor.part_sha256),
        'source_initialization':dict(SOURCE_INITIALIZATION),
        'destination_map':s.map_name,'destination_part':s.part_name,'destination_entity_id':s.entity_id,
    } for s in destinations]
    retained = []
    for state in rom.ROM_STATES:
        specs = [(3200200+i, rom.SPIDER_ARCHETYPE, None, rom.ROM_SPIDER_PINS[state][i],
                  'retain_native_part_disabled_alive_until_destination_completion') for i in range(30)]
        specs += [(3200801, arch, part, rom.POSTBOSS_PINS[state][part],
                   'retain_native_post_defeat_actor_unchanged') for part, arch in rom.POSTBOSS_ARCHETYPES.items()]
        for entity, arch, part, fingerprint, policy in specs:
            found = [s for s in slots if s.map_name == state and s.entity_id == entity and
                     s.archetype == arch and (part is None or s.part_name == part)]
            if len(found) != 1:
                raise ValueError('Rom retained helper identity drift')
            retained.append({'map':state,'part':found[0].part_name,'entity_id':entity,
                'archetype':asdict(arch),'source_provenance':rom._pin(fingerprint),
                'source_initialization':rom._initialization(),'policy':policy})
    changes, skips = plan_scaling([swap], destinations, npcs, effects, boss_tiers=True)
    return {'format':'bb-enemizer-plan-v2','dry_run':True,'seed':seed,'swap_count':1,'swaps':[swap.json()],
        'primary_init_source_bindings':bindings,
        'boss_contract':{'arena':'rom','donor':donor.key,'validation_status':'static-contract-only',
                         'retained_destination_helpers':retained,
                         'preserved_destination_events':[13201800,13201801,13201802,13201803,13201804]},
        'scaling':{'enabled':bool(changes),'mechanism':'inferred_static_npc_clone_sp_effect',
                   'change_count':len(changes),'changes':[c.json() for c in changes],
                   'skip_count':len(skips),'skips':skips}}


def recipes():
    return tuple(EncounterRecipe(ARENA, d, 'chalice-rom:humanoid',
        lambda dest, source, d=d:patch_rom(dest,source,d),
        lambda slots,npcs,effects,seed,d=d:native_plan(slots,npcs,effects,seed,d),
        lambda slots:[]) for d in DONORS.values())
