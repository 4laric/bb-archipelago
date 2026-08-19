# Central Yharnam vertical slice

The first Bloodborne Archipelago game is deliberately bounded to Central
Yharnam through Father Gascoigne. The broader model in `data.py` remains
research scaffolding; it is not emitted into this slice's multidata.

## Seed contents

- **51 physical fixed pickups** from canonical map `m24_01_00_00` and its
  `_01` / `_11` runtime variants.
- **2 boss checks:** Cleric Beast and Father Gascoigne.
- **53 network locations total.**
- **Goal:** Father Gascoigne.
- **Item pool:** the live-validated Saw Spear plus Blood Vial filler. Torch,
  Hunter attire, auto-upgrade, and auto-equip remain outside the receive pool.

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

The slot-data contract exposes all 53 flag bindings and identifies Gascoigne's
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

The native writer has built and reopened this complete binder successfully.
Installation and one in-game canary remain deliberate playtest steps. The seed
requires the installed-binder hash witness before the native client will arm.

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

The event-flag accessor is validated, but automatic live sends remain fail
closed until the backend can prove both `gameplay_ready` and the stable loaded
save identity. The same identity must ultimately be witnessed again at actual
game-thread grant execution so a queued command cannot cross a save switch.

Mock mode exercises the complete 53-location slot-data contract, debounce,
delivery ledger, reconnect behavior, and goal selection without weakening that
boundary.

The final playtest is therefore specific and finite:

1. validate one suppressed pickup still sets its acquisition flag;
2. validate both boss flags through the live reader;
3. complete a generated seed through Gascoigne;
4. restart/reconnect and confirm no location or item is replayed.
