# Real icons on named checks (follow-up to toast placeholders)

## Goal

Physical-pickup popups already show the real seeded item's name and recipient
(`worlds/bloodborne/toast_placeholders.py`, `tools/bb_toast_writer/Program.cs`,
shipped in the Unreleased changelog entry "Physical pickup popups now show the
randomized item and recipient"). Every one of those popups currently shows the
same generic icon, because every entry is cloned from one fixed template row.
The goal: a check for a native Bloodborne item shows that item's own icon; a
check for an item from another game in the multiworld shows a shared
Archipelago icon (a flower, matching the convention other AP games use for
their own generic item icon) instead.

This document exists because neither half of that is a small, obviously-safe
change -- it needs static research this contributor cannot do (no local game
dump, no live shadPS4 session; see `no-local-game-dump` in project memory) --
and docs/CONTRIBUTING-LIVE-PROBES.md is explicit that a probe not already
proven against a known case is not ready to be pointed at operator time.
Nothing here proposes touching game files or asking for a playtest yet.

## What is already established

`tools/bb_toast_writer/Program.cs` clones one fixed source `GoodsParam` row
(`source_goods_id: 1000`, the Blood Vial, set in `build_toast_placeholder_plan`)
for every check, renaming it and repointing the owning `ItemLotParam` row at
the clone. The writer already refuses to proceed if that source row's two
safety-critical fields (`yesNoDialogMessageId`, `isOnlyOne` -- non-modal,
stackable) have drifted, rather than silently inheriting a different shape;
any icon field this adds should follow the same pattern, not a bare
`row["..."] = value` with no check. Every field the clone doesn't explicitly
overwrite -- icon included -- is whatever the Blood Vial row has. This is why
every check's popup looks the same today regardless of what it actually
contains.

## Mechanism this proposes

Same shape as the existing clone-and-rename: add an `icon_id` (or equivalent)
to each `ToastPlaceholder` entry in the plan, and have the writer set that
field on the clone instead of leaving it inherited. Two sources per entry:

- **Native Bloodborne item**: the icon the vanilla item already uses, read
  from its own param row.
- **Foreign-game item** (the common multiworld case: a check holds an item
  from another game entirely): a fixed Archipelago-flower icon ID, the same
  for every such check.

## What is not yet known

1. **The field name and its semantics.** This repo has never read or written
   an icon field on any param, on any writer (`grep`-confirmed: no `icon`
   anywhere in `tools/*/Program.cs`, `bb_launcher/`, or `worlds/bloodborne/`).
   Bloodborne's param field names come from paramdefs embedded in the game's
   own param binder (see `ReadMatchingDefinition` in `Program.cs`), not from
   anything checked into this repo or the pinned SoulsFormatsNEXT fork (that
   fork carries the `PARAMDEF` reader/writer code, not Bloodborne's own
   definitions). Reading the real field name needs an extracted copy of
   Bloodborne's `GoodsParam` paramdef, which this environment does not have.
2. **Whether icon IDs are shared across param types.** In several other
   FromSoftware games a single icon-atlas index space is referenced from
   goods, weapon, armor, and accessory params alike; whether that holds for
   Bloodborne specifically, and whether a `GoodsParam` row can safely
   reference an icon that a weapon/armor/gem row normally owns, is unverified
   here.
3. **Whether a flower-like icon already exists in Bloodborne's own icon
   atlas** that could be reused for the Archipelago-item case with zero new
   assets, or whether this needs a new texture added to the built overlay (a
   materially bigger task: new DDS/TPF content, not just a param edit, and a
   new kind of asset this project has not shipped before).

## Proposed next steps

**Phase 1 -- static research, no game session needed.** Whoever has an
extracted Bloodborne `GoodsParam`/`EquipParamWeapon`/`EquipParamProtector`
paramdef (or the existing research dump this repo's own tooling was built
from) should answer, purely by reading definitions and existing vanilla
values, offline:

- the exact icon field name(s) per param, and their value range;
- for a handful of known items (e.g. a Blood Vial, a known weapon, a known
  armor piece), whether their vanilla icon IDs sit in one shared numbering
  space or are scoped per param;
- candidate existing icon IDs that already render as a flower or something
  close enough, from the same static inspection, without needing to load the
  game to look at each one.

This is observation of already-dumped data, not a probe against the running
game, so it does not need operator playtest time or a pre-registered
prediction under docs/CONTRIBUTING-LIVE-PROBES.md.

**Phase 2 -- a live probe, once phase 1 has a candidate field name and icon
IDs.** Only then does this need operator time, and only for a narrow,
low-stakes check:

- *Positive control*: a toast-placeholder clone whose icon field is set to a
  known native item's own vanilla icon ID renders identically to that item's
  own vanilla inventory icon.
- *H: `icon_field_is_shared_across_params`*: a clone whose icon field is set
  to a weapon's or armor's vanilla icon ID (not a goods icon) renders that
  same icon on the goods-type clone. False: it renders the wrong icon, a
  broken/placeholder icon, or a visibly different texture -- meaning icon IDs
  are not shared across param types, and native items would need per-category
  handling (goods-sourced icons only, or a lookup table) rather than a single
  uniform field.
- *H: `flower_icon_id_renders_as_a_flower`*: the candidate reused-vanilla-icon
  ID (or newly added texture, if phase 1 finds no reusable candidate) renders
  as a recognizable flower on a foreign-item check.

This is a single short session, reusing the existing toast-writer plumbing
with one extra field -- not a new probe harness.

## Rejected for now

- **Adding a new custom texture before ruling out reuse.** A bigger asset
  pipeline this project has not built (new DDS/TPF content, atlas packing,
  build-time inclusion). Only worth it if phase 1 finds no existing icon that
  reads as a flower.
- **Guessing a field name and shipping it.** Exactly the mistake
  docs/CONTRIBUTING-LIVE-PROBES.md's `#214` table catalogs: an unverified
  classifier trusted before it was tested against a known case.
