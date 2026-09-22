# Boss shuffle live acceptance preparation

This is a preregistration template, not a completed playtest or a request to
activate an overlay. No runtime result is recorded here. It follows
[CONTRIBUTING-LIVE-PROBES.md](CONTRIBUTING-LIVE-PROBES.md). Finish the session
header and instrument control before asking for operator time.

## Session identity and evidence

Record the source commit, game serial and AppVer, emulator/client versions and
hashes, NG cycle, backed-up throwaway save, seed, exact arena-to-donor mapping,
and active overlay receipt SHA256. Verify every receipt file immediately before
activation. Keep captures outside the overlay. Offline native receipts prove
file consistency; they do not prove that the selected overlay was loaded.

Record the actual client command used for labels and its output file. The
repository bridge client implements `/mark <label>` and `BB_PROBE_MARKS`; do
not assume a different packaged client implements the same command. Verify
the chosen client in step 0. Capture the client/server check journal, event-flag
readbacks when available, continuous game video, and the labels on one time
base. Archive the session header, labels and evidence together. Video alone
cannot establish absence of duplicate network checks.

Check existing playtest bundles linked from issue #133 before each request and
name the bundles inspected. Current native build receipts contain no live
entry, combat, phase or AP-check evidence; they cannot answer those questions.
Do not claim there are no applicable captures without checking the issue.

## Step 0: instrument and installation control

Allow ten minutes and at most one restart, on the throwaway character. Before
testing a shuffled boss, capture a labeled, known vanilla location check with
the same client/capture setup. Select an unchecked location from the exact
seed's location table and write its expected AP ID and game flag in the header.
Do not use the client's manual-check command as evidence of game detection.

Wait five seconds, label `control.before`, perform the known action, label
`control.after`, then wait five seconds. Pass requires both labels, the visible
action, its expected game result and one correctly identified network check.
Record the control evidence paths before proceeding. Also verify the loaded
overlay through the game's visible donor at the selected destination and the
activation receipt; a matching on-disk hash alone is insufficient.

Missing labels, unreadable flags, a failed install, absent expected check, or
unbounded capture gaps mean **probe defect**. Stop before the boss experiment.
Do not reinterpret missing capture as a negative boss result. If sequence/loss
information is unavailable, the session cannot support an absence claim for
network events; report that limitation explicitly.

## Registered encounter prediction

Hypothesis: this exact donor fights through all of its implemented phases in
the selected destination, and defeat advances only the destination's AP and
game progression once, including after reload.

True: labeled entry and phase observations match the contract, death/re-entry
works, the destination completion/reward/exit succeeds, the expected AP ID is
reported once, and the donor's original progression stays unchanged.

False: with the control still passing, the labeled action produces a concrete
contradiction: absent or inert boss, stuck phase, passive death, inaccessible
arena, wrong flag/check, duplicate reward, failed exit, or respawn after victory.

Probe defect: missing or inconsistent session identity, labels, control,
installation evidence or relevant capture coverage prevents deciding between
those outcomes. An unexpected result is unresolved until the instrumentation
can distinguish it. A freeze/crash is a failed run; preserve logs and the last
label rather than repeating without a new finding.

## Labeled operator script

Budget 30 minutes, one deliberate death and at most two reloads per encounter;
extend the estimate before requesting a difficult fight. Wait five quiet
seconds before and after each label/action where gameplay permits. Mark the
phase boundaries during combat as they happen; do not reconstruct labels from
memory afterward.

1. `arena.before`: record destination and donor progression flags/checks, then
   enter through the original destination conditions and fog.
2. `arena.entered`: record visible actors, bar label, camera, music and the first
   attack. Observe arena containment and absence of an immediate passive win.
3. `phase.<name>`: record each contract-specific threshold, transition, helper
   spawn/respawn, damage behavior and resumed combat. Use the source-backed
   thresholds from the selected adapter, not a generic boss percentage.
4. `retry.death` and `retry.entered`: die deliberately, re-enter and verify a
   playable fight with appropriate phase/helper initialization.
5. `reload.undefeated`: save/reload before victory; verify no completion/check
   was awarded and the fight can still finish. Record whether the game's save
   policy resets the fight instead of assuming mid-phase persistence.
6. `victory`: defeat the donor. Record destination flag, reward, lamp/exit and
   expected AP check; re-read donor progression and unrelated shared-map boss
   flags. A health bar disappearing alone is not completion evidence.
7. `reload.completed`: reload after victory. Verify the boss remains defeated,
   the camera is released, the exit works, and no reward/check is repeated.
8. `session.end`: save captures and classify true, false or probe defect with
   evidence paths. Do not promote an entire donor from one successful placement.

Run co-op and NG+ as separately identified sessions after the solo baseline;
neither is implied by solo success.

## Coverage required for the full feature

Maintain one result row per selected arena/donor/build combination. For all
22 encounters, cover destination progression and donor combat behavior, then
exercise both complete seed assignments used by the release build matrix.
Increase this matrix when new compatibility edges create new behavior; two
seeds are not proof of every possible placement.

Include explicit witnesses for single-actor phases, transformations with two
bodies, simultaneous enemies, shared-health proxies, generators/respawns,
projectile owners, special entry/progression, and shared-map composition.
Examples already needing distinct sessions include Logarius's sword and c9010
owner, Ludwig's two-body handoff, Orphan's support and post-fight shadow, and
the fixed final-boss reciprocal pair. Wet Nurse's opaque `2600803` reference
remains an additional runtime question; static absence of a placement does
not resolve its engine semantics.

The decision after each session is whether to retain the tested compatibility
edge, repair a specific controller/placement, or invalidate the instrument.
Keep the PR experimental until the complete roster and required live matrix
have evidence. Record failures and untested cases as such.
