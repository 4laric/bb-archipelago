# Progression item validation

MVP scope: fixed main-game and Old Hunters content; Chalice content is excluded.

`research/validation/progression_items.tsv` compares 35 progression-relevant keys, tools, and
badges from the Bloodborne-Wiki key-item table against three independent game-data paths:

1. English `engus` FMG name ID -> `EquipParamGoods.ID`
2. `ItemLotParam` -> MSBB treasure or NPC drop placement
3. literal or parameter-resolved `AwardItemLot` calls in decompiled EMEVD

Current result: 33/35 entries have a compatible static source. No numeric mismatch was found.
The ESD dump contains all 20 talk bundles (271 non-empty Python files). It narrows the two semantic
review entries as follows:

- Underground Cell Inner Chamber Key: wiki describes acquisition from Simon, while the fixed MSBB
  join exposes its lot as a treasure placement. Simon's `t350505.py` explicitly checks possession
  of goods 4015 afterward, supporting a spawned/drop-object implementation rather than a mismatch.
- Cainhurst Badge: the lot and English goods ID exist, but neither fixed MSBB placement nor EMEVD
  `AwardItemLot` supplies it. Annalise's `t250307.py` proves the Vileblood oath transition: it sets
  flags 72500332 and 72500312 after the player accepts, while event 9042 is activated through the
  oath flow. No explicit goods-4117 acquisition call exists in ESD, so the badge appears to be an
  engine/covenant side effect rather than a conventional lot award.

Wiki descriptions are used only as human-readable expectations. IDs, flags, and source evidence
come from the user's extracted game files.

Hunter Chief Emblem is included explicitly because it is in the randomized pool. Its Japanese
`EquipParamGoods` internal name is the stale `旧市街への鍵` ("key to the old town"), but four
independent joins agree on the identity: English FMG goods 4011, raw runtime descriptor
`0xB0000FAB`, ItemLot 2400450 with acquisition flag 52400450, and the fixed Cathedral Ward
treasure placement in `m24_00_00_00`. The internal label is therefore not treated as a mismatch.
