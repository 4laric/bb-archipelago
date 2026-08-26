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


## A2 — The grant routine's return value names the outcome

**Assumption.** The game's `quantity_delta`/grant routine returns the **new held
count** on a normal add, and **`1`** when the added item overflowed the held cap
and the surplus went to the Hunter's Dream storage box.

**Provenance: `inferred`, from three live data points.** Two of them are oz's
first full clear on the native stack, taken during the goal-release flood rather
than on purpose: `expected_after=5 actual=Some(20) native_result=1` (Pebbles,
held cap 20) and `expected_after=4 actual=Some(10) native_result=1` (Molotovs,
held cap 10). The third is the normal-add case, `native_result=8` (clients#443).
Two overflow observations and one normal one are consistent with the assumption
and with several other readings of the same cell; **sufficient is not necessary.**

**Why it is load-bearing.** It is the only signal the delivery path has for the
difference between "delivered, held" and "delivered, in storage". Under it, the
completion detail can say `delivered to storage (held stack full)` instead of the
generic wording, which is the whole of clients#445 — a progression key silently
placed in storage leaves a player soft-stuck in practice, not because delivery
failed but because nothing said where the item went. It is also why an at-cap
grant ends `failed` in the state machine: the held stack never reaches
`expected_after`, and the tool currently has no way to tell that apart from a
delivery that did not land.

**What would refute it.** Any at-cap add whose result cell is not `1`, or any
normal add whose result cell is not the final held count. Both are step outcomes
the probe classifies explicitly.

**How to check it.** `python -m tools.bb_native_delivery probe-storage` — steps
`a1-normal-add` and `a3-cap-overflow` on one goods id, `b1-vial-normal-add` and
`b2-vial-overflow` on another. See `docs/STORAGE-ROUTING-PROBE.md`. Record the
result here when the session runs; until then this stays `inferred`, and it must
not be written into the contract JSON (see the note at the top of this file and
issue #157 — the clients crate guards that file, and a semantic edit is a
cross-repo step).

**Open beside it.** Three further questions the same probe settles, all currently
**unmeasured**: whether a unique-item insert delivered idle lands held (oz's
Cheat-Engine-era control says yes; nothing has re-run it natively), whether an
overflow makes the *next* add sticky to storage whatever it is, and whether the
post-boss / non-gameplay state routes differently. Each step also records the
insert source lane, so `persistent` vs `in_frame` can be ruled in or out as the
cause rather than assumed innocent.
