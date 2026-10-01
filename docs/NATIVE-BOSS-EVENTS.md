# Native boss event emission

Boss seed generation no longer downloads or launches DarkScript. The launcher
passes original EMEVD binaries to `BBEnemizerWriter`, which reads and writes
Bloodborne events through SoulsFormatsNEXT. The builder consumes the committed
`tools/bb_enemizer/native_event_catalog.json`. Release packaging includes that
file in both the launcher and the standalone builder, and the launcher hashes
the builder's copy into the build identity.

The catalogue covers all 258 current directed boss routes, including chalice
donors. It contains 2,067 authored event templates and 6,931 literal constructor
statements. The existing Python adapters remain the behavior specifications;
changing an adapter requires refreshing its native templates. This is a
finite recipe emitter, not a general JavaScript compiler.

## Preservation and composition

Native instruction and parameter fingerprints select known source witnesses
for the existing adapter pin checks. Unknown unrelated events stay opaque and
are carried through unchanged. A changed event without a reviewed template
fails before publication. Known witnesses currently come from the owner's
`CUSA03173` AppVer `01.09` inputs; another original revision needs additional
witnesses rather than a guessed source conversion.

Nonzero events use the exact instruction bytes, layer masks, restart behavior
and parameter substitution records of their templates. Constructor edits are
anchored to unique native instruction sequences. Original instructions remain
unchanged except for literal removals/replacements and relocation of relative
skip counts. Ludwig's existing guarded initializer insertion is explicitly
supported; arbitrary changes to constructor control flow are refused.

AP overlays compose as binary edits against the same originals. Conflicting
event ownership or overlapping constructor edits fail. Protected progression
events cannot be replaced. Before writing, the native writer checks the input
file hash and recipe fingerprints. Serialized readback must preserve every
untouched event, event ordering, linked-file offsets and string data. The
builder publishes the complete overlay only after its remaining native checks.

## Development oracle

DarkScript 3.6.3 is retained only as an offline development oracle for refreshing
the catalogue. The refresh tool verifies the pinned executable hash. It does
not run during seed generation, and the catalogue does not include EMEDF.

```powershell
python -m tools.build_native_event_catalog `
  --events <private-original-event-directory> `
  --darkscript <pinned-DarkScript3.exe> `
  --writer tools/bb_enemizer_writer/bin/Release/net9.0/BBEnemizerWriter.dll `
  --work work/native-catalog-refresh `
  --output tools/bb_enemizer/native_event_catalog.json
```

Use a new work directory. `--resume` reuses completed original-source extraction
and checks that the original binary hashes still agree. Compilation stages are
fresh on each run. Re-run the route matrix and oracle comparisons when recipes
change; merely adding a route to the coverage list does not prove its encoding.

## Verification recorded on 2026-10-01

On the owner's original inputs:

- All 245 routes generated native event recipes, serialized successfully and
  passed persisted instruction/parameter fingerprint verification.
- Four representative routes (Cleric/Ludwig in both directions, Maria with
  Pthumerian Descendant, Rom with Ebrietas) matched the oracle for 64 changed or
  added nonzero events and all constructor instruction edits. Retained calls to
  disabled vanilla callees preserve their original unused argument payloads;
  the oracle unnecessarily re-encodes some of those payloads.
- Complete direct builds succeeded for BSB at Cleric and Pthumerian Descendant
  at Maria. Two complete `good` seeds succeeded with 67 files verified each;
  the second included the Cathedral AP overlay.
- Gascoigne at Hemwick composed with the native Hemwick AP gate and verified
  eight files. The PyInstaller builder also completed Maria/Descendant with
  its packaged catalogue and no compiler argument.

These are build and encoding checks. Gameplay, AP check delivery and co-op
behavior still require the existing playtest queue.

The subsequent [placement expansion](boss-placement-expansion.md) adds 13
verified native routes. Complete seed `2` builds passed in both pools: 66 files
verified for `good` and 61 for `reviewed`. Two Living Failures routes were
excluded after effect-bank conflicts failed preflight.

## CI and private workers

`tests/test_native_events.py` checks catalogue coverage and source/native
composition guards. `tests/native_events` generates synthetic Bloodborne
EMEVD records and exercises native serialization, layers, parameters, links,
strings, protected events, drift checks and malformed-recipe refusal. The
Linux synthetic integration job runs these binary checks without game files
or DarkScript.

Full seed builds still require original maps, parameters, scripts, characters,
effects and events. A private Linux worker can use those inputs with Python and
the .NET writer; removing DarkScript removes its Windows compiler requirement.
Keep full-game inputs and generated game overlays on the private worker. The
public synthetic job does not provide a full-game or gameplay validation gate.
