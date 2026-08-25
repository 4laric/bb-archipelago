# Spec: retiring Cheat Engine from the player-facing path

Status: **design, plus an extracted contract and a prototype that has now been driven end to end
against a live game.** The analysis below is unchanged. What has since been built, and what it is
worth, is in [What now exists](#what-now-exists) and the
[owner validation checklist](#owner-validation-checklist).

On 2026-08-24 the checklist was run on the owner's machine — shadPS4, CUSA03173 `01.09`, throwaway
saves — and items 4 through 10 passed, two of them only after a live failure was diagnosed and
fixed (issues #144 and #146, PRs #145 and #147). The tool has attached to, installed into, granted
through, and recovered against a real guest. That is `validated` for the paths the checklist
actually walked and nothing wider: one serial, one game build, one emulator version, one machine.
Two paths stay `inferred` because nothing exercised them — the equipment insert path, and any
build that is not CUSA03173 `01.09`.

Cheat Engine remains the supported delivery path and the tables are untouched: the client half has
not shipped, so none of this is player-facing yet. Item 3 (refusing a CUSA00900 image) is the one
checklist item still open, and it waits on a dump.

## The decomposition, and its load-bearing assumption

Automatic checks and automatic item delivery have different dependencies, and the project has
been treating them as one problem.

| | mechanism | needs code injection? | blocked on |
| --- | --- | --- | --- |
| Item delivery | native call on the game thread | **yes** | nothing — it works |
| Check detection | read the event-flag state | **no** | #15's client half |

Delivery is hard because a write has to land in a legal execution context. Detection is a read.

**Resolved 2026-08-18 — the assumption held.** Earlier drafts hedged this cell to "probably not",
because the claim rested on the flag manager being reachable from a static root and the one
comparable hunt this project had run said otherwise: the harness gets the inventory pointer by
hooking (`mov [bbAutoInventory],r13` at the consume hook) and needs the player to use one bullet
after launch before it caches. That is what finding a heap structure looks like when nobody found a
static chain to it.

The flag manager is not that. It hangs off eboot-relative pointer slot `RVA 0x553B100` on
CUSA03173 `01.09`, and a standalone reader running outside Cheat Engine rediscovered the base after
it moved between launches, passed the setter-signature gate at `RVA 0x17D6EFA`, and returned live
flag state. That is `validated` in this project's evidence vocabulary, across two independently
randomized launches — no cave, no detour, no bootstrap action. Detection is a plain
`ReadProcessMemory` traversal.

Two caveats survive. The validation covers CUSA03173 only; **CUSA00900 is untested**, and the
signature gate must fail closed there rather than guess. And "detection needs no injection" is a
claim about the *read*, not about the send — the containment work in `WORKPLAN.md` Phase 1 is
what stands between a correct read and an irreversible `LocationChecks`.

## What Cheat Engine is actually providing

| CE service | used for | replacement | difficulty |
| --- | --- | --- | --- |
| `openProcess("shadPS4.exe")` | attach | `OpenProcess` | trivial |
| `readInteger` / `readQword` | inventory walk, polling `done` | `ReadProcessMemory` | trivial |
| `writeInteger` / `writeQword` | queue a descriptor, set `request` | `WriteProcessMemory` | trivial |
| a repeating timer | the poll loop | any loop | trivial |
| the command/state files | client ↔ harness bridge | **disappears** — same process | negative work |
| `assert(addr, bytes)` | refuse to patch a changed image | read + compare | trivial, and it is the AOB seed |
| `autoAssemble(...)` | build the cave payload and the detours | **build-time, not runtime** | see below |

Only the last looks hard, and it is not: the payload is static. Every operand in the cave assembly
is a constant or a label — verified by inspection. Assemble once, capture the bytes, ship them as a
constant blob. Cheat Engine becomes a developer's build tool, not a player's runtime dependency.

The native `ItemGrant` argument is a 24-byte object, not the earlier inferred
16-byte pair: raw descriptor at `+0x00`, internal pointer at `+0x08`, and
normalized ID at `+0x10`. On shadPS4 v0.18, placing that object below the
consumable callback's current `rsp` allowed it to become zero before the nested
insertion helper used it. The validated payload materializes all 24 bytes in
the callback's retiring 0x28-byte local frame and calls `ItemGrant` before the
original epilogue releases that frame.

## The payload is position-dependent

The cave embeds absolute addresses:

```
mov rax,8014DA0A0     ; ItemGrant
mov rax,8014D94A0     ; quantity-delta routine
mov rax,8014DA2C0     ; find-slot-by-descriptor
jmp 8014D957C         ; return to the consume hook
lea rsi,[8050DBE40]   ; heartbeat descriptor
add rsp,7E8 / jmp 801BFE889
```

and both hook sites take `E9 rel32`, which depends on where the cave lands.

All of these are `guest_base + fixed_offset`. shadPS4 has hardcoded `0x800000000` as the module
base since PR #2879, so this is stabler than "an observation on two serials" — but the same PR
thread records the mapping as knowingly inaccurate with an address-space rework anticipated, and
`g_eboot_address` is exported (`src/common/memory_patcher.h`, `extern EXPORT uintptr_t`) precisely
so nobody has to assume. **Resolve it. Ship a relocation table:** `(offset_into_blob, width,
eboot_relative_target)`, fixed up at install.

## Staged path

### Stage 1 — read-only client (#13)

No injection, no writes. Open `shadPS4.exe`, resolve `g_eboot_address`, dereference for the guest
base, read 16 bytes at each of the six published hook sites and compare against the recorded
originals, then report base, matched-site count and the client's own version on connect.

`tables/Bloodborne-shadPS4-readonly.CT` is already the specification for the byte checks.

⚠️ **Stage 1 is not a prerequisite for stage 2, and must not be sequenced as one.** It is parallel
polish that de-risks the base assumption and makes #7 answerable. It also overlaps
`tools/read_hook_sites.ps1`, which already does the read side.

### Stage 2 — automatic checks

Needs #15. Read the manager pointer, poll, diff, send `LocationChecks`, keep `/check` as fallback.

**The fastest path to automatic checks does not go through stage 1 or stage 3.** The Cheat Engine
harness is already a proven scriptable reader with a proven file bridge — 200 lines of Lua driving
timers, memory reads and file I/O. Adding a `POLL` command to the table and a state-file consumer
to `client.py` gets automatic checks the day #15 closes, with no new attach, relocation or
injection code on the critical path. Do that first; port it to native reads afterwards.

**Containment is the hard half, and it belongs here.** `LocationChecks` cannot be retracted, so an
unsynchronised read against a live structure is not "no risk" — it is irreversible risk spread
across an entire multiworld. Required before this ships:

- revalidate the manager pointer every poll, not once per session;
- gate polling on being in gameplay, not a loading screen or a menu;
- debounce: N consecutive polls agreeing before a check is sent;
- bind to save identity, so character B's flags are never read against character A's slot.

Also one live test owed while the debugger is out: **can the native grant path itself set
acquisition flags?** If so, deliveries self-report as checks. Probably not, since the grant
bypasses lot logic, but nobody has checked.

### Stage 3 — client-side injection

The client installs the frozen, relocated blob and drives `request` / `done` / `descriptor`
directly. The file bridge and the `.CT` are deleted.

**Install atomicity — now implemented; the live primitive is owner-gated.** The heartbeat hook at
`0x801BFE882` executes every frame; a 5-byte `E9` written by `WriteProcessMemory` is not atomic
against a guest thread mid-fetch, and re-verification passes happily after that thread has already
died. The standard answer is implemented in `threadcontrol.py` and documented in
`docs/INSTALL-ATOMICITY.md`: suspend all guest threads, check each RIP against the two seven-byte
patch windows, write both detours under one suspend, resume; abort with no detour written if a
bounded budget is exhausted. The live suspend/RIP read is `validated` as of 2026-08-24 (checklist
item 5a): both detours were committed under one live suspend and the game kept running.
`VirtualProtectEx` on the RX code pages is also hiding inside the "trivial"
`WriteProcessMemory` row above.

### Stage 4 — install via shadPS4's IPC (probably not)

`mask_jump32` over `PATCH_MEMORY` pattern-scans and detours inside the emulator, and mask patches
bypass the `APP_VER` filter — verified in `memory_patcher.cpp`:
`if (!versionMatches && type != "mask" && type != "mask_jump32") continue;`.

An earlier draft called that "version robustness for free." **It is the opposite for this
payload.** mask_jump32 relocates the *hook site* and the *cave* by pattern; it does nothing about
the absolute operands inside the payload. On a different game build those constants point at the
wrong code — and the AppVer bypass guarantees the broken detour gets installed where every other
patch type would have been filtered out. It also appends its own back-jump after the payload,
while these caves already end in one.

Two further constraints: the IPC is **write-only** (command set is RUN/START/PATCH_MEMORY/PAUSE/
RESUME/STOP/TOGGLE_FULLSCREEN, no read), so reads still need `ReadProcessMemory`; and with
`SHADPS4_ENABLE_IPC=true` shadPS4 blocks waiting for `RUN` and calls `exit(1)` after five seconds.
That makes the client a hard launch dependency with a handshake deadline, not an optional extra.

Worth knowing about. Not recommended.

## Verified since the first draft

- `g_eboot_address` is exported — `src/common/memory_patcher.h`, `extern EXPORT uintptr_t`.
- Guest base `0x800000000` is hardcoded since shadPS4 PR #2879, with an address-space rework
  anticipated. Resolve it anyway.
- shadPS4 executes guest x86-64 natively and HLEs system libraries. Code caves remain viable.
- The payload has no runtime-variable operands. The frozen-blob plan is sound given relocation.
- No anti-cheat.

## What this does not solve

#15. Everything above is client engineering; none of it discovers where a flag lives. Stages 1 and
3 can be built while #15 is open. Stage 2 cannot start until it closes — but when it does, the
existing Cheat Engine harness is the shortest route to shipping it.

## What now exists

Landed on `agent/retire-ce-delivery` in this repository.

### The contract, extracted

`research/runtime/bb-native-grant-contract.v5.json` is the machine-readable statement of what
`bb-native-grant-v5` does to the guest process: hook sites and their original bytes, the three
native routine entries and their calling conventions, the cave and data RVAs, the state-cell
layout the bridge polls, the inventory geometry, the assert/AOB byte strings, the 24-byte
`ItemGrant` descriptor layout, the frozen payload bytes with their relocation table, and the
fail-closed policies. It is generated by `python -m tools.bb_native_delivery contract --write`,
and a test asserts the committed file is exactly what the generator produces.

It exists because RESEARCH-BASELINE.md already records the problem: the CE table, this document
and `crates/bb-archipelago` in the clients repo were three uncompared copies of one contract.
Now there is one artifact, and the tests compare it against the CE table's own text.

Every entry carries a `provenance` label from the RESEARCH-BASELINE.md vocabulary, and the tests
enforce that only those five labels appear. Two labels deserve emphasis:

- the **assembly source** is `validated` — Cheat Engine installed and exercised it live;
- the **byte encoding** is now `validated` too. On 2026-08-24 the caves were read back from a live
  armed shadPS4 process (`tools/compare_ce_payload.py`) and compared against the relocated frozen
  blobs. They agreed except for three reg-to-reg `mov`s that CE assembles in the RM form (`8B`)
  where the prototype had emitted the equivalent MR form (`89`) — semantically identical. The
  assembler was switched to CE's encoding, and the shipped blob is now byte-identical to what CE
  emits. Checklist item 1 is complete.

### The payload is position-independent apart from three quadwords

Assembling at base 0 shows the relocation table is smaller than the spec assumed. Every absolute
in the CE template except three is reached through a RIP-relative or REL32 form whose displacement
is a difference of two eboot RVAs, and those are base-invariant. The entire relocation table is:

| blob | offset | width | target |
| --- | ---: | ---: | --- |
| `consume_cave` | `+0x7A` | 8 | `eboot+0x14DA0A0` (`ItemGrant`) |
| `consume_cave` | `+0xB5` | 8 | `eboot+0x14D94A0` (quantity delta) |
| `heartbeat_cave` | `+0x38` | 8 | `eboot+0x14DA2C0` (find slot) |
| `heartbeat_cave` | `+0x5F` | 8 | `eboot+0x14D94A0` (quantity delta) |

A test asserts that two wildly different bases produce blobs differing *only* in those bytes.

Sizes: consume cave 219 bytes, heartbeat cave 117 bytes, state region 112 bytes, each detour
7 bytes (`E9 rel32` + two `NOP`, exactly covering the displaced original).

### The prototype

`tools/bb_native_delivery/` — developer-only, inert by default, Windows-only at runtime.

| module | what it replaces |
| --- | --- |
| `payload.py` | `autoAssemble` — assembles the cave from source, emits bytes + relocations |
| `aob.py` | `assert(addr, bytes)` and `AOBScan` byte-string semantics |
| `descriptor.py` | the 24-byte `ItemGrant` source object and the category branch |
| `process.py` | `openProcess` / `readInteger` / `writeInteger`, plus `VirtualProtectEx` |
| `threadcontrol.py` | suspend all guest threads, check RIPs, commit both detours atomically |
| `guest.py` | the inventory walk and the request/state cells |
| `delivery.py` | the harness `poll()` loop — queue, bounded verify, replay recovery |
| `contract.py` | emits and loads the contract |
| `cli.py` | `contract` / `payload` / `verify` / `install` / `grant`, all needing `--arm` to write |

The command-file bridge has no module, because in-process it does not exist.

`verify` never writes. `install` and `grant` are dry runs without `--arm`. `require_validated_image`
refuses on any assert mismatch, which is how CUSA00900 and every other build fail closed: a partial
match is a different image, not a near-enough one.

### Install atomicity — implemented, and validated live 2026-08-24

The heartbeat hook executes every frame, so writing its detour is not atomic
against a guest thread mid-fetch. This is now handled:
`tools/bb_native_delivery/threadcontrol.py` suspends every guest thread, verifies
no RIP is inside either seven-byte detour window, writes both detours under that
one suspend, and resumes; the budget-exhausted path aborts having written no
detour (the caves are harmless). `install()` routes the two detours through it
when arming, and refuses to arm without a thread controller. The protocol,
ordering, nudge loop, fail-closed abort, and guaranteed-resume invariant are unit
tested against a fake controller. The **live suspend + RIP read**
(`WindowsThreadController`) is `validated` as of 2026-08-24 (owner checklist item
5a below): on a live shadPS4 process it enumerated the guest's threads, suspended
and resumed them in balance, returned plausible in-module RIPs, and both detours
went in under a single suspend with the game still running afterwards. One pass
on one build — it is not a claim about every schedule the guest can produce.
Full rationale in `docs/INSTALL-ATOMICITY.md`.

### What is deliberately not implemented

- **Live AOB base discovery.** `process.py` reads the logged base and validates it against both
  hook originals; the scan fallback the CE table has is not ported. `--base` covers the gap.
- **Everything in stage 2.** No flag polling, no `LocationChecks`, no containment.

### Tests

`tests/test_native_delivery.py`, 97 tests, in the AP-free CI tier. They cover descriptor encoding
and the category branch, AOB parse/match/scan including fail-closed on a one-byte difference,
payload byte assembly against a frozen encoding plus structural invariants (detour covers the
original exactly, the displaced original is replayed, no region overlaps, caves install before
detours), the inventory bank split, log base resolution, and fourteen state-machine transitions:
the retired direct write, hydration grace, absent-Vial refusal, quantity mismatch, replay recovery with and
without a matching tag, slot-verified completion, fast-budget failure, hydration-budget patience,
and the busy request cell. The eleven added for install atomicity drive the safe-detour protocol against a fake thread controller: a clear RIP writes on the first attempt, a RIP inside a window nudges until it clears, budget exhaustion aborts with no detour written (a positive witness that both hook sites keep their original bytes), both detours land under one suspend, and every path resumes every thread. The live suspend/RIP read is no longer untested — checklist item 5a passed on 2026-08-24 — but nothing in this file exercises it; the fake is still what the suite drives.

They prove nothing about whether the guest accepts any of it. The
[checklist](#owner-validation-checklist) is where that evidence lives.

## Owner validation checklist

In order. Items 1-2 need no game running; items 3 onward need a live session and a throwaway save.

1. **~~Compare the frozen bytes against Cheat Engine's.~~ DONE 2026-08-24.**
   `python -m tools.compare_ce_payload --pid <shadPS4> --base 0x<from the table's AUTO V5 READY
   line> --armed` read back the 219 bytes at `eboot+0x50DBA00` and the 117 at `eboot+0x50DBC00`
   from a live armed process and diffed them against the relocated frozen blobs. Result: agreement
   after switching three reg-to-reg movs to CE's RM-form encoding (see above). The payload is now
   `validated`. (`--armed` is required because a loaded table overwrites the hook originals with
   `E9` detours, so the unarmed image check cannot pass; the tool confirms the base by the detours
   instead.)
2. **~~Run `verify` against unpatched then patched.~~ DONE 2026-08-24.** Unpatched (base
   0x5830000) returned six `ok` rows. With the CE table loaded, both hook rows flipped to `FAIL`
   (showing the `E9` detours) and `require_validated_image` refused — the gate detects the patched
   state. The armed cave bytes also matched the validated frozen payload. Pass `--base` from the
   AUTO V5 READY line for the patched run, since the loaded table overwrites the logged-base
   anchor.
3. **Refuse a wrong image.** If a CUSA00900 install is available, `verify` against it and confirm
   the refusal message names the mismatching site. If not, record that this remains untested.
   **Still open 2026-08-24** — no CUSA00900 dump was available. This is the only checklist item
   not yet run, and until it is, cross-build refusal is `inferred` from
   `require_validated_image`'s unit tests alone.
4. **~~Dry-run install~~ DONE 2026-08-24.** `install --pid <pid>` with no `--arm` on an unpatched
   process listed five planned writes whose names, addresses and sizes matched the contract at
   base `0x56B0000`. Nothing was written.
5. **~~Armed install on a throwaway save~~ DONE 2026-08-24.** With the CE table *not* loaded, the
   armed install wrote all five regions; the readback of every region matched the plan byte for
   byte.
5a. **~~Validate the live thread-suspend primitive~~ DONE 2026-08-24.** The armed install of item 5
   routed both detours through `WindowsThreadController`: `enumerate()` returned the guest's
   threads, `SuspendThread`/`ResumeThread` balanced, `GetThreadContext` returned plausible
   in-module RIPs, both detours landed under one suspend, and the game kept running afterwards —
   the still-running guest is the pass. The primitive is now `validated`; note the scope, which is
   one install on one build, not a proof against every thread schedule. See
   `docs/INSTALL-ATOMICITY.md`.
6. **~~One grant, category 4: absent Pebble~~ DONE 2026-08-24.**
   (`--raw 0xB00004CE --normalized 0x400004CE`, one Bullet fired first to cache the inventory
   pointer.) A native slot appeared with quantity 1 and the game stayed responsive. This is the
   first item ever delivered into Bloodborne by this project without Cheat Engine.
7. **~~One grant, existing stack~~ DONE 2026-08-24, after a live failure and a fix.** The original
   plan here was "expect the direct-write path, no native call". Running it **froze the guest
   twice**. Finding (issue #144, with the evidence in its revision comment): the guest inventory
   page is protection-tracked by shadPS4, so an external `WriteProcessMemory` into it wounds the
   emulator regardless of how correct the value is. **The direct-write path is retired for live
   guests.** PR #145 routes existing-stack grants through the cave's request-word-2
   quantity-delta branch instead, which executes on the game thread; the re-run passed
   (`native existing-stack delta slot=78`). The delta branch is `validated`. Whether the *insert*
   path's `ItemGrant` merges into an existing stack or duplicates the slot is moot for the delta
   path and stays `inferred` for the equipment insert path. Eboot-image regions remain safe for
   external writes — the retirement is about guest data pages, not about every write.
8. **~~Restart persistence~~ DONE 2026-08-24, with a stronger witness than asked for.** The
   granted item survived a **hard process kill** of shadPS4 and a relaunch, not merely a graceful
   shutdown. The grant is in the save, not in emulator state.
9. **~~Replay recovery~~ DONE 2026-08-24, with a caveat that is now load-bearing.** Killing the
   client between the durable grant and the acknowledgement and restarting produced
   `recovered_complete` with no second grant — **when `--expected-before` was supplied.** Without
   it, a same-tag rerun *double-granted*, observed live: the CLI samples a live baseline when none
   is given, so a partial prior delivery is invisible to it. PR #147 added the tag journal and the
   baseline-free warning that guards this, but the rule survives the guard: **replay recovery
   requires `--expected-before`.**
10. **Confirm the fail-closed rows still fail closed.**
    a. **~~Absent Blood Vial refused~~ DONE 2026-08-24.** The hydration budget was exhausted
       (39 of 40 polls) and then the coded refusal fired, exactly as designed.
    b. **~~Torch ItemLot id unreachable~~ FAILED 2026-08-24 on the first run, then fixed and
       re-run.** The Torch canary **executed** via the persistent-source path and produced an
       invisible record at slot 79 on a throwaway save. Cause (issue #146): the CLI had no
       descriptor allowlist, so the negative canary reached the attach at all. PR #147 added a
       fail-closed pre-attach allowlist; the re-run **refused with zero polls and no guest memory
       touched**. Recorded as a failure because it was one — the design intent was right and the
       CLI did not implement it.

Items 1, 2, 4, 5, 5a, 6, 7, 8, 9 and 10 are done; item 3 is open on a CUSA00900 dump. Two of those
passes cost a live defect each (#144, #146) and both fixes shipped (#145, #147). Cheat Engine
remains the shipping path for at least one more release regardless — the checklist validates the
delivery tool, not a client that uses it.
