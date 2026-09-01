# Armor item-pool contract

Armor is a receive-item feature, not an extension of the location catalog.
The existing attire pickups are already Archipelago locations and their
`ItemLotParam` awards are already replaced by the seed-owned suppression
binder. Adding an armor piece as a sendable item must not create another check
or make the suppression planner search every vanilla copy of that piece.

## Admission rules

Each admitted piece must carry all of the following data:

- one permanent AP item key and network ID;
- its reviewed `EquipParamProtector` row;
- a category-1 descriptor pair, with normalized ID
  `0x10000000 | protector_id` and raw ID
  `0x90000000 | protector_id`;
- quantity exactly one and no reinforcement level;
- one explicit equipment feed slot: head, chest, hands, or legs;
- descriptor evidence. `param_id_inferred` is sufficient to generate a
  diagnostic build, but only a successful live insert, inventory render,
  equip, save, and reload may promote a row to observed evidence.

The client must continue to fail closed if a category-1 row has the wrong
prefix, mismatched low 28 bits, an unsupported feed slot, or a quantity other
than one. Armor must use the native category-1 allocator; it must never be sent
through the goods or weapon path.

## Pool and YAML policy

Armor should be controlled by an independent, opt-in YAML toggle while most
rows retain inferred descriptor evidence. The option adds each eligible piece
once as a useful item and replaces ordinary filler; it does not add locations.
Turning it off must preserve the pre-armor item pool byte-for-byte for the same
seed and options.

The catalog currently contains four Old Hunters sets (`old_hunter`,
`maria_hunter`, `constable`, and `yamamura`). Those pieces must also require
`include_dlc`; the armor option alone must never introduce DLC equipment into a
base-game seed. All other catalog sets are eligible independently of the DLC
option.

Because the armor catalog is larger than the old useful-item tier, capacity
shedding must remain deterministic. Progression items are never shed. If a
small active location set cannot hold every useful item, armor follows the
same documented useful-item policy rather than silently displacing a key.

## Suppression boundary

Do not add every armor key to `POOL_SUPPRESSION_ITEM_KEYS`. That set means
"remove every reviewed natural source of this randomized progression/equipment
item" and is appropriate only when vanilla ownership itself would bypass the
randomized contract. Armor has shops, repeated lots, shared acquisition flags,
and alternate-cycle copies; globally chasing them would both over-suppress the
game and make the fail-closed planner reject ambiguous rows.

Physical pickup checks remain governed by their `RuntimeLocationBinding` and
`vanilla_award_suppressed` declaration. A chest containing four attire pieces
may still be one AP location with four lot rows sharing one acquisition flag;
the suppression plan must replace every continuation row while sending exactly
one location check. Receiving an armor item elsewhere is independent of that
location.

## Promotion checklist

Before enabling the option by default, capture at least one clean live result
for every distinct protector row:

1. receive the piece into an inventory that has never held it;
2. verify the delivery ledger reports the expected category-1 descriptor;
3. verify it appears in the correct attire inventory tab and can be equipped;
4. save, reload, and verify it persists and remains equippable;
5. receive a duplicate and confirm the game/client's duplicate policy is
   deliberate (no invisible record, blocked queue, or unrelated storage item);
6. repeat one representative delivery with auto-equip enabled and disabled.

The already observed Charred Hunter Garb is the category-1 allocator canary,
not evidence for every protector row. Until the remaining rows are witnessed,
the diagnostic build must label their descriptor provenance as inferred.
