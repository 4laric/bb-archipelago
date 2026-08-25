# Install atomicity: committing the detours without crashing the guest

Status: **implemented, and validated against the game on 2026-08-24.**
The protocol, its ordering guarantees, and the fail-closed abort are exercised by
unit tests against a fake thread controller (`tests/test_native_delivery.py`,
classes `SafeInstallProtocolTests` and `InstallRoutingTests`). The live
suspend-and-read-RIP primitive (`WindowsThreadController`) passed owner checklist
item 5a in `docs/SPEC-client-without-cheat-engine.md`: on a live shadPS4 process
(CUSA03173 `01.09`) it enumerated the guest's threads, balanced
suspend/resume, returned plausible in-module RIPs, and both detours were
committed under a single suspend with the game still running afterwards. Scope:
one armed install on one build. It is not a proof against every thread schedule
the guest can produce, and CI still exercises the fake, not the primitive.

## The hazard

`tools/bb_native_delivery` installs its payload by writing, at two hook sites,
an `E9 rel32` jump plus `NOP` padding that exactly covers the displaced original
instruction bytes:

| hook | eboot RVA | original bytes | window |
| --- | --- | --- | --- |
| consume | `0x14D9575` | `44 89 E0 48 83 C4 28` (7) | `E9 rel32` + 2 `NOP` |
| heartbeat | `0x1BFE882` | `48 81 C4 E8 07 00 00` (7) | `E9 rel32` + 2 `NOP` |

The heartbeat hook **executes every frame**. So at the instant the installer
calls `WriteProcessMemory` over its seven bytes, a guest thread can be partway
through fetching or executing the instruction that lives in that window. The
write is not atomic against that thread: it can resume into a half-old,
half-new byte sequence — an illegal or wrong instruction — and take a native
CPU fault. That fault is not a Python exception the installer can catch; the
guest is already gone. Re-reading the bytes after the write ("verify after")
passes happily, because the bytes are now correct — the thread that died died on
the *intermediate* state, which no readback can observe. This is why install
atomicity was left absent-not-half-done: it cannot be made safe by verification,
only by making sure no thread is inside the window when the bytes change.

Note on tearing: `WriteProcessMemory` of seven bytes is not architecturally
guaranteed single-copy-atomic — only aligned accesses up to eight bytes are, and
the hook offsets are not aligned. But tearing is the smaller problem. Even a
perfectly atomic seven-byte store does not help a thread that is *mid-instruction
inside the window*: the store changes the bytes under its feet regardless of how
few memory transactions it took. A full thread suspend is required either way;
the atomicity of the store itself is a second-order concern behind it.

## The write ordering is the first line of defense (already structurally true)

The payload has five regions. Two — the caves — are jump targets; the detours
are what redirect the guest into them; the state region is data. `payload.blobs()`
returns them in this order, with the detours last:

```
[state_region, consume_cave, heartbeat_cave, consume_detour, heartbeat_detour]
```

and its docstring says why: "a detour that lands before its cave points a live
guest thread at zeroed memory." A detour is the **commit point** — nothing in the
guest jumps to a cave until a detour exists, so everything written before the
detours (state + both caves) is inert on its own. This ordering is not just a
convention; it is pinned by the test
`test_install_order_writes_the_caves_before_the_detours`
(`tests/test_native_delivery.py`), which asserts `consume_cave` precedes
`consume_detour` and `heartbeat_cave` precedes `heartbeat_detour` in the install
list. `install()` in `process.py` writes the non-detour blobs in full before it
begins the detour protocol, so the same ordering holds at write time, not only
structurally — asserted by `test_a_clear_arm_writes_caves_before_detours`.

The consequence that makes fail-closed cheap: **if we abort after the caves but
before the detours, the image is consistent and un-hooked.** Aborting costs
nothing to clean up.

## The safe-install protocol

Implemented in `tools/bb_native_delivery/threadcontrol.py`
(`install_detours_atomically`). Both detour writes are the second phase of
`install()`, run only when arming (`dry_run=False`) and only with a
`ThreadController` supplied — arming without one raises rather than writing a
detour blind (`test_arming_without_a_controller_fails_closed`).

For each attempt, up to a bounded budget (`DEFAULT_ATTEMPT_BUDGET = 100`):

1. **Enumerate** the guest process's threads.
2. **Suspend all** of them.
3. **Read each thread's RIP** once. If any RIP falls within `[hook, hook+7)` for
   *either* detour site, this is the unsafe window.
4. **If unsafe — nudge:** resume all threads (letting the scheduler advance them
   out of the window), then loop and re-enumerate/re-suspend/re-check. This is
   the "resume briefly, re-suspend, re-check" step.
5. **If clear:** write **both** detours, under this one suspend, then resume all.
6. **Budget exhausted → fail closed:** raise `InstallAborted` having written **no
   detour**. The caves are harmless, so the image is left consistent and
   un-hooked. (`test_budget_exhaustion_aborts_with_no_detour_written`,
   `test_a_blocked_arm_aborts_leaving_the_original_hook_bytes` — the latter a
   positive witness: both hook sites still hold their original bytes after the
   abort.)

### Both detours under a single suspend — yes, deliberately

The two writes happen inside one suspend, not two. If the first detour were
committed and threads resumed before the second went in, a thread redirected
through the first cave could re-enter the *second* window after the first
redirect but before the second detour existed — reintroducing exactly the hazard
the protocol removes. One suspend, both writes, then resume.
`test_both_detours_are_written_under_one_suspend` asserts the commit callback
runs while every thread is still held (net suspends > 0) and within a single
enumerate round.

### Resume is guaranteed on every path

A leaked suspend is its own hang — a thread never resumed freezes the guest as
surely as a crash. `install_detours_atomically` resumes every suspended thread in
a `finally`, so the clear-and-write path, the not-clear-nudge path, and a
*raising* `write_detours` all resume. `test_resume_runs_even_when_the_write_raises`
and every abort/nudge test assert `net_suspended == 0` afterward.

### RIP window test is half-open

`[hook, hook+7)`. `hook+7` is the first byte past the detour and is safe; a
terminated thread (no context, RIP `None`) is treated as not-in-window.
(`test_the_window_boundary_is_half_open`.)

## What CE itself does — and does not do

`tables/Bloodborne-native-item-grant-auto-v2.CT` installs via a single
`autoAssemble` block. It contains no thread suspension, freeze, or
`SuspendThread`/`speedhack` call — grep confirms one `autoAssemble` and zero
suspend primitives. Cheat Engine's `autoAssemble` writes the detour bytes with
the same non-atomic `WriteProcessMemory` this hazard describes; it simply gets
away with it in practice because the odds of catching the heartbeat thread
mid-window on any one install are low. That is a probability, not a guarantee,
and "low odds per install, across every player and every launch" is not a
safety argument this project is willing to ship on. The protocol above closes it
deterministically.

## The seam and what stays owner-gated

The live primitive is injected exactly the way `process.py` injects
`OpenProcess`/`ReadProcessMemory`, so the whole control flow runs on Linux under
a fake:

- `ThreadController` (Protocol): `enumerate()`, `suspend(tid)`, `resume(tid)`,
  `rip(tid) -> int | None`.
- `WindowsThreadController`: the real implementation — Toolhelp thread snapshot
  filtered to the pid; `SuspendThread`/`ResumeThread`; `GetThreadContext` with
  `CONTEXT_CONTROL` for RIP. **`validated` 2026-08-24** — owner checklist item 5a
  passed on a live shadPS4 process, one install on one build. No automated test
  touches it.
- `FakeThreadController`: scriptable RIPs (fixed or a per-read sequence) and full
  suspend/resume logging, so tests drive the nudge loop, the abort, and the
  no-leaked-suspend invariant.

Everything except the live suspend/RIP read is tested. The live read is the one
thing this environment cannot exercise; it was validated by hand on a throwaway
save on 2026-08-24, and any future change to it needs the same treatment, because
no gate here will catch a regression in it.
