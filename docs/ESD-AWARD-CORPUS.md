# Dialogue award corpus

Bloodborne has a third vanilla-award path beyond placed `ItemLotParam` rows and
EMEVD `AwardItemLot`: talk ESDs can award lots during NPC dialogue. The current
committed `research/bb_inputs.db` does **not** contain those scripts, so the
project cannot yet claim complete coverage or safely suppress any dialogue
award. In particular, Iosefka's Blood Vial remains a known vanilla leak.

## Rebuild and census

Use ESDLang to decompile the CUSA03173 01.09 talk binders to Python beneath:

```text
<dump-root>/bloodborne_artifacts/talk/**/*.py
```

Then rebuild and verify the private inputs bundle:

```powershell
python tools/bb_inputs.py --build <dump-root>
python tools/bb_inputs.py --check-esd-coverage
python tools/mine_esd_awards.py
```

The miner follows ESDLang helper calls and resolves literal keyword arguments,
including the common `helper(lot1=123) -> AwardItemLot(lot1)` shape. It records
both `AwardItemLot` variants, the innermost statically visible event-flag gate,
and unresolved runtime expressions. Every emitted row is deliberately marked
`review_required`; the catalog is evidence, not an edit plan.

## Suppression admission gate

A dialogue award may enter suppression only when all of these are established:

1. its resolved lot joins to the expected item and quantity;
2. the gate is proven to be the one-shot received flag, rather than an unrelated
   quest-state condition;
3. leaving the dialogue interaction intact while replacing its payout is known
   not to break the NPC state machine;
4. an ESD compiler can round-trip the exact source binder and the launcher can
   install the result atomically with the seed contract;
5. a live witness proves the replacement suppresses only the payout and that
   the corresponding AP check fires once.

Until then, no ESD edit is produced and no acquisition flag is inferred. Awards
with no lot argument or only an engine/covenant side effect remain catalogued as
unresolved rather than disappearing from the accounting.

## Current blocker

The repository now has the packer source, a strict `--check-esd-coverage` gate,
and the reproducible census. The owner still needs to provide the 271-file,
20-bundle decompiled corpus previously used for progression research, rebuild
`research/bb_inputs.db`, and identify a Bloodborne-compatible ESD compile and
repack path. Only after that can the slice audit and guarded patch planner be
populated with real award rows.
