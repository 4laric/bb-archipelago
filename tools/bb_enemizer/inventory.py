from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from .model import Archetype, EnemyTag, Slot, SlotPolicy


def _integer(value: str, default: int = -1) -> int:
    return int(value) if value not in (None, "") else default


def _number(value: str) -> float:
    return float(value) if value not in (None, "") else 0.0


def load_slots(path: str | Path, fixed_maps_only: bool = True) -> list[Slot]:
    slots: list[Slot] = []
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if fixed_maps_only and "/" in row["map_path"].replace("\\", "/"):
                continue
            slots.append(
                Slot(
                    map_path=row["map_path"],
                    map_name=row["map_name"],
                    part_name=row["part_name"],
                    entity_id=_integer(row["part_entity_id"]),
                    talk_id=_integer(row["talk_id"]),
                    collision_name=row["collision_name"],
                    dummy=row["dummy"].lower() == "true",
                    x=_number(row["x"]),
                    y=_number(row["y"]),
                    z=_number(row["z"]),
                    archetype=Archetype(
                        model_name=row["model_name"],
                        npc_param_id=_integer(row["npc_param_id"]),
                        think_param_id=_integer(row["think_param_id"]),
                        chara_init_id=_integer(row["chara_init_id"]),
                    ),
                )
            )
    return slots


def load_tags(path: str | Path | None) -> dict[str, EnemyTag]:
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return {key: EnemyTag.from_json(value) for key, value in raw.items()}


def load_slot_overrides(path: str | Path | None) -> dict[str, dict]:
    if path is None:
        return {}
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("slot policy file must be a JSON object")
    return raw


def classify_slot(slot: Slot, overrides: dict[str, dict]) -> SlotPolicy:
    override = overrides.get(slot.key) or overrides.get(slot.logical_key)
    if override is not None:
        return SlotPolicy(
            randomize=bool(override.get("randomize", False)),
            reason=str(override.get("reason", "explicit override")),
            size_class=str(override.get("size_class", "unknown")),
            tier=str(override.get("tier", "common")),
            locomotion=str(override.get("locomotion", "unknown")),
            bans=tuple(override.get("bans", ())),
        )
    if slot.dummy:
        return SlotPolicy(False, "dummy/script-spawn Part")
    if slot.talk_id > 0:
        return SlotPolicy(False, "talk-bound character")
    if slot.archetype.chara_init_id > 0:
        return SlotPolicy(False, "character-init-bound NPC or hunter")
    if not slot.archetype.model_name.startswith("c"):
        return SlotPolicy(False, "non-character model")
    if slot.archetype.npc_param_id <= 0 or slot.archetype.think_param_id <= 0:
        return SlotPolicy(False, "missing NPC/Think parameter")
    return SlotPolicy(True, "conservative common-enemy heuristic")


def apply_archetype_tag(policy: SlotPolicy, tag: EnemyTag | None) -> SlotPolicy:
    """Fold generated roster evidence into an otherwise physical slot policy."""
    if tag is None or not policy.randomize:
        return policy
    if not tag.target:
        return replace(policy, randomize=False, reason="archetype not approved as a target/source")
    return replace(
        policy,
        size_class=tag.size_class,
        tier=tag.tier,
        locomotion=tag.locomotion,
        scaling_hp=tag.scaling_hp,
    )


def inventory_summary(slots: list[Slot], policies: dict[str, SlotPolicy]) -> dict:
    reasons = Counter(policies[slot.key].reason for slot in slots)
    return {
        "slots": len(slots),
        "logical_slots": len({slot.logical_key for slot in slots}),
        "archetypes": len({slot.archetype.key for slot in slots}),
        "eligible_physical_slots": sum(policies[slot.key].randomize for slot in slots),
        "reasons": dict(sorted(reasons.items())),
    }
