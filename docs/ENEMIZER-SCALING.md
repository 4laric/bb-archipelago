# Enemizer scaling design

Status: **design**, written 2026-08-24 from committed data (`research/bb_inputs.db`:
`params/NpcParam.csv`, `params/SpEffectParam.csv`) and from the Elden Ring client's
shipped scaling stack (`from-software-archipelago-clients/crates/er-logic/src/{scaling,
native_tiers,rescale_watch,scaling_settle}.rs`). No prototype exists. Every number
below regenerates from the bundle; every game-behavior claim is labelled.

## Two consumers, one mechanism

1. **Transplant normalization.** The enemizer moves an enemy's NpcParam identity with
   it: a late-game enemy planted in Central Yharnam keeps late-game HP and damage. A
   swap manifest is not playable at scale until the transplanted enemy is renormalized
   toward its destination slot's difficulty.
2. **Depth/completion scaling.** The ER-style option: enemies in deeper seed regions
   scale up so progression feels paced. Not needed for slice-scale seeds; the design
   must not preclude it.

Both reduce to: *apply a chosen (hp, attack, defense) multiplier triple to one placed
enemy instance.*

## What the ER client teaches — and what BB gets to skip

ER applies scaling at **runtime**: the client walks live `ChrIns` sets and applies a
vanilla SpEffect rung per enemy. That bought a long tail of defects the ER repo spent
weeks settling: writes that don't recompute `max_hp` (er client#186/#188), unloaded
characters silently keeping stale HP, sweeps during map streaming crashing the game
natively, and progress counters reporting requests instead of results. ER needed all
of it because ModEngine gives no seed-time param overlay for per-instance edits.

**BB does not have to inherit any of that.** shadPS4's `CUSA03173-mods` overlay already
carries a per-seed `gameparam.parambnd.dcx` (the suppression binder) and per-seed
MapStudio MSBs (the enemizer writer). Scaling can be fully **static**: decided at plan
time, written into params the engine reads at character construction. There is no
write-vs-recompute race because there is no write to a live process. The entire
`rescale_watch`/`scaling_settle` apparatus becomes unnecessary by construction.

What we DO take from ER:

* **Use the game's own ladder, derived from params with asserted invariants** — never
  hand-invented multipliers (ER's `SCALING_TIERS` is derived from `SpEffectParam` at
  generation time, with `spCategory`/`haveSoulRate` asserted per row).
* **Reward-neutrality is a property to assert, not assume** (ER chose rungs with
  `haveSoulRate = 1`).
* **A native-tier oracle from the designers' own signal**, with an honest boundary
  around rows the signal cannot speak for (ER's `native_tiers.rs` and its excluded
  named characters).

## Bloodborne's native ladder: the NG+ block IS an area-tier table

`GameClearSpEffectID` is BB's NG+ mechanism: 814 of 6,064 NpcParam rows point at a
`74xx` SpEffectParam row named `周回パワーアップ_レベルN：<area>` ("NG-cycle power-up,
level N: area"). The designers tiered the game's areas 1–13 (14 = an NPC bucket) and
gave each level a rate triple. The main-line curve (7401–7413):

| level | area (row name) | maxHpRate | physAtkPowerRate | physDefRate |
|---|---|---|---|---|
| 1 | Cathedral B / start | 8.735 | 2.555 | 1.500 |
| 2 | ruins | 4.553 | 2.118 | 1.351 |
| 3 | Cathedral A / vicar | 4.118 | 1.683 | 1.326 |
| 4 | Cathedral C, first half | 4.946 | 1.776 | 1.367 |
| 5 | graveyard | 4.534 | 1.588 | 1.350 |
| 6 | forest | 3.967 | 1.402 | 1.243 |
| 7 | old home, first half | 4.022 | 1.397 | 1.220 |
| 8 | university | 2.496 | 1.334 | 1.176 |
| 9 | old castle | 1.887 | 1.283 | 1.156 |
| 10 | sacrifice village | 1.883 | 1.248 | 1.137 |
| 11 | Cathedral C, second half | 1.591 | 1.209 | 1.118 |
| 12 | trap road / nightmare | 1.456 | 1.143 | 1.080 |
| 13 | hub / final boss | 1.340 | 1.089 | 1.016 |

The curve is *inverted by purpose* — NG+ boosts early areas hardest so everything meets
one endgame bar. Read the other way, it is the designers' statement of **how far below
endgame each area sits**: relative area strength `S(level) ≈ 1 / maxHpRate(level)`.
That ratio is the transplant normalizer. Moving an enemy from a level-12 area into a
level-3 slot wants roughly `hp × (1/4.118)/(1/1.456) ≈ ×0.35`; the reverse transplant
wants `×2.83`. Attack uses the same construction on `physicsAttackPowerRate` (a gentler
curve, correctly — one-shotting is the failure mode to avoid).

Two honest caveats on the oracle:

* **The area labels attach to enemies, not maps** — coverage is 814 rows. The oracle
  for a *slot* is its map/area; the DLC blocks (7490–7497: Cathedral D, clocktower,
  fishing hamlet, boss variants) slot into the same level indices (11–13). A committed
  derivation (`level ↔ area ↔ map`) with each mapping's evidence is implementation
  step 1 and is fully regenerable from the bundle.
* **Echo reward is NOT a usable per-enemy fallback.** Measured on the 756 labelled
  main-line rows: per-level `getSoul` medians are non-monotonic (lvl 6 med 521 >
  lvl 7 med 394; lvl 12 med 1,089 > lvl 13 med 486) with enormous in-level spread
  (lvl 6 spans 0–6,811). ER could calibrate on rune rewards; BB's equivalent signal is
  too noisy to defend. Unlabelled enemies take their **area's** tier or stay untouched.

## Mechanism: cloned NpcParam rows + minted echo-neutral SpEffects

The engine applies a row's `spEffectID0..7` at character construction
(**inferred** — this is how the DS family behaves and how `GameClearSpEffectID`
itself works, gated on clear count; it has never been witnessed on BB in this project.
The canary below is the first game-session item).

Per (source enemy, target tier) pair the planner needs:

1. **Mint a scaling SpEffect row** per tier rung, cloned from a `74xx` template with
   the chosen `maxHpRate` / `physicsAttackPowerRate` / `physicsDiffenceRate`, and —
   asserted at build time — **echo-neutral** (`haveSoulRate = 1`; the NG+ rows
   multiply echoes 3–19×, which would corrupt the economy) and visually silent.
   New row ids live in a claimed, documented range (claim-registry discipline; the
   `74xx`/`79xx` neighborhoods are occupied).
2. **Clone the enemy's NpcParam row** to a new id in a claimed range, with the minted
   SpEffect in a free `spEffectID` slot. 6,006 of 6,064 rows have a free slot; the 58
   that don't (Iosefka-clinic variants, m12 rows, …) are skipped, fail-closed, and
   listed in the plan output. The clone must copy `GameClearSpEffectID` unchanged so
   NG+ still composes.
3. **Retarget the placed MSB part** to the cloned NpcParam id — the exact edit the
   MSBB enemizer writer already performs for swaps, extended by one field. Only the
   placements the plan names change; every other user of the original row is untouched.
   This sidesteps the shared-row problem (one NpcParam id serves many placements) that
   would make in-place NpcParam edits leak scaling onto vanilla slots.

Why not in-place `hp` edits: `hp` covers only HP (no attack lever — that lives in
AtkParam/behavior space), and 267 rows carry `hp = 0` (engine-default), where a
multiplier on 0 is meaningless. Rate-based SpEffects scale whatever the engine
computes, cover attack and defense, and match the game's own NG+ mechanism.

Pipeline placement: the planner (`tools/bb_enemizer`) emits a **scaling manifest**
beside the swap manifest, same `enemizer_seed`, deterministic (its own fixture, not the
existing `[308,308]` pin). The guarded writer applies both: param clones into the
binder build, part retargets into the MSB pass. Suppression tooling is untouched — the
scaling clones are *new* rows, and the suppression invariants (row id + `getItemFlagId`
preserved) never see them. Cloned rows keep `itemLotId_*` so drops follow the enemy —
consistent with slice-1 behavior; note the interaction with enemy-drop *checks* if any
are ever seeded (er#1000's lesson: settle whether a drop check is spawn-keyed or
entity-keyed before an enemy with a check attached is ever swapped or re-rowed).

## Tier policy (the knob, kept boring)

* **Normalization (default once enemizer playtests pass):** transplant multiplier =
  `S(dest area level) / S(source area level)`, clamped to a conservative band
  (e.g. ×0.25 – ×4) so a mismeasured area cannot produce a one-hit-kill or a sponge.
  Bosses and protected slots never scale (they never swap either).
* **Depth scaling (later, optional):** compose a second multiplier from AP region
  depth exactly as ER's basis-agnostic `region target → tier` mapping does, reusing
  the same minted rungs. Off by default; needs the AP world to export per-region
  depth, which slice-3's region graph already implies.

## What needs the game (owner session items, in order)

1. **The construction canary:** clone one Central Yharnam mob's NpcParam row, attach a
   minted `maxHpRate 2.0` SpEffect, retarget one MSB part, verify in-game that THAT
   placement (and no other user of the original row) takes ~2× hits to kill. This
   single test promotes the mechanism from `inferred` to `validated`.
2. Confirm a minted SpEffect id in the claimed range is inert otherwise (no visual,
   no echo change on kill).
3. One extreme-clamp spot check (weakest enemy at ×4, strongest allowed at ×0.25)
   for feel, before any default flips on.

Until item 1 passes, everything here is design. The enemizer writer playtest (#64)
should come first regardless — scaling normalizes a mechanism that has itself never
been seen live.
