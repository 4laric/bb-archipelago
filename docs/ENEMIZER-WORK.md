# Enemizer implementation checkpoint

User authorization (2026-09-09): continue working through remaining enemizer
features while the user is AFK. Heartbeat `continue-bloodborne-enemizer-implementation`
continues this task every 30 minutes. Keep later changes local and reviewable;
the only authorized published release so far is `v0.1.0-enemizer-ai.1`.

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

1. Static scaling writer (#186) is implemented. Optional launcher/cache wiring
   and a reproducible construction-canary builder remain possible followups;
   keep both experimental and default-off. Do not promote before #187.
2. AI/scaling bad-enemy report evidence is implemented. Next: deterministic
   playtest case selection for missing-AI donors, scaling, and repeatedly
   dying placements (#321), or the optional launcher/cache scaling wiring.
3. Investigate the unresolved EMEVD callee-resolution boundary before widening
   coverage (#188); keep policy changes experimental pending map-load evidence.
4. Build the offline boss/EMEVD coupling census described in #133, preserving
   the AP progression flag chain. Boss swaps themselves require live evidence.
5. Assess compiled planner replacement (#318) after correctness work.

Record each finished batch, tests and remaining limitations here. Pause the
heartbeat when only human/live-playtest-dependent work remains.
