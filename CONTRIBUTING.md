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
