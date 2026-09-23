# Contributing to bb-archipelago

This project has two equally useful contributor lanes. You do not need a copy of
Bloodborne, an emulator, or a debugger to work on the Archipelago world, client,
logic model, tests, planners, or most derived research. The committed
`research/bb_inputs.db` makes the inputs used by repository tools available for
reproducible, repo-only work. Tasks that require a game session are labelled
`needs-game`; tasks that do not are labelled `no-game-needed`.

## Before starting

1. **Claim before you branch.** Assign the issue to yourself and check for a
   linked or open pull request. If you stop, leave a short handoff and unassign
   yourself. This prevents two contributors from solving the same problem on
   different branches.
2. **Do not invent game IDs.** Every numeric game ID must trace to a named source:
   a committed param or catalog row, an EMEVD/MSB reference, a runtime probe, or
   a recorded readback. A plausible value is not evidence. Put runtime IDs and
   their provenance in `worlds/bloodborne/runtime_bindings.py`; keep design data
   in `worlds/bloodborne/data.py`.
3. **Own constraints.** Distinguish game facts, measured observations, working
   hypotheses, and project choices. Do not hand a heuristic to another
   contributor as a requirement they are no longer allowed to question. State
   who chose a constraint, why, and what evidence could overturn it.

Create a focused branch named `agent/<description>` (or an equivalently clear
contributor prefix). Keep unrelated fixes in separate pull requests.

## Evidence and source boundaries

Read `docs/RESEARCH-BASELINE.md` before changing runtime claims. Its evidence
vocabulary is part of the project contract:

- `inferred`: derived from static evidence but not observed live;
- `observed`: reproduced in a named runtime experiment;
- `validated`: survives the controls and build coverage stated by the research
  document.

Record the serial, AppVer, source path or symbol, and reproduction method close
to each claim. `CUSA00900` and `CUSA03173` at AppVer `01.09` are distinct targets;
evidence from one does not silently cover the other.

Do not reuse or adapt existing Bloodborne randomizer code, binaries, extracted
datasets, address tables, or patches. Research inputs come from user-owned game
files, original experiments, or separately published evidence with attribution,
as described in the baseline.

## Working without a game dump

List or verify the committed input bundle:

```powershell
python tools/bb_inputs.py --list
python tools/bb_inputs.py --verify
```

Read one input without extracting the bundle:

```powershell
python tools/bb_inputs.py --get params/ItemLotParam.csv
```

Or extract the narrow, committed corpus under the ignored `work/` directory:

```powershell
python tools/bb_inputs.py --extract work/inputs
```

See `docs/INPUTS-BUNDLE.md` before expanding or rebuilding the bundle. Rebuilding
it requires the owner's dump and should happen only when a committed tool needs a
new input.

## Live probes and playtest requests

Anything that asks an operator to run the game, including capture hooks,
runtime probes, and direct native calls, follows
[docs/CONTRIBUTING-LIVE-PROBES.md](docs/CONTRIBUTING-LIVE-PROBES.md). The short
version: a probe must have captured a known, planted event before it is pointed
at an unknown one, every session is pre-registered with a prediction, and
"nothing was captured" is a diagnostic miss unless the bundle proves otherwise.

**Design probes to settle a question and save playtest time.** Before asking
the operator to launch, define the question and an outcome table: every expected
result, including no visible change, partial results and control failure, must
have a distinguishable observation, interpretation and next action. A valid
run should answer the question whichever substantive result occurs. If two
competing explanations still look identical, redesign the probe before spending
operator time. An unexpected or invalid result stops the experiment and returns
to engineering; it is not permission for an endless series of "try this build"
requests.

Minimize the operator's total effort: setup, travel, combat, waiting, restarts,
capture and cleanup. Prefer an immediate, unmistakable canary over a distant
single target when both answer the same question. In the Saw Spear example
reported by the maintainer on 2026-09-23, a probe changed that one pickup and
asked the player to travel to it. For the question "is this item patch active?",
changing every applicable item to an unmistakable canary in a disposable test
overlay would let the next convenient pickup answer it. That is one controlled
change applied broadly, not several independent experiments. Verify coverage
and activation, and provide restoration; a broad canary proves the tested patch
path is active, not that every item path works. Use a specific item only when
its identity or behavior is the question. The request must explain why a cheaper
action cannot give the same answer. See the live-probe contract for the required
outcome table, time budget and stop conditions.

## The client pin

`packaging/client-ref.txt` holds the full commit SHA of
`from-software-archipelago-clients` that releases and the main-branch
playtest bundle build. It is the one place the world/client pair is chosen.
To bump it: put the new SHA in the file in its own pull request, and let the
packaging smoke (the frozen launcher's `--self-check` and the built client's
`--check-contract` against this apworld's widest contract) prove the pair
before it merges. A client-commit dispatch or a manual `client_ref` builds
against another ref without changing what a release ships. Never point the
file at a branch name.

## Cutting a release

`v0.1.0-beta.6` shipped the `beta.5` client because the pin was never bumped and
nothing in the release noticed. Work the list in order; it is short because each
line is a thing that has already gone wrong once.

1. **Main is green.** Not "green except the slow tier" -- the binder and
   packaging jobs too. A tag builds from main; a red main is a red release.
2. **The client pin is current.** `packaging/client-ref.txt` must hold the
   `from-software-archipelago-clients` `main` head, not merely a valid SHA. If
   it is behind, bump it in its own pull request first (see *The client pin*
   above), let it merge, and tag after that. The release workflow now checks
   this for you: its `The client pin is current` step fetches the clients repo's
   `main` and fails the build when the pin is not that head. A manual
   `client_ref`, or the `allow_stale_client` dispatch input, is the deliberate
   way to build an older client on purpose.
3. **`RUNTIME_BUILD` is identical in both repos.** The world's `RUNTIME_BUILD`
   and the client's must be the same string, or the bridge handshake rejects
   every session in the package you just shipped.
4. **Tag.** Push the `v*` tag from the merge commit you checked, or dispatch the
   workflow with that tag. The tag spells the release number:

   - **`vV.R.M.F`** (`v0.1.0.0`) for a player release --
     Version.Release.Modification.Fixpack. The workflow publishes it as a
     normal, latest GitHub release, not a prerelease. `V.R.M` is the
     seed-compatibility line and must equal the world's `world_version`, so
     `v0.1.0.F` is the only four-part form a `0.1.0` apworld can tag; `F` is
     the fixpack, and any two clients sharing `V.R.M` are drop-in swaps on the
     same seed.
   - **`vV.R.M-beta.N`** (`v0.1.0-beta.9`) for a playtest build. These stay
     prereleases. `-signing-canary.N` behaves the same way.

   Tag the paired client in `from-software-archipelago-clients` as
   **`bb-V.R.M.F`** (`bb-0.1.0.0`) on the commit in `packaging/client-ref.txt`,
   so a player can read from the two numbers alone whether an update is a
   binary swap or a paired upgrade. The clients repo's `AGENTS.md` owns the
   full V.R.M.F policy.
5. **Watch the run.** Do not announce the prerelease until the workflow has
   finished and the attached zip's manifest names the client SHA you expect.
   For a bounded pre-publication test, dispatch the workflow with `draft`
   enabled. The resulting release and its downloads are visible only while
   signed in to GitHub with write access to this repository. Draft builds skip
   public provenance attestation and VirusTotal upload; publish only after the
   package has passed the intended tests.
6. **Never move a published tag.** If a tag shipped something wrong, fix
   forward: land the fix and cut the next beta. Re-pointing a tag people have
   already downloaded makes the build unreproducible and the report unreadable.

## Checks

Run the repository gate before opening a pull request:

```powershell
.\build.ps1 -Test -Preflight
```

Use `-Data` only when intentionally regenerating derived research, and inspect
the resulting diff. Generated tables must be reproducible; never hand-edit them
to make a test pass. Use `-Apworld` when the change affects packaging.

The slow suppression binder job normally runs only on main and on manual or
client dispatches, so most pull requests get a fast verdict. It also runs on a
pull request that touches anything the binder build reads -- the plan pin in
`worlds/bloodborne/__init__.py`, `tools/plan_vanilla_suppression.py`,
`tools/check_suppression_plan_pin.py`, `tools/build_vanilla_suppression.ps1`,
`tools/bb_inputs.py`, `tools/bb_suppression_writer/`, `tools/bb_objact_miner/`,
`research/bb_inputs.db`, `research/joined/objact_params.tsv`,
`tests/fixtures/shop-seed-request.json`, `tests/fixtures/enemy-drop-request.json`,
`tests/fixtures/enemy-drop-request-v2.json`,
`worlds/bloodborne/enemy_drop_catalog.json`, or `.github/workflows/tests.yaml`. The
`binder inputs touched` job decides this from a plain `git diff` against the
pull request's base. Moving `SUPPRESSION_PLAN_SHA256` without repinning
`EXPECTED_OUTPUT_SHA256` left main red from #391 to #397; that pair is now
checked before the merge, not after. If you add a new input to the binder
build, add its path to that job's list in the same pull request.

Tests that assert an empty result or universal property need a separate witness
that their input population was non-empty and the intended records were
examined. A green test that collected nothing is not evidence.

## Pull requests

Keep the pull request description concrete:

- link the issue and describe the user or research impact;
- separate measured facts from design decisions;
- name the source of every new runtime ID or address;
- list the commands run and any environment-dependent skips;
- call out generated artifacts and confirm whether the game was tested;
- preserve stable network IDs in `worlds/bloodborne/ids.tsv`.

Every player-visible change must update `CHANGELOG.md` in the same commit. Write
the entry for a player: what changed in their build and why it matters. Keep
unfinished or unvalidated behavior under `Unreleased`, and do not defer release
notes until tag time.

Draft pull requests are welcome for research with a clear evidence boundary.
Do not describe static analysis as playtested, or a single-build observation as
portable.

## Postmortem: launcher UI/UX pass (September 2026)

A multi-session redesign of `bb_launcher/` (theme, wizard flow, session details
drawer, py-launcher discovery) shipped real improvements, but the pass ran far
longer than it should have because visual work and functional work were not
kept separate enough:

- Polish changes (palette, layout, collapsible drawers) and behavior changes
  (Python interpreter discovery, seed/slot validation) landed in the same
  branches and the same review passes. When a behavior change broke a real
  launch, the polish work around it made the diff harder to bisect and the
  regression harder to isolate.
- Several sessions reported "the UI looks done" while the underlying launch
  path was still broken -- a packaged build a user actually downloaded could
  not generate or host a seed. Visual completeness was mistaken for
  functional completeness more than once. Treat "looks good" and "works" as
  two separate acceptance criteria that both must be checked against a real
  build, not just against `pytest`; see `docs/DESIGN.md`-equivalent guidance
  in this file about evidence boundaries -- a passing unit test for UI code
  is not evidence the packaged app launches a seed.
- For the record: "looks done" was also not the same as "looks good."
  Getting the launch path working became the overriding priority partway
  through the pass, and rightly so, but that did not retroactively make the
  visual/UX state of the launcher acceptable. After the pass, the launcher
  was still genuinely ugly and a bad user experience. Fixing the launch
  blocker does not close out the polish work it interrupted; the polish work
  is still owed, not satisfied by having shipped something that runs.
- The fix that actually unblocked play (`py`-launcher interpreter discovery,
  see `bb_launcher/local_session.py`) was implemented and sitting uncommitted
  for a stretch while cosmetic iteration continued elsewhere. When a change
  is release-blocking, land and ship it before returning to unrelated polish,
  even if the polish was requested first.
- A release tag (`v0.1.0.5`) had to be re-pointed at a later commit to pick up
  a launch-blocking fix after the fact. The tag was still an unpublished
  draft at the time, so this did not violate "never move a published tag"
  above, but it is a symptom of the same problem: the fix should have been on
  the branch before the tag was first cut.

Takeaway for future launcher work: land and verify the functional fix first
(against a real packaged build, not just tests), *then* do the cosmetic pass
on top of a working baseline. Do not let "make it pretty" and "make it work"
share a commit, a branch, or a review pass when the launch path is at risk.

## Item: the launcher's blocking-check gauntlet needs to shrink

Recent launcher work (attributed to the Codex agent lane rather than this
pass) added several launch-time guard checks in `bb_launcher/doctor.py` and
`bb_launcher/workflow.py` -- seed/slot mismatch checks, the suppression
binder pin check, save-file/profile checks -- each of which can independently
refuse to let a user proceed. Individually each check has a rationale, but
together they turned "click play" into a gauntlet, and every guard is one
more thing that can misfire and block a real launch for a reason unrelated to
whether the game can actually run.

Two concrete problems this caused during the UI/UX pass:

- These checks fire *before* the thing the user actually wants (host or join
  a seed), so a false positive or an overly strict check looks identical to a
  real launch failure from the user's side. Several hours of the "why can't I
  launch" debugging this pass were spent proving a guard was wrong, not that
  the launch path was broken.
- Stacking checks compounds failure surface without compounding value: each
  new check is a new way to block a launch, but the checks do not compose --
  passing four checks and failing one still means no seed. Every guard added
  is a net subtraction from launch reliability unless it is checking
  something that would otherwise corrupt a save or desync a multiworld.

Going forward, a new launch-time guard needs to justify itself against that
cost, not just against the failure mode it prevents:

- Prefer a warning the user can see and dismiss (or an `--allow-*` /
  `allow_*` override, as already exists for seed mismatch in
  `bb_launcher/ui.py`) over a hard refusal, unless the failure mode is
  unrecoverable (for example, corrupting a save file in place).
  Recoverable/informational mismatches should not be launch-blocking by
  default.
- A guard should say precisely what it checked and what it found, not just
  that it failed -- vague guard errors are what obscured the actual
  py-launcher interpreter bug for multiple sessions in this pass.
  Investigate whether a check is masking a different, fixable problem before
  adding another layer that suppresses or works around its symptom.
- When in doubt, remove a check rather than add one. If a guard has not
  caught a real problem in practice, or exists to police a state that the
  workflow already can't reach, delete it instead of tuning it.
