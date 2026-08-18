"""Small, dependency-free schema for Bloodborne world design data."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class ItemKind(Enum):
    PROGRESSION = "progression"
    USEFUL = "useful"
    FILLER = "filler"
    TRAP = "trap"
    EVENT = "event"


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    kind: ItemKind
    quantity: int = 1


@dataclass(frozen=True)
class Rule:
    """Disjunctive normal form: any clause may satisfy the rule."""

    any_of: tuple[frozenset[str], ...] = (frozenset(),)

    @classmethod
    def all(cls, *item_keys: str) -> "Rule":
        return cls((frozenset(item_keys),))

    @classmethod
    def any(cls, *clauses: Iterable[str]) -> "Rule":
        return cls(tuple(frozenset(clause) for clause in clauses))

    def allows(self, inventory: set[str]) -> bool:
        return any(clause <= inventory for clause in self.any_of)

    @property
    def referenced_items(self) -> set[str]:
        return set().union(*self.any_of) if self.any_of else set()


@dataclass(frozen=True)
class Entrance:
    name: str
    source: str
    target: str
    rule: Rule = Rule()


@dataclass(frozen=True)
class Location:
    key: str
    name: str
    region: str
    rule: Rule = Rule()
    locked_item: str | None = None


@dataclass(frozen=True)
class WorldModel:
    items: tuple[Item, ...]
    regions: tuple[str, ...]
    entrances: tuple[Entrance, ...]
    locations: tuple[Location, ...]

    def validate(self) -> list[str]:
        errors: list[str] = []
        item_keys = [item.key for item in self.items]
        region_set = set(self.regions)
        location_keys = [location.key for location in self.locations]
        for label, values in (("item key", item_keys), ("region", list(self.regions)),
                              ("location key", location_keys)):
            duplicates = sorted({value for value in values if values.count(value) > 1})
            errors.extend(f"duplicate {label}: {value}" for value in duplicates)
        known_items = set(item_keys)
        for entrance in self.entrances:
            if entrance.source not in region_set or entrance.target not in region_set:
                errors.append(f"entrance has unknown region: {entrance.name}")
            for key in entrance.rule.referenced_items - known_items:
                errors.append(f"entrance {entrance.name} references unknown item: {key}")
        for location in self.locations:
            if location.region not in region_set:
                errors.append(f"location {location.key} has unknown region: {location.region}")
            referenced = location.rule.referenced_items | ({location.locked_item} if location.locked_item else set())
            for key in referenced - known_items:
                errors.append(f"location {location.key} references unknown item: {key}")
            if location.locked_item:
                item = next((item for item in self.items if item.key == location.locked_item), None)
                if item and item.kind is not ItemKind.EVENT:
                    errors.append(f"locked item is not an event: {location.locked_item}")
        return errors
