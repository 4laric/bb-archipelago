# Enemizer coverage: sharpening the EMEVD protection rule

## Why this document exists

The Bloodborne enemizer swaps 308 of 2,646 logical placements (~11.6%;
545 physical destinations pre-planner). The
single largest reason a slot is held vanilla is one blunt lexical rule in
`tools/build_enemizer_catalog.py`:

> A slot is protected when its entity ID **occurs anywhere** in its area's EMEVD.

That rule protects **2,399 physical slots** — collapsing alternate-map-state
copies, **1,536 logical placements** — which is the dominant share of all
enemizer protection. "Occurs in EMEVD" is a *lexical* test, not a proven
game-semantic one. This document decomposes those 2,399 slots by *why* the
number appears, proposes a sharper predicate, measures the coverage delta the
predicate would earn, and states the risk. It changes no default: the wider
mode ships **off by default, behind an explicit flag**.

All numbers below are reproduced by `tests/test_enemizer_coverage.py` from the
committed census (`research/enemizer/emevd_entity_usage.tsv`) and the bundled
inventory (`research/bb_inputs.db`). **No game dump is required.**

## The decomposition of the 2,399 protected slots

`tools/build_emevd_entity_usage.py` already parses every match: it separates
direct character operations, `$InitializeEvent` arguments, callee parameters
resolved through single-definition events, comments, and namespace collisions
with item-lot / acquisition-flag numbers. Folding each slot's operations into
families gives:

| Bucket | Physical slots | Share |
| --- | ---: | ---: |
| **Operand of a character operation** (`SetCharacter*`, AI, boss/HP/SpEffect, backread, kill, invincibility, …) | **2,332** | 97.2% |
| **No character operation** — "reviewable" | **67** | 2.8% |
| **Total EMEVD-protected** | **2,399** | 100% |

The census resolves callee bodies through same-area **and shared `common`**
event definitions (a prior revision omitted `common` and undercounted by 78;
see `docs/ENEMIZER-PROTECTION-AUDIT.md` §1/§4). Any `$InitializeEvent`
argument whose callee still cannot be resolved is recorded as
`unresolved_event_reference` — currently 0 slots — rather than silently
dropped. Unresolved remains UNKNOWN, never safe.

The 67 reviewable slots break down by which non-character families *do* touch
them (a slot may sit in several):

| Usage-class combination | Slots |
| --- | ---: |
| `event_argument` + `other` + `spatial` | 24 |
| `event_argument` + `other` | 15 |
| `other` only | 9 |
| `event_argument` + `other` + `presentation` | 7 |
| `event_argument` + `object` + `other` | 3 |
| `event_argument` + `spatial` | 3 |
| `item_lot_operand` only | 2 |
| `object` only / `object`+`spatial` / `spatial` only | 4 |

The dominant residue is **`event_argument` combined with resolved
non-character operations** (`HasDamageType`, `ForceAnimationPlayback`,
`InArea`): every reviewable slot now resolves its callee — the 78 old
`event_argument`-only rows were all actors passed into shared `common`
events and carried hidden character operations. The **item-lot namespace
collision** is almost entirely spurious:
308 protected slots share a number with an `ItemLotParam` row, but only **2**
occurrences are actual `AwardItemLot` operands, and only **10** item-lot
collisions lack a separate character operation. This refutes the strong
"numeric collisions are item-lot uses" premise without adopting its inverse as
policy.

## The proposed sharper predicate

> Protect a slot only when its entity id is the **operand of a character
> operation** in its area's EMEVD (per the reproducible census), not merely a
> number that appears somewhere in it.

It is a one-line reading of the census column the tool already commits, exposed
as `tools.build_emevd_entity_usage.has_character_operation(usage_classes)`. It
**fails closed**: a slot with any character operation on any alternate-state
copy stays protected.

At the logical level, **39 of the 1,536 EMEVD-protected placements (2.5%)** have
no character operation on any copy and would lose *this* protection.

## The measured coverage delta

Relaxing EMEVD protection is **not** the same as making a slot swappable: the
independent conservative gates in `classify_slot` (dummy, talk-bound, hunter /
CharaInit, non-character model, missing NPC/Think, unapproved archetype) and the
planner's "no compatible target" still apply. Running the planner over the real
inventory with the sharper predicate:

| Mode | Logical swaps |
| --- | ---: |
| Default (blunt rule) | **308** |
| Sharper predicate (character-operation operand) | **327** |
| **Net new swappable placements** | **+19 (+6.2%)** |

Of the 39 logical keys the predicate releases, only **19** actually become
swaps. The other 20 stay vanilla because a *different* conservative gate already
covers them:

| Outcome of the 39 released keys | Count |
| --- | ---: |
| **Newly swapped** | **19** |
| Still protected: archetype not approved as target/source | 8 |
| Still protected: dummy / script-spawn Part | 5 |
| Still protected: no compatible target | 3 |
| Still protected: talk-bound character | 3 |
| Still protected: character-init-bound NPC/hunter | 1 |

### Risk profile of the +19

- **Tier:** 18 common, 1 elite, **0 boss**. No scripted boss, miniboss, or
  cutscene actor is released — those all carry `HandleBossDefeat` /
  `DisplayBossHealthBar` / AI operations and land in the 2,332.
- **Spread:** m23 ×3, m24 ×2, m26 ×2, m27 ×12.
- **Models:** dominated by `c2190` (×12, a single m27 cluster of ids
  2700610–2700630, each referenced only as an `$InitializeEvent` argument plus
  a region/`InArea` spatial check and a `HasDamageType` predicate),
  `c1090` (×3), `c1241` (×2), `c1060`/`c2520` (×1 each).

### What a relaxation could still break

The residual risk is **not** boss/quest soft-locks (those keep a character
operation) but two narrower failure modes:

1. **Non-character scripted roles.** A `spatial`/`object`/`presentation`
   reference (region trigger, action button, treasure objact, or a literal
   `ForceAnimationPlayback` animation ID such as 7010/7011) can still make an
   enemy load-bearing for an encounter trigger even with no character
   operation. Every one of the +19 carries such a resolved use
   (`HasDamageType`, `InArea`, or model-specific animation IDs) — swapping
   its archetype changes model/AI and could perturb that trigger. These need
   per-event review and playtesting (audit tranches T2–T3), not a bulk
   release.
2. **Census resolver completeness.** `$InitializeEvent` callees resolve
   through same-area and shared `common` definitions, single-hop only. Any
   callee that still cannot be resolved is recorded as
   `unresolved_event_reference` (currently zero) and stays out of the
   releasable set by definition of the predicate — but multi-hop initializer
   chains and dynamic IDs remain unexamined by construction.

Both are why the mode stays **off by default and gated on an in-game map-load +
playtest pass**. The measurement is the deliverable; the policy is not.

## What shipped

- `tools/build_emevd_entity_usage.py`: `has_character_operation()` — the
  reusable predicate over the committed `usage_classes` column.
- `tools/build_enemizer_catalog.py`: opt-in flag
  `--relax-non-character-emevd` (**off by default**). When set, it reproduces
  the census over the freshly derived slot policy and drops EMEVD protection
  only for logical placements with no character operation on any copy. The
  default `slot_policy.json` and the pinned 308-swap set are unchanged.
- `tests/test_enemizer_coverage.py`: pins the decomposition (2,332 / 67 / 10 /
  39), the delta (308 → 327, +19), the tier profile (0 boss), and the opt-in
  mode's **own** determinism fixture (327 across seeds and reversed inventory),
  kept separate from the default 308 pin in `research/enemizer/audit.json`.

No default swap set, safety gate, or MSBB writer behavior changed.
