# Session runbook: solving the flag addressing

One sitting. The goal is not "find a flag" — it is **solve the mapping from flag
id to memory address**, which closes #15 and turns every one of the 651 catalogued
acquisition flags into a readable check at once.

## Why this is a solve and not a search

We already know the flag id each pickup sets, from the `ItemLotParam` join. What
we do not know is where flag ids live in memory. So each pickup is a **known
point on an unknown line**, and two widely-separated points over-determine it.

`tools/solve_flag_addressing.py` does the arithmetic and, more importantly,
refuses when the points do not fit. Elden Ring's mapping is
`id = byte_offset * 8 + (7 - bit) + 50000`; Bloodborne's constant and bit order
are unknown, so both bit orders are tried and only an exact fit is reported.

⭐ **A fit is not the evidence. The prediction is.** Two pickups produce a
mapping; the third pickup is where it either holds or dies.

## The three targets, fixed in advance

Chosen from `research/catalog/fixed_location_catalog.tsv` for being single-lot,
single-flag, in the first playable area, and unmistakable when taken. **Do not
substitute** — the whole method depends on repeated trials being comparable, and
"a corpse near the lamp" is not a target.

| # | flag id | lot | item | coordinates | role |
|---|---|---|---|---|---|
| 1 | **52410100** | 2410100 | Saw Spear | `-126.42, -67.97, -103.75` | solve |
| 2 | **50002200** | 42000 | White Messenger Ribbon | `-178.66, -46.45, -63.04` | solve |
| 3 | **52410140** | 2410140 | Madman's Knowledge | `-210.73, -54.32, 184.02` | **predict** |

All three are Central Yharnam (`m24_01_00_00`, with the `_01`/`_11` map variants
being the same logical placement).

Targets 1 and 2 are chosen to have **widely separated ids with different
prefixes** — `5241xxxx` against `5000xxxx`. If the mapping is linear across the
whole flag space, those two pin it. If it is not linear, two points from the same
prefix would have hidden that and target 3 would have failed mysteriously later.

Target 3 is deliberately **not** used to fit. Take it last, and only after the
solver has printed a predicted byte and bit for it.

## Before you start

- Restore the same pre-pickup save for every trial. One save, restored three
  times, not three saves.
- Disable BBLauncher automatic backups for the duration.
- Record the shadPS4 version; `Initialize` will demand it.
- Do not activate a lamp, open a shortcut, or trigger dialogue in the same trial.
  The comparator removes anything that also moved in the idle pair, but a bundled
  action puts real flags in the noise as well.

## Run

```powershell
# once per target
.\tools\event_flag_session.ps1 -Mode Initialize `
    -LocationName "Central Yharnam - Saw Spear" `
    -Serial CUSA03173 -EmulatorVersion "<version>" -TrialCount 3

# per trial: five captures, in this order
.\tools\event_flag_session.ps1 -Mode Capture -Session <path> -Trial 1 -Stage idle-a  -Source <dump>
.\tools\event_flag_session.ps1 -Mode Capture -Session <path> -Trial 1 -Stage idle-b  -Source <dump>
.\tools\event_flag_session.ps1 -Mode Capture -Session <path> -Trial 1 -Stage before  -Source <dump>
#   take the pickup, let the banner clear, do not walk into anything else
.\tools\event_flag_session.ps1 -Mode Capture -Session <path> -Trial 1 -Stage after   -Source <dump>
#   quit to title, reload the save
.\tools\event_flag_session.ps1 -Mode Capture -Session <path> -Trial 1 -Stage reload  -Source <dump>

.\tools\event_flag_session.ps1 -Mode Analyze -Session <path>
```

`Bloodborne-event-flag-snapshot.CT` produces the dumps. Never change the base
address or the length within a session — the comparator works on byte offsets,
so a moved base makes every trial incomparable and it cannot tell.

## Reading the result

`Analyze` prints two numbers that matter:

```
Reload filter: N of M survived 3 reload capture(s).
```

- **M** is how many bit transitions were repeatable across all three trials.
- **N** is how many of those survived a reload. Only these are candidate flags.

If it says *"No reload.bin captured, so persistence was NOT tested"*, the run is
incomplete — that filter is requirement 4 and it is what separates a saved flag
from a session artefact.

Expected shape: M in the tens is normal, N should be small. **N of 0 means the
region does not hold saved flags** — that is a real result, not a failed session,
and the next move is a different memory region rather than more trials.

## Then solve

```powershell
python tools\solve_flag_addressing.py `
    --observation 52410100=<byte>:<bit> `
    --observation 50002200=<byte>:<bit> `
    --predict 52410140 `
    --intersection <session>\intersection.csv
```

Three outcomes:

- **SOLVED, and target 3's predicted position is in its intersection** — #15 is
  answered. Every catalogued flag is now addressable.
- **SOLVED, prediction absent** — the fit was coincidence. Two points always fit
  *something*; this is exactly why target 3 exists.
- **No linear mapping fits** — the flags are not contiguously packed, or a
  capture is wrong. Not a dead end: it means the next step is the write
  breakpoint (`Bloodborne-event-flag-write-breakpoint.CT`) to find the accessor
  directly rather than inferring it.

## If you only get one thing done

Take target 1 with all five stages, three trials. A single fully-captured target
with a reload filter is worth more than three half-captured ones, because the
next session can start from a known-good byte offset instead of repeating this.

## What this session does not answer

**Whether the award path still sets the acquisition flag when the award is a
placeholder.** That is the assumption the whole of #14 rests on, and it needs
suppressed params installed, which needs the CSV repacked into
`gameparam.parambnd` first. It cannot ride along here.

Worth knowing it is one observation once you can repack: take a suppressed
pickup, and check the same flag bit moves.
