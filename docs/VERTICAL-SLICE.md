# Bloodborne Archipelago playable slices

The playable scope grows one reviewed step at a time. Slice 1 was Central
Yharnam through Father Gascoigne; **slice 3 extends it to Cathedral Ward, Old
Yharnam, and the Blood-starved Beast**, which is now the goal. The broader
model in `data.py` remains research scaffolding; it is not emitted into the
seed. Slice 3 is specified in its own section at the end of this document; the
slice-1 sections below still describe the Central Yharnam half exactly.

## Seed contents

- **48 in-slice physical fixed pickups** from canonical map `m24_01_00_00`
  and its `_01` / `_11` runtime variants. Three further pickups stay in the
  manifest but out of slice seeds: the Iosefka's Clinic back-yard pair
  (gated behind the Amelia → Laurence's-skull password chain) and the White
  Messenger Ribbon (the little-girl quest reward collectible only after
  Rom's blood moon). All three are far past the slice's goal; their vanilla
  awards remain suppressed, so in slice 1 they are inert pickups (no vanilla
  item, no AP check).
- **2 boss checks:** Cleric Beast and Father Gascoigne.
- **50 network locations total.**
- **Goal:** Father Gascoigne.
- **Post-goal region:** Cathedral Ward enters the slice behind
  `event_gascoigne_defeated`, which keeps the Tomb of Oedon strip pickups
  (Blood Gem Workshop Tool, Red Jeweled Brooch) honest as post-goal checks.
- **Item pool:** Saw Spear and Augur of Ebrietas once each, then a deliberate
  cycle of Blood Vials, Quicksilver Bullets x3, Pebbles x3, Molotov Cocktails
  x2, and Blood Stone Shards x2. Torch, Hunter attire, auto-upgrade, and
  auto-equip remain outside the receive pool.

The pickup manifest is generated from
`research/catalog/fixed_location_catalog.tsv` by
`tools/build_fixed_location_slice.py`. Two mutually exclusive later-cycle
replacement rows are collapsed onto their first-cycle physical chests, so they
cannot become phantom checks. Existing published keys retain their permanent
AP IDs; every new ID is append-only in `worlds/bloodborne/ids.tsv`.

The catalog describes flag `52410610` as Hunter Hat, but the source corpus
shows a four-row Hunter Set award group (`2410610` through `2410613`) sharing
that flag. It is one physical check and four suppression edits.

## Runtime flags

Every pickup keeps the acquisition flag derived from its ItemLotParam row.
The two boss-completion flags come directly from Central Yharnam EMEVD:

| Check | Event flag | Static evidence |
| --- | ---: | --- |
| Cleric Beast | `12411700` | paired boss completion state in `m24_01_00_00` |
| Father Gascoigne | `12411800` | gates arena cleanup, key award, and downstream world state |

The slot-data contract exposes all 50 flag bindings and identifies Gascoigne's
AP location ID as `goal_location`. The native client sends `CLIENT_GOAL` when
that debounced check is reported, and resends it after reconnect if the server
already knows the goal location is checked.

## Vanilla-award suppression

All 51 fixed pickups declare suppression required. The v2 suppression plan
contains **54 guarded ItemLotParam edits**:

- one edit per physical pickup;
- three continuation edits for the Hunter Set award group;
- no refusals.

The writer now matches the original category and item ID, then replaces the
slot with one Blood Vial while preserving the row ID and acquisition flag. This
covers goods, weapons, attire, and the category-8 blood-gem row without deriving
unsupported runtime grant descriptors from ItemLot IDs.

The native writer built and reopened this complete binder successfully. The
binder was then installed on shadPS4 0.18.0 and live-tested: a suppressed pickup
gave the one-Vial placeholder, set its acquisition flag, stayed collected after
restart, and retained the placeholder reward. The seed requires this installed
binder's hash witness before the native client will arm.

## Runtime sequence

1. Generate a Bloodborne player with Archipelago.
2. Build the seed-matching suppression binder and install it through the
   documented BBLauncher path.
3. Load `tables/Bloodborne-native-item-grant-auto-v2.CT` and launch the native
   Bloodborne client.
4. The client verifies runtime build `bb-0.1.0-r5`, suppression manifest, and
   installed binder before constructing the runtime loop.
5. Pickup and boss flags require three consecutive true reads before a
   `LocationChecks` send.
6. Received items are processed in AP index order and acknowledged only after
   the native harness reports durable completion.
7. Gascoigne's check also sends the Archipelago goal status.

## Remaining live boundary

The event-flag accessor and automatic location sends are live-validated. For
the bounded MVP, `--assume-correct-save` makes the operator attest that the
loaded character belongs to the connected AP slot. Three stable manager reads
arm gameplay; losing that manager immediately disarms and clears debounce
streaks. This is intentionally less safe than real save identification: checks
sent from the wrong character are irreversible, and a reward delivered there
still advances the AP ledger.

The live run automatically reported the already-collected Iosefka courtyard
lot plus two newly collected lots. AP returned three Vials; the r5 CE bridge
granted and durably acknowledged indices 0 through 2 without manual `/check`.

The remaining finite playtest is:

1. exercise every varied goods shape and the Saw Spear through the automatic path;
2. validate Cleric Beast and Gascoigne flags, including `CLIENT_GOAL`;
3. restart/reconnect and confirm no location or item is replayed;
4. replace operator attestation with a real loaded-save identity before general release.


## Slice 3: Cathedral Ward, Old Yharnam, Blood-starved Beast

### Scope

Three maps, read off `research/catalog/fixed_location_catalog.tsv` rather than
assumed: `m24_01_00_00` (Central Yharnam, slice 1), `m24_00_00_00` (Cathedral
Ward) and `m23_00_00_00` (Old Yharnam). `SLICE_MAPS` in
`tools/build_fixed_location_slice.py` is the whole scope statement.

### Seed contents

- **164 reviewed fixed pickups** in the manifest, of which **161** are seeded:
  46 Central Yharnam, 61 Cathedral Ward (59 from `m24_00` plus the two Tomb of
  Oedon strip rows slice 1 already placed there), and 54 Old Yharnam. Three
  rows stay out of seeds: the Iosefka's Clinic back-yard pair (unchanged from
  slice 1) and the White Messenger Ribbon, a little-girl quest reward
  collectible only after Rom's blood moon.
- **6 scripted checks:** Cleric Beast, Father Gascoigne, Blood-starved Beast,
  Vicar Amelia, the Laurence's-skull altar interaction, and the Radiant Sword
  Hunter Badge treasure.
- **167 network locations total.**
- **Goal:** the Blood-starved Beast (`12301800`). The client reads the goal
  from slot data's `goal_location`, so this is a seed-owned move, not a client
  rebuild.

### Regions and gates

```
Menu -> Hunter's Dream -> Central Yharnam
Central Yharnam --(Father Gascoigne defeated)--> Cathedral Ward
Cathedral Ward --(free)--> Old Yharnam            [Blood-starved Beast]
Cathedral Ward --(Hunter Chief Emblem)--> Grand Cathedral
```

**Why the emblem is modelled as a single-clause gate.** The audited edge in
`PROGRESSION-DAG.md` is "Hunter Chief Emblem **or** the Healing Church Workshop
route". Written as one two-clause rule on one entrance, it is vacuous: Old
Yharnam is free from Cathedral Ward and the Blood-starved Beast is free inside
it, so the Beast clause is always satisfiable and the emblem can never be the
requirement. The route is two hops in the game, and it is now two hops in the
model: the emblem opens the gate directly, while the workshop is entered behind
the Beast and reaches the same plaza from the other side. Slice 3 does not seed
the Healing Church Workshop, so inside a slice-3 seed the emblem is the only
way into the Grand Cathedral and it gates the two checks there.
`tests/test_bloodborne_gates.py::EmblemIsNotVacuousTests` and the reachability
test in `tests/test_bloodborne_model.py` hold that claim: withholding the
emblem must make a non-empty set of seeded checks unreachable.

The Hunter Chief Emblem is therefore in **both** pools — the full pool and the
reduced `SLICE_ITEM_KEYS` pool — because an emblem-only gate with no emblem in
the pool is an unreachable region, not a challenge.

### Evidence and its limits

Every new row is a catalog row. Its acquisition flag, item lot, category and
item id come from `fixed_location_catalog.tsv` and `fixed_location_items.tsv`,
and the builder refuses any row whose flag/lot pair is missing from
`research/joined/fixed_location_event_refs.tsv` — a `lot_items.tsv`
acquisition-flag row on its own is a param join, not a placement, and is not
evidence that a treasure exists. `source_kind` stays `treasure` for exactly
that reason.

What is **not** claimed:

- No new flag has been observed live. Slice 1's canary (`52410800`) is still
  the only pickup flag with a pre/post/restart runtime witness. Cathedral Ward
  and Old Yharnam need their own canary runs before this slice can be called
  playtested, and neither region's boss flag (`12301800`, `12401800`) has been
  seen fire.
  `docs/SLICE3-WITNESS-PASS.md` traces every one of those flags to its
  instruction or param row, records which claims a live session still has to
  close, and carries the checklist for that session.
- No new runtime **item** descriptor was added. The pool is unchanged apart
  from the emblem, which already had a validated category-4 binding. The Rifle
  Spear, Hunter's Torch and Charred Hunter Garb that Old Yharnam holds in
  vanilla are suppressed, not granted: admitting a weapon or attire item to the
  pool still needs its own live grant canary.
- Two rows in the slice maps are deliberately excluded, with reasons recorded
  in `EXCLUDED_FLAGS`: `52400480` already ships from `data.py`, and `52420320`
  shares its flag between an `m24_00` dummy corpse and the real `m24_02`
  placement.
- Three more NG-cycle replacement rows (`52400485`, `52420645`, `52420695`)
  collapse onto their first-cycle chests, exactly as slice 1's two did.

### Suppression

The canonical plan is now **179 edits, zero refusals** (see
`VANILLA-SUPPRESSION.md`); the 179th is lot 31000, the Oedon Tomb Key's EMEVD
award, which is now a shuffled progression item. Its SHA-256 changed, so **every
playtester must rebuild and reinstall the binder** — and `build.ps1` keeps
`work\vanilla-suppression-build` when it already exists, so delete that
directory first or the rebuild does nothing. A binder from any earlier plan will
not satisfy a current seed's installation witness and the native client will
stay disarmed.
