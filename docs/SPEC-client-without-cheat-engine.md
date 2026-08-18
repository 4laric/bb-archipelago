# Spec: retiring Cheat Engine from the player-facing path

Status: design. Derived from reading `tables/Bloodborne-native-item-grant-auto-v2.CT` and
`tables/Bloodborne-shadPS4-readonly.CT`, not from a prototype.

## The decomposition that matters

Automatic checks and automatic item delivery are **different problems with different
dependencies**, and the project has been treating them as one.

| | mechanism | needs code injection? | blocked on |
| --- | --- | --- | --- |
| Item delivery | native call on the game thread | **yes** | nothing — it is done |
| Check detection | read the event-flag table | **no** | Lane B (where the table is) |

Delivery is hard because a write has to happen in a legal execution context. Detection is a
read. It needs no cave, no detour, no trigger, and no game thread. Once Lane B answers *where
the flag state lives and how a flag id indexes into it*, automatic checks are a
`ReadProcessMemory` loop.

**So the path to automatic checks does not run through porting the grant harness.** It runs
through Lane B plus a read-only client, and those can be built in either order.

## What Cheat Engine is actually providing

Itemised from the working table, with the replacement for each:

| CE service | used for | replacement | difficulty |
| --- | --- | --- | --- |
| `openProcess("shadPS4.exe")` | attach | `OpenProcess` | trivial |
| `readInteger` / `readQword` | inventory walk, polling `done` | `ReadProcessMemory` | trivial |
| `writeInteger` / `writeQword` | queue a descriptor, set `request` | `WriteProcessMemory` | trivial |
| a repeating timer | the poll loop | any loop | trivial |
| the command/state files | client ↔ harness bridge | **disappears** — same process | negative work |
| `assert(addr, bytes)` | refuse to patch a changed image | read + compare | trivial, and it is the AOB seed |
| `autoAssemble(...)` | build the cave payload and the detours | **build-time, not runtime** | see below |

Only the last one looks hard, and it is not, because **the payload is static**. The assembly
in the table has no runtime-variable operands. Assemble it once, capture the bytes, ship them
as a constant blob. Cheat Engine becomes a build dependency of the developer, not a runtime
dependency of the player.

## The one real gotcha: the payload is position-dependent

The cave assembly embeds absolute addresses:

```
mov rax,8014DA0A0     ; ItemGrant
mov rax,8014D94A0     ; quantity-delta routine
mov rax,8014DA2C0     ; find-slot-by-descriptor
jmp 8014D957C         ; return to the consume hook
lea rsi,[8050DBE40]   ; heartbeat descriptor
add rsp,7E8 / jmp 801BFE889
```

and the two hook sites are patched with `E9 rel32`, which depends on both ends. All of these
are `guest_base + fixed_offset` where `guest_base` was `0x800000000` in every observation so
far — but that is an observation across two serials, not a guarantee, and shadPS4 exports
`g_eboot_address` precisely so it does not have to be assumed.

Therefore the blob ships with a **relocation table**: a list of `(offset_into_blob, width,
eboot_relative_target)` that the installer fixes up after resolving the real base. This is
about thirty lines of code and it is the difference between a client that works on one
machine and one that works.

Do not skip it and hardcode `0x8...`. That is the same class of mistake as pinning a symptom
instead of deriving the datum.

## Staged path

Each stage is independently shippable and each one is useful on its own.

### Stage 1 — read-only client

No injection, no writes, no risk. The client:

1. Opens `shadPS4.exe`.
2. Resolves `g_eboot_address` from the module's export table and dereferences it to get the
   guest base.
3. Reads 16 bytes at each of the six published hook sites and compares against the recorded
   originals — the same check `assert()` does in the table.
4. Reports base, matched-site count, and its own version on connect.

This proves attach, base resolution and image identity without touching a byte, and it is
what makes #7 answerable: a tester's connect banner names the client build, the resolved base,
and whether the image is the one we know.

`tables/Bloodborne-shadPS4-readonly.CT` is already the specification for step 3; it is a list
of six addresses and their expected byte arrays.

### Stage 2 — automatic checks

Needs Lane B first. Once the flag-manager global and the id-to-bit addressing are known:

1. Read the global once per session to get the manager pointer.
2. Poll the relevant words, decode to flag ids, diff against the previous poll.
3. Send `LocationChecks` for the six mapped pickups; keep `/check` as the manual fallback.

Nothing here needs a write. **This is the stage that makes Bloodborne an Archipelago game**,
and it can ship with delivery still going through Cheat Engine if that ordering is convenient.

The discovery method is already proven in this codebase, on this game: the harness captures
the live inventory pointer with `mov [bbAutoInventory],r13` at the consume hook — a register
snapshot at a known instruction. The flag manager gets found the same way, via a write
breakpoint on a confirmed flag bit.

### Stage 3 — client-side injection

The client installs the frozen, relocated blob itself and drives `request` / `done` /
`descriptor` by direct writes. The file bridge in `client.py` and the whole `.CT` are deleted.

Ordering note: install must not patch bytes a guest thread is currently executing. The table
gets away with it because the player is at a menu; a client should verify the original bytes
immediately before the write and re-verify immediately after, and treat a mismatch as fatal
rather than retrying.

### Stage 4 — optional: install via shadPS4's own IPC

`mask_jump32` over `PATCH_MEMORY` does pattern-scan-and-detour inside the emulator, which
buys version robustness for free — it applies regardless of `APP_VER`, unlike every other
patch type. Two constraints: the IPC is **write-only**, so reads still need
`ReadProcessMemory`, and enabling it makes the client shadPS4's parent process and hands it
ownership of the entire patch set.

Worth knowing about. Not worth doing before stage 3 works.

## Assumptions to verify rather than assume

- **Guest memory sits at a stable host virtual address.** The harness hardcodes `0x8...` and
  works, so this holds in practice today. It is an emulator implementation detail and could
  change.
- **`g_eboot_address` is exported.** True per an earlier read of shadPS4's source; re-verify
  against the version testers will actually run.
- **shadPS4 executes guest x86-64 natively.** This is why code caves work at all. If it ever
  gained a recompiler, the entire approach changes.
- **No anti-cheat.** It is an emulator running offline. Nothing to defeat.

## What this does not solve

Lane B. Everything above is client engineering; none of it discovers where a flag lives.
Stage 1 and stage 3 can be built while Lane B is open, and stage 2 cannot start until it
closes.
