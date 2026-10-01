# Boss variety: second pass, 2026-10-01

This follow-up adds 14 directed placements for **Only the good bosses**.
It builds on the [first placement expansion](boss-placement-expansion.md).

| Donors | Additional arenas |
|---|---|
| Pthumerian Elder, Pthumerian Descendant, Keeper of the Old Lords | Shadows of Yharnam, One Reborn, Witch of Hemwick, Living Failures |
| Watchdog of the Old Lords, Abhorrent Beast | One Reborn |

The four destination arenas had one, one, two and two eligible good-pool
donors respectively before this pass. The new humanoid adapters use the
pinned m29 health, wake and source-owned phase routines. Each arena keeps
its original completion, rewards, fog and guest-entry ownership. One Reborn's
guest entry drops only the displaced second-body enable instruction.

Original generators and helper AI retire before replacement combat starts.
The original terminal helpers remain disabled and invincible until replacement
death: two Shadows, One Reborn's proxy, Hemwick's second Witch or the Living
Failures aggregate proxy. The death bridge releases only those helpers to the
unchanged destination terminal. Living Failures also clears player effect
8035 and its five meteor SFX, and uses its own completion flag for music
cleanup. Maria's shared progression events remain unchanged.

The two additional One Reborn beasts reuse the existing Beast-possessed Soul
arena adapter. Each carries all five pinned m29 limb controllers and their
authored actor/part initializer arguments. Their music retains the first track
until destination completion, as in the existing reusable beast adapters.

## Measured variety and tradeoffs

Both samples use string seeds `0` through `999`, disallow self-pairings, and
measure the matcher before asset preflight. These are sample frequencies,
not uniform probabilities or gameplay observations.

| Arena / donor in good pool | After first pass | After second pass |
|---|---:|---:|
| Shadows / Ludwig | 100.0% | 53.0% |
| One Reborn / Beast-possessed Soul | 100.0% | 7.8% |
| Living Failures / Maria | 84.9% | 47.9% |
| Witch / Gascoigne | 89.2% | 76.5% |
| Gascoigne / Orphan | 39.6% | 64.4% |

One Reborn's most common choices are now Abhorrent Beast (42.2%) and Watchdog
(42.0%). Across all 22 arenas, the arithmetic mean of each arena's largest
pairing frequency falls from 49.9% to 44.5%.

The Gascoigne regression is real: the exact-family pool uses every family
once, so the new constrained arenas compete for the same three humanoids.
Orphan at Gascoigne remains below the original 77.0% sample, but this pass
does not preserve the first pass's 39.6%. The two new beast routes add families
beyond those three; they substantially improve One Reborn without fixing
every remaining matching bottleneck.

Remaining concentrated pairings include Wet Nurse at Logarius (76.6%),
Gascoigne at Witch (76.5%), Shadows at Celestial Emissary (68.7%), Gehrman at
Moon Presence (68.0%) and Moon Presence at Micolash (65.1%). The standard
pool's assignment counts remain identical to the first pass.

The before snapshot is `research/validation/placement-expansion-after.json`;
the after snapshot is `research/validation/boss-variety-pass-two-after.json`.
Reproduce the after snapshot with:

```powershell
python tools/analyze_boss_placements.py --seeds 1000 --output work/second-pass-distribution.json
```

## Source evidence and validation

All actor, event and generator identities come from the existing pinned
Shadows, One Reborn, Amelia/Hemwick, BSB/Living Failures and m29 contracts.
The four new bridge event IDs are collision-checked `12997420` through
`12997423`; they introduce no separate readiness flags.

The generated `chalice_complex_arena_pins.json` records 51 original primary
and helper actors across six physical map states. Regenerate it from private
original maps with `tools/build_chalice_complex_arena_pins.py --maps <maps>
--writer <BBEnemizerWriter.dll> --output <output.json>` (and `--dotnet` when
needed). The checked-in actor resource reproduces byte-for-byte.

Hemwick's m22_00 and Shadows' m27_00 effect banks have the exact original
bytes already witnessed for the other empty subarea banks, hash
`31f2b584d42fae7d923f116083f6cc9a772efe86caa2d707a66db756bd41441f`.
Their conflict proof adds those exact destination banks. Living Failures
shares Maria's existing m35_00 proof. Character roots and the existing
recursive-effect/runtime-precedence evidence limits remain the same.

All 14 routes completed native builds on private original inputs, including
effect preflight, actor/initialization checks, AI delivery and persisted
receipt verification. Complete good-pool seeds `0` and `2` also passed with
67 files verified each. Together they exercise the new routes at all four
arenas, including both beast alternatives. The refreshed native catalogue contains 272 routes,
2,093 event templates and 6,945 constructor statements, compiled with the
pinned DarkScript development oracle. Gameplay, arena geometry, AP check
delivery and co-op remain unobserved for the new routes.
