"""Deterministic standalone item placement and independent sphere replay."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from random import Random
from typing import Any, Iterable, Mapping

from .catalog import (
    CatalogEntry,
    build_catalog,
    catalog_sha256,
    load_catalog_document,
)
from .schema import GAMEPARAM_PATH, PLAN_FORMAT, Reward, digest, validate_source_hashes


@dataclass(frozen=True)
class StandaloneOptions:
    include_dlc: bool = False
    full_item_pool: bool = True
    include_dlc_gear: bool = True
    uncanny_weapons: bool = False
    randomize_armor: bool = False
    alternate_hypogean_gaol_routes: bool = False
    one_time_enemy_checks: bool = False
    questlines_hold_progression: bool = False
    consumable_quantity_bonus: int = 0
    goal: str = "moon_presence"

    def __post_init__(self) -> None:
        if self.goal not in {"submit_to_gehrman", "refuse_gehrman", "moon_presence"}:
            raise ValueError(f"unsupported goal: {self.goal}")
        if self.consumable_quantity_bonus != 0:
            raise ValueError(
                "standalone item plan v1 requires consumable_quantity_bonus=0"
            )


def _world(options: StandaloneOptions):
    import worlds.bloodborne as world
    from worlds.bloodborne.data import (
        ALTERNATE_GAOL_ENTRANCE_NAMES,
        ALTERNATE_GAOL_LOCATION_KEYS,
        ALTERNATE_GAOL_REGIONS,
        ATTIRE_ITEM_KEYS,
        DLC_ATTIRE_ITEM_KEYS,
        DLC_ENTRANCE_NAMES,
        DLC_ITEM_KEYS,
        DLC_LOCATION_KEYS,
        DLC_REGIONS,
        DLC_WEAPON_KEYS,
        HEMWICK_GATE_ITEM_KEYS,
        ONE_TIME_ENEMY_LOCATION_KEYS,
        PHANTOM_ATTIRE_ITEM_KEYS,
        QUESTLINE_LOCATION_KEYS,
        SLICE_ENTRANCES,
        SLICE_ITEM_KEYS,
        SLICE_REGIONS,
        UNCANNY_WEAPONS,
    )

    locations = tuple(
        location
        for location in world.ALL_NETWORK_LOCATIONS
        if options.include_dlc or location.key not in DLC_LOCATION_KEYS
        if options.alternate_hypogean_gaol_routes
        or location.key not in ALTERNATE_GAOL_LOCATION_KEYS
        if options.one_time_enemy_checks
        or location.key not in ONE_TIME_ENEMY_LOCATION_KEYS
    )
    entrances = list(
        entrance
        for entrance in SLICE_ENTRANCES
        if options.include_dlc or entrance.name not in DLC_ENTRANCE_NAMES
    )
    regions = set(SLICE_REGIONS)
    if not options.include_dlc:
        regions -= set(DLC_REGIONS)
    if options.alternate_hypogean_gaol_routes:
        regions |= set(ALTERNATE_GAOL_REGIONS)
        entrances.extend(
            entrance
            for entrance in world.MODEL.entrances
            if entrance.name in ALTERNATE_GAOL_ENTRANCE_NAMES
        )
    keys = set(world.FULL_POOL_ITEM_KEYS if options.full_item_pool else SLICE_ITEM_KEYS)
    # Standalone leaves native memory progression native. These are AP-created
    # event effects, not inventory rewards a static ItemLot writer can place.
    keys -= set(HEMWICK_GATE_ITEM_KEYS)
    keys.discard("forbidden_woods_password")
    if not options.include_dlc:
        keys -= set(DLC_ITEM_KEYS) - set(DLC_WEAPON_KEYS)
    if not options.include_dlc_gear:
        keys -= set(DLC_WEAPON_KEYS)
    if options.randomize_armor:
        armor = set(ATTIRE_ITEM_KEYS) - set(PHANTOM_ATTIRE_ITEM_KEYS)
        if not options.include_dlc_gear:
            armor -= set(DLC_ATTIRE_ITEM_KEYS)
        keys |= armor
    if options.uncanny_weapons:
        keys |= {uncanny for base, uncanny in UNCANNY_WEAPONS.items() if base in keys}
    goal_key = {
        "submit_to_gehrman": "boss_mergos_wet_nurse",
        "refuse_gehrman": "boss_gehrman",
        "moon_presence": "boss_moon_presence",
    }[options.goal]
    return (
        world,
        locations,
        tuple(entrances),
        frozenset(regions),
        frozenset(keys),
        goal_key,
        QUESTLINE_LOCATION_KEYS,
    )


def _closure(
    inventory: set[str], locations: Iterable, entrances: Iterable, regions: set[str]
) -> tuple[set[str], set[str]]:
    reached = {"Menu"}
    items = set(inventory)
    changed = True
    while changed:
        changed = False
        for entrance in entrances:
            if (
                entrance.source in reached
                and entrance.target in regions
                and entrance.target not in reached
                and entrance.rule.allows(items)
            ):
                reached.add(entrance.target)
                changed = True
        for location in locations:
            if (
                location.region in reached
                and location.rule.allows(items)
                and location.locked_item
                and location.locked_item not in items
            ):
                items.add(location.locked_item)
                changed = True
        # Original event 12401803 grants this logical capability after Amelia's
        # altar memory. It stays out of the physical item pool.
        if "event_amelia_defeated" in items and "forbidden_woods_password" not in items:
            items.add("forbidden_woods_password")
            changed = True
    return reached, items


def _reachable(
    inventory: set[str], locations: Iterable, entrances: Iterable, regions: set[str]
) -> tuple[set[str], set[str]]:
    reached, items = _closure(inventory, locations, entrances, regions)
    return {
        location.key
        for location in locations
        if location.region in reached and location.rule.allows(items)
    }, items


def _reward(world, key: str, bonus: int) -> Reward:
    from worlds.bloodborne.runtime_bindings import DELIVERY_FIXTURES, ITEM_BINDINGS

    consumable_delivery_quantity = world.consumable_delivery_quantity
    if key == "blood_vial":
        binding = DELIVERY_FIXTURES["blood_vial"]
        quantity = consumable_delivery_quantity(key, 1, bonus)
    else:
        item = next(item for item in world.SHUFFLABLE_ITEMS if item.key == key)
        binding = ITEM_BINDINGS[key]
        quantity = consumable_delivery_quantity(key, item.quantity, bonus)
    if binding.gemgen_id is not None:
        return Reward(8, binding.gemgen_id, quantity)
    if binding.item_category == 255:
        raise ValueError(f"{key}: AP-only event effect entered standalone placement")
    assert binding.normalized_item_id is not None
    return Reward(
        binding.item_category, binding.normalized_item_id & 0x0FFFFFFF, quantity
    )


def _pool(world, keys: frozenset[str], seed: str, capacity: int) -> list[str]:
    by_name = {item.name: item.key for item in world.SHUFFLABLE_ITEMS}
    names = world.build_item_pool_names(keys, seed, capacity=capacity)
    return [
        "blood_vial" if name == world.FILLER_ITEM_NAME else by_name[name]
        for name in names
    ]


def _place(
    *,
    seed: str,
    items: list[str],
    placeable: list,
    locations: tuple,
    entrances: tuple,
    regions: set[str],
    quest_keys: frozenset[str],
    quest_progression: bool,
) -> dict[str, str]:
    from worlds.bloodborne.model import ItemKind
    import worlds.bloodborne as world

    kind = {item.key: item.kind for item in world.SHUFFLABLE_ITEMS}
    kind["blood_vial"] = ItemKind.FILLER
    progression = [key for key in items if kind[key] is ItemKind.PROGRESSION]
    remainder = [key for key in items if kind[key] is not ItemKind.PROGRESSION]
    random = Random(f"bloodborne-standalone-placement:{seed}")
    random.shuffle(progression)
    random.shuffle(remainder)
    unfilled = {location.key: location for location in placeable}
    placements: dict[str, str] = {}
    inventory = set(world.STARTING_TOOL_KEYS)
    for item_key in progression:
        reachable, inventory = _reachable(inventory, locations, entrances, regions)
        candidates = sorted(reachable & set(unfilled))
        if not quest_progression:
            candidates = [key for key in candidates if key not in quest_keys]
        if not candidates:
            raise ValueError(
                f"no reachable location can hold progression item {item_key}"
            )
        location_key = candidates[random.randrange(len(candidates))]
        placements[location_key] = item_key
        unfilled.pop(location_key)
        inventory.add(item_key)
    remaining_locations = sorted(unfilled)
    random.shuffle(remaining_locations)
    if len(remainder) != len(remaining_locations):
        raise ValueError("item pool and placeable location counts differ")
    placements.update(zip(remaining_locations, remainder))
    return placements


def verify_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    if plan.get("format") != PLAN_FORMAT:
        raise ValueError("unsupported standalone plan format")
    validate_source_hashes(plan.get("source_hashes", {}))
    if plan.get("unsupported"):
        raise ValueError("standalone plan contains unsupported active locations")
    if plan.get("catalog_sha256") != catalog_sha256():
        raise ValueError(
            "standalone plan catalog hash does not match award_targets.json"
        )
    raw_options = plan.get("options")
    if not isinstance(raw_options, dict):
        raise ValueError("standalone plan options must be an object")
    options = StandaloneOptions(**raw_options)
    catalog = load_catalog_document()
    active = [
        row
        for row in catalog["entries"]
        if all(
            getattr(options, key) == value for key, value in row.get("when", {}).items()
        )
    ]
    active_unsupported = [
        row["location_key"] for row in active if row["status"] == "unsupported"
    ]
    if active_unsupported:
        raise ValueError(
            "active standalone locations lack native award targets: "
            + ", ".join(active_unsupported)
        )
    expected_locations = {
        row["location_key"]: row for row in active if row["status"] == "placeable"
    }
    expected_items = {row["item_key"]: row["reward"] for row in catalog["items"]}
    placements = plan.get("placements")
    if not isinstance(placements, list) or not placements:
        raise ValueError("standalone plan has no placements")
    seen_locations: set[str] = set()
    seen_targets: set[tuple[int, int]] = set()
    for placement in placements:
        key = str(placement["location_key"])
        if key in seen_locations:
            raise ValueError(f"duplicate placement location: {key}")
        seen_locations.add(key)
        reward = Reward(**placement["reward"])
        item_key = str(placement["item_key"])
        if (
            item_key not in expected_items
            or reward.as_dict() != expected_items[item_key]
        ):
            raise ValueError(f"{key}: reward does not match catalog item {item_key}")
        targets = placement.get("award_targets", [])
        expected = expected_locations.get(key)
        if expected is None or targets != expected["targets"]:
            raise ValueError(f"{key}: award targets do not match the catalog")
        if sum(target.get("role") == "delivery" for target in targets) != 1:
            raise ValueError(f"{key}: placement requires exactly one delivery target")
        for target in targets:
            identity = (int(target["item_lot_id"]), int(target["slot"]))
            if identity in seen_targets:
                raise ValueError(f"duplicate physical award target: {identity}")
            seen_targets.add(identity)
    if seen_locations != set(expected_locations):
        missing = sorted(set(expected_locations) - seen_locations)
        extra = sorted(seen_locations - set(expected_locations))
        raise ValueError(
            f"standalone placement location set differs: missing={missing} extra={extra}"
        )
    return {"placements": len(placements), "targets": len(seen_targets)}


def generate_plan(
    seed: str,
    source_hashes: Mapping[str, str],
    options: StandaloneOptions = StandaloneOptions(),
) -> dict[str, Any]:
    if not seed.strip():
        raise ValueError("standalone seed must be non-empty")
    source_hashes = validate_source_hashes(source_hashes)
    world, locations, entrances, regions, item_keys, goal_key, quest_keys = _world(
        options
    )
    catalog = build_catalog(locations)
    unsupported = [entry for entry in catalog if entry.status == "unsupported"]
    if unsupported:
        details = ", ".join(entry.location_key for entry in unsupported)
        raise ValueError(
            f"active standalone locations lack native award targets: {details}"
        )
    by_key = {entry.location_key: entry for entry in catalog}
    placeable = [
        location for location in locations if by_key[location.key].status == "placeable"
    ]
    items = _pool(world, item_keys, seed, len(placeable))
    placed = _place(
        seed=seed,
        items=items,
        placeable=placeable,
        locations=locations,
        entrances=entrances,
        regions=set(regions),
        quest_keys=quest_keys,
        quest_progression=options.questlines_hold_progression,
    )
    rows = []
    for location_key in sorted(placed):
        item_key = placed[location_key]
        entry = by_key[location_key]
        rows.append(
            {
                "location_key": location_key,
                "item_key": item_key,
                "reward": _reward(
                    world, item_key, options.consumable_quantity_bonus
                ).as_dict(),
                "award_targets": [target.as_dict() for target in entry.targets],
            }
        )
    # Independent collection replay: consume every newly reachable placement,
    # then require every placement and the chosen goal to be reachable.
    inventory = set(world.STARTING_TOOL_KEYS)
    collected: set[str] = set()
    while True:
        reachable, inventory = _reachable(inventory, locations, entrances, set(regions))
        newly = sorted((reachable & set(placed)) - collected)
        if not newly:
            break
        for key in newly:
            inventory.add(placed[key])
            collected.add(key)
    reachable, inventory = _reachable(inventory, locations, entrances, set(regions))
    if collected != set(placed):
        missing = sorted(set(placed) - collected)
        raise ValueError(
            f"sphere replay cannot collect {len(missing)} placements: {missing[:5]}"
        )
    if goal_key not in reachable:
        raise ValueError(f"sphere replay cannot reach goal {goal_key}")
    fixed = [entry.as_dict() for entry in catalog if entry.status != "placeable"]
    plan = {
        "format": PLAN_FORMAT,
        "seed": seed,
        "generator_build": world.WORLD_VERSION,
        "options": asdict(options),
        "source_hashes": source_hashes,
        "catalog_sha256": catalog_sha256(),
        "placements": rows,
        "fixed_progression": fixed,
        "unsupported": [],
        "verification": {
            "goal_location": goal_key,
            "reachable_placements": len(collected),
            "plan_sha256": digest(rows),
        },
    }
    verify_plan(plan)
    return plan
