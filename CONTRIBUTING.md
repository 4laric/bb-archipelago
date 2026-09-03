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

## Checks

Run the repository gate before opening a pull request:

```powershell
.\build.ps1 -Test -Preflight
```

Use `-Data` only when intentionally regenerating derived research, and inspect
the resulting diff. Generated tables must be reproducible; never hand-edit them
to make a test pass. Use `-Apworld` when the change affects packaging.

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
