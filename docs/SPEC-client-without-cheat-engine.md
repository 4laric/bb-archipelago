# Spec: retiring Cheat Engine from the player-facing path

Status: design. Derived from reading `tables/Bloodborne-native-item-grant-auto-v2.CT` and
`tables/Bloodborne-shadPS4-readonly.CT`, then revised after an adversarial review. Not from a
prototype.

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

**Install atomicity is under-specified and "verify before, re-verify after" does not cover it.**
The heartbeat hook at `0x801BFE882` executes every frame; a 5-byte `E9` written by
`WriteProcessMemory` is not atomic against a guest thread mid-fetch, and re-verification passes
happily after that thread has already died. The standard answer applies: suspend threads, check
their instruction pointers against the patch window, write, resume. `VirtualProtectEx` on the RX
code pages is also hiding inside the "trivial" `WriteProcessMemory` row above.

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
