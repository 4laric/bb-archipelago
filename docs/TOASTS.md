# Bloodborne item-name presentations

The client overlay already shows truthful sent and received item names. This
document covers the separate, optional path that makes Bloodborne's own pickup
popup name an Archipelago placement.

## Current safety boundary

Every generated seed contains a `toast_placeholders` plan, but the plan has
`enabled: false`. The launcher does not apply it. This is intentional: static
inspection can prove the archive edits are internally consistent, but cannot
prove that Bloodborne reads the replacement archive at runtime or that its
pickup presentation remains non-blocking.

`BBToastWriter` is therefore a build/research tool, not part of an ordinary
launch. It requires both `--probe-confirmed` and `--apply`, rejects an inert
plan, refuses occupied goods IDs, and refuses any clone whose Blood Vial source
has acquired a modal-dialog ID or unique-item flag.

## Seed policy

- Goods IDs `900000..900999` are reserved for pickup-name clones. The bundled
  `EquipParamGoods` census proves the range is empty.
- Allocation is deterministic by network location ID.
- Only progression and useful placements receive a named clone. Filler keeps
  goods 1000, bounding inventory clutter.
- Names are at most 48 characters and use `Item name (recipient)`.
- The goods row is cloned from Blood Vial 1000, preserving its ordinary,
  stackable acquisition shape.

## One required live verdict

Build one canary plan with one entry and run `BBToastWriter` against copies of
the installed gameparam, paramdef, and English `item.msgbnd.dcx`. Place both
outputs in the managed overlay, then acquire that exact physical lot.

The feature may be promoted only if all of the following are witnessed:

1. The lower-corner popup displays the canary FMG text.
2. No modal `press X` dialog appears and input is never captured.
3. Reloading the game still reads the replacement archive (not a stale cache).
4. The dummy can enter storage and return without corrupting inventory.
5. A shop opens normally with the dummy present.

Record `mark popup` or `mark modal` in the client console beside the pickup and
export diagnostics. A modal result is a permanent refusal for this approach,
not a prompt to call the modal path from the client.

## What remains after a passing verdict

Promotion is deliberately mechanical: change the seed-plan activation verdict,
compose the two writer outputs into the seed-owned overlay, and extend overlay
ownership and Doctor hashing to include `msg/engus/item.msgbnd.dcx`. Received
items continue to use client-window toasts until the native non-blocking queue
is separately mapped; game-modal notifications are never an acceptable
fallback.
