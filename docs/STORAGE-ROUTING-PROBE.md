# Storage-routing probe — operator runbook

`python -m tools.bb_native_delivery probe-storage`

## What it answers

Native grants sometimes land in **held inventory** and sometimes in the Hunter's
Dream **storage box**, and nothing in the tool can see which: the destination is
visible only in the game's UI. oz's two full-seed clears (clients#445 and its
follow-up comment) narrowed it to four questions, and every one of them needs an
operator's eyes:

| | question | how it is settled |
| --- | --- | --- |
| **H1** | Does the grant routine return the new **held count** on a normal add and **`1`** on overflow-to-storage? Currently `inferred` from two live data points. | a normal sub-cap add and a deliberate at-cap add, on two different goods ids |
| **H2** | Does a **unique-item** insert delivered **idle** in normal gameplay land held? | one Saw Spear insert, idle, before anything has overflowed |
| **H3** | **STICKY** — after a vial add overflows at cap, does the **next** add go to storage too, whatever it is? | a Saw Spear insert immediately after a witnessed vial overflow, plus a sub-cap Pebble after a second one |
| **H4** | Does the **state** matter — right after a boss kill, or while not gameplay-idle? | the same sub-cap Pebble add, in each state, against the idle baseline |

Every step also records the insert **source lane** (`persistent` for equipment,
`in_frame` for goods — `uses_persistent_source`), so "it is our lane selection"
can be ruled in or out rather than argued about.

## Before you start

- **Use a throwaway save.** Two steps insert a unique weapon. A unique item can
  be inserted **once per save** and is not removable afterwards. `--arm` refuses
  without `--yes-throwaway-save` for exactly this reason.
- **Two passes, two saves.** Because the unique insert is once-per-save, H2 (idle)
  and H3 (sticky) cannot share one. Pass **A** runs the idle unique; pass **B**
  runs the sticky one, on a second throwaway save.
- The game must be the validated image (shadPS4, CUSA03173 01.09) with the
  payload installed. `verify` first; a partial assert match is a different image,
  not a near-enough one.
- Nothing writes a guest data page. Probe grants go through the ordinary
  `GrantSession`, so they inherit the descriptor allowlist (#146), the stale
  request-cell gate (#144), the `--expected-before` reconciliation, and the
  loop-wide Ctrl+C disarm (#147). There is **no** `--unvalidated-descriptor` on
  this subcommand; the probe's items are Pebble, Blood Vial and the Saw Spear.

## The order, and why it is the order

Ordering is evidence here, not presentation. In pass A the unique insert (`a2`)
runs **before** the deliberate cap overflow (`a3`): running it after would
measure H3 and call the result H2 — the exact confound the sticky hypothesis
proposes. In pass B, `b3` must follow `b2` with **nothing in between**.

Print the full list, generated from the step definitions so it cannot drift:

```
python -m tools.bb_native_delivery probe-storage --runbook
```

| step | H | item | what to do in game first |
| --- | --- | --- | --- |
| `a1-normal-add` | H1 | Pebble | hold 2–18 Pebbles, idle at a lantern |
| `a2-unique-idle` | H2 | Saw Spear | still idle, **nothing overflowed yet**, no boss killed since load |
| `a3-cap-overflow` | H1 | Pebble | fill Pebbles to 20/20; note the storage count first |
| `a4-post-boss` | H4 | Pebble | drop back below cap, kill a boss, arm while the post-kill state is current |
| `a5-non-gameplay` | H4 | Pebble | sub-cap, but sitting in the inventory menu / a warp |
| `b1-vial-normal-add` | H1 | Blood Vial | **save B**; hold ≥1 Vial, below cap, idle |
| `b2-vial-overflow` | H1 | Blood Vial | fill Vials to 20/20; note the storage count |
| `b3-unique-after-overflow` | H3 | Saw Spear | immediately after `b2`, touching nothing |
| `b4-reoverflow` | H3 | Blood Vial | refill to cap, overflow again |
| `b5-goods-after-overflow` | H3 | Pebble | immediately after `b4`, Pebbles **below** cap |

## Running a pass

```
python -m tools.bb_native_delivery probe-storage --pid <shadPS4> --pass a \
    --save-id throwaway-a --arm --yes-throwaway-save
```

Without `--arm` it is a rehearsal: it prints the steps still to run and touches
no process.

Each step prints what to do in game, waits for `y`, and then:

1. reads the held stack back and asks you to confirm the count **off the in-game
   UI**. A disagreement between the two refuses the step — a baseline the tool
   cannot reconcile records nothing;
2. delivers exactly one grant through the ordinary delivery machine;
3. prints the request/result cells (`native_result`, `expected_before`,
   `expected_after`) and the held read-back after;
4. asks where the item went (`held` / `storage` / `both` / `?`), the held count,
   the storage-box count, and any note.

**An at-cap step is expected to end `failed`.** That is the observation, not a
malfunction: the held stack did not reach `expected_after` because the surplus
went to storage — precisely the shape clients#445 read as
`expected_after=5 actual=Some(20) native_result=1`.

### What to write down

For every step: the held count before and after **from the UI**, the storage-box
count for that item before and after, and where the item appeared. The tool
records what it can see; the storage box it cannot see at all.

### Skipping, stopping, resuming

At each step: `y` delivers, `s` skips it, `q` stops the pass. Resume state lives
in the **grant journal** (`.bb-native-grant-journal.json`), keyed by the step's
grant tag — the same store the `grant` subcommand's reused-tag gate reads, not a
parallel one. Re-run the same command and recorded steps are announced and
skipped. `--redo <step>` runs one again; `--only` / `--skip` select. The journal
is keyed by `--save-id`, so resuming against a different throwaway save correctly
runs everything.

Ctrl+C disarms the native request cell and journals the step as `interrupted`, so
it is offered again — **check in game whether the item arrived before resuming.**

## The report and the summary

Records append as JSON lines to `./bb-storage-probe.jsonl` (`--report` to move
it) in the operator's working directory. Nothing in the repo consumes it; it is
session evidence from one machine.

```
python -m tools.bb_native_delivery probe-storage --summary
```

renders a table of every recorded step and a verdict —
`supported` / `refuted` / `unclear` — for H1–H4 plus the lane correlation. An
`unclear` means a step was skipped or an answer was unreadable; it is a gap in
the session, not a weak result.

**Paste the summary into clients#445.**

## Where findings go

Into the issue, and into `research/runtime/ASSUMPTIONS.md` (assumption **A2**),
which is where the return-value semantics are recorded as `inferred` today.

Findings do **not** go into `research/runtime/bb-native-grant-contract.v5.json`.
The clients crate deserializes that file and guards it with
`Contract::assert_agrees_with_crate`; a semantic edit is a cross-repo step and
`tools/check_contract_drift.py` would red the PR that made it alone.
