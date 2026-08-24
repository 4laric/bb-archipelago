# Save-restore and character-slot reconciliation (#77)

Status: **implemented and mock-tested in the native client; not live-validated.**
The scheme this document proposed (§5/§7) has landed in
`from-software-archipelago-clients` `crates/bb-archipelago`
(`ccf2dd8 bb: save-restore reconciliation via a save-resident receive
watermark`, on top of the identity gating in `ef2445e`). Every restore/switch
shape in §2 now has code and a mock fixture (§9). What is **not** done is the
game-bound half owned by #56: the live backend's `location_context`,
`read_save_watermark`, and `write_save_watermark` return the fail-closed
default (`None` / attested mode), so no restore is *automatically* detected
against a real save yet. Until those addresses are bound (§11), the shipping
path is operator attestation via the `bb-restored` command -- the honest MVP,
not a stub.

Evidence label (per `docs/RESEARCH-BASELINE.md`): the reconciliation logic and
state machine are **implemented and mock-tested**; they are **not `validated`**
-- nothing here has been seen live against CUSA03173 01.09, because the live
accessors are unresolved. Do not upgrade this to `validated` until the §11
address binding is done under the game with a readback canary.

The rest of this document is unchanged as the rationale of record: §1 is
verified code fact, §2-§10 are the design that shipped, and §11 (new) is the
owner game-session checklist for the remaining live facts.

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

## 11. Owner game-session checklist (the remaining live facts)

Everything in §2–§10 is implemented behind the `BloodborneBackend` boundary and
exercised in mock mode. Three facts still need a live CUSA03173 01.09 session on
current shadPS4 to bind; none can be guessed from static data, and each stays
fail-closed until bound. This is the `needs-game` residue of #56 and O1/O2.

Bind them in this order — each later step depends on the earlier one holding
across death, warp, reload and NG:

1. **Save identity source → `FileBackend::location_context` (`save_identity`).**
   Resolve a value that is stable per save+character, changes on slot switch or
   a different save, and survives process restart. Today `location_context`
   returns `None` in normal mode (fail-closed) and the `--assume-correct-save`
   gate substitutes an operator string. Record the address/derivation with a
   readback in `docs/RESEARCH-BASELINE.md` before wiring it.
   - Unblocks #56 acceptance: "mismatched character produces no checks",
     "switching to another character that already owns the pickup does not send",
     "a full shad restart … does not reuse stale identity".
   - Anti-hazard: two different characters must never hash to the same identity;
     prove distinctness live, do not assume the first field that looks unique is.

2. **Gameplay-ready signal → `FileBackend::location_context` (`gameplay_ready`).**
   A version-gated signal that is false on the main menu, during load
   transitions, and in the no-save state, and true only in live play. The
   attested gate approximates this with three consecutive event-flag-manager
   health reads (`ASSUMED_CONTEXT_STABLE_READS = 3`); a real signal should be
   something the manager-health proxy cannot spoof (e.g. a world/loaded-map
   state field), still funnelled through the same three-consecutive-read
   debounce so the acceptance timing is unchanged.
   - Unblocks #56 acceptance: "main menu, loading screens, no-save state …
     produce no flag reads and no AP checks"; the Iosefka Bullet canary sending
     exactly once.

3. **Save-resident watermark field → `read_save_watermark` / `write_save_watermark`.**
   A writable, game-inert scratch field in the save that survives save/load, is
   never rewritten by game systems, and passes a write→readback canary of the
   same standard the grant descriptors are held to (the #70 lesson: a nominal
   write can produce garbage). An existing strictly-monotonic counter is an
   acceptable substitute **only** if its monotonicity is observed across death,
   warp, reload and NG cycles (O2). Until this is bound, leave both methods at
   their attested-mode defaults (`None` / `false`) and rely on `bb-restored`.
   - Unblocks the *automatic* half of shapes B and C (§2). With it absent, the
     semantics still hold via operator attestation; with it present and
     canaried, restore detection becomes automatic with no re-grant hazard.

Do-not-do without the game: do not invent any of these three addresses, do not
relax the fail-closed defaults, and do not add an unsafe opt-out to seed data
(the `--assume-correct-save` flag is the only sanctioned attestation, and it
lives in the client, not the world/slot data). When a step is bound, flip the
corresponding evidence label in §Status from *mock-tested* to *validated* for
that fact only — one fact at a time, each with its own live readback.
