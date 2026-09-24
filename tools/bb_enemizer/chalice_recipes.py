"""Explicit experimental chalice builds, outside the closed main-boss pool."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from .boss_contracts import CLERIC_ARENA
from .encounter_recipes import EncounterRecipe
from .chalice_character_ffx import character_ffx_plan


def source_manifest(donor: str) -> dict:
    raw = Path(__file__).with_name('chalice_source_manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != 'b6d993c4648886d5caadb3ecea71637478ca94f291985edac11abc6956a0755e':
        raise ValueError('chalice source manifest changed')
    return json.loads(raw)['donors'][donor]


def validate_original_source(events: Path, donor: str) -> dict:
    source = source_manifest(donor)
    path = events / source['event_file']
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError(f'{donor} original chalice constructor provenance drift')
    return source


def _humanoid_recipes():
    from .chalice_humanoid_donors import (
        DONORS, patch_chalice_humanoid_donor, native_plan_chalice_humanoid_donor,
    )
    for donor in DONORS.values():
        yield EncounterRecipe(
            arena=CLERIC_ARENA, donor=donor, adapter='chalice-humanoid:source-combat',
            _patch=lambda destination, source, d=donor:
                patch_chalice_humanoid_donor(CLERIC_ARENA, d, destination, source),
            _native_plan=lambda slots, npcs, effects, seed, d=donor:
                native_plan_chalice_humanoid_donor(CLERIC_ARENA, d, slots, npcs, effects, seed),
            _actor_requirements=lambda slots: [],
        )


def chalice_recipes() -> dict[tuple[str, str], EncounterRecipe]:
    from .chalice_beast_donors import chalice_beast_recipes
    from .chalice_giant_bloodletting_donors import chalice_recipes as giant_recipes

    result = {}
    for recipe in (*_humanoid_recipes(), *chalice_beast_recipes(), *giant_recipes()):
        # Other arena contracts must acquire their own asset delivery proof.
        if recipe.arena.key != 'cleric-beast':
            continue
        def plan(slots, npcs, effects, seed, r=recipe):
            output = r.native_plan(slots, npcs, effects, seed)
            output['boss_contract']['chalice_source_constructor'] = source_manifest(r.donor.key)
            requirements, deliveries, merges = {}, [], {}
            for actor in output['primary_init_source_bindings']:
                assets = character_ffx_plan(actor, r.arena.key)
                for requirement in assets['boss_character_ffx_requirements']:
                    key = (requirement['source_map'], requirement['source_part'],
                           requirement['source_entity_id'])
                    requirements[key] = requirement
                deliveries.extend(assets['boss_character_ffx_bank_requirements'])
                for merge in assets['boss_ffx_merges']:
                    merges[merge['source_file'], merge['destination_file']] = merge
                output['boss_contract']['chalice_character_effect_limits'] = assets['chalice_character_effect_limits']
            output['boss_character_ffx_requirements'] = list(requirements.values())
            output['boss_character_ffx_bank_requirements'] = deliveries
            output['boss_ffx_merges'] = list(merges.values())
            return output
        if recipe.key in result:
            raise ValueError('duplicate chalice recipe')
        result[recipe.key] = replace(recipe, _native_plan=plan)
    return result
