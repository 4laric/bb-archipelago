from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


SIZE_CLASSES = ("XS", "S", "M", "L", "XL", "XXL", "GIGA", "unknown")


def canonical_map(map_name: str) -> str:
    """Collapse Bloodborne's alternate map-state suffixes.

    m24_01_00_00, m24_01_00_01, and m24_01_00_11 contain parallel Parts.
    Planning them independently can put a different enemy in the same logical
    placement after a world-state transition.
    """
    fields = map_name.split("_")
    return "_".join(fields[:3] + ["00"]) if len(fields) == 4 else map_name


@dataclass(frozen=True)
class Archetype:
    model_name: str
    npc_param_id: int
    think_param_id: int
    chara_init_id: int

    @property
    def key(self) -> str:
        return (
            f"{self.model_name}:{self.npc_param_id}:"
            f"{self.think_param_id}:{self.chara_init_id}"
        )


@dataclass(frozen=True)
class Slot:
    map_path: str
    map_name: str
    part_name: str
    entity_id: int
    talk_id: int
    collision_name: str
    dummy: bool
    x: float
    y: float
    z: float
    archetype: Archetype

    @property
    def key(self) -> str:
        return f"{self.map_name}:{self.part_name}"

    @property
    def logical_key(self) -> str:
        return f"{canonical_map(self.map_name)}:{self.part_name}"


@dataclass(frozen=True)
class EnemyTag:
    size_class: str = "unknown"
    tier: str = "common"
    locomotion: str = "unknown"
    scaling_hp: float = 1.0
    target: bool = True
    notes: str = ""

    @classmethod
    def from_json(cls, value: dict[str, Any]) -> "EnemyTag":
        tag = cls(**{k: v for k, v in value.items() if k in cls.__dataclass_fields__})
        if tag.size_class not in SIZE_CLASSES:
            raise ValueError(f"invalid size_class {tag.size_class!r}")
        return tag


@dataclass(frozen=True)
class SlotPolicy:
    randomize: bool
    reason: str
    size_class: str = "unknown"
    tier: str = "common"
    locomotion: str = "unknown"
    scaling_hp: float = 1.0
    bans: tuple[str, ...] = ()


def slot_placement(slot: Slot) -> dict[str, Any]:
    """Where a physical copy stands, for the player-facing enemy report."""
    return {
        "map_name": slot.map_name,
        "entity_id": slot.entity_id,
        "x": slot.x,
        "y": slot.y,
        "z": slot.z,
    }


def tag_summary(tag: EnemyTag) -> dict[str, Any]:
    return {
        "size_class": tag.size_class,
        "tier": tag.tier,
        "locomotion": tag.locomotion,
        "scaling_hp": tag.scaling_hp,
    }


@dataclass
class Swap:
    logical_key: str
    destination_keys: list[str]
    destination_sources: dict[str, Archetype]
    source: Archetype
    target: Archetype
    warnings: list[str] = field(default_factory=list)
    # Diagnostic context stamped at plan time so a retained plan can name a
    # swap after the fact without the game dump (bb-archipelago#321).
    destinations: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_tag: dict[str, Any] = field(default_factory=dict)
    target_tag: dict[str, Any] = field(default_factory=dict)
    source_facts: dict[str, Any] = field(default_factory=dict)
    target_facts: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return {
            "logical_key": self.logical_key,
            "destination_keys": self.destination_keys,
            "destination_sources": {
                key: asdict(value) for key, value in sorted(self.destination_sources.items())
            },
            "destinations": {key: dict(value) for key, value in sorted(self.destinations.items())},
            "source": asdict(self.source),
            "target": asdict(self.target),
            "source_tag": dict(self.source_tag),
            "target_tag": dict(self.target_tag),
            "source_facts": dict(self.source_facts),
            "target_facts": dict(self.target_facts),
            "warnings": self.warnings,
        }
