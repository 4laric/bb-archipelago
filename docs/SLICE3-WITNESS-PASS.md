# Slice-3 witness pass: what the corpus settles, and what still needs the game

Issue #158. Slice 3 shipped Cathedral Ward, Old Yharnam and the Blood-starved
Beast goal with **no live witness in either new region**. This is the static
half of that pass: every slice-3 detection flag traced to the exact instruction
or param row behind it, so that the session the owner still has to run is as
short as it can be and knows what it is looking for.

Nothing here is a runtime observation. Per `CONTRIBUTING.md` every row's
evidence label is `inferred`. The audit's `corpus_status` column says something
narrower and checkable: whether the static claim is complete from named sources
(`corpus_complete`) or has a hole in it (`corpus_gap:<reason>`).

Reproduce it:

```powershell
python tools/audit_slice3_witnesses.py --check
```

Output: `research/validation/slice3_witness_audit.tsv` (121 rows) and
`research/validation/slice3_witness_summary.json`. Held by
`tests/test_slice3_witnesses.py`.

## Verdict

| | rows | status |
|---|---|---|
| Slice-3 pickups (Cathedral Ward 61, Old Yharnam 54) | 115 | `corpus_complete` |
| Radiant Sword Hunter Badge (`52400480`) | 1 | `corpus_complete` |
| Boss / interaction flags, **including both slice-1 controls** | 5 | `corpus_gap: implicit_write` |

**Live observation required: 0 of 121.** The one gap is uniform, it is the same
gap slice 1 has shipped with since the first vertical slice, and it is not the
kind a bigger corpus can close.

## The one gap: nothing in the corpus writes a boss flag

`12301800` (Blood-starved Beast), `12401800` (Vicar Amelia), `12401803` (the
Grand Cathedral altar), and the slice-1 controls `12411700` and `12411800` have
**no `SetEventFlag` anywhere in the 27 committed event archives** — 50,934 lines
scanned; the same scan does find `SetEventFlag(12401802, ON)` in
`m24_00_00_00.emevd.dcx.js`, so it is not looking through a hole. The write is
the engine's own rule that an event reaching `End` turns on the event flag with
its ID. That rule is not an instruction. It cannot be cited, only observed.

What the corpus *does* corroborate, and does not refute:

- **Each event tests its own ID as a persistent flag.** `$Event(12301800)` opens
  `if (ThisEvent()) { … EndEvent(); }` (`m23_00_00_00.emevd.dcx.js:497`), the
  already-defeated branch that despawns the boss and its fog. An event ID that
  is only an event ID has nothing to test.
- **The ID is read as boss state by other maps.** `common.emevd.dcx.js:208`
  branches on `EventFlag(12301800)`, `:216` on `EventFlag(12401800)`;
  `m21_00_00_00.emevd.dcx.js:882` gates a Hunter's Dream event on
  `EventFlag(12301800)`. `m24_01_00_00.emevd.dcx.js:1048` (event `12411899`) sets flag `2410` once
  both `12411800` and `12411700` are on.
- **The corpus sets an ID in this range directly, in the same map.**
  `$Event(12401804)` ends with `SetEventFlag(12401802, ON)`
  (`m24_00_00_00.emevd.dcx.js:4406`) — the guest-side handler forcing the
  boss-room-entry event's own ID on. Event IDs in this family *are* flags.
- **The boss identities are param-confirmed, not string-guessed.**
  `$Event(12301800)` calls `HandleBossDefeat(2300800)`; MSB places `2300800` in
  `m23_00_00_00` with `NpcParam 209000` = 血に渇いた獣　廃墟 (Blood-starved
  Beast). `$Event(12401800)` calls `HandleBossDefeat(2400800)`; MSB places it in
  `m24_00_00_00` with `NpcParam 502000` = 聖女ビースト　聖堂街A (Vicar Amelia).

So the flag *identity* is corpus-complete. The flag *write* is not, and the
distinction is the whole reason this document exists.

## Refuted, corrected, and newly recorded

- **Two binding citations pointed at readers, not sources.**
  `boss_cleric_beast` cited `m24_01_00_00.emevd.dcx.js:1047`, which is a
  `WaitFor(EventFlag(12411700))` inside event `12411899` — a *reader* of the
  flag. The definition is at `:1052`. `boss_father_gascoigne` cited
  `:1394-1417`, its host-only award block, not the event. Both are corrected to
  the event bodies (`1052-1094`, `1362-1412`), and
  `SourceCitationTests.test_every_scripted_binding_cites_its_own_event_definition`
  now checks all 15 scripted bindings against the corpus so it cannot recur.
- **`12401803` can be held without the interaction, in co-op.**
  `m24_00_00_00.emevd.dcx.js:4390` is `EndIf(HasMultiplayerState(Client))`,
  before the `ActionButtonInArea(2400010, 2401801)` wait. A guest reaches `End`
  — and therefore, under the engine rule above, the flag — on Amelia's defeat
  plus map load, never touching the altar. Solo play is unaffected. Recorded in
  the binding; item 6 of the checklist below is the cheap way to settle it.
- **No slice-3 flag can be cleared.** 279 `BatchSetEventFlags(..., OFF)` ranges
  were resolved, including the 27 whose bounds are event parameters (resolved
  through their `$InitializeEvent` arguments rather than skipped). None covers
  any of the 121 audited flags. The nearest is
  `BatchSetEventFlags(1320, 1325, OFF)` in `m23_00_00_00` — the same map, four
  orders of magnitude away.
- **Five slice-3 flags sit on more than one ItemLotParam row and are still one
  check each.** `52400120`, `52400290`, `52420540`, `52300400` are attire
  continuation rows in the Hunter Set shape; `52410580` is shared by lot
  `2400760` (our Cathedral Ward chest) and lot `2410580`, which carries a
  `m24_01` prefix and looks like a Central Yharnam collision. It is not one:
  `2410580` appears in **no** MSB treasure placement, so exactly one placed lot
  writes each flag. This is the check that would have caught a real collapse,
  and it did not fire.
- **Two slice-3 pickup flags are read by the corpus, read-only.**
  `m21_00_00_00.emevd.dcx.js:1269,1272` mirror `52420640` and `52420690` onto
  bookkeeping flags `6310`/`6311`. Reads, not writes; monotonicity is untouched.
  Note that both flags carry an `m24_02` prefix while their lots are `2400640`
  and `2400690` — the prefix is not a map, and the pairing is what
  `ItemLotParam.getItemFlagId` actually says.

## Owner checklist: the live pass

Needs the game (`needs-game`), one session, a clean pre-Amelia save. Same shape
as the suppression canary in `VANILLA-SUPPRESSION.md`; record results in
`docs/PLAYTESTING.md` with serial and AppVer, and only then may `12301800` and
`12401800` be relabelled `observed`.

1. Take the two quiescent control snapshots first, per
   `EVENT-FLAG-RESEARCH.md`. Without a control pair the after-image is not a
   measurement.
2. Cathedral Ward pickup canary: collect one `m24_00` chest — `2400760`
   (flag `52410580`) is the useful one, since it is the shared-flag row — and
   confirm the flag reader sees the flag turn on, survives a reload, and that
   no *other* seeded check reports at the same moment.
3. Old Yharnam pickup canary: repeat with one `m23_00` corpse. The two regions
   are separate map archives; one region's canary is not the other's.
4. Kill Vicar Amelia. Confirm `12401800` reads true **after** the death banner
   and the three-second `HandleBossDefeat` delay, and still true after a full
   restart and save reload. This is the first observation of any Cathedral Ward
   boss flag.
5. Kill the Blood-starved Beast. Confirm `12301800` the same way. This is the
   slice goal: if it does not fire, the seed cannot be completed.
6. Only if co-op is in scope: as a **guest**, load into Cathedral Ward after the
   host has beaten Amelia and check whether `12401803` is already on without
   anyone using the altar. A yes makes the altar check unsound in co-op and is
   an issue, not a note.
7. Confirm none of steps 2–5 turned on a flag that a *later* step was supposed
   to turn on. A flag that is already true when the player arrives is the
   failure mode this whole pass is buying against.

Steps 4 and 5 are the two the issue asks for. Steps 2, 3 and 7 cost minutes on
top and are what turn "the goal fired once" into a region that can be trusted.
