from __future__ import annotations

import hashlib
import math
import random
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any, Mapping

from .model import (
    EnemyTag,
    SIZE_CLASSES,
    Slot,
    SlotPolicy,
    Swap,
    canonical_map,
    slot_placement,
    tag_summary,
)


@dataclass(frozen=True)
class EnemizerConfig:
    seed: str
    max_size_up: int = 1
    max_size_down: int = 3
    preserve_tier: bool = True
    preserve_locomotion: bool = False


# Stress profiles: pregenerated worst-case seeds that limit-test the planner's
# compatibility assumptions in one map instead of waiting for them to surface
# across many ordinary seeds. A profile rides inside the enemy seed string so
# any launcher build can run one by typing it into the Enemy seed field:
#
#     stress:<kind>[=<argument>][:<map prefix>]
#
# e.g. ``stress:size-up:m24_01`` or ``stress:family=c4060:m24_01``. The map
# prefix keeps every other map vanilla so the tester knows where to look.
# An ordinary seed never starts with ``stress:`` and is planned exactly as
# before; the pinned 308-swap set is untouched.
STRESS_PREFIX = "stress:"
STRESS_KINDS = {
    "size-up": "every swap takes the largest size step up the rule allows",
    "size-down": "every swap takes the largest size step down the rule allows",
    "locomotion": "every swap changes locomotion class where a candidate exists",
    "tier-up": "every swap takes the highest-tier candidate (implies tier mixing)",
    "echoes": "every swap takes the candidate with the largest Blood Echo reward",
    "family": "every swap takes the named model family where compatible (family=cXXXX)",
}
TIER_RANK = {"common": 0, "elite": 1, "boss": 2}


@dataclass(frozen=True)
class StressProfile:
    kind: str
    argument: str = ""
    focus: str = ""

    @classmethod
    def parse(cls, seed: str) -> "StressProfile | None":
        if not seed.startswith(STRESS_PREFIX):
            return None
        fields = seed[len(STRESS_PREFIX):].split(":")
        if not fields or not fields[0] or len(fields) > 2:
            raise ValueError(
                f"malformed stress seed {seed!r}; expected stress:<kind>[=arg][:map]"
            )
        kind, _, argument = fields[0].partition("=")
        if kind not in STRESS_KINDS:
            raise ValueError(
                f"unknown stress kind {kind!r}; expected one of {sorted(STRESS_KINDS)}"
            )
        if kind == "family" and not argument.startswith("c"):
            raise ValueError("stress:family needs a model family, e.g. stress:family=c4060")
        if kind != "family" and argument:
            raise ValueError(f"stress:{kind} takes no argument")
        focus = fields[1] if len(fields) == 2 else ""
        if focus and not (focus.startswith("m") and focus[1:].replace("_", "").isdigit()):
            raise ValueError(f"stress focus {focus!r} must be a map prefix such as m24_01")
        return cls(kind=kind, argument=argument, focus=focus)

    def json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "argument": self.argument,
            "focus": self.focus,
            "description": STRESS_KINDS[self.kind],
        }

    def applies_to(self, logical_key: str) -> bool:
        if not self.focus:
            return True
        return canonical_map(logical_key.split(":", 1)[0]).startswith(self.focus)


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
        return False, ["target archetype not approved"]
    if target_key in policy.bans:
        return False, ["target banned for slot"]
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


def _echoes(facts: Mapping[int, Mapping[str, Any]], npc_param_id: int) -> int:
    row = facts.get(npc_param_id)
    return int(row.get("echoes", 0)) if row else 0


def _stress_score(
    stress: StressProfile,
    policy: SlotPolicy,
    family: str,
    variants: list[tuple[str, list[str]]],
    target_tags: Mapping[str, EnemyTag],
    archetypes: Mapping[str, Any],
    facts: Mapping[int, Mapping[str, Any]],
) -> float:
    """Rank a candidate family for a stress profile; larger is harsher, so preferred."""
    tags = [target_tags[key] for key, _ in variants]
    if stress.kind == "size-up":
        deltas = [_size_delta(policy.size_class, tag.size_class) for tag in tags]
        return max((d for d in deltas if d is not None), default=-99)
    if stress.kind == "size-down":
        deltas = [_size_delta(policy.size_class, tag.size_class) for tag in tags]
        return max((-d for d in deltas if d is not None), default=-99)
    if stress.kind == "locomotion":
        return float(any(
            tag.locomotion != "unknown" and policy.locomotion != "unknown"
            and tag.locomotion != policy.locomotion for tag in tags
        ))
    if stress.kind == "tier-up":
        return max(TIER_RANK.get(tag.tier, 0) for tag in tags)
    if stress.kind == "echoes":
        return max(_echoes(facts, archetypes[key].npc_param_id) for key, _ in variants)
    if stress.kind == "family":
        return float(family == stress.argument)
    raise ValueError(stress.kind)


def _stress_variants(
    stress: StressProfile,
    policy: SlotPolicy,
    variants: list[tuple[str, list[str]]],
    target_tags: Mapping[str, EnemyTag],
    archetypes: Mapping[str, Any],
    facts: Mapping[int, Mapping[str, Any]],
) -> list[tuple[str, list[str]]]:
    """Narrow a chosen family's variants to the ones that embody the profile."""
    if stress.kind == "echoes":
        best = max(_echoes(facts, archetypes[key].npc_param_id) for key, _ in variants)
        return [v for v in variants if _echoes(facts, archetypes[v[0]].npc_param_id) == best]
    if stress.kind == "tier-up":
        best = max(TIER_RANK.get(target_tags[key].tier, 0) for key, _ in variants)
        return [v for v in variants if TIER_RANK.get(target_tags[v[0]].tier, 0) == best]
    if stress.kind == "locomotion":
        moved = [
            v for v in variants
            if target_tags[v[0]].locomotion not in ("unknown", policy.locomotion)
        ]
        return moved or variants
    return variants


def plan_swaps(
    slots: list[Slot],
    policies: dict[str, SlotPolicy],
    tags: dict[str, EnemyTag],
    config: EnemizerConfig,
    facts: Mapping[int, Mapping[str, Any]] | None = None,
) -> tuple[list[Swap], list[dict]]:
    """Build a deterministic manifest without touching an MSB.

    Alternate-state copies of one logical placement receive one shared choice.
    The target pool is archetype-based rather than placement-weighted, avoiding
    the Nightreign failure mode where heavily duplicated enemies dominate.
    """
    facts = facts or {}
    stress = StressProfile.parse(config.seed)
    if stress is not None and stress.kind == "tier-up":
        config = replace(config, preserve_tier=False)
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
        if stress is not None and not stress.applies_to(logical_key):
            rejections.append({
                "logical_key": logical_key,
                "reason": f"outside stress focus {stress.focus}",
            })
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
        families = sorted(candidates_by_family)
        if stress is not None:
            scores = {
                name: _stress_score(stress, policy, name, candidates_by_family[name],
                                    target_tags, archetypes, facts)
                for name in families
            }
            top = max(scores.values())
            families = [name for name in families if scores[name] == top]
        family = families[rng.randrange(len(families))]
        family_candidates = candidates_by_family[family]
        if stress is not None:
            family_candidates = _stress_variants(
                stress, policy, family_candidates, target_tags, archetypes, facts)
        distances = []
        for target_key, notes in family_candidates:
            target_hp = max(target_tags[target_key].scaling_hp, 0.001)
            source_hp = max(policy.scaling_hp, 0.001)
            distances.append((abs(math.log(target_hp / source_hp)), target_key, notes))
        best_distance = min(value[0] for value in distances)
        best = [(key, notes) for distance, key, notes in distances
                if abs(distance - best_distance) < 1e-9]
        target_key, warnings = best[rng.randrange(len(best))]
        target = archetypes[target_key]
        swaps.append(
            Swap(
                logical_key=logical_key,
                destination_keys=[slot.key for slot in copies],
                destination_sources={slot.key: slot.archetype for slot in copies},
                source=source.archetype,
                target=target,
                warnings=warnings,
                destinations={slot.key: slot_placement(slot) for slot in copies},
                source_tag=tag_summary(tags.get(source.archetype.key, EnemyTag())),
                target_tag=tag_summary(target_tags[target_key]),
                source_facts=dict(facts.get(source.archetype.npc_param_id, {})),
                target_facts=dict(facts.get(target.npc_param_id, {})),
            )
        )
    return swaps, rejections
