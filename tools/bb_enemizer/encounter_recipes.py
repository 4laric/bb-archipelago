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
        SUPPORTED_MARIA_ARENAS,
        native_plan_maria_donor,
        patch_maria_donor,
    )

    allocation = MariaArenaAllocation(12994700, 12994701)
    recipes: list[EncounterRecipe] = []
    for arena in SUPPORTED_MARIA_ARENAS:

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
        SUPPORTED_LAURENCE_ARENAS,
        native_plan_laurence_donor,
        patch_laurence_donor,
    )

    donor = DonorIdentity("laurence", LAURENCE_EVENT_FILE)
    recipes: list[EncounterRecipe] = []
    for arena in SUPPORTED_LAURENCE_ARENAS:

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


def _maria_arena_recipes() -> tuple[EncounterRecipe, ...]:
    from .maria_arena_contract import (
        MARIA_ARENA_CONTRACT,
        native_plan_portable_donor_at_maria,
        patch_portable_donor_at_maria,
        portable_maria_donors,
    )

    arena = MARIA_ARENA_CONTRACT
    recipes: list[EncounterRecipe] = []
    for donor in portable_maria_donors():
        def patch(destination: str, donor_source: str, *, _donor=donor) -> str:
            return patch_portable_donor_at_maria(destination, _donor, donor_source)

        def native_plan(
            slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict],
            seed: str, *, _donor=donor,
        ) -> dict:
            return native_plan_portable_donor_at_maria(_donor, slots, npcs, effects, seed)

        def requirements(slots: list, *, _donor=donor) -> list[dict]:
            return actor_addition_requirements(arena, _donor, slots)

        recipes.append(EncounterRecipe(
            arena=arena,
            donor=donor,
            adapter="maria-arena:portable-combat",
            _patch=patch,
            _native_plan=native_plan,
            _actor_requirements=requirements,
        ))
    return tuple(recipes)


def _laurence_arena_recipes() -> tuple[EncounterRecipe, ...]:
    from .laurence_arena_contract import (
        LAURENCE_ARENA_CONTRACT,
        native_plan_portable_donor_at_laurence,
        patch_portable_donor_at_laurence,
        portable_laurence_donors,
    )

    arena = LAURENCE_ARENA_CONTRACT
    recipes: list[EncounterRecipe] = []
    for donor in portable_laurence_donors():
        def patch(destination: str, donor_source: str, *, _donor=donor) -> str:
            return patch_portable_donor_at_laurence(destination, _donor, donor_source)

        def native_plan(
            slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict],
            seed: str, *, _donor=donor,
        ) -> dict:
            return native_plan_portable_donor_at_laurence(_donor, slots, npcs, effects, seed)

        def requirements(slots: list, *, _donor=donor) -> list[dict]:
            return actor_addition_requirements(arena, _donor, slots)

        recipes.append(EncounterRecipe(
            arena=arena, donor=donor, adapter="laurence-arena:portable-combat",
            _patch=patch, _native_plan=native_plan, _actor_requirements=requirements,
        ))
    return tuple(recipes)


def _gascoigne_arena_recipes() -> tuple[EncounterRecipe, ...]:
    from .gascoigne_arena_contract import (
        GASCOIGNE_ARENA_CONTRACT,
        native_plan_portable_donor_at_gascoigne,
        patch_portable_donor_at_gascoigne,
        portable_gascoigne_donors,
    )

    arena = GASCOIGNE_ARENA_CONTRACT
    recipes: list[EncounterRecipe] = []
    for donor in portable_gascoigne_donors():
        def patch(destination: str, donor_source: str, *, _donor=donor) -> str:
            return patch_portable_donor_at_gascoigne(destination, _donor, donor_source)

        def native_plan(
            slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict],
            seed: str, *, _donor=donor,
        ) -> dict:
            return native_plan_portable_donor_at_gascoigne(_donor, slots, npcs, effects, seed)

        def requirements(slots: list, *, _donor=donor) -> list[dict]:
            return actor_addition_requirements(arena, _donor, slots)

        recipes.append(EncounterRecipe(
            arena=arena, donor=donor, adapter="gascoigne-arena:portable-combat",
            _patch=patch, _native_plan=native_plan, _actor_requirements=requirements,
        ))
    return tuple(recipes)


def _logarius_recipes() -> tuple[EncounterRecipe, ...]:
    from .logarius_donor import (
        SUPPORTED_LOGARIUS_ARENAS,
        native_plan_logarius_donor,
        patch_logarius_donor,
    )

    donor = DonorIdentity("martyr-logarius", "m25_00_00_00.emevd.dcx.js")
    recipes: list[EncounterRecipe] = []
    for arena in SUPPORTED_LOGARIUS_ARENAS:
        def patch(destination: str, donor_source: str, *, _arena=arena) -> str:
            return patch_logarius_donor(_arena, destination, donor_source)

        def native_plan(
            slots: list, npcs: Mapping[int, dict], effects: Mapping[int, dict],
            seed: str, *, _arena=arena,
        ) -> dict:
            return native_plan_logarius_donor(_arena, slots, npcs, effects, seed)

        recipes.append(EncounterRecipe(
            arena=arena,
            donor=donor,
            adapter="logarius-donor:portable-combat",
            _patch=patch,
            _native_plan=native_plan,
            _actor_requirements=lambda slots: [],
        ))
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

    for recipe in (*_maria_recipes(), *_laurence_recipes(), *_maria_arena_recipes(),
                   *_logarius_recipes(), *_laurence_arena_recipes(), *_gascoigne_arena_recipes()):
        if recipe.arena.key == recipe.donor.key:
            raise ValueError(f"self encounter recipe is not a shuffle: {recipe.key}")
        if recipe.key in recipes:
            raise ValueError(f"duplicate reusable encounter recipe {recipe.key}")
        recipes[recipe.key] = recipe

    return recipes
