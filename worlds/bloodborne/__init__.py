"""Archipelago adapter for the conservative Bloodborne vertical slice."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .data import (
    CENTRAL_YHARNAM_SLICE_ENTRANCES,
    CENTRAL_YHARNAM_SLICE_ITEM_KEYS,
    CENTRAL_YHARNAM_SLICE_LOCATION_KEYS,
    CENTRAL_YHARNAM_SLICE_REGIONS,
    MODEL,
)
from .model import ItemKind, Rule
from .runtime_bindings import ITEM_BINDINGS, LOCATION_BINDINGS, validate_runtime_item_binding

GAME = "Bloodborne"
WORLD_VERSION = json.loads((Path(__file__).parent / "archipelago.json").read_text(encoding="utf-8"))["world_version"]
RUNTIME_BUILD = "bb-0.1.0-r5"
SUPPRESSION_MANIFEST_FORMAT = "bb-vanilla-suppression-build-v1"
SUPPRESSION_PLAN_SHA256 = "d044bdb5b02eeedf049718b69630866cf5eb89d98067445d772dd6ac486c6c73"
ID_BASE = 0xBB0000
NETWORK_LOCATIONS = tuple(
    location for location in MODEL.locations
    if location.key in CENTRAL_YHARNAM_SLICE_LOCATION_KEYS
)
SHUFFLABLE_ITEMS = tuple(
    item for item in MODEL.items
    if item.key in CENTRAL_YHARNAM_SLICE_ITEM_KEYS
)
EVENT_ITEMS = tuple(item for item in MODEL.items if item.kind is ItemKind.EVENT)
FILLER_ITEM_NAME = "Blood Vial"
GOAL_LOCATION_KEY = "boss_father_gascoigne"


class IdRegistryError(RuntimeError):
    """A key has no assigned network id, or the registry is malformed."""


def _load_id_registry(path: Path) -> dict[str, dict[str, int]]:
    """Read the append-only key -> network id registry.

    Network ids are a permanent contract: they travel in multidata and in the
    datapackage, so a key's id must never change once released. Deriving them
    from tuple order made every id a function of position, so inserting one row
    in data.py silently renumbered everything after it. They are now looked up.
    """
    registry: dict[str, dict[str, int]] = {"item": {}, "location": {}}
    seen: dict[int, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("kind\t"):
            continue
        try:
            kind, key, raw = line.split("\t")
            value = int(raw, 16)
        except ValueError as exc:
            raise IdRegistryError(f"{path.name}:{number}: malformed row: {line!r}") from exc
        if kind not in registry:
            raise IdRegistryError(f"{path.name}:{number}: unknown kind {kind!r}")
        if key in registry[kind]:
            raise IdRegistryError(f"{path.name}:{number}: duplicate {kind} key {key!r}")
        if value in seen:
            raise IdRegistryError(f"{path.name}:{number}: id 0x{value:X} already used by {seen[value]!r}")
        seen[value] = key
        registry[kind][key] = value
    return registry


ID_REGISTRY = _load_id_registry(Path(__file__).parent / "ids.tsv")


def _assigned(kind: str, key: str) -> int:
    try:
        return ID_REGISTRY[kind][key]
    except KeyError:
        raise IdRegistryError(
            f"no network id assigned for {kind} {key!r}. Add a row to "
            f"worlds/bloodborne/ids.tsv; never reuse an id and never change an existing one."
        ) from None


ITEM_ID_BY_KEY = {item.key: _assigned("item", item.key) for item in SHUFFLABLE_ITEMS}
ITEM_NAME_TO_ID = {item.name: ITEM_ID_BY_KEY[item.key] for item in SHUFFLABLE_ITEMS}
ITEM_NAME_TO_ID[FILLER_ITEM_NAME] = _assigned("item", "blood_vial")
LOCATION_ID_BY_KEY = {loc.key: _assigned("location", loc.key) for loc in NETWORK_LOCATIONS}
LOCATION_NAME_TO_ID = {loc.name: LOCATION_ID_BY_KEY[loc.key] for loc in NETWORK_LOCATIONS}


def build_runtime_slot_data() -> dict[str, Any]:
    """Return the address-free world/client contract for this seed.

    AP ids are serialized as object keys because JSON has no integer-keyed
    objects.  The client validates and converts them back to signed 64-bit ids.
    """
    locations_by_key = {location.key: location for location in NETWORK_LOCATIONS}
    items_by_key = {item.key: item for item in SHUFFLABLE_ITEMS}
    active_item_bindings = {
        key: ITEM_BINDINGS[key] for key in items_by_key
    }
    active_location_bindings = {
        key: LOCATION_BINDINGS[key] for key in locations_by_key
    }
    for key, binding in active_item_bindings.items():
        validate_runtime_item_binding(key, binding, items_by_key[key].quantity)
    locations = {
        str(LOCATION_ID_BY_KEY[key]): {
            "event_flag": binding.event_flag,
            "vanilla_award_suppressed": locations_by_key[key].vanilla_award_suppressed,
        }
        for key, binding in active_location_bindings.items()
    }
    items = {
        str(ITEM_ID_BY_KEY[key]): {
            "normalized_item_id": binding.normalized_item_id,
            "raw_descriptor": binding.raw_descriptor,
            "item_category": binding.item_category,
            "descriptor_evidence": binding.descriptor_evidence,
            "quantity": items_by_key[key].quantity,
            "reinforcement_level": binding.reinforcement_level,
            "feed_effect": binding.feed_effect,
        }
        for key, binding in active_item_bindings.items()
    }
    items[str(ITEM_NAME_TO_ID[FILLER_ITEM_NAME])] = {
        "normalized_item_id": 0x400003E8,
        "raw_descriptor": 0xB00003E8,
        "item_category": 4,
        "descriptor_evidence": "goods_formula_observed",
        "quantity": 1,
        "reinforcement_level": None,
        "feed_effect": "not_equippable",
    }
    suppression_required = any(
        row["vanilla_award_suppressed"] for row in locations.values()
    )
    return {
        "runtime_locations": locations,
        "runtime_items": items,
        "suppression": {
            "required": suppression_required,
            "manifest_format": SUPPRESSION_MANIFEST_FORMAT,
            "plan_sha256": SUPPRESSION_PLAN_SHA256,
        },
        "goal_location": LOCATION_ID_BY_KEY[GOAL_LOCATION_KEY],
    }

try:
    from BaseClasses import Item as APItem, ItemClassification, Location as APLocation, Region
    from Options import PerGameCommonOptions, Toggle
    from worlds.AutoWorld import World
except ImportError:
    __all__ = ["MODEL"]
else:
    from dataclasses import dataclass

    class Enemizer(Toggle):
        """Generate a deterministic enemizer request beside the multiworld output."""
        display_name = "Enemy Randomizer"
        default = 1

    class AutoUpgrade(Toggle):
        """Raise received weapons to the player's validated reinforcement target."""
        display_name = "Auto Upgrade Received Weapons"
        default = 0

    class AutoEquip(Toggle):
        """Equip received gear in deterministic Archipelago feed order."""
        display_name = "Auto Equip Received Gear"
        default = 0

    @dataclass
    class BloodborneOptions(PerGameCommonOptions):
        enemizer: Enemizer
        auto_upgrade: AutoUpgrade
        auto_equip: AutoEquip

    class BloodborneItem(APItem):
        game = GAME

    class BloodborneLocation(APLocation):
        game = GAME

    def _rule(rule: Rule, player: int):
        clauses = tuple(tuple(key for key in clause) for clause in rule.any_of)
        names = {item.key: item.name for item in MODEL.items}
        return lambda state: any(all(state.has(names[key], player) for key in clause) for clause in clauses)

    class BloodborneWorld(World):
        game = GAME
        options_dataclass = BloodborneOptions
        options: BloodborneOptions
        item_name_to_id = ITEM_NAME_TO_ID
        location_name_to_id = LOCATION_NAME_TO_ID
        origin_region_name = "Menu"

        def get_filler_item_name(self) -> str:
            """Archipelago's default picks a RANDOM name from item_name_to_id, and
            create_item classifies everything but the filler as progression — so
            without this the world hands out progression-classified keys as filler."""
            return FILLER_ITEM_NAME

        def create_item(self, name: str) -> BloodborneItem:
            if name == FILLER_ITEM_NAME:
                classification = ItemClassification.filler
            else:
                item = next(item for item in SHUFFLABLE_ITEMS if item.name == name)
                classification = {
                    ItemKind.PROGRESSION: ItemClassification.progression,
                    ItemKind.USEFUL: ItemClassification.useful,
                    ItemKind.FILLER: ItemClassification.filler,
                    ItemKind.TRAP: ItemClassification.trap,
                }[item.kind]
            return BloodborneItem(name, classification, ITEM_NAME_TO_ID[name], self.player)

        def create_regions(self) -> None:
            regions = {
                name: Region(name, self.player, self.multiworld)
                for name in CENTRAL_YHARNAM_SLICE_REGIONS
            }
            self.multiworld.regions.extend(regions.values())
            for data in NETWORK_LOCATIONS:
                location = BloodborneLocation(self.player, data.name, LOCATION_ID_BY_KEY[data.key], regions[data.region])
                location.access_rule = _rule(data.rule, self.player)
                regions[data.region].locations.append(location)
            for data in CENTRAL_YHARNAM_SLICE_ENTRANCES:
                entrance = regions[data.source].create_exit(data.name)
                entrance.access_rule = _rule(data.rule, self.player)
                entrance.connect(regions[data.target])

        def create_items(self) -> None:
            names = [item.name for item in SHUFFLABLE_ITEMS]
            names.extend([FILLER_ITEM_NAME] * (len(NETWORK_LOCATIONS) - len(names)))
            self.multiworld.itempool.extend(self.create_item(name) for name in names)

        def set_rules(self) -> None:
            # Runtime completion is authoritative: the client sends CLIENT_GOAL
            # when the debounced Gascoigne location flag is reported.  The
            # slice has no item-logic gate before either boss, so generation's
            # reachability condition is intentionally unconditional.
            self.multiworld.completion_condition[self.player] = lambda state: True

        def fill_slot_data(self) -> dict[str, Any]:
            seed = f"{self.multiworld.seed_name}:{self.player}"
            return {
                "version": 4,
                "runtime_build": RUNTIME_BUILD,
                "enemizer": bool(self.options.enemizer),
                "auto_upgrade": bool(self.options.auto_upgrade),
                "auto_equip": bool(self.options.auto_equip),
                "enemizer_seed": seed,
                **build_runtime_slot_data(),
            }

        def generate_output(self, output_directory: str) -> None:
            if not self.options.enemizer:
                return
            request = {"format": "bb-enemizer-request-v1", **self.fill_slot_data(), "player": self.player,
                       "player_name": self.player_name}
            path = Path(output_directory) / f"{self.multiworld.get_out_file_name_base(self.player)}.bbenemizer.json"
            path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")

    __all__ = ["MODEL", "BloodborneWorld"]

    try:
        from worlds.LauncherComponents import Component, Type, components
        def _launch_client(*args: str) -> None:
            from .client import launch
            launch(*args)
        components.append(Component("Bloodborne Client", game_name=GAME, func=_launch_client,
                                    component_type=Type.CLIENT, supports_uri=True))
    except ImportError:
        pass
