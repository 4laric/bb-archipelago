# Bloodborne location-signal research

Status: fifteen fixed-location acquisition flags mapped statically; live accessor not yet mapped
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

The committed source census establishes acquisition-flag IDs for fifteen
randomized fixed locations in the vertical slice. Of the original six, Upper
Cathedral Key is the only MSB treasure and the other five are EMEVD item-lot
awards; the nine expansion checks are MSB treasures. Their source kind, source
location, item-lot ID, item identity, and acquisition flag are recorded in
`worlds/bloodborne/runtime_bindings.py`. This completes the static mapping only;
automatic client reporting remains disabled until Lane B identifies and validates
the live flag-manager accessor.

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

### Instrumented session kit

Create the evidence directory before launching the emulator. Include every
artifact the tester will actually load so the manifest records its hash:

```powershell
$session = .\tools\event_flag_session.ps1 -Mode Initialize `
  -LocationName "Healing Church Workshop - Old Hunter Bone" `
  -Serial CUSA03173 -EmulatorVersion "0.17.0" -TrialCount 3 `
  -Artifact build\bloodborne.apworld,tables\Bloodborne-native-item-grant-auto-v2.CT
```

`tables/Bloodborne-event-flag-snapshot.CT` asks once for the candidate memory
region and the current trial directory. Its five hotkeys write identically sized
`idle-a`, `idle-b`, `before`, `after`, and `reload` dumps and append capture
timestamps. `reload` is taken after quitting to title and loading the save again,
and it is what requirement 4 above is tested with; without it `Analyze` can only
report leads. Restore the same pre-action save and reload the table for each trial.

Unreadable chunks inside the window are zero-filled rather than aborting the dump,
and the filled byte count is recorded per stage in `capture-state.txt`. A constant
fill cannot manufacture a candidate, because the comparator reports only positions
that changed. A fill count that differs between stages of one trial means the
region moved, and that trial is not comparable.

If the inputs are save files or dumps made by another tool, copy them into the
same layout with `-Mode Capture`. Once all trials are present, run:

```powershell
.\tools\event_flag_session.ps1 -Mode Analyze -Session $session
```

The analyzer applies the idle control independently to every trial, then writes
`intersection.csv` containing only transitions that survived every repetition.
Arm `tables/Bloodborne-event-flag-write-breakpoint.CT` on the best candidate's
live byte address. It captures the writer, every general-purpose register, and
48 surrounding code bytes before disarming itself. Preserve its output in the
session directory.

## Discovery order

The first tranche should intentionally contain different signal classes:

| Priority | Check | Class | Why first |
| ---: | --- | --- | --- |
| 1 | Healing Church Workshop - Old Hunter Bone (`52110000`) | world pickup | Exact mapped treasure; atomic and repeatable from a backup |
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

Use `Healing Church Workshop - Old Hunter Bone`, the fixed treasure whose
catalog-backed acquisition flag is `52110000`:

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

### Iosefka courtyard Bullet trial

The ten Quicksilver Bullets outside Iosefka's Clinic resolve to item lot
`2410800` and acquisition flag `52410800`. A first whole-process byte scan used
unknown-initial, repeated unchanged controls, one increased scan around only the
pickup, and further unchanged controls. A DS3-layout heuristic ranked addresses
whose byte was `0x80` at word offset `+3`; this heuristic was used only for
candidate ranking and is not yet a Bloodborne layout claim.

Candidate `0x23369541F` in shadPS4 process `0x6C70` was changed from `0x80` to
zero under an exact-value and PID guard. It remained zero across a Hunter's Mark
area reload, but the Bullet lot did not return, disproving it as the acquisition
flag. Restoring the stale byte to `0x80` after the reload caused an access
violation at `0x077759C7`. The associated write tables are retired. Remaining
candidates must be tested by replaying the backed-up pre-pickup transition and
read-only comparison or write breakpoints, not sequential speculative writes.

#### Resolved live manager path (CUSA03173 01.09, shadPS4 v0.18.0)

The verified pre-pickup save was restored and the Bullet lot returned. A
read-only before/after replay over the preserved scan addresses produced three
unique exact `0x00 -> 0x80` transitions. Two candidates changed again without
another pickup and lived in repeating transient structures. The remaining byte,
`0x20803170A` in process 16592, stayed `0x80` in an otherwise zeroed region.
Restoring the pre-pickup save while retaining the same shad process returned that
byte to `0x00` and returned the lot.

A one-shot hardware write breakpoint on `0x20803170A` fired when the lot was
collected and resumed the game safely. The captured write sequence was:

```text
44 89 F0          mov eax,r14d
C1 E8 03          shr eax,3
41 F7 D6          not r14d
41 80 E6 07       and r14b,7
BE 01 00 00 00    mov esi,1
44 88 F1          mov cl,r14b
D3 E6             shl esi,cl
0F B6 0C 02       movzx ecx,byte ptr [rdx+rax]
09 F1             or ecx,esi
88 0C 02          mov byte ptr [rdx+rax],cl
```

At the write, `RAX=100`, `RSI=0x80`, `RDX=0x2080316A6`, and the resulting byte
was `0x80`. This proves Bloodborne uses MSB-first bits within each group bank:

```text
byte_offset = suffix / 8
mask        = 1 << (7 - (suffix % 8))
```

The live function resolves the full flag ID through a manager at eboot-relative
pointer slot `RVA 0x553B100`. For this launch, eboot was at `0x05660000`, making
the slot `0x0AB9B100`; it pointed to manager `0x20802EEB0`. The observed manager
and tree layout is:

| Field | Offset | Observed meaning |
| --- | ---: | --- |
| group divisor | `+0x1C` | `1000` |
| packed-bank stride | `+0x20` | `125` bytes |
| packed-bank base | `+0x28` | base for type-1 groups |
| group-tree sentinel | `+0x38` | red-black-tree header/sentinel |
| node nil marker | `+0x19` | terminates lookup |
| node group key | `+0x20` | `flag_id / 1000` |
| node storage type | `+0x28` | `1` packed, `2` direct pointer |
| node storage value | `+0x30` | packed index or direct bank pointer |

The inlined setter write is at eboot `RVA 0x17D6EFA` and begins with signature
`88 0C 02`. A read-only generic resolver then independently produced:

```text
flag_id=52410800
divisor=1000
group=52410
suffix=800
storage_type=1
bank_base=0x2080316A6
byte_offset=100
bit_index=7
mask=0x80
resolved_address=0x20803170A
value=0x80
is_set=true
address_match=true
```

This closes the live event-flag-manager read-path unknown for the tested 01.09
build. The client must resolve the randomized eboot base per launch, verify the
setter signature, and fail closed on mismatch. Evidence is preserved in
`work/event-flag-manager-resolution.txt`,
`work/iosefka-bullet-flag-write-breakpoint.txt`, and
`work/live-event-flag-setter-code.bin`.

The standalone Rust client reader was then tested outside Cheat Engine after a
new shadPS4 launch. In process 31676, eboot moved from the discovery launch's
`0x05660000` to `0x057C0000`. The elevated reader parsed the new base from
`shad_log`, passed the setter signature gate, resolved the new manager and bank
addresses, and returned `event_flag=52410800 set=true`. This validates the
manager-relative implementation across two independently randomized launches.
