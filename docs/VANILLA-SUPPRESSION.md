# Suppressing the vanilla item award

Status: native binder writer implemented and round-tripped; installation and
in-game canary validation remain pending.

## The problem

Archipelago shuffles Bloodborne's key items, and nothing stops the game handing
you the original one where it has always been. Walk into Iosefka's Clinic and
you pick up the real Cainhurst Summons. Every gate in `worlds/bloodborne/data.py`
— `Rule.all("cainhurst_summons")`, `upper_cathedral_key`, `laurences_skull` — is
satisfied by the vanilla copy regardless of where the shuffled one went.

**The world is a check emitter and an item receiver. The shuffle currently
decides nothing.** That is the item-randomisation half of a randomiser, and it
was missing from the project entirely.

## Suppress at the lot, not at the placement

The obvious move is to edit the thing holding the item — the MSB treasure Part,
or the NpcParam drop table. That is the wrong layer, for two reasons that were
measured rather than assumed.

### 1. The acquisition flag belongs to the lot

Across all 8,888 rows of `research/joined/lot_items.tsv`, the number of lots
carrying more than one distinct acquisition flag is **zero**. The flag is a
property of the `ItemLotParam` row.

Those flags are the detection targets recorded in
`worlds/bloodborne/runtime_bindings.py`. Repointing a placement at a different
lot moves the flag out from under them. Editing the row in place changes what
comes out and leaves the flag exactly where the client expects it.

### 2. One lot, several delivery mechanisms

MSB treasures, NpcParam drop tables and EMEVD `AwardItemLot` calls all terminate
at the same row. Editing the row covers every route at once.

This matters more than it sounds, because the current pool is mostly *not*
treasure:

| pool item | lot | how the game delivers it |
| --- | ---: | --- |
| Upper Cathedral Key | 2800290 | MSB treasure (宝死体_ミイラ) |
| Cainhurst Summons | 2410990 | scripted award, Iosefka's Clinic bed |
| Orphanage Key | 2420900 | Brainsucker fixed drop |
| Eye of a Blood-drunk Hunter | 10040 | Hunter's Dream messenger gift |
| Eye Pendant | 3401810 | scripted, before the Vicar fight |
| Laurence's Skull | 3502000 | hidden altar |
| Astral Clocktower Key | 3501850 | Living Failures defeat reward |
| Celestial Dial | 3501800 | Lady Maria defeat reward |
| Hunter Chief Emblem | 2400450 | fixed placement, 2 copies |
| Tonsil Stone | 39000 | Patches gift |

Only one of ten is an MSB treasure. A placement-level strategy would need three
separate tools and would still miss the boss rewards.

⚠️ Note the asymmetry with the growth pool: `research/catalog/fixed_location_catalog.tsv`
is **100% MSB treasure by construction**, because it is built from treasure
placements. So the 651 catalog locations and the 10 items currently randomized
sit at opposite ends of the delivery spectrum. Suppressing at the lot is the only
approach that covers both.

## What the edit is

Rewrite the `ItemLotParam` row to award a placeholder. Keep the row id, keep the
acquisition flag. The pickup still exists, the player still interacts with it,
the flag still fires so the check reports, and what comes out is junk instead of
a key.

Awarding *nothing* is not the same thing and is not the plan: an empty lot risks
the game skipping the award path entirely, which would take the flag with it.

## The planner

```bash
python tools/plan_vanilla_suppression.py --output work/suppression-plan.json
```

Reads the committed research, resolves each randomized item to the single row
that awards it, then adds every declared fixed check by its explicit runtime
binding. Location bindings name the exact lot and item identity, so a common item
does not become an ambiguous global lookup. The planner **refuses rather than
guessing** whenever either source disagrees.

Refusal cases, each with a test that fires it:

| refusal | why it cannot be guessed past |
| --- | --- |
| `no_lot` | nothing awards it — shop, covenant, or an engine side effect |
| `multiple_lots` | editing one leaves the others reachable |
| `no_acquisition_flag` | suppressible, but never detectable |
| `flag_not_unique` | the edit would make the detection target ambiguous |
| `multi_item_lot` | the row awards other things too; the edit has to be per-slot |

## Native binder writer

`tools/bb_suppression_writer` consumes the planner JSON and edits the real
`gameparam.parambnd.dcx` through SoulsFormatsNEXT. It applies the matching
Bloodborne PARAMDEF, finds the exact category-4 slot named by each plan row,
changes only that item ID, serializes the binder, reopens it, and then proves:

- the binder file count, order, IDs and names are unchanged;
- every unrelated embedded file is byte-identical;
- the ItemLotParam row count and order are unchanged (including duplicate IDs
  present in the retail table);
- every unplanned row and every protected field are semantically identical;
- each planned item field became the placeholder; and
- every row ID, item category and acquisition flag survived.

It preflights all plan rows before creating output, refuses in-place writes,
refuses to overwrite an existing output, and requires an explicit `--apply`.
The wrapper adds the same guard and never installs anything:

```powershell
.\tools\build_vanilla_suppression.ps1 `
  -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT `
  -OutputRoot .\work\vanilla-suppression-build `
  -Apply
```

The output directory contains the separate binder, the exact plan, and a hash
manifest whose `installed` field is false. Installation remains a deliberate
later step after backup and canary review.

## Current result

On the pre-catalog vertical slice, **eighteen rows plan cleanly: nine
shuffled-key awards and nine additional fixed checks. One pool item is
refused.** Generated catalog slices may add clean category-4 rows and explicit
refusals for weapon/armor rows until the placeholder policy covers those
categories.

`tonsil_stone` resolves to lot 39000 — a Patches gift — whose
`generic_acquisition_flag` is `-1`. That is "no flag", not flag −1; 2,778 rows in
the corpus carry it. The Tonsil Stone can be suppressed, but **it can never be
detected**, so it cannot be a check until some other signal is found for it. It
is currently in the item pool and gates the Nightmare Frontier, which holds no
checks — so nothing breaks today, but it should not be assumed workable later.

Two lots have two placements each (Hunter Chief Emblem, Upper Cathedral Key). One
row edit covers both copies, which is what we want here — but the planner reports
the count, because for a lot with 158 placements it would not be.

## Cross-check

The planner derives each flag from `lot_items.tsv`. `runtime_bindings.py` derived
its flags independently. `tests/test_vanilla_suppression.py` asserts the two
agree wherever both exist, and fails if the cross-check examined fewer than five
of them — a consistency test that can pass by checking nothing is not a test.

## Not done here

Repacking. `tools/apply_vanilla_suppression.py` writes and re-verifies the edited
CSV directly from the committed bundle. Putting that CSV back into the game's
param BND still needs the owner's game tooling. The writer proves that the changed
row set is exact and that every row ID and acquisition flag survives.

Open questions that need the game rather than the corpus:

1. Does the game gate anything on *possession* of a key item rather than on its
   acquisition flag? `docs/LOGIC-MODEL.md` question 2 is the same question. If it
   does, a suppressed key needs the client to grant it on receipt for the vanilla
   door to open.
2. Does the award path still set the flag when the awarded item is a placeholder?
   Everything here assumes yes; it is one live test.
3. What should the placeholder be? Something worthless, repeatable and safe to
   receive many times.
