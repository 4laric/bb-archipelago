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

The implementation:

1. expose an off-by-default YAML toggle;
2. derive one deterministic permutation from the AP seed;
3. rewrite only `qwcId` values in the inclusive `12101000..12101009` set;
4. apply the same old-to-new mapping to every NG-cycle copy;
5. preserve row order, item, price, quantity, purchase flag, shop type, and
   every unrelated binder file byte-for-byte;
6. include the permutation in the seed request and seed-cache identity; and
7. refuse malformed, incomplete, duplicate, or out-of-domain mappings.

The goods-to-gate audit is now complete. `research/validation/shop_gate_witnesses.tsv`
ties every gate to a representative stock row and to the independently mined
badge goods id:

| Gate | Badge | Goods | Representative stock |
|---|---|---:|---|
| 12101000 | Saw Hunter Badge | 4110 | Saw Cleaver |
| 12101001 | Crow Hunter Badge | 4111 | Blade of Mercy |
| 12101002 | Powder Keg Hunter Badge | 4112 | Stake Driver |
| 12101003 | Old Hunter Badge | 4113 | Burial Blade |
| 12101004 | Sword Hunter Badge | 4114 | Kirkhammer |
| 12101005 | Radiant Sword Hunter Badge | 4115 | Ludwig's Holy Blade |
| 12101006 | Wheel Hunter Badge | 4116 | Logarius' Wheel |
| 12101007 | Cainhurst Badge | 4117 | Reiterpallasch |
| 12101008 | Spark Hunter Badge | 4118 | Tonitrus |
| 12101009 | Cosmic Eye Watcher Badge | 4119 | Rosmarinus |

All ten badge goods are now modeled as AP items. Saw, Radiant Sword, Cosmic Eye
Watcher, and Spark use their existing treasure/boss checks; Eileen, Djura,
Alfred, and Annalise expose their shared acquisition flags as checks. Every
reviewed natural badge lot is in the global suppression plan. The pool-safety
gate is therefore green.

Set `randomize_shops: true` in the player YAML to enable it. It defaults off.
Generation writes a deterministic bijection to the seed request. The launcher
includes that mapping in the cache identity, then its native parameter writer
changes all matching ordinary Bath rows in the already-suppressed binder and
reopens the output to prove that only `qwcId` changed. The seed-specific binder
hash and mapping are recorded in the launch manifest, so a stale cached overlay
cannot silently carry another seed's shops.

Run the executable gate before working on the option:

```powershell
python tools/audit_shop_randomization.py
```

It rejects duplicate or missing
gate/goods identities, and cross-checks each goods id against the independent
progression-item mine. `--json` produces machine-readable diagnostics.

The option shuffles *unlock ownership*, not inventory contents: for example,
the Saw stock group may require the Cainhurst Badge in one seed. Prices, items,
quantities, one-time purchase flags, Insight stock, and Chalice stock remain
vanilla.

## Inspection

The parameter writer has a read-only inspection mode:

```powershell
dotnet run --project tools/bb_suppression_writer -- `
  --inspect-shops gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

It emits every `ShopLineupParam` row and every decoded field as a tab-separated
record. This makes the gate audit reproducible against the same installed
binder the launcher will eventually edit.

The committed witnesses can be checked directly against that binder too:

```powershell
dotnet run --project tools/bb_suppression_writer -- `
  --audit-shop-gates research/validation/shop_gate_witnesses.tsv `
  gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

This refuses a missing or duplicate gate, a changed representative row, a
non-Blood-Echo-shop witness, or a mismatched item identity.
