#!/usr/bin/env python3
"""Compile reviewed arena/combat contracts into an experimental boss overlay.

Uses the owner's original binaries and the pinned development compiler. No
overlay is activated and no game process is started. Runtime behavior remains
unvalidated even after all structural and serialization checks pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bb_enemizer.scripted_fallbacks import patch_initializers, scripted_fallback_keys
from tools.bb_enemizer.boss_contracts import (
    ARENAS as ARENA_CONTRACTS, PACKAGES as COMBAT_PACKAGES, COMPATIBILITY, event_blocks, patch_contract_swap,
    plan_contract_swap, actor_addition_requirements,
)
from tools.bb_enemizer.witch_amygdala_contract import (
    patch_witch_at_amygdala, native_plan_witch_at_amygdala)
from tools.bb_enemizer.amelia_witch_contract import (
    patch_amelia_at_witch, native_plan_amelia_at_witch)
from tools.bb_enemizer.micolash_moon_contract import (
    patch_micolash_at_moon, native_plan_micolash_at_moon)
from tools.bb_enemizer.micolash_gehrman_contract import (
    patch_micolash_at_gehrman, native_plan_micolash_at_gehrman)
from tools.bb_enemizer.one_reborn_ebrietas_contract import (
    patch_one_reborn_at_ebrietas, native_plan_one_reborn_at_ebrietas)
from tools.bb_enemizer.rom_one_reborn_contract import (
    patch_rom_at_one_reborn, native_plan_rom_at_one_reborn)
from tools.bb_enemizer.celestial_paarl_contract import (
    patch_celestial_emissary_at_paarl, native_plan_celestial_at_paarl)
from tools.bb_enemizer.ludwig_shadows_contract import (
    patch_ludwig_at_shadows, native_plan_ludwig_at_shadows)
from tools.bb_enemizer.maria_living_failures_contract import (
    patch_maria_at_living_failures, native_plan_maria_at_living_failures,
    maria_living_failures_external_reference_requirement)
from tools.bb_enemizer.shadows_orphan_contract import (
    patch_shadows_at_orphan, native_plan_shadows_at_orphan)
from tools.bb_enemizer.laurence_living_failures_contract import (
    patch_laurence_at_living_failures, native_plan_laurence_at_living_failures)
from tools.bb_enemizer.boss_pool import (
    assign_donors, combine_native_plans, compose_event_patches, validate_terminal_predicates,
    combine_ordinary_and_boss_plans,
)
from tools.bb_enemizer.encounter_recipes import reusable_recipes
from tools.bb_enemizer.chalice_recipes import chalice_recipes, validate_original_source
from tools.bb_enemizer.good_boss_pool import assign_good_bosses
from tools.bb_enemizer.boss_entrances import skip_replacement_entrance
from tools.bb_enemizer.inventory import load_slots
from tools.bb_enemizer.gascoigne_contract import (
    ProjectOwnedIds, NativeActorPin, patch_gascoigne_at_cleric, native_plan_gascoigne_at_cleric,
)
from tools.bb_enemizer.gascoigne_arena import (
    ClericGascoigneIds, patch_cleric_at_gascoigne, native_plan_cleric_at_gascoigne,
)
from tools.bb_enemizer.ludwig_contract import LudwigIds, patch_ludwig_at_cleric, native_plan_ludwig_at_cleric, EVENTS as LUDWIG_EVENTS
from tools.bb_enemizer.laurence_contract import LaurenceIds, patch_laurence_at_cleric, native_plan_laurence_at_cleric
from tools.bb_enemizer.laurence_arena import patch_cleric_at_laurence, native_plan_cleric_at_laurence
from tools.bb_enemizer.ludwig_arena import patch_cleric_at_ludwig, native_plan_cleric_at_ludwig
from tools.bb_enemizer.laurence_ludwig_contract import (
    patch_laurence_at_ludwig, native_plan_laurence_at_ludwig,
)
from tools.bb_enemizer.bsb_laurence_contract import patch_bsb_at_laurence, native_plan_bsb_at_laurence
from tools.bb_enemizer.bsb_maria_contract import patch_bsb_at_maria, native_plan_bsb_at_maria
from tools.bb_enemizer.bsb_orphan_contract import (
    patch_bsb_at_orphan, native_plan_bsb_at_orphan,
)
from tools.bb_enemizer.ludwig_orphan_contract import (
    patch_ludwig_at_orphan, native_plan_ludwig_at_orphan,
)
from tools.bb_enemizer.logarius_contract import (
    patch_logarius_at_bsb, native_plan_logarius_at_bsb,
    helper_scaling_parents as logarius_helper_scaling_parents,
)
from tools.bb_enemizer.bsb_logarius_contract import patch_bsb_at_logarius, native_plan_bsb_at_logarius
from tools.bb_enemizer.paarl_logarius_contract import patch_paarl_at_logarius, native_plan_paarl_at_logarius
from tools.bb_enemizer.logarius_wet_nurse_contract import (
    patch_logarius_at_wet_nurse, native_plan_logarius_at_wet_nurse)
from tools.bb_enemizer.shadows_celestial_contract import patch_shadows_at_celestial_emissary, native_plan_shadows_at_celestial_emissary
from tools.bb_enemizer.witch_one_reborn_contract import patch_witch_at_one_reborn, native_plan_witch_at_one_reborn
from tools.bb_enemizer.one_reborn_shadows_contract import patch_one_reborn_at_shadows, native_plan_one_reborn_at_shadows
from tools.bb_enemizer.celestial_rom_contract import patch_celestial_emissary_at_rom, native_plan_celestial_at_rom
from tools.bb_enemizer.moon_micolash_contract import patch_moon_at_micolash, native_plan_moon_at_micolash
from tools.bb_enemizer.gascoigne_witch_contract import patch_gascoigne_at_witch, native_plan_gascoigne_at_witch
from tools.bb_enemizer.wet_nurse_logarius_contract import patch_wet_nurse_at_logarius, native_plan_wet_nurse_at_logarius
from tools.bb_enemizer.paarl_wet_nurse_contract import patch_paarl_at_wet_nurse, native_plan_paarl_at_wet_nurse
from tools.bb_enemizer.wet_nurse_bsb_contract import (
    patch_wet_nurse_at_bsb, native_plan_wet_nurse_at_bsb)
from tools.bb_enemizer.bsb_wet_nurse_contract import patch_bsb_at_wet_nurse, native_plan_bsb_at_wet_nurse
from tools.bb_enemizer.amygdala_celestial_emissary_contract import (
    patch_amygdala_at_celestial_emissary, native_plan_amygdala_at_celestial_emissary)
from tools.bb_enemizer.bsb_celestial_emissary_contract import (
    patch_bsb_at_celestial_emissary, native_plan_bsb_at_celestial_emissary)
from tools.bb_enemizer.bsb_living_failures_contract import patch_bsb_at_living_failures, native_plan_bsb_at_living_failures
from tools.bb_enemizer.living_failures_maria_contract import (
    patch_living_failures_at_maria, native_plan_living_failures_at_maria)
from tools.bb_enemizer.living_failures_laurence_contract import (
    patch_living_failures_at_laurence, native_plan_living_failures_at_laurence)
from tools.bb_enemizer.ebrietas_rom_contract import (
    patch_ebrietas_at_rom, native_plan_ebrietas_at_rom, ebrietas_rom_helper_scaling_parents)
from tools.bb_enemizer.rom_ebrietas_contract import (patch_rom_at_ebrietas, native_plan_rom_at_ebrietas,
    helper_scaling_parents as rom_helper_scaling_parents)
from tools.bb_enemizer.orphan_gascoigne_contract import patch_orphan_at_gascoigne, native_plan_orphan_at_gascoigne
from tools.bb_enemizer.orphan_contract import (
    OrphanIds, NativeActorPin as OrphanActorPin,
    patch_orphan_at_cleric, native_plan_orphan_at_cleric,
)
from tools.bb_enemizer.gehrman_micolash_contract import (
    patch_gehrman_at_micolash, native_plan_gehrman_at_micolash)
from tools.bb_enemizer.final_boss_contracts import (
    GEHRMAN_ARENA, MOON_ARENA, GEHRMAN_PACKAGE, MOON_PACKAGE, FinalAttachmentIds,
    patch_gehrman_at_moon, patch_moon_at_gehrman, plan_final_boss_swap,
)
from tools.bb_enemizer.maria_contract import (
    MARIA_PACKAGE, MariaClericAttachmentIds, ClericMariaAttachmentIds,
    patch_maria_at_cleric, patch_cleric_at_maria,
    native_plan_maria_at_cleric, native_plan_cleric_at_maria,
)
from tools.bb_enemizer.maria_amelia_contract import (
    MariaAmeliaAttachmentIds, maria_at_amelia_external_reference_requirement,
    native_plan_maria_at_amelia, patch_maria_at_amelia,
)
from tools.bb_enemizer.scaling import load_params
from tools.bb_enemizer.boss_actor_scaling import allocate_actor_scaling
from tools.bb_inputs import read_blob, read_prefix
from tools.build_boss_canary import compile_events
from tools.build_boss_catalog import build as build_catalog
from tools.build_boss_shuffle import check_output
from tools.build_cathedral_emevd import DARKSCRIPT_SHA256

ARENAS = {arena.key: arena for arena in ARENA_CONTRACTS}
PACKAGES = {package.key: package for package in COMBAT_PACKAGES}


@dataclass(frozen=True)
class SpecialEndpoint:
    """Minimal event identity for a reviewed directed special adapter."""

    key: str
    event_file: str


GASCOIGNE_ENDPOINT = SpecialEndpoint('father-gascoigne', 'm24_01_00_00.emevd.dcx.js')
# Special endpoints dispatch through their explicit combat/arena adapters.
ARENAS[GASCOIGNE_ENDPOINT.key] = GASCOIGNE_ENDPOINT
PACKAGES[GASCOIGNE_ENDPOINT.key] = GASCOIGNE_ENDPOINT
LAURENCE_ENDPOINT = SpecialEndpoint('laurence', 'm34_00_00_00.emevd.dcx.js')
ARENAS[LAURENCE_ENDPOINT.key] = LAURENCE_ENDPOINT
LUDWIG_ENDPOINT = SpecialEndpoint('ludwig', 'm34_00_00_00.emevd.dcx.js')
ARENAS[LUDWIG_ENDPOINT.key] = LUDWIG_ENDPOINT
PACKAGES[LUDWIG_ENDPOINT.key] = LUDWIG_ENDPOINT
PACKAGES[LAURENCE_ENDPOINT.key] = LAURENCE_ENDPOINT
PACKAGES['orphan-of-kos'] = SpecialEndpoint('orphan-of-kos', 'm36_00_00_00.emevd.dcx.js')
ARENAS['orphan-of-kos'] = SpecialEndpoint('orphan-of-kos', 'm36_00_00_00.emevd.dcx.js')
PACKAGES['martyr-logarius'] = SpecialEndpoint('martyr-logarius', 'm25_00_00_00.emevd.dcx.js')
ARENAS['martyr-logarius'] = PACKAGES['martyr-logarius']
ARENAS['mergos-wet-nurse'] = SpecialEndpoint('mergos-wet-nurse', 'm26_00_00_00.emevd.dcx.js')
PACKAGES['mergos-wet-nurse'] = ARENAS['mergos-wet-nurse']
ARENAS['celestial-emissary'] = SpecialEndpoint('celestial-emissary', 'm24_02_00_00.emevd.dcx.js')
PACKAGES['celestial-emissary'] = ARENAS['celestial-emissary']
ARENAS['living-failures'] = SpecialEndpoint('living-failures', 'm35_00_00_00.emevd.dcx.js')
PACKAGES['living-failures'] = ARENAS['living-failures']
PACKAGES['rom'] = SpecialEndpoint('rom', 'm32_00_00_00.emevd.dcx.js')
ARENAS['rom'] = PACKAGES['rom']
ARENAS['witch-of-hemwick'] = SpecialEndpoint('witch-of-hemwick', 'm22_00_00_00.emevd.dcx.js')
PACKAGES['witch-of-hemwick'] = ARENAS['witch-of-hemwick']
ARENAS['micolash'] = SpecialEndpoint('micolash', 'm26_00_00_00.emevd.dcx.js')
PACKAGES['micolash'] = ARENAS['micolash']
ARENAS['the-one-reborn'] = SpecialEndpoint('the-one-reborn', 'm28_00_00_00.emevd.dcx.js')
PACKAGES['the-one-reborn'] = ARENAS['the-one-reborn']
ARENAS['shadows-of-yharnam'] = SpecialEndpoint('shadows-of-yharnam', 'm27_00_00_00.emevd.dcx.js')
PACKAGES['shadows-of-yharnam'] = ARENAS['shadows-of-yharnam']
FINAL_ARENAS = {arena.key: arena for arena in (GEHRMAN_ARENA, MOON_ARENA)}
FINAL_COMPATIBILITY = {'gehrman': ('moon-presence',), 'moon-presence': ('gehrman',)}
FINAL_ATTACHMENTS = {'gehrman': FinalAttachmentIds(12104917, 12104918),
                     'moon-presence': FinalAttachmentIds(12104907, 12104908)}
for package in (GEHRMAN_PACKAGE, MOON_PACKAGE, MARIA_PACKAGE):
    # Their encounter sources also provide the event-file identity used here;
    # their distinct arena/terminal contracts are passed to the pair planner.
    ARENAS[package.key] = package
    PACKAGES[package.key] = package

CHALICE_PACKAGES = {recipe.donor.key: recipe.donor for recipe in chalice_recipes().values()}
# Explicit direct builds only: reviewed_compatibility remains the main-game pool.
PACKAGES.update(CHALICE_PACKAGES)

MARIA_ATTACHMENTS = MariaClericAttachmentIds(12990011)
CLERIC_MARIA_ATTACHMENTS = ClericMariaAttachmentIds(12990012, 12990013, 12990014, 12990015)
MARIA_AMELIA_ATTACHMENTS = MariaAmeliaAttachmentIds(12990016)
MARIA_COMPATIBILITY = {
    'cleric-beast': ('lady-maria',),
    'lady-maria': ('cleric-beast', 'blood-starved-beast', 'living-failures'),
    'vicar-amelia': ('lady-maria',),
}

LAURENCE_COMPATIBILITY = {
    'cleric-beast': ('laurence',),
    'laurence': ('cleric-beast', 'blood-starved-beast', 'living-failures'),
}

LUDWIG_COMPATIBILITY = {
    'cleric-beast': ('ludwig',),
    'ludwig': ('cleric-beast', 'laurence'),
}

ORPHAN_COMPATIBILITY = {
    'cleric-beast': ('orphan-of-kos',),
    'orphan-of-kos': ('blood-starved-beast', 'ludwig'),
}

LOGARIUS_COMPATIBILITY = {
    'blood-starved-beast': ('martyr-logarius',),
    'martyr-logarius': ('blood-starved-beast', 'darkbeast-paarl', 'mergos-wet-nurse'),
}

GASCOIGNE_COMPATIBILITY = {
    'cleric-beast': ('father-gascoigne',),
    'father-gascoigne': ('cleric-beast', 'orphan-of-kos'),
}


WET_NURSE_COMPATIBILITY = {
    'blood-starved-beast': ('mergos-wet-nurse',),
    'mergos-wet-nurse': ('blood-starved-beast', 'martyr-logarius', 'darkbeast-paarl'),
}


WITCH_COMPATIBILITY = {'amygdala': ('witch-of-hemwick',),
                       'witch-of-hemwick': ('vicar-amelia', 'father-gascoigne')}


LIVING_FAILURES_COMPATIBILITY = {'living-failures': ('blood-starved-beast', 'lady-maria', 'laurence')}


ROM_COMPATIBILITY = {'ebrietas': ('rom',), 'rom': ('ebrietas', 'celestial-emissary')}

CELESTIAL_COMPATIBILITY = {'darkbeast-paarl': ('celestial-emissary',),
                           'celestial-emissary': ('amygdala', 'shadows-of-yharnam', 'blood-starved-beast')}
MICOLASH_COMPATIBILITY = {'moon-presence': ('micolash',),
                          'micolash': ('gehrman', 'moon-presence'),
                          'gehrman': ('micolash',)}
ONE_REBORN_COMPATIBILITY = {'ebrietas': ('the-one-reborn',),
                            'the-one-reborn': ('rom', 'witch-of-hemwick')}
SHADOWS_COMPATIBILITY = {'orphan-of-kos': ('shadows-of-yharnam',),
                         'shadows-of-yharnam': ('ludwig', 'the-one-reborn')}


def reviewed_compatibility() -> dict[str, tuple[str, ...]]:
    """Closed roster assembled from explicitly reviewed directed adapters."""
    graph = {}
    for section in (
        COMPATIBILITY,
        MARIA_COMPATIBILITY,
        LAURENCE_COMPATIBILITY,
        LUDWIG_COMPATIBILITY,
        ORPHAN_COMPATIBILITY,
        LOGARIUS_COMPATIBILITY,
        GASCOIGNE_COMPATIBILITY,
        ROM_COMPATIBILITY,
        LIVING_FAILURES_COMPATIBILITY,
        WET_NURSE_COMPATIBILITY,
        WITCH_COMPATIBILITY,
        CELESTIAL_COMPATIBILITY,
        MICOLASH_COMPATIBILITY,
        ONE_REBORN_COMPATIBILITY,
        SHADOWS_COMPATIBILITY,
        FINAL_COMPATIBILITY,
    ):
        for arena, donors in section.items():
            graph[arena] = tuple(dict.fromkeys((*graph.get(arena, ()), *donors)))
    for arena, donor in reusable_recipes():
        graph[arena] = tuple(dict.fromkeys((*graph.get(arena, ()), donor)))
    return dict(sorted(graph.items()))


def good_boss_routes() -> set[tuple[str, str]]:
    return {(arena, donor) for arena, donors in reviewed_compatibility().items()
            for donor in donors} | set(chalice_recipes())


def dlc_pair_flags(arena, package) -> tuple[bool, bool, bool, bool]:
    """Directed dispatch is per encounter, including inside reciprocal pools."""
    return (package.key == 'ludwig', package.key == 'laurence',
            arena.key == 'ludwig', arena.key == 'laurence')


def is_laurence_ludwig_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('ludwig', 'laurence')


def is_bsb_orphan_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('orphan-of-kos', 'blood-starved-beast')


def is_ludwig_orphan_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('orphan-of-kos', 'ludwig')


def is_logarius_bsb_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('blood-starved-beast', 'martyr-logarius')


def is_bsb_logarius_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('martyr-logarius', 'blood-starved-beast')


def is_shadows_celestial_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('celestial-emissary', 'shadows-of-yharnam')


def is_witch_one_reborn_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('the-one-reborn', 'witch-of-hemwick')


def is_one_reborn_shadows_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('shadows-of-yharnam', 'the-one-reborn')


def is_celestial_rom_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('rom', 'celestial-emissary')


def is_moon_micolash_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('micolash', 'moon-presence')


def is_gascoigne_witch_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('witch-of-hemwick', 'father-gascoigne')


def is_wet_nurse_logarius_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('martyr-logarius', 'mergos-wet-nurse')


def is_paarl_wet_nurse_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('mergos-wet-nurse', 'darkbeast-paarl')


def is_paarl_logarius_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('martyr-logarius', 'darkbeast-paarl')


def is_logarius_wet_nurse_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('mergos-wet-nurse', 'martyr-logarius')


def is_wet_nurse_bsb_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('blood-starved-beast', 'mergos-wet-nurse')


def is_micolash_moon_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('moon-presence', 'micolash')


def is_micolash_gehrman_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('gehrman', 'micolash')


def is_one_reborn_ebrietas_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('ebrietas', 'the-one-reborn')


def is_rom_one_reborn_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('the-one-reborn', 'rom')


def is_ludwig_shadows_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('shadows-of-yharnam', 'ludwig')


def is_shadows_orphan_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('orphan-of-kos', 'shadows-of-yharnam')


def is_maria_living_failures_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('living-failures', 'lady-maria')


def is_laurence_living_failures_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('living-failures', 'laurence')


def is_celestial_paarl_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('darkbeast-paarl', 'celestial-emissary')


def is_witch_amygdala_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('amygdala', 'witch-of-hemwick')


def is_gehrman_micolash_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('micolash', 'gehrman')


def is_amelia_witch_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('witch-of-hemwick', 'vicar-amelia')


def is_amygdala_celestial_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('celestial-emissary', 'amygdala')


def is_bsb_celestial_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('celestial-emissary', 'blood-starved-beast')


def is_living_failures_maria_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('lady-maria', 'living-failures')


def is_living_failures_laurence_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('laurence', 'living-failures')


def is_ebrietas_rom_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('rom', 'ebrietas')


def is_rom_ebrietas_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('ebrietas', 'rom')


def is_bsb_living_failures_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('living-failures', 'blood-starved-beast')


def is_bsb_wet_nurse_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('mergos-wet-nurse', 'blood-starved-beast')


def is_orphan_gascoigne_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('father-gascoigne', 'orphan-of-kos')


def is_maria_pair(arena, package) -> bool:
    return package is not None and 'lady-maria' in (arena.key, package.key)


def maria_external_reference(args, plan: dict, arena) -> dict:
    """Bind Maria's unplaced operand to original map/event evidence."""
    requirement = (maria_at_amelia_external_reference_requirement()
                   if arena.key == 'vicar-amelia' else
                   maria_living_failures_external_reference_requirement()
                   if arena.key == 'living-failures' else {
                       'entity_id': 3500801, 'source_map': 'm35_00_00_00',
                       'source_event_file': 'm35_00_00_00.emevd.dcx', 'source_event_id': 13504802,
                       'source_actor': 3500800, 'destination_event_file': arena.event_file.removesuffix('.js'),
                       'destination_event_id': arena.health_bar_event, 'destination_actor': arena.actor,
                   })
    source_map = 'm35_00_00_00'
    destination_maps = sorted({row['destination_map'] for row in plan['boss_actor_initializations']})
    reports = {name: inspect_actor_map(args, name) for name in [source_map, *destination_maps]}
    if any(requirement['entity_id'] in report['entity_ids'] for report in reports.values()):
        raise ValueError('Maria opaque event target unexpectedly resolves to an MSB entity')
    return {
        'format': 'bb-boss-external-reference-v1', 'entity_id': requirement['entity_id'],
        'source_map': requirement['source_map'], 'destination_maps': destination_maps,
        'source_map_sha256': reports[source_map]['map_sha256'],
        'destination_map_sha256': {name: reports[name]['map_sha256'] for name in destination_maps},
        'source_event_file': requirement['source_event_file'],
        'source_event_sha256': digest(args.events / requirement['source_event_file']),
        'source_event_id': requirement['source_event_id'], 'source_actor': requirement['source_actor'],
        'destination_event_file': requirement['destination_event_file'],
        'destination_event_id': requirement['destination_event_id'],
        'destination_actor': requirement['destination_actor'],
        'evidence_status': 'inferred', 'runtime_status': 'unobserved',
    }

# Project-owned allocation, not original game IDs. The Gascoigne planner scans
# every bundled EMEVD operand and MSB actor before accepting these numbers.

LUDWIG_ALLOCATION = LudwigIds(980002, 12990200,
    {event: 12990201 + index for index, event in enumerate(LUDWIG_EVENTS)},
    'ap_ludwig_phase_two', 'BB AP Ludwig phase-two allocation v1; full corpus collision scan')

ORPHAN_ALLOCATION = OrphanIds(
    980003, 980004, 12990600, 12990601, 12990602, 12990603, 12990604, 12990605,
    'ap_orphan_phase_two', 'ap_orphan_support',
    'BB AP Orphan allocation v1; original full-corpus collision scan',
)

GASCOIGNE_ALLOCATION = ProjectOwnedIds(
    beast_entity_id=980001,
    phase_event_ids={12414807: 12414780, 12414808: 12414781, 12414809: 12414782},
    terminal_bridge_event_id=12414783, destination_part='ap_gascoigne_beast',
    evidence=('BB AP Gascoigne-at-Cleric allocation v2; full original corpus collision scan; '
              '12414 flag group and 12414780-12414783 probed backed and clear in live client'),
)

GASCOIGNE_ARENA_ATTACHMENTS = ClericGascoigneIds(
    phase=12990400, cloth_phase=12990401, limbs=12990402, cloth=12990403,
    beast_cleanup=12990404,
)


def is_gascoigne_donor_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('cleric-beast', 'father-gascoigne')


def is_gascoigne_arena_pair(arena, package) -> bool:
    return package is not None and (arena.key, package.key) == ('father-gascoigne', 'cleric-beast')


def is_gascoigne_pair(arena, package) -> bool:
    return is_gascoigne_donor_pair(arena, package) or is_gascoigne_arena_pair(arena, package)


def inspect_actor_map(args, name: str) -> dict:
    """Read original map witnesses once per build, never from staged output."""
    cache = getattr(args, '_actor_pin_cache', None)
    if cache is None:
        args._actor_pin_cache = cache = {}
    if name not in cache:
        if Path(name).name != name or not re.fullmatch(r'm\d\d_\d\d_\d\d_\d\d', name):
            raise ValueError('invalid actor source map name')
        path = next((args.maps / (name + suffix) for suffix in ('.msb.dcx', '.msb')
                     if (args.maps / (name + suffix)).is_file()), None)
        if path is None and name.startswith('m29_'):
            directory = name[:-2] + '00'
            path = next((args.maps / directory / (name + suffix)
                         for suffix in ('.msb.dcx', '.msb')
                         if (args.maps / directory / (name + suffix)).is_file()), None)
        if path is None:
            raise ValueError('missing actor source map state ' + name)
        run = subprocess.run(command_for(args) + ['--boss-actor-pins', str(path)],
                             check=True, capture_output=True, text=True)
        report = json.loads(run.stdout)
        if report.get('format') != 'bb-boss-actor-pins-v1' or report.get('map') != name:
            raise ValueError('invalid native actor pin report')
        if len({part['name'] for part in report['parts']}) != len(report['parts']):
            raise ValueError('ambiguous native actor source parts')
        cache[name] = report
    return cache[name]


def pin_actor_requirements(args, requirements: list[dict]) -> list[dict]:
    """Bind declared placements/initializations to exact installed donor Parts."""
    output = []
    for requirement in requirements:
        report = inspect_actor_map(args, requirement['source_map'])
        parts = {part['name']: part for part in report['parts']}
        donor = parts[requirement['source_part']]
        if (donor['entity_id'] != requirement['source_entity_id']
                or donor['source_archetype'] != requirement['source_archetype']
                or donor['source_initialization'] is None):
            raise ValueError('actor requirement differs from original native source')
        pinned = dict(requirement)
        pinned['source_provenance'] = {'format': 'bb-boss-actor-pin-v1', 'part_sha256': donor['fingerprint']}
        pinned['source_initialization'] = dict(donor['source_initialization'])
        if 'source_anchor_part' in requirement:
            pinned['source_provenance']['anchor_sha256'] = parts[requirement['source_anchor_part']]['fingerprint']
            pinned['source_part_kind'] = donor['kind']
        for field in ('source_provenance', 'source_initialization'):
            declared = requirement.get(field)
            if declared is not None and declared != pinned[field]:
                raise ValueError('reviewed actor ' + field + ' differs from original native source')
        output.append(pinned)
    return output


def _pin_anchored_requirements(args, requirements: list[dict], kind: str) -> list[dict]:
    """Verify reviewed region geometry and both original anchor witnesses."""
    cache_name = '_' + kind + '_pin_cache'
    cache = getattr(args, cache_name, None)
    if cache is None:
        cache = {}
        setattr(args, cache_name, cache)
    output = []
    for requirement in requirements:
        name = requirement['source_map']
        # Actor inspection validates the map identity and locates original inputs.
        source_actors = inspect_actor_map(args, name)
        destination_actors = inspect_actor_map(args, requirement['destination_map'])
        if name not in cache:
            path = next(args.maps / (name + suffix) for suffix in ('.msb.dcx', '.msb')
                        if (args.maps / (name + suffix)).is_file())
            run = subprocess.run(command_for(args) + ['--boss-' + kind + '-pins', str(path)],
                                 check=True, capture_output=True, text=True)
            report = json.loads(run.stdout)
            if (report.get('format') != 'bb-boss-' + kind + '-pins-v1' or report.get('map') != name
                    or len({row['name'] for row in report[kind + 's']}) != len(report[kind + 's'])):
                raise ValueError('invalid native ' + kind + ' pin report')
            cache[name] = report
        region = next((row for row in cache[name][kind + 's']
                       if row['name'] == requirement['source_region' if kind == 'region' else 'source_part']), None)
        if (region is None or region['entity_id'] != requirement['source_entity_id']
                or requirement['source_provenance'] != {
                    'format': 'bb-boss-' + kind + '-pin-v1',
                    ('region_sha256' if kind == 'region' else 'part_sha256'): region['fingerprint']}):
            raise ValueError(kind + ' requirement differs from original native source')
        for role, report in (('source', source_actors), ('destination', destination_actors)):
            actor = next((row for row in report['parts']
                          if row['name'] == requirement[role + '_anchor_part']), None)
            if actor is None or requirement[role + '_anchor_provenance'] != {
                    'format': 'bb-boss-actor-pin-v1', 'part_sha256': actor['fingerprint']}:
                raise ValueError(role + ' ' + kind + ' anchor differs from original native source')
        output.append(dict(requirement))
    return output


def pin_region_requirements(args, requirements: list[dict]) -> list[dict]:
    return _pin_anchored_requirements(args, requirements, 'region')


def pin_object_requirements(args, requirements: list[dict]) -> list[dict]:
    return _pin_anchored_requirements(args, requirements, 'object')


def verify_sfx_requirements(args, requirements: list[dict]) -> None:
    cache = {}
    for row in requirements:
        name = row['source_map']
        inspect_actor_map(args, name)
        if name not in cache:
            path = next(args.maps / (name + suffix) for suffix in ('.msb.dcx', '.msb')
                        if (args.maps / (name + suffix)).is_file())
            run = subprocess.run(command_for(args) + ['--boss-sfx-pins', str(path)],
                                 check=True, capture_output=True, text=True)
            report = json.loads(run.stdout)
            if report.get('format') != 'bb-boss-sfx-pins-v1' or report.get('map') != name:
                raise ValueError('invalid native SFX pin report')
            cache[name] = report
        matches = [entry for entry in cache[name]['sfx'] if entry['name'] == row['source_event']]
        if (len(matches) != 1 or matches[0]['event_id'] != row['source_event_id']
                or matches[0]['entity_id'] != row['source_entity_id']
                or row['source_provenance'] != {
                    'format': 'bb-boss-sfx-pin-v1', 'event_sha256': matches[0]['fingerprint']}):
            raise ValueError('SFX requirement differs from original native source')


def verify_retained_helpers(args, plan) -> None:
    """A retired controller still depends on the original helper identity."""
    for helper in plan.get('boss_contract', {}).get('retained_destination_helpers', ()):
        parts = {part['name']: part for part in inspect_actor_map(args, helper['map'])['parts']}
        part = parts.get(helper['part'])
        if (part is None or part['entity_id'] != helper['entity_id']
                or part['source_archetype'] != helper['archetype']
                or part['fingerprint'] != helper['source_provenance']['part_sha256']
                or part['source_initialization'] != helper['source_initialization']):
            raise ValueError('retained destination helper differs from its original native pin')


def gascoigne_actor_pins(args, slots) -> tuple[dict[str, NativeActorPin], list[dict]]:
    pins, initializations = {}, []
    for name in sorted({slot.map_name for slot in slots
                        if slot.entity_id == 2410800 and slot.map_name.startswith('m24_01_')}):
        parts = {part['name']: part for part in inspect_actor_map(args, name)['parts']}
        beast, human = parts['c2720_0000'], parts['c2710_0000']
        pins[name] = NativeActorPin(part_sha256=beast['fingerprint'], anchor_sha256=human['fingerprint'],
                                   **beast['source_initialization'])
        initializations.append({
            'source_map': name, 'source_part': human['name'], 'source_entity_id': human['entity_id'],
            'source_archetype': human['source_archetype'],
            'source_provenance': {'format': 'bb-boss-actor-pin-v1', 'part_sha256': human['fingerprint']},
            'source_initialization': human['source_initialization'],
            'destination_map': name, 'destination_part': 'c5000_0000', 'destination_entity_id': 2410800,
        })
    return pins, initializations


def orphan_actor_pins(args) -> dict[str, OrphanActorPin]:
    parts = {part['name']: part for part in inspect_actor_map(args, 'm36_00_00_00')['parts']}
    anchor = parts['c4540_0000']['fingerprint']
    return {role: OrphanActorPin(part_sha256=parts[name]['fingerprint'],
                                anchor_sha256=anchor, **parts[name]['source_initialization'])
            for role, name in (('core', 'c4540_0000'), ('phase', 'c4541_0000'), ('support', 'c4543_0000'))}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_for(args) -> list[str]:
    return ([str(args.dotnet)] if args.dotnet else []) + [str(args.writer)]


def lift_zero_argument_initializers(source: str) -> str:
    """Lift native AP calls whose absent argument payload DarkScript won't recompile.

    Only zero-parameter functions declared in this file qualify. The high-level
    form lets DarkScript encode its required unused argument padding.
    """
    no_parameters = {int(match[1]) for match in re.finditer(
        r'\$Event\((\d+),\s*\w+,\s*function\(\s*\)', source)}
    def replace(match):
        if int(match[2]) not in no_parameters:
            raise ValueError('argumentless initializer has no declared zero-parameter event')
        return f'$InitializeEvent({match[1]}, {match[2]});'
    return re.sub(r'(?<![\w$])InitializeEvent\((\d+),\s*(\d+)\);', replace, source)


def add_scripted_variants(variants: dict, texts: dict, scripted: dict) -> None:
    """Swapped scripted-AI placements lose only their pinned initializers.

    Each map's removal is one more constructor variant, composed against the
    same original as every boss adapter and AP override, then recompiled.
    """
    for filename, keys in sorted(scripted.items()):
        variants.setdefault(filename, []).append(
            patch_initializers(filename[:12], texts[filename], keys))


def retire_applied_fallbacks(plan: dict) -> dict:
    """Move JS-applied fallback rows out of the rows the launcher would apply.

    The launcher's native wakeup writer never runs for a boss build and
    refuses a boss plan that still carries rows, so they are recorded as
    applied instead.
    """
    applied = [*plan.get('wakeup_fallbacks', []), *plan.pop('scripted_fallbacks', [])]
    plan['wakeup_fallbacks'] = []
    if applied:
        plan['boss_scripted_fallbacks'] = sorted(applied, key=lambda row: row['logical_key'])
    return plan


def disable_player_scaling(plan: dict) -> dict:
    """Retain reviewed placements while explicitly declining every parameter clone."""
    swaps = plan.get('swaps')
    scaling = plan.get('scaling')
    if not isinstance(swaps, list) or not swaps or not isinstance(scaling, dict):
        raise ValueError('unscaled boss plan has no placements or scaling ledger')
    keys = [row.get('logical_key') for row in swaps if isinstance(row, dict)]
    if len(keys) != len(swaps) or any(not isinstance(key, str) or not key for key in keys):
        raise ValueError('unscaled boss plan has invalid placement keys')
    changes, skips = scaling.get('changes'), scaling.get('skips')
    if not isinstance(changes, list) or not isinstance(skips, list):
        raise ValueError('unscaled boss plan has an invalid scaling ledger')
    accounted = [row.get('logical_key') for row in changes + skips if isinstance(row, dict)]
    if (len(accounted) != len(changes) + len(skips)
            or any(not isinstance(key, str) or not key for key in accounted)
            or len(set(keys)) != len(keys) or sorted(accounted) != sorted(keys)):
        raise ValueError('unscaled boss plan scaling ledger does not cover every placement')
    plan['scaling'] = {
        'enabled': False, 'mechanism': 'inferred_static_npc_clone_sp_effect',
        'change_count': 0, 'changes': [], 'skip_count': len(keys),
        'skips': [{'logical_key': key, 'reason': 'disabled by player'} for key in sorted(keys)],
    }
    if not isinstance(plan.get('options'), dict):
        raise ValueError('unscaled boss plan has invalid options')
    plan['options']['normalize_scaling'] = False
    plan.pop('boss_actor_scaling', None)
    return plan


def validate_allocations(bundle: Path, slots, records: list[dict], plan: dict) -> None:
    """Check project-owned identifiers against the entire original corpus."""
    used = {slot.entity_id for slot in slots}
    for body in read_prefix(bundle, 'event/').values():
        used.update(int(value) for value in re.findall(r'(?<![\w])-?\d+(?![\w])', body.decode('utf-8-sig')))
    events = [event for record in records for event in record['added_event_ids']]
    if len(events) != len(set(events)):
        raise ValueError('added event IDs collide across output maps')
    actors = {row['destination_entity_id'] for row in plan.get('boss_actor_additions', [])}
    if set(events) & actors:
        raise ValueError('added event and actor identifiers collide')
    regions = {row['destination_entity_id'] for row in plan.get('boss_region_additions', [])
               if row['destination_entity_id'] >= 0}
    generators = {row['destination_entity_id'] for row in plan.get('boss_generator_additions', [])
                  if row['destination_entity_id'] >= 0}
    if (regions & (set(events) | actors | generators)
            or generators & (set(events) | actors)):
        raise ValueError('added event, actor, region or generator identifiers collide')
    objects = {row['destination_entity_id'] for row in plan.get('boss_object_additions', [])}
    if objects & (set(events) | actors | regions | generators):
        raise ValueError('added object identifiers collide with another encounter resource')
    sfx = {row['destination_entity_id'] for row in plan.get('boss_sfx_additions', [])}
    if sfx & (set(events) | actors | regions | generators | objects):
        raise ValueError('added SFX identifiers collide with another encounter resource')
    allocated = set(events) | actors | regions | generators | objects | sfx
    if any(not isinstance(value, int) or value <= 0 for value in allocated) or allocated & used:
        raise ValueError('project-owned identifier collides with an original corpus operand or actor')


def event_record(original: Path, before: str, after: str, fingerprints: dict,
                 protected: list[int], terminals: tuple[dict, ...] = ()) -> dict:
    """Bind the compiled replacements to the exact source and edit set."""
    source, patched = event_blocks(before), event_blocks(after)
    if source.keys() - patched.keys():
        raise ValueError("encounter contract removed original events")
    changed = sorted(key for key in source if source[key] != patched[key])
    added = sorted(patched.keys() - source.keys())
    if not changed and not added:
        raise ValueError("encounter contract produced no event changes")
    validate_terminal_predicates(source, patched, protected, terminals)
    terminal_ids = {row['event_id'] for row in terminals}
    for key in protected:
        if key in terminal_ids:
            continue
        if key not in source or source[key] != patched[key]:
            raise ValueError(f"encounter contract changed AP completion event {key}")
    pins = {}
    for key in changed + added:
        pin = fingerprints.get(str(key))
        if not isinstance(pin, str) or len(pin) != 64 or any(c not in '0123456789abcdef' for c in pin):
            raise ValueError(f"missing or invalid compiled event fingerprint {key}")
        pins[str(key)] = pin
    return {
        "destination_event_file": original.name,
        "original_event_sha256": digest(original),
        "changed_event_ids": changed,
        "added_event_ids": added,
        "compiled_event_fingerprints": pins,
        "protected_completion_event_ids": sorted(protected),
        "terminal_predicates": list(terminals),
    }


def verify_receipt(root: Path) -> dict:
    receipt = json.loads((root / 'boss-encounters-report.json').read_text(encoding='utf-8-sig'))
    if receipt.get('format') != 'bb-boss-encounters-v1' or receipt.get('applied') is not True:
        raise ValueError('writer did not produce an applied encounter receipt')
    rows = receipt.get('files')
    if not isinstance(rows, list) or not rows:
        raise ValueError('encounter receipt has no files')
    expected = set()
    for row in rows:
        name = row['path']
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or name in expected:
            raise ValueError('duplicate or escaping encounter receipt path')
        expected.add(name)
        if not path.is_file() or path.stat().st_size != row['size'] or digest(path) != row['sha256']:
            raise ValueError('encounter output changed: ' + name)
    actual = {path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file()}
    if actual != expected | {'boss-encounters-report.json'}:
        raise ValueError('encounter output file set differs from receipt')
    return receipt


def build(args) -> dict:
    args._actor_pin_cache = {}
    recipes = reusable_recipes()
    experimental = chalice_recipes()
    recipes.update(experimental)
    good_assignment = None
    direct_chalice = (getattr(args, 'arena', None), getattr(args, 'donor', None)) in experimental
    if getattr(args, 'donor', None) in CHALICE_PACKAGES and not direct_chalice:
        raise ValueError('no supported experimental chalice route for this arena')
    if direct_chalice:
        validate_original_source(args.events, args.donor)
    ludwig = getattr(args, 'donor', None) == 'ludwig'
    laurence = getattr(args, 'donor', None) == 'laurence'
    orphan = getattr(args, 'donor', None) == 'orphan-of-kos'
    direct_orphan = (getattr(args, 'arena', None), getattr(args, 'donor', None))
    if direct_orphan[0] == 'shadows-of-yharnam' and direct_orphan[1] not in ('ludwig', 'the-one-reborn'):
        raise ValueError('Shadows arena requires a reviewed Ludwig or One Reborn donor adapter')
    if direct_orphan[1] == 'shadows-of-yharnam' and direct_orphan[0] not in ('orphan-of-kos', 'celestial-emissary'):
        raise ValueError('Shadows donor requires a reviewed Orphan or Celestial arena adapter')
    if direct_orphan[0] == 'the-one-reborn' and direct_orphan not in recipes and direct_orphan[1] not in ('rom', 'witch-of-hemwick'):
        raise ValueError('One Reborn arena requires a reviewed Rom or Witch donor adapter')
    if (direct_orphan[1] == 'the-one-reborn' and direct_orphan not in recipes
            and direct_orphan[0] not in ('ebrietas', 'shadows-of-yharnam')):
        raise ValueError('One Reborn donor requires a reviewed Ebrietas or Shadows arena adapter')
    if (direct_orphan[1] == 'celestial-emissary' and direct_orphan not in reusable_recipes()
            and direct_orphan[0] not in ('darkbeast-paarl', 'rom')):
        raise ValueError('Celestial donor requires a reviewed Paarl or Rom arena adapter')
    if (direct_orphan[1] == 'micolash' and direct_orphan not in recipes
            and direct_orphan[0] not in ('moon-presence', 'gehrman')):
        raise ValueError('Micolash donor requires a reviewed Moon Presence or Gehrman arena adapter')
    if direct_orphan[1] == 'witch-of-hemwick' and direct_orphan[0] not in ('amygdala', 'the-one-reborn'):
        raise ValueError('Witch donor requires a reviewed Amygdala or One Reborn arena adapter')
    if (direct_orphan[0] == 'micolash' and direct_orphan not in recipes
            and direct_orphan[1] not in ('gehrman', 'moon-presence')):
        raise ValueError('Micolash arena requires a reviewed Gehrman or Moon Presence donor adapter')
    if direct_orphan[0] == 'witch-of-hemwick' and direct_orphan[1] not in ('vicar-amelia', 'father-gascoigne'):
        raise ValueError('Witch arena requires a reviewed Amelia or Gascoigne donor adapter')
    if (direct_orphan[1] == 'mergos-wet-nurse' and direct_orphan not in recipes
            and direct_orphan[0] not in ('blood-starved-beast', 'martyr-logarius')):
        raise ValueError('Wet Nurse donor requires a reviewed BSB or Logarius arena adapter')
    if direct_orphan[0] == 'celestial-emissary' and direct_orphan[1] not in ('blood-starved-beast', 'amygdala', 'shadows-of-yharnam'):
        raise ValueError('Celestial Emissary arena requires a reviewed BSB, Amygdala or Shadows donor adapter')
    if direct_orphan[1] == 'living-failures' and direct_orphan[0] not in ('laurence', 'lady-maria'):
        raise ValueError('Living Failures donor requires a reviewed Laurence or Maria arena adapter')
    if direct_orphan[0] == 'rom' and direct_orphan not in recipes and direct_orphan[1] not in ('ebrietas', 'celestial-emissary'):
        raise ValueError('Rom arena requires a reviewed Ebrietas or Celestial donor adapter')
    if direct_orphan[1] == 'rom' and direct_orphan[0] not in ('ebrietas', 'the-one-reborn'):
        raise ValueError('Rom donor requires a reviewed Ebrietas or One Reborn arena adapter')
    if direct_orphan[0] == 'living-failures' and direct_orphan[1] not in ('blood-starved-beast', 'lady-maria', 'laurence'):
        raise ValueError('Living Failures arena requires a reviewed BSB, Maria or Laurence donor adapter')
    if direct_orphan[0] == 'mergos-wet-nurse' and direct_orphan[1] not in ('blood-starved-beast', 'martyr-logarius', 'darkbeast-paarl'):
        raise ValueError('Wet Nurse arena requires a reviewed BSB, Logarius or Paarl donor adapter')
    if (orphan and direct_orphan not in recipes
            and getattr(args, 'arena', None) not in ('cleric-beast', 'father-gascoigne')):
        raise ValueError('Orphan requires a reviewed Cleric or Gascoigne arena adapter')
    reviewed_orphan_pairs = {
        ('orphan-of-kos', 'shadows-of-yharnam'),
        ('orphan-of-kos', 'blood-starved-beast'),
        ('orphan-of-kos', 'ludwig'),
    }
    if (direct_orphan[0] == 'orphan-of-kos' and direct_orphan not in recipes
            and direct_orphan not in reviewed_orphan_pairs):
        raise ValueError('Orphan arena requires a reviewed donor adapter')
    direct_logarius = (getattr(args, 'arena', None), getattr(args, 'donor', None))
    if (direct_logarius[0] == 'martyr-logarius' and direct_logarius not in recipes
            and direct_logarius[1] not in (*LOGARIUS_COMPATIBILITY['martyr-logarius'], 'mergos-wet-nurse')):
        raise ValueError('Logarius arena requires a reviewed BSB, Paarl or Wet Nurse donor adapter')
    if (direct_logarius[1] == 'martyr-logarius' and direct_logarius not in recipes
            and direct_logarius[0] not in ('blood-starved-beast', 'mergos-wet-nurse')):
        raise ValueError('Martyr Logarius requires an implemented arena adapter')
    laurence_arena = getattr(args, 'arena', None) == 'laurence'
    ludwig_arena = getattr(args, 'arena', None) == 'ludwig'
    reviewed_ludwig_donors = LUDWIG_COMPATIBILITY['ludwig']
    if (ludwig_arena and direct_orphan not in recipes
            and getattr(args, 'donor', None) not in reviewed_ludwig_donors):
        raise ValueError('Ludwig arena requires a reviewed donor adapter')
    if (laurence_arena and direct_orphan not in recipes
            and getattr(args, 'donor', None) not in (*LAURENCE_COMPATIBILITY['laurence'], 'living-failures')):
        raise ValueError('Laurence arena requires a reviewed donor adapter')
    laurence_ids = LaurenceIds(12990300, 12990301)
    direct_gascoigne = (getattr(args, 'arena', None), getattr(args, 'donor', None))
    reviewed_gascoigne_pairs = {
        ('witch-of-hemwick', 'father-gascoigne'),
        ('cleric-beast', 'father-gascoigne'),
        ('father-gascoigne', 'cleric-beast'),
        ('father-gascoigne', 'orphan-of-kos'),
    }
    if direct_gascoigne[0] == 'father-gascoigne' or direct_gascoigne[1] == 'father-gascoigne':
        if direct_gascoigne not in reviewed_gascoigne_pairs and direct_gascoigne not in recipes:
            raise ValueError('Father Gascoigne is available only in the reviewed Cleric reciprocal adapters')
    if (ludwig and not getattr(args, 'pool', None) and direct_orphan not in recipes
            and args.arena not in ('cleric-beast', 'orphan-of-kos', 'shadows-of-yharnam')):
        raise ValueError('Ludwig donor requires a reviewed Cleric, Orphan or Shadows arena adapter')
    if (laurence and direct_orphan not in recipes
            and (getattr(args, 'pool', None) or args.arena not in ('cleric-beast', 'ludwig', 'living-failures'))):
        raise ValueError('Laurence donor requires a reviewed Cleric, Ludwig or Living Failures arena adapter')
    if getattr(args, 'pool', None):
        graph = {
            'blood-starved-beast': ('darkbeast-paarl',),
            'darkbeast-paarl': ('blood-starved-beast',),
        } if args.pool == 'bsb-paarl' else {
            'cleric-beast': ('lady-maria',), 'lady-maria': ('cleric-beast',),
        } if args.pool == 'maria-cleric' else {
            'cleric-beast': ('father-gascoigne',),
            'father-gascoigne': ('cleric-beast',),
        } if args.pool == 'gascoigne-cleric' else {
            'blood-starved-beast': ('martyr-logarius',), 'martyr-logarius': ('blood-starved-beast',),
        } if args.pool == 'logarius-bsb' else {
            'cleric-beast': ('ludwig',), 'ludwig': ('cleric-beast',),
        } if args.pool == 'ludwig-cleric' else {
            'cleric-beast': ('laurence',), 'laurence': ('cleric-beast',),
        } if args.pool == 'laurence-cleric' else FINAL_COMPATIBILITY if args.pool == 'finals' else reviewed_compatibility()
        if args.pool == 'good':
            good_assignment = assign_good_bosses(args.seed, good_boss_routes(), allow_self=False)
            mapping = good_assignment.arena_to_donor
        else:
            mapping = assign_donors(args.seed, graph)
        pairs = [(ARENAS[key], PACKAGES[value]) for key, value in mapping.items()]
    else:
        pairs = [(ARENAS[args.arena], PACKAGES[args.donor])]
    has_chalice = any(package.key in CHALICE_PACKAGES for _, package in pairs)
    for _, package in pairs:
        if package.key in CHALICE_PACKAGES:
            validate_original_source(args.events, package.key)
    if digest(args.darkscript) != DARKSCRIPT_SHA256:
        raise ValueError('requires pinned DarkScript 3.6.3')
    check_output(args.output, (args.maps, args.scripts, args.events, args.gameparam,
                              args.paramdef, args.bundle, args.writer, args.darkscript))
    if getattr(args, 'sfx', None):
        check_output(args.output, (args.sfx,))
    if getattr(args, 'characters', None):
        check_output(args.output, (args.characters,))
    event_overrides = getattr(args, 'event_overrides', None)
    if event_overrides is not None:
        if not event_overrides.is_dir():
            raise ValueError('event override directory does not exist')
        check_output(args.output, (event_overrides,))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Same-volume scratch permits atomic publication after native verification.
    with tempfile.TemporaryDirectory(prefix='.bb-encounter-build-', dir=args.output.parent) as temporary:
        scratch = Path(temporary)
        inventory = scratch / 'inventory.tsv'
        inventory.write_bytes(read_blob(args.bundle, 'mined/msb_enemies.tsv'))
        slots = load_slots(inventory, fixed_maps_only=not has_chalice)
        npcs, effects = load_params(args.bundle)
        materializations = {}
        for arena, package in pairs:
            recipe = recipes.get((arena.key, package.key))
            if recipe is not None:
                requirements = recipe.actor_requirements(slots)
                if requirements:
                    materializations[arena.key] = pin_actor_requirements(args, requirements)
                continue
            if (package is not None and arena.key not in FINAL_ARENAS
                    and not is_maria_pair(arena, package) and not is_gascoigne_pair(arena, package)
                    and not any(dlc_pair_flags(arena, package)) and package.key != 'orphan-of-kos'
                    and not is_bsb_orphan_pair(arena, package) and not is_ludwig_orphan_pair(arena, package)
                    and not is_logarius_bsb_pair(arena, package)
                    and not is_bsb_logarius_pair(arena, package) and not is_paarl_logarius_pair(arena, package)
                    and not is_bsb_wet_nurse_pair(arena, package)
                    and not is_bsb_living_failures_pair(arena, package)
                    and not is_rom_ebrietas_pair(arena, package)
                    and not is_ebrietas_rom_pair(arena, package)
                    and not is_living_failures_laurence_pair(arena, package)
                    and not is_bsb_celestial_pair(arena, package)
                    and not is_wet_nurse_bsb_pair(arena, package)
                    and not is_one_reborn_shadows_pair(arena, package)
                    and not is_witch_one_reborn_pair(arena, package)
                    and not is_shadows_celestial_pair(arena, package)
                    and not is_celestial_rom_pair(arena, package)
                    and not is_moon_micolash_pair(arena, package)
                    and not is_gascoigne_witch_pair(arena, package)
                    and not is_wet_nurse_logarius_pair(arena, package)
                    and not is_paarl_wet_nurse_pair(arena, package)
                    and not is_living_failures_maria_pair(arena, package)
                    and not is_amygdala_celestial_pair(arena, package)
                    and not is_logarius_wet_nurse_pair(arena, package)
                    and not is_amelia_witch_pair(arena, package)
                    and not is_gehrman_micolash_pair(arena, package)
                    and not is_micolash_moon_pair(arena, package)
                    and not is_micolash_gehrman_pair(arena, package)
                    and not is_one_reborn_ebrietas_pair(arena, package)
                    and not is_rom_one_reborn_pair(arena, package)
                    and not is_ludwig_shadows_pair(arena, package)
                    and not is_shadows_orphan_pair(arena, package)
                    and not is_maria_living_failures_pair(arena, package)
                    and not is_laurence_living_failures_pair(arena, package)
                    and not is_celestial_paarl_pair(arena, package)
                    and not is_witch_amygdala_pair(arena, package)):
                requirements = actor_addition_requirements(arena, package, slots)
                if requirements:
                    materializations[arena.key] = pin_actor_requirements(args, requirements)
        ordinary_plan_path = getattr(args, 'ordinary_plan', None)
        ordinary_plan = (json.loads(ordinary_plan_path.read_text(encoding='utf-8-sig'))
                         if ordinary_plan_path is not None else None)
        scripted = scripted_fallback_keys(ordinary_plan) if ordinary_plan is not None else {}
        originals, source, compiled = (scratch / name for name in ('original', 'source', 'compiled'))
        originals.mkdir()
        filenames = {item.event_file.removesuffix('.js') for pair in pairs for item in pair if item is not None}
        filenames |= {filename.removesuffix('.js') for filename in scripted}
        for name in filenames | {'common.emevd.dcx'}:
            shutil.copyfile(args.events / name, originals / name)
        compile_events(args.darkscript, 'decompile', originals, source, pairs[0][0].event_file)
        texts = {name + '.js': (source / (name + '.js')).read_text(encoding='utf-8-sig')
                 for name in filenames}
        variants = {}
        terminals = {}
        for arena, package in pairs:
            ludwig, laurence, ludwig_arena, laurence_arena = dlc_pair_flags(arena, package)
            recipe = recipes.get((arena.key, package.key))
            if recipe is not None:
                patched = recipe.patch(texts[arena.event_file], texts[package.event_file])
            elif is_orphan_gascoigne_pair(arena, package):
                patched = patch_orphan_at_gascoigne(texts[arena.event_file], texts[package.event_file])
            elif package.key == 'orphan-of-kos':
                patched = patch_orphan_at_cleric(texts[arena.event_file], texts[package.event_file], ORPHAN_ALLOCATION)
                terminals[arena.event_file] = ({'event_id': 12411700, 'original_actor': 2410800,
                    'bridge_event_id': ORPHAN_ALLOCATION.terminal_bridge_event_id},)
            elif is_bsb_orphan_pair(arena, package):
                patched = patch_bsb_at_orphan(
                    texts[arena.event_file], texts[package.event_file]
                )
            elif is_ludwig_orphan_pair(arena, package):
                patched = patch_ludwig_at_orphan(
                    texts[arena.event_file], texts[package.event_file]
                )
            elif is_micolash_moon_pair(arena, package):
                patched = patch_micolash_at_moon(texts[arena.event_file], texts[package.event_file])
            elif is_micolash_gehrman_pair(arena, package):
                patched = patch_micolash_at_gehrman(texts[arena.event_file], texts[package.event_file])
            elif is_one_reborn_ebrietas_pair(arena, package):
                patched = patch_one_reborn_at_ebrietas(texts[arena.event_file], texts[package.event_file])
            elif is_rom_one_reborn_pair(arena, package):
                patched = patch_rom_at_one_reborn(texts[arena.event_file], texts[package.event_file])
            elif is_ludwig_shadows_pair(arena, package):
                patched = patch_ludwig_at_shadows(texts[arena.event_file], texts[package.event_file])
            elif is_shadows_orphan_pair(arena, package):
                patched = patch_shadows_at_orphan(texts[arena.event_file], texts[package.event_file])
            elif is_maria_living_failures_pair(arena, package):
                patched = patch_maria_at_living_failures(texts[arena.event_file], texts[package.event_file])
            elif is_laurence_living_failures_pair(arena, package):
                patched = patch_laurence_at_living_failures(texts[arena.event_file], texts[package.event_file])
            elif is_celestial_paarl_pair(arena, package):
                patched = patch_celestial_emissary_at_paarl(texts[arena.event_file], texts[package.event_file])
            elif is_witch_amygdala_pair(arena, package):
                patched = patch_witch_at_amygdala(texts[arena.event_file], texts[package.event_file])
            elif is_gehrman_micolash_pair(arena, package):
                patched = patch_gehrman_at_micolash(texts[arena.event_file], texts[package.event_file])
            elif is_amelia_witch_pair(arena, package):
                patched = patch_amelia_at_witch(texts[arena.event_file], texts[package.event_file])
            elif is_logarius_wet_nurse_pair(arena, package):
                patched = patch_logarius_at_wet_nurse(texts[arena.event_file], texts[package.event_file])
            elif is_gascoigne_witch_pair(arena, package):
                patched = patch_gascoigne_at_witch(texts[arena.event_file], texts[package.event_file])
            elif is_shadows_celestial_pair(arena, package):
                patched = patch_shadows_at_celestial_emissary(texts[arena.event_file], texts[package.event_file])
            elif is_witch_one_reborn_pair(arena, package):
                patched = patch_witch_at_one_reborn(texts[arena.event_file], texts[package.event_file])
            elif is_one_reborn_shadows_pair(arena, package):
                patched = patch_one_reborn_at_shadows(texts[arena.event_file], texts[package.event_file])
            elif is_celestial_rom_pair(arena, package):
                patched = patch_celestial_emissary_at_rom(texts[arena.event_file], texts[package.event_file])
            elif is_moon_micolash_pair(arena, package):
                patched = patch_moon_at_micolash(texts[arena.event_file], texts[package.event_file])
            elif is_wet_nurse_logarius_pair(arena, package):
                patched = patch_wet_nurse_at_logarius(texts[arena.event_file], texts[package.event_file])
            elif is_paarl_wet_nurse_pair(arena, package):
                patched = patch_paarl_at_wet_nurse(texts[arena.event_file], texts[package.event_file])
            elif is_wet_nurse_bsb_pair(arena, package):
                patched = patch_wet_nurse_at_bsb(texts[arena.event_file], texts[package.event_file])
            elif is_amygdala_celestial_pair(arena, package):
                patched = patch_amygdala_at_celestial_emissary(texts[arena.event_file], texts[package.event_file])
            elif is_bsb_celestial_pair(arena, package):
                patched = patch_bsb_at_celestial_emissary(texts[arena.event_file], texts[package.event_file])
            elif is_living_failures_maria_pair(arena, package):
                patched = patch_living_failures_at_maria(texts[arena.event_file], texts[package.event_file])
            elif is_living_failures_laurence_pair(arena, package):
                patched = patch_living_failures_at_laurence(texts[arena.event_file], texts[package.event_file])
            elif is_ebrietas_rom_pair(arena, package):
                patched = patch_ebrietas_at_rom(texts[arena.event_file], texts[package.event_file])
            elif is_rom_ebrietas_pair(arena, package):
                patched = patch_rom_at_ebrietas(texts[arena.event_file], texts[package.event_file])
            elif is_bsb_living_failures_pair(arena, package):
                patched = patch_bsb_at_living_failures(texts[arena.event_file], texts[package.event_file])
            elif is_bsb_wet_nurse_pair(arena, package):
                patched = patch_bsb_at_wet_nurse(texts[arena.event_file], texts[package.event_file])
            elif is_paarl_logarius_pair(arena, package):
                patched = patch_paarl_at_logarius(texts[arena.event_file], texts[package.event_file])
            elif is_bsb_logarius_pair(arena, package):
                patched = patch_bsb_at_logarius(texts[arena.event_file], texts[package.event_file])
            elif is_logarius_bsb_pair(arena, package):
                patched = patch_logarius_at_bsb(
                    texts[arena.event_file], texts[package.event_file]
                )
            elif is_laurence_ludwig_pair(arena, package):
                # Both endpoints share m34, so the adapter preserves Laurence's
                # original bodies and emits project-owned copies for Ludwig.
                patched = patch_laurence_at_ludwig(
                    texts[arena.event_file], texts[package.event_file]
                )
            elif ludwig_arena:
                patched = patch_cleric_at_ludwig(texts[arena.event_file], texts[package.event_file])
            elif laurence_arena:
                patcher = (patch_bsb_at_laurence if package.key == 'blood-starved-beast'
                           else patch_cleric_at_laurence)
                patched = patcher(texts[arena.event_file], texts[package.event_file])
            elif laurence:
                patched = patch_laurence_at_cleric(texts[arena.event_file], texts['m34_00_00_00.emevd.dcx.js'], laurence_ids)
            elif ludwig:
                patched = patch_ludwig_at_cleric(texts[arena.event_file], texts['m34_00_00_00.emevd.dcx.js'], LUDWIG_ALLOCATION)
                terminals[arena.event_file] = ({'event_id': 12411700, 'original_actor': 2410800,
                    'bridge_event_id': LUDWIG_ALLOCATION.bridge_event},)
            elif is_gascoigne_donor_pair(arena, package):
                patched = patch_gascoigne_at_cleric(texts[arena.event_file], GASCOIGNE_ALLOCATION)
                terminals.setdefault(arena.event_file, ())
                terminals[arena.event_file] += ({'event_id': 12411700, 'original_actor': 2410800,
                    'bridge_event_id': GASCOIGNE_ALLOCATION.terminal_bridge_event_id},)
            elif is_gascoigne_arena_pair(arena, package):
                patched = patch_cleric_at_gascoigne(texts[arena.event_file], texts[package.event_file],
                                                    GASCOIGNE_ARENA_ATTACHMENTS)
            elif is_maria_pair(arena, package):
                if (arena.key, package.key) == ('cleric-beast', 'lady-maria'):
                    patched = patch_maria_at_cleric(texts[arena.event_file], texts[package.event_file], MARIA_ATTACHMENTS)
                elif (arena.key, package.key) == ('lady-maria', 'cleric-beast'):
                    patched = patch_cleric_at_maria(texts[arena.event_file], texts[package.event_file], CLERIC_MARIA_ATTACHMENTS)
                elif (arena.key, package.key) == ('lady-maria', 'blood-starved-beast'):
                    patched = patch_bsb_at_maria(texts[arena.event_file], texts[package.event_file])
                elif (arena.key, package.key) == ('vicar-amelia', 'lady-maria'):
                    patched = patch_maria_at_amelia(texts[arena.event_file], texts[package.event_file], MARIA_AMELIA_ATTACHMENTS)
                else:
                    raise ValueError('unreviewed Maria donor/arena pair')
            elif arena.key in FINAL_ARENAS:
                if package.key not in FINAL_COMPATIBILITY[arena.key]:
                    raise ValueError('unreviewed final-boss donor/arena pair')
                patcher = patch_moon_at_gehrman if arena.key == 'gehrman' else patch_gehrman_at_moon
                patched = patcher(texts[arena.event_file], FINAL_ATTACHMENTS[arena.key])
            else:
                patched = patch_contract_swap(arena, package, texts[arena.event_file], texts[package.event_file],
                    allow_materialized_actor_additions=bool(materializations.get(arena.key)))
            patched = skip_replacement_entrance(arena.key, texts[arena.event_file], patched)
            variants.setdefault(arena.event_file, []).append(patched)
        add_scripted_variants(variants, texts, scripted)
        override_inputs = []
        if event_overrides is not None:
            override_binary, override_source = scratch / 'override-binary', scratch / 'override-source'
            override_binary.mkdir()
            for filename in variants:
                path = event_overrides / filename.removesuffix('.js')
                if path.is_file():
                    shutil.copyfile(path, override_binary / path.name)
                    override_inputs.append({'file': path.name, 'sha256': digest(path)})
            if override_inputs:
                shutil.copyfile(originals / 'common.emevd.dcx', override_binary / 'common.emevd.dcx')
                compile_events(args.darkscript, 'decompile', override_binary, override_source,
                               override_inputs[0]['file'] + '.js')
                for item in override_inputs:
                    filename = item['file'] + '.js'
                    variants[filename].append(lift_zero_argument_initializers(
                        (override_source / filename).read_text(encoding='utf-8-sig')))
        catalog = build_catalog(args.bundle)
        protected_by_file = {}
        for filename, patches in variants.items():
            protected = [row['completion_event'] for row in catalog['encounters']
                         if row['map'] == filename[:12]]
            protected_by_file[filename] = protected
            combined = compose_event_patches(texts[filename], patches, protected, terminals.get(filename, ()))
            (source / filename).write_text(combined, encoding='utf-8')
        compile_events(args.darkscript, 'compile', source, compiled,
                       pairs[0][0].event_file.removesuffix('.js'))
        records = []
        for filename in sorted(variants):
            event_name = filename.removesuffix('.js')
            pins_run = subprocess.run(command_for(args) + ['--boss-encounter-pins', str(compiled / event_name)],
                                      check=True, capture_output=True, text=True)
            records.append(event_record(originals / event_name, texts[filename],
                                        (source / filename).read_text(encoding='utf-8'),
                                        json.loads(pins_run.stdout), protected_by_file[filename],
                                        terminals.get(filename, ())))
        plans = []
        for arena, package in pairs:
            ludwig, laurence, ludwig_arena, laurence_arena = dlc_pair_flags(arena, package)
            recipe = recipes.get((arena.key, package.key))
            if recipe is not None:
                plan = recipe.native_plan(slots, npcs, effects, args.seed)
                if arena.key in materializations:
                    plan['boss_actor_additions'] = materializations[arena.key]
                elif plan.get('boss_actor_additions'):
                    plan['boss_actor_additions'] = pin_actor_requirements(
                        args, plan['boss_actor_additions'])
                if plan.get('primary_init_source_bindings'):
                    plan['boss_actor_initializations'] = pin_actor_requirements(
                        args, plan['primary_init_source_bindings'])
                if package.key == 'lady-maria':
                    plan['boss_external_references'] = [maria_external_reference(args, plan, recipe.arena)]
            elif is_orphan_gascoigne_pair(arena, package):
                plan = native_plan_orphan_at_gascoigne(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif package.key == 'orphan-of-kos':
                plan = native_plan_orphan_at_cleric(slots, npcs, effects, ORPHAN_ALLOCATION,
                                                    orphan_actor_pins(args), args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_bsb_orphan_pair(arena, package):
                plan = native_plan_bsb_at_orphan(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['primary_init_source_bindings']
                )
            elif is_ludwig_orphan_pair(arena, package):
                plan = native_plan_ludwig_at_orphan(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['primary_init_source_bindings']
                )
            elif is_micolash_moon_pair(arena, package):
                plan = native_plan_micolash_at_moon(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_micolash_gehrman_pair(arena, package):
                plan = native_plan_micolash_at_gehrman(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_one_reborn_ebrietas_pair(arena, package):
                plan = native_plan_one_reborn_at_ebrietas(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_rom_one_reborn_pair(arena, package):
                plan = native_plan_rom_at_one_reborn(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_ludwig_shadows_pair(arena, package):
                plan = native_plan_ludwig_at_shadows(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_shadows_orphan_pair(arena, package):
                plan = native_plan_shadows_at_orphan(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_maria_living_failures_pair(arena, package):
                plan = native_plan_maria_at_living_failures(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
                plan['boss_external_references'] = [maria_external_reference(args, plan, arena)]
            elif is_laurence_living_failures_pair(arena, package):
                plan = native_plan_laurence_at_living_failures(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_celestial_paarl_pair(arena, package):
                plan = native_plan_celestial_at_paarl(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_witch_amygdala_pair(arena, package):
                plan = native_plan_witch_at_amygdala(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_gehrman_micolash_pair(arena, package):
                plan = native_plan_gehrman_at_micolash(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_amelia_witch_pair(arena, package):
                plan = native_plan_amelia_at_witch(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_logarius_wet_nurse_pair(arena, package):
                plan = native_plan_logarius_at_wet_nurse(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_gascoigne_witch_pair(arena, package):
                plan = native_plan_gascoigne_at_witch(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_shadows_celestial_pair(arena, package):
                plan = native_plan_shadows_at_celestial_emissary(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_witch_one_reborn_pair(arena, package):
                plan = native_plan_witch_at_one_reborn(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_one_reborn_shadows_pair(arena, package):
                plan = native_plan_one_reborn_at_shadows(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_celestial_rom_pair(arena, package):
                plan = native_plan_celestial_at_rom(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_moon_micolash_pair(arena, package):
                plan = native_plan_moon_at_micolash(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_wet_nurse_logarius_pair(arena, package):
                plan = native_plan_wet_nurse_at_logarius(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_paarl_wet_nurse_pair(arena, package):
                plan = native_plan_paarl_at_wet_nurse(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_wet_nurse_bsb_pair(arena, package):
                plan = native_plan_wet_nurse_at_bsb(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_amygdala_celestial_pair(arena, package):
                plan = native_plan_amygdala_at_celestial_emissary(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_bsb_celestial_pair(arena, package):
                plan = native_plan_bsb_at_celestial_emissary(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_living_failures_maria_pair(arena, package):
                plan = native_plan_living_failures_at_maria(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_living_failures_laurence_pair(arena, package):
                plan = native_plan_living_failures_at_laurence(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_ebrietas_rom_pair(arena, package):
                plan = native_plan_ebrietas_at_rom(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_rom_ebrietas_pair(arena, package):
                plan = native_plan_rom_at_ebrietas(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_bsb_living_failures_pair(arena, package):
                plan = native_plan_bsb_at_living_failures(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_bsb_wet_nurse_pair(arena, package):
                plan = native_plan_bsb_at_wet_nurse(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_paarl_logarius_pair(arena, package):
                plan = native_plan_paarl_at_logarius(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_bsb_logarius_pair(arena, package):
                plan = native_plan_bsb_at_logarius(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_logarius_bsb_pair(arena, package):
                plan = native_plan_logarius_at_bsb(slots, npcs, effects, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(
                    args, plan['boss_actor_additions']
                )
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['primary_init_source_bindings']
                )
            elif is_laurence_ludwig_pair(arena, package):
                plan = native_plan_laurence_at_ludwig(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['primary_init_source_bindings']
                )
            elif ludwig_arena:
                plan = native_plan_cleric_at_ludwig(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif laurence_arena:
                planner = (native_plan_bsb_at_laurence if package.key == 'blood-starved-beast'
                           else native_plan_cleric_at_laurence)
                plan = planner(slots, npcs, effects, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif laurence:
                plan = native_plan_laurence_at_cleric(slots, npcs, effects, laurence_ids, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif ludwig:
                plan = native_plan_ludwig_at_cleric(slots, npcs, effects, LUDWIG_ALLOCATION, args.seed)
                plan['boss_actor_additions'] = pin_actor_requirements(args, plan['boss_actor_additions'])
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
            elif is_gascoigne_donor_pair(arena, package):
                actor_pins, initializations = gascoigne_actor_pins(args, slots)
                plan = native_plan_gascoigne_at_cleric(slots, npcs, effects, GASCOIGNE_ALLOCATION,
                                                       actor_pins, args.seed)
                # The donor primary is the original Gascoigne human and
                # therefore carries its native Talk 241330 pin.
                plan['boss_actor_initializations'] = initializations
            elif is_gascoigne_arena_pair(arena, package):
                plan = native_plan_cleric_at_gascoigne(slots, npcs, effects,
                                                       GASCOIGNE_ARENA_ATTACHMENTS, args.seed)
                # The source primary is Cleric Beast and must retain the
                # original Talk 0 initialization in every m24 state.
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['primary_init_source_bindings'])
            elif is_maria_pair(arena, package):
                if arena.key == 'cleric-beast':
                    plan = native_plan_maria_at_cleric(slots, npcs, effects, MARIA_ATTACHMENTS, args.seed)
                elif arena.key == 'vicar-amelia':
                    plan = native_plan_maria_at_amelia(slots, npcs, effects, MARIA_AMELIA_ATTACHMENTS, args.seed)
                elif package.key == 'blood-starved-beast':
                    plan = native_plan_bsb_at_maria(slots, npcs, effects, args.seed)
                else:
                    plan = native_plan_cleric_at_maria(slots, npcs, effects, CLERIC_MARIA_ATTACHMENTS, args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(args, plan['primary_init_source_bindings'])
                if package.key == 'lady-maria':
                    plan['boss_external_references'] = [maria_external_reference(args, plan, arena)]
            elif arena.key in FINAL_ARENAS:
                plan = plan_final_boss_swap(slots, npcs, effects, arena=FINAL_ARENAS[arena.key],
                    donor=FINAL_ARENAS[package.key], attachment_ids=FINAL_ATTACHMENTS[arena.key], seed=args.seed)
                plan['boss_actor_initializations'] = pin_actor_requirements(
                    args, plan['boss_contract']['primary_init_source_bindings'])
            else:
                plan = plan_contract_swap(arena, package, slots, npcs, effects, args.seed)
                if arena.key in materializations:
                    plan['boss_actor_additions'] = materializations[arena.key]
            if plan.get('boss_region_additions'):
                plan['boss_region_additions'] = pin_region_requirements(args, plan['boss_region_additions'])
            if plan.get('boss_object_additions'):
                plan['boss_object_additions'] = pin_object_requirements(args, plan['boss_object_additions'])
            verify_sfx_requirements(args, plan.get('boss_sfx_additions', []))
            verify_retained_helpers(args, plan)
            plans.append(plan)
        if ordinary_plan is not None:
            if ordinary_plan.get('seed') != args.seed:
                raise ValueError('ordinary and boss seed differ')
            plan = retire_applied_fallbacks(combine_ordinary_and_boss_plans(ordinary_plan, plans))
        else:
            plan = plans[0] if len(plans) == 1 else combine_native_plans(args.seed, plans)
        if good_assignment is not None:
            plan['boss_contract']['good_boss_assignment'] = good_assignment.as_dict()
            plan.setdefault('options', {})['boss_pool'] = 'good'
        # Combat helpers declare a parent swap explicitly or are matched to a
        # reviewed phase-body source. Both feed one post-combination allocator.
        helper_parents = {}
        for pair_plan in plans:
            for addition in pair_plan.get('boss_actor_additions', []):
                if addition['source_archetype']['npc_param_id'] not in (272000, 451001, 454100, 454300):
                    continue
                anchor = f"{addition['destination_map']}:{addition['destination_anchor_part']}"
                parents = [swap['logical_key'] for swap in pair_plan['swaps']
                           if anchor in swap['destination_keys']]
                if len(parents) != 1:
                    raise ValueError('combat phase helper has no unique primary placement')
                helper = (addition['destination_map'], addition['destination_part'])
                if helper in helper_parents:
                    raise ValueError('combat helper has multiple parent declarations')
                helper_parents[helper] = parents[0]
            declared_parents = [*logarius_helper_scaling_parents(pair_plan).items(),
                                *rom_helper_scaling_parents(pair_plan).items(),
                                *ebrietas_rom_helper_scaling_parents(pair_plan).items()]
            for helper, parent in declared_parents:
                existing = helper_parents.get(helper)
                if existing is not None and existing != parent:
                    raise ValueError('combat helper has conflicting parent declarations')
                helper_parents[helper] = parent
        if helper_parents and not getattr(args, 'no_scaling', False):
            plan['boss_actor_scaling'] = allocate_actor_scaling(plan, npcs, helper_parents)
        if getattr(args, 'no_scaling', False):
            disable_player_scaling(plan)
        validate_allocations(args.bundle, slots, records, plan)
        plan['boss_encounters'] = {'format': 'bb-boss-encounters-v1', 'encounters': records}
        if override_inputs:
            plan['input_event_overrides'] = override_inputs
        plan_path = scratch / 'plan' / 'plan.json'
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        output = scratch / 'overlay'
        asset_args = ['--sfx', str(args.sfx)] if getattr(args, 'sfx', None) else []
        if getattr(args, 'characters', None):
            asset_args.extend(['--characters', str(args.characters)])
        subprocess.run(command_for(args) + [
            '--boss-encounters', str(plan_path), str(args.gameparam), str(args.paramdef),
            str(args.maps), str(args.scripts), str(originals), str(compiled), str(output),
        ] + asset_args + ['--apply'], check=True)
        receipt = verify_receipt(output)
        if args.output.exists():
            raise ValueError('output appeared during build; refusing to replace it')
        output.rename(args.output)
        return receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('darkscript', 'writer', 'gameparam', 'paramdef', 'maps', 'scripts', 'events', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--dotnet', type=Path)
    parser.add_argument('--sfx', type=Path, help='original effective SFX binder directory for encounter asset closure')
    parser.add_argument('--characters', type=Path, help='original animation binders for declared character effect witnesses')
    parser.add_argument('--ordinary-plan', type=Path,
                        help='compose an ordinary enemy plan before one shared scaling/map/AI pass')
    parser.add_argument('--event-overrides', type=Path,
                        help='compose existing AP event patches affecting boss maps against the same originals')
    parser.add_argument('--bundle', type=Path, default=ROOT / 'research/bb_inputs.db')
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--arena', choices=sorted(ARENAS))
    selection.add_argument('--pool', choices=('bsb-paarl', 'maria-cleric', 'gascoigne-cleric', 'logarius-bsb', 'ludwig-cleric', 'laurence-cleric', 'finals', 'reviewed', 'good'))
    parser.add_argument('--donor', choices=sorted(PACKAGES))
    parser.add_argument('--seed', required=True)
    parser.add_argument('--no-scaling', action='store_true',
                        help='retain original enemy parameters for every ordinary and boss placement')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    if bool(args.arena) != bool(args.donor):
        parser.error('--arena and --donor must be supplied together')
    if not args.apply:
        parser.error('refusing to build without --apply')
    for name, value in vars(args).items():
        if isinstance(value, Path):
            setattr(args, name, value.resolve())
    result = build(args)
    print(json.dumps({'output': str(args.output), 'files_verified': len(result['files']),
                      'runtime_validated': False}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
