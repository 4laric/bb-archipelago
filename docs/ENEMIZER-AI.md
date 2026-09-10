# Enemy AI transplantation

Target: CUSA03173, AppVer 01.09. Recorded 2026-09-09.
Status: static analysis and persisted binary tests; **not live-validated**.

## Defect and evidence

The user reported that randomized enemies mostly stand idle. The existing
writer changed `ModelName`, `NPCParamID`, `ThinkParamID`, and `CharaInitID` but
never wrote `script/*.luabnd.dcx`. Original map-specific AI therefore remained
unchanged even when a replacement required different goals.

Original local base/update files were resolved per file, with update precedence:

- `dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx`, `NpcThinkParam`;
- `dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx`;
- `dvdroot_ps4/script/aicommon.luabnd.dcx` and the fixed-map binders;
- the bundled `mined/msb_enemies.tsv` and the committed enemizer catalog.

For seed `enemizer-ai-repair`, 220 of 308 logical swaps required at least one
goal ID absent from both the destination and common `LUAINFO`. This is a
measured missing-resource defect and a strong explanation for idle enemies;
it is not a live causal witness. For example, replacing
`m22_00_00_00:c2630_0000` with `c1060`, Think row 106000, requires battle goal
106000 (`BrainEater106000Battle`). The destination does not provide that goal;
the authored `106000_battle.lua` exists in other map binders. The writer now
imports it and its registrations.

The inspected 24 base-listed fixed maps contained 2,890 normal enemy Parts,
all with `InitAnimID = -1`. There was no evidence supporting an animation
rewrite, so the existing animation-preservation contract remains intact.

The actual Think table also contains two different rows with ID 250100. The
importer refuses that ID if selected and its required goal fields disagree;
it does not arbitrarily choose which duplicate the engine uses. Unselected
duplicates do not prevent a build.

## Implementation and limits

`tools/bb_enemizer_writer/AiTransplant.cs` reads requirements from the source
parameters, finds the corresponding authored script and registration, imports
missing donor-context helpers and named subgoals, and merges registrations.
`Lua50.cs` reads globals from all nested prototypes, distinguishing top-level
definitions from runtime scratch writes. It follows the documented Lua 5.0
[chunk layout](https://www.lua.org/source/5.0/lundump.c.html) and
[instruction layout](https://www.lua.org/source/5.0/lopcodes.h.html).
Bloodborne's observed header is checked before parsing. Lua 5.1 and other
layouts are refused. No game script is executed or decompiled into a rewritten
replacement, and no executable patch was necessary for this defect.

The donor index remains immutable while individual destination binders are
built. Reused goal IDs are distinguished by their registration names and
script kind. Existing files, registrations, and order are retained; imported
chunks are byte-identical to their source. The report records source, plan,
parameter, and output hashes. The launcher stages the effective original
script set, makes AI inputs part of cache identity, and verifies AI/map coverage
before activation. The `enemy_ai_version` option forces prior map-only caches
to rebuild while retaining their existing placement seed.
The placement plan is retained beside `seed-manifest.json` as
`bb-enemizer-plan.json`, with its hash and swap count under `enemizer.plan`.
The AI report is retained under `enemizer.ai` and copied into the activated
ownership record.

This is static dependency analysis. It does not prove dynamic Lua lookups,
event-driven activation, arena assumptions, navigation, effects, animation
compatibility, or boss progression. Existing boss/event protections remain.
Missing functions already absent from a donor's own load context are not
resolved by importing unrelated enemies with similarly named scratch globals.

## Reproduction and checks

```powershell
dotnet run --project tests/bb_enemizer_writer -c Release `
  -p:SoulsFormatsNextRoot=C:\path\to\pinned-SoulsFormatsNEXT
python -m unittest tests.test_enemizer_ai tests.test_launcher_ui
```

The binary integration test creates synthetic BND4, PARAM, LUAINFO, LUAGNL,
and Lua chunks. It exercises shared numeric logic/battle IDs, helper and
subgoal dependencies, alternate maps, ID collisions, ambiguous donors,
missing Think rows, source preservation, deterministic serialization, audit
mode, invalid headers, and nested globals. It requires no licensed inputs.

On the owner's real files, seeds `offline-audit-0` through `offline-audit-24`
each produced 308 logical swaps. All 350 destination binders (14 per seed)
were written with the repository-pinned SoulsFormatsNEXT revision
`7cef52a7366678448d85930eeb8e94093b179d24`, reopened, and verified with zero
requested goals missing afterward. Local, ignored reports are under
`work/enemizer-ai-inspect/seed-audit/`. They are file-level evidence only.

## Live acceptance session

Existing data checked: the original map/parameter/script inventory and the
25-seed persisted-output reports above. They cannot show an enemy detecting
or attacking a player. No runtime hook is proposed; the observed behavior
and exact installed file hashes are the evidence for this session.

Hypothesis: installing each replacement's missing AI makes previously idle
enemies acquire the player and use their authored combat behavior.

Cost: approximately 10–15 minutes plus travel, two or three restarts. Use a
throwaway character or a backed-up save. The result decides whether the
transplant mechanism can be promoted to live-tested, or whether the next
investigation should trace activation/events, navigation, or resource loading.

1. **CONTROL:** on the chosen test character, use vanilla launch and verify
   one ordinary nearby enemy detects and attacks. Record the map/location and
   start/end of this step in a continuous video or timestamped notes. Wait five
   seconds before and after. If vanilla AI is idle too, stop: this is a control
   failure, not evidence about the transplant.
2. **REPLACEMENT:** close the game, use the repaired launcher with the same AP
   seed and Randomize Enemies enabled, and record its cache key/build report.
   At a visibly replaced enemy, wait five seconds, approach through its sight
   range, then retreat. Record detection, movement, an attack, and response to
   being hit. Wait five seconds afterward. Retain the source/destination/Think
   tuple from the seed manifest or AI report.
3. **RELOAD:** quit normally, relaunch the same seed, and revisit a respawning
   replacement. Repeat detection and attack. Confirm the same model remains
   installed. Include at least one replacement whose goal was absent before
   repair; an already-native goal is a useful comparison, not the decisive
   witness.

True prediction: the correct replacement spawns and demonstrates detection,
movement where appropriate, and attacks, including after reload.
False prediction: the correct replacement and verified AI files load but it
remains idle while the vanilla control works.
Invalid session: the model never changes, the installed file hashes do not
match, the wrong cache launches, or the control fails. A crash is a separate
failure requiring the emulator log and exact donor/destination pair; it is
not evidence of successful AI repair.

One pair is an initial witness, not whole-roster validation. Before calling
the feature broadly tested, repeat with several families across at least two
maps, including a donor with custom logic as well as a common-logic donor.
