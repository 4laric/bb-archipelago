# Suppressing vanilla pickup awards

Status: the complete Central Yharnam plan builds and reopens successfully;
installation and in-game canary validation remain pending.

## Why suppression is at ItemLotParam

Archipelago must preserve the pickup interaction and its acquisition flag while
preventing the original item from satisfying its own randomized placement.
Editing the existing ItemLotParam row in place does exactly that. Repointing an
MSB treasure would move the acquisition flag, while clearing a lot completely
could skip the award path that sets it.

The plan therefore replaces the awarded slot with one Blood Vial and preserves:

- the ItemLotParam row ID;
- the acquisition flag;
- every unrelated slot and field;
- every unrelated binder file.

## Slice plan

`tools/plan_vanilla_suppression.py` consumes the active world contract rather
than the whole future model. Since slice 3 (Cathedral Ward, Old Yharnam, the
Blood-starved Beast) its canonical plan contains **178 edits and zero
refusals**:

- 164 physical pickups on the reviewed manifest;
- the Radiant Sword Hunter Badge, which ships from `data.py` under its own key;
- 13 continuation rows in shared-acquisition-flag award groups (Hunter Set,
  Top Hat, Black Church, Rumpled Yharnam, Charred Hunter Garb, and the m24_00
  chest whose flag is numbered in the m24_01 range).

Four of those edits are no-ops on the bytes: the Blood Vial x1 corpses in Old
Yharnam and Cathedral Ward already award exactly the placeholder. The writer
now records them as such, so "the row did not change" stays distinguishable
from "the write did not happen".

**The plan digest changed with slice 3.** A binder built for the slice-1 plan
no longer matches the seed's `plan_sha256`, and the client will refuse to arm
until the binder is rebuilt and reinstalled.

Saw Spear, Torch, Hunter attire, and the category-8 blood-gem row are all
covered. The planner records the original item category and item ID for every
edit. This is suppression evidence only; it does not infer a native grant
descriptor for unsupported equipment.

The two later-cycle replacement chests are not separate checks and are omitted
from the plan. They share physical placements with the first-cycle rows.

## Guarded writer

The v2 plan is consumed by both the CSV verifier and the SoulsFormatsNEXT native
writer. For each planned row they:

1. require the exact row, acquisition flag, category, and item ID;
2. require exactly one matching slot;
3. replace that slot's category with goods (`4`), item ID with Blood Vial
   (`1000`), and quantity with one;
4. serialize and reopen the output;
5. prove that only the planned category/item/quantity fields changed and every
   acquisition flag survived.

The native writer preflights every edit before mutation, refuses in-place
writes, refuses to overwrite output, and requires explicit `--apply`:

```powershell
.\tools\build_vanilla_suppression.ps1 `
  -SoulsFormatsNextRoot C:\path\to\SoulsFormatsNEXT `
  -OutputRoot .\work\vanilla-suppression-build `
  -Apply
```

Despite the switch name, this command only creates a separate build directory.
It never installs the binder. The directory contains:

- `suppression-plan.json`;
- the rewritten `gameparam.parambnd.dcx`;
- `build-manifest.json` with source, plan, and output SHA-256 values and
  `installed: false`.

The complete slice-1 54-edit binder was built and reopened against the committed
game inputs. That proves the offline transformation, not in-game behavior.

## Installation witness

Every active fixed pickup declares `vanilla_award_suppressed: true`, so the seed
requires an installation witness. The native client will not construct its
runtime loop until:

- the manifest format matches the seed;
- the canonical plan SHA-256 matches the seed;
- the configured installed gameparam path exists; and
- the installed binder's independent SHA-256 equals the manifest output hash.

A build artifact sitting in `work/` is not installation evidence. Replacing the
installed binder after the manifest was created also fails closed.

## Remaining live test

Use the Iosefka courtyard Bullets lot (`2410800`, flag `52410800`) as the first
canary:

1. install the generated binder through the normal BBLauncher patch path;
2. confirm the pickup remains visible and collectible;
3. confirm the placeholder is awarded instead of ten bullets;
4. confirm the direct flag reader sees `52410800` become true;
5. reload and confirm the pickup does not return.

Once that succeeds, repeat one equipment-shaped pickup—Saw Spear is ideal—to
prove that changing an original category-0 award slot to the category-4
placeholder behaves the same way in game.
