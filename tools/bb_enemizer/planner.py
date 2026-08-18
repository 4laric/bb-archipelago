from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass

from .model import EnemyTag, SIZE_CLASSES, Slot, SlotPolicy, Swap


@dataclass(frozen=True)
class EnemizerConfig:
    seed: str
    max_size_up: int = 1
    max_size_down: int = 3
    preserve_tier: bool = True
    preserve_locomotion: bool = False


def _rng(seed: str) -> random.Random:
    # Python's hash() is process-randomized.  A digest makes manifests stable
    # across Python versions, machines, and PYTHONHASHSEED values.
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _size_delta(source: str, target: str) -> int | None:
    if source == "unknown" or target == "unknown":
        return None
    return SIZE_CLASSES.index(target) - SIZE_CLASSES.index(source)


def compatible(
    policy: SlotPolicy,
    target_key: str,
    target_tag: EnemyTag,
    config: EnemizerConfig,
) -> tuple[bool, list[str]]:
    if not target_tag.target:
        return False, ["target disabled"]
    if target_key in policy.bans:
        return False, ["target explicitly banned for slot"]
    if config.preserve_tier and policy.tier != target_tag.tier:
        return False, [f"tier mismatch: {policy.tier} -> {target_tag.tier}"]
    if (
        config.preserve_locomotion
        and policy.locomotion != "unknown"
        and target_tag.locomotion != "unknown"
        and policy.locomotion != target_tag.locomotion
    ):
        return False, [f"locomotion mismatch: {policy.locomotion} -> {target_tag.locomotion}"]

    warnings: list[str] = []
    delta = _size_delta(policy.size_class, target_tag.size_class)
    if delta is None:
        warnings.append("size compatibility unknown")
    elif delta > config.max_size_up:
        return False, [f"size-up exceeds limit: +{delta}"]
    elif -delta > config.max_size_down:
        return False, [f"size-down exceeds limit: {-delta}"]
    elif delta == config.max_size_up and delta > 0:
        warnings.append(f"size-up at limit: +{delta}")
    return True, warnings


def plan_swaps(
    slots: list[Slot],
    policies: dict[str, SlotPolicy],
    tags: dict[str, EnemyTag],
    config: EnemizerConfig,
) -> tuple[list[Swap], list[dict]]:
    """Build a deterministic manifest without touching an MSB.

    Alternate-state copies of one logical placement receive one shared choice.
    The target pool is archetype-based rather than placement-weighted, avoiding
    the Nightreign failure mode where heavily duplicated enemies dominate.
    """
    grouped: dict[str, list[Slot]] = defaultdict(list)
    for slot in slots:
        grouped[slot.logical_key].append(slot)

    # A protected placement is not automatically a valid donor. This prevents
    # talk NPCs, hunters, dummy-only spawns, and other excluded archetypes from
    # leaking back into ordinary slots through the global roster.
    archetypes = {
        slot.archetype.key: slot.archetype
        for slot in slots
        if policies[slot.key].randomize
    }
    target_tags = {key: tags.get(key, EnemyTag()) for key in archetypes}
    ordered_targets = sorted(archetypes)
    rng = _rng(config.seed)
    swaps: list[Swap] = []
    rejections: list[dict] = []

    for logical_key in sorted(grouped):
        copies = sorted(grouped[logical_key], key=lambda slot: slot.key)
        source = copies[0]
        copy_policies = [policies[slot.key] for slot in copies]
        if not all(policy.randomize for policy in copy_policies):
            rejections.append({
                "logical_key": logical_key,
                "reason": "protected copy: " + ", ".join(sorted({p.reason for p in copy_policies if not p.randomize})),
            })
            continue

        # Policy disagreements across alternate map states are unsafe.  A
        # curated override must describe the logical slot consistently.
        policy = copy_policies[0]
        if any(p != policy for p in copy_policies[1:]):
            rejections.append({"logical_key": logical_key, "reason": "alternate-state policy mismatch"})
            continue

        candidates_by_family: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
        denied: dict[str, int] = defaultdict(int)
        for target_key in ordered_targets:
            if target_key == source.archetype.key:
                continue
            if archetypes[target_key].model_name == source.archetype.model_name:
                continue
            ok, notes = compatible(policy, target_key, target_tags[target_key], config)
            if ok:
                candidates_by_family[archetypes[target_key].model_name].append((target_key, notes))
            else:
                denied[notes[0]] += 1
        if not candidates_by_family:
            rejections.append({
                "logical_key": logical_key,
                "reason": "no compatible target",
                "denied": dict(sorted(denied.items())),
            })
            continue
        # Nightreign's crucial two-stage shape: choose an enemy FAMILY
        # uniformly, then choose its best destination-scaled variant. Without
        # this, models with dozens of authored NpcParam rows dominate models
        # with only one or two variants.
        family = sorted(candidates_by_family)[rng.randrange(len(candidates_by_family))]
        family_candidates = candidates_by_family[family]
        distances = []
        for target_key, notes in family_candidates:
            target_hp = max(target_tags[target_key].scaling_hp, 0.001)
            source_hp = max(policy.scaling_hp, 0.001)
            distances.append((abs(math.log(target_hp / source_hp)), target_key, notes))
        best_distance = min(value[0] for value in distances)
        best = [(key, notes) for distance, key, notes in distances
                if abs(distance - best_distance) < 1e-9]
        target_key, warnings = best[rng.randrange(len(best))]
        swaps.append(
            Swap(
                logical_key=logical_key,
                destination_keys=[slot.key for slot in copies],
                destination_sources={slot.key: slot.archetype for slot in copies},
                source=source.archetype,
                target=archetypes[target_key],
                warnings=warnings,
            )
        )
    return swaps, rejections
