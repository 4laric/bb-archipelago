# Enemizer expansion: toward all-enemy randomization

Status: implemented, statically tested, **in-game validation owed**.
The conservative default (308 logical swaps) is unchanged. Three opt-in
release tranches replace one blanket exclusion each with reviewed
compatibility handling; they compose through the planner's `--release-file`
and the launcher's venture options (all default off). When any expanded
tranche is selected, the launcher also includes the source-pinned wakeup
fallback record; it is not a separate user option.

Regenerate everything from committed inputs only:

```powershell
python tools/build_quest_carriers.py
python tools/build_emevd_entity_usage.py
python tools/build_enemizer_catalog.py --release-contracts --release-script-spawns --release-chara-bound --release-wakeup-fallbacks
python tools/audit_enemizer_protection.py
$env:PYTHONPATH = (Get-Location).Path; python -m unittest tests.test_enemizer_releases tests.test_enemizer_coverage tests.test_enemizer_protection_audit -v
```

(The catalog's dump-layout defaults also work; the committed release
records were regenerated from `research/bb_inputs.db` materialized under
the ignored `work/` directory.)

## 1. Target population (logical placements, n=2,646)

| Population | n | Treatment |
| --- | ---: | --- |
| Hostile mobs (team 23 / npcType 0) | 2,142 | **Target.** Tranches below. |
| Boss-track hostiles (team 23 / npcType 1, 40; plus teams 20/24/25/28 npcType 1) | ~56 | Encounter-template track (§6), not mob donors. |
| Infighting faction (team 24 / npcType 0, 73) | 73 | Real enemies (Cathedral infighting pairs); need same-faction donor handling — future tranche, mechanism specified (§5). |
| Quest pigs (team 25 / npcType 0, 6) | 6 | Ribbon mechanism is entity-bound EMEVD/treasure, not the NpcParam lot (vials-only); kept out pending faction-behavior review. |
| Patrol-dummy infrastructure (team 22, c9030 leaders) | 45 | Non-enemy: group-patrol dummies followers track. Excluded with evidence (designer name 集団巡回ダミーリーダー). |
| Neutral markers (team 0, all dummy) | 92 | Non-enemy objects. Excluded. |
| Co-op guests (team 20) | 22 | Allies (incl. Gascoigne guest). Excluded. |
| Friendlies/NPCs (team 26, talk-heavy; team 27; team 28 event actors; team 29 bullet dummies) | ~200 | Friendlies, event actors, markers. Excluded with per-team evidence. |
| Missing NpcParam rows (8, all dummy) | 8 | No data to transplant. Excluded. |

Team semantics come from NpcParam designer names, not assumption:
c9010/26 = warp-statue dummy; c9010/28 = sound-trap bullet owner;
c4000/29 = bullet-owner dummy; c0000/26 = lonely old woman (friendly);
c2710/20 = Gascoigne co-op guest; c1090/c4140/24 = infighting beasts
(同士討ち); c1270/25 = ribbon boar; c5140/23,1 = boss-track.
Quest-drop carriers (142 logicals, 86 hostile) are excluded from every
tranche: their exact NpcParam row owns a flagged or quest-goods lot the
drop rewriter deliberately leaves vanilla
(`tools/build_quest_carriers.py` → `research/enemizer/quest_drop_carriers.json`).

## 2. Tranches (measured at seed 12345; seed-stable)

| Tranche | Record | Keys | Swaps (alone) | Central m24_01 |
| --- | --- | ---: | ---: | ---: |
| default | — | — | 308 | 49 / 277 |
| contracts (supported script contracts) | `release_contracts.json` | 750 | 827 (+519) | 94 |
| spawns (hostile script-spawns, incl. CharaInit-bound) | `release_spawns.json` | 666 | 796 (+488) | 106 |
| chara (hostile CharaInit-bound) | `release_chara.json` | 294 | 345 (+37) | 59 |
| wakeup helper (`release_wakeup.json`) | 10 keys (8 newly eligible) | — | 316 alone | 57 |
| **all combined + helper** | union (1,437 keys) | — | **1,633 (+1,325)** | **199 / 277 (72%)** |

Why chara alone converts little: most CharaInit hostiles are also
EMEVD-protected; the tranche composes (union) rather than acting alone.
The 78 CharaInit-bound script-spawn Parts (e.g. the face-down Central Yharnam
crawlers) are listed in both the spawns and chara records and only swap when
both tranches are on.

## 3. Compatibility handling (what replaced each blanket)

- **EMEVD lexical match → contract classes**
  (`tools/bb_enemizer/script_contracts.py`, total over the observed
  77-operation vocabulary; unlisted ops fail closed). Supported: reads and
  predicates, generic AI-interface toggles (donor AI is transplanted),
  backread/LOD, absolute data writes (team/flags), transform/physics
  (preserved), event plumbing (preserved bindings), death/treasure
  mechanics, netcode/co-op plumbing, fire-and-forget animation
  (0 of 1,222 playback calls inside WaitFor corpus-wide — no wait-hang
  mechanism; downstream animation-state/TAE/flag effects unvalidated,
  playtest owed), ID-addressed SpEffect writes (no live
  set-then-wait-same-effect pair outside parts-gated placements;
  wrong-skeleton behavior unvalidated, playtest owed), and all
  spatial/object/presentation/item-lot families (preserved world data).
  Hard (stay protected): boss wiring (33 logicals), NPC-part/limb ops
  (36), `SetCharacterAIId` (221+5, except the exact wakeup placements
  handled by the pinned fallback below), `RequestCharacterAICommand` (261 —
  per-command review owed), `RequestAnimationPlayback` (1, unproven),
  `SetSpEffectAndUnknown200455` (unknown semantics).
- **Dummy gate → spawn handling**: entity ID, part name and spawn triggers
  preserved by the writer; the planner's size gate bounds spawn-closet
  overflow. 499 of 596 dummy hostiles have zero script references;
  EMEVD-carrying dummies compose with the contracts tranche (hard-flagged
  ones stay blocked through the still-present override).
- **CharaInit gate → donor-init handling**: the donor's own CharaInit
  travels inside the swapped archetype tuple; talk-bound actors are never
  released by any tranche (talk corpus empty → quest ownership unprovable).
- **Central Yharnam sleep-to-wake animation**: for the ten pinned `c1120`
  placements, the writer suppresses only their `InitializeEvent` calls to
  event 12415130 when those placements actually swap. That event assigns
  special AI IDs 112499/112400 around sleep and wake animations 9000/9061;
  those IDs cannot be carried onto donor AI. The event body has no AI-disable,
  backread, or quest-flag writes; all other event calls and spawn handling
  remain intact. The two dummy-spawn placements still need the spawn tranche.
- **Never released by any tranche**: talk bindings, non-character models,
  missing NPC/Think rows, unapproved (non-hostile) archetypes, the
  Snatcher progression row, quest-drop carriers, boss/parts/AI-ID/AI-command/
  unknown-op placements.

## 4. Remaining gaps (truthful, bounded)

- Talk-bound hostiles (34): quest ownership unprovable offline (talk corpus
  pending in bundle). Needs ESD/quest research.
- Infighting faction (73): needs same-faction donor pool + coordination-op
  review. Mechanism: team-restricted donors + existing contract classes.
- AI-command placements (261): per-command-ID semantics review.
- Unknown-effect placements (63): operation research.
- Boss encounters: 22 arenas × 22 donors, 67 directed pairs in the reviewed
  pool (`reviewed_compatibility()`), all statically verified,
  **in-game validation owed for every pair**; canary (BSB-at-Cleric) is the
  only pair with any live history, itself incomplete.
- Chalice dungeons: outside the inventory by design (fixed-map scope).
- Every tranche: map-load + combat playtest per area (see enemy-report flow).

## 5. Presentation (launcher)

- Three venture checkboxes (all default off, all labeled experimental,
  gameplay untested); seed identity + cache records carry
  `release_tranches`; enemy reports name them; areas with no swaps say so.
- Per-area truthful summary reads `protection_audit.json` +
  plan `destinations`: "changed X of Y placements", never a global
  "randomized" percentage, never "activation failure" for ordinary
  exclusions. First-area expectation with all tranches: ~2 in 3 placements
  changed in Central Yharnam (187/277); lamp approach, NPCs, quest actors
  and hard-wired encounters stay vanilla by design.

## 6. Implemented vs in-game-validated ledger

| Item | Implemented + static tests | In-game validated |
| --- | --- | --- |
| Default 308-swap policy | yes | partial (prior playtests) |
| contracts / spawns / chara + wakeup fallback | yes (pins: 827/796/345/1633) | **no** — owed |
| Boss reviewed pool (67 pairs) | yes (existing contract tests) | **no** — owed |
| Central Yharnam visibility (187) | yes (plan-level) | **no** — owed |
