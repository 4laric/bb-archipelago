# Starting attire research

Issue: bb-archipelago#234.

## Corpus finding

The bundled `gameparam.parambnd.dcx` and matching Paramdef contain a direct
starting-attire surface. `CharaInitParam` rows 2000 through 2009 are the ten
real origin rows (their internal names say “initial character” plus the origin
name). Every row carries the same four exact fields and values:

| field | protector id | evidenced slot |
|---|---:|---|
| `equip_Helm` | 230000 | head |
| `equip_Armer` | 231000 | body |
| `equip_Gaunt` | 232000 | arms |
| `equip_Leg` | 233000 | legs |

`EquipParamProtector` identifies those four rows as the initial-equipment head,
body, arms, and legs respectively. Its literal slot flags agree: `headEquip`,
`bodyEquip`, `armEquip`, and `legEquip` each select exactly the corresponding
row.

Rows 3000 through 3009 are a parallel character-creation-screen block. They use
the same body, arms, and legs, while `equip_Helm` is `-1`. This means an
implementation must decide deliberately whether to change only the final
character rows or also make the creation preview reflect the seed choice.

The read-only command below reproduces this finding from the bundle rather than
depending on this document's transcription:

```powershell
dotnet run --project tools/bb_suppression_writer/BBSuppressionWriter.csproj -- `
  --inspect-starting-attire gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

## What this proves

- Bloodborne has explicit initial-attire parameter fields for every origin.
- A seed-owned GameParam implementation can cover every origin without live
  equip-slot writes.
- The selected values are `EquipParamProtector` row ids, so choices can be
  validated against the protector table and its body-slot flags.

## What still needs a witness

The corpus does not prove when the game consumes these rows. Before exposing a
YAML option, build one canary binder that changes all ten 2000-series rows to a
reviewed four-piece set, then create a fresh character and verify:

1. the four pieces are present and equipped after character creation;
2. they survive the first wake-up, death, Dream warp, save/reload, and launcher
   restart;
3. an already-created character is unchanged;
4. changing the 3000-series preview rows is cosmetic only and does not create
   duplicate inventory instances.

Only after that witness should the implementation add deterministic seed
choices and the `randomize_starting_attire` option.

## Reviewed choice catalog (not activated)

`worlds/bloodborne/starting_attire_catalog.tsv` is the bounded player-facing
catalog for the next canary. It contains 17 coherent four-piece sets (68 rows),
with one `EquipParamProtector` id per literal slot and an explicit native grant
descriptor (`category:item:quantity`, always `1:<protector id>:1`). Names were
cross-checked against the English item names already present in the fixed-lot
catalog; a set is admitted only when the remaining ids form the same contiguous
head/body/arms/legs parameter family. Incomplete families, transformation
pieces, wandering/NPC duplicates, bloodied NPC variants, and naked/system rows
are excluded rather than guessed into completeness.

The native corpus audit proves that every reviewed id still exists and that its
four literal slot flags identify exactly the catalogued slot:

```powershell
dotnet run --project tools/bb_suppression_writer/BBSuppressionWriter.csproj -- `
  --audit-starting-attire-catalog `
  worlds/bloodborne/starting_attire_catalog.tsv `
  gameparam.parambnd.dcx paramdef.paramdefbnd.dcx
```

`build_starting_attire_choice()` supplies a domain-separated SHA-256 selection
over complete sets. The same AP seed/slot string always selects the same set;
pieces can never be mixed between sets, and the loader refuses malformed slot
orders, duplicate ids, or mismatched grant descriptors. This is deliberately a
library layer only: slot data does not call it, there is no YAML option, and the
writer's existing canary is still the only write path until a fresh-save witness
establishes consumption and persistence.

## Packaged canary writer

The native writer now builds that exact canary without weakening the launcher
or publishing an unvalidated YAML option. The command is refusal-safe: input
and output must differ, an existing output is never overwritten, every target
must be one real `EquipParamProtector` row exclusively marked for the requested
body slot, and all ten `2000..2009` origin rows must exist. It edits only the
four attire fields on those ten rows and verifies every unrelated row, field,
and binder file after serialization.

The first witness uses the coherent Charred Hunter set. Its four protector rows
are `10000`, `11000`, `12000`, and `13000`; the writer has validated their
literal head/body/arms/legs slot flags against the installed Paramdef.

```powershell
dotnet run --project tools/bb_suppression_writer/BBSuppressionWriter.csproj -- `
  --write-starting-attire-canary gameparam.parambnd.dcx paramdef.paramdefbnd.dcx `
  charred-canary.parambnd.dcx 10000 11000 12000 13000 --apply
```

The canary deliberately leaves the `3000..3009` character-creation preview
rows unchanged. A fresh character should therefore show the vanilla preview,
then either receive and equip the Charred Hunter set when the real origin row
is consumed or remain vanilla. That single transition answers the consumption
timing question without risking duplicate preview grants.
