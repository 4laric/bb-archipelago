# Enemizer protection audit

Branch: `codex/enemizer-protection-audit`. Policy-neutral audit: **no default
swap set, safety gate, or writer behavior was changed.** The one analysis
defect that is fixed here is the EMEVD-usage census missing shared
(`common`) event bodies; the default 308-swap set is byte-identical before
and after. All counts below reproduce from committed inputs only:

```powershell
python tools/build_emevd_entity_usage.py          # regenerates the census + summary
python tools/audit_enemizer_protection.py         # regenerates research/enemizer/protection_audit.json
$env:PYTHONPATH = (Get-Location).Path; python -m unittest tests.test_enemizer_protection_audit tests.test_enemizer_coverage -v
```

## 1. Executive findings

1. **The published 308 → 336 (+28) relaxation delta was measured with an
   incomplete resolver and is wrong.** `tools/build_emevd_entity_usage.py`
   never parsed `common.emevd.dcx.js`, so every entity passed into a shared
   event (co-op/invader AI gates 9220/9240/9260/9280 and others) was recorded
   as `event_argument` with no resolved operations and classified as having
   "no character operation". Including common definitions moves **78 of 145**
   reviewable physical slots (and 47 of 86 relaxable logical placements) into
   the character-operation set. Corrected census: **2,332 with character
   operations, 67 without, 0 unresolved**. Corrected delta: **308 → 327
   (+19)**. Of the 9 removed candidates, all are `c1051` actors under active
   `SetCharacterAIState` / `ForceAnimationPlayback` / `CharacterDead` /
   `SetSpEffect` / `HPRatio` scripts — see §4 witness `m22_00_00_00`
   entity 2200710 → common event 9220.
2. **"Non-character" never meant safe, and the old code made UNKNOWN look
   like safe.** Before this audit, an `$InitializeEvent` argument whose callee
   could not be resolved (`target is None: continue`) was silently dropped,
   leaving `event_argument`-only rows that `has_character_operation()` reads
   as `False` — the exact predicate the relax flag treats as releasable. The
   prior doc language calling that bail "conservative" was backwards: it is a
   fail-open fallback. Fixed: common events are now resolved, and any still
   unresolvable callee is recorded as `unresolved_event_reference` (currently
   0 slots) instead of vanishing.
3. **First-hit rejection counters are not root causes.** The planner reports
   one reason per logical placement (precedence: EMEVD override → dummy →
   talk → CharaInit → non-character → missing params → tag → compatibility).
   The full multi-gate census (`research/enemizer/protection_audit.json`)
   shows most rejections carry several independent gates: game-wide, 884 of
   2,338 rejections are EMEVD-only, the rest overlap; in Central Yharnam
   (`m24_01`, 277 logical: 49 swapped, 228 rejected) **48 rejected placements
   carry EMEVD plus at least one other gate**, so relaxing EMEVD alone could
   at most release 83 of the 131 EMEVD-first-hit placements there — and most
   of those keep a character operation anyway.
4. **Two advertised overbreadths are real in the predicate but currently
   load-free.** Zero of 2,399 protected slots match only in comments, and zero
   logical protections come solely from a different canonical map than the
   slot's own. The 6–9-digit lexical scan *including comments* and the broad
   `m24`-prefix area grouping should still be narrowed (they are accident
   fuel), but neither inflates today's counts. The 876 cross-*file* physical
   protections are alternate-state copies (e.g. `m23_00_00_01` matched only in
   `m23_00_00_00`), which the logical grouping already unions by design.
5. **The committed census was stale in a second way.** The Hypogean Gaol
   commit (`ae783e0`) changed the Snatcher row's reason text without
   regenerating the table, and the builder's strict `==` filter then excluded
   it (2399 → 2397 on regen). Fixed with a substring match; the Snatcher
   remains protected (its reason no longer strictly equals the relax flag's
   match string, so the opt-in flag cannot release it either).
6. **Even the corrected +19 needs per-contract review, not a bulk release.**
   Every surviving candidate's callee resolves to real operations the family
   classifier does not count as character operations: `ForceAnimationPlayback`
   with model-specific animation IDs (7010/7011), `HasDamageType` predicates,
   `InArea` spatial checks (§5). Releasing them is proposed as reviewed
   tranches (§7), not applied here.
7. **Denominator hygiene.** 308 is *logical* swaps; 4,186 is *physical*
   slots. Correct rates: **308/2,646 = 11.6% logical**, 545 eligible-physical
   pre-planner destinations (≈13% physical, seed-stable in count though not
   in membership). 545 is the whole-plan physical fan-out, not Central
   Yharnam. Chalice templates (~664k rows) are outside both numerator and
   denominator.

## 2. Rule matrix (source → shipped planner)

Precedence in `classify_slot` (`tools/bb_enemizer/inventory.py:75-96`) is
top-down; the first hit wins the reported reason. The planner
(`tools/bb_enemizer/planner.py:240-282`) then applies donor/compatibility
gates. `apply_archetype_tag` (`inventory.py:99-111`) folds roster tags in
between. Overrides from `research/enemizer/slot_policy.json` bypass **all**
physical gates (line 76-85).

| # | Gate | Exact predicate | Source location | Precedence | Affected actors | Chosen by / evidence class |
| --- | --- | --- | --- | --- | --- | --- |
| G0 | Explicit override | `overrides[physical] or overrides[logical]` present → `randomize`/`reason` as written | `inventory.py:76-85`; data `slot_policy.json` (built by `build_enemizer_catalog.py:137-153`) | First; bypasses G1–G6 | 1,535 logical EMEVD + 1 Snatcher progression row | Project policy (bootstrap + `ae783e0` Gaol). EMEVD half is a lexical heuristic, **policy choice**, not observed constraint |
| G1 | No EMEVD coverage | area prefix not in extracted set → protect | `build_enemizer_catalog.py:139-145` | Catalog build | 0 slots today (all 14 areas covered) | Fail-closed project choice; dormant |
| G2 | Dummy / script-spawn | `slot.dummy` (MSB Part flag) | `inventory.py:86-87` | 2nd | 496 pure + overlaps (m35/m34/m36 heavy) | Project heuristic for authored spawns. **Unknown**: which dummies are spawn-point vs decoration is unproven per-Part; needs MSB spawn-graph review (tranche T4) |
| G3 | Talk-bound | `talk_id > 0` | `inventory.py:88-89` | 3rd | 41 pure-talk + overlaps | Project heuristic. Quest/dialogue protection is plausible but talk ID alone does not prove the dialogue matters (tranche T5) |
| G4 | CharaInit-bound | `chara_init_id > 0` | `inventory.py:90-91` | 4th | NPCs/hunters (m32/m33/m34 heavy) | Project heuristic. Bundles friendly NPCs, hunters, and special spawns in one predicate — overbroad by construction (tranche T5) |
| G5 | Non-character model | `not model.startswith("c")` | `inventory.py:92-93` | 5th | Objects, animals, SFX parts (m24/m34) | Project heuristic; sound |
| G6 | Missing NPC/Think | `npc_param_id <= 0 or think_param_id <= 0` | `inventory.py:94-95` | 6th | 6 pure + overlaps (m35/m36) | Engineering guard (no data to transplant); sound |
| G7 | Archetype approval | NpcParam `team == 23 and npcType == 0 and radius > 0 and height > 0` → `target` | `build_enemizer_catalog.py:109,121-133` | Folds into policy via `apply_archetype_tag` | 219/933 archetypes excluded as source *and* donor | Project policy. Faction gate is the strongest non-script protection; narrowing needs per-archetype review (tranche T6) |
| G8 | Alternate-state agreement | all copies `randomize` and all `SlotPolicy` equal, else reject (`protected copy:` / `alternate-state policy mismatch`) | `planner.py:228-233,240-256` | Planner, per logical | 1 variant-disagreement logical today | Sound consistency invariant |
| G9 | Donor eligibility | donor pool = archetypes from fully-eligible agreeing groups only | `planner.py:227-234` | Planner pool | Protected archetypes never leak as donors | Sound; prevents NPC→mob transplants through the back door |
| G10 | Same-model exclusion | skip `target_key == source key` and same `model_name` | `planner.py:267-270` | Per candidate | — | Design choice (every swap visually meaningful) |
| G11 | Tier preservation | `policy.tier == target.tier` unless `--allow-tier-mixing` | `planner.py:120-121`; tiers from `build_enemizer_catalog.py:37-45` (hp/souls/no-respawn/radius) | Per candidate | 0 boss donors/targets in default (41 boss archetypes never eligible: G7/G0 block them first) | Project policy; tier formula is heuristic |
| G12 | Size window | `+1 up / -3 down` on collider-derived classes | `planner.py:131-137`; classes `build_enemizer_catalog.py:25-34` | Per candidate | — | Project policy (asymmetric by design) |
| G13 | Locomotion | off by default; opt-in equality | `planner.py:122-128`; UI labels it experimental/incomplete | Per candidate | −3 swaps when enabled (305 vs 308) | Project option; tags incomplete by its own label |
| G14 | No compatible target | no family passes G10–G13 | `planner.py:276-282` | Terminal | small (3 of the old 86) | Outcome, not a guard |
| G15 | Boss-shuffle templates | only hand-verified `SwapTemplate` registry (today: BSB-at-Cleric) | `boss_shuffle.py`, `boss_contracts.py`, ~50 pairwise `*contract*.py` | Separate `--boss-shuffle` path, unreachable from launcher | 1 of 22 encounters | Hand-pinned evidence; **not** transferable permission (§6) |

Mismatches found (all pre-existing, none introduced here):

- `--relax-non-character-emevd` exists only in `build_enemizer_catalog.py`;
  nothing in `packaging/*`, `bb_launcher/*`, `tools/bb_enemizer/cli.py`, or
  `worlds/*` references it. The shipped catalog is always the conservative
  one; the relaxed set requires an offline regen. No UI implies otherwise
  today, but any future toggle must present it as experimental (+19, review
  pending), not as "more randomization".
- `bb_launcher/external_ui.py` and `bb_launcher/cli.py` drop `boss_pool`;
  `workflow.py` never emits `--boss-shuffle`. Launcher-reachable boss paths
  are canary + `reviewed` overlay only.
- `worlds/bloodborne` exposes **no** enemizer options at all (seed flows via
  `bb-seed-request-v1`; randomization is a launch-time decision). There is no
  global checkbox implying every enemy randomizes — keep it that way (§8).

## 3. Coverage: denominators that actually divide

- Inventory: **4,186 physical** fixed-map slots → **2,646 logical**
  placements → **308 swapped (11.6% logical)**, 2,338 rejected logical.
  Eligible-physical pre-planner fan-out: **545** (whole plan, all maps).
- EMEVD rule: **2,399 physical sightings = 1,536 logical** (1535 plain +
  Snatcher progression row). EMEVD-only rejections (no other gate): 884
  logical game-wide.
- Corrected census decomposition: **2,332** with ≥1 character operation
  (97.2%), **67** fully resolved without (2.8%), **0** unresolved, 2
  code-without-parsed-operation, 0 comment-only. Item-lot collisions: 308
  share a number, 2 are real `AwardItemLot` operands, **10** lack a separate
  character operation (down from 20 — the other 10 were common-event actors).
- Corrected relaxation: **39/1,536** logical placements lack a character
  operation on every copy; **19** become swaps (308 → 327, +6.2%); 20 stay
  vanilla under other gates (talk 41% of the old-86 table shape — recompute
  per release; see `protection_audit.json`).

Per-area logical swapped/logical (gate hits overlap, so rows do not sum):

| Area | Logical | Swapped | EMEVD | Dummy | Talk | CharaInit | Unapproved | Missing | Nonchar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| m21 | 36 | 0 | 36 | 3 | 26 | 0 | 14 | 0 | 0 |
| m22 | 98 | 11 | 80 | 9 | 4 | 29 | 14 | 0 | 0 |
| m23 | 118 | 4 | 98 | 15 | 4 | 42 | 16 | 0 | 0 |
| m24 | 593 | 88 | 293 | 203 | 57 | 43 | 116 | 28 | 2 |
| m25 | 110 | 8 | 96 | 6 | 14 | 4 | 10 | 0 | 0 |
| m26 | 144 | 28 | 101 | 18 | 5 | 11 | 19 | 1 | 0 |
| m27 | 221 | 83 | 115 | 9 | 7 | 34 | 36 | 1 | 0 |
| m28 | 207 | 5 | 144 | 60 | 5 | 14 | 41 | 14 | 0 |
| m32 | 137 | 8 | 95 | 54 | 6 | 51 | 16 | 2 | 0 |
| m33 | 120 | 25 | 55 | 28 | 2 | 39 | 10 | 0 | 0 |
| m34 | 255 | 25 | 158 | 123 | 8 | 31 | 106 | 9 | 5 |
| m35 | 346 | 6 | 148 | 204 | 21 | 31 | 83 | 43 | 0 |
| m36 | 261 | 17 | 117 | 127 | 8 | 0 | 53 | 25 | 0 |

Outside the inventory (not in any denominator): ~664k Chalice-template rows
(filtered by `load_slots(fixed_maps_only=True)`) and the recursive Chalice
EMEVD scripts the catalog deliberately does not traverse. No claim in this
audit covers Chalice dungeons.

## 4. Script-reference analysis: what the numbers actually prove

Namespaces: entity IDs (6–9 digits), ItemLot IDs, acquisition flags, event
IDs, and animation/SpEffect IDs share one lexical number space. The catalog's
`NUMBER` regex cannot tell them apart; the census can, partially: only **2**
of 308 item-lot collisions are genuine `AwardItemLot` operands. Typed
argument positions (`$InitializeEvent:event_id vs :argument`), callee
parameter resolution, and the `operation_family` classifier do the rest —
with the gaps this audit found:

- **Common/shared events were invisible.** 82 definitions in
  `common.emevd.dcx.js`, 305 area-file `$InitializeEvent` sites targeting
  events with no same-area definition, 0 multi-definition collisions
  globally, 0 within-file duplicate `$Event` IDs. The "ambiguous callee"
  bail therefore never fires today, but the *missing-callee* bail fired for
  every common-event call — and was mislabeled safe. Fixed by resolving
  through common definitions and recording `unresolved_event_reference`.
- **Comments and bare lexical matches are dead predicates today**
  (0 comment-only, 2 code-without-operation of 2,399), but the catalog still
  scans comments. Narrow the regex to code (strip `//` tails like
  `line_uses` does) so a future comment containing an entity ID cannot
  silently protect — or unprotect — a slot.
- **Broad-area grouping is dead weight today** (0 cross-canonical logical
  protections) but wrong in principle: group by exact map file plus common,
  union across a logical placement's alternate states explicitly, instead of
  by `m24` prefix.
- **Single-hop, single-definition resolution only.** Multi-hop initializer
  chains, indirect group references, and dynamic IDs are not followed; the
  census proves presence of operations, never their absence. `resolved/`
  prefixes mark the resolved subset; everything else is call-site syntax.

Witness (corrected-census smoking gun): entity **2200710** (`m22_00_00_00`,
`c1051`, a +28 candidate) is passed as `chrEntityId` to common events
9220/9240/9260/9280 (`m22_00_00_00.emevd.dcx.js:22-25`), whose bodies apply
`SetCharacterAIState`, `ForceAnimationPlayback` (anim 7010/7011/7012),
`CharacterDead` watches, `SetSpEffect` 9100, `RequestCharacterAIReplan`, and
`HPRatio` checks to that parameter. The old census recorded
`event_argument:4` and nothing else.

## 5. Dependency taxonomy (what each operation family needs)

**Identity-stable** (preserving entity ID + event bindings, which the writer
does, plausibly suffices; replacement model still needs compatible
skeleton for animations): presence/alive checks (`CharacterDead`,
`CharacterType`), enable/disable (`ChangeCharacterEnableState`,
`SetCharacterAIState` toggles), simple flag triggers, `HPRatio` watches,
`HasDamageType` predicates, `InArea`/`EntityInRadiusOfEntity` spatial checks.
Counterexample to "every character op is incompatible": a `CharacterDead`
gate that opens a door only needs *something* killable at that entity ID —
but the replacement must actually be killable by the player (a wall-beast
that cannot die would soft-lock; tier/size gates mitigate, not prove).

**Behavior-requiring** (replacement data must be adapted or the encounter
rewritten): `SetCharacterAIId` / AI state machines, `DisplayBossHealthBar` /
`HandleBossDefeat` / `HandleMinibossDefeat` (boss wiring), `SetCharacterTeamType`,
patrol/home/gravity/map-hit setup, NPC-part construction
(`CreateNPCPart`/`SetNPCPartHP` — limb counts differ per model: Cleric 5,
Amygdala 10, BSB 1), cloth/hitmask changes, `SetSpEffect` families that
assume a skeleton, and **`ForceAnimationPlayback` with literal animation IDs**
— the corrected +19 all carry this or `HasDamageType`/`InArea` (e.g. m26
`12600105` plays 7010/7011 on the entity; m24_02 `12425400` likewise; m27
`12705100` gates on `InArea` + damage type). Swapping the model under a
literal animation ID risks a T-pose/freeze or a silently skipped beat, not a
logic soft-lock — but that is a playtest verdict per event, not a census
verdict.

**Load-bearing without any character operation**: region triggers, action
buttons, treasure objacts, and initializer-only bindings (the m27 `c2190`
cluster: `$InitializeEvent` argument + `InArea`). These stay vanilla under
the corrected predicate only if a *different* gate holds them; 12 of them
are the corrected +19's largest block and need encounter review (tranche T2).

## 6. Boss adapters: transferable discipline, not permission

`bosses.py` explicitly disclaims safety (`runtime_validated=False`,
`approved_for_randomization=False`). `boss_canary.py` (BSB-at-Cleric) and
`boss_shuffle.py` (1-template registry) prove a *method*: hash-pin
originals, preserve destination entity/completion/start IDs and health-bar
labels, copy donor combat into project-owned event IDs after numeric
collision scans, verify byte-identity of unrelated events. The ~50 pairwise
`*contract*.py` files prove the *opposite* of generality: entry animations
(Cleric 3028 vs BSB/Paarl 7001 vs Amygdala 7003/7006/7002), phase/music/part
slots, multi-actor additions (Gascoigne human→beast, Witch second bride,
Orphan 980003/980004), and shared-cutscene arenas (Gehrman/Moon `m21`)
each need bespoke bridges. All are `runtime_status: unobserved`. Nothing
here licenses randomizing unreviewed encounters — common mobs or bosses.

## 7. Central Yharnam / bonfire case study

Committed-data facts: `m24_01` canonical = **277 logical** placements: **49
swapped**, 228 rejected (first-hit: 131 EMEVD, 79 dummy, 10 CharaInit, 7
talk, 1 unapproved). Multi-gate truth: **48** of the 131 EMEVD-first-hit
placements carry another gate (14 unapproved-only overlap, 14 dummy overlap,
10 talk+unapproved, 4 CharaInit, remainder mixed); 77 of all 277 carry 2+
gates. Per-copy gate hits for the map: EMEVD 131, dummy 96, talk 22,
CharaInit 28, unapproved 48, missing 4, variant-disagreement 1.

Bonfire-landmark mapping: **unproven**. No committed source ties the
observed bonfire cluster to exact actor IDs — MSB part names/coordinates
(`research/mined/msb_enemies.tsv` via `bb_inputs.py --get`) give candidate
positions, and per-swap coordinates ship in every plan's `destinations`, but
the parent session has not mapped the observed in-game cluster to IDs, and
the shad log line (`opens m24_01_00_01.msb.dcx`) is a generic guest-path
open, not proof of loaded bytes. Minimal witness to close it: an
`enemy-report --area m24_01` (or one screenshot with HUD position) naming
echo reward + nearest plan entries by coordinate, matched against the plan's
`destinations` for seed `28965067894467505359:1`. Until then, any "bonfire
IDs" list is inference, and this audit provides none.

What a first-area player should expect (default policy): roughly 1 in 6
placements changed (49/277); the lamp approach, scripted patrols under event
watches, NPCs/hunters, and doorway/despawn-gated dummies stay vanilla. That
is the design working, not a failure to activate.

## 8. Prioritized expansion tranches

Estimates only where marked; each tranche states its own recomputation.

| Tranche | Change | Coverage delta (est.) | Risk / cost | Acceptance |
| --- | --- | --- | --- | --- |
| T0 (done here) | Census: resolve common events, track unresolved, Snatcher substring | +28 → **+19** corrected; default 308 unchanged | Analysis only | Unit pins (this audit) |
| T1 | Strip comments from catalog scan; group EMEVD by exact map file + common, union over alternate states | **0** measured today; prevents future accidents | Static: regen diff must be empty on current corpus | Regen + pin |
| T2 | Hand-review the corrected 19 (m27 c2190 ×12, m23 c1090 ×3, m24_02 ×2, m26 c1241 ×2): per-event animation/predicate analysis + map-load + combat playtest each | **+19 logical** (39 released − 20 other-gated), physical fan-out recomputed at plan time | Medium: literal anim IDs, `InArea` triggers | Per-event sign-off + `stress:family` session per model |
| T3 | Character-op taxonomy pass: allowlist identity-stable ops (`CharacterDead` gates, enable/disable) with per-map verification, starting with m24_01's 83 EMEVD-only placements | Unknown until allowlist is defined; bounded by 884 EMEVD-only logical game-wide | High: each op needs a transplant-compatibility argument | Fault-injection tests + playtest per map |
| T4 | Dummy triage: separate spawn-points from decoration via MSB spawn-graph/event cross-ref | m35/m34/m36 heavy; est. small | Medium: authored-spawn risk | Static proof per released dummy + playtest |
| T5 | Split CharaInit (hunters vs NPCs vs quest) and talk (flavor vs quest) predicates | m32/m33/m34 heavy | High: quest-ownership research | Quest-owner sign-off per actor |
| T6 | Per-archetype faction review (team/npcType beyond the `23/0` blanket) | Bounded by 219 excluded archetypes | High | NpcParam + in-game behavior per archetype |
| T7 | Boss-shuffle registry growth (one template at a time, canary method) | Per-template | Very high | Full encounter playthrough per template |

Explicitly **not** proposed: bulk-releasing EMEVD-protected slots on the
character-operation predicate alone (T3's allowlist is the narrow version),
reaching the relax flag from the launcher UI before T2 completes, or
extending any denominator to Chalice content.

## 9. Presentation (launcher truthfulness)

- Report per-area "changed X of Y placements (Z% logical)"; never a global
  "randomized" percentage against 4,186 without saying physical-vs-logical.
- Name the top unchanged reasons per area in plain words ("scripted
  encounter", "NPC or hunter", "authored spawn", "quest dialogue") with
  counts from `protection_audit.json`; never "activation failure".
- The relaxed/expansion modes, if ever exposed, must be labeled experimental
  with their reviewed-tranche scope (e.g. "Tranche T2: 19 reviewed
  placements"), not a stronger "randomize everything" checkbox.
- `enemy-report --area` already says when an area has no swaps — keep that
  sentence; it is the anti-blame path for vanilla misbehavior.

## 10. Unresolved questions

- Do literal animation IDs 7010/7011/7012 exist on the +19's candidate donor
  skeletons? (Static binder check + playtest; blocks T2.)
- Which dummies/talk/CharaInit actors own quests? (No committed source;
  blocks T4/T5.)
- Live combat/traversal validity of any swap remains unobserved in this
  audit; all in-game acceptance in §8 is still owed.
- Cross-serial/version portability (CUSA00900 vs CUSA03173, AppVer beyond
  01.09) is untouched by this audit.
