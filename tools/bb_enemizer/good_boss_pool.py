"""Seeded, exact-family matching over *implemented directed encounter routes*.

The experimental good-boss roster has 22 distinct families, while Bloodletting
and Darkbeast each permit more than one physical donor.  This module accepts a
route graph supplied by the builder; it never manufactures a missing adapter.
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Iterable, Mapping

GOOD_FAMILIES = (
    "father-gascoigne", "lady-maria", "orphan-of-kos", "cleric-beast",
    "pthumerian-elder", "vicar-amelia", "abhorrent-beast",
    "pthumerian-descendant", "martyr-logarius", "mergos-wet-nurse",
    "blood-starved-beast", "amygdala", "moon-presence", "darkbeast-paarl",
    "ludwig", "gehrman", "undead-giant", "keeper-of-old-lords",
    "beast-possessed-soul", "shadows-of-yharnam", "bloodletting-beast",
    "watchdog-of-the-old-lords",
)

# Main-game's 22 receiving encounters, including arenas whose own boss is not
# in the requested donor roster.  Those arenas still need one supported edge.
GOOD_ARENAS = (
    "amygdala", "blood-starved-beast", "celestial-emissary", "cleric-beast",
    "darkbeast-paarl", "ebrietas", "father-gascoigne", "gehrman",
    "lady-maria", "laurence", "living-failures", "ludwig",
    "martyr-logarius", "mergos-wet-nurse", "micolash", "moon-presence",
    "orphan-of-kos", "rom", "shadows-of-yharnam", "the-one-reborn",
    "vicar-amelia", "witch-of-hemwick",
)

FAMILY_VARIANTS = {
    "darkbeast-paarl": ("darkbeast-paarl", "loran-darkbeast"),
    "bloodletting-beast": ("bloodletting-beast", "headless-bloodletting-beast"),
}
VARIANT_FAMILY = {variant: family for family, variants in FAMILY_VARIANTS.items()
                  for variant in variants}


class CoverageError(ValueError):
    """No complete 22-family matching exists in the supplied route graph."""

    def __init__(self, message: str, report: dict):
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class GoodBossAssignment:
    arena_to_donor: dict[str, str]
    arena_to_family: dict[str, str]
    selected_variants: dict[str, str]
    unavailable_variants: tuple[str, ...]
    self_pairs: tuple[str, ...]
    seed: str

    def as_dict(self) -> dict:
        return {
            "format": "bb-good-boss-assignment-v1",
            "seed": self.seed,
            "arena_to_donor": dict(sorted(self.arena_to_donor.items())),
            "arena_to_family": dict(sorted(self.arena_to_family.items())),
            "selected_variants": dict(sorted(self.selected_variants.items())),
            "unavailable_variants": list(self.unavailable_variants),
            "self_pairs": list(self.self_pairs),
            "family_count": len(self.arena_to_family),
        }


def donor_family(donor: str) -> str | None:
    """Map a physical donor key to a requested family; others are excluded."""
    family = VARIANT_FAMILY.get(donor, donor)
    return family if family in GOOD_FAMILIES else None


def _route_pairs(routes: Mapping | Iterable) -> set[tuple[str, str]]:
    items = routes.keys() if isinstance(routes, Mapping) else routes
    output: set[tuple[str, str]] = set()
    for item in items:
        key = item.key if hasattr(item, "key") else item
        if not (isinstance(key, tuple) and len(key) == 2
                and all(isinstance(value, str) and value for value in key)):
            raise ValueError("good-boss routes require (arena, donor) keys")
        if key in output:
            raise ValueError(f"duplicate good-boss route {key}")
        output.add(key)
    return output


def _graph(pairs: set[tuple[str, str]], arenas: tuple[str, ...]) -> dict[str, dict[str, set[str]]]:
    result = {arena: {} for arena in arenas}
    for arena, donor in pairs:
        family = donor_family(donor)
        if arena in result and family is not None:
            result[arena].setdefault(family, set()).add(donor)
    return result


def coverage_report(routes: Mapping | Iterable, *,
                    arenas: Iterable[str] = GOOD_ARENAS) -> dict:
    """Expose missing routes and variant availability before assignment."""
    selected = tuple(arenas)
    if len(selected) != len(set(selected)):
        raise ValueError("good-boss arenas repeat a destination")
    graph = _graph(_route_pairs(routes), selected)
    available = {family: sorted({variant for options in graph.values()
                                 for variant in options.get(family, ())})
                 for family in GOOD_FAMILIES}
    return {
        "arena_count": len(selected), "family_count": len(GOOD_FAMILIES),
        "arenas_without_good_routes": sorted(a for a, options in graph.items() if not options),
        "families_without_routes": sorted(f for f, choices in available.items() if not choices),
        "available_variants": {f: available[f] for f in FAMILY_VARIANTS},
        "unavailable_variants": sorted(v for f, variants in FAMILY_VARIANTS.items()
                                       for v in variants if v not in available[f]),
    }


def _maximum_matching(graph: dict[str, dict[str, set[str]]],
                      selected: Mapping[str, str], seed: str, *,
                      allow_self: bool) -> dict[str, str]:
    """Maximum arena-to-family matching with seeded, stable edge ordering."""
    rng = random.Random("bb-good-boss-v1:" + seed + (":self" if allow_self else ":no-self"))
    options = {}
    for arena, families in graph.items():
        candidates = [family for family, donors in families.items()
                      if family not in selected or selected[family] in donors]
        if not allow_self:
            candidates = [family for family in candidates if family != arena]
        candidates.sort()
        rng.shuffle(candidates)
        options[arena] = candidates
    arena_order = sorted(options, key=lambda arena: (len(options[arena]), arena))
    by_family: dict[str, str] = {}

    def augment(arena: str, seen: set[str]) -> bool:
        for family in options[arena]:
            if family in seen:
                continue
            seen.add(family)
            if family not in by_family or augment(by_family[family], seen):
                by_family[family] = arena
                return True
        return False

    for arena in arena_order:
        augment(arena, set())
    return {arena: family for family, arena in by_family.items()}


def assign_good_bosses(seed: str, routes: Mapping | Iterable, *,
                       arenas: Iterable[str] = GOOD_ARENAS,
                       required_variants: Mapping[str, str] | None = None,
                       allow_self: bool = True) -> GoodBossAssignment:
    """Assign every requested family once, or fail with concrete coverage.

    A requested variant is mandatory. Without one, seeded variant order is
    tried against the *full* matching, so an available headless/Loran route is
    selectable when it belongs to some complete assignment. Zero-self routes
    are preferred globally; self pairs are returned explicitly if necessary.
    """
    if not isinstance(seed, str) or not seed:
        raise ValueError("good-boss assignment requires a nonempty seed")
    selected_arenas = tuple(arenas)
    if len(selected_arenas) != len(GOOD_FAMILIES) or len(set(selected_arenas)) != len(selected_arenas):
        raise ValueError("good-boss assignment requires 22 distinct arenas")
    pairs = _route_pairs(routes)
    graph = _graph(pairs, selected_arenas)
    report = coverage_report(pairs, arenas=selected_arenas)
    required = dict(required_variants or {})
    for family, variant in required.items():
        if family not in FAMILY_VARIANTS or variant not in FAMILY_VARIANTS[family]:
            raise ValueError(f"unsupported requested good-boss variant {family}: {variant}")
        if variant not in report["available_variants"][family]:
            raise CoverageError(f"requested variant {variant} has no supported route", report)
    if report["arenas_without_good_routes"] or report["families_without_routes"]:
        maximum = _maximum_matching(graph, required, seed, allow_self=True)
        report.update(maximum_matching_size=len(maximum),
                      unmatched_arenas=sorted(set(selected_arenas) - set(maximum)),
                      unmatched_families=sorted(set(GOOD_FAMILIES) - set(maximum.values())))
        raise CoverageError("good-boss routes cannot cover all 22 families", report)

    variant_families = tuple(FAMILY_VARIANTS)
    rng = random.Random("bb-good-boss-variants-v1:" + seed)
    choices = []
    for family in variant_families:
        available = list(report["available_variants"][family])
        rng.shuffle(available)
        choices.append([required[family]] if family in required else available)
    best: tuple[int, dict[str, str]] = (-1, {})
    for self_allowed in ((False, True) if allow_self else (False,)):
        for variants in itertools.product(*choices):
            chosen = dict(zip(variant_families, variants))
            matched = _maximum_matching(graph, chosen, seed, allow_self=self_allowed)
            if len(matched) > best[0]:
                best = len(matched), matched
            if len(matched) != len(GOOD_FAMILIES):
                continue
            donor_by_arena = {}
            for arena, family in matched.items():
                donors = graph[arena][family]
                if family in chosen:
                    donor_by_arena[arena] = chosen[family]
                else:
                    if donors != {family}:
                        raise ValueError(f"ambiguous physical donor for {family}")
                    donor_by_arena[arena] = family
            return GoodBossAssignment(
                arena_to_donor=donor_by_arena,
                arena_to_family=matched,
                selected_variants=chosen,
                unavailable_variants=tuple(report["unavailable_variants"]),
                self_pairs=tuple(sorted(a for a, f in matched.items() if a == f)),
                seed=seed,
            )
    report.update(maximum_matching_size=best[0],
                  unmatched_arenas=sorted(set(selected_arenas) - set(best[1])),
                  unmatched_families=sorted(set(GOOD_FAMILIES) - set(best[1].values())))
    raise CoverageError("good-boss routes have no complete 22-family matching", report)
