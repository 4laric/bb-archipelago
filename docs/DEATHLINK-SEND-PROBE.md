# Live probe: validating the outbound DeathLink signal

Issue #78 (client) and #383 (grace). This is the session that decides whether
the client's inferred local-death signal is real. Read
[CONTRIBUTING-LIVE-PROBES.md](CONTRIBUTING-LIVE-PROBES.md) first; this document
is the request that document demands, filled in.

[SESSION-death-signal.md](SESSION-death-signal.md) narrowed the candidates and
ruled out an event flag outright. The client now implements **candidate class
1, "HP at zero"**, and everything below is about that one candidate.

## What is implemented, and what it is not

The client reads the player's current HP from the same cell the incoming
DeathLink kill already writes through, and reports a death on an **alive->dead
edge**:

- two consecutive polls at HP > 0 arm it, two consecutive polls at HP == 0 fire
  it, so a single torn read is not a death;
- an unobservable poll (no captured player pointer, or the client's own
  gameplay gate refusing) resets it to "nothing known", so a load, a menu, a
  quit-to-title and an out-of-world stretch cannot produce an edge;
- loading straight into a save that reads zero produces no edge, because only
  alive->dead fires -- unknown->dead is absorbed;
- a death caused by an **incoming** DeathLink is attributed to this client and
  suppressed, so a received death cannot echo back out.

This was `inferred` in the baseline's vocabulary when the probe was written.
As of **2026-09-08 it is `observed` for the positive half only** (see *Results
so far* below): an ordinary death does produce the edge and does reach the
multiworld. The negative half -- that nothing else produces the edge -- is
still `inferred`, and it is the half that decides whether players can be told
to turn sending on. The session below still needs running.

## Results so far

**2026-09-08**, launcher `v0.1.0.1` with client `bb-0.1.0.0`, ordinary
multiworld session (not the scripted probe run), reported by Oz on Discord.
Seed rolled with `death_link: true` and `death_link_send: true`.

- **Step 1, ordinary death: CONFIRMED, TRUE column.** A real player death was
  detected by the HP-edge detector and broadcast; another player in the
  multiworld observed the arrival. The instrument sees the death it is meant
  to see, and the send path end-to-end works.
- **Every other row remains open.** Steps 2--9 were not exercised: no incoming
  echo suppression check, no quit-to-title, no lamp warp, no send-disabled
  gating, no first-death grace, no amnesty cadence. This was not a controlled
  run -- there were no `mark` labels and no console transcript -- so it is a
  single observation, not the session. The step 0 positive control was not run
  either.
- Because the false-positive rows are untouched, the detector is **not**
  promoted to `validated` and `death_link_send` stays experimental. Run the
  script below as written.

### Open: an incoming DeathLink that did not arrive

In the same session, a Balatro slot in the same multiworld ended a run and no
DeathLink visibly arrived in Bloodborne. This is recorded as an open
observation, not a receive regression -- receive is unchanged and was working
in earlier betas.

**Question to answer before treating it as a fault:** did the sender actually
broadcast? A manually ended Balatro run may not emit a DeathLink at all. Check
the Bloodborne client console for a `DeathLink received from <slot>` line: if
that line is present, the arrival happened and the failure is in-game
application (a real bug); if it is absent, check the Archipelago server log or
the other slot's client for an outgoing DeathLink before blaming this client.
Step 0 of the script below is the controlled version of this same test.

## Cost and decision

Fifteen minutes. No restarts beyond the deaths themselves. A throwaway or
backed-up save, because the script deliberately kills the character several
times. **Decision it settles:** whether `death_link_send` can ever be
recommended to players, or whether the HP candidate is dead and the session kit
in `SESSION-death-signal.md` has to run its memory hunt after all.

## Why existing data cannot answer it

No bundle in this repo contains a player-HP time series across a death. The
`SESSION-death-signal.md` kit was written to *produce* one and has not been
run; the storage-routing and popup bundles never sampled HP. There is nothing
to reread.

## Setup

1. Roll a seed with `death_link: true`, **`death_link_send: false`**, and
   `death_link_amnesty: 0`. Sending stays off for the whole first half: the
   client still prints every observation, which is exactly what is being
   validated, and nothing reaches the multiworld while the instrument is
   unproven.
2. Have a second slot in the same multiworld with DeathLink on, to send from
   and to receive at. Any game.
3. Keep the client console visible. Every line this probe reads begins
   `DeathLink probe:`.
4. Label each step with the client's `mark` console command, typed immediately
   *before* you act, exactly as
   [CONTRIBUTING-LIVE-PROBES.md](CONTRIBUTING-LIVE-PROBES.md) rule 3 requires.
   Five seconds of quiet either side of every step. Wall-clock recollection is
   not a label.

Type `deathlink` at the client console at any point to see what the seed
actually armed.

## Step 0 -- the positive control

**Do this first, and stop if it fails.** The instrument here is the HP read,
and the one death this client can already cause on demand is an incoming
DeathLink kill, so that is the control: a known, planted death whose expected
record is fixed in advance.

1. `mark control-incoming-kill`
2. Stand still, alive, in a safe spot with control of the character.
3. Have the other slot die, sending a DeathLink.

**Pass condition:** the console prints `DeathLink received from <slot>` and
then, within a second,
`DeathLink probe: death_observed suppressed_echo`.

That single pair proves three things at once: the HP cell is readable in this
session, the detector sees an alive->dead edge on it, and echo suppression
works. If the kill lands (the character dies on screen) but no
`death_observed` line appears, **the probe is broken** -- the detector cannot
see the same death the writer just caused -- and the session ends here as a
probe defect, not as a data point about Bloodborne deaths.

If `DeathLink received` never appears at all, that is the pre-existing receive
path failing, not this probe; fix that first.

## Pre-registered predictions

The hypothesis, in one sentence: **an ordinary player death produces exactly
one alive->dead HP edge, and nothing else the player does produces one.**

| step | if the hypothesis is TRUE | if it is FALSE | if the PROBE is broken |
| --- | --- | --- | --- |
| 1. Ordinary death **(CONFIRMED 2026-09-08)** | exactly one `death_observed` line, within ~1s of the YOU DIED screen | zero lines, or two or more for one death | step 0 already failed; or lines appear with no death at all |
| 2. Death by incoming DeathLink | exactly one, `suppressed_echo` | one line WITHOUT `suppressed_echo` (echo would be broadcast) | no line at all |
| 3. Quit to title while alive, reload | no lines at all | any `death_observed` line | -- |
| 4. Lamp warp / load screen while alive | no lines at all | any `death_observed` line | -- |
| 5. Death while sending is off | `death_observed send_disabled` | `sent`, or a `graced`/`amnesty` line (durable state must not move while gated off) | no line |
| 6. First death with grace on | `death_observed graced` | `sent` on the first death | no line |
| 7. Second death with grace on, amnesty 1 | `death_observed amnesty 1/1` | `graced` again, or `sent` | no line |
| 8. Third death, amnesty 1 | `death_observed sent` | anything else | no line |

A result matching none of the three columns is a probe defect and voids the
session. In particular, a `death_observed` line during a **loading screen** is
neither "true" nor "false": it is the gate failing, and it is reported as such.

## The script

Steps 1--5 run with `death_link_send: false`. Nothing is broadcast and nothing
is persisted; you are reading console lines only.

1. `mark ordinary-death-1` -- die to an ordinary enemy in Central Yharnam.
   Respawn at the lamp, regain control.
2. `mark ordinary-death-2` -- die the same way again. (Two, because "fires once
   per death" is not observable from one.)
3. `mark incoming-kill` -- have the other slot die. Repeat of step 0, now with
   the marks in the stream.
4. `mark quit-to-title` -- quit to title while alive, reload the save, regain
   control. Wait ten seconds.
5. `mark lamp-warp` -- warp lamp to lamp without dying. Wait ten seconds.

**Stop here if any of steps 1--5 contradicted the table.** The remaining steps
only mean anything if the signal itself held.

Now reroll (or re-edit the slot data) with **`death_link_send: true`**,
`death_link_first_death_grace: true`, `death_link_amnesty: 1`, and a fresh
ledger, and watch the other slot for arrivals:

6. `mark grace-death` -- die. Expect `graced`, and **no** arrival at the other
   slot.
7. `mark amnesty-death` -- die. Expect `amnesty 1/1`, and no arrival.
8. `mark send-death` -- die. Expect `sent`, and an arrival at the other slot.
9. `mark reconnect` -- close the client, reopen it, reconnect, die once. Expect
   `amnesty 1/1` (the cycle reset when it sent) and **never** `graced` again:
   the grace is spent for this slot forever.

## Reporting

Paste the console lines with their `mark` labels, in order, plus the eboot base
and client build hash the session header prints. Then say which of the three
columns each step landed in.

Row 1 landed in the TRUE column on 2026-09-08 outside a controlled run; the
other seven rows are still open, so the session below is still owed in full.

- All eight rows in the TRUE column: the signal is promoted from `inferred` to
  **validated**, `death_link_send` can be documented as working (still
  experimental), and #78 closes.
- Any row in the FALSE column: the HP candidate is disproved. Say which row.
  Per the baseline, a disproved classifier is removed rather than narrowed --
  the detector comes out of the client and `SESSION-death-signal.md`'s memory
  hunt runs.
- Anything else: probe defect. Name what was inconsistent; the next build
  changes one thing.

Retractions follow the baseline's rules: a new comment beginning "retracts",
linked from the original.
