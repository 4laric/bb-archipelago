# Contributing live probes and playtest requests

This is the contributor contract for any work that asks an operator to run the
game: runtime probes, capture hooks, direct native calls, and the playtest
sessions that exercise them. It exists because #214 burned five playtests on
probes that did not capture what they were built to capture, each time followed
by "fixed, it will work on the next one". It applies to every `needs-game`
issue, not only category 8.

Read [CONTRIBUTING.md](../CONTRIBUTING.md) and
[RESEARCH-BASELINE.md](RESEARCH-BASELINE.md) first. This document adds rules;
it does not relax any.

## The rule in one sentence

**A probe that has not already captured a known, planted event is not ready to
be pointed at an unknown one.** Operator time is spent only on questions, never
on finding out whether the instrument works.

## What went wrong, so the rules make sense

Each rule below blocks one of these. They are all from #214 between
2026-08-29 and 2026-09-02.

| what was claimed | what was true | cost |
| --- | --- | --- |
| Four inventory rows are natural blood gems (runtime-id prefix classifier) | They were armor. The classifier had never been checked against a labeled item. | one capture bundle, two comments, one retraction |
| No gem was acquired during the session | Several were. The scanner diffed the ordinary held-inventory geometry, which gems do not use. | one session; "absence" reported as a fact |
| Sequence gaps were sampler loss | Correct, but the single mailbox meant the lost call could never be recovered, so the whole bundle was uninformative. | one session |
| `caller=0`, sequence-64 records are game evidence | The probe had failed to install and the reader ran anyway. | analysis time; noise in the record |
| Sequence 65 is a natural Blood Gem, sequence 71 is the rune Lake | Both were the AP client's own armor and weapon deliveries, 12 ms and 13 ms earlier in the delivery log, caller RVA inside the AP cave. The reanalysis also used the wrong eboot base. | a comment full of conclusions, then a full retraction |
| `+0x1A87590` is a callable four-argument constructor | The entry capture showed argument values, not a contract. Two direct calls crashed shadPS4 before returning. | two crashes on the throwaway save, and the lane is now closed |

The common factor: the instrument was trusted before it had been tested, and
the analyst confirmed the hypothesis instead of trying to break it.

## Before you ask for a playtest

A request for operator time is a pull request or an issue comment containing
all of the following. If any is missing the request is not ready and the
operator should decline it.

### 1. A positive control the probe has already passed

State the known event the probe captured, with the record it produced, before
the session was requested. Acceptable controls:

- the client's own delivery of a known item, which the hook must record with
  the expected id, quantity, and a caller RVA inside the AP cave;
- a vanilla action the operator can perform on demand with a known result
  (desocketing an existing gem, buying a Blood Vial);
- a record from a previous bundle that the new build re-reads identically.

If nobody on the development side can run the game, the first minutes of the
operator's session are the control, scripted as step 0 with a written pass
condition. If step 0 fails the session ends there and the outcome is
"probe defect", not a data point. Do not continue into the real test hoping
the failure was incidental.

### 2. A pre-registered prediction

Write down, before the run:

- the hypothesis, in one sentence;
- what the capture looks like if the hypothesis is true;
- what it looks like if the hypothesis is false;
- what it looks like if **the probe is broken**, and how that is
  distinguishable from "false".

If the third case is not distinguishable from the second, the probe cannot
support an absence claim and the request must say so. A result that matches
none of the three is a probe defect and voids the session.

### 3. A labeled-acquisition script for the operator

The operator gets a numbered list of actions with a label for each, and the
client provides a way to stamp that label into the capture stream at the moment
it happens (a console command, a hotkey, anything that writes to the same
`.jsonl` with the same clock). Wall-clock recollection after the fact is not a
label. Unlabeled acquisitions are not witnesses and cannot become witnesses
later by reasoning about timestamps.

Each labeled step states the wait before and after it. Five seconds of quiet
on either side has been enough to separate events so far.

### 4. The cost and the decision

One line each: how many minutes of operator time, how many restarts, whether a
throwaway save is required, and what decision the result will settle. If the
result would not change what gets built next, do not run it.

### 5. Why existing data cannot answer it

Every bundle already captured is listed in the issue. Before requesting a new
capture, say which existing bundle you checked and why it is insufficient. The
#330 design was reached by rereading PT32 and PT35 rather than by a sixth
probe; that should be the default path.

## Rules for the probe itself

### Install gating

Readers do not run unless installation reported success. A failed install
produces zero records and one clearly labeled `probe_install_failed` entry with
the reason. The bundle header carries the install status, the client build
hash, the image hash, and the eboot base for that session. Any analysis that
does not restate the eboot base it used is not reviewable.

### Attribution on every record

Each captured record carries at minimum:

- caller RVA (relative, computed with the session's base, not an absolute
  address);
- `origin`: `ap_delivery` when the caller is inside the AP cave or the record
  matches a delivery-diagnostics entry within a short window, otherwise `game`;
- a monotonic sequence number and the count of missed calls since the
  previous sample.

A record with `origin = ap_delivery` is excluded from natural-witness analysis
before anything else is done. Cross-check candidate natural witnesses against
`delivery-diagnostics.jsonl` first, every time, even when the operator's
recollection makes the natural explanation plausible. That check would have
prevented the seq-65/seq-71 retraction in ten minutes.

### No lossy buffers

A hook that can drop a call must record that it dropped one. A single mailbox
is not acceptable for any call site that can fire twice within a sampling
interval. Ring size and overwrite policy are stated in the pull request.

### Classifiers are hypotheses

A rule of the form "ids with prefix X are class Y" is `inferred` until it is
checked against at least one labeled item of class Y and one labeled item that
is not. Once a classifier is disproved it is removed from the client, not
narrowed. Do not admit a category by prefix.

### Observation before mutation

Entry captures show what values arguments held. They do not show what the
callee requires. Before any direct call into game code from the cave:

1. static xref enumeration of the callee, committed to the issue or to
   `RESEARCH-BASELINE.md`;
2. the prologue and every register and stack slot the callee reads before its
   first store, from this exact image;
3. for every pointer argument, the memory it dereferences, transitively, to
   the depth the callee reaches before returning;
4. a construct-only stage that touches no inventory, with a readback of the
   returned object, before any insertion stage.

If the call crashes the emulator, that is a failed prediction. Record which
of the four items above was wrong. A second attempt without a new static
finding is not permitted; the lane goes back to static analysis or is closed,
as #214 did.

## Reading and reporting a bundle

### The three words

Use exactly these, as in the baseline, and do not upgrade without the stated
evidence:

- **candidate**: a record consistent with the hypothesis, not yet correlated
  with a labeled action and not yet checked against the AP delivery log;
- **witness**: a candidate that is correlated with a labeled operator action,
  is not attributable to the AP client, and whose probe passed its positive
  control in the same session;
- **validated**: a witness that survived the controls the issue's acceptance
  criteria specify (save and reload, equip or imprint, negative controls).

The PT32 Communion record is the standard: labeled on screen by the operator,
readback matches, decoded fields match the catalog, not attributable to AP.

### Absence claims

"No X was observed" may be reported only when all of:

- the operator's labeled script confirms X was performed;
- the sequence numbers around that label are continuous with zero missed
  calls;
- the same hook captured its positive control in the same session.

Otherwise the report says "diagnostic miss" and names which of the three
failed. The 2026-08-31 correction ("the absence is a diagnostic miss, not
absence of acquisition") is the wording to copy.

### One change per rebuild

When a session fails, the next build changes one thing, and the request for the
next session lists the diff between the two client hashes. "Rewrote the
capture path" is not one thing. If a rebuild needs more than one change, the
first session with the new build is a control-only session.

### Retractions

A claim that turns out to be wrong is retracted in a new comment that links the
retracted one, says "retracts" in the first line, and states what remains
valid. Edit the original to add a pointer to the retraction. Update
`RESEARCH-BASELINE.md` in the same day. Silent narrowing ("the four rows are
now understood as armor") without the word "retracts" is how the same claim
gets cited again a week later.

## Checklist

Copy this into the request comment and tick it:

```
- [ ] positive control passed on build <hash>; record: <paste>
- [ ] prediction written: true / false / probe-broken all distinguishable
- [ ] labeled script with in-stream markers; waits stated
- [ ] cost: <minutes>, restarts: <n>, throwaway save: yes/no
- [ ] decision this settles: <one line>
- [ ] existing bundles checked: <list>; why insufficient: <one line>
- [ ] install gating and origin classification present in the build
- [ ] (direct calls only) static ABI writeup linked; construct-only stage first
```

Operators: if the checklist is not there, ask for it before launching. A
session run without it produces a bundle nobody can interpret, and you will be
asked to run it again.
