"""Registry entries for encounter routes backed by reusable adapters.

This module binds only implementations which already accept an independent
arena contract and combat package.  It does not infer support from matching
models, map prefixes, or numeric identifiers; specialized pair adapters remain
outside this registry until they expose the same reusable boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Protocol

from .boss_contracts import (
    ARENAS,
    COMPATIBILITY,
    PACKAGES,
    ArenaContract,
    CombatPackage,
    actor_addition_requirements,
    contract_capability,
    patch_contract_swap,
    plan_contract_swap,
)

Patch = Callable[[str, str], str]
NativePlan = Callable[[list, Mapping[int, dict], Mapping[int, dict], str], dict]
ActorRequirements = Callable[[list], list[dict]]


class EncounterDonor(Protocol):
    """Identity shared by full combat packages and specialized donor sources."""

    key: str
    event_file: str


@dataclass(frozen=True)
class DonorIdentity:
    """Minimal identity for a source-pinned adapter outside boss_contracts."""

    key: str
    event_file: str


@dataclass(frozen=True)
class EncounterRecipe:
    """One concrete binding of a reusable arena and donor implementation.

    The ownership fields describe the static adapter boundary.  They are not
    claims that the pair has passed native installation or gameplay testing.
    """

    arena: ArenaContract
    donor: EncounterDonor
    adapter: str
    _patch: Patch = field(repr=False, compare=False)
    _native_plan: NativePlan = field(repr=False, compare=False)
    _actor_requirements: ActorRequirements = field(repr=False, compare=False)
    combat_owner: str = "donor-source"
    progression_owner: str = "destination-arena"
    validation_status: str = "static-contract-only"

    @property
    def key(self) -> tuple[str, str]:
        return self.arena.key, self.donor.key

    def patch(self, destination: str, donor_source: str) -> str:
        return self._patch(destination, donor_source)

    def native_plan(
        self,
        slots: list,
        npcs: Mapping[int, dict],
        effects: Mapping[int, dict],
        seed: str,
    ) -> dict:
        return self._native_plan(slots, npcs, effects, seed)

    def actor_requirements(self, slots: list) -> list[dict]:
        return self._actor_requirements(slots)


def _base_recipe(arena: ArenaContract, donor: CombatPackage) -> EncounterRecipe:
    capability = contract_capability(arena, donor)
    if capability is None:
        raise ValueError(
            f"no reusable contract capability for {arena.key} <- {donor.key}"
        )

    def patch(destination: str, donor_source: str) -> str:
        return patch_contract_swap(
            arena,
            donor,
            destination,
            donor_source,
            allow_materialized_actor_additions=capability.requires_actor_additions,
        )

    def native_plan(
        slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict], seed: str
    ) -> dict:
        return plan_contract_swap(arena, donor, slots, npcs, effects, seed)

    def requirements(slots: list) -> list[dict]:
        return actor_addition_requirements(arena, donor, slots)

    return EncounterRecipe(
        arena=arena,
        donor=donor,
        adapter=f"boss-contracts:{capability.adapter}",
        _patch=patch,
        _native_plan=native_plan,
        _actor_requirements=requirements,
    )


def _maria_recipes() -> tuple[EncounterRecipe, ...]:
    # Kept local so this registry cannot become an import dependency of the
    # donor implementation it registers.
    from .maria_contract import MARIA_PACKAGE
    from .maria_donor import (
        MariaArenaAllocation,
        native_plan_maria_donor,
        patch_maria_donor,
    )

    allocation = MariaArenaAllocation(12994700, 12994701)
    recipes: list[EncounterRecipe] = []
    for arena in ARENAS:

        def patch(destination: str, donor_source: str, *, _arena=arena) -> str:
            return patch_maria_donor(_arena, destination, donor_source, allocation)

        def native_plan(
            slots: list,
            npcs: Mapping[int, dict],
            effects: Mapping[int, dict],
            seed: str,
            *,
            _arena=arena,
        ) -> dict:
            return native_plan_maria_donor(
                _arena, slots, npcs, effects, allocation, seed
            )

        recipes.append(
            EncounterRecipe(
                arena=arena,
                donor=MARIA_PACKAGE,
                adapter="maria-donor:portable-combat",
                _patch=patch,
                _native_plan=native_plan,
                _actor_requirements=lambda slots: [],
            )
        )
    return tuple(recipes)


def _laurence_recipes() -> tuple[EncounterRecipe, ...]:
    from .laurence_donor import (
        DEFAULT_LAURENCE_ALLOCATION,
        LAURENCE_EVENT_FILE,
        native_plan_laurence_donor,
        patch_laurence_donor,
    )

    donor = DonorIdentity("laurence", LAURENCE_EVENT_FILE)
    recipes: list[EncounterRecipe] = []
    for arena in ARENAS:

        def patch(destination: str, donor_source: str, *, _arena=arena) -> str:
            return patch_laurence_donor(
                _arena,
                destination,
                donor_source,
                DEFAULT_LAURENCE_ALLOCATION,
            )

        def native_plan(
            slots: list,
            npcs: Mapping[int, dict],
            effects: Mapping[int, dict],
            seed: str,
            *,
            _arena=arena,
        ) -> dict:
            return native_plan_laurence_donor(
                _arena,
                slots,
                npcs,
                effects,
                seed,
                DEFAULT_LAURENCE_ALLOCATION,
            )

        recipes.append(
            EncounterRecipe(
                arena=arena,
                donor=donor,
                adapter="laurence-donor:portable-combat",
                _patch=patch,
                _native_plan=native_plan,
                _actor_requirements=lambda slots: [],
            )
        )
    return tuple(recipes)


def reusable_recipes() -> dict[tuple[str, str], EncounterRecipe]:
    """Return every route backed by a parameterized, source-pinned adapter."""
    arenas = {arena.key: arena for arena in ARENAS}
    packages = {package.key: package for package in PACKAGES}
    recipes: dict[tuple[str, str], EncounterRecipe] = {}

    for arena_key, donor_keys in COMPATIBILITY.items():
        if arena_key not in arenas:
            raise ValueError(f"compatibility names unknown arena {arena_key}")
        for donor_key in donor_keys:
            if donor_key not in packages:
                raise ValueError(f"compatibility names unknown donor {donor_key}")
            recipe = _base_recipe(arenas[arena_key], packages[donor_key])
            if recipe.key in recipes:
                raise ValueError(f"duplicate reusable encounter recipe {recipe.key}")
            recipes[recipe.key] = recipe

    for recipe in (*_maria_recipes(), *_laurence_recipes()):
        if recipe.arena.key == recipe.donor.key:
            raise ValueError(f"self encounter recipe is not a shuffle: {recipe.key}")
        if recipe.key in recipes:
            raise ValueError(f"duplicate reusable encounter recipe {recipe.key}")
        recipes[recipe.key] = recipe

    return recipes
