# Enemy drop randomization

## Scope

`randomize_enemy_drops` is an opt-in YAML choice that rewrites local,
repeatable enemy consumable loot. It does **not** add Archipelago locations:
killing or farming an ordinary enemy never sends a network check. The rewritten
table follows the `NpcParam` archetype, including when the enemy enemizer moves
that archetype to another physical slot.

The catalog is generated from the committed CUSA03173 01.09 inputs. Of 473
fixed-map `NpcParam.itemLotId_*` fields, 280 are eligible: 215 whose vanilla
table awards something and 65 whose vanilla table is empty.

## Why the first design did nothing

Version 1 permuted whole loot tables inside compatibility groups. Of the 73
eligible tables, 35.0% of the field-weighted contents were Blood Vials and
20.9% Quicksilver Bullets, so a permutation overwhelmingly swapped one vial
table for another. The player report was blunt: "the only difference is 5x
vials and 3x bullets". Version 2 rewrites table *contents* instead.

## Slot semantics (measured)

The eight `lotItem*` slots of an `ItemLotParam` row are **one weighted pick**,
not eight independent rolls. Across the 329 distinct lots referenced by
fixed-map NPC drop fields in `research/bb_inputs.db`:

- `lotItemBasePoint01..08` sums to 1000 on 267 rows and to 100 on 55 rows;
- the "nothing" outcome is an explicit slot with `lotItemCategory = -1`,
  `lotItemId = 0` and a positive base point (163 such slots);
- an unused slot is category 0 / id 0 / base point 0 (1877 such slots).

A slot's drop chance is therefore `basePoint / sum(basePoint)`. Every rewritten
row carries its own "nothing" slot, or the enemy would drop on every kill.
Evidence: `tools/build_enemy_drop_catalog.py` derives all three counts from the
bundle; lot 10602420 (`nothing` 700, two Quicksilver Bullet slots, one Shaman
Bone Blade slot, total 1000) is a worked vanilla example.

## Fail-closed eligibility

A drop field enters the catalog only when all of these are true:

- its NPC archetype occurs in a fixed map in the committed MSB mine;
- the referenced `ItemLotParam` row exists;
- neither the row nor any slot has a positive acquisition flag;
- every award slot is category 4 (`EquipParamGoods`) and every awarded goods
  row is repeatable and droppable: `isDrop=1`, `isOnlyOne=0`, `isFixItem=0`,
  `maxNum>1`, `qwcId<0`.

An empty vanilla table now passes (it has no award slot to fail on) and becomes
a rewrite target, which is where the 65 newly eligible fields come from. A
field whose vanilla table awards a weapon, a Caryll rune, a blood gem, or a
one-off good is still excluded outright, so a rewrite can never *delete* a
vanilla reward. The catalog is a generated artifact; tests regenerate it from
`research/bb_inputs.db` so a source-data change cannot silently widen the
policy.

## Modes

- `off` leaves enemy drops vanilla.
- `balanced` rewrites every eligible table from the **consumable pool** only:
  25 kinds, the reviewed `CONSUMABLE_ITEM_KEYS` consumables that pass the
  policy, plus Blood Vials.
- `dropsanity` rewrites from a widened pool: consumables plus 3 repeatable
  upgrade materials (Blood Stone Shard 3000, Twin Blood Stone Shards 3010,
  Blood Stone Chunk 3020 -- never Blood Rock), 14 Coldblood denominations, and
  28 blood-gem recipes.

For backward compatibility, YAML `true` selects `balanced` and `false` selects
`off`.

### Sampling

Per field, seeded `bloodborne-enemy-drops:v2:<mode>:<seed>:<npc>:<field>`, so
the plan is deterministic and independent per archetype.

1. **Populate?** One roll at the vanilla populated share (215/280 = 76.8%).
   Empty tables gain drops at exactly the rate populated ones lose them, so the
   overall drop density stays where vanilla put it. A vanilla-populated field
   that rolls empty gets a nothing-only row; a vanilla-empty field that rolls
   empty is simply left alone.
2. **Cadence.** A populated field reuses its **own vanilla** chance, quantity
   and luck shape. A vanilla-empty field draws a slot count from the observed
   vanilla distribution and then a full profile from the catalog's 69 observed
   cadence profiles, weighted by how often vanilla uses each. Either way the
   emitted base points are a shape a real Bloodborne enemy already has, so farm
   rates are vanilla by construction rather than by estimate.
3. **Item kinds.** Distinct kinds are drawn without replacement, uniform within
   a class, with per-kind class weights: staple 8, consumable 2, material 2,
   Coldblood 1, gem 1. Blood Vials and Quicksilver Bullets are the "staples":
   weight 8 leaves them the two commonest single kinds a player meets
   (measured 12.6% and 10.6% of populated balanced slots for `AP_TEST:1`) and a
   long way from the 35%/21% that made a permutation invisible.
4. **Quantity.** The cadence's quantity at that rank, clamped to the kind's
   `EquipParamGoods.maxNum`. Gems are always quantity 1.

### Blood gems (dropsanity only)

Only recipes vanilla enemies already drop are admitted: a category-8 recipe
enters the pool when an *unflagged* vanilla enemy lot awards it and no flagged
lot does. That is exactly the 28 recipes in the 900xx band; the flagged
category-8 ids (Caryll runes, boss gems, 90230) are one-time rewards and stay
excluded.

Tier is by map. A field's candidate recipes are the ones an enemy in the
archetype's earliest map already drops. Map names sort in rough progression
order (m22 Central Yharnam through m36 Fishing Hamlet), so the earliest map is
the conservative cap for an archetype that appears in several. Two maps
(m24_02, m32) have no vanilla enemy gem at all; they fall back to the union
over the archetype's maps and then to the whole repeatable pool. The only
claim made is that a rewritten gem is one an enemy in that archetype's own maps
already drops, except in the documented fallback.

At most one gem slot per table, and it always lands in the rarest slot of the
cadence.

## Mechanics: new rows, never edits

Vanilla `ItemLotParam` rows are never edited in place -- fixed treasure and the
vanilla suppression plan own many of them. Each rewritten field gets a **new**
row and `NpcParam.itemLotId_N` is repointed at it.

The reserved band is `99_000_000` with stride 10, one id per eligible field
(99_000_000 .. 99_002_790). Stride 10 repeats the finding in
`worlds/bloodborne/category8_awards.py`: ItemLotParam ids are read as
consecutive groups, so award ids must not be adjacent. The band sits above both
category-8 bands (98_000_000 generated, 98_100_000 event awards) and
`tests/test_enemy_drops.py` proves it is disjoint from every vanilla lot id and
from every category-8 award lot. New rows carry `getItemFlagId = -1` and
`cumulateNumFlagId = -1`, so nothing they award is ever consumed once.

## Seed contract and writer

When enabled, the apworld writes `enemy_drop_assignments` into the player's
`.bbseed.json` alongside `"enemy_drop_plan_format": "bb-enemy-drop-plan-v2"`.
Each assignment names the NPC row, field, expected source lot, and the new lot:

```json
{
  "npc_param_id": 100010,
  "drop_field": "itemLotId_1",
  "source_lot_id": 10002420,
  "lot": {"id": 99000000, "rarity": 1, "slots": [
    {"slot": 1, "category": -1, "item_id": 0, "quantity": 0,
     "base_point": 700, "luck": false},
    {"slot": 2, "category": 4, "item_id": 1230, "quantity": 2,
     "base_point": 300, "luck": false}
  ]}
}
```

The launcher includes the entire plan and its format marker in the cache
identity and passes the request to `BBSuppressionWriter` while composing the
already suppressed seed binder.

**Version 1 compatibility.** Seeds rolled by the shipped world are still in
flight and carry no `enemy_drop_plan_format`. The launcher and the native
writer both branch on the marker and never guess the shape from the payload: no
marker means the v1 permutation plan with `target_lot_id`, and that path is
unchanged. An unrecognised marker is refused rather than downgraded.

The native writer refuses a v2 plan unless every NPC row exists and is unique,
the live source value equals `source_lot_id`, every new row id is unique in the
plan and absent from the input binder, every category-4 slot names a real
`EquipParamGoods` row with a quantity inside its `maxNum`, and every category-8
slot names a recipe some vanilla lot already awards (GemGenParam is not one of
the params this tool opens, so the vanilla-lot witness is the existence proof,
which is the same evidence the catalog used). After writing it reopens the
binder and proves that the ItemLotParam row set changed by exactly the declared
new rows, that every pre-existing lot row is byte-identical, that each new row
matches its declared slots, and that only the declared `NpcParam.itemLotId_*`
cells (plus independently requested weapon/shop cells) changed.

## Interaction and acceptance

- Enemy randomization off: drops still rewrite when this independent option is
  on.
- Enemy randomization on: drops follow the transplanted NPC archetype because
  cloned rows retain their item-lot fields.
- The option is off by default and does not change AP logic or item-pool size.

Static acceptance is deterministic generation, catalog regeneration, the guarded
writer round-trip in CI's binder job (the only place the C# compiles and runs,
against both a v1 and a v2 fixture plus a forged over-stacked one that must be
refused), package integration, and seed-cache separation.

Live beta acceptance is partly met. **Observed 2026-09-08** (launcher
`v0.1.0.1`, client `bb-0.1.0.0`, playtest report by Oz): on a `dropsanity`
seed, the first enemy killed dropped a **Delayed Rope Molotov** -- an item that
exists only in the rewritten content pool, so it cannot have come from a
vanilla loot table. That is one rewritten archetype dropping rewritten
contents, in one mode, from one kill. It establishes that the v2 content
rewrite reaches a live enemy's loot table at all; it says nothing about rates,
breadth, or the exclusions.

Still owed before this is accepted:

- a second changed archetype dropping its rewritten contents, and at a sane
  rate rather than a single lucky kill;
- the same on a `balanced` seed, which has not been played at all;
- a `dropsanity` blood gem or upgrade material actually dropping (only a
  consumable has been seen);
- an excluded guaranteed/flagged one-time reward observed remaining vanilla;
- enabling the enemy enemizer alongside this and confirming loot stays attached
  to the transplanted archetype.
