"""Archipelago adapter for the conservative Bloodborne vertical slice."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .data import MODEL
from .model import ItemKind, Rule

GAME = "Bloodborne"
WORLD_VERSION = json.loads((Path(__file__).parent / "archipelago.json").read_text(encoding="utf-8"))["world_version"]
ID_BASE = 0xBB0000
NETWORK_LOCATIONS = tuple(MODEL.locations)
SHUFFLABLE_ITEMS = tuple(item for item in MODEL.items if item.kind is not ItemKind.EVENT)
EVENT_ITEMS = tuple(item for item in MODEL.items if item.kind is ItemKind.EVENT)
FILLER_ITEM_NAME = "Blood Vial"


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

    @dataclass
    class BloodborneOptions(PerGameCommonOptions):
        enemizer: Enemizer

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
            kind = ItemClassification.filler if name == FILLER_ITEM_NAME else ItemClassification.progression
            return BloodborneItem(name, kind, ITEM_NAME_TO_ID[name], self.player)

        def create_regions(self) -> None:
            regions = {name: Region(name, self.player, self.multiworld) for name in MODEL.regions}
            self.multiworld.regions.extend(regions.values())
            for data in NETWORK_LOCATIONS:
                location = BloodborneLocation(self.player, data.name, LOCATION_ID_BY_KEY[data.key], regions[data.region])
                location.access_rule = _rule(data.rule, self.player)
                regions[data.region].locations.append(location)
                if data.locked_item:
                    event = next(item for item in EVENT_ITEMS if item.key == data.locked_item)
                    event_location = BloodborneLocation(self.player, f"{data.name} Event", None, regions[data.region])
                    event_location.access_rule = _rule(data.rule, self.player)
                    event_location.place_locked_item(BloodborneItem(event.name, ItemClassification.progression, None, self.player))
                    regions[data.region].locations.append(event_location)
            for data in MODEL.entrances:
                entrance = regions[data.source].create_exit(data.name)
                entrance.access_rule = _rule(data.rule, self.player)
                entrance.connect(regions[data.target])

        def create_items(self) -> None:
            names = [item.name for item in SHUFFLABLE_ITEMS]
            names.extend([FILLER_ITEM_NAME] * (len(NETWORK_LOCATIONS) - len(names)))
            self.multiworld.itempool.extend(self.create_item(name) for name in names)

        def set_rules(self) -> None:
            self.multiworld.completion_condition[self.player] = lambda state: state.has("Mergo's Wet Nurse Defeated", self.player)

        def fill_slot_data(self) -> dict[str, Any]:
            seed = f"{self.multiworld.seed_name}:{self.player}"
            return {"version": 1, "enemizer": bool(self.options.enemizer), "enemizer_seed": seed,
                    "runtime_locations": "manual"}

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
