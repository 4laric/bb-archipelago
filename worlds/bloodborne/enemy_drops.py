"""Seed-owned, local enemy-drop permutations (never AP locations)."""
from __future__ import annotations

import json
from random import Random
from typing import Any

from .resource_data import read_resource_text


def enemy_drop_catalog() -> dict[str, Any]:
    value = json.loads(read_resource_text("enemy_drop_catalog.json"))
    if value.get("format") != "bb-enemy-drop-catalog-v1":
        raise ValueError("unsupported enemy-drop catalog")
    return value


def build_enemy_drop_assignments(
    seed: str, mode: str = "balanced"
) -> list[dict[str, int | str]]:
    """Permute whole safe loot tables, with optional global dropsanity."""

    if mode not in {"balanced", "dropsanity"}:
        raise ValueError(f"unsupported enemy-drop mode: {mode}")

    assignments: list[dict[str, int | str]] = []
    catalog_groups = enemy_drop_catalog()["groups"]
    groups = (
        [{
            "group": "global-dropsanity",
            "entries": [
                entry for group in catalog_groups for entry in group["entries"]
            ],
        }]
        if mode == "dropsanity" else catalog_groups
    )
    for group in groups:
        entries = sorted(
            group["entries"], key=lambda row: (row["npc_param_id"], row["drop_field"])
        )
        sources = [int(row["source_lot_id"]) for row in entries]
        random = Random(f"bloodborne-enemy-drops:{mode}:{seed}:{group['group']}")
        # Keep the best deterministic permutation from a bounded search. Equal
        # source lots can make a complete derangement impossible, but this
        # minimizes unchanged archetypes without changing the lot multiset.
        best = list(sources)
        best_fixed = len(sources)
        for _ in range(128):
            candidate = list(sources)
            random.shuffle(candidate)
            fixed = sum(left == right for left, right in zip(sources, candidate))
            if fixed < best_fixed:
                best, best_fixed = candidate, fixed
                if fixed == 0:
                    break
        for entry, target in zip(entries, best):
            source = int(entry["source_lot_id"])
            if source == target:
                continue
            assignments.append(
                {
                    "npc_param_id": int(entry["npc_param_id"]),
                    "drop_field": str(entry["drop_field"]),
                    "source_lot_id": source,
                    "target_lot_id": target,
                }
            )
    return assignments
