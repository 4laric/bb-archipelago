# Enemizer implementation checkpoint

User authorization (2026-09-09): continue working through remaining enemizer
features while the user is AFK. Heartbeat `continue-bloodborne-enemizer-implementation`
continues this task every 30 minutes. The user subsequently authorized shipping
the opt-in changes for public playtesting. Published `v0.1.0-enemizer-playtest.1`
from commit `258d160aa7c0a44fa27a13b4d451b7e1aadb121e`; follow-on development stays local until
separately authorized. Earlier published release: `v0.1.0-enemizer-ai.1`.

Scope clarification: the user explicitly added **boss randomization** ("bosses
too"). Prioritize that track next. The older #133 note saying not to start a
branch is a historical project assessment, not a restriction on this newly
authorized work. Start with the original boss/EMEVD coupling census and a
boss-specific roster; continue into experimental compatibility, planning,
AI/scaling and event handling where evidence supports implementation. Preserve
the destination defeat flag and AP progression chain. Trace activation, fog,
health bars, cutscenes and multi-actor phases; do not simply remove protection
rules. Use original binary/Ghidra investigation where needed. Keep unvalidated
swaps default-off and record live acceptance requirements. Do not stop at
research if independent implementation work is possible.

## Current work

Branch: `codex/enemizer-scaling`, based on AI repair commit `dcb2171f`.
Scaling implementation checkpoint commit: `6413469` (local, not pushed).
Issue #186 has been assigned to the signed-in owner; no competing PR was open.
Completed the guarded `BBEnemizerWriter --scaled` path, matching map retargets,
AI transplantation, and composition with the already-built suppression
gameparam. Experimental, off by default, and not yet exposed in launcher UI.
The map-only writer now refuses enabled scaling plans instead of silently
ignoring them. Implementation: `ScalingTransplant.cs`, map runner extracted in
`Program.cs`, `ScalingTests.cs`, and stronger Python ladder assertions.

Evidence from original bundled SpEffect 7401: besides HP and four attack and
defense rates, it changes `staminaAttackRate`, `haveSoulRate`, and
`bGameClearBonus`. A normalization clone must neutralize the stamina/reward
changes and clear the NG-cycle marker; copying the template blindly is wrong.
Runtime application and NG+ composition remain inferred pending #187.

Scaling validation (2026-09-09):

- 73 synthetic scaling integration assertions and 23 existing AI assertions
  pass using the ordinary local `dotnet run` command. No Application Control
  change was necessary; the earlier apphost failure did not recur.
- 26 focused Python tests pass. `build.ps1 -Test -Preflight` passes with
  1,133 tests / 49 skips per run (the gate runs the suite twice).
- Four real-file seeds built successfully against an existing suppression
  binder. `scaling-fixture`: 237 NPC clones / 71 effects; audit seeds 0..2:
  216/64, 221/67, 213/69. Each builds 22 maps and 14 AI archives with zero
  required goals missing. After the final ordering/template guards, reran
  `scaling-fixture` successfully into `work/enemizer-scaling-final`.
- Original NPC rows reach 910301060; the new 6000000 range must be inserted
  among them, not appended. The writer preserves original relative row order,
  inserts new IDs before the first greater row, and verifies both complete
  output and original row subsequence. Original SpEffect ordering is not
  globally sorted and is deliberately preserved.
- Logs: `work/enemizer-ai-inspect/scaling-tests.log`, `scaling-gate.log`;
  real audit summary: `work/enemizer-scaling-inputs/audit-summary.json`.
- No game launch, active-overlay installation, release, or live stat claim.

## Completed baseline

- AI transplantation and launcher cache validation published in the signed
  prerelease, source `dcb2171f80aa440d4d7f4207fbca0e935dbac3c5`.
- CI run 34346149037 passed; release package job 34346350626 passed.
- Downloaded ZIP SHA256
  `fb200fb2a19ab887a469e4030b7bbfd214dda14f5d456b91c52a5b5b8ea6b861`;
  provenance, eight timestamped signatures, 1,072 package hashes and frozen
  launcher self-check passed locally.
- Signed AI writer rebuilt 14 real map binders with 188 added scripts and
  zero required goals missing. No live combat test has been performed.
- Release run 34346350626 is now fully successful, including VirusTotal reporting.

## Diagnostic followup

Implemented in `bb_launcher/enemy_report.py` and the AI writer receipt:
source/replacement ThinkParam IDs, per-ThinkParam actual logic/battle goal IDs,
per-map required goals, imported script donors/hashes, output hash matching,
and planned-versus-applied scaling details. Older receipts remain readable
and explicitly lack goal detail. Fixed current-settings seed misidentification
and cross-area echo ranking when the reported area had no swaps.
Tests: 82 focused report/AI/launcher-UI tests pass after final formatting;
binary suite now has 73 scaling and 26 AI assertions. Full repository gate
passed before this diagnostic followup. Logs:
`work/enemizer-ai-inspect/diagnostic-tests.log` and
`work/enemizer-ai-inspect/diagnostic-binary-tests.log`.

## Environment and preservation

- Leave user changes to `docs/SPEC-peliarch-bloodborne.md` and `.claude/` alone.
- SDK: `work/dotnet-sdk/dotnet.exe`.
- Pinned SoulsFormats: `work/SoulsFormatsNEXT-release`, commit
  `7cef52a7366678448d85930eeb8e94093b179d24`. The other checkout is incompatible.
- Original game root:
  `C:/Users/alari/Downloads/BB_Launcher-win64-qt-2026-08-09-f092023/install`.
  Patch gameparam, base paramdefs; effective original scripts already staged
  in `work/enemizer-ai-inspect/scripts`. Never use active mod scripts as donors.
- Windows Application Control blocked unsigned apphosts. Do not bypass it.
  Standard SDK builds/tests may work through the managed test runner; if blocked,
  record the limitation and rely on CI only when separately authorized to push.
- Read CONTRIBUTING.md and docs/RESEARCH-BASELINE.md for evidence conventions.
  No existing Bloodborne randomizer code or datasets may be reused.

## Next independent work

### Local seed handoff and AI script IDs, 2026-09-10

- Successful launcher-owned local hosting now records the selected archive's
  validated seed/player for its loopback address. Identity changes happen only
  after `start_server` reports readiness; failed starts preserve the old lock.
  Session ledgers and other server identities are untouched. Ordinary remote
  connections still use the existing mismatch guard.
- Original CUSA03173 01.09 common/map AI binders use script IDs in 1000..3009
  across the inspected corpus; metadata occupies 1000000/1000001. The separate
  eventcommon binder uses script IDs 0/1. The AI importer previously allocated
  new chunk IDs starting at zero. It now appends after the destination's highest
  script ID, with minimum 1000 and a metadata-boundary check; cache version is 3.
  Synthetic fixtures now match original AI IDs instead of masking this mismatch.
- This is observed archive-layout evidence, not proof of the native loader's
  filtering rule or confirmation that combat freezing is resolved. Static
  inspection of direct numeric subgoal calls and literal callback names did
  not identify another missing dependency in the inspected seed.
- Binary suite: 36 AI, 79 scaling, 37 boss assertions passed. Local-host suite:
  28 tests passed. Original-input audit: 25 seeds, 350 archives, 17,234 script
  entries all within the original AI ID range. Evidence is under
  `work/combat-ai-inspect/`; no original game files were changed or installed.

### Offline hardening batches, 2026-09-10

- User confirmed the reported attack-then-freeze occurred with AI transplantation
  installed. Do not attribute it to the old map-only release. No runtime cause
  or combat fix has been established from this work.
- AI imports now repair metadata for byte-identical retained chunks and visit
  retained roots/helpers/subgoals. Map subgoal registrations must have chunks;
  recursive helpers use a visited set. Referenced same-file helper version
  conflicts fail preflight. Different filenames defining the same global remain
  an unresolved semantic boundary, since original archives contain such overlap.
- Launcher AI cache version advanced to 2 so old outputs rebuild. Planner donor
  eligibility now requires a consistent eligible logical placement, preventing
  protected alternate-state copies from supplying otherwise excluded donors.
  Another independently eligible placement can still supply that archetype.
- Added `python -m tools.audit_enemizer_seeds` for isolated original-input batches,
  with per-seed output, failure logs, receipt/hash checks and cumulative coverage.
  Final run: `work/enemizer-batches-final-audit/summary.json`; 25/25 seeds passed,
  350 written/reopened AI binders, 905 canonical map/Think pairs, 308 swaps per seed.
  This is static archive validation, not movement/combat evidence.
- Binary suite: 35 AI, 79 scaling, 37 boss assertions passed; log
  `work/enemizer-batches-binary-tests.log`. Includes missing retained metadata,
  helper cycles, retained helper dependencies, missing registered subgoal chunks,
  and conflicting helper versions refusing before output.
- Final `./build.ps1 -Test -Preflight` passed both suite runs: 1,161 tests,
  49 skips, plus generated-table/shipping-boundary checks. Log:
  `work/enemizer-batches-final-gate.log`.
- No installation, commit, publication or external messages in these batches.

### Opt-in playtest release preparation, 2026-09-09

- User authorized shipping without waiting for live gameplay validation.
  Added two default-off Advanced enemy options: ordinary-enemy normalization,
  and BSB-at-Cleric boss playtest (other enemy placements unchanged; scaling
  included). Master Randomize Enemies controls both. No new YAML surface.
- Added native embedded event recipe, checked against the existing nine event
  pins. No DarkScript/Ghidra requirement for players. Developer reproduction
  still uses the compiler oracle. Native output's six game binaries match the
  independently compiler-built canary exactly.
- Launcher composes normalization after seed parameter edits, then caches
  verified maps, AI, parameters, boss event and provenance together. Option
  changes produce distinct cache identities. Cache verification requires the
  event/receipt/option and AI/normalization plan hashes to agree. Mode-switch
  tests cover removing the boss event and restoring ordinary parameters.
- Real pipelines: `work/launcher-playtest-boss` and
  `work/launcher-playtest-scaling`, caches `work/launcher-playtest-cache`.
  Scaling: 308 logical swaps / 545 parts, 234 clones, 68 effects, 22 maps,
  14 AI archives, zero missing required goals. Neither was installed live.
- Packaged planner uses bundled original parameter data; boss guide included.
  Client pin updated to e31f1bba560a842083092545a1ab6c579e45f75a, current main;
  intervening changes concern ER DirectInput interception, not BB runtime.
- Binary tests: 37 boss, 79 scaling, 26 AI assertions pass. Full release gate
  `./build.ps1 -Test -Preflight` passes: 1,156 tests / 49 skips, run twice.
  Log `work/boss-canary/release-gate.log`; real-build log
  `work/boss-canary/real-launcher-builds.log`. Focused launcher/report suite:
  158 pass / 4 skips / 10 subtests. Branch CI 34364402394 passed.
- Release https://github.com/4laric/bb-archipelago/releases/tag/v0.1.0-enemizer-playtest.1
  is published. Run 34364420322: package, both smoke checks, Authenticode
  signing/verification and artifact attestations passed. Windows ZIP SHA256:
  `98473829637c1d777a98fab4e57d5543df691cdbf514ca8022c181c1e23869ae`.
  VirusTotal publication is still running at this checkpoint; inspect its result
  separately rather than equating a successful signing job with a clean scan.
  The release is available now; the scan workflow publishes its links automatically.
  Next heartbeat: inspect run 34364420322's scan outcome first and report any
  actionable failure/detections, then resume independent enemizer development.

### Boss verification batch, 2026-09-09 09:23 local heartbeat

- Boss writer receipts now hash all ten retained overlay files, including the
  three map states and both plans. Added `tools/verify_boss_canary.py` to check
  the exact file set, hashes/sizes, path containment and cross-component
  plan/parameter/AI/event provenance. Older receipts require a rebuild.
- Added a build-specific live worksheet with eleven explicitly unrun checks:
  entry, aggression, two phase transitions, UI/camera/music, containment and
  passive deaths, re-entry, save/reload, destination AP completion, persistent
  victory, and separate co-op/NG+ evidence. It does not install anything.
- Real rebuilt output `work/boss-canary-verified-output` passes verification;
  worksheet `work/boss-canary/live-test-worksheet.md`. Receipt SHA256:
  `61176126c3b0c8f3194a48c316a09d8549d66c88ea52995b2353c6bd5c50927b`.
- Focused Python suite: 19 tests plus 3 subtests pass (boss construction,
  census, verification and test-quality guard). Includes mixed/stale receipt,
  altered map, missing/extra files, bad completion and unresolved AI controls.
  Binary suite passes 26 boss, 79 scaling and 26 AI assertions; log
  `work/boss-canary/receipt-tests.log`.
- Next independent work remains wider boss compatibility/adapters, ordinary
  placement death investigation, or experimental scaling launcher integration.
  No live validation, installation, release or GitHub notification in this batch.

### Boss batch, 2026-09-09

- Implemented original encounter census for all 22 AP boss bindings:
  `tools/build_boss_catalog.py`, `research/enemizer/boss_catalog.json`.
  Twelve encounters have one referenced actor, ten have multiple actors/proxies.
  Literal-only analysis records unresolved calls; it does not authorize swaps.
- Implemented `bsb-at-cleric-v1`, a guarded combined map/AI/scaling/event writer
  and reproducible `tools/build_boss_canary.py`. Nine pinned event replacements;
  all other event fingerprints including AP defeat 12411700 preserved.
  Source pins match linked decompilation of original 01.09 binaries.
- Built two real overlays successfully: `work/boss-canary-output` and
  `work/boss-canary-builder-output`. Three maps, one missing AI goal supplied,
  one normalized NPC clone/effect, nine event edits. No live installation.
- DarkScript reports unused parameters as per-file exceptions despite a zero
  process exit code. Disabled limb event parameter names now use `unused_`;
  builder verifies expected files exist and reports captured compiler errors.
- Eleven Python boss tests pass; binary tests include 26 boss merge assertions,
  79 scaling and 26 AI assertions. `./build.ps1 -Test -Preflight` passes:
  1,148 tests, 49 skipped, repeated by preflight; log
  `work/boss-canary/full-gate.log`. All six game binaries from the direct and
  reproducible-builder overlays are byte-identical.
- See `docs/ENEMIZER-BOSS-CANARY.md` for exact behavior and live test protocol.
  Next: continue roster compatibility/encounter adapters or other offline
  enemizer features. Compiler missing-output failure has a regression test. Keep
  default boss protection until runtime evidence supports promotion.

1. Static scaling writer (#186) is implemented. Optional launcher/cache wiring
   and a reproducible construction-canary builder remain possible followups;
   keep both experimental and default-off. Do not promote before #187.
2. AI/scaling bad-enemy report evidence is implemented. Next: deterministic
   playtest case selection for missing-AI donors, scaling, and repeatedly
   dying placements (#321), or the optional launcher/cache scaling wiring.
3. Investigate the unresolved EMEVD callee-resolution boundary before widening
   coverage (#188); keep policy changes experimental pending map-load evidence.
4. **Now prioritized by the user:** build the boss/EMEVD coupling census and
   roster described in #133, then implement supported experimental boss swaps,
   preserving the AP progression flag chain. Runtime behavior requires live
   evidence before promotion; offline implementation may proceed.
5. Assess compiled planner replacement (#318) after correctness work.

Record each finished batch, tests and remaining limitations here. Pause the
heartbeat when only human/live-playtest-dependent work remains.
