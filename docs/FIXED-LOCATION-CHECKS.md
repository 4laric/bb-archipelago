# Generated fixed-location checks

Status: first Central Yharnam slice generated; live end-to-end AP check pending.

## Source contract

`worlds/bloodborne/fixed_locations.tsv` is the reviewed shipping manifest. Its
rows are copied from `research/catalog/fixed_location_catalog.tsv` at repository
revision `eebdd7e8f5cb27336db65d57f6cf83b7baf6c22d`; that catalog's SHA-256 is
`22ac0b6e8768663f700fb46aa62ef46577dc4fe1845ae9b0bc4b1748edbf1102`.

Tests join every shipping row back to the canonical catalog, its per-item
evidence and the MSB/event-reference evidence. A row is rejected if its flag,
lot, item identity, classification or source map has drifted. Executable RVAs,
signatures and shadPS4 process details are deliberately absent: the standalone
client owns those version-specific facts.

## Included slice

The first slice contains six Central Yharnam checks:

- White Messenger Ribbon
- Saw Spear
- Saw Hunter Badge
- Torch
- Iosefka courtyard Quicksilver Bullets x10
- Blood Gem Workshop Tool

The bullet pickup is the canary: ItemLotParam `2410800`, acquisition flag
`52410800`. That exact flag was observed false before pickup and true after
pickup through the resolved event-flag manager, and the manager-relative reader
was then repeated after a fresh shadPS4 launch at a different eboot base.

The Hunter Hat catalog row is intentionally not included yet. Flag `52410610`
is shared by four ItemLotParam rows, so it fails the current one-flag/one-lot
identity guard.

## Wire format

`fill_slot_data()` emits `runtime_locations` keyed by permanent AP location id:

```json
{
  "12259363": {
    "event_flag": 52410800,
    "vanilla_award_suppressed": false
  }
}
```

It also emits `runtime_items`, mapping AP item ids to validated raw descriptors,
normalized ids, item categories, evidence classes, quantities, reinforcement
levels and feed effects. Category-4 goods use the observed goods formula. Saw
Spear is the first explicit category-0 allowlist entry (`raw=0x806C5660`,
`normalized=0x006C5660`, right-hand weapon, +0); it was granted on a clean save
and confirmed in the inventory UI. Torch is deliberately excluded: the rejected
ItemLot-derived descriptor allocated an invisible record. Future weapon, attire,
rune and workshop-tool rows must carry equivalent live evidence rather than
relying on client-side or ItemLot-ID inference. The seed also emits
disabled-by-default `auto_upgrade` and `auto_equip` options. The
standalone client consumes these seed-owned tables; it does not bake world ids,
flags or equipment policy classifications into its executable.

All selected checks currently advertise `vanilla_award_suppressed: false`. They are
valid check signals, but still award their vanilla contents until the offline
ItemLotParam transformation in issue #14 is installed and playtested.

Slot data also emits the suppression manifest format and canonical plan
SHA-256. If any row is changed to `vanilla_award_suppressed: true`, the seed
requires an installation witness: the runtime hashes the binder actually loaded
by the game and compares it with the matching build manifest before arming.

## Expansion procedure

Expand one region at a time. For each proposed row:

1. require one canonical acquisition flag and defensible MSB/lot provenance;
2. reject flags shared by unrelated lots until their coupling is understood;
3. append a permanent id to `ids.tsv` (never renumber an existing id);
4. append the reviewed row to `fixed_locations.tsv`;
5. run the catalog, model, id-registry and slot-data tests;
6. exercise at least one pre-pickup/post-pickup/restart canary in the region.

Chalice locations and enemizer integration are outside this pipeline.
