# Category-8 runtime investigation and test boundary

## Field evidence for #362 (2026-09-05)

Target: CUSA03173, AppVer 01.09, shadPS4 0.18.0. Read-only inspection of
PID 20060 with client PID 2772 (`b5077b9ed0d3`, r10). Guest eboot base:
`0x55F0000`. The initial inspection changed no game state. The subsequent authorized
throwaway-save experiment is recorded below. The operator reported normal gameplay and no visible incoming token
in held inventory. The local evidence bundle is `work/issue362-live-20260905`
in the owner's original checkout; game bytes in it must not be committed.

### Observed

- Setter bytes at eboot+`0x17D6EFA` match `88 0C 02`. Flag `12400913` reads
  false through the native client's tree-walk algorithm.
- The entire decompressed common event file is present at `0x211938810`,
  matching installed bytes (SHA-256
  `8b931b6c0cbcefdff86a0b97d438e609cf2dbe9f5beba11b8a56b6e5ec3456cf`).
  Its DCX hash is
  `4f696bc5b8b96449ee35509fecbac3d0fe950649ddbb59c5127454ca6d6451e3`.
  Presence in process memory does not establish execution of each event.
- The installed Goods parameter file is also present byte-for-byte in memory
  at `0x2095269C0`. Token 9815 exists in this table.
- The client's cached inventory pointer is `0x2080700B0`. It has two occupied
  records: 11 Blood Vials and one token 9815 (slot 66). The token record is
  `572600b0572600400100000042805507`.
- A second object with the same vtable, `0x208067778`, contains equipment,
  progression items, ordinary consumables and 22 Vials, with no token 9815.
  Its `+0x288` points to the cached object. The objects' mode bytes at
  `+0x8C` are respectively 0 (equipment-filled) and 1 (cached).
- Disassembling the live quantity-delta routine shows `r13 = rdi` at
  eboot+`0x14D94B6`. At `0x14D9522`, `[r13+0x8C]` selects either
  `0x1A89230` (zero) or `0x1A894A0` (nonzero). The latter's Goods branch
  reads the signed word at Goods row `+0x48`, falling back to 99 when
  nonpositive. The extracted Vial row has 600 there, the source token-template
  row 99, and token 9815 has 0, matching their repository capacities.
- The consume detour unconditionally caches `r13` and can dispatch a pending
  AP request on either kind of inventory. The native client's `geometry()`
  and `inventory_ready()` do not distinguish these modes.
- The seed and active ItemLot table use old consecutive AP lot IDs. Row 15
  is `98000015`. The bundled isolated event uses `98000150`, absent from the
  active parameter table. The launcher sources params from the request and
  common events from its current catalog, allowing this contradiction even
  after a complete cache rebuild.

### Conclusions and limits

The cache is pointing at the repository-capacity inventory, while the client
labels its successful readbacks as held. This is a concrete defect in inventory
selection and destination diagnosis. It strongly explains the held-token stall:
the event's including-storage predicate can see the token, but its held-only
removal cannot consume it. Event instruction-pointer sampling was not performed,
so the exact event PC has not been observed. Object roles have static and memory
evidence; A subsequent normal Vial use decreased both the HUD and held-memory count
from 22 to 21 and captured the mode-zero object. Token recovery remains open. Do not call the whole delivery path fixed or validated by these reads.

The mismatched lot IDs are an independently confirmed construction defect that
would remain after resolving inventory selection. The launcher now migrates the known consecutive lot IDs to the catalog stride
before cache selection and sends the migrated rows to the parameter writer.
Token, acknowledgement, recipe and AP identity remain unchanged. Other contract
mismatches are rejected. This repairs generated files; it does not transfer an
already stranded storage token.

The unsorted Goods row tail was also inspected. Sorting is not proposed as a
fix: no evidence established the game's lookup algorithm as the cause.

## What CI now executes

The existing native integration job forges a synthetic common event file,
runs the real C# writer with all 58 catalog rows, reads its binary back using
`dump`, and feeds the resulting instructions and parameter substitutions into
`tools/check_category8_event_runtime.py`. There are no licensed input bytes.

Each row exercises absence, one token, duplicate tokens, stale acknowledgement,
replay, blocked removal, storage-only possession, and withdrawal. Assertions
check consumption, one award, acknowledgement ordering and waiting on replay.
Six injected row-15 faults must fail: wrong token, wrong lot, wrong ack
substitution, wrong removal substitution, early ack, and missing initializer.
The launcher tests separately cover the actual old seed/new bridge mismatch,
including rejection before plan/cache/process work. The development compiler
verifier checks every isolated event rather than just the pilot event.

This is a bounded protocol model, not a general EMEVD interpreter. Fair event
scheduling, item recognition, single predicate groups, and held-only removal
are declared assumptions. In particular it cannot independently validate the
engine's condition-group lifetime or prove a native hook selected held inventory.
Unknown instruction shapes fail rather than silently succeeding.

## How far mocking can go

| Layer | Suitable for CI | What remains outside its proof |
| --- | --- | --- |
| World/params/events | Real writers over synthetic formats; cross-file IDs, token flags, lot stride, parameter substitutions, unrelated-file preservation | Game engine acceptance of a structurally valid file |
| AP client protocol | Scripted server/backend, durable ledger reload, duplicates, reconnects, stalls, readiness and character changes | Actual game item creation |
| Process memory | Two separate held/storage objects with the same valid geometry; null, stale and torn pointers; short reads, access failures and process exit | Whether captured offsets match an emulator/game build |
| Native hooks | Controlled helper process and instruction emulation to test payload branches, registers, guarded writes, stopping/cleanup and failure injection | Real guest-thread scheduling and emulator protection behavior |
| Live acceptance | Small scripted tests with positive controls, named builds and save/reload evidence | Broad build compatibility unless tested explicitly |

## Implemented guards and live control

The consume payload checks inventory mode at `+0x8C` before caching or dispatch.
The heartbeat rejects a retained storage cache. Python and Rust inventory readers
also reject that mode even when all other geometry is valid. The generated
contract, vendored client contract and assembly table carry the same change.

CI executes the actual relocated x86-64 payloads using Unicorn 2.1.4. Native
callees are observation boundaries. Tests cover held capture, storage calls with
idle/grant/remove requests, retained storage at heartbeat, and a held heartbeat
positive control. Removing the consume guard reproduces the bad storage dispatch.
The Rust fake-memory regression provides two modes with otherwise valid geometry.

On 2026-09-05 the operator explicitly authorized the open save as disposable.
The save and session were backed up and the AP client stopped. A bounded patch
window suspended 106 emulator threads, checked their instruction pointers,
installed and read back the two guarded caves, flushed the instruction cache,
and resumed every thread. A normal Vial use then changed the HUD by minus one,
changed held Vials from 22 to 21, and changed the cache from storage
`0x2080700B0` to held `0x208067778`. This is an observed live capture control,
not restart validation or completed token/reward recovery. Ack remained false.

The operator found `?GoodsName?` in storage and withdrew it through the chest.
Memory showed exactly the same token instance move from storage to held slot 76,
with no duplicate. It remained held and unacknowledged after ten seconds outside
menus. Therefore storage selection alone does not explain the already-running
event's state; the precise pre-restart event PC remains unknown.

After a normal save, a controlled restart used the migrated 58-row lot table and
temporary flags for constructor entry, row-15 entry and its token predicate.
All three markers fired. Held slot 76 changed from token 9815 to exactly one
category-8 instance with recipe 102001; no other slot changed. Ack 12400913 became
true. The operator independently reported the Clear Deep Sea award. Restoring
the clean event file and restarting again preserved the rune with no second
popup and the ack still true. No replacement token or host-written ack was used.
Marker flags were confined to unused reserved IDs 12400997..12400999; their
instrumentation was removed. Private before/after files and saves are retained.

The fresh debug client also exposed a Windows context-buffer alignment failure.
Its AMD64 CONTEXT buffer now has explicit 16-byte alignment; a Windows CI test
suspends a real helper thread, samples its RIP and resumes it without a game.
The corrected client subsequently installed and connected on the clean restart.
After a Vial control it acknowledged index 34 without reissuing its token,
automatically re-queued parked index 6, and delivered the Butcher Gloves on the
next Vial. The operator confirmed both the rune persistence and the gloves.
Subsequent received items resumed through the normal queue.

## Local verification of this change

- Built BBFixtureForge and BBEventWriter with the CI-pinned SoulsFormatsNEXT
  revision `7cef52a7366678448d85930eeb8e94093b179d24` and .NET 9.
- Forged fresh inputs, ran the real writer, dumped its binary, and modeled all
  58 rows. All six injected row-15 faults were rejected.
- Common-event, bridge-contract, launcher workflow, packaging, and UI test
  modules pass. The final UI/bridge/native/common group passes 173 tests;
  the five CPU-emulation tests also pass.
- The full build gate encountered two existing test errors also reproduced
  in an untouched checkout of `348bbe3`: the bundled-goods resource test gets
  `None` during full-suite execution, and the case-collision test assumes a
  case-sensitive filesystem on Windows. The baseline ran 870 tests with two
  errors and 36 skips. The final changed tree ran 878 tests with the same two
  errors and 36 skips. These are not reported as a green full gate.
- A third error in the first changed-tree run came from an obsolete synthetic
  category-8 UI fixture. That fixture now uses the actual pilot contract and
  the entire UI module passes, including the cross-writer migration test.
- The client passes all 306 library tests with one test thread. A parallel run
  exposed an unrelated shared-console logging race (304/305 passed before the
  new Windows test); the serialized run is not evidence that race is fixed.
- No hosted CI run has been performed. Live capture, recovery and clean
  save/reload acceptance passed as described above.
