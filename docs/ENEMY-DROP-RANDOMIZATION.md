# Enemy drop randomization

## Scope

`randomize_enemy_drops` is an opt-in YAML option that shuffles local,
repeatable enemy consumable/material loot. It does **not** add Archipelago
locations: killing or farming an ordinary enemy never sends a network check.
The shuffled table follows the `NpcParam` archetype, including when the enemy
enemizer moves that archetype to another physical slot.

The first catalog is generated from the committed CUSA03173 01.09 inputs. Of
473 fixed-map `NpcParam.itemLotId_*` fields, 149 assignments in 26 compatible
groups are eligible, covering 73 distinct loot tables.

## Fail-closed eligibility

A drop field enters the catalog only when all of these are true:

- its NPC archetype occurs in a fixed map in the committed MSB mine;
- the referenced `ItemLotParam` row exists and has at least one active slot;
- neither the row nor any slot has a positive acquisition flag;
- every active slot is category 4 (`EquipParamGoods`);
- every awarded goods row is repeatable and droppable: `isDrop=1`,
  `isOnlyOne=0`, `isFixItem=0`, `maxNum>1`, and `qwcId<0`.

This excludes keys, badges, progression rewards, one-time NPC rewards,
weapons, armor, runes, blood gems, and unknown/missing rows. The catalog is a
generated artifact; tests regenerate it from `research/bb_inputs.db` so a
source-data change cannot silently widen the policy.

## Compatibility groups and determinism

Whole lot IDs are permuted rather than rewriting their contents. A lot may
move only within an exact group sharing:

1. the same `NpcParam` drop field (`itemLotId_1` through `_6`);
2. the same `ItemLotParam.lotItem_Rarity`;
3. the same ordered chance, quantity, and luck-enable cadence.

This preserves each enemy field's probability/quantity shape and the global
multiset of eligible lots. The permutation is derived from the multiworld seed
and player number. A bounded deterministic search minimizes unchanged fields
where duplicate source lots make a complete derangement impossible.

## Seed contract and writer

When enabled, the apworld writes `enemy_drop_assignments` into the player's
`.bbseed.json`. Each assignment names the NPC row, field, expected source lot,
and target lot. The launcher includes the entire plan in its cache identity and
passes the request to `BBSuppressionWriter` while composing the already
suppressed seed binder.

The native writer refuses unless every NPC row and field is unique, the live
source value equals the request, and every target lot exists. After writing it
reopens the binder and proves that only the declared `NpcParam.itemLotId_*`
cells (plus independently requested weapon/shop cells) changed.

## Interaction and acceptance

- Enemy randomization off: drops still shuffle when this independent option is
  on.
- Enemy randomization on: drops follow the transplanted NPC archetype because
  cloned rows retain their item-lot fields.
- The option is off by default and does not change AP logic or item-pool size.

Static acceptance is deterministic generation, catalog regeneration, guarded
writer round-trip, package integration, and seed-cache separation. Live beta
acceptance is one enabled seed proving two changed archetypes drop their target
lots, an excluded guaranteed/flagged reward remains vanilla, and enabling the
enemy enemizer does not detach loot from its archetype.
