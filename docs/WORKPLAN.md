# Work plan

Written 2026-08-18, after an audit of the 08-16/17 working tree and a subsequent adversarial
review. Every state claim below was verified by running the thing, not by reading it.

## Where the project actually is

| Piece | State |
| --- | --- |
| World generation | **Works.** AP 0.6.7 / Python 3.11, clean at `full`, `minimal`, enemizer on and off. |
| Item delivery | **Existing-stack and replay recovery work** through the v3 Cheat Engine bridge. Failed verification is bounded and a retained completed command survives a full restart without double-granting. The latest absent-stack Pebble canary failed safely and remains under investigation. |
| The AP client | **Crashes on every launch path** (#17). Whatever exercised delivery end to end did not go through `launch()`. |
| Item *randomisation* | **Does not exist.** Nothing suppresses the vanilla award, so shuffled keys gate nothing (#14). |
| Location detection | **Does not exist.** No flag-manager accessor. Checks are typed by hand (#15). |
| Enemizer planning | **Works.** 308 swaps of 4186 slots, deterministic across 25 seeds. |
| Enemizer writing | Guarded writer + packaging entrypoint exist. **Not playtested.** |

## The two blockers

An Archipelago game has to do two things: report what the player found, and make what it hands
back matter. Bloodborne currently does neither.

**#15 — detection.** Until the flag-manager accessor exists, checks are typed by hand.

**#14 — vanilla award suppression.** There is no `ItemLotParam` edit, no MSB treasure edit and no
runtime lot interception anywhere in the project. The player who walks to Iosefka's Clinic picks
up the real Cainhurst Summons, so every gate in `data.py` is satisfied by the vanilla copy no
matter where Archipelago put the shuffled one. Item placement is decorative.

These are independent, and only one of them needs the game running.

### On parallelising #15

An earlier draft of this plan said Lane B "cannot be parallelised — no contributor and no agent
can do it." That was too strong. Four separable activities were collapsed into one debugger
session:

1. **Candidate narrowing.** Lane A static EMEVD analysis. The corpus is mined and committed.
2. **Snapshot capture.** Already scripted; the owner's part is "restore save, do one action."
3. **Diff analysis.** Runs on `.bin` files anywhere.
4. **The write breakpoint.** The only owner-bound step — and even it is scriptable, since Cheat
   Engine's Lua API sets breakpoints and logs registers, which is what the delivery harness
   already does for a living.

The accurate claim: **#15 needs the owner's gameplay minutes, not the owner's engineering weeks**
— and no advance preparation is currently scheduled that would shorten those minutes. That prep
is Phase 0 work and it is the highest-leverage schedulable item in the project.

The owner's game time is also the contended resource: #15, the enemizer writer playtest, broader
item-class delivery validation, and the "does a native grant set acquisition flags" test all queue
on the same machine and the same person. #15 preempts.

---

## Phase 0 — cheap now, expensive later

Elden Ring lessons that cost real money to learn there. Ordered by how badly the cost curve bites.

### 0.1 Stable network IDs (#16)

Every item and location ID is `ID_BASE + enumerate(...)` position. Insert one row in `data.py`
and every later ID shifts while names stay valid — old multidata and older clients desync with no
error. `data.py`'s docstring promises the opposite; `docs/LOGIC-MODEL.md` promises an adapter that
derives IDs from stable keys, and the adapter derives them from order.

Both #1 and #14 grow the location list. A key-to-ID registry costs an hour today and is a
compatibility break after the first release. **This is the item on this list with the steepest
curve**, and an earlier draft ranked it below a changelog.

### 0.2 Build identity, on the surface a tester can read (#7, #8)

Elden Ring shipped `APWORLD_VERSION = "0.2.0"` across five distinct contract shapes, and two
builds of `v0.2.17` — one with a stall guard, one without, both reporting the same version and
both passing the compatibility check. A player on the wrong one was telling the truth.

Bloodborne is worse off: 43 `.CT` files named `-v2`, `-v3`, `-upgrade`, and no version anywhere
except `archipelago.json`. A tester who says "I loaded the auto-grant table" has told us nothing.

One version spanning apworld, client and harness; the client prints it on connect; the harness
writes its own version into the state file so the client can refuse a mismatch. #7 and #8 are one
change — the state-file handshake in #7 *is* #8's mechanism — and both belong before the first
external tester.

### 0.3 CI that asserts what it collected (#9)

No CI today. When it lands it must assert the **collected test count**, not just exit green.
Elden Ring's `ci-linux.sh` carried a WORLD gate that ran zero tests and reported success for
weeks. A gate that can pass while examining nothing is worse than no gate, because it retires the
question.

### 0.4 The witness ratchet, installed at 14 tests (#10)

`test_fixed_pickup_flags_cover_randomized_pickups` passes while the provenance it names is wrong
(#2), because it checks that six keys exist rather than that they mean anything. Elden Ring
reached 154 tests of that shape, at which point static classification of the backlog *failed* and
ranking them needed a bespoke tracing probe. A ceiling at 14 costs nothing.

### 0.5 Lane B session prep

Per the note above: candidate narrowing, an instrumented capture package, diff tooling, a scripted
breakpoint. Nothing here needs the game; all of it shortens the sessions that do.

### 0.6 CONTRIBUTING.md (#22)

Elden Ring's exists as an **external legibility asset** — a way to show someone why the bar is
where it is without relitigating it per pull request. It is also the only place that tells the
no-dump contributor population that it exists.

### 0.7 Release notes as part of the change (#11)

Every player-visible change lands its changelog line in the same commit. Elden Ring's blurb series
silently stopped for five releases; nobody decided to stop, the reconstruction cost just kept
rising until it was always tomorrow's job.

---

## Phase 1 — detection (#15)

`docs/EVENT-FLAG-RESEARCH.md` specifies the method well. Three things to hold onto:

- **The deliverable is the code path, not the bit.** One repeatable transition plus the instruction
  that writes it. A bit alone is a session that has to be redone.
- **A coincidence is not evidence.** A flag that changes *only* when you do the thing, survives
  reload, and has an identifiable writer is a finding. Skipping the control pair is how this goes
  wrong; Elden Ring lost a filed issue and a parked branch to exactly that.
- **The pointer trap.** The harness captures the inventory pointer at a hook (`mov
  [bbAutoInventory],r13`) and needs "use one bullet once after launch" to bootstrap — which is a
  confession that no static chain was ever found. If the flag manager lands the same way, automatic
  checks inherit a cave and a detour. EVENT-FLAG-RESEARCH requirement 6 is an acceptance criterion,
  not a finding.

**Detection has a second half that nothing currently owns: false-positive containment.**
`LocationChecks` cannot be retracted. A stale pointer after a save reload, a read during a loading
screen while the flag block is repopulating, or a read against the wrong character slot can each
mint irreversible false checks across an entire multiworld. Pointer revalidation per poll,
gameplay-state gating, N-consecutive-poll debounce and save-identity binding are part of this
phase, not an afterthought.

Also one live test to schedule while the debugger is out: **can the native grant path itself set
acquisition flags?** If it can, Archipelago deliveries self-report as checks.

## Phase 2 — make the randomiser a randomiser

**#14 first.** Suppressing the vanilla award is what makes a shuffled item matter. It is offline
file work through the same SoulsFormatsNEXT path the enemizer writer already proves out, needs no
live game, and is the largest contributor-shaped task in the project.

One constraint to design in: lot edits must preserve the acquisition-flag IDs in
`runtime_bindings.py`, or Phase 1's detection targets move underneath it.

**Then #1**, growing the pool. `research/catalog/fixed_location_catalog.tsv` holds 651 canonical
locations, 83 tagged `mvp_candidate`. Fill the nine empty regions first.

⚠️ **Phase 2 outruns the manual-check boundary.** Typing 20 location names works. Typing 83 does
not — and the catalog contains **no player-facing English names at all**, only flags, maps, lots,
Japanese event names and coordinates. Every seed Phase 2 produces is unplayable in practice until
Phase 1 lands. That is acceptable as prep work; it should not be mistaken for shippable progress.

One interim option worth evaluating rather than assuming away: for **unique goods**, the client
already knows what it delivered and the harness already walks the live inventory (`findItem`), so
"appeared in inventory and I didn't send it" is a serviceable monotonic signal for exactly the
key-item pool that makes up the MVP. `EVENT-FLAG-RESEARCH.md` dismisses inventory presence for the
general case, correctly — but the degenerate case is the current pool.

## Phase 3 — enemizer to shippable

#3: 308 of 4186 slots, with `entity ID referenced by area EMEVD` protecting 2399. That rule is a
bare numeric grep over decompiled script text, so it also catches lot IDs, region IDs and numbers
in comments — 259 of 1979 eligible slots have entity IDs that collide numerically with
`ItemLotParam` IDs. The refinement may be less "classify usage" than "stop counting collisions."

**Needs the writer playtested first.** A wrong swap that crashes a map load is worse than a
conservative one, and no oracle short of the game detects it — the 25-seed audit pins determinism,
not safety.

---

## What Elden Ring learned that transfers

| Lesson | Where it bites here |
| --- | --- |
| A version number cannot identify a build | 43 unversioned `.CT` files (#7) |
| If the contract changes, the version changes | The `GRANT` command wire (#8) |
| A gate can pass while examining nothing | No CI yet; assert the collected count (#9) |
| A guard its subject cannot witness | #2's coverage test (#10) |
| A gate that greps reads comments too | The enemizer's EMEVD protection rule (#3) |
| A coincidence is not evidence | The whole of Phase 1 |
| Establish the base before comparing derived numbers | Flag snapshot diffing needs its control pair |
| Cite the source or probe it — no invented IDs | #2, and every future flag |
| A census column is not a population | 614 of 651 acquisition flags appear in no script |
| Claim the issue before you branch | Two agents plus a maintainer on one queue (#22) |
| A corpus ledger is a regression ratchet, not a correctness one | The enemizer's 308 pin (#3) |

## Owned by nobody yet

Named so they stop being invisible. None of these has an issue or a phase:

- **Save-restore and character-slot reconciliation.** The delivery receipt is keyed
  `seed_name:slot` only. A restored BBLauncher backup rolls inventory back while the receipt says
  delivered, and the items are gone. A second character in the same slot inherits the first one's
  queue.
- **Goal design and detection.** The goal currently fires when a human types `/check Mergo's Wet
  Nurse`. `docs/LOGIC-MODEL.md` question 5 is open, and no boss flag is in `LOCATION_BINDINGS`.
- **DeathLink.** Receiving is already technically possible via the validated HP write. Sending
  needs a death signal — another Phase 1-class find, worth adding to the discovery tranche while
  the methodology is out anyway.
- **Location naming as a permanent contract.** Names are datapackage-facing and effectively frozen
  at first release. The catalog has none to freeze.
- **Client lifecycle around the emulator.** Re-attach and re-inject after a shadPS4 restart, and
  the "use one consumable per launch" bootstrap — currently folklore in a status string.

## Deliberately out of scope

Chalice Dungeons, the three endings as selectable goals, cross-serial support beyond the two
`01.09` builds already reproduced, and regulation/param editing in the enemizer.
