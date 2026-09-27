# Shuffled boss activation audit

This audit covers all 22 destination arenas and the admitted main-game and
chalice donor routes. It follows the reported Gascoigne health bar outside
Oedon Chapel and Wet Nurse dying during Cleric Beast's entrance. Findings below
are static/generated-event evidence; they are not a claim of completed in-game
playtests for every pairing.

## Changes

- The final encounter builder bounds initial boss health bars, boss-room
  notifications and combat AI to the destination's original music region and
  map. Original host/client rules remain present.
- Separate phase routines use a per-load entry latch plus current map, rather
  than waiting repeatedly inside a potentially smaller music region during a
  transformation. A latch requires the destination start flag and room entry;
  constructor resets run before initializers. New IDs use the destination's
  existing event-flag bank and are checked for collisions.
- Positive HP phase thresholds require that latch, actor backread, and positive
  HP. Zero-HP death predicates retain their separate completion semantics.
- Gascoigne and Ludwig imported readiness/phase/AI routines wait for entered
  combat and live actors. Gascoigne death propagation waits for readiness.
- Celestial Emissary at Rom and Witches at Amygdala receive explicit live-actor
  witnesses before phase triggers. Celestial's giant death bridge first
  observes a living giant. Wet Nurse's proxy is kept loaded and its death bridge
  first observes positive HP before permitting a clear.
- All replacement entrances remove remaining exact original-boss forced
  animations. Combat-phase animations are outside this edit. Cleric's elevated
  entry warp, leap and delay are removed, including previously animation-only
  rewrites. Amygdala, Keeper, Pthumerian Descendant and Elder had
  replaced the animation/delay but retained that same elevated warp; it is now
  removed while their donor entrance motions remain. Already-grounded donor
  entrances remain accepted.
- Required ground and player warps remain. Laurence's original actor position
  is Y=1540.014, while entry region 3402853 is Y=1535.71; deleting that warp would
  leave the replacement at the statue instead of lowering it to the arena.
  Gascoigne, Ebrietas and Shadows retain their source-backed ground placements.

## Destination witnesses

Each row's music event and exact source hash are declared in
`tools/bb_enemizer/boss_activation.py`. The original event, rather than inferred
numeric region IDs, supplies the room witness. Shared-map bosses have distinct
regions and entry latches.

| Arena | Music event | Region/map condition | Per-load latch |
| --- | --- | --- | --- |
| amygdala | 13304803 | `PlayerInMap(33, 0) && InArea(10000, 3302802)` | 13304980 |
| blood-starved-beast | 12304803 | `PlayerInMap(23, 0) && InArea(10000, 2302801)` | 12304980 |
| celestial-emissary | 12424703 | `PlayerInMap(24, 2) && InArea(10000, 2422812)` | 12424982 |
| cleric-beast | 12414703 | `PlayerInMap(24, 1) && InArea(10000, 2412801)` | 12414980 |
| darkbeast-paarl | 12304703 | `PlayerInMap(23, 0) && InArea(10000, 2302812)` | 12304981 |
| ebrietas | 12424803 | `PlayerInMap(24, 2) && InArea(10000, 2422802)` | 12424981 |
| father-gascoigne | 12414803 | `PlayerInMap(24, 1) && InArea(10000, 2412812)` | 12414981 |
| gehrman | 12104803 | `PlayerInMap(21, 0) && InArea(10000, 2102802)` | 12104980 |
| lady-maria | 13504803 | `PlayerInMap(35, 0) && InArea(10000, 3502802)` | 13504980 |
| laurence | 13404853 | `PlayerInMap(34, 0) && InArea(10000, 3402852)` | 13404980 |
| living-failures | 13504853 | `PlayerInMap(35, 0) && InArea(10000, 3502812)` | 13504981 |
| ludwig | 13404803 | `PlayerInMap(34, 0) && InArea(10000, 3402802)` | 13404981 |
| martyr-logarius | 12504803 | `PlayerInMap(25, 0) && InArea(10000, 2502802)` | 12504980 |
| mergos-wet-nurse | 12604803 | `PlayerInMap(26, 0) && InArea(10000, 2602801)` | 12604982 |
| micolash | 12604853 | `PlayerInMap(26, 0) && InArea(10000, 2602852)` | 12604981 |
| moon-presence | 12104853 | `PlayerInMap(21, 0) && InArea(10000, 2102801)` | 12104981 |
| orphan-of-kos | 13604803 | `PlayerInMap(36, 0) && InArea(10000, 3602802)` | 13604980 |
| rom | 13204803 | `PlayerInMap(32, 0) && InArea(10000, 3202801)` | 13204980 |
| shadows-of-yharnam | 12704803 | `PlayerInMap(27, 0) && InArea(10000, 2702802)` | 12704980 |
| the-one-reborn | 12804803 | `PlayerInMap(28, 0) && InArea(10000, 2802802)` | 12804980 |
| vicar-amelia | 12404803 | `PlayerInMap(24, 0) && InArea(10000, 2402802)` | 12404980 |
| witch-of-hemwick | 12204803 | `PlayerInMap(22, 0) && InArea(10000, 2202801)` | 12204980 |

## Limits and runtime checks

The active m23 event binary matched the player's prepared seed exactly; the
Gascoigne adapter lacked a room witness on its health and phase paths. The
reason the player's start flag became active has not been established.

Music-region source conditions establish entry witnesses, not full collision
geometry. The per-load latch permits phase transitions after movement within
the encounter. Mesh fit, floor collision, animations supplied by transplanted
models and actual multiplayer behavior still need in-game validation. No
save/progression repair is performed, and an already awarded boss clear is not
undone.

The shared pass preserves completion and reward events. Death bridges are
reviewed separately from cleanup routines that intentionally kill retired
actors; cleanup is not blocked on room entry.

## Validation

- All 245 admitted directed pairings generated successfully; completion/reward
  event bodies remained unchanged by the shared activation pass.
- 41 focused root tests, 20 Gascoigne/Ludwig/port tests, and 11 special-phase
  tests passed. Final entrance tests cover the additional four warp remnants
  and Paarl's already-grounded form; quality-gate tests passed.
- A complete shuffled seed produced 61 verified files and 23 map variants,
  with zero missing AI goals. This output was not installed.
- All five affected Cleric routes compiled with the pinned DarkScript fixture
  after applying both shared safety passes. Donor/phase suites also compiled
  the affected source-specific outputs.
