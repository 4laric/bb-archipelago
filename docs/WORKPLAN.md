# Work plan

> **2026-08-20 handoff update:** the generated world is bounded to 51
> Central Yharnam pickups plus Cleric Beast and Father Gascoigne. The complete
> 54-row suppression binder is installed and live-tested. The unsafe MVP client
> automatically reported three pickups and delivered their rewards in AP index
> order. The varied pool now covers five goods shapes, Augur, and Saw Spear.
> Historical phase text below explains how the project reached this point and
> is not a current blocker list. See `HANDOFF.md` and `VERTICAL-SLICE.md` for
> current truth.

Written 2026-08-18, after an audit of the 08-16/17 working tree and a subsequent adversarial
review. Every state claim below was verified by running the thing, not by reading it.

Updated 2026-08-19 for the overnight session: the event-flag manager read path is validated, the
absent-item grant is fixed, and one build string now spans every artifact. Phase 0.2 and 0.5 are
closed; Phase 1's remaining work is the client half, not the discovery half.

## Where the project actually is

| Piece | State |
| --- | --- |
| World generation | **Works.** AP 0.6.7; 53 locations and a seven-item-type varied pool generate successfully. |
| Item delivery | **Absent-stack, existing-stack, equipment insertion, and replay recovery work** through the v5 Cheat Engine bridge. Category-4 goods use the validated 24-byte in-frame descriptor; category-0 equipment uses the persistent 24-byte descriptor. A Saw Spear grant completed through native `ItemGrant` and was confirmed in inventory. Failed verification is bounded, and a retained completed command survives a full restart without double-granting. |
| The AP client | **Works in bounded unsafe MVP mode.** `--assume-correct-save` connected, reported three live pickups automatically, and drove ordered reward delivery. Normal live mode still fails closed without real save identity. |
| Item *randomisation* | **Works for the slice.** The installed 54-edit binder replaces each pickup's vanilla award with one Vial while retaining its check flag. |
| Location detection | **Automatic pickup reporting works.** The manager-relative reader, three-read gameplay gate, debounce, and `LocationChecks` send are live-validated. Boss flags and `CLIENT_GOAL` still need the completion run. |
| Enemizer planning | **Works.** 308 swaps of 4186 slots, deterministic across 25 seeds. |
| Enemizer writing | Guarded writer + packaging entrypoint exist. **Not playtested.** |

## Historical blockers (now retired or mitigated)

An Archipelago game has to report what the player found and make received items
matter. The slice now does both; this section records the investigation that
produced the current implementation.

**#15 — detection.** The accessor now exists: a validated, signature-gated, manager-relative read
path that survives a randomized eboot base. The poll loop exists too — in
`from-software-archipelago-clients`, `crates/bb-archipelago/src/client_loop.rs`. It now requires a
backend-provided gameplay/save context, matches that identity to explicit configuration and
debounces true reads. The unsafe MVP backend now substitutes explicit operator attestation and a
three-read manager-health gate. Real save identity remains a release-safety task, not a vertical-
slice blocker.

**#14 — vanilla award suppression.** Retired for the slice. The guarded 54-edit
ItemLotParam binder is installed and live-tested; physical checks retain their
flags and award the one-Vial placeholder instead of their original contents.

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

**Settled 2026-08-19.** The discovery session ran on 08-18 and cost gameplay minutes, as predicted.
All four activities happened: candidates narrowed statically, a save-restored before/after replay
captured, the diff intersected, and the write breakpoint scripted in Cheat Engine Lua. The write
proved divisor-1000 grouping with MSB-first packing, and the manager turned out to hang off a
static eboot-relative slot rather than a hooked register. The owner's queue is therefore free for
the enemizer writer playtest and the native-grant-sets-flags test; #15 no longer preempts, because
what remains of it needs no game running.

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

**Done 2026-08-19 across both repositories.** `bb-0.1.0-r5` is stamped across the apworld, both
clients, the Cheat Engine table and the PS1 helper; the harness identifies itself as
`bb-native-grant-v5` over the `BBGRANT1` wire contract, and either client refuses a different or
missing version. `tests/test_grant_harness_contract.py` asserts this repository's stamps, and the
Rust bridge tests assert the native client's expected build, protocol and harness. Release work
must still update both repositories together because neither CI checkout contains the other.

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

**Done, and it paid.** The kit went in on 08-18 and the session it was built for closed the read
path the same night. Keep the pattern for DeathLink's send signal and the boss-flag hunt, which are
the same shape of problem.

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

**The discovery half is done (2026-08-18).** `docs/EVENT-FLAG-RESEARCH.md` records the layout:
flag ID divided by 1000 selects the group, the remainder indexes a bank with MSB-first bit packing,
the manager hangs off eboot `RVA 0x553B100` on CUSA03173 `01.09`, and the inlined setter write at
`RVA 0x17D6EFA` is the version gate. Three things that shaped it, kept because the next hunt needs
them:

- **The deliverable is the code path, not the bit.** One repeatable transition plus the instruction
  that writes it. A bit alone is a session that has to be redone. This is what made the resolver
  generic instead of a hardcoded address for one Bullet lot.
- **A coincidence is not evidence.** A flag that changes *only* when you do the thing, survives
  reload, and has an identifiable writer is a finding. Skipping the control pair is how this goes
  wrong; Elden Ring lost a filed issue and a parked branch to exactly that.
- **The pointer trap did not spring.** The harness captures the inventory pointer at a hook (`mov
  [bbAutoInventory],r13`) and needs "use one bullet once after launch" to bootstrap, so the fear was
  that the flag manager would land the same way and drag a cave and a detour behind it. It did not:
  the manager is reachable from a static eboot-relative slot, and a reader outside Cheat Engine
  resolved it after the base moved from `0x05660000` to `0x057C0000`. EVENT-FLAG-RESEARCH
  requirement 6 wants manager-relative addressing on **both** supported builds; CUSA03173 `01.09`
  has it, CUSA00900 is untested. Do not let the second serial go unclaimed by default.

**Detection's second half is now the whole of the phase: validated live context.**
`LocationChecks` cannot be retracted. A stale pointer after a save reload, a read during a loading
screen while the flag block is repopulating, or a read against the wrong character slot can each
mint irreversible false checks across an entire multiworld. Pointer revalidation per poll,
gameplay-state gating, N-consecutive-poll debounce and save-identity binding are part of this
phase, not an afterthought.

Audited against `crates/bb-archipelago` as it stands, of those four:

| Guard | State in the Rust client |
| --- | --- |
| Pointer revalidation per poll | **Present.** `read()` re-reads the manager pointer every call rather than caching it, and `read_resilient` reattaches on error. |
| Gameplay-state gating | **Contract present, live source absent.** `poll_locations` abstains unless `gameplay_ready`; the v0.18 backend returns no context, so live sends remain disarmed. |
| N-consecutive-poll debounce | **Present.** The default is three consecutive true reads and false/unavailable reads reset the streak. |
| Save-identity binding | **Contract present, live source absent.** The polled identity must equal `expected_save_identity`; the v0.18 backend cannot resolve one yet and therefore abstains. |

`read_resilient` stays behind that context gate. Reattaching and retrying converts a failed read
into a fresh read; that is right for a restarted emulator and wrong for a read that failed because
the game is mid-transition. The live backend therefore abstains before calling it until gameplay
state can be proven. Abstaining is always safe here; guessing is never.

Also one live test, now cheap: **can the native grant path itself set acquisition flags?** If it
can, Archipelago deliveries self-report as checks. The validated reader answers this in one
grant — read the item's acquisition flag before and after — with no debugger session required.

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
| A version number cannot identify a build | Was 43 unversioned `.CT` files; the grant table now self-identifies (#7 closed). The research and debug tables still do not. |
| If the contract changes, the version changes | The `GRANT` command wire, now `BBGRANT1` and refused on mismatch (#8 closed) |
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
