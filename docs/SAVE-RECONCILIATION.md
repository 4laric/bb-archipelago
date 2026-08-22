# Save-restore and character-slot reconciliation (#77)

Status: **design, not implemented.** This document defines what the receive
ledger must do about save restores and character switches before any of it is
built. It depends on #56 (which supplies the live identity signal) and cites
the client code as of `from-software-archipelago-clients` `main`; section 1 is
verified code fact, sections 2 onward are proposal.

## 1. What the receipts record today

Two receipt implementations exist, and they are not equivalent.

**Native client (`crates/bb-archipelago`).** `ReceiveLedger.slots` is keyed by
`seed_name \u001f slot_name`. Each `SlotLedger` carries:

- `bound_save_identity` — bound durably on the first validated runtime
  context, before any game mutation (`ClientLoop::require_runtime_context`).
  A later context with a different identity is **refused**; a mismatched
  `expected_save_identity` is **refused**; no context at all means **disarmed**.
- `highest_processed_index`, `acknowledged`, and a durable `pending` plan with
  `grant_complete` / `equip_complete` sub-states. Acknowledgement is strictly
  in AP index order and an acknowledged item is never re-executed
  (`mock_loop_never_regrants_an_acknowledged_item`).
- A published-but-unexecuted grant command is **withdrawn** when the validated
  context disappears — save switch, load transition, or process restart
  (`poll_items`' withdrawal path, `reconcile_pending_command`, clients#296).

**Python fallback client (`worlds/bloodborne/client.py`).** The receipt is
`ap-client-state.json` = `{slot_key: "seed:slot", delivered: N}`. A bare
counter: no identity binding, no pending plan, no withdrawal. It still drives
automatic delivery through `bridge_loop`, so it shares every hazard below
with none of the guards.

## 2. Failure shapes

| # | Shape | Detected today | Outcome today | Gap |
| --- | --- | --- | --- | --- |
| A | Character/save **switch** (different identity) | `bound_save_identity` / `expected_save_identity` refusal — once #56 supplies a real identity | refused, pending plan held, in-flight command withdrawn | structurally complete; only the identity *source* is missing (#56) |
| B | Save **restore to an earlier state** (same identity) | **nothing** | ledger still says delivered; the restored inventory lacks the items; they are never re-granted | **the gap this issue exists for** — permanent silent item loss |
| C | **Ledger loss** (receipt deleted/corrupt, save intact) | nothing | every received item re-executes → duplicate goods and equipment | duplicates, the mirror image of B |
| D | New character created in the same file slot | identity change (with #56) | refused | covered by A |
| E | Process death mid-grant | durable pending plan + startup reconcile | replay to fixed point | **done** (clients#296) |
| F | Restore **and** switch together | identity refusal fires first | refused | covered by A, provided restore detection survives the refused path (§5) |

## 3. Invariants

- **I1.** No acknowledged delivery is ever re-executed against a state the
  ledger cannot vouch for.
- **I2.** No pending delivery is dropped silently; held is a visible state.
- **I3.** Ambiguity resolves to *pending + operator-visible*, never to a
  guessed grant.
- **I4.** Every restore/switch shape has exactly one defined outcome:
  `resume`, `hold`, `refuse`, or `reconcile`.

## 4. The core ambiguity: inventory diffing cannot detect a restore

The tempting detection — "acknowledged item is missing from inventory" — is
unsound, because three different truths produce the same observation:

- the player **consumed** the goods (Bullets get shot; that is what they are
  for),
- the player **deposited** the item in the storage box,
- the save was **restored** to before the delivery.

Re-delivering on inventory absence alone would duplicate legitimately consumed
items (violates I1). Never detecting restores loses items (shape B). So
detection must rest on a **monotonic marker that a restore regresses**, with
inventory state as corroboration at most. This is the load-bearing design
decision of this document: *restore detection is a property of a save-side
clock, not of inventory contents.*

## 5. Proposed scheme: a save-resident receive watermark

The grant harness already writes to the save on every delivery. Extend the
acknowledgement step so that, after each successful grant, the client records
the AP receive cursor **into the save itself** (the watermark W), alongside
the ledger's own `highest_processed_index` H.

On every connect/bind, compare:

| Observation | Meaning | Outcome |
| --- | --- | --- |
| W == H | fixed point | `resume` |
| W < H | the save is earlier than the ledger: a restore happened (shape B) | `reconcile`: re-issue indexes W+1..H in order, under the normal per-item pending plan, then continue |
| W > H | the ledger is earlier than the save: ledger loss/restore (shape C) | adopt W as the cursor, **no re-grant** (I1); log loudly |
| identity mismatch | shape A/D/F | `refuse`, exactly as today; no watermark comparison is trusted across identities |
| watermark unreadable, identity valid | unknown | `hold`: no grants, no checks, operator-visible (I3) |

Why re-issuing W+1..H is safe under a *proven* regression: a restore erases
everything after the restore point in game terms, including any post-restore
consumption, so re-delivering to ledger state cannot duplicate. Duplicates
only arise from *misdetecting* a restore — which is why §4 forbids
detection by inventory absence, and why the watermark comparison must be
exact, not heuristic.

**MVP alternative.** Until the watermark write is validated, the same
semantics can be driven by operator attestation, mirroring
`--assume-correct-save`'s posture: an explicit `restored` client command that
asserts "I restored the save to before index K", rewinds the durable cursor
to K, and replays. Manual, honest about its evidence, and it exercises the
exact re-delivery path the watermark will later trigger automatically.

## 6. What this requires from #56's discovery

Two deliverables instead of one:

1. **Save identity** (already scoped): stable per save+character, changes on
   slot switch or different save, survives process restart.
2. **A writable, game-inert scratch field** to hold the watermark (new):
   survives save/load, is never rewritten by game systems, and has a
   write/readback canary of the same standard the grant descriptors are held
   to. #70 is the standing lesson that a nominal write can produce garbage;
   the watermark field needs the same prove-it-first treatment. An existing
   strictly-monotonic counter would be an acceptable substitute **only** if
   its monotonicity is observed across death, warp, reload, and NG cycles.

## 7. Receipt schema extension

- `SlotLedger` gains `save_watermark: Option<u64>` — the last cursor value
  confirmed written to the save. `#[serde(default)]` keeps older ledgers
  loadable; a missing watermark under the current attested mode is the
  status quo, not an error.
- The Python fallback client does **not** grow this. Its receipt stays a bare
  counter and, per §1, it should stop auto-delivering for any seed the native
  client covers rather than grow a second, weaker reconciliation path. That
  retirement is owner decision O3 below.

## 8. Operator surface

Every non-`resume` comparison prints one line a player can act on:
`restore detected: save is at delivery 41 of 53; re-delivering 12 items`, or
`refusing: this character is not the one bound to this slot`, or `held:
delivery state could not be verified; no items granted or lost`. Silent
success and silent refusal are both bugs here.

## 9. Mock fixtures to add before any live behavior

- restore with goods partially consumed *before* the restore (re-delivery
  must not double-count consumption that the restore erased);
- restore across an equipment ack (re-grant skips the storage-box ambiguity
  entirely: watermark decides, inventory never does);
- ledger rolled back with save intact (W > H: adopt, no re-grant);
- switch-then-restore (identity refusal precedes watermark comparison);
- watermark unreadable mid-seed (hold; resume after it recovers; no grants in
  between);
- operator-attested `restored K` rewind replays K+1..H exactly once and is a
  fixed point across a process restart.

## 10. Open questions for the owner

- **O1.** Accept a new per-delivery save write (the watermark), or start with
  the attested `restored` command and treat the watermark as later hardening?
- **O2.** Watermark home: dedicated scratch field vs. a validated monotonic
  counter — decided by #56's discovery, not here.
- **O3.** Retire auto-delivery from the Python fallback once the native path
  covers the seed, or keep it as a deliberately weaker mode with the hazards
  documented in its `--help`?
