"""Generalized boss-for-boss encounter-swap planner.

``boss_canary.py`` hand-derived one pair (Blood-Starved Beast donor onto the
Cleric Beast arena, CUSA03173 AppVer 01.09): it hashed the exact original
text of every event it depends on, fingerprinted the actual actor
placements, and only then applied a hand-written surgical edit, verified
afterward against three invariants. This module keeps that exact discipline
but expresses it as a reusable ``SwapTemplate`` plus a small engine
(``plan_template_swap`` / ``patch_template_swap``) instead of one hardcoded
function pair, so additional hand-verified boss pairs can be registered
without duplicating the hash/patch/verify machinery.

## Why the registry has one entry, not twenty-two

The mined corpus (``research/bb_inputs.db``) plus
``tools/build_boss_catalog.py`` gives a structural census of all 22
main-game AP boss encounters (see ``research/enemizer/boss_catalog.json``).
That census answers "what are this boss's actors/health-bar/completion
events" but it does **not** by itself tell you which of a boss's 10-25
"related events" are safe to touch versus load-bearing for an unrelated
quest/ending/insight flag -- that requires reading the actual EMEVD bodies
and hand-verifying (as ``boss_canary.py`` did for BSB/Cleric: 11 of
Cleric's ~23 related events touched, hashed, and pinned).

Probing every single-actor boss's related-event set (see the
`extract_profiles` docstring) shows *every one of them*, not just BSB and
Cleric, carries a comparable number of extra quest/cutscene/flag events
(10-24 each) with boss-specific shapes. There is no shortcut that derives a
safe edit recipe purely from the catalog's structural shape -- attempting
one would mean guessing which of those events are safe to leave alone,
which is exactly the kind of guess the task's honesty requirement forbids
("a wrong guess here means a tester's game breaks").

So: the registry (`REGISTRY`) holds only pairs that have gone through the
same manual hash-pinning ``boss_canary.py`` used. Right now that is exactly
the one pair it already shipped. Every other boss in the catalog is
reported through `profile_catalog` as **unsupported**, with the specific
structural reason it was not safe to auto-derive a template for, rather
than silently dropped. Registering a second verified pair is a matter of
adding another `SwapTemplate` (with its own pinned `EXPECTED` hashes and
patch function) to `REGISTRY` -- the engine below does not change.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from . import boss_canary
from .bosses import parse_events
from .model import Archetype, Swap
from .scaling import plan_scaling

EventBlocks = dict[int, str]


def event_blocks(text: str) -> EventBlocks:
    return boss_canary.event_blocks(text)


@dataclass(frozen=True)
class SwapTemplate:
    """One hand-verified (destination, donor) boss-encounter adapter."""

    name: str
    destination_event_file: str
    donor_event_file: str
    destination_map_prefix: str
    donor_map_prefix: str
    destination_count: int
    completion_event: int
    destination_entity: int
    donor_entity: int
    destination_archetype: Archetype
    donor_archetype: Archetype
    destination_expected: dict[int, str]
    donor_expected: dict[int, str]
    changed_events: tuple[int, ...]
    patch: Callable[[str, str], str]
    warning: str


def _bsb_at_cleric_patch(destination: str, donor: str) -> str:
    return boss_canary.patch_event_source(destination, donor)


BSB_AT_CLERIC = SwapTemplate(
    name=boss_canary.ADAPTER,
    destination_event_file=boss_canary.DESTINATION_EVENT_FILE,
    donor_event_file=boss_canary.DONOR_EVENT_FILE,
    destination_map_prefix="m24_01_",
    donor_map_prefix="m23_00_",
    destination_count=3,
    completion_event=boss_canary.COMPLETION_EVENT,
    destination_entity=boss_canary.DESTINATION_ENTITY,
    donor_entity=boss_canary.DONOR_ENTITY,
    destination_archetype=Archetype("c5000", 500241, 500241, 0),
    donor_archetype=Archetype("c2090", 209000, 209000, 0),
    destination_expected={key: value for key, value in boss_canary.EXPECTED.items()
                          if key >= 12400000},
    donor_expected={key: value for key, value in boss_canary.EXPECTED.items()
                    if key < 12400000},
    changed_events=tuple(boss_canary.CHANGED_EVENTS),
    patch=_bsb_at_cleric_patch,
    warning="experimental boss adapter; entrance, phases and AP completion require live validation",
)

# Registration point for future hand-verified pairs. See module docstring
# for why this is not auto-populated from the boss catalog.
REGISTRY: tuple[SwapTemplate, ...] = (BSB_AT_CLERIC,)


def _validate_pins(template: SwapTemplate, role: str, pins: dict[int, str]) -> None:
    if not pins:
        raise ValueError(f"boss adapter {template.name} has no {role} event hash pins")
    for event_id, digest in pins.items():
        if not isinstance(event_id, int) or event_id <= 0:
            raise ValueError(f"boss adapter {template.name} has an invalid {role} event ID")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"boss adapter {template.name} has an invalid {role} hash pin for {event_id}")


def validate_template(template: SwapTemplate) -> None:
    """Reject an adapter that omits the static evidence required to patch it.

    Pins are separated by source role.  A single mixed mapping made it too
    easy for a future callback to skip checking one input while appearing to
    carry the canary's provenance metadata.
    """
    if not template.name or not template.destination_event_file or not template.donor_event_file:
        raise ValueError("boss adapter has an incomplete identity")
    if template.destination_event_file == template.donor_event_file:
        raise ValueError(f"boss adapter {template.name} uses one file as both destination and donor")
    if not template.destination_map_prefix or not template.donor_map_prefix or template.destination_count < 1:
        raise ValueError(f"boss adapter {template.name} has invalid placement provenance")
    if template.completion_event in template.changed_events:
        raise ValueError(f"boss adapter {template.name} changes its destination completion event")
    if not template.changed_events or len(set(template.changed_events)) != len(template.changed_events):
        raise ValueError(f"boss adapter {template.name} has invalid changed-event declarations")
    _validate_pins(template, "destination", template.destination_expected)
    _validate_pins(template, "donor", template.donor_expected)
    if not set(template.changed_events).issubset(template.destination_expected):
        raise ValueError(f"boss adapter {template.name} leaves a changed event unhashed")


def validate_registry(registry: tuple[SwapTemplate, ...]) -> None:
    """Fail before planning if two adapters would write the same encounter.

    Planning each template independently cannot safely compose EMEVD edits to
    one destination file.  The native writer also needs one unambiguous owner
    for every destination actor, so reject both forms of collision here.
    """
    names: set[str] = set()
    destination_files: set[str] = set()
    destination_actors: set[tuple[str, int]] = set()
    for template in registry:
        validate_template(template)
        if template.name in names:
            raise ValueError(f"boss template registry repeats adapter name {template.name}")
        if template.destination_event_file in destination_files:
            raise ValueError(f"boss template registry has colliding destination event file {template.destination_event_file}")
        actor = (template.destination_map_prefix, template.destination_entity)
        if actor in destination_actors:
            raise ValueError(f"boss template registry has colliding destination actor {template.destination_entity}")
        names.add(template.name)
        destination_files.add(template.destination_event_file)
        destination_actors.add(actor)


def _verify_pinned_events(template: SwapTemplate, role: str, blocks: EventBlocks,
                          pins: dict[int, str]) -> None:
    for event_id, expected in pins.items():
        block = blocks.get(event_id)
        if block is None or hashlib.sha256(block.encode("utf-8")).hexdigest() != expected:
            raise ValueError(f"unsupported original {role} boss event {event_id} for {template.name}")


def verify_swap_invariants(original: EventBlocks, output: EventBlocks, template: SwapTemplate) -> None:
    """The same three post-conditions boss_canary.py checks, made reusable.

    1. the edited script defines exactly the same set of events as before;
    2. every event outside the template's declared edit set is byte-identical;
    3. the destination's own completion/progression event is untouched.
    """
    if original.keys() != output.keys():
        raise ValueError(f"boss adapter {template.name} changed event identity set")
    for event_id in original:
        if event_id not in template.changed_events and original[event_id] != output[event_id]:
            raise ValueError(f"boss adapter {template.name} touched unrelated event {event_id}")
    if output[template.completion_event] != original[template.completion_event]:
        raise ValueError(f"boss adapter {template.name} changed destination progression event")


def patch_template_swap(template: SwapTemplate, destination: str, donor: str) -> str:
    """Verify both hash-pinned inputs before invoking the template callback."""
    validate_template(template)
    original = event_blocks(destination)
    _verify_pinned_events(template, "destination", original, template.destination_expected)
    _verify_pinned_events(template, "donor", event_blocks(donor), template.donor_expected)
    result = template.patch(destination, donor)
    output = event_blocks(result)
    verify_swap_invariants(original, output, template)
    return result


def _plan_template_swap(template: SwapTemplate, slots) -> tuple[Swap, list]:
    """Generalized form of boss_canary.plan_canary: fingerprint the actual
    actor placements for one (destination, donor) template before planning
    a swap, and refuse loudly if they don't match the template's expected
    provenance exactly."""
    destinations = sorted(
        (slot for slot in slots if slot.entity_id == template.destination_entity
         and slot.map_name.startswith(template.destination_map_prefix)),
        key=lambda slot: slot.key,
    )
    donors = [slot for slot in slots if slot.entity_id == template.donor_entity
              and slot.map_name.startswith(template.donor_map_prefix)]
    if (len(destinations) != template.destination_count or not donors
            or any(s.archetype != template.destination_archetype for s in destinations)
            or any(s.archetype != template.donor_archetype for s in donors)):
        raise ValueError(f"unsupported boss placement provenance for {template.name}")
    if (len({s.logical_key for s in destinations}) != 1
            or any(s.dummy or s.talk_id or s.archetype.chara_init_id for s in destinations + donors)):
        raise ValueError(f"boss adapter {template.name} requires ordinary non-talk-bound actor placements")
    swap = Swap(
        destinations[0].logical_key, [s.key for s in destinations],
        {s.key: s.archetype for s in destinations}, template.destination_archetype, template.donor_archetype,
        warnings=[template.warning],
        destinations={s.key: {"map_name": s.map_name, "entity_id": s.entity_id,
                              "x": s.x, "y": s.y, "z": s.z} for s in destinations},
    )
    return swap, destinations


def _template_plan(template: SwapTemplate, swap: Swap, change) -> dict:
    return {
        "template": template.name,
        "swap": swap.json(),
        "required_event_overlay": "dvdroot_ps4/event/" + template.destination_event_file,
        "scaling_change": change.json(),
    }


def plan_template_swap(template: SwapTemplate, slots, npcs, effects) -> dict:
    """Plan and normalize one template without sharing clone IDs with others."""
    validate_template(template)
    swap, destinations = _plan_template_swap(template, slots)
    changes, skips = plan_scaling([swap], destinations, npcs, effects)
    if len(changes) != 1 or skips:
        raise ValueError(f"boss adapter {template.name} requires an applicable normalization clone")
    return _template_plan(template, swap, changes[0])


UNSUPPORTED_REASON_MULTI = (
    "encounter has {n} distinct actors; entity remap onto a single destination "
    "slot would be ambiguous without a hand-verified per-actor mapping"
)
UNSUPPORTED_REASON_NO_TEMPLATE = (
    "no hand-verified SwapTemplate registered for this boss (as either destination or "
    "donor); its encounter carries {extra} event(s) beyond its terminal/health-bar "
    "events (entry choreography, quest flags, phase transitions) whose safety cannot be "
    "derived from the structural catalog alone -- see boss_shuffle.py module docstring"
)
UNSUPPORTED_REASON_DONOR_ONLY = (
    "registered only as a donor for a different destination; no SwapTemplate writes this "
    "encounter, so its own AP boss check remains unsupported"
)
UNSUPPORTED_REASON_EXTRA_GAPS = (
    "boss_catalog.json flags additional gaps beyond the baseline two: {gaps}"
)


def profile_catalog(catalog: dict, registry: tuple[SwapTemplate, ...] = REGISTRY) -> tuple[list[dict], list[dict]]:
    """Split every boss in the mined boss catalog into (covered, unsupported).

    `covered` lists only destination encounters that a registered template
    actually rewrites.  A donor is source material, not coverage for its own
    AP check, and is reported as unsupported until it becomes a destination.
    """
    destination_entities = set()
    donor_entities = set()
    for template in registry:
        destination_entities.add((template.destination_map_prefix, template.destination_entity))
        donor_entities.add((template.donor_map_prefix, template.donor_entity))
    baseline_gaps = {"runtime encounter behavior unvalidated", "callee and flag dependency traversal incomplete"}
    covered, unsupported = [], []
    for record in catalog["encounters"]:
        entity = record["defeat_entities"][0] if len(record["defeat_entities"]) == 1 else None
        is_covered = entity is not None and any(
            record["map"].startswith(prefix) and entity == covered_entity
            for prefix, covered_entity in destination_entities
        )
        if is_covered:
            covered.append(record)
            continue
        is_donor = entity is not None and any(
            record["map"].startswith(prefix) and entity == donor_entity
            for prefix, donor_entity in donor_entities
        )
        if is_donor:
            reason = UNSUPPORTED_REASON_DONOR_ONLY
        elif record["actor_shape"] != "single_actor":
            actors = len(record["actors"])
            reason = UNSUPPORTED_REASON_MULTI.format(n=actors)
        else:
            extra_gaps = sorted(set(record["gaps"]) - baseline_gaps)
            if extra_gaps:
                reason = UNSUPPORTED_REASON_EXTRA_GAPS.format(gaps=", ".join(extra_gaps))
            else:
                hb_ids = {b["event_id"] for b in record["health_bars"]}
                related_ids = {r["event_id"] for r in record["related_events"]}
                extra = len(related_ids - hb_ids - {record["completion_event"]})
                reason = UNSUPPORTED_REASON_NO_TEMPLATE.format(extra=extra)
        unsupported.append({
            "key": record["key"], "map": record["map"],
            "ap_locations": record["ap_locations"], "actor_shape": record["actor_shape"],
            "reason": reason,
        })
    return covered, unsupported


def plan_boss_shuffle(seed: str, slots, npcs, effects, catalog: dict,
                      registry: tuple[SwapTemplate, ...] = REGISTRY) -> dict:
    """Plan every registered swap template against real actor placements,
    and report every catalog boss that a template does not cover.

    This is deliberately not a free permutation over the whole roster (see
    module docstring): each template is its own hand-verified adapter, so
    "the shuffle" is "apply every currently-verified adapter", not "pick a
    random donor for a random destination". A seed is still threaded
    through so the plan format matches the rest of the enemizer's output
    and so future multi-template registries have a deterministic
    tie-breaking hook (`sorted(registry, key=...)` below) without changing
    callers.
    """
    validate_registry(registry)
    covered, unsupported = profile_catalog(catalog, registry)
    candidates, failures = [], []
    for template in sorted(registry, key=lambda t: t.name):
        try:
            swap, _ = _plan_template_swap(template, slots)
            candidates.append((template, swap))
        except ValueError as exc:
            failures.append({"template": template.name, "reason": str(exc)})
    planned = []
    if candidates and not failures:
        logical_keys = [swap.logical_key for _, swap in candidates]
        if len(set(logical_keys)) != len(logical_keys):
            failures.append({"template": "registry", "reason": "planned templates collide on a destination logical slot"})
        else:
            try:
                changes, skips = plan_scaling([swap for _, swap in candidates], slots, npcs, effects)
                by_key = {change.logical_key: change for change in changes}
                if skips or len(by_key) != len(candidates):
                    raise ValueError("one or more planned templates lack an applicable normalization clone")
                planned = [_template_plan(template, swap, by_key[swap.logical_key])
                           for template, swap in candidates]
            except ValueError as exc:
                failures.append({"template": "registry", "reason": str(exc)})
    return {
        "format": "bb-enemizer-boss-shuffle-plan-v1",
        "dry_run": True,
        "seed": seed,
        "registry_size": len(registry),
        "status": "failed" if failures else "planned",
        "writer_status": "not_written",
        "coverage_status": "complete" if not unsupported else "partial",
        "templates_planned": [item["template"] for item in planned],
        "template_failures": failures,
        "swap_count": len(planned),
        "swaps": planned,
        "covered_boss_count": len(covered),
        "covered_bosses": sorted(r["key"] for r in covered),
        "unsupported_count": len(unsupported),
        "unsupported_bosses": sorted(unsupported, key=lambda r: r["key"]),
    }
