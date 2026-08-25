# Native-grant runtime assumptions

Load-bearing design assumptions behind `bb-native-grant-contract.v5.json`. These
are *checkable claims about the emulator and the guest*, not implementation
notes. If a future shadPS4 upgrade changes memory tracking, a grant path breaks
against one of these assumptions instead of being rediscovered as a freeze.

The contract JSON deliberately does **not** carry these — the clients crate
deserializes that file and guards it with `Contract::assert_agrees_with_crate`,
so a written assumption belongs beside the contract, not inside its parsed
structure. See issue #157.

## A1 — External writes to guest inventory pages wound the emulator

**Assumption.** An external `WriteProcessMemory` into shadPS4's *guest* inventory
pages wounds the emulator: the pages are protection-tracked, so an out-of-process
write trips the tracking and freezes (or intermittently corrupts) the guest.
Writes into the **eboot-image** regions — the caves, the state block, and the
descriptor at `eboot+0x50DBxxx` — are safe from an external process.

**Why it is load-bearing.** This is *why* existing-stack grants route through the
cave (PR #145, closing #144) instead of writing the inventory record directly:

- The absent-record path (native insertion) succeeds because the game's *own*
  thread performs the inventory write; the external process only ever touches
  eboot-image cells.
- The direct external write to an existing stack (`_direct_write`) was retired
  for live guests. Two reproductions on 2026-08-24 showed the same shape:
  `find_stack` READ the entry id and quantity fine, `write_quantity` WROTE the
  guest inventory address without error, and a read-back of that *same* address
  microseconds later failed and the guest froze — with the state cell idle and
  the descriptor empty, so nothing armed detonated it. The external write itself
  is what wounded the emulator. An existing stack now arms the cave
  (`bbAutoRequest == 2`) on the game thread, exactly like the absent case.
- All-session evidence for the safe half: the caves/state/descriptor at
  `eboot+0x50DBxxx` were written externally throughout the session with no ill
  effect, because they live inside the eboot image rather than on a
  protection-tracked guest page.

**Observed on.** shadPS4 build in use 2026-08-24 — recorded elsewhere in this
repo as **shadPS4 0.18.0** (see `docs/HANDOFF.md`, `docs/RESEARCH-BASELINE.md`,
and the contract's `target.emulator` = `"shadPS4 0.18.x"`); serial `CUSA03173`,
app version `01.09`. Origin and full evidence: issue #144 (revised diagnosis) and
PR #145.

**How to recheck after a shadPS4 upgrade.** Attempt a *single* external
`WriteProcessMemory` to a live guest inventory record and read it back. If the
read-back succeeds and the guest stays stable across a menu/level transition, the
protection-tracking behavior has changed and the external direct-write path may
be reconsidered. Until such a recheck passes, all inventory writes must be
performed by the guest thread via the cave.
