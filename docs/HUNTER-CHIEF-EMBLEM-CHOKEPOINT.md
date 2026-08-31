# Hunter Chief Emblem chokepoint

Issue #243 is intentionally not represented as stricter world logic yet. The
game still permits the Healing Church Workshop bypass, so changing logic alone
would produce false spheres.

## Mapped native changes

The Blood Echo Bath sells goods `4011` from five NG-cycle copies of the same
lineup row:

| ShopLineupParam row | goods | price | purchase flag | unlock flag |
|---:|---:|---:|---:|---:|
| 100607 | 4011 | 10000 | 70009250 | 12101004 |
| 110607 | 4011 | 10000 | 70009250 | 12101004 |
| 120607 | 4011 | 10000 | 70009250 | 12101004 |
| 130607 | 4011 | 10000 | 70009250 | 12101004 |
| 140607 | 4011 | 10000 | 70009250 | 12101004 |

These are the only rows returned by inspecting the bundled supported
`ShopLineupParam` for `shopType=0`, `equipType=3`, `equipId=4011`. A playable
build must suppress all five and no other shop rows.

Cathedral Ward event `12400760` contains the independent far-side success
condition `ObjActEventFlag(12400170)`. `tools/patch_emblem_chokepoint.py`
removes that one disjunct while preserving both goods-`4011` interaction paths.
It pins the supported decompiled-source hash, verifies the exact event shape,
refuses overwrite, and emits a source/output ownership manifest.

## Remaining activation boundary

The inputs bundle contains the reproducible DarkScript source but neither the
licensed `m24_00_00_00.emevd.dcx` nor a DarkScript compiler. Therefore this
slice does not pretend that a `.js` file is a game-loadable patch and does not
remove the Workshop edge from world logic.

Activation requires one follow-up that is atomic:

1. compile the guarded source against a user-owned supported EMEVD;
2. verify only event `12400760` changed and record binary source/output hashes;
3. suppress exactly the five shop rows above in the composed param binder;
4. install both artifacts through the managed overlay manifest and restore path;
5. remove the unconditional `Healing Church Workshop -> Grand Cathedral` edge;
6. run the issue's front-side, far-side, reload, and Amelia smoke test.

Until all six happen together, current physical-game logic remains authoritative.
