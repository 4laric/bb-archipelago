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

Boss `AwardItemLot` payouts are censused separately from placed checks. Sixteen
payout-only rows are suppressed: ordinary ritual materials, Coldblood, armour,
runes/gems, repeat-cycle Insight substitutes, Amelia's Gold Pendant and the
Orphan's Kos Parasite. The boss defeat event remains the AP check and every lot
acquisition flag is preserved byte-for-byte.

The Sword Hunter Badge, Old Hunter Badge, and Gold Pendant are randomized
category-4 goods. Their reviewed natural award rows are suppressed, so badge
shop stock and Pendant conversion unlock on AP receipt rather than boss death.
The `4114` associated with Cleric Beast is the badge's **goods id**, not the
lot's `getItemFlagId` (which is `-1`). Blood-starved Beast, Amygdala and
Ebrietas deliberately keep their chalices because Chalice Dungeon progression
is outside the randomized world.

## Slice plan

`tools/plan_vanilla_suppression.py` consumes the active world contract rather
than the whole future model. The current full-world canonical plan contains
**621 edits and zero refusals**. It includes:

- 164 physical pickups on the reviewed manifest;
- the Radiant Sword Hunter Badge, which ships from `data.py` under its own key;
- 13 continuation rows in shared-acquisition-flag award groups (Hunter Set,
  Top Hat, Black Church, Rumpled Yharnam, Charred Hunter Garb, and the m24_00
  chest whose flag is numbered in the m24_01 range);
- lot 31000, the Oedon Tomb Key's EMEVD award (see below);
- lot 55100000, Wet Nurse's shuffled Umbilical Cord award;
- 21 reviewed boss/exact awards, including every natural source of the randomized
  boss badges and Amelia's randomized Gold Pendant;
- every seeded fixed-location award and its related shared-flag rows.

## The script-award lane, and a lot with no flag

Most edits are found by search: resolve the randomized item to the one row that
awards it. The planner refuses two shapes rather than guessing past them — an
item awarded by several rows, and a row with no acquisition flag. Both refusals
are requests for a decision, and `SCRIPT_AWARD_SUPPRESSIONS` in
`worlds/bloodborne/runtime_bindings.py` is where the decision is written down.
`plan_script_awards` re-checks that record against the corpus every time it
plans, so a review that has gone stale becomes a refusal instead of a silent
omission.

The Oedon Tomb Key is the first entry, and it hits both shapes:

- **It is a script award.** `event/m24_01_00_00.emevd.dcx.js:1394` — event
  12411800 waits on `CharacterDead(2410810 || 2410811)` and, host-only, calls
  `AwardItemLot(31000)` and then `SetEventFlag(2412/9457/5910)`. There is no MSB
  treasure and no NpcParam drop for it.
- **Its lot has no acquisition flag.** Lot 31000 awards category 4 item 4000
  (`聖堂街Bの鍵`) in slot 01 with `getItemFlagId = -1`. The plan records `-1`
  literally, because both writers preflight "the row's flag is what the plan
  says" before touching anything, and inventing a flag for a row that has none
  would make that check assert a fiction. Nothing is lost: this fight's check is
  Gascoigne's own defeat flag 12411800, which the same event sets on the same
  line regardless of what the lot awards.
- **A second lot awards the same goods and is deliberately not edited.** Lot
  27100000 (`ガスコイン神父（獣）　聖堂街B`) is reachable from nothing in the
  committed corpus: it appears in no MSB treasure (`mined/msb_treasures.tsv`,
  146,152 rows), no MSB enemy drop field (`mined/msb_enemies.tsv`), no NpcParam
  item-lot column, and no committed EMEVD decompile. It is recorded in the
  declaration as reviewed-and-unreachable, and a test re-counts that census so
  the absence is measured rather than asserted. If a future corpus does reach
  it, the planner refuses instead of shipping a half-suppression.

The Cathedral Ward door itself is untouched. Object 2411304 is the generic key
door: `m24_01_00_00.emevd.dcx.js:168` initializes event 12410110 slot 5 with
`objParameterId 2410080` and persistent flag 12411307, so the item requirement
lives in `ObjActParam` row 2410080 and no `PlayerHasItem(Goods, 4000)` condition
exists anywhere in the event files. The committed mine records goods 4000 in
that row's `spQualifiedId`; `tests/test_objact_params.py` locks the relationship
down. Suppressing the award changes what the player receives, not what the door
asks for.

### Owner validation checklist (runtime behaviour)

The param relationship is now cited. These runtime checks still decide whether
the complete shuffled-key path behaves correctly in the running game.

1. **A suppressed script-award lot awards the placeholder without breaking the
   event.** Kill Father Gascoigne on a suppressed binder and confirm: one Blood
   Vial is received instead of the key; flag 12411800 is set (the AP check
   reports); flags 2412, 9457 and 5910 are set; and the achievement/world-state
   tail of event 12411800 still runs. A `SetEventFlag` that stops firing because
   the award ahead of it changed would be silent and would strand the seed.
2. **An AP-granted goods 4000 opens door 2411304.** With no vanilla key ever
   received, take the key from Archipelago and confirm the Tomb of Oedon door
   opens and sets flag 12411307. The item relationship is mined; this validates
   that a client-granted copy behaves like a native copy at runtime. If the door
   instead reads an event flag, suppression is not enough on its own and the
   door needs its own edit.
3. **The grant survives an absent stack.** Goods 4000 is `maxNum 1`,
   `isOnlyOne 0` — the same shape as the Hunter Chief Emblem, and the shape
   behind the #70-class risk that a native grant into a slot the inventory has
   never held behaves differently from a top-up of an existing stack. Grant the
   key on a character that has never carried one, then reload the save and
   confirm it is still there.

Record the results in `docs/PLAYTESTING.md` with serial and AppVer; only then
may either claim be relabelled.

Four of those edits are no-ops on the bytes: the Blood Vial x1 corpses in Old
Yharnam and Cathedral Ward already award exactly the placeholder. The writer
now records them as such, so "the row did not change" stays distinguishable
from "the write did not happen".

**The plan digest changed again with the Oedon Tomb Key.** A binder built for
any earlier plan no longer matches the seed's `plan_sha256`, and the client will
refuse to arm until the binder is rebuilt and reinstalled. `build.ps1` caches its
output in `work\vanilla-suppression-build` and keeps that directory if it
exists, so **delete `work\vanilla-suppression-build` first** or the rebuild is a
no-op that reinstalls the stale binder.

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
