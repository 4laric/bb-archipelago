# Bloodborne location-signal research

Status: six fixed-pickup acquisition flags mapped statically; live accessor not yet mapped  
Target builds: `CUSA00900` and `CUSA03173`, AppVer `01.09`

## Scope and evidence boundary

Location detection must be derived from user-owned Bloodborne files and original
runtime experiments. The excluded existing randomizer corpus is not an input.
Names or IDs found in the game's own event archives are only candidates until the
game is observed reading or writing the corresponding state.

Use the evidence labels in `RESEARCH-BASELINE.md`. In particular, a plausible
event number found in a script is `inferred`, not `observed` or `validated`.

## What counts as a location signal

A signal is acceptable for the Archipelago client only when it is:

1. monotonic for the relevant save slot (it does not clear during ordinary play);
2. specific to one declared check, or has a documented composite predicate;
3. readable without changing game state;
4. present after quit, full emulator restart, and save reload;
5. reproducible from a clean pre-check save; and
6. resolved by signature or stable manager-relative addressing on both supported
   01.09 serials, rather than by a session heap address.

Inventory presence is not sufficient for world pickups or NPC rewards: an item
can be consumed, sold, stored, or received from Archipelago. Lamp menu visibility
may be a useful area signal, but it is not automatically evidence that every
nearby pickup has been checked.

## Static mappings now available

The MSB treasure to `ItemLotParam` join establishes acquisition-flag IDs for
the six randomized pickups in the vertical slice. They are recorded in
`worlds/bloodborne/runtime_bindings.py`. This completes the static mapping only;
automatic client reporting remains disabled until Lane B identifies and
validates the live flag-manager accessor.

Eye Pendant's flag `9470` is intentionally short. A full `lot_items.tsv` audit
finds it on exactly one lot, `3401810`; the other short progression flags `6670`
and `6671` are also each unique to one lot. EMEVD references `9470` in the
Hunter's Nightmare award path and the Research Hall altar-state path, consistent
with one acquisition transition and its downstream consumer. The unit suite
asserts that every runtime location flag remains specific to exactly one lot.

## Two discovery lanes

### Lane A: event-script candidates

Work from the game's own `dvdroot_ps4/event/*.emevd.dcx` files. Unpack and decode
copies into a separate research output directory; never modify installed game
files. For each deliberately chosen early-game event, record:

- map archive and event number;
- instructions that test, set, or clear candidate flags;
- entity, item-lot, treasure, character, object, or region IDs used nearby;
- whether the candidate appears to represent attempt/start, defeat/acquisition,
  reward, lamp activation, or cleanup; and
- all other writers and readers of that candidate ID.

This lane identifies which transitions are worth watching. It does not establish
the runtime flag-table representation or address.

### Lane B: controlled runtime transitions

Start with a restored pre-action save. Take two quiescent control snapshots with
no gameplay action between them, then take an immediate before/after pair around
exactly one action. Candidate bytes/bits are the action-pair changes after removing
positions that also changed in the control pair:

```powershell
.\tools\compare_event_snapshots.ps1 `
  -Before work\flags\pickup-before.bin `
  -After work\flags\pickup-after.bin `
  -ControlBefore work\flags\idle-a.bin `
  -ControlAfter work\flags\idle-b.bin `
  -CsvPath work\flags\pickup-candidates.csv
```

The comparator can be used for equal-length raw memory-region dumps or matching
save-slot files. Save-file differences may include checksums, journals, counters,
encryption, or compression; correlated changed bits are leads, not flags.

Repeat the action from the same pre-action save at least three times. Intersect
the surviving candidates. Restore the post-action save and verify that the bit is
still set without repeating the action. A write breakpoint on the final runtime
candidate should then identify the flag setter or backing-table access path.

## Discovery order

The first tranche should intentionally contain different signal classes:

| Priority | Check | Class | Why first |
| ---: | --- | --- | --- |
| 1 | Central Yharnam fixed corpse pickup near a lamp | world pickup | Fast, atomic, repeatable from a backup |
| 2 | Central Yharnam Lamp activation on a save where it is inactive | lamp/area | Tests a persistent non-item world transition |
| 3 | Cleric Beast defeat | boss | Optional early boss; separates defeat from story progression |
| 4 | Father Gascoigne defeat | boss/progression | Early mandatory transition with downstream world changes |
| 5 | One early NPC dialogue reward | NPC reward | Tests a multi-stage quest/reward state machine |

Choose and record the exact corpse and NPC before capture; descriptive ambiguity
would make repeated trials incomparable. Avoid bundled actions: do not activate a
lamp, pick up an item, open a shortcut, or trigger new dialogue in the same trial.

## Candidate record

Every mapping should be one row in a future machine-readable table with at least:

```text
location_name, class, map, source_event, candidate_flag,
runtime_accessor_signature, predicate, reset_behavior,
save_reload_test, cusa00900_test, cusa03173_test, evidence, notes
```

Bosses may need a completion flag distinct from encounter-start and fog state.
Pickups may use item-lot acquisition, treasure-object state, or both. NPC rewards
may require a reward flag rather than the NPC's quest phase. Lamps/areas should be
treated as optional checks until their semantics and logic value are established.

## Next live experiment

Use the fixed Central Yharnam corpse pickup selected in advance:

1. Restore the same pre-pickup backup for every trial and disable incidental play.
2. Capture two idle snapshots 10 seconds apart.
3. Capture `before`, acquire only that pickup, wait for the acquisition banner to
   clear without moving into another trigger, and capture `after`.
4. Compare with `compare_event_snapshots.ps1`; repeat from the backup three times.
5. Test surviving candidates against a post-pickup reload.
6. Put a write breakpoint on the best runtime candidate and repeat once to capture
   the instruction, registers, module-relative call site, and surrounding bytes.

Success for this experiment is not merely finding a changed address. It is one
repeatable bit transition plus the code path that writes it. That code path is the
starting point for locating the event-flag manager and converting later mappings
into manager-relative flag queries.
