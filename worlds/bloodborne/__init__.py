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
ITEM_ID_BY_KEY = {item.key: ID_BASE + index for index, item in enumerate(SHUFFLABLE_ITEMS, 1)}
ITEM_NAME_TO_ID = {item.name: ITEM_ID_BY_KEY[item.key] for item in SHUFFLABLE_ITEMS}
ITEM_NAME_TO_ID["Blood Vial"] = ID_BASE + 0x100
LOCATION_ID_BY_KEY = {loc.key: ID_BASE + 0x1000 + index for index, loc in enumerate(NETWORK_LOCATIONS, 1)}
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

        def create_item(self, name: str) -> BloodborneItem:
            kind = ItemClassification.filler if name == "Blood Vial" else ItemClassification.progression
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
            names.extend(["Blood Vial"] * (len(NETWORK_LOCATIONS) - len(names)))
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
