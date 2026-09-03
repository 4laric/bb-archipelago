# Equipment grant census

One throwaway-save session that force-grants every weapon and attire binding
through the client's own delivery lane and records, per item, whether the
game produced a visible inventory record. It answers #330 phase 2's first
question: which of the inferred-id equipment bindings actually deliver.

This request follows [CONTRIBUTING-LIVE-PROBES.md](CONTRIBUTING-LIVE-PROBES.md).

## Why

Beta 1 (Klubb, 2026-09-03): Chikage and Reiterpallasch delivered visibly;
Burial Blade and Ludwig's Holy Blade were acknowledged by the client and never
appeared. All four carry the same `param_id_inferred` evidence and all four
rows exist in EquipParamWeapon, so neither the id source nor the param row
explains it. The client completes an equipment grant on either a verified slot
readback or on execution evidence alone, and the log line does not say which.
The delivery diagnostics do.

## Positive control

Before the first census command, the operator delivers one item known to work
through the same lane, and the verdict tool must classify it `verified_slot`:

```
give <ap id of Saw Spear> CONFIRM
```

`python tools/equipment_grant_census.py script` prints the id. If the control
comes back `execution_evidence_only`, the session ends there; the instrument
is not reading back slots and no census result would mean anything.

## Prediction

- A binding that delivers correctly: `verified_slot`, `inferred_destination`
  held (or storage, which the operator can confirm in the box), and the item
  visible in the equipment menu.
- A binding with the Rifle Spear/Torch shape: `execution_evidence_only`, a
  real `native_result`, and nothing in the menu.
- Probe broken: the control fails, or every row is `execution_evidence_only`
  including items the beta already delivered visibly (Chikage, Reiterpallasch).

## Script

1. Fresh throwaway save, ordinary seed with the full pool so every equipment
   id is in the contract (`give` refuses ids outside it). Uncanny variants and
   attire need their options on if they are to be covered.
2. Reach gameplay, wait for `delivery ready`.
3. Run the control above. Wait for the `AUDIT` line and the equipment menu.
4. Paste the commands from `equipment_grant_census.py script` one at a time.
   After each: wait for the `AUDIT rescue give ... queued` line, then for the
   delivery line, then open the equipment menu and record `yes`, `no`, or
   `storage` in the UI sheet:

   ```
   ap_item_id	seen
   12255248	no
   ```

   Do not batch. The operator lane is one grant at a time and the readback
   window is short.
5. Save, quit to title, reload, and note whether anything changed.
6. Send `delivery-diagnostics.jsonl`, `client.log`, and the UI sheet.

Cost: about 90 grants at roughly 15 seconds each, one save, no restarts.

## Reading the result

```
python tools/equipment_grant_census.py verdict delivery-diagnostics.jsonl --ui ui.tsv
```

One row per grant with the completion branch. The interesting set is every
row where `branch` is `execution_evidence_only` or `ui_seen` is `no`. Those
bindings are not deliverable on the native lane and are the candidates for
the AwardItemLot lane in #330, or for exclusion in the meantime.

Post the verdict table on #330 and record the session in
RESEARCH-BASELINE with the image hash and client build.
