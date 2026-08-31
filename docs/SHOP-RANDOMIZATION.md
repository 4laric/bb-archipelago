# Bath Messenger shop randomization

Issue #271 is an opt-in feature. Vanilla stock and unlock timing must remain
unchanged when the option is disabled.

## What is now established

`ShopLineupParam` is the authoritative stock table. The Blood Echo Bath uses
`shopType=0`; each row identifies the sold item with `equipType` and `equipId`.
One-time purchases carry an `eventFlag`, and `qwcId` is the visibility gate.

The ordinary badge-gated stock is grouped behind ten flags,
`12101000` through `12101009`. A gate appears on every NG-cycle copy of its
stock, so an implementation must change every matching row, not merely the
first row with that value. Chalice discovery gates (small `qwcId` values) and
the Insight shop are separate systems and are out of scope for the first
version.

The two live `shop-capture.jsonl` sessions independently observed goods 4103
and 4104, and one also observed goods 4114. Those prove the inventory
descriptors for the Blood Gem Workshop Tool, Rune Workshop Tool, and Sword
Hunter Badge. They do **not** by themselves prove that 4103 or 4104 unlock Bath
stock: the workshop tools are capabilities, not badges. The capture probe's
historical `shop_unlock_goods` label is therefore broader than its evidence.

## Safe implementation contract

The first playable version should:

1. expose an off-by-default YAML toggle;
2. derive one deterministic permutation from the AP seed;
3. rewrite only `qwcId` values in the inclusive `12101000..12101009` set;
4. apply the same old-to-new mapping to every NG-cycle copy;
5. preserve row order, item, price, quantity, purchase flag, shop type, and
   every unrelated binder file byte-for-byte;
6. include the permutation in the seed request and seed-cache identity; and
7. refuse malformed, incomplete, duplicate, or out-of-domain mappings.

Before enabling the toggle in a playtest bundle, the ten flags still need a
goods-to-gate witness table. This matters because suppression removes the
natural award at randomized checks: a badge that is absent from the AP item
pool can no longer set its shop gate. Shipping a permutation before auditing
that table could create permanently unavailable stock while appearing healthy.

## Inspection

The parameter writer has a read-only inspection mode:

```powershell
dotnet run --project tools/bb_suppression_writer -- `
  --inspect-shops gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

It emits every `ShopLineupParam` row and every decoded field as a tab-separated
record. This makes the gate audit reproducible against the same installed
binder the launcher will eventually edit.

