# Boss placement expansion — 2026-10-01

This pass adds 13 directed routes. The matcher algorithm and donor rosters
stay the same; compatible combat adapters and destination support expand.

| Donor | Additional destinations | Pool |
|---|---|---|
| Shadows of Yharnam | Cleric Beast, Blood-starved Beast, Paarl, Amelia, Amygdala, Ebrietas | Standard and Only the good bosses |
| Living Failures | Cleric Beast, Amelia, Amygdala, Ebrietas | Standard |
| Pthumerian Elder, Pthumerian Descendant, Keeper of the Old Lords | Gascoigne | Only the good bosses |

Shadows retain all ten combat/snake/attachment actors, three generators and
twelve spawn regions. Their three deaths release an inert destination primary
to the original reward event. Living Failures retain their six actors, referred
health proxy, four generators, five regions and five MapSFX records. Their
controllers wait for health setup and stop combat side effects at completion;
cleanup clears the player effect, SFX and health bars. All physical destination
map states use the same logical assignment with individually pinned anchors.

The Chalice donors use their original m29 health/AI/phase routines at Gascoigne.
His original beast stays hidden and invincible until completion, navigation
initializers and transformation controllers retire, and the destination keeps
its rewards, guest entry and notification ownership. Gascoigne shares Cleric's
exact m24_01 effect bank, so the existing pinned character-bank conflict proof
applies to these three new deliveries.

Living Failures at BSB and Paarl were attempted and excluded after native
preflight proved a conflict: m23 and m35 contain different bytes for
`effect/f000626200.fxr`. The current full source-bank union cannot preserve
both. Those routes are absent from the registry and rejected by the adapter.

## Distribution

Both snapshots use string seeds `0` through `999`, disallow self-pairings,
and run the matcher before asset-conflict selection. They measure this sample,
not uniform probabilities or final distributions after native preflight.

| Pool | Arena / donor | Before | After |
|---|---|---:|---:|
| Standard | Orphan / Shadows | 66.0% | 36.1% |
| Standard | Laurence / Living Failures | 53.2% | 30.1% |
| Standard | Maria / Living Failures | 46.8% | 37.8% |
| Standard | Gascoigne / Orphan | 28.5% | 26.2% |
| Only the good bosses | Gascoigne / Orphan | 77.0% | 39.6% |
| Only the good bosses | Orphan / Shadows | 24.0% | 21.6% |

Witch, Rom and Living Failures remain excluded as good-pool donors. Standard
Witch-at-Amygdala and Rom-at-Ebrietas remain near 50%. Remaining good-pool
bottlenecks include Ludwig at Shadows and Beast-possessed Soul at One Reborn
(100% in this sample), Gascoigne at Witch (89.2%), Maria at Living Failures
(84.9%) and Shadows at Celestial Emissary (65.6%). This pass does not claim
to make the complete assignment distribution uniform.

Counts live in `research/validation/placement-expansion-before.json` and
`research/validation/placement-expansion-after.json`. Reproduce the current
snapshot with:

```powershell
python tools/analyze_boss_placements.py --seeds 1000 --output work/placement-distribution.json
```

Newly generated or rebuilt seeds can change assignments because the route graph
changed. Previously generated overlays keep their original placements.

## Validation

All 13 retained routes completed native builds on the owner's original inputs,
including serialized actor/region/generator/event checks, AI script delivery,
effect-bank preflight and persisted receipt verification. The two m23 Living
Failures routes failed preflight and were removed. Native event recipes were
refreshed using the pinned development oracle; seed generation uses the native
catalogue without a compiler dependency.

Complete seed `2` builds also passed in both pools: 66 files verified for
`good` and 61 for `reviewed`. The final catalogue covers 258 routes with
2,067 event templates and 6,931 constructor statements.

Focused tests cover source drift, complete alternate map states, progression
preservation, authored initializer slots, terminal ownership, referred health,
player-effect cleanup, source-bank delivery and forced complete good-pool
assignments for every new Shadows and Gascoigne route.

These checks establish construction and encoding. Gameplay, geometry, AP check
delivery and co-op behavior remain unobserved for the new routes.
