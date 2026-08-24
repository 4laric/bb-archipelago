# Central Yharnam vertical slice

The first Bloodborne Archipelago game is deliberately bounded to Central
Yharnam through Father Gascoigne. The broader model in `data.py` remains
research scaffolding; it is not emitted into this slice's multidata.

## Seed contents

- **49 in-slice physical fixed pickups** from canonical map `m24_01_00_00`
  and its `_01` / `_11` runtime variants. Two further pickups — the Iosefka's
  Clinic back-yard pair — stay in the manifest but out of slice seeds: they
  are gated behind the Amelia → Laurence's-skull password chain, far past
  the slice's goal. Their vanilla awards remain suppressed, so in slice 1
  they are inert pickups (no vanilla item, no AP check).
- **2 boss checks:** Cleric Beast and Father Gascoigne.
- **51 network locations total.**
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
`tools/build_central_yharnam_slice.py`. Two mutually exclusive later-cycle
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

The slot-data contract exposes all 51 flag bindings and identifies Gascoigne's
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
