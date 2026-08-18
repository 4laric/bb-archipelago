# Work plan

Written 2026-08-18, after an audit of the 08-16/17 working tree. Every state claim below was
verified by running the thing, not by reading it.

## Where the project actually is

| Piece | State |
| --- | --- |
| World generation | **Works.** AP 0.6.7 / Python 3.11, clean at `full`, `minimal`, enemizer on and off. |
| Item delivery | **Works.** Native game-thread grant, absent-item insertion, persistence across a full emulator restart. |
| Enemizer planning | **Works.** Consumes the AP request, 308 swaps of 4186 slots, deterministic across 25 seeds. |
| Enemizer writing | Guarded writer + packaging entrypoint exist. Not playtested. |
| Location detection | **Does not exist.** No flag-manager accessor. Checks are typed by hand. |

## The one blocker

Everything else is polish next to this: **the client cannot tell when a player has done something.**
`docs/EVENT-FLAG-RESEARCH.md` Lane B is the whole game. Until it lands, Bloodborne is an
Archipelago *item receiver*, not an Archipelago *game* — it can take deliveries but it cannot
participate.

Two properties of that work shape this plan:

1. **It cannot be parallelised.** It needs the game running under a debugger on the machine that
   owns the dump. No contributor and no agent can do it.
2. **The manual `/check` boundary is a real unlock, not a placeholder.** Because a human can report
   a check by typing, the entire logic model, item placement, and enemizer can be playtested
   *today*, with Lane B still open. That is unusual and worth exploiting.

So: Lane B is the critical path and it belongs to one person. Everything in Phase 0 and Phase 2
runs beside it and does not wait on it.

---

## Phase 0 — cheap now, expensive later

These are the Elden Ring lessons that cost real money to learn there. Every one of them is
approximately free today and approximately unfixable once a tester is running an unknown build.
None of them should wait for Lane B.

### 0.1 Build identity, on the surface a tester can read

ER's most expensive single lesson: `APWORLD_VERSION = "0.2.0"` shipped **five distinct contract
shapes**, and a player on the wrong one is telling the truth when they say "I'm on the new version."
The fix there was to put the git SHA on the overlay — the surface the player photographs — rather
than in a log they can't produce.

Bloodborne is worse off than ER was. The harness is 43 loose `.CT` files with names like
`Bloodborne-native-item-grant-auto-v2.CT` and `...-v2-upgrade.CT`. There is no version anywhere
except `archipelago.json`'s `world_version`. A tester who says "I loaded the auto-grant table" has
told you almost nothing, and no amount of later work recovers which bytes were in memory.

The rule to adopt now: **one version string spans the world, the client and the harness, and the
client prints it on connect.** A report that cannot name its build is not a report.

### 0.2 A version on the command wire

`client.py` writes `GRANT 0x… 0x… 1 AUTO <tag>` into a text file that a Cheat Engine script parses.
That is a protocol between two independently-updated artefacts, with no version field. ER hit this
exact class and answered it with `CONTRACT_HASH` and the house rule *if the contract changes, the
release version changes with it*.

Add a version token to the command line before anyone else is running it. The cost now is one
token; the cost later is a silent mismatch that looks like a game bug.

### 0.3 CI, and a gate that proves it ran something

There is no CI. When it goes in, it must **assert the collected test count**, not just a green exit.
ER's `ci-linux.sh` had a WORLD gate that ran zero tests and reported success for weeks; the
diagnostic that eventually cracked a related problem was noticing that collected counts differed
between two environments. A gate that can pass while examining nothing is worse than no gate,
because it retires the question.

Minimum useful CI: install the world into a pinned AP checkout, run the 14 tests, assert the count,
generate the three tester seeds, and fail on a `FillError` or a stack trace.

### 0.4 The witness ratchet, installed at 14 tests

ER reached **154 tests that assert an empty result without proving they examined anything**, and
ranking them needed a bespoke `sys.settrace` probe. Issue #2 is already one of these:
`test_fixed_pickup_flags_cover_randomized_pickups` passes while the provenance it names is wrong,
because it checks that six keys exist rather than that they mean what they claim.

A ceiling costs nothing to install at 14 tests and cannot be retrofitted cheaply at 154.

### 0.5 Release notes as part of the change

ER's rule 14: *every player-visible change lands its changelog line in the same commit.* It exists
because the blurb series silently stopped for five releases — nobody decided to stop, the
reconstruction cost just kept rising until it was always tomorrow's job. Start the changelog at
v0.1.0 while there is nothing to reconstruct.

### 0.6 CONTRIBUTING.md

ER's exists primarily as an **external legibility asset** — a way to show someone else why the bar
is where it is, without relitigating it per pull request. That is exactly the need that appears the
moment a second person touches this.

---

## Phase 1 — Lane B: the flag-manager accessor

`docs/EVENT-FLAG-RESEARCH.md` already specifies this well: control snapshots, three repeats from the
same pre-action save, intersect survivors, then a write breakpoint to catch the setter. Two additions
from the Elden Ring experience:

- **The deliverable is the code path, not the bit.** The doc says this already; it is worth
  restating because the temptation at the moment a bit is found is enormous. One repeatable bit
  plus the instruction that writes it is success. A bit alone is a session that has to be redone.
- **A coincidence is not evidence, and sufficient is not necessary.** A flag that changes when you
  do the thing is a candidate. A flag that changes *only* when you do the thing, survives reload,
  and is written by an identifiable instruction is a finding. Elden Ring lost a filed issue and a
  parked branch to skipping the control row.

Once the accessor exists, the six statically-mapped pickups in `runtime_bindings.py` become the
first automatic checks, and the manual `/check` path stays as the fallback.

## Phase 2 — a seed worth playing

Issue #1: the critical path currently requires **zero** shuffled items, and 9 of 25 regions hold no
checks. Twenty locations is not yet a multiworld contribution.

The growth path is already mined and committed: `research/catalog/fixed_location_catalog.tsv` holds
**651 canonical locations**, of which **83** are already tagged `mvp_candidate`. This is the largest
piece of work in the project that needs **no game access at all** — which makes it the natural place
for a contributor, and the natural thing to do while Lane B is blocked.

Order: fill the empty regions first (Cathedral Ward, Hemwick, Cainhurst, the Lecture Buildings, the
Frontier), because that is what turns four dead progression items into real gates. Then breadth.

## Phase 3 — enemizer to shippable

Issue #3: 308 of 4186 slots, with a single rule — *entity ID appears in the area's EMEVD* —
protecting 2399 of them. Splitting that bucket by **how** the ID is used is the highest-leverage
change available, and it is measurable against a fixed 308 baseline. Needs the writer playtested
first; a wrong swap that crashes a map is worse than a conservative one.

---

## What Elden Ring learned that transfers

| Lesson | Where it bites here |
| --- | --- |
| A version number cannot identify a build | 43 unversioned `.CT` files (0.1) |
| If the contract changes, the version changes | The `GRANT` command wire (0.2) |
| A gate can pass while examining nothing | No CI yet; assert the collected count (0.3) |
| A guard its subject cannot witness | Issue #2's coverage test (0.4) |
| Release notes are part of the change | No changelog yet (0.5) |
| A coincidence is not evidence | The whole of Lane B (Phase 1) |
| Establish the base before comparing derived numbers | Flag snapshot diffing needs its control pair |
| Don't use CI as a test runner | The suite runs locally in under a second |
| Cite the source or probe it — no invented IDs | Issue #2, and every future flag |
| A census column is not a population | 614 of 651 acquisition flags appear in no script |

## What is deliberately not in scope yet

Chalice Dungeons, the three endings as selectable goals, cross-serial support beyond the two
`01.09` builds already reproduced, and any regulation/param editing in the enemizer. Each is a real
feature; none of them is on the path to the first playable multiworld.
