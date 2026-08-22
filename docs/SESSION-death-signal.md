# Session runbook: finding the DeathLink send signal

One sitting. The goal is not "watch the player die" — it is **a validated,
reconnect-safe death signal** the client can send DeathLink on. Receiving is
already possible through the validated HP write; sending is the Phase-1-class
find this session is meant to land. This kit is the repo-only prep for issue
#78: the narrowing is done below, so the live part is short and scripted.

Targets CUSA03173 `01.09` under shadPS4, like every session kit in this repo.

## What the corpus already ruled out

Run it, don't trust this paragraph:

```powershell
python tools\death_signal_candidates.py
```

The committed inputs bundle says there is **no event flag to read**.
`CharacterDead(10000)` — the player-death primitive, entity 10000 — appears
exactly three times in the whole decompiled EMEVD corpus, and none of them is
a general "the player died" flag write:

| event | wait requires | flag writes after death | respawn point |
|---|---|---|---|
| 9400 (初回死亡で拠点へ) | death only | none (9402 is set *before* the wait) | 2102962 |
| 9404 (insight ≥ 1 first death) | death + flag 9401 + insight | none | 2102961 |
| 9782 (spider-man quest) | death + carrying Goods 4310, or flag 1431 | 1438 ON, 1439 OFF — quest-gated | none |

The bloodstain side is not script-visible either (`Bloodstain` and friends
have zero occurrences; only the respawn warp is scripted, 22 uses). So the
flag manager that already serves location checks **does not observe death**,
and the send signal must come from a live state read. The tests in
`tests/test_death_signal_candidates.py` pin all of this; if the corpus ever
grows a fourth site, they go red, not stale.

## The candidate classes, fixed in advance

Everything below is `inferred` until this session validates it:

1. **HP at zero.** The most direct signal, and the tooling exists
   (`tools/scan_hp_structure.ps1`, a validated HP write). HP at zero is not by
   itself the signal — it must be distinguished from quit-out revival and from
   loading into a save — but it is the cheapest live poll and the fallback if
   the memory hunt comes back empty.
2. **Death-state SpEffects.** Seven player death transition/state rows in
   `SpEffectParam`: 5904/5905 (仮死亡遷移 / 仮死亡状態維持, the main fake-death
   pair), 5914 (event use), 5915 (cage-only), 560 (revive on death), and the
   5912/5913 dungeon variants (chalice-only — out of scope here, consistent
   with the project's chalice exclusion). A live `CharacterHasSpEffect`-class
   watch on 5904/5905 is the second cheapest probe.
3. **A memory bit or counter** found by this session's diff. This is the
   hunt below.

## What a send signal must look like

DeathLink sending has two fixed points a candidate is judged against:

- **It must not double-send.** On reconnect or reload the client must not
  re-report an old death. A *counter-class* candidate (still set after reload)
  is used as a monotonic cursor — send when the value increases past the last
  sent value. An *edge-class* candidate (cleared by reload) is used as a live
  edge — send on the transition, debounce, and never persist it.
- **It must not fire on a quit-out revival.** Quitting during the death screen
  and reloading revives the player without a death having "happened" for
  DeathLink purposes. The `reload` stage is what tells the two apart.

## The trials, fixed in advance

**Do not substitute targets.** Repeated trials must be comparable.

- **Death trials ×3.** Same backup save, same spot: Central Yharnam, in range
  of a patrol near the Central Yharnam lamp. Stand still, take the hit, die.
  Restore the backup before each trial — dying is repeatable from a backup.
- **Control trial ×1.** Same save. Warp lamp → lamp (Central Yharnam to itself
  via the Hunter's Dream is fine) **without dying**. This is the control pair
  the baseline demands: anything that also moves here is "changed during the
  trial", not "is the death signal", and Analyze subtracts it.

## Before you start

- One backup save, restored before every trial. Disable BBLauncher automatic
  backups for the duration.
- Record the shadPS4 version; `Initialize` demands it.
- Do not pick up items, ring bells, or trigger dialogue inside a trial.
- Never change the snapshot base address or length within a session — the
  comparator works on byte offsets and cannot tell that you moved.

## Run

```powershell
# once
.\tools\death_signal_session.ps1 -Mode Initialize `
    -Serial CUSA03173 -EmulatorVersion "<version>" -TrialCount 3 -ControlCount 1

# per DEATH trial (restore the backup first), six captures in order:
#   idle-a, idle-b, before   - alive; before = in the hazard's range
#   primary                  - YOU DIED on screen
#   secondary                - respawned at the lamp, control regained
#   reload                   - quit to title, reload the save
.\tools\death_signal_session.ps1 -Mode Capture -Session <path> -Kind death `
    -Trial 1 -Stage <stage> -Source <dump>

# the CONTROL trial, same six stages, no death:
#   primary = warp arrival settled, secondary = ten idle seconds later
.\tools\death_signal_session.ps1 -Mode Capture -Session <path> -Kind control `
    -Trial 1 -Stage <stage> -Source <dump>

.\tools\death_signal_session.ps1 -Mode Analyze -Session <path>
```

`tables/Bloodborne-death-signal-snapshot.CT` produces the dumps: F5–F10 in the
stage order above. Which memory region? Start with the event-flag region the
flag hunt already solves (the manager at eboot RVA `0x553B100`, divisor-1000
groups, MSB-first packing — the solved addressing makes any hit there
immediately readable as a flag id), then the HP structure neighborhood from
the HP scan notes if that comes back empty.

## Reading the result

```
Death trials intersected and control-subtracted: N surviving bit transition(s).
  counter-class (held after reload): C - candidate monotonic death records
  edge-class (cleared by reload):    E - candidate transient signals
```

- **N of 0 is a real result, not a failed session.** It means the death signal
  is not a saved bit in this region — fall back to the HP poll and the 5904 /
  5905 SpEffect watch, which need no memory hunt at all.
- C and E are both usable; they imply different client send logic (cursor vs.
  edge + debounce). Neither is "the signal" yet.

## Then attribute

For each surviving candidate byte, arm
`tables/Bloodborne-death-signal-write-breakpoint.CT`, restore the backup, die
once. The table logs the writer's RIP, the full register set, 48 bytes of code
around RIP, and a 16-byte neighborhood around the candidate — the
neighborhood distinguishes a packed flag byte from a small-integer counter,
and the RIP says which system owns the write. A candidate whose writer is the
event-flag setter (signature `88 0C 02`, eboot RVA `0x17D6EFA`) is a flag and
is immediately addressable; anything else needs its own resolver.

## If you only get one thing done

One full death trial with all six stages plus the control trial. That pair
alone answers "is there a death-only bit in the flag region at all", and the
next session starts from the answer instead of repeating the question.

## What this session does not answer

- **Chalice-only deaths.** Deliberately out of scope (the 5912/5913 dungeon
  SpEffect variants are listed but untested), consistent with the project's
  chalice exclusion.
- **Whether any candidate IS the signal.** Every candidate this kit presents
  is `inferred` until a live trial validates it; the kit narrows, it does not
  conclude.
- **The client send logic.** That follows once a signal is validated — cursor
  or edge per the class above — and is deliberately not in this prep.
