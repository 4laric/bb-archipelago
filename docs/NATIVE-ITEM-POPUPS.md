# Native item popups (issue #330)

## Goal

A received AP item currently produces no in-game feedback beyond the
client-window toast (docs/TOASTS.md). The goal is for received items to also
produce Bloodborne's own lower-corner pickup popup -- the same non-blocking
notification a vanilla pickup shows -- without any modal dialog and without a
new, unmapped RVA.

## Mechanism

The game presents what it awards. Vanilla pickups reach the player through
`AwardItemLot`; the category-8 event-award bridge (docs/EVENT-WRITER.md,
`tools/patch_category8_awards.py`, `worlds/bloodborne/category8_awards.py`)
already calls the same routine from inside the game's own Restart event, to
hand out runes and blood gems. So the plan is: **received items get a native
popup by being delivered through the event-award lane**, not by adding a new
presentation call. No new RVA is required and no direct call into an unmapped
routine is proposed.

The `ItemGrant` descriptor lane (`tools/bb_native_delivery/`, used today for
goods, weapons and attire) writes the inventory record directly. It never
calls `AwardItemLot` or anything else in the game's acquisition path. **This
is a pre-registered prediction, not an established fact**: nobody has run the
game and watched the corner of the screen after an `ItemGrant` delivery. The
probe below is what turns it into one or the other.

## Rejected alternatives

- **A direct call into an unmapped presentation routine.** Forbidden by
  docs/CONTRIBUTING-LIVE-PROBES.md's "observation before mutation" rule: no
  static ABI writeup, no construct-only stage, no prior xref enumeration
  exists for any such routine. The #214 history in that document is two
  crashes from exactly this shortcut.
- **`DisplayGenericDialog`.** The only vanilla message instruction identified
  in the bundled scripts. It is modal. docs/TOASTS.md is explicit that a modal
  notification is never acceptable, so this instruction is refused outright,
  not merely deprioritized.
- **`item.msgbnd` toast clones (`BBToastWriter`, docs/TOASTS.md).** These
  rename the *physical pickup lot's* FMG text ("Item name (recipient)"). They
  cannot make a *received* item show a popup at all -- the popup has to exist
  first, from a real acquisition call, before a clone can put a name on it.
  They remain the later path (phase 3 below) for naming the popup once the
  event-award lane is confirmed to produce one.

## Pre-registered predictions

Written before any session, per docs/CONTRIBUTING-LIVE-PROBES.md rule 2: for
each hypothesis, what true / false / probe-broken look like, and how false is
told apart from probe-broken.

### Positive control (not a hypothesis; gates the session)

A vanilla pickup, performed on demand, with a known result.

- **True**: observation is `popup`.
- **False**: not applicable -- a vanilla pickup not showing its own popup has
  no plausible game-mechanics explanation.
- **Probe-broken**: observation is anything other than `popup` (`none`,
  `modal`, `deferred`, `unknown`). Distinguishable from "false" because there
  is no "false" case here: any non-`popup` result means the operator's
  reading of the screen, the `mark` timing, or the build is wrong, not that
  Bloodborne sometimes hides its own pickup popup.

### H: `itemgrant_presents_popup`

- **True**: the `ItemGrant` lane's delivery of a Pebble shows a popup.
- **False**: observation is `none` or `deferred` -- consistent with the
  mechanism prediction that this lane bypasses `AwardItemLot` entirely.
- **Probe-broken**: observation is `modal` (a lane producing a blocking
  dialog is a probe/lane defect regardless of what the hypothesis predicted,
  and per the refusal conditions below closes the lane) or `unknown` (the
  operator could not read the screen). Distinguishable from "false" because
  `none`/`deferred` are readable non-events; `modal`/`unknown` are not.

### H: `award_presents_popup`

- **True**: the event-award delivery of the Communion token shows a popup.
- **False**: observation is `none` or `deferred` -- the mechanism prediction
  (this lane calls `AwardItemLot`, so it should present like a vanilla
  pickup) does not hold for this delivery shape.
- **Probe-broken**: the positive control failed this session (see Refusal
  conditions), or the token never resolved (the Restart event's ack flag
  never raised -- check the storage box per the CLI's existing hint before
  treating this as `none`).

### H: `award_nonblocking`

- **True**: the same delivery, made while the inventory menu is held open,
  shows the popup during the menu or after it closes (`deferred`), and input
  never stops responding (`nonblocking: y`).
- **False**: not applicable in the same sense as the control -- a blocking
  result IS the refutation, see below.
- **Probe-broken/refuted**: observation is `modal`, or `nonblocking: n`. Per
  Refusal conditions, this is not "probe broken" but a permanent refusal of
  the lane -- the two are deliberately not separated here because either one
  ends the feature the same way.

### H: `award_persists`

- **True**: after a full shadPS4 restart and reload, the awarded Communion
  rune (from the earlier step) is still present (`persisted: y`).
- **False**: `persisted: n` -- the award did not stick; any popup observed
  earlier was cosmetic and the underlying `AwardItemLot` call did not commit.
- **Probe-broken**: the operator cannot tell (menu is ambiguous, save
  corrupted) -- recorded as `unknown`, not guessed at.

## The probe

```
python -m tools.bb_native_delivery probe-popup --runbook
python -m tools.bb_native_delivery probe-popup --pid 1234 --save-id throwaway-c \
    --arm --yes-throwaway-save
python -m tools.bb_native_delivery probe-popup --summary
```

Implemented in `tools/bb_native_delivery/popup_probe.py`, mirroring
`tools/bb_native_delivery/probe.py`'s engine shape exactly (steps, context,
append-only `.jsonl` report, classifiers, resume against the shared grant
journal) rather than inventing a second one.

Five steps, in order:

0. `control-vanilla-pickup` -- **the positive control**. No delivery. Pick up
   any physical lot. Expected: `popup`. If this fails the session, everything
   after it, is a probe defect (see Refusal conditions).
1. `itemgrant-pebble` -- deliver 1 Pebble through the ordinary `ItemGrant`
   lane (`_probe_deliver`, unchanged). Expected: `none`.
2. `award-rune-token` -- deliver the category-8 token good for Communion
   (rune 102901) through the event-award lane. Expected: `popup`.
3. `award-while-menu-open` -- same delivery on the same save (a second
   Communion is expected to coexist, per issue #330), operator holds the
   inventory menu open. Expected: `deferred`, `nonblocking: y`.
4. `award-after-reload` -- no delivery. Save, fully restart shadPS4, reload.
   Expected: no popup replays on load (`none`) and `persisted: y` for the
   runes from steps 2 and 3.

**The Communion token descriptor is derived statically**, not typed by hand:
`worlds/bloodborne/category8_awards.py`'s first pilot row gives
`token_goods_id = 9800`; `worlds/bloodborne/runtime_bindings.py` binds every
category-8 token through the same category-4 goods formula every other goods
canary uses (`raw = 0xB0000000 | id`, `normalized = 0x40000000 | id`). No live
dump and no `--token-descriptor` flag is required for Communion; that flag
exists only as a sanity check (it refuses on a mismatch) for anyone pointing
the probe at a category-8 row this file does not know about yet.

**`mark` command**: before each step, type `mark <step_id>` in the *client's*
console (`worlds/bloodborne/client.py`'s `BloodborneCommandProcessor`, not
this CLI) at the moment named in the step's setup. It appends one line to
`bb-probe-marks.jsonl` (or `$BB_PROBE_MARKS`) with a UTC clock
(`worlds/bloodborne/probe_marks.py`), satisfying
docs/CONTRIBUTING-LIVE-PROBES.md rule 3 -- an operator's recollection after
the fact is not a label. `probe-popup --summary` merges marks from that file
alongside the recorded steps.

## Promotion after a passing verdict

**Phase 1** -- record the verdict. Update this document's predictions section
with the actual observations, and update RESEARCH-BASELINE.md's vocabulary:
a `witness` (correlated with a labeled action, not attributable to the AP
client, control passed in the same session) is promoted to `validated` only
on a **second independent run** that reproduces it, per the three-word
discipline in docs/CONTRIBUTING-LIVE-PROBES.md.

**Phase 2** -- extend the event-award lane. Once `award_presents_popup` and
`award_nonblocking` are `validated`, extend it from category-8 runes/gems to
progression and useful items of other categories, as issue #330 phases 2-4
describe. This is the mechanical part: more `Category8Award`-shaped rows and
more `Restart` events, the same bridge, no new mechanism.

**Phase 3** -- optional popup naming. Once popups exist for received items,
`BBToastWriter`'s `item.msgbnd` clones (docs/TOASTS.md) can be pointed at the
award-lane token goods to put "(from Player)" text in the native popup,
exactly as that document already specifies for physical pickups.

## Refusal conditions

- **A `modal` observation on any lane permanently closes that lane** for
  native popups. Not a retry condition, not a "try a different trigger"
  condition -- docs/TOASTS.md already establishes that a modal notification
  is never an acceptable fallback, and this applies identically here.
- **A popup that appears only after a menu closes is `deferred` and
  acceptable.** This is the expected true case for `award_nonblocking`, not a
  degraded one.
- **A popup that appears on a load screen, during a cutscene, or at any point
  where the player cannot act on it is a refusal**, on the same non-blocking
  principle -- record it as `modal` if it captures input, `unknown` if it is
  ambiguous, and do not round it up to `popup`.
- **A failing positive control ends the session.** `probe-popup`'s CLI
  detects this itself (the observation for `control-vanilla-pickup` is
  checked immediately after it is recorded) and exits non-zero with "probe
  defect: positive control failed" rather than continuing into steps whose
  result cannot be trusted.
